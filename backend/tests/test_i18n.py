"""Multi-language catalog search: the same product found from any of the
ten languages, deterministically (no AI) — app/i18n/grocery_terms.py."""

import pytest

from app.i18n.grocery_terms import TERMS, expand_query
from app.repositories import product_repo
from app.voice.languages import SUPPORTED_CODES


@pytest.mark.parametrize("query,tag", [
    ("2 किलो आटा चाहिए", "atta"),
    ("నాకు ఆట్టా కావాలి", "atta"),
    ("ஒரு லிட்டர் பால்", "milk"),
    ("ಹಾಲು ಬೇಕು", "milk"),
    ("doodh chahiye", "milk"),
    ("ঘি", "ghee"),
    ("તેલ", "oil"),
    ("ਦਾਲ", "dal"),
    ("ചായ", "tea"),
    ("तांदूळ", "rice"),
    ("kutte ka khana nahi, dog food chahiye", "dog food"),
])
def test_query_in_any_language_maps_to_the_catalog_tag(query, tag):
    assert tag in expand_query(query)


def test_every_term_covers_all_ten_languages():
    for tag, by_lang in TERMS.items():
        assert set(by_lang) == SUPPORTED_CODES, tag


def test_repository_search_finds_products_from_native_script(db_session):
    product_repo.upsert(db_session, {
        "sku": "DAI-001", "name": "Amul Taaza Toned Milk 1L", "brand": "Amul", "category": "dairy",
        "price_paise": 6800, "unit": "1 L", "stock": 10, "description": "toned milk", "tags": ["milk", "dairy"],
        "cost_paise": 5000,
    })
    db_session.commit()
    for q in ("పాలు", "दूध", "1 litre milk", "Amul"):
        items, total = product_repo.list_products(db_session, search=q)
        assert total == 1 and items[0].sku == "DAI-001", q
    product = product_repo.get_by_sku(db_session, "DAI-001")
    assert product.aliases["te-IN"] == "పాలు" and product.aliases["hi-IN"] == "दूध"
