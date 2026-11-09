"""Order orchestration: idempotent order creation and the status transitions
(AWAITING_PAYMENT, PAID, CONFIRMED_COD, FAILED).

Deliberately has no knowledge of the agent, the policy engine, HTTP, or any
particular payment method — those layers call into this one, not the other
way around. Money movement itself lives in app/payments/.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cart import Cart
from app.models.order import Order, Payment
from app.orders import repository as order_repo
from app.orders.idempotency import compute_idempotency_key
from app.orders.state_machine import OrderStatus, require_transition
from app.repositories import cart_repo


class EmptyCartError(Exception):
    pass


@dataclass
class OrderCreationResult:
    order: Order
    was_duplicate: bool  # True if an order for this idempotency key already existed


def _line_items(cart: Cart) -> list[tuple[str, int, int]]:
    return [(item.product.sku, item.quantity, item.unit_price_paise) for item in cart.items]


def create_or_get_order(db: Session, *, user_id: str, session_id: str, cart: Cart) -> OrderCreationResult:
    if not cart.items:
        raise EmptyCartError("Cart is empty — nothing to pay for.")

    line_items = _line_items(cart)
    amount_paise = sum(qty * price for _, qty, price in line_items)
    key = compute_idempotency_key(user_id, line_items, amount_paise, cart.id)

    order, created = order_repo.get_or_create(
        db,
        idempotency_key=key,
        user_id=user_id,
        session_id=session_id,
        cart_id=cart.id,
        amount_paise=amount_paise,
        currency=settings.currency,
    )
    return OrderCreationResult(order=order, was_duplicate=not created)


def ensure_awaiting_payment(db: Session, order: Order) -> Order:
    """Moves a fresh (PENDING) or previously FAILED order to AWAITING_PAYMENT.
    Idempotent: an order already AWAITING_PAYMENT is returned unchanged, so a
    double confirm-click never does anything twice."""
    current = OrderStatus(order.status)
    if current == OrderStatus.AWAITING_PAYMENT:
        return order
    require_transition(current, OrderStatus.AWAITING_PAYMENT)
    order.status = OrderStatus.AWAITING_PAYMENT.value
    return order_repo.save(db, order)


def mark_paid(
    db: Session,
    order: Order,
    *,
    method: str,
    reference: str,
    authorized_by: str,
    raw_response: dict | None = None,
) -> Payment:
    require_transition(OrderStatus(order.status), OrderStatus.PAID)
    order.status = OrderStatus.PAID.value
    order.payment_method = method
    order_repo.save(db, order)

    payment = Payment(
        order_id=order.id,
        reference=reference,
        status="captured",
        amount_paise=order.amount_paise,
        method=method,
        authorized_by=authorized_by,
        raw_response=raw_response,
    )
    order_repo.add_payment(db, payment)
    _reset_cart_after_commit(db, order)
    return payment


def mark_cod_confirmed(db: Session, order: Order, *, authorized_by: str) -> Payment:
    """Cash on Delivery: the order is placed, no money has moved. The Payment
    row records the commitment with status "cod_confirmed", never "captured"."""
    require_transition(OrderStatus(order.status), OrderStatus.CONFIRMED_COD)
    order.status = OrderStatus.CONFIRMED_COD.value
    order.payment_method = "cod"
    order_repo.save(db, order)

    payment = Payment(
        order_id=order.id,
        reference=f"cod_{order.id}",
        status="cod_confirmed",
        amount_paise=order.amount_paise,
        method="cod",
        authorized_by=authorized_by,
    )
    order_repo.add_payment(db, payment)
    _reset_cart_after_commit(db, order)
    return payment


def mark_cod_collected(db: Session, order: Order) -> Payment:
    """Merchant records the cash as collected on delivery: CONFIRMED_COD → PAID."""
    require_transition(OrderStatus(order.status), OrderStatus.PAID)
    order.status = OrderStatus.PAID.value
    order_repo.save(db, order)
    payment = Payment(
        order_id=order.id,
        reference=f"cod_{order.id}",
        status="captured",
        amount_paise=order.amount_paise,
        method="cod",
        authorized_by="merchant_cash_collected",
    )
    return order_repo.add_payment(db, payment)


def mark_failed(
    db: Session,
    order: Order,
    *,
    method: str | None,
    error_code: str | None,
    error_description: str | None,
    authorized_by: str | None = None,
) -> Payment:
    current = OrderStatus(order.status)
    if current in (OrderStatus.PAID, OrderStatus.CONFIRMED_COD, OrderStatus.FAILED):
        # Never downgrade a committed order on a stale failure, and FAILED →
        # FAILED is not a transition — the attempt is still recorded below.
        pass
    else:
        require_transition(current, OrderStatus.FAILED)
        order.status = OrderStatus.FAILED.value
        order_repo.save(db, order)

    payment = Payment(
        order_id=order.id,
        status="failed",
        amount_paise=order.amount_paise,
        method=method,
        authorized_by=authorized_by,
        error_code=error_code,
        error_description=error_description,
    )
    return order_repo.add_payment(db, payment)


def _reset_cart_after_commit(db: Session, order: Order) -> None:
    cart = cart_repo.get_by_id(db, order.cart_id)
    if cart is not None and cart.status == "active":
        cart_repo.mark_checked_out(db, cart)
    cart_repo.get_or_create_active_cart(db, order.user_id)
