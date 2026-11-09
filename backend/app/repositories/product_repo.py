from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session

from app.i18n.grocery_terms import expand_query, native_names
from app.models.product import Product


def get_by_sku(db: Session, sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.sku == sku))


def get_by_id(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def list_products(
    db: Session,
    *,
    category: str | None = None,
    search: str | None = None,
    min_price_paise: int | None = None,
    max_price_paise: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    stmt = select(Product)

    if category:
        stmt = stmt.where(Product.category == category)
    if min_price_paise is not None:
        stmt = stmt.where(Product.price_paise >= min_price_paise)
    if max_price_paise is not None:
        stmt = stmt.where(Product.price_paise <= max_price_paise)
    if search:
        # The query itself plus any catalog tag it names in one of the ten
        # languages ("ఆట్టా" → "atta") — a dictionary lookup, no AI
        # (app/i18n/grocery_terms.py). SQLite has no native array containment,
        # so tags are matched by casting the JSON column to text — portable
        # across SQLite/Postgres, if coarser than a real array operator.
        conditions = []
        for term in expand_query(search) + _significant_words(search):
            like = f"%{term.lower()}%"
            conditions += [
                func.lower(Product.name).like(like),
                func.lower(func.cast(Product.tags, String)).like(like),
                func.lower(Product.brand).like(like),
            ]
        stmt = stmt.where(or_(*conditions))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(Product.id).offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(stmt))
    return items, total


_UNIT_WORDS = {"kg", "kgs", "kilo", "kilos", "g", "gm", "gram", "grams", "l", "ltr", "litre", "liter", "litres",
               "liters", "ml", "pack", "packs", "packet", "packets", "pcs", "piece", "pieces", "bottle", "the",
               "and", "for", "with", "some", "any", "want", "need", "buy", "please"}


def _significant_words(search: str) -> list[str]:
    """"milk 1 litre" → ["milk"]: the words that name a product, so a phrase
    with a quantity in it still finds "Amul Taaza Toned Milk 1L". Only used
    when the query has more than one word."""
    words = [w.strip(".,!?").lower() for w in search.split()]
    if len(words) < 2:
        return []
    return [w for w in words if len(w) >= 3 and not w.isdigit() and w not in _UNIT_WORDS]


def list_categories(db: Session) -> list[tuple[str, int]]:
    stmt = (
        select(Product.category, func.count(Product.id))
        .group_by(Product.category)
        .order_by(Product.category)
    )
    return list(db.execute(stmt).all())


def aliases_for_tags(tags: list[str]) -> dict[str, str]:
    """Local names for a product from the first of its tags the vocabulary
    knows — e.g. tags ["atta", "flour"] → {"hi-IN": "आटा", "te-IN": "గోధుమ పిండి", ...}."""
    for tag in tags or []:
        names = native_names(tag)
        if names:
            return names
    return {}


def upsert(db: Session, data: dict) -> Product:
    if "aliases" not in data:
        data = {**data, "aliases": aliases_for_tags(data.get("tags", []))}
    product = get_by_sku(db, data["sku"])
    if product is None:
        product = Product(**data)
        db.add(product)
    else:
        for key, value in data.items():
            setattr(product, key, value)
    return product
