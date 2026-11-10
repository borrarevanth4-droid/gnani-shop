"""Every buyer's AI data is theirs alone.

Alice chats (text and voice), fills a cart and places an order. Bob — another
signed-in buyer — then tries every way in: reusing her conversation id for
chat, confirm and voice, reading her audit trail / replay, deleting her cart
line, reading her cart history and orders, re-ordering her basket, and
making himself the shop owner (who can read every conversation). All of it
must fail, and nothing Bob does may end up in Alice's conversation.
"""

import io
import json
import wave
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth.principal as principal_module
from app.auth.security import create_access_token
from app.core.config import settings
from app.database import Base, get_db
from app.llm.gateway import GatewayResult
from app.llm.gateway import ToolCall as GatewayToolCall
from app.main import app
from app.models.agent_session import AgentMessage
from app.models.audit_event import AuditEvent
from app.models.cart import Cart
from app.models.order import Order
from app.models.user import User
from app.repositories import product_repo

ALICE = ("user_alice", "alice@example.test")
BOB = ("user_bob", "bob@example.test")
SID = "s-alice-private"


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    f = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = f()
    for uid, email in (ALICE, BOB):
        db.add(User(id=uid, email=email, name=email, google_sub=None, role="BUYER"))
    product_repo.upsert(db, {
        "sku": "PET-001", "name": "Pedigree Adult Dry Dog Food", "brand": "Pedigree", "category": "pet_supplies",
        "price_paise": 74000, "unit": "3kg pack", "stock": 25, "description": "dog food", "tags": ["dog"],
        "cost_paise": 40000,
    })
    db.commit()
    db.close()
    yield f
    engine.dispose()


@pytest.fixture()
def client(factory, monkeypatch):
    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(principal_module, "SessionLocal", factory)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "merchant_emails", "owner@example.test")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _h(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(sub=user[0], email=user[1], role='BUYER')}"}


def _model_adds_dog_food():
    return [
        GatewayResult(content=None, tool_calls=[GatewayToolCall(
            id="c1", name="add_to_cart", arguments_raw=json.dumps({"sku": "PET-001", "quantity": 1}))],
            model_used="t", fallback_used=False, latency_ms=1),
        GatewayResult(content="Added dog food.", tool_calls=[], model_used="t", fallback_used=False, latency_ms=1),
    ]


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


@pytest.fixture()
def alice_has_data(client, factory):
    with patch("app.agent.harness.gateway.call", side_effect=_model_adds_dog_food()):
        r = client.post("/api/agent/chat", headers=_h(ALICE),
                        json={"session_id": SID, "message": "my secret: add dog food for Bruno"})
    assert r.status_code == 200, r.text
    db = factory()
    cart = db.query(Cart).filter(Cart.user_id == ALICE[0]).first()
    order = Order(user_id=ALICE[0], session_id=SID, cart_id=cart.id, amount_paise=74000, status="PAID",
                  idempotency_key="alice-order-1")
    db.add(order)
    db.commit()
    ids = {"order": order.id, "item": cart.items[0].id,
           "messages": db.query(AgentMessage).filter(AgentMessage.session_id == SID).count()}
    db.close()
    return ids


def test_bob_cannot_chat_or_confirm_in_alices_conversation(client, factory, alice_has_data):
    with patch("app.agent.harness.gateway.call", side_effect=AssertionError("model must not run")):
        assert client.post("/api/agent/chat", headers=_h(BOB),
                           json={"session_id": SID, "message": "what did she say?"}).status_code == 403
    assert client.post("/api/agent/confirm", headers=_h(BOB),
                       json={"session_id": SID, "approve": True}).status_code in (403, 404)
    db = factory()
    assert db.query(AgentMessage).filter(AgentMessage.session_id == SID).count() == alice_has_data["messages"]
    db.close()


def test_bob_cannot_use_alices_conversation_by_voice(client, factory, alice_has_data):
    with patch("app.voice.service.voice_gateway.transcribe", side_effect=AssertionError("must not reach Gnani")):
        r = client.post("/api/voice/turn", headers=_h(BOB), data={"session_id": SID},
                        files={"audio": ("a.wav", _wav(), "audio/wav")})
    assert r.status_code == 403
    db = factory()
    # nothing of Bob's was written into Alice's conversation
    assert db.query(AuditEvent).filter(AuditEvent.session_id == SID, AuditEvent.user_id == BOB[0]).count() == 0
    db.close()


def test_bob_cannot_read_alices_audit_or_replay(client, alice_has_data):
    assert client.get(f"/api/audit/{SID}", headers=_h(BOB)).status_code == 404
    assert client.get(f"/api/audit/{SID}/replay", headers=_h(BOB)).status_code == 404
    assert client.get("/api/audit/sessions", headers=_h(BOB)).status_code == 403
    # Alice can read her own
    assert client.get(f"/api/audit/{SID}", headers=_h(ALICE)).status_code == 200


def test_bob_cannot_touch_alices_cart_history_or_orders(client, alice_has_data):
    assert all(i["sku"] != "PET-001" for i in client.get("/api/cart", headers=_h(BOB)).json()["items"])
    assert client.delete(f"/api/cart/items/{alice_has_data['item']}", headers=_h(BOB)).status_code == 404
    hist = client.get("/api/cart/history", headers=_h(BOB)).json()
    assert hist == {"events": [], "baskets": []}
    assert client.get(f"/api/orders/{alice_has_data['order']}", headers=_h(BOB)).status_code == 404
    assert client.get("/api/orders", headers=_h(BOB)).json() == []
    assert client.post(f"/api/cart/reorder/{alice_has_data['order']}", headers=_h(BOB)).status_code == 404
    # Alice still sees all of hers
    mine = client.get("/api/cart/history", headers=_h(ALICE)).json()
    assert mine["events"] and mine["baskets"]


def test_bob_cannot_make_himself_the_shop_owner(client):
    assert client.get("/api/auth/me", headers=_h(BOB)).json()["can_be_merchant"] is False
    assert client.post("/api/dev/switch-role", headers=_h(BOB), json={"role": "MERCHANT"}).status_code == 403


def test_the_shop_owner_account_can(client, factory):
    owner = ("user_owner", "owner@example.test")
    db = factory()
    db.add(User(id=owner[0], email=owner[1], name="Owner", google_sub=None, role="BUYER"))
    db.commit()
    db.close()
    assert client.get("/api/auth/me", headers=_h(owner)).json()["can_be_merchant"] is True
    r = client.post("/api/dev/switch-role", headers=_h(owner), json={"role": "MERCHANT"})
    assert r.status_code == 200 and r.json()["role"] == "MERCHANT"
