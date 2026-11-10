"""Understanding simple shopping sentences without a language model.

"ఒక లీటర్ పాలు మరియు రెండు ప్యాకెట్ల ఉప్పు కావాలి", "2 पैकेट Maggi और 1 पनीर चाहिए",
"naaku oka Amul butter add cheyyi" — most spoken orders are a list of products
with quantities, wrapped in a few everyday words. Recognising that is a lookup
(the 10-language grocery vocabulary, number words, units, filler words), not a
judgement, so it is done here in plain code: instant, free, and the same every
time. Live tests showed the model taking 7–44 seconds for exactly these.

The rule that keeps this safe: it only produces a plan when it understood
EVERY word of the sentence and every product resolves to exactly one catalog
item. "milk and mangoes", a question, a budget, a negation, a payment, two
possible biscuits with no brand named — anything else returns None and the
turn goes to the model as before. The plan it returns is executed by the
harness through the same policy engine and audit trail as a model proposal.
"""

import re
from dataclasses import dataclass

from app.i18n.grocery_terms import TERMS

# --- number words (1–10) in the ten languages + common romanised forms ----------------
_NUMBERS: dict[str, int] = {}
for _n, _words in {
    1: "one a an एक ఒక ఒకటి ఒక్క ஒரு ஒன்று ಒಂದು ಒಂದ ഒരു ഒന്ന് এক એક ਇੱਕ ਇਕ ek oka okka oru ondu onnu",
    2: "two दो दोन రెండు இரண்டு ரெண்டு ಎರಡು ರಡು രണ്ട് দুই দু બે ਦੋ do rendu irandu eradu randu dui be",
    3: "three तीन మూడు மூன்று ಮೂರು മൂന്ന് তিন ત્રણ ਤਿੰਨ teen moodu moonu mooru",
    4: "four चार నాలుగు நான்கு ನಾಲ್ಕು നാല് চার ચાર ਚਾਰ char naalugu naalu",
    5: "five पांच पाँच पाच ఐదు ஐந்து ಐದು അഞ്ച് পাঁচ પાંચ ਪੰਜ paanch panch aidu",
    6: "six छह छः सहा ఆరు ஆறு ಆರು ആറ് ছয় છ ਛੇ chhe aaru",
    7: "seven सात ఏడు ஏழு ಏಳು ഏഴ് সাত સાત ਸੱਤ saat",
    8: "eight आठ ఎనిమిది எட்டு ಎಂಟು എട്ട് আট આઠ ਅੱਠ aath",
    9: "nine नौ नऊ తొమ్మిది ஒன்பது ಒಂಬತ್ತು ഒമ്പത് নয় નવ ਨੌਂ nau",
    10: "ten दस दहा పది பத்து ಹತ್ತು പത്ത് দশ દસ ਦਸ das",
}.items():
    for _w in _words.split():
        _NUMBERS[_w.lower()] = _n

# "one more" words: a quantity of 1
for _w in "ఇంకో ఇంకొక ఇంకొకటి inko inkoka और_एक ek_aur another more".split():
    _NUMBERS.setdefault(_w.replace("_", " ").lower(), 1)

# --- units ---------------------------------------------------------------------------------
_MASS = ("kg", "kgs", "kilo", "kilos", "किलो", "కిలో", "கிலோ", "ಕಿಲೋ", "ಕೆಜಿ", "കിലോ", "কেজি", "কিলো", "કિલો", "ਕਿਲੋ")
_VOLUME = ("l", "ltr", "litre", "liter", "litres", "liters", "लीटर", "लिटर", "లీటర్", "லிட்டர்", "ಲೀಟರ್", "ലിറ്റർ",
           "লিটার", "લીટર", "લિટર", "ਲੀਟਰ")
_GRAM = ("g", "gm", "gram", "grams", "ग्राम", "గ్రాము", "கிராம்", "ಗ್ರಾಂ", "ഗ്രാം", "গ্রাম", "ગ્રામ", "ਗ੍ਰਾਮ")
_COUNT = ("packet", "packets", "pack", "packs", "pkt", "पैकेट", "ప్యాకెట్", "பாக்கெட்", "ಪ್ಯಾಕೆಟ್", "പാക്കറ്റ്",
          "প্যাকেট", "પેકેટ", "ਪੈਕੇਟ", "bottle", "bottles", "बोतल", "బాటిల్", "பாட்டில்", "ಬಾಟಲ್", "കുപ്പി", "বোতল",
          "બોટલ", "ਬੋਤਲ", "box", "tin", "can", "dabba", "डब्बा", "డబ్బా", "டப்பா", "piece", "pieces")

