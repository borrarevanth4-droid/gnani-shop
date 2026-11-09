"""Prisma v3.0 `keyterms`, built from the catalog — deterministic, no AI.

Brand and product names are exactly the words a general speech model gets
wrong ("Aashirvaad" → "aashirwad", "Haldiram's" → "haldi rams"). Sending the
catalog's own vocabulary as keyterms lets Prisma bias toward the spellings our
product search will actually match. Gnani's limits: at most 200 terms, and no
`<|` / `|>` sequences in any value.
"""

import re
import time

from sqlalchemy.orm import Session

from app.models.product import Product

MAX_KEYTERMS = 200
_CACHE_SECONDS = 300
_cache: tuple[float, list[str]] | None = None


def _clean(term: str) -> str | None:
    term = re.sub(r"\s+", " ", term).strip()
    if not term or "<|" in term or "|>" in term or len(term) > 60:
        return None
    return term


def build_keyterms(db: Session) -> list[str]:
    """Brands first (highest value: proper nouns), then short product names,
    then each product's names in other languages (app/i18n). Deduplicated
    case-insensitively, capped at 200. Cached for five minutes — the catalog
    changes rarely and this runs on every voice turn."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]

    products = db.query(Product).all()
    ordered: list[str] = []
    ordered += sorted({p.brand for p in products if p.brand})
    for p in products:
        # "Aashirvaad Shudh Chakki Atta 5kg" → "Aashirvaad Shudh Chakki Atta"
        ordered.append(re.sub(r"\s*\d+(\.\d+)?\s*(kg|g|ml|l|ltr|pcs?|pack)\b.*$", "", p.name, flags=re.I))
    for p in products:
        for alias in (p.aliases or {}).values():
            for a in alias if isinstance(alias, list) else [alias]:
                ordered.append(a)

    seen: set[str] = set()
    out: list[str] = []
    for term in ordered:
        cleaned = _clean(term or "")
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
        if len(out) >= MAX_KEYTERMS:
            break
    _cache = (now, out)
    return out


def clear_cache() -> None:
    global _cache
    _cache = None
