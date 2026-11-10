"""Tools the agent may call.

Each function is a thin wrapper over the existing the core shop service layer —
none of them run a raw query. All prices in and out are integer paise. Every
function returns plain, JSON-serializable data, never prose: the model reads
these as tool results, not as something to paraphrase blindly.

These functions are also the *execution* step the harness calls once the
policy engine has said ALLOW — the LLM only ever proposes a call by name; it
never runs one directly.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.injection_detection import scan_for_injection
from app.audit.service import AuditService
from app.orders import service as order_service
from app.orders.state_machine import COMMITTED_STATUSES, OrderStatus
from app.payments import service as payment_service
from app.payments import wallet as wallet_service
from app.repositories import cart_repo
from app.schemas.cart import CartItemCreate
from app.services import cart_service, product_service
from app.upsell import state as upsell_state

_audit = AuditService()


def _flag_if_injection(db: Session, user_id: str, session_id: str, tool_name: str, sku: str, text: str | None) -> None:
    match = scan_for_injection(text)
    if match is None:
        return
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="injection_detected",
        actor="system",
        tool_name=tool_name,
        tool_args={"sku": sku, "matched": match},
        reason=f"Suspicious instruction-like text found in catalog data for SKU '{sku}': {match!r}. "
        "Treated as inert data — tool results are never spliced into the system prompt, and the "
        "policy engine re-checks any resulting action regardless of what the model does with it.",
    )


def search_products(
    db: Session, user_id: str = "", session_id: str = "", query: str = "", max_price_paise: int | None = None, category: str | None = None
) -> dict:
    result = product_service.list_products(
        db,
        category=category,
        search=query or None,
        min_price_paise=None,
        max_price_paise=max_price_paise,
        page=1,
        page_size=6,
    )
    relaxed: str | None = None
    buyer_said = _buyer_terms(db, session_id)
    if buyer_said:
        # Ground the model's query in the buyer's own words: if they said a
        # word our 10-language vocabulary knows (पनीर → paneer) but the model
        # searched something else ("cheese"), the products for what they
        # actually said are added to the results — first — so the model can't
        # quietly substitute a different product.
        have = {p.sku for p in result.items}
        extra = []
        for term in buyer_said:
            if not any(term in [t.lower() for t in p.tags] for p in result.items):
                found = product_service.list_products(db, category=None, search=term, min_price_paise=None,
                                                      max_price_paise=max_price_paise, page=1, page_size=5)
                extra += [p for p in found.items if p.sku not in have and term in [t.lower() for t in p.tags]]
                have |= {p.sku for p in found.items}
        if extra:
            result.items = extra + list(result.items)
            result.total = len(result.items)
    if result.total == 0 and category:
        # The model guessed a category; a wrong guess ("milk" under
        # groceries) must not hide a product we actually stock.
        result = product_service.list_products(db, category=None, search=query or None, min_price_paise=None,
                                               max_price_paise=max_price_paise, page=1, page_size=6)
        relaxed = f"No match in category '{category}', so all categories were searched."
    for p in result.items:
        _flag_if_injection(db, user_id, session_id, "search_products", p.sku, p.description)
    return {
        "total": result.total,
        **({"note": relaxed} if relaxed else {}),
        **({"buyer_said": buyer_said} if buyer_said else {}),
        "items": [
            {
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                # Already reflects any active discount — this is what will
                # actually be charged. discount_pct is only present when a
                # discount is active, so the model can mention "on sale"
                # naturally without having to compute anything itself.
                "price_paise": p.effective_price_paise,
                "price_display": p.effective_price_display,
                "original_price_paise": p.price_paise if p.discount_pct else None,
                "discount_pct": p.discount_pct,
                "unit": p.unit,
                "stock": p.stock,
                # Short on purpose: every search result is resent to the model
                # on each step. Full text is one get_product call away.
                "description": (p.description or "")[:80],
            }
            for p in result.items[:6]
        ],
    }


def _buyer_terms(db: Session, session_id: str) -> list[str]:
    """Catalog tags named, in any of the ten languages, in the buyer's most
    recent message (app/i18n/grocery_terms.py — a lookup, not a model)."""
    if not session_id:
        return []
    from app.i18n.grocery_terms import expand_query
    from app.repositories import agent_session_repo

    for m in reversed(agent_session_repo.list_messages(db, session_id)):
        if m.role == "user" and m.content:
            return [t.lower() for t in expand_query(m.content)[1:]]
    return []


def get_product(db: Session, user_id: str, session_id: str, sku: str) -> dict:
    try:
        product = product_service.get_product_by_sku(db, sku)
    except HTTPException:
        return {"error": f"SKU '{sku}' was not found in the catalog."}
    _flag_if_injection(db, user_id, session_id, "get_product", product.sku, product.description)
    return {
        "sku": product.sku,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "price_paise": product.effective_price_paise,
        "price_display": product.effective_price_display,
        "original_price_paise": product.price_paise if product.discount_pct else None,
        "discount_pct": product.discount_pct,
        "stock": product.stock,
        "description": product.description,
    }


def present_product(db: Session, user_id: str, session_id: str, sku: str, within_budget: bool, note: str) -> dict:
    """Non-mutating — marks one specific catalog item as the assistant's
    structured recommendation for this turn, rendered as a card in the UI
    instead of only described in prose. Price/stock/unit are looked up fresh
    here, never trusted from the model's own claim about them, same
    discipline as every other tool result the model is handed."""
    try:
        product = product_service.get_product_by_sku(db, sku)
    except HTTPException:
        return {"error": f"SKU '{sku}' was not found in the catalog."}
    return {
        "sku": product.sku,
        "name": product.name,
        "unit": product.unit,
        "price_paise": product.effective_price_paise,
        "price_display": product.effective_price_display,
        "stock": product.stock,
        "within_budget": within_budget,
        "note": note,
    }


def add_to_cart(db: Session, user_id: str, sku: str, quantity: int = 1) -> dict:
    cart = cart_service.add_item(db, user_id, CartItemCreate(sku=sku, quantity=quantity), source="assistant")
    return cart.model_dump(mode="json")


def view_cart(db: Session, user_id: str) -> dict:
    cart = cart_service.get_cart(db, user_id)
    return cart.model_dump(mode="json")


def remove_from_cart(db: Session, user_id: str, sku: str) -> dict:
    cart = cart_repo.get_or_create_active_cart(db, user_id)
    match = next((item for item in cart.items if item.product.sku == sku), None)
    if match is None:
        # The model sometimes passes the product word ("salt", "ఉప్పు")
        # instead of the SKU. Resolve it against what's actually in the cart —
        # by name, brand, tag or local name — but only when exactly one line fits.
        from app.i18n.grocery_terms import expand_query

        terms = [t.lower() for t in expand_query(sku)]
        hits = [
            item for item in cart.items
            if any(
                t in (item.product.name or "").lower()
                or t in (item.product.brand or "").lower()
                or t in [tag.lower() for tag in (item.product.tags or [])]
                or t in [a.lower() for a in (item.product.aliases or {}).values()]
                for t in terms
            )
        ]
        if len(hits) == 1:
            match = hits[0]
    if match is None:
        return {"error": f"'{sku}' is not in the cart. Use a SKU from the current cart."}
    updated = cart_service.delete_item(db, user_id, match.id, source="assistant")
    return updated.model_dump(mode="json")


def _auto_decline_stale_upsell(db: Session, user_id: str, session_id: str) -> None:
    """The user moving straight to payment without responding to an
    outstanding offer is a decline in every practical sense — recorded here
    so the offer doesn't linger forever and (with a higher session cap) so
    the SKU is correctly remembered as declined rather than silently forgotten."""
    state = upsell_state.get_state(db, session_id)
    if state.pending is None:
        return
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="upsell_declined",
        actor="system",
        tool_name=state.pending.sku,
        tool_args={"sku": state.pending.sku},
        reason="Implicit decline — the user proceeded to payment without responding to the offer.",
    )


def decline_upsell(db: Session, user_id: str, session_id: str) -> dict:
    """Explicitly records that the user turned down the outstanding upsell
    offer, so the recommender never re-proposes that SKU this session
    (UpsellPolicyRule enforces this — see policy/rules.py). Not policy-gated:
    declining something is never itself a risk, so it isn't evaluated by
    the engine — it just always executes.
    """
    state = upsell_state.get_state(db, session_id)
    if state.pending is None:
        return {"error": "There is no pending upsell offer to decline."}
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="upsell_declined",
        actor="user",
        tool_name=state.pending.sku,
        tool_args={"sku": state.pending.sku},
        reason="The user declined this upsell offer.",
    )
    return {"declined_sku": state.pending.sku}


def report_content_gap(db: Session, user_id: str, session_id: str, sku: str, question: str) -> dict:
    """Flags a question about a product that its catalog description
    doesn't answer — logged as an ordinary audit event (event_type
    "content_gap_reported"), aggregated merchant-side by
    GET /api/campaigns/content-gaps (grouped by sku, with example
    questions). No new table: this reuses the exact same append-only
    audit log every other event in this project already writes to.

    Not policy-gated — flagging a documentation gap is never a risk, same
    reasoning as decline_upsell. Calling this never stops the model from
    still giving the user its best available answer; it only records that
    the description itself didn't cover it.
    """
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="content_gap_reported",
        actor="agent",
        tool_name=sku,
        tool_args={"sku": sku, "question": question},
        reason=question,
    )
    return {"logged": True}


def initiate_payment(db: Session, user_id: str, session_id: str) -> dict:
    """Creates (or reuses) the order for the current cart and moves it to
    AWAITING_PAYMENT. It never moves money: the buyer finishes with a tap on
    Wallet or Cash on Delivery (POST /api/payments/pay), or — Mode B only —
    the harness pays from the wallet for an autopay agent.

    Idempotent: the same cart always resolves to the same Order row
    (DB-unique idempotency key), so a double confirm-click is always safe.

    Only ever reached after the policy engine has said REQUIRE_CONFIRMATION
    and that was explicitly approved — never a straight ALLOW.
    """
    _auto_decline_stale_upsell(db, user_id, session_id)
    cart = cart_repo.get_or_create_active_cart(db, user_id)
    if not cart.items:
        return {"error": "Cart is empty — nothing to pay for."}

    creation = order_service.create_or_get_order(db, user_id=user_id, session_id=session_id, cart=cart)
    order = creation.order

    if creation.was_duplicate:
        _audit.log_event(
            db,
            session_id=session_id,
            user_id=user_id,
            event_type="duplicate_payment_prevented",
            actor="system",
            decision="DENY" if OrderStatus(order.status) in COMMITTED_STATUSES else None,
            reason=f"Reused existing order {order.id} (status={order.status}) for this idempotency key "
            "instead of creating a new one.",
        )
    else:
        _audit.log_event(
            db,
            session_id=session_id,
            user_id=user_id,
            event_type="order_created",
            actor="system",
            reason=f"Order {order.id} created for {len(cart.items)} item(s), ₹{order.amount_paise / 100:.2f}.",
        )

    if OrderStatus(order.status) in COMMITTED_STATUSES:
        return {
            "error": "This exact cart has already been ordered.",
            "order_id": order.id,
            "status": order.status,
        }

    order = order_service.ensure_awaiting_payment(db, order)
    return {
        "order_id": order.id,
        "amount_paise": order.amount_paise,
        "currency": order.currency,
        "status": order.status,
        "methods": [m["name"] for m in payment_service.available_methods()],
        "wallet_balance_paise": wallet_service.balance_paise(db, user_id),
        "next_step": "The buyer taps Wallet or Cash on Delivery to finish. You cannot complete payment yourself.",
    }


def list_orders(db: Session, user_id: str) -> dict:
    """The buyer's own recent orders, newest first (read-only)."""
    from app.orders import repository as order_repo

    orders = order_repo.list_by_user(db, user_id, limit=5)
    out = []
    for o in orders:
        cart = cart_repo.get_by_id(db, o.cart_id)
        out.append({
            "order_id": o.id,
            "status": o.status,
            "payment_method": o.payment_method,
            "amount_paise": o.amount_paise,
            "placed_at": o.created_at.date().isoformat(),
            "items": [{"sku": i.product.sku, "name": i.product.name, "quantity": i.quantity}
                      for i in (cart.items if cart else [])],
        })
    return {"orders": out, "count": len(out)}


