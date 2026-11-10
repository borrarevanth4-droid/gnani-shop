"""Grocery vocabulary in Gnani's 10 languages — a plain lookup table.

Why a table and not the language model: "ఆట్టా", "आटा" and "aata" all mean
the same catalog tag `atta`. Deciding that is a dictionary lookup, not a
judgement — code is exact, instant, free and testable. The agent still
translates the buyer's words when it calls `search_products`; this table is
the deterministic safety net under it, and what the storefront's own search
box uses.

Keys are the English catalog tags (backend/data/products.json). Each
language lists native-script forms first, then common romanised spellings
(how people type, and what Prisma's `codemix`/`transliterate` formats return).
"""

TERMS: dict[str, dict[str, list[str]]] = {
    "atta": {
        "hi-IN": ["आटा", "गेहूं का आटा"], "mr-IN": ["पीठ", "कणीक", "आटा"], "ta-IN": ["கோதுமை மாவு", "ஆட்டா"],
        "te-IN": ["గోధుమ పిండి", "ఆట్టా", "పిండి"], "kn-IN": ["ಗೋಧಿ ಹಿಟ್ಟು", "ಆಟ್ಟಾ", "ಹಿಟ್ಟು"],
        "ml-IN": ["ഗോതമ്പ് പൊടി", "ആട്ട"], "bn-IN": ["আটা"], "gu-IN": ["લોટ", "આટો"], "pa-IN": ["ਆਟਾ"],
        "en-IN": ["atta", "aata", "wheat flour", "godhuma pindi"],
    },
    "rice": {
        "hi-IN": ["चावल"], "mr-IN": ["तांदूळ"], "ta-IN": ["அரிசி"], "te-IN": ["బియ్యం"], "kn-IN": ["ಅಕ್ಕಿ"],
        "ml-IN": ["അരി"], "bn-IN": ["চাল"], "gu-IN": ["ચોખા"], "pa-IN": ["ਚੌਲ"],
        "en-IN": ["rice", "chawal", "chaval", "biyyam", "arisi", "basmati"],
    },
    "oil": {
        "hi-IN": ["तेल"], "mr-IN": ["तेल"], "ta-IN": ["எண்ணெய்"], "te-IN": ["నూనె"], "kn-IN": ["ಎಣ್ಣೆ"],
        "ml-IN": ["എണ്ണ"], "bn-IN": ["তেল"], "gu-IN": ["તેલ"], "pa-IN": ["ਤੇਲ"],
        "en-IN": ["oil", "tel", "nune", "ennai", "cooking oil"],
    },
    "salt": {
        "hi-IN": ["नमक"], "mr-IN": ["मीठ"], "ta-IN": ["உப்பு"], "te-IN": ["ఉప్పు"], "kn-IN": ["ಉಪ್ಪು"],
        "ml-IN": ["ഉപ്പ്"], "bn-IN": ["লবণ", "নুন"], "gu-IN": ["મીઠું"], "pa-IN": ["ਲੂਣ"],
        "en-IN": ["salt", "namak", "uppu"],
    },
    "dal": {
        "hi-IN": ["तूर दाल", "अरहर दाल", "दाल"], "mr-IN": ["तूर डाळ", "डाळ"], "ta-IN": ["பருப்பு"], "te-IN": ["పప్పు"], "kn-IN": ["ಬೇಳೆ"],
        "ml-IN": ["പരിപ്പ്"], "bn-IN": ["ডাল"], "gu-IN": ["દાળ"], "pa-IN": ["ਦਾਲ"],
        "en-IN": ["dal", "daal", "pappu", "paruppu", "lentils", "toor dal"],
    },
    "tea": {
        "hi-IN": ["चाय"], "mr-IN": ["चहा"], "ta-IN": ["டீ", "தேநீர்"], "te-IN": ["టీ"], "kn-IN": ["ಟೀ", "ಚಹಾ"],
        "ml-IN": ["ചായ"], "bn-IN": ["চা"], "gu-IN": ["ચા"], "pa-IN": ["ਚਾਹ"],
        "en-IN": ["tea", "chai", "chaya", "chaha"],
    },
    "coffee": {
        "hi-IN": ["कॉफ़ी", "कॉफी"], "mr-IN": ["कॉफी"], "ta-IN": ["காபி"], "te-IN": ["కాఫీ"], "kn-IN": ["ಕಾಫಿ"],
        "ml-IN": ["കാപ്പി"], "bn-IN": ["কফি"], "gu-IN": ["કોફી"], "pa-IN": ["ਕੌਫੀ"],
        "en-IN": ["coffee", "kaapi", "kapi"],
    },
    "noodles": {
        "hi-IN": ["मैगी", "नूडल्स"], "mr-IN": ["मॅगी", "नूडल्स"], "ta-IN": ["மேகி", "நூடுல்ஸ்"],
        "te-IN": ["మ్యాగీ", "నూడుల్స్"], "kn-IN": ["ಮ್ಯಾಗಿ", "ನೂಡಲ್ಸ್"], "ml-IN": ["മാഗി", "നൂഡിൽസ്"],
        "bn-IN": ["ম্যাগি", "নুডলস"], "gu-IN": ["મેગી", "નૂડલ્સ"], "pa-IN": ["ਮੈਗੀ", "ਨੂਡਲਜ਼"],
        "en-IN": ["noodles", "maggi"],
    },
    "ice cream": {
        "hi-IN": ["आइसक्रीम", "आइस क्रीम"], "mr-IN": ["आईस्क्रीम"], "ta-IN": ["ஐஸ்கிரீம்"], "te-IN": ["ఐస్ క్రీమ్", "ఐస్‌క్రీమ్"],
        "kn-IN": ["ಐಸ್ ಕ್ರೀಮ್"], "ml-IN": ["ഐസ്ക്രീം"], "bn-IN": ["আইসক্রিম"], "gu-IN": ["આઈસ્ક્રીમ"], "pa-IN": ["ਆਈਸਕ੍ਰੀਮ"],
        "en-IN": ["ice cream", "icecream"],
    },
    "kulfi": {
        "hi-IN": ["कुल्फी"], "mr-IN": ["कुल्फी"], "ta-IN": ["குல்ஃபி"], "te-IN": ["కుల్ఫీ"], "kn-IN": ["ಕುಲ್ಫಿ"],
        "ml-IN": ["കുൽഫി"], "bn-IN": ["কুলফি"], "gu-IN": ["કુલ્ફી"], "pa-IN": ["ਕੁਲਫੀ"], "en-IN": ["kulfi"],
    },
    "chocolate": {
        "hi-IN": ["चॉकलेट"], "mr-IN": ["चॉकलेट"], "ta-IN": ["சாக்லேட்"], "te-IN": ["చాక్లెట్"], "kn-IN": ["ಚಾಕೊಲೇಟ್"],
        "ml-IN": ["ചോക്ലേറ്റ്"], "bn-IN": ["চকলেট"], "gu-IN": ["ચોકલેટ"], "pa-IN": ["ਚਾਕਲੇਟ"],
        "en-IN": ["chocolate", "choclate"],
    },
    "milk": {
        "hi-IN": ["दूध"], "mr-IN": ["दूध"], "ta-IN": ["பால்"], "te-IN": ["పాలు"], "kn-IN": ["ಹಾಲು"],
        "ml-IN": ["പാൽ"], "bn-IN": ["দুধ"], "gu-IN": ["દૂધ"], "pa-IN": ["ਦੁੱਧ"],
        "en-IN": ["milk", "doodh", "dudh", "paalu", "paal", "haalu"],
    },
    "butter": {
        "hi-IN": ["मक्खन"], "mr-IN": ["लोणी"], "ta-IN": ["வெண்ணெய்"], "te-IN": ["వెన్న"], "kn-IN": ["ಬೆಣ್ಣೆ"],
        "ml-IN": ["വെണ്ണ"], "bn-IN": ["মাখন"], "gu-IN": ["માખણ"], "pa-IN": ["ਮੱਖਣ"],
        "en-IN": ["butter", "makhan", "makkhan", "venna"],
    },
    "cheese": {
        "hi-IN": ["चीज़", "चीज"], "mr-IN": ["चीज"], "ta-IN": ["சீஸ்"], "te-IN": ["చీజ్"], "kn-IN": ["ಚೀಸ್"],
        "ml-IN": ["ചീസ്"], "bn-IN": ["চিজ"], "gu-IN": ["ચીઝ"], "pa-IN": ["ਚੀਜ਼"], "en-IN": ["cheese"],
    },
    "curd": {
        "hi-IN": ["दही"], "mr-IN": ["दही"], "ta-IN": ["தயிர்"], "te-IN": ["పెరుగు"], "kn-IN": ["ಮೊಸರು"],
        "ml-IN": ["തൈര്"], "bn-IN": ["দই"], "gu-IN": ["દહીં"], "pa-IN": ["ਦਹੀਂ"],
        "en-IN": ["curd", "dahi", "perugu", "thayir", "mosaru", "yogurt"],
    },
    "paneer": {
        "hi-IN": ["पनीर"], "mr-IN": ["पनीर"], "ta-IN": ["பனீர்"], "te-IN": ["పనీర్"], "kn-IN": ["ಪನೀರ್"],
        "ml-IN": ["പനീർ"], "bn-IN": ["পনির"], "gu-IN": ["પનીર"], "pa-IN": ["ਪਨੀਰ"], "en-IN": ["paneer", "panir"],
    },
    "ghee": {
        "hi-IN": ["घी"], "mr-IN": ["तूप"], "ta-IN": ["நெய்"], "te-IN": ["నెయ్యి"], "kn-IN": ["ತುಪ್ಪ"],
        "ml-IN": ["നെയ്യ്"], "bn-IN": ["ঘি"], "gu-IN": ["ઘી"], "pa-IN": ["ਘਿਓ"],
        "en-IN": ["ghee", "neyyi", "nei", "tuppa", "toop"],
    },
    "cold drink": {
        "hi-IN": ["कोल्ड ड्रिंक", "ठंडा"], "mr-IN": ["कोल्ड ड्रिंक"], "ta-IN": ["குளிர்பானம்"], "te-IN": ["కూల్ డ్రింక్"],
        "kn-IN": ["ಕೂಲ್ ಡ್ರಿಂಕ್"], "ml-IN": ["കൂൾ ഡ്രിങ്ക്"], "bn-IN": ["কোল্ড ড্রিংক"], "gu-IN": ["કોલ્ડ ડ્રિંક"],
        "pa-IN": ["ਕੋਲਡ ਡਰਿੰਕ"], "en-IN": ["cold drink", "soft drink", "thanda", "cool drink", "cola"],
    },
    "juice": {
        "hi-IN": ["जूस"], "mr-IN": ["ज्यूस"], "ta-IN": ["ஜூஸ்", "பழச்சாறு"], "te-IN": ["జ్యూస్"], "kn-IN": ["ಜ್ಯೂಸ್"],
        "ml-IN": ["ജ്യൂസ്"], "bn-IN": ["জুস"], "gu-IN": ["જ્યુસ"], "pa-IN": ["ਜੂਸ"], "en-IN": ["juice"],
    },
    "water": {
        "hi-IN": ["पानी"], "mr-IN": ["पाणी"], "ta-IN": ["தண்ணீர்"], "te-IN": ["నీళ్ళు", "నీరు"], "kn-IN": ["ನೀರು"],
        "ml-IN": ["വെള്ളം"], "bn-IN": ["জল", "পানি"], "gu-IN": ["પાણી"], "pa-IN": ["ਪਾਣੀ"],
        "en-IN": ["water", "paani", "pani", "neeru", "neellu", "thanni"],
    },
    "biscuit": {
        "hi-IN": ["बिस्कुट"], "mr-IN": ["बिस्किट"], "ta-IN": ["பிஸ்கட்"], "te-IN": ["బిస్కెట్"], "kn-IN": ["ಬಿಸ್ಕತ್"],
        "ml-IN": ["ബിസ്ക്കറ്റ്"], "bn-IN": ["বিস্কুট"], "gu-IN": ["બિસ્કિટ"], "pa-IN": ["ਬਿਸਕੁਟ"],
        "en-IN": ["biscuit", "biscuits", "biskut", "cookie"],
    },
    "dog food": {
        "hi-IN": ["कुत्ते का खाना"], "mr-IN": ["कुत्र्याचे अन्न"], "ta-IN": ["நாய் உணவு"], "te-IN": ["కుక్క ఆహారం"],
        "kn-IN": ["ನಾಯಿ ಆಹಾರ"], "ml-IN": ["നായ ഭക്ഷണം"], "bn-IN": ["কুকুরের খাবার"], "gu-IN": ["કૂતરાનો ખોરાક"],
        "pa-IN": ["ਕੁੱਤੇ ਦਾ ਖਾਣਾ"], "en-IN": ["dog food"],
    },
    "cat food": {
        "hi-IN": ["बिल्ली का खाना"], "mr-IN": ["मांजरीचे अन्न"], "ta-IN": ["பூனை உணவு"], "te-IN": ["పిల్లి ఆహారం"],
        "kn-IN": ["ಬೆಕ್ಕಿನ ಆಹಾರ"], "ml-IN": ["പൂച്ച ഭക്ഷണം"], "bn-IN": ["বিড়ালের খাবার"], "gu-IN": ["બિલાડીનો ખોરાક"],
        "pa-IN": ["ਬਿੱਲੀ ਦਾ ਖਾਣਾ"], "en-IN": ["cat food"],
    },
    "earphones": {
        "hi-IN": ["ईयरफ़ोन", "ईयरफोन"], "mr-IN": ["इयरफोन"], "ta-IN": ["இயர்போன்"], "te-IN": ["ఇయర్‌ఫోన్"],
        "kn-IN": ["ಇಯರ್‌ಫೋನ್"], "ml-IN": ["ഇയർഫോൺ"], "bn-IN": ["ইয়ারফোন"], "gu-IN": ["ઈયરફોન"], "pa-IN": ["ਈਅਰਫੋਨ"],
        "en-IN": ["earphones", "earphone", "headphones"],
    },
    "charger": {
        "hi-IN": ["चार्जर"], "mr-IN": ["चार्जर"], "ta-IN": ["சார்ஜர்"], "te-IN": ["ఛార్జర్"], "kn-IN": ["ಚಾರ್ಜರ್"],
        "ml-IN": ["ചാർജർ"], "bn-IN": ["চার্জার"], "gu-IN": ["ચાર્જર"], "pa-IN": ["ਚਾਰਜਰ"], "en-IN": ["charger"],
    },
    "power bank": {
        "hi-IN": ["पावर बैंक"], "mr-IN": ["पॉवर बँक"], "ta-IN": ["பவர் பேங்க்"], "te-IN": ["పవర్ బ్యాంక్"],
        "kn-IN": ["ಪವರ್ ಬ್ಯಾಂಕ್"], "ml-IN": ["പവർ ബാങ്ക്"], "bn-IN": ["পাওয়ার ব্যাংক"], "gu-IN": ["પાવર બેંક"],
        "pa-IN": ["ਪਾਵਰ ਬੈਂਕ"], "en-IN": ["power bank", "powerbank"],
    },
}


