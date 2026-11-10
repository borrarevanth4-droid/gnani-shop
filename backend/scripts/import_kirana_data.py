"""One-off import from the Shabda Kirana training data (Revanth's earlier
project) into Gnani Shop:

  1. everyday kirana products Gnani Shop didn't stock (onion, sugar, eggs…)
     → backend/data/products.json
  2. their names, and extra names for products we already had, in all ten
     languages → backend/app/i18n/kirana_terms.py (merged into the grocery
     vocabulary by app/i18n/grocery_terms.py)

Run:  python scripts/import_kirana_data.py <path to shabda_kirana_training_data.json>
Safe to re-run: products are matched by SKU, terms file is regenerated.
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LANG = {"hi": "hi-IN", "ta": "ta-IN", "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN", "bn": "bn-IN", "gu": "gu-IN",
        "pa": "pa-IN"}

# training-data id -> (our tag, new SKU or existing SKU, category, brand) ; existing SKUs only gain names
MAP = {
    "rice_sona_5kg": ("rice", "KIR-001", "groceries", "Kirana Select"),
    "toor_dal_1kg": ("dal", "GRO-005", None, None),
    "moong_dal_500g": ("moong dal", "KIR-002", "groceries", "Kirana Select"),
    "atta_5kg": ("atta", "GRO-001", None, None),
    "sunflower_oil_1l": ("oil", "GRO-003", None, None),
    "groundnut_oil_1l": ("groundnut oil", "KIR-003", "groceries", "Kirana Select"),
    "milk_500ml": ("milk", "DAI-001", None, None),
    "curd_400g": ("curd", "DAI-004", None, None),
    "ghee_500ml": ("ghee", "DAI-006", None, None),
    "sugar_1kg": ("sugar", "KIR-004", "groceries", "Kirana Select"),
    "salt_1kg": ("salt", "GRO-004", None, None),
    "tea_250g": ("tea", "GRO-006", None, None),
    "coffee_200g": ("coffee", "GRO-007", None, None),
    "turmeric_100g": ("turmeric", "KIR-005", "spices", "Kirana Select"),
    "chilli_powder_200g": ("chilli powder", "KIR-006", "spices", "Kirana Select"),
    "tamarind_250g": ("tamarind", "KIR-007", "spices", "Kirana Select"),
    "onion_1kg": ("onion", "KIR-008", "vegetables", "Farm Fresh"),
    "tomato_1kg": ("tomato", "KIR-009", "vegetables", "Farm Fresh"),
    "potato_1kg": ("potato", "KIR-010", "vegetables", "Farm Fresh"),
    "eggs_6": ("eggs", "KIR-011", "dairy", "Farm Fresh"),
    "bread_400g": ("bread", "KIR-012", "groceries", "Modern"),
    "biscuits_glucose": ("biscuit", None, None, None),  # we already have several biscuits
    "soap_bar": ("soap", "KIR-013", "household", "Kirana Select"),
    "detergent_1kg": ("detergent", "KIR-014", "household", "Kirana Select"),
}

UNITS = {"5 kg": "5 kg pack", "1 kg": "1 kg pack", "500 g": "500 g pack", "1 L": "1 L bottle", "500 ml": "500 ml pack",
         "400 g": "400 g", "250 g": "250 g pack", "200 g": "200 g pack", "100 g": "100 g pack", "6 pcs": "6 pcs",
         "1 pack": "1 pack", "1 bar": "1 bar"}


def main(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    translations = data["product_translations"]
    catalog_path = BACKEND / "data" / "products.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_sku = {p["sku"]: p for p in catalog["products"]}
    terms: dict[str, dict[str, list[str]]] = {}

    for item in data["catalog"]:
        tag, sku, category, brand = MAP[item["id"]]
        tr = translations.get(item["name_en"], {})
        forms: dict[str, list[str]] = {lang: [] for lang in ("en-IN", "te-IN", *LANG.values())}
        forms["te-IN"].append(item["name_te"])
        forms["en-IN"].append(item["name_en"].lower())  # "Whole Wheat Atta", "Toned Milk"
        for short, lang in LANG.items():
            if tr.get(short):
                forms[lang].append(tr[short])
        for alias in item["aliases"]:
            if alias.isascii():
                forms["en-IN"].append(alias.lower())
            elif any("ఀ" <= c <= "౿" for c in alias):
                forms["te-IN"].append(alias)
            elif any("ऀ" <= c <= "ॿ" for c in alias):
                forms["hi-IN"].append(alias)
        terms[tag] = {k: sorted(set(v), key=len, reverse=True) for k, v in forms.items() if v}

        if sku and sku.startswith("KIR-") and sku not in by_sku:
            product = {
                "sku": sku,
                "name": f"{brand} {item['name_en']} {item['unit'].replace(' ', '')}" if brand != "Farm Fresh"
                else f"{item['name_en']} {item['unit'].replace(' ', '')}",
                "brand": brand,
                "category": category,
                "price_paise": int(item["price"] * 100),
                "cost_paise": int(item["price"] * 75),
                "unit": UNITS.get(item["unit"], item["unit"]),
                "stock": 60,
                "description": f"Everyday kirana staple: {item['name_en'].lower()}.",
                "tags": [tag, "kirana", "staple"],
            }
            catalog["products"].insert(len(catalog["products"]) - 1, product)  # keep INJ-001 last
            by_sku[sku] = product

    # Basmati is "basmati"; plain "rice / biyyam / चावल" means everyday Sona Masoori.
    if "GRO-002" in by_sku:
        by_sku["GRO-002"]["tags"] = ["basmati", "basmati rice", "staple"]
    for cat in ("vegetables", "spices", "household"):
        if cat not in catalog["categories"]:
            catalog["categories"].append(cat)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    terms["basmati"] = {"en-IN": ["basmati rice", "basmati"], "hi-IN": ["बासमती"], "te-IN": ["బాస్మతి"],
                        "ta-IN": ["பாஸ்மதி"], "kn-IN": ["ಬಾಸ್ಮತಿ"], "ml-IN": ["ബസ്മതി"], "mr-IN": ["बासमती"],
                        "bn-IN": ["বাসমতি"], "gu-IN": ["બાસમતી"], "pa-IN": ["ਬਾਸਮਤੀ"]}
    out = BACKEND / "app" / "i18n" / "kirana_terms.py"
    out.write_text(
        '"""Generated by scripts/import_kirana_data.py from the Shabda Kirana training data —\n'
        'product names and everyday aliases in the ten languages. Merged into TERMS."""\n\n'
        "KIRANA_TERMS: dict[str, dict[str, list[str]]] = "
        + json.dumps(terms, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    print(f"products: {len(catalog['products'])} · terms: {len(terms)} → {out.relative_to(BACKEND)}")


if __name__ == "__main__":
    main(sys.argv[1])