def wallet_balance(db: Session, user_id: str) -> dict:
    return {"balance_paise": wallet_service.balance_paise(db, user_id)}


# Uniform dispatch signature: fn(db, user_id, session_id, **arguments) -> dict.
# Tools that don't need user_id/session_id still accept them for a uniform call site.
TOOL_FUNCTIONS = {
    "search_products": lambda db, user_id, session_id, **kw: search_products(db, user_id, session_id, **kw),
    "get_product": lambda db, user_id, session_id, **kw: get_product(db, user_id, session_id, **kw),
    "present_product": lambda db, user_id, session_id, **kw: present_product(db, user_id, session_id, **kw),
    "add_to_cart": lambda db, user_id, session_id, **kw: add_to_cart(db, user_id, **kw),
    "view_cart": lambda db, user_id, session_id, **kw: view_cart(db, user_id),
    "remove_from_cart": lambda db, user_id, session_id, **kw: remove_from_cart(db, user_id, **kw),
    "initiate_payment": lambda db, user_id, session_id, **kw: initiate_payment(db, user_id, session_id),
    "decline_upsell": lambda db, user_id, session_id, **kw: decline_upsell(db, user_id, session_id),
    "report_content_gap": lambda db, user_id, session_id, **kw: report_content_gap(db, user_id, session_id, **kw),
    "list_orders": lambda db, user_id, session_id, **kw: list_orders(db, user_id),
    "wallet_balance": lambda db, user_id, session_id, **kw: wallet_balance(db, user_id),
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_orders",
            "description": "The buyer's own past orders, newest first: order number, date, items, total (paise), "
            "status (PAID / CONFIRMED_COD = cash on delivery / AWAITING_PAYMENT / CANCELLED). Use for any question "
            "about previous, old, last or past orders.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wallet_balance",
            "description": "The buyer's Gnani Shop wallet balance in paise.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog by name/tag text, optionally filtered by "
            "category and a maximum price. Returns matching products with prices in paise "
            "(integer, 100 paise = 1 rupee).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text, matched against product name and tags."},
                    "max_price_paise": {
                        "type": "integer",
                        "description": "Optional maximum price in paise (e.g. ₹800 = 80000).",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional exact category, e.g. 'pet_supplies', 'groceries'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Look up a single product by its exact SKU.",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string", "description": "The product SKU, e.g. 'PET-001'."}},
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "present_product",
            "description": "Present one specific product as a structured recommendation card to the "
            "user, instead of only describing it in prose — use this once you've picked the best match "
            "for a stated item + budget request (or the closest available alternative, if nothing fits). "
            "Does not add anything to the cart; the user buys it themselves via the card's own button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "The exact SKU of the product to present."},
                    "within_budget": {
                        "type": "boolean",
                        "description": "True if this fits the budget the user stated; false if it's the closest "
                        "available option but exceeds it.",
                    },
                    "note": {
                        "type": "string",
                        "description": "One short sentence for the card, e.g. 'Within your ₹400 budget.' or "
                        "'Closest match — ₹450, over your ₹400 budget.'",
                    },
                },
                "required": ["sku", "within_budget", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Propose adding a product to the cart. This does not execute immediately — "
            "it is checked against budget, stock, and catalog rules before anything happens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "The exact SKU of the product to add."},
                    "quantity": {"type": ["integer", "null"], "description": "How many units to add. Defaults to 1."},
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "View the current cart contents and total (in paise).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a product from the cart by SKU.",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string", "description": "The SKU to remove from the cart."}},
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decline_upsell",
            "description": "Record that the user does not want the currently-offered upsell add-on "
            "(a 'suggested_upsell' field on a prior tool result). Call this once the user has said no "
            "or clearly moved on, so it is not suggested again this session. Takes no arguments.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_content_gap",
            "description": "Flag that a product's catalog description does not answer a question the "
            "user just asked about it. Call this in addition to giving your best available answer, not "
            "instead of it — this only records that the merchant's description has a gap, it never "
            "blocks or changes your reply to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "The SKU whose description didn't cover the question."},
                    "question": {"type": "string", "description": "The user's question, close to verbatim."},
                },
                "required": ["sku", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_payment",
            "description": "Propose paying for everything currently in the cart. This ALWAYS needs "
            "approval before an order is created, and the buyer finishes payment themselves by "
            "tapping Wallet or Cash on Delivery — you can never complete a payment on your own. "
            "Takes no arguments; it always acts on the current cart.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
