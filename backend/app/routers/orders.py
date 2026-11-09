"""Order history — the buyer's own list/detail, and the merchant-wide list.

Mostly the read side: every payment write goes through app/payments/service.py.
The one write here is the merchant recording cash collected for a Cash on
Delivery order (CONFIRMED_COD → PAID), which goes through the order service
and its state machine like every other transition.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.auth.routing import AuthRequirement, SecureAPIRoute, requires
from app.database import get_db
from app.models.cart import CartItem
from app.models.order import Order
from app.models.user import User
from app.audit.service import AuditService
from app.orders import repository as order_repo
from app.orders import service as order_service
from app.orders.state_machine import InvalidTransitionError, OrderStatus
from app.repositories import cart_repo
from app.schemas.orders import OrderDetailOut, OrderItemOut, OrderListItemOut

router = APIRouter(tags=["orders"], route_class=SecureAPIRoute)


def _item_counts(db: Session, cart_ids: list[int]) -> dict[int, int]:
    if not cart_ids:
        return {}
    rows = db.execute(
        select(CartItem.cart_id, func.count(CartItem.id))
        .where(CartItem.cart_id.in_(cart_ids))
        .group_by(CartItem.cart_id)
    ).all()
    return dict(rows)


def _to_list_item(order: Order, item_count: int, buyer_email: str | None = None) -> OrderListItemOut:
    return OrderListItemOut(
        id=order.id,
        status=order.status,
        amount_paise=order.amount_paise,
        created_at=order.created_at,
        item_count=item_count,
        payment_method=order.payment_method,
        buyer_email=buyer_email,
    )


@router.get("/api/orders", response_model=list[OrderListItemOut])
@requires(AuthRequirement.BUYER)
def list_my_orders(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> list[OrderListItemOut]:
    orders = order_repo.list_by_user(db, principal.user_id, limit=200)
    counts = _item_counts(db, [o.cart_id for o in orders])
    return [_to_list_item(o, counts.get(o.cart_id, 0)) for o in orders]


@router.get("/api/merchant/orders", response_model=list[OrderListItemOut])
@requires(AuthRequirement.MERCHANT)
def list_all_orders(db: Session = Depends(get_db)) -> list[OrderListItemOut]:
    orders = order_repo.list_all(db, limit=200)
    counts = _item_counts(db, [o.cart_id for o in orders])
    user_ids = {o.user_id for o in orders}
    emails = dict(db.execute(select(User.id, User.email).where(User.id.in_(user_ids))).all()) if user_ids else {}
    return [_to_list_item(o, counts.get(o.cart_id, 0), emails.get(o.user_id, o.user_id)) for o in orders]


def _order_detail(db: Session, order: Order) -> OrderDetailOut:
    cart = cart_repo.get_by_id(db, order.cart_id)
    items = [
        OrderItemOut(
            sku=ci.product.sku,
            name=ci.product.name,
            quantity=ci.quantity,
            unit_price_paise=ci.unit_price_paise,
            line_total_paise=ci.quantity * ci.unit_price_paise,
        )
        for ci in (cart.items if cart else [])
    ]

    payments_by_recency = sorted(order.payments, key=lambda p: p.created_at, reverse=True)
    latest_committed = next((p for p in payments_by_recency if p.status in ("captured", "cod_confirmed")), None)
    latest_failed = next((p for p in payments_by_recency if p.status == "failed"), None)
    is_failed = OrderStatus(order.status) == OrderStatus.FAILED

    email = db.scalar(select(User.email).where(User.id == order.user_id)) or order.user_id

    return OrderDetailOut(
        id=order.id,
        status=order.status,
        amount_paise=order.amount_paise,
        currency=order.currency,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
        payment_method=order.payment_method,
        payment_reference=latest_committed.reference if latest_committed else None,
        authorized_by=latest_committed.authorized_by if latest_committed else None,
        failure_code=latest_failed.error_code if (is_failed and latest_failed) else None,
        failure_description=latest_failed.error_description if (is_failed and latest_failed) else None,
        buyer_email=email,
    )


@router.get("/api/orders/{order_id}", response_model=OrderDetailOut)
@requires(AuthRequirement.BUYER, AuthRequirement.MERCHANT)
def get_order_detail(
    order_id: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> OrderDetailOut:
    order = order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"No order '{order_id}'.")
    # A merchant can read any order; a buyer only their own — a 404 either
    # way so this endpoint can't be used to probe which order ids are real,
    # same reasoning as app/routers/payments.py::pay.
    if principal.type != "merchant" and order.user_id != principal.user_id:
        raise HTTPException(status_code=404, detail=f"No order '{order_id}'.")
    return _order_detail(db, order)


@router.post("/api/merchant/orders/{order_id}/cod-collected", response_model=OrderDetailOut)
@requires(AuthRequirement.MERCHANT)
def mark_cod_collected(order_id: int, request: Request, db: Session = Depends(get_db)) -> OrderDetailOut:
    """The merchant records cash received on delivery: CONFIRMED_COD → PAID."""
    order = order_repo.get_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"No order '{order_id}'.")
    try:
        order_service.mark_cod_collected(db, order)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    AuditService().log_event(
        db,
        session_id=order.session_id,
        user_id=order.user_id,
        event_type="cod_cash_collected",
        actor="merchant",
        decision="ALLOW",
        tool_args={"order_id": order.id, "amount_paise": order.amount_paise},
        reason=f"Merchant recorded ₹{order.amount_paise / 100:.2f} cash collected on delivery for order {order.id}.",
        request_id=getattr(request.state, "request_id", None),
    )
    return _order_detail(db, order)
