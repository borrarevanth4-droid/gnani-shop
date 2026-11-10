"""Cart history: every add/remove is logged (taps and assistant alike), past
baskets come back per order, and "buy again" refills the cart."""

from app.models.cart_event import CartEvent
from app.repositories import cart_repo
from app.schemas.cart import CartItemCreate
from app.services import cart_service


def test_add_and_remove_are_logged(db_session):
    db = db_session
    from app.models.product import Product

    p = Product(sku="DAI-001", name="Amul Taaza Toned Milk 1L", brand="Amul", category="dairy",
                price_paise=6800, unit="1L", stock=25, description="", tags=["milk"])
    db.add(p)
    db.commit()
    cart = cart_service.add_item(db, "u-hist", CartItemCreate(sku=p.sku, quantity=2))
    cart_service.add_item(db, "u-hist", CartItemCreate(sku=p.sku, quantity=1), source="assistant")
    cart_service.delete_item(db, "u-hist", cart.items[0].id, source="assistant")
    ev = db.query(CartEvent).filter(CartEvent.user_id == "u-hist").order_by(CartEvent.id).all()
    assert [(e.action, e.quantity, e.source) for e in ev] == [
        ("added", 2, "you"), ("added", 1, "assistant"), ("removed", 3, "assistant")]
    assert all(e.sku == p.sku and e.name == p.name for e in ev)
    assert cart_repo.get_active_cart(db, "u-hist").items == []