# --- everyday words that carry no product meaning (prefix stems, so inflections match) ------
_FILLER = """
i want need please pls add give me and also some of to my cart the put get order can you kindly too with in into
want to buy bring
मुझे मुझको चाहिए चाहिये और भी डाल डालो डालिए डालिये डाल_दो दे दो दीजिए दीजिये देना कर करो करें करिए जोड़ जोड़ो जोड़
ऐड प्लीज़ प्लीज कृपया मेरे मेरी कार्ट में लाओ ला लेना लेके एक्स्ट्रा ज़रा
mujhe chahiye aur bhi daalo daaldo dedo dijiye karo kar add please mere cart mein
నాకు కావాలి కావాల మరియు కూడా వేయండి వేయి వేసి వేయ్ ఇవ్వండి ఇవ్వు చేయి చేయండి చెయ్యి కార్ట్ లో ప్లీజ్
naaku kavali kaavali kuda kooda cheyyi cheyandi veyandi veyyi ivvandi
எனக்கு வேண்டும் வேணும் மற்றும் கூட சேர் சேர்க்க சேர்த்து கொடு போடு தா பண்ண கார்ட் தயவு
enakku venum vendum pannunga podunga kodunga sethu
ನನಗೆ ಬೇಕು ಮತ್ತು ಕೂಡ ಸೇರಿಸ ಕೊಡ ಹಾಕ ಮಾಡ ಕಾರ್ಟ್ ದಯವಿಟ್ಟು
എനിക്ക് വേണം കൂടെ ചേർക്ക ചേർത്ത തര ഇട കാർട്ട് ദയവായി
मला हवे हवा हवी आणि पण द्या टाका घाला करा कार्टमध्ये
আমার আমাকে চাই আর এবং দিন দাও যোগ করুন কার্টে দয়া
મને જોઈએ અને પણ આપો ઉમેરો નાખો કરો કાર્ટમાં કૃપા
ਮੈਨੂੰ ਚਾਹੀਦਾ ਚਾਹੀਦੇ ਅਤੇ ਤੇ ਵੀ ਪਾ ਦਿਓ ਦਿਉ ਜੋੜੋ ਕਾਰਟ ਕਿਰਪਾ
"""
_FILLER_STEMS = tuple(sorted({w.replace("_", " ").lower() for w in _FILLER.split()}, key=len, reverse=True))

# Words that mean the sentence is NOT a simple "add these" — let the model handle it.
_NOT_SIMPLE = re.compile(
    r"[?₹]|\b(remove|delete|pay|payment|checkout|under|below|budget|price|cheap|best|which|what|how|not|don'?t|no|"
    r"instead|cancel|recommend|suggest|compare)\b|"
    r"हटा|निकाल|पेमेंट|भुगतान|रुपये|रुपए|कितने|कितना|क्या|नहीं|मत|सस्ता|"
    r"తీసే|తీసివే|తొలగ|చెల్లించ|రూపాయ|ఎంత|ఏమి|ఏముంది|వద్దు|లేదు|"
    r"நீக்க|பணம்|ரூபாய்|எவ்வளவு|என்ன|வேண்டாம்|"
    r"ತೆಗೆ|ಪಾವತಿ|ರೂಪಾಯಿ|ಎಷ್ಟು|ಏನು|ಬೇಡ|"
    r"നീക്ക|മാറ്റ|പണം|രൂപ|എത്ര|എന്ത്|വേണ്ട|"
    r"काढ|पैसे|किती|काय|नको|"
    r"বাদ|সরিয়ে|টাকা|কত|কী|না|"
    r"કાઢ|દૂર|પૈસા|કેટલ|શું|નથી|"
    r"ਹਟਾ|ਕੱਢ|ਭੁਗਤਾਨ|ਰੁਪਏ|ਕਿੰਨ|ਕੀ|ਨਹੀਂ",
    re.IGNORECASE,
)

# Romanised "daal do" means "put it in", not lentils.
_DAAL_VERB = re.compile(r"\b(daal|dal)\s+(do|dijiye|diya|dena|de)\b", re.IGNORECASE)


@dataclass
class PlannedItem:
    tag: str | None
    quantity: int | None  # None = no number said
    size: tuple[float, str] | None  # e.g. (2, "kg") when the buyer named a size
    brand_words: list[str]
    sku: str | None = None  # set when a brand alone named the product ("a Coca-Cola")


def _forms() -> list[tuple[str, str]]:
    out = []
    for tag, by_lang in TERMS.items():
        for forms in by_lang.values():
            for f in forms:
                out.append((f.lower(), tag))
    return sorted(set(out), key=lambda x: len(x[0]), reverse=True)


_FORMS = _forms()