# Merge the kirana vocabulary (generated from the Shabda Kirana training data):
# new products get their own entries, existing ones gain extra everyday names.
from app.i18n.kirana_terms import KIRANA_TERMS  # noqa: E402

for _tag, _by_lang in KIRANA_TERMS.items():
    _entry = TERMS.setdefault(_tag, {})
    for _lang, _forms in _by_lang.items():
        _have = _entry.setdefault(_lang, [])
        _have.extend(f for f in _forms if f not in _have)
# Spoken variants found by testing real sentences in every language: plurals,
# common spelling variants and everyday words the training data missed.
EXTRA_FORMS: dict[str, dict[str, list[str]]] = {
    "onion": {"hi-IN": ["प्याज", "प्याज़", "कांदा"], "mr-IN": ["कांदे"], "pa-IN": ["ਪਿਆਜ"], "bn-IN": ["পিঁয়াজ"],
              "ml-IN": ["സവാള"], "en-IN": ["pyaaz", "pyaz", "pyaj", "kanda", "ullipaya", "ullipayalu", "vengayam"]},
    "eggs": {"hi-IN": ["अंडे", "अंडा", "अण्डे"], "mr-IN": ["अंडे", "अंडा"], "pa-IN": ["ਅੰਡੇ", "ਅੰਡਾ", "ਆਂਡਾ"],
             "gu-IN": ["ઈંડાં", "ઇંડા"], "te-IN": ["గుడ్డు"], "en-IN": ["egg", "anda", "ande", "anda", "guddu", "gudlu", "muttai"]},
    "bread": {"pa-IN": ["ਬ੍ਰੈੱਡ", "ਬ੍ਰੈਡ", "ਬਰੈਡ"], "bn-IN": ["ব্রেড"], "ta-IN": ["பிரெட்", "ரொட்டி"], "hi-IN": ["ब्रेड"]},
    "tomato": {"mr-IN": ["टमाटे", "टोमॅटो"], "gu-IN": ["ટામેટા", "ટમેટા"], "bn-IN": ["টম্যাটো"], "hi-IN": ["टमाटर"],
               "en-IN": ["tamatar", "tamatar", "takkali", "tamata"]},
    "potato": {"te-IN": ["ఆలుగడ్డ", "బంగాళాదుంప"], "mr-IN": ["बटाटे"], "gu-IN": ["બટેટા", "બટાટા"],
               "en-IN": ["aloo", "alu", "batata"]},
    "sugar": {"hi-IN": ["चीनी", "शक्कर"], "ta-IN": ["சீனி"], "en-IN": ["cheeni", "chini", "shakkar"]},
    "paneer": {"ml-IN": ["പനീറ്"], "ta-IN": ["பன்னீர்"]},
    "milk": {"en-IN": ["doodh", "dudh", "paalu", "paal"]},
}
for _tag, _by_lang in EXTRA_FORMS.items():
    _entry = TERMS.setdefault(_tag, {})
    for _lang, _forms in _by_lang.items():
        _have = _entry.setdefault(_lang, [])
        _have.extend(f for f in _forms if f not in _have)

# Rice in the vocabulary means everyday rice; basmati has its own entry.
TERMS["rice"]["en-IN"] = [f for f in TERMS["rice"]["en-IN"] if f != "basmati"]


def expand_query(query: str) -> list[str]:
    """English catalog tags whose word (in any language) appears in `query`,
    plus the query itself. "2 किलो आटा चाहिए" → ["2 किलो आटा चाहिए", "atta"].
    Longest forms are checked first so "dog food" wins over a shorter overlap."""
    q = (query or "").strip().lower()
    if not q:
        return []
    found: list[str] = []
    for tag, by_lang in TERMS.items():
        forms = sorted({f.lower() for forms in by_lang.values() for f in forms}, key=len, reverse=True)
        if any(f in q for f in forms) and tag not in found:
            found.append(tag)
    return [query.strip(), *found]


def native_names(tag: str) -> dict[str, str]:
    """{language: first native form} for one tag — used as a product's aliases."""
    return {lang: forms[0] for lang, forms in TERMS.get(tag, {}).items() if lang != "en-IN" and forms}
