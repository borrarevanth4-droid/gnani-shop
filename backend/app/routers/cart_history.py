"""Cart history — everything that went in and out of the buyer's carts, and
every past basket (one per order) with a one-tap "buy again".

BUYER only, like the rest of /api/cart. "Buy again" only fills the cart;
paying is still a separate tap on the checkout screen.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.auth.routing import AuthRequirement, SecureAPIRoute, requires
from app.database import get_db
from app.models.cart import Cart
from app.models.cart_event import CartEvent
from app.models.order import Order
from app.schemas.cart import CartItemCreate, CartOut
from app.services import cart_service

router = APIRouter(tags=["cart"], route_class=SecureAPIRoute)


class CartEventOut(BaseModel):
    id: int
    cart_id: int
    action: str
    sku: str
    name: str
    quantity: int
    unit_price_paise: int
    source: str
    created_at: datetime


class BasketItemOut(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price_paise: int


class BasketOut(BaseModel):
    order_id: int
    cart_id: int
    status: str
    amount_paise: int
    payment_method: str | None
    created_at: datetime
    items: list[BasketItemOut]


class CartHistoryOut(BaseModel):
    events: list[CartEventOut]
    baskets: list[BasketOut]


class ReorderOut(BaseModel):
    cart: CartOut
    added: list[str]
    skipped: list[str]  # out of stock or no longer sold


@router.get("/api/cart/history", response_model=CartHistoryOut)
@requires(AuthRequirement.BUYER)
def cart_history(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> CartHistoryOut:
    events = db.scalars(
        select(CartEvent).where(CartEvent.user_id == principal.user_id).order_by(CartEvent.id.desc()).limit(200)
    ).all()
    orders = db.scalars(
        select(Order).where(Order.user_id == principal.user_id).order_by(Order.created_at.desc()).limit(50)
    ).all()
    baskets = []
    for o in orders:
        cart = db.get(Cart, o.cart_id)
        items = [
            BasketItemOut(sku=i.product.sku, name=i.product.name, quantity=i.quantity, unit_price_paise=i.unit_price_paise)
            for i in (cart.items if cart else [])
        ]
        baskets.append(BasketOut(order_id=o.id, cart_id=o.cart_id, status=o.status, amount_paise=o.amount_paise,
                                 payment_method=o.payment_method, created_at=o.created_at, items=items))
    return CartHistoryOut(events=[CartEventOut.model_validate(e, from_attributes=True) for e in events], baskets=baskets)


@router.post("/api/cart/reorder/{order_id}", response_model=ReorderOut)
@requires(AuthRequirement.BUYER)
def buy_again(order_id: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> ReorderOut:
    order = db.get(Order, order_id)
    if order is None or order.user_id != principal.user_id:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    cart = db.get(Cart, order.cart_id)
    added, skipped = [], []
    for item in list(cart.items if cart else []):
        p = item.product
        if p is None or p.stock < item.quantity:
            skipped.append(p.name if p else f"item {item.id}")
            continue
        cart_service.add_item(db, principal.user_id, CartItemCreate(sku=p.sku, quantity=item.quantity), source="reorder")
        added.append(p.name)
    return ReorderOut(cart=cart_service.get_cart(db, principal.user_id), added=added, skipped=skipped)
