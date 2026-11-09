"""Gnani Shop payments: Wallet + Cash on Delivery, Mode A (human tap) and
Mode B (optional agent autopay), and the guarantees around them:

- money moves only through POST /api/payments/pay (BUYER-only) or Mode B autopay
- an agent key can never approve its own pending action
- the same order is never charged twice
- autopay is wallet-only, off by default, bounded by its own limit
- several agents together can't exceed the account-wide agent limit
- removing an item gives an agent its spend headroom back
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth.principal as principal_module
from app.auth.security import create_access_token, generate_agent_key, hash_agent_key
from app.core.config import settings
from app.database import Base, get_db
from app.llm.gateway import GatewayResult
from app.llm.gateway import ToolCall as GatewayToolCall
from app.main import app
from app.models.agent_credential import AgentCredential
from app.models.order import Order
from app.models.user import User
from app.models.wallet import WalletEntry
from app.orders import service as order_service
from app.orders.state_machine import OrderStatus
from app.payments import service as payment_service
from app.payments import wallet as wallet_service
from app.repositories import cart_repo, product_repo
from app.schemas.cart import CartItemCreate
from app.services import cart_service

BUYER = "buyer-pay-1"


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def client(session_factory, monkeypatch):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(principal_module, "SessionLocal", session_factory)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


def _seed(session_factory, user_id: str = BUYER) -> None:
    db = session_factory()
    try:
        db.add(User(id=user_id, email=f"{user_id}@example.test", name=user_id, google_sub=None, role="BUYER"))
        for sku, price in (("GRO-004", 2800), ("GRO-001", 30000), ("DAI-001", 6000)):
            product_repo.upsert(
                db,
                {
                    "sku": sku, "name": f"Item {sku}", "brand": "Test", "category": "groceries",
                    "price_paise": price, "unit": "1 pc", "stock": 100, "description": "plain item",
                    "tags": [], "cost_paise": price // 2,
                },
            )
        db.commit()
    finally:
        db.close()


def _token(user_id: str = BUYER) -> dict:
    return {"Authorization": f"Bearer {create_access_token(sub=user_id, email=f'{user_id}@example.test', role='BUYER')}"}


def _order_for(db, user_id: str, items: list[tuple[str, int]], session_id: str = "s1") -> Order:
    for sku, qty in items:
        cart_service.add_item(db, user_id, CartItemCreate(sku=sku, quantity=qty))
    cart = cart_repo.get_or_create_active_cart(db, user_id)
    return order_service.create_or_get_order(db, user_id=user_id, session_id=session_id, cart=cart).order


def _agent(session_factory, *, owner=BUYER, scopes=None, limit=100_000, autopay=False, autopay_limit=0, mode="EXTERNAL"):
    raw = generate_agent_key()
    db = session_factory()
    try:
        cred = AgentCredential(
            owner_user_id=owner, name="test-agent", key_hash=hash_agent_key(raw), delivery_mode=mode,
            scopes=scopes or ["search_products", "add_to_cart", "view_cart", "remove_from_cart", "initiate_payment"],
            spend_limit_paise=limit, status="ACTIVE", autopay_enabled=autopay, autopay_limit_paise=autopay_limit,
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        return cred.id, raw
    finally:
        db.close()


def _call(name: str, args: dict) -> GatewayResult:
    return GatewayResult(
        content=None, tool_calls=[GatewayToolCall(id=f"c-{name}", name=name, arguments_raw=json.dumps(args))],
        model_used="test-model", fallback_used=False, latency_ms=1,
    )


def _final(text: str) -> GatewayResult:
    return GatewayResult(content=text, tool_calls=[], model_used="test-model", fallback_used=False, latency_ms=1)


def _chat_as_agent(client, key: str, session_id: str, message: str, script: list[GatewayResult]) -> dict:
    it = iter(script)
    with patch("app.agent.harness.gateway.call", side_effect=lambda *a, **k: next(it)):
        res = client.post("/api/agent/chat", headers={"X-Agent-Key": key}, json={"session_id": session_id, "message": message})
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------- wallet


def test_new_wallet_starts_with_the_demo_balance(session_factory, db):
    _seed(session_factory)
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise


def test_wallet_payment_debits_once_even_when_repeated(session_factory, db):
    _seed(session_factory)
    order = _order_for(db, BUYER, [("GRO-004", 2)])
    first = payment_service.pay_order(db, order, method="wallet", authorized_by="human_tap")
    second = payment_service.pay_order(db, order, method="wallet", authorized_by="human_tap")

    assert first.status == "PAID" and first.money_moved
    assert second.money_moved is False  # already placed — nothing charged again
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise - 5600
    debits = db.query(WalletEntry).filter(WalletEntry.kind == "debit").all()
    assert len(debits) == 1


def test_insufficient_balance_fails_cleanly_and_can_retry_as_cod(session_factory, db):
    _seed(session_factory)
    order = _order_for(db, BUYER, [("GRO-001", 8)])  # ₹2,400 > ₹2,000 demo balance
    failed = payment_service.pay_order(db, order, method="wallet", authorized_by="human_tap")
    assert failed.status == "FAILED"
    assert "Not enough wallet balance" in failed.message
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise  # untouched

    retry = payment_service.pay_order(db, order, method="cod", authorized_by="human_tap")
    assert retry.status == "CONFIRMED_COD"
    assert retry.money_moved is False


def test_top_up_is_idempotent_per_request_key(session_factory, db):
    _seed(session_factory)
    wallet_service.top_up(db, BUYER, 50_000, request_key="req-abc-1")
    wallet_service.top_up(db, BUYER, 50_000, request_key="req-abc-1")
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise + 50_000


def test_cod_commits_without_moving_money_then_merchant_collects(session_factory, db):
    _seed(session_factory)
    order = _order_for(db, BUYER, [("DAI-001", 1)])
    result = payment_service.pay_order(db, order, method="cod", authorized_by="human_tap")
    assert result.status == OrderStatus.CONFIRMED_COD.value
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise

    order_service.mark_cod_collected(db, order)
    assert order.status == OrderStatus.PAID.value


def test_chaos_provider_timeout_fails_without_charging(session_factory, db, monkeypatch):
    _seed(session_factory)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "chaos_fault", "PAYMENT_PROVIDER_TIMEOUT")
    order = _order_for(db, BUYER, [("GRO-004", 1)])
    result = payment_service.pay_order(db, order, method="wallet", authorized_by="human_tap")
    assert result.status == "FAILED"
    assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise


# ---------------------------------------------------------------- HTTP: who can pay


def test_human_pays_through_the_pay_endpoint(client, session_factory):
    _seed(session_factory)
    db = session_factory()
    order_id = _order_for(db, BUYER, [("GRO-004", 1)]).id
    db.close()
    res = client.post("/api/payments/pay", headers=_token(), json={"order_id": order_id, "method": "wallet"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "PAID"
    assert body["authorized_by"] == "human_tap"
    assert body["wallet_balance_paise"] == settings.wallet_starting_balance_paise - 2800


def test_agent_key_cannot_reach_the_pay_endpoint(client, session_factory):
    _seed(session_factory)
    _, key = _agent(session_factory)
    db = session_factory()
    order_id = _order_for(db, BUYER, [("GRO-004", 1)]).id
    db.close()
    res = client.post("/api/payments/pay", headers={"X-Agent-Key": key}, json={"order_id": order_id, "method": "wallet"})
    assert res.status_code == 403


def test_agent_key_cannot_switch_on_its_own_autopay(client, session_factory):
    _seed(session_factory)
    cred_id, key = _agent(session_factory)
    res = client.post(f"/api/agents/{cred_id}/autopay", headers={"X-Agent-Key": key}, json={"enabled": True})
    assert res.status_code == 403


# ---------------------------------------------------------------- Mode A vs Mode B


def test_mode_a_agent_payment_waits_for_the_owner_and_agent_cannot_approve(client, session_factory):
    _seed(session_factory)
    cred_id, key = _agent(session_factory)  # autopay OFF (default)
    _chat_as_agent(client, key, "sess-a", "add salt", [_call("add_to_cart", {"sku": "GRO-004", "quantity": 1}), _final("Added.")])
    body = _chat_as_agent(client, key, "sess-a", "pay", [_call("initiate_payment", {})])

    assert body["status"] == "awaiting_confirmation"
    assert body["pending"]["rule_name"] == "AgentAutopayRule"

    # The agent key may not approve its own pending payment...
    denied = client.post("/api/agent/confirm", headers={"X-Agent-Key": key}, json={"session_id": "sess-a", "approve": True})
    assert denied.status_code == 403

    # ...it shows up in the owner's pending list...
    pending = client.get(f"/api/agents/{cred_id}/pending", headers=_token())
    assert pending.status_code == 200
    assert [p["session_id"] for p in pending.json()] == ["sess-a"]

    # ...and the owner approves it, which creates the order (no money yet).
    with patch("app.agent.harness.gateway.call", side_effect=lambda *a, **k: _final("ok")):
        approved = client.post(f"/api/agents/{cred_id}/confirm", headers=_token(), json={"session_id": "sess-a", "approve": True})
    assert approved.status_code == 200
    payment = approved.json()["payment"]
    assert payment["status"] == "AWAITING_PAYMENT"

    db = session_factory()
    try:
        assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise
    finally:
        db.close()


def test_agent_may_decline_its_own_pending_action(client, session_factory):
    _seed(session_factory)
    _, key = _agent(session_factory)
    _chat_as_agent(client, key, "sess-d", "add", [_call("add_to_cart", {"sku": "GRO-004", "quantity": 1}), _final("Added.")])
    _chat_as_agent(client, key, "sess-d", "pay", [_call("initiate_payment", {})])
    with patch("app.agent.harness.gateway.call", side_effect=lambda *a, **k: _final("Okay, cancelled.")):
        res = client.post("/api/agent/confirm", headers={"X-Agent-Key": key}, json={"session_id": "sess-d", "approve": False})
    assert res.status_code == 200


def test_mode_b_autopay_pays_from_wallet_within_its_limit(client, session_factory):
    _seed(session_factory)
    cred_id, key = _agent(session_factory, autopay=True, autopay_limit=10_000)
    _chat_as_agent(client, key, "sess-b", "add", [_call("add_to_cart", {"sku": "GRO-004", "quantity": 2}), _final("Added.")])
    body = _chat_as_agent(client, key, "sess-b", "pay", [_call("initiate_payment", {})])

    assert body["status"] == "completed"
    assert body["payment"]["status"] == "PAID"
    assert body["payment"]["authorized_by"] == "agent_autopay"

    db = session_factory()
    try:
        assert wallet_service.balance_paise(db, BUYER) == settings.wallet_starting_balance_paise - 5600
        cred = db.get(AgentCredential, cred_id)
        assert cred.autopay_spent_paise == 5600
        order = db.query(Order).filter(Order.user_id == BUYER).one()
        assert order.payments[-1].authorized_by == "agent_autopay"
        assert order.payment_method == "wallet"
    finally:
        db.close()


def test_mode_b_over_the_autopay_limit_falls_back_to_the_owner(client, session_factory):
    _seed(session_factory)
    _, key = _agent(session_factory, autopay=True, autopay_limit=5_000)
    _chat_as_agent(client, key, "sess-c", "add", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Added.")])
    body = _chat_as_agent(client, key, "sess-c", "pay", [_call("initiate_payment", {})])
    assert body["status"] == "awaiting_confirmation"
    assert body["pending"]["rule_name"] == "AgentAutopayRule"
    assert "autopay limit" in body["pending"]["reason"]


def test_autopay_can_never_use_cash_on_delivery(session_factory, db):
    _seed(session_factory)
    order = _order_for(db, BUYER, [("GRO-004", 1)])
    with pytest.raises(payment_service.UnknownPaymentMethodError):
        payment_service.pay_order(db, order, method="cod", authorized_by=payment_service.AUTHORIZED_BY_AGENT_AUTOPAY)


def test_owner_turns_autopay_on_and_off(client, session_factory):
    _seed(session_factory)
    cred_id, _ = _agent(session_factory)
    on = client.post(f"/api/agents/{cred_id}/autopay", headers=_token(), json={"enabled": True})
    assert on.status_code == 200
    assert on.json()["autopay_enabled"] is True
    assert on.json()["autopay_limit_paise"] == settings.agent_autopay_default_limit_paise
    off = client.post(f"/api/agents/{cred_id}/autopay", headers=_token(), json={"enabled": False})
    assert off.json()["autopay_enabled"] is False


# ---------------------------------------------------------------- agent budgets


def test_removing_an_item_releases_the_agents_reservation(client, session_factory):
    _seed(session_factory)
    cred_id, key = _agent(session_factory, limit=10_000)
    _chat_as_agent(client, key, "sess-r", "add", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Added.")])
    _chat_as_agent(client, key, "sess-r", "remove", [_call("remove_from_cart", {"sku": "DAI-001"}), _final("Removed.")])
    db = session_factory()
    try:
        assert db.get(AgentCredential, cred_id).spent_paise == 0
    finally:
        db.close()
    # The freed headroom is usable again.
    body = _chat_as_agent(client, key, "sess-r", "add again", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Added.")])
    assert len(body["cart"]["items"]) == 1


def test_account_wide_limit_spans_all_agents(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "policy_account_agent_spend_cap_paise", 10_000)
    _seed(session_factory)
    # Each agent's own limit is generous; only the account-wide cap can object.
    _, key1 = _agent(session_factory, limit=50_000)
    _, key2 = _agent(session_factory, limit=50_000)
    _chat_as_agent(client, key1, "sess-x1", "add", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Added.")])

    # Agent 2 is within its OWN limit, but both together would exceed the account cap.
    from app.policy import engine as engine_module
    from app.agent import harness

    monkeypatch.setattr(harness, "_policy", engine_module.default_policy_engine())
    body = _chat_as_agent(client, key2, "sess-x2", "add", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Could not add.")])
    # Still only agent 1's line in the (shared) cart: agent 2's add was refused.
    assert sum(i["quantity"] for i in body["cart"]["items"]) == 1

    db = session_factory()
    try:
        from app.audit.service import AuditService

        decisions = [e for e in AuditService().get_trail(db, "sess-x2") if e.event_type == "policy_decision"]
        assert decisions[-1].decision == "DENY"
        assert decisions[-1].rule_name == "AccountSpendLimitRule"
    finally:
        db.close()


def test_agent_payment_is_not_double_counted_against_its_spend_limit(client, session_factory):
    """Regression guard: items an agent added are already reserved against its
    spend limit. Re-validating the cart at payment time must not count them a
    second time (a ₹56 cart under a ₹100 limit must still be payable)."""
    _seed(session_factory)
    _, key = _agent(session_factory, limit=10_000, autopay=True, autopay_limit=10_000)
    _chat_as_agent(client, key, "sess-n", "add", [_call("add_to_cart", {"sku": "DAI-001", "quantity": 1}), _final("Added.")])
    body = _chat_as_agent(client, key, "sess-n", "pay", [_call("initiate_payment", {})])
    assert body["payment"] is not None, body
    assert body["payment"]["status"] == "PAID"