def _unit_kind(token: str) -> str | None:
    t = token.lower()
    for kind, words in (("kg", _MASS), ("l", _VOLUME), ("g", _GRAM), ("count", _COUNT)):
        if any(t == w or (len(w) > 2 and t.startswith(w)) for w in words):
            return kind
    return None


def _number(token: str) -> int | None:
    t = token.lower()
    if t.isdigit():
        n = int(t)
        return n if 1 <= n <= 50 else None
    return _NUMBERS.get(t)


def parse(message: str, brand_words: set[str], brand_only: dict[str, str] | None = None) -> list[PlannedItem] | None:
    """A plan of items when the whole sentence is understood, else None."""
    text = (message or "").strip()
    if not text or len(text) > 200 or _NOT_SIMPLE.search(text):
        return None
    text = _DAAL_VERB.sub(r"\2", text)
    low = " " + re.sub(r"[,.!।|;:]+", " ", text.lower()) + " "

    # replace product mentions (longest first) with placeholders
    found: list[str] = []
    for form, tag in _FORMS:
        pattern = re.compile(r"(?<![\w-])" + re.escape(form) + r"\w*")
        while True:
            m = pattern.search(low)
            if not m:
                break
            found.append(tag)
            low = low[: m.start()] + f" §{len(found) - 1}§ " + low[m.end():]
    if not found:
        return None

    tokens = low.split()
    items: list[PlannedItem] = []
    used_brands: list[str] = []
    pending_number: int | None = None
    pending_size: tuple[float, str] | None = None
    for i, tok in enumerate(tokens):
        if tok.startswith("§") and tok.endswith("§"):
            tag = found[int(tok.strip("§"))]
            prev = tokens[i - 1] if i else ""
            if items and prev.startswith("§") and items[-1].tag == tag:
                continue  # "Sona Masoori Rice": two names for ONE product, not two items
            items.append(PlannedItem(tag=tag, quantity=pending_number, size=pending_size, brand_words=used_brands))
            pending_number, pending_size, used_brands = None, None, []
            continue
        n = _number(tok)
        unit = _unit_kind(tok)
        # "2kg" written together
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-zA-Z]+)", tok)
        if m and _unit_kind(m.group(2)):
            n, unit = None, _unit_kind(m.group(2))
            value = float(m.group(1))
            if unit == "count":
                pending_number = int(value)
            else:
                pending_size = (value, unit)
            continue
        if n is not None and (unit is None or tok in ("l", "g")):
            if pending_number is not None and tok in ("a", "an", "one"):
                continue
            pending_number = n
            continue
        if unit is not None:
            if unit != "count" and pending_number is not None:
                pending_size = (float(pending_number), unit)
                pending_number = None
            continue
        if tok in brand_words or any(tok.startswith(b) for b in brand_words if len(b) >= 4):
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if brand_only and tok in brand_only and not (nxt.startswith("§") and nxt.endswith("§")):
                # The brand IS the product here ("a Coca-Cola", "3 Maggi packets").
                items.append(PlannedItem(tag=None, quantity=pending_number, size=pending_size,
                                         brand_words=[tok], sku=brand_only[tok]))
                pending_number, pending_size, used_brands = None, None, []
                continue
            used_brands.append(tok)
            continue
        if any(tok == s or (len(s) >= 3 and tok.startswith(s)) for s in _FILLER_STEMS):
            continue
        return None  # a word we don't understand — not a simple order
    return items or None


def pack_quantity(requested: PlannedItem, unit_text: str) -> int:
    """How many packs to add. A said count wins; a said size is converted to
    packs of this product's size (2 L of a 1 L pack → 2; 2 kg of a 5 kg pack → 1)."""
    if requested.size is None:
        # "six eggs" when eggs come in packs of 6 = one pack, not six packs
        pieces = re.match(r"\s*(\d+)\s*(pcs|pieces|eggs)\b", (unit_text or "").lower())
        if pieces and requested.quantity and requested.quantity >= int(pieces.group(1)):
            return max(1, requested.quantity // int(pieces.group(1)))
        return max(1, requested.quantity or 1)
    value, unit = requested.size
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(kg|g|l|ml)\b", (unit_text or "").lower())
    if not m:
        return max(1, requested.quantity or 1)
    pack, pack_unit = float(m.group(1)), m.group(2)
    to_base = {"kg": 1000, "g": 1, "l": 1000, "ml": 1}
    req_unit = {"kg": "kg", "g": "g", "l": "l"}[unit]
    if {req_unit, pack_unit} <= {"kg", "g"} or {req_unit, pack_unit} <= {"l", "ml"}:
        packs = round(value * to_base[req_unit] / (pack * to_base[pack_unit]))
        return max(1, packs)
    return max(1, requested.quantity or 1)
