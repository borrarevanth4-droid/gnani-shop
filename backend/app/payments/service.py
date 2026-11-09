"""The single place money moves.

`pay_order` is called from exactly two places:
  1. POST /api/payments/pay — a logged-in human tapping Pay (Mode A). BUYER-only.
  2. The agent harness, for an agent whose owner switched on autopay (Mode B),
     after the policy engine has re-validated the whole cart.

There is no third path. In particular the voice endpoints never reach this
module: speech can put things in a cart and ask for payment, but cannot
complete one (see app/routers/voice.py).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.models.order import Order
from app.orders import service as order_service
from app.orders.state_machine import OrderStatus
from app.payments.cod import CashOnDeliveryProvider
from app.payments.provider import PaymentProvider
from app.payments.wallet import WalletProvider, balance_paise
from app.testing.chaos import ChaosFault, is_active, log_injection

_audit = AuditService()

PROVIDERS: dict[str, PaymentProvider] = {p.name: p for p in (WalletProvider(), CashOnDeliveryProvider())}

AUTHORIZED_BY_HUMAN = "human_tap"
AUTHORIZED_BY_AGENT_AUTOPAY = "agent_autopay"


class UnknownPaymentMethodError(Exception):
    pass


@dataclass
class PayResult:
    status: str  # final order status
    order_id: int
    amount_paise: int
    method: str
    authorized_by: str
    reference: str | None
    money_moved: bool
    message: str
    wallet_balance_paise: int | None = None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "order_id": self.order_id,
            "amount_paise": self.amount_paise,
            "method": self.method,
            "authorized_by": self.authorized_by,
            "reference": self.reference,
            "money_moved": self.money_moved,
            "message": self.message,
            "wallet_balance_paise": self.wallet_balance_paise,
        }


def available_methods() -> list[dict]:
    return [
        {"name": p.name, "display_name": p.display_name, "agent_autopay_allowed": p.agent_autopay_allowed}
        for p in PROVIDERS.values()
    ]


def get_provider(method: str) -> PaymentProvider:
    provider = PROVIDERS.get(method)
    if provider is None:
        raise UnknownPaymentMethodError(f"Unknown payment method '{method}'. Choose one of: {', '.join(PROVIDERS)}.")
    return provider


def pay_order(
    db: Session,
    order: Order,
    *,
    method: str,
    authorized_by: str,
    request_id: str | None = None,
) -> PayResult:
    provider = get_provider(method)
    if authorized_by == AUTHORIZED_BY_AGENT_AUTOPAY and not provider.agent_autopay_allowed:
        raise UnknownPaymentMethodError(f"{provider.display_name} can only be chosen by a human.")

    status = OrderStatus(order.status)
    if status in (OrderStatus.PAID, OrderStatus.CONFIRMED_COD):
        _audit.log_event(
            db,
            session_id=order.session_id,
            user_id=order.user_id,
            event_type="duplicate_payment_prevented",
            actor="system",
            decision="DENY",
            tool_args={"order_id": order.id, "method": method},
            reason=f"Order {order.id} is already {order.status} — ignoring a repeat payment request.",
            request_id=request_id,
        )
        return PayResult(
            status=order.status,
            order_id=order.id,
            amount_paise=order.amount_paise,
            method=order.payment_method or method,
            authorized_by=authorized_by,
            reference=order.payments[-1].reference if order.payments else None,
            money_moved=False,
            message="This order was already placed — nothing was charged again.",
            wallet_balance_paise=_balance_or_none(db, order),
        )

    if status in (OrderStatus.PENDING, OrderStatus.FAILED):
        order = order_service.ensure_awaiting_payment(db, order)

    fault = _chaos_fault_for(db, order)
    if fault is not None:
        return _record_failure(db, order, method, authorized_by, fault[0], fault[1], request_id)

    outcome = provider.charge(db, order)
    if not outcome.committed:
        return _record_failure(db, order, method, authorized_by, outcome.error_code, outcome.message, request_id)

    if outcome.money_moved:
        order_service.mark_paid(
            db, order, method=method, reference=outcome.reference or "", authorized_by=authorized_by,
            raw_response=outcome.details,
        )
        event_type = "payment_succeeded"
    else:
        order_service.mark_cod_confirmed(db, order, authorized_by=authorized_by)
        event_type = "cod_order_confirmed"

    _audit.log_event(
        db,
        session_id=order.session_id,
        user_id=order.user_id,
        event_type=event_type,
        actor="agent" if authorized_by == AUTHORIZED_BY_AGENT_AUTOPAY else "user",
        decision="ALLOW",
        tool_args={
            "order_id": order.id,
            "method": method,
            "reference": outcome.reference,
            "authorized_by": authorized_by,
            "amount_paise": order.amount_paise,
        },
        reason=outcome.message,
        request_id=request_id,
    )
    return PayResult(
        status=order.status,
        order_id=order.id,
        amount_paise=order.amount_paise,
        method=method,
        authorized_by=authorized_by,
        reference=outcome.reference,
        money_moved=outcome.money_moved,
        message=outcome.message,
        wallet_balance_paise=_balance_or_none(db, order),
    )


def _balance_or_none(db: Session, order: Order) -> int | None:
    try:
        return balance_paise(db, order.user_id)
    except Exception:  # noqa: BLE001 — a cosmetic field must never fail a payment response
        return None


def _chaos_fault_for(db: Session, order: Order) -> tuple[str, str] | None:
    if is_active(ChaosFault.FAIL_PAYMENT):
        log_injection(
            db, session_id=order.session_id, user_id=order.user_id, fault=ChaosFault.FAIL_PAYMENT,
            detail=f"Forcing order {order.id} to a declined payment.",
        )
        return "chaos_injected_decline", "Chaos: simulated payment decline."
    if is_active(ChaosFault.PAYMENT_PROVIDER_TIMEOUT):
        log_injection(
            db, session_id=order.session_id, user_id=order.user_id, fault=ChaosFault.PAYMENT_PROVIDER_TIMEOUT,
            detail=f"Simulating a payment provider timeout for order {order.id}.",
        )
        return "provider_timeout", "Chaos: the payment provider timed out. Nothing was charged; please try again."
    return None


def _record_failure(
    db: Session,
    order: Order,
    method: str,
    authorized_by: str,
    error_code: str | None,
    message: str,
    request_id: str | None,
) -> PayResult:
    order_service.mark_failed(
        db, order, method=method, error_code=error_code, error_description=message, authorized_by=authorized_by
    )
    _audit.log_event(
        db,
        session_id=order.session_id,
        user_id=order.user_id,
        event_type="payment_failed",
        actor="system",
        decision="FAILED",
        tool_args={"order_id": order.id, "method": method, "error_code": error_code, "authorized_by": authorized_by},
        reason=message,
        request_id=request_id,
    )
    return PayResult(
        status=order.status,
        order_id=order.id,
        amount_paise=order.amount_paise,
        method=method,
        authorized_by=authorized_by,
        reference=None,
        money_moved=False,
        message=message,
        wallet_balance_paise=_balance_or_none(db, order),
    )
