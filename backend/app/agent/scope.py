"""ShopScopeRule — the assistant only does what a shop assistant does.

Asked "who is the president of America?", a general-purpose model answers it.
A shop assistant shouldn't: it isn't what the buyer came for, the answer may
be out of date or wrong, and it makes the assistant look like it knows things
it was never meant to. The system prompt asks the model to stay in scope, but
a prompt is a request, not a guarantee — so this rule checks every model turn
in code, after the model has answered and before anything is shown or spoken:

  * the turn did real shop work (changed the cart, found products, read
    orders / wallet, started a payment)        → the reply stands
  * it only searched, and found nothing          → fixed "we don't stock that"
  * no shop work, but the buyer used shop words
    (a product, cart, order, price, delivery…)   → the reply stands
  * no shop work and no shop words               → fixed "I can only help with
                                                   shopping" in their language

Every refusal is written to the audit log as a policy_decision (DENY,
ShopScopeRule) so it shows up in the harness steps like any other rule.
Instant (no-model) paths never reach this: they only ever say fixed phrases.
"""

import re

from sqlalchemy.orm import Session

from app.agent import fast_path
from app.audit.service import AuditService
from app.models.product import Product

RULE_NAME = "ShopScopeRule"

# Tools whose execution means the turn did real shop work.
_SHOP_WORK = {
    "add_to_cart", "remove_from_cart", "view_cart", "initiate_payment", "present_product", "get_product",
    "list_orders", "wallet_balance", "decline_upsell", "report_content_gap",
}

# Words that make a message about the shop even when no product is named.
_SHOP_WORDS = """
add remove shop store grocery groceries kirana item items product products cart basket order orders buy purchase price prices
cost costs rate rupee rupees rs ₹ pay payment checkout wallet balance cod cash delivery deliver deliveries offer
offers discount discounts stock available availability brand brands pack packet packets kg kilo litre liter gram
refund return cancel budget cheap cheaper cheapest expensive total bill receipt invoice upi
sasta mehenga dukaan saaman saman kharid daam bhav keemat
दुकान सामान सामग्री किराना कार्ट टोकरी ऑर्डर खरीद ख़रीद दाम कीमत क़ीमत रुपये रुपए भुगतान पेमेंट वॉलेट डिलीवरी ऑफर छूट
स्टॉक ब्रांड पैकेट बिल सस्ता महंगा
दुकान वस्तू किराणा कार्ट ऑर्डर खरेदी किंमत रुपये पैसे पेमेंट वॉलेट डिलिव्हरी सवलत
అంగడి దుకాణం షాప్ సరుకులు వస్తువు కార్ట్ ఆర్డర్ కొను కొన ధర రూపాయ చెల్లింపు చెల్లించ వాలెట్ డెలివరీ ఆఫర్ తగ్గింపు
స్టాక్ బ్రాండ్ ప్యాకెట్ బిల్లు
கடை மளிகை பொருள் கார்ட் ஆர்டர் வாங்க விலை ரூபாய் பணம் வாலட் டெலிவரி சலுகை தள்ளுபடி ஸ்டாக் பிராண்ட் பாக்கெட் பில்
ಅಂಗಡಿ ದಿನಸಿ ವಸ್ತು ಕಾರ್ಟ್ ಆರ್ಡರ್ ಖರೀದಿ ಬೆಲೆ ರೂಪಾಯಿ ಪಾವತಿ ವಾಲೆಟ್ ಡೆಲಿವರಿ ಆಫರ್ ರಿಯಾಯಿತಿ ಸ್ಟಾಕ್ ಬ್ರಾಂಡ್ ಪ್ಯಾಕೆಟ್ ಬಿಲ್
കട പലചരക്ക് സാധനം കാർട്ട് ഓർഡർ വാങ്ങ വില രൂപ പണം വാലറ്റ് ഡെലിവറി ഓഫർ കിഴിവ് സ്റ്റോക്ക് ബ്രാൻഡ് പാക്കറ്റ് ബിൽ
দোকান মুদি জিনিস কার্ট অর্ডার কিন দাম টাকা পেমেন্ট ওয়ালেট ডেলিভারি অফার ছাড় স্টক ব্র্যান্ড প্যাকেট বিল
દુકાન કરિયાણું વસ્તુ કાર્ટ ઓર્ડર ખરીદ ભાવ કિંમત રૂપિયા ચુકવણી પેમેન્ટ વૉલેટ ડિલિવરી ઓફર ડિસ્કાઉન્ટ સ્ટોક બ્રાન્ડ પેકેટ બિલ
ਦੁਕਾਨ ਕਰਿਆਨਾ ਸਮਾਨ ਕਾਰਟ ਆਰਡਰ ਖਰੀਦ ਕੀਮਤ ਰੁਪਏ ਭੁਗਤਾਨ ਪੇਮੈਂਟ ਵਾਲਿਟ ਡਿਲੀਵਰੀ ਆਫਰ ਛੋਟ ਸਟਾਕ ਬ੍ਰਾਂਡ ਪੈਕੇਟ ਬਿੱਲ
"""
_SHOP_STEMS = tuple(sorted({fast_path.normalize(w) for w in _SHOP_WORDS.split()}, key=len, reverse=True))

# A product word must start a word ("tea" ≠ "steam"). Short Latin words must
# BE the whole word ("tel" — oil — ≠ "tell"); longer ones and Indian-script
# words may carry an ending (plurals, case endings: "onions", "పాలు").
def _is_short_latin(f: str) -> bool:
    return f.isascii() and len(f) <= 4


_W = fast_path._WCH
_PRODUCT_WORD = re.compile(
    r"(?<!" + _W + r")(?:"
    + "|".join(re.escape(f) + r"(?!" + _W + r")" for f, _ in fast_path._FORMS if _is_short_latin(f) and len(f) >= 3)
    + "|"
    + "|".join(re.escape(f) for f, _ in fast_path._FORMS if not _is_short_latin(f) and len(f) >= 2)
    + r")"
)

# Everyday English words that happen to be in product names ("India Gate",
# "Fast Charging") — not a sign that a question is about the shop.
_GENERIC = set("""
india gate fast classic gold premium pure select original double royale adult wireless power bank ocean minute
good dark fantasy hide seek mixed real kirana modern mineral energy type bullets neckband charging adapter cable
salted toned processed block assorted bonanza sticks puppy collar adjustable gravy treat bundle mystery bottle
flavoured lime instant masala noodles shudh chakki sunlite refined iodised premium celebrations finger silk
""".split())

_audit = AuditService()
_catalog_cache: tuple[tuple[int, int], frozenset[str]] | None = None


def _catalog_words(db: Session) -> frozenset[str]:
    """Distinctive words from product names and brands ("maggi", "amul",
    "basmati"), so "is Amul butter fresh?" counts as a shop question."""
    global _catalog_cache
    key = (id(db.get_bind()), db.query(Product).count())  # per database, refreshed when the catalog changes
    if _catalog_cache is None or _catalog_cache[0] != key:
        words = set()
        for name, brand in db.query(Product.name, Product.brand).all():
            for w in re.findall(r"[^\W\d_]{4,}", f"{name} {brand or ''}".lower()):
                if w not in _GENERIC:
                    words.add(fast_path.normalize(w))
        _catalog_cache = (key, frozenset(words))
    return _catalog_cache[1]


def _shop_word(tok: str) -> bool:
    for stem in _SHOP_STEMS:
        if tok == stem:
            return True
        # endings allowed for Indian-script stems and long Latin ones; short
        # Latin ones must be the whole word ("cod" must not match "code").
        if tok.startswith(stem) and (not stem.isascii() and len(stem) >= 2 or len(stem) >= 5):
            return True
    return False


def is_about_shopping(db: Session, message: str) -> bool:
    text = " " + re.sub(r"[,.!?।|;:()\"'“”‘’]+", " ", fast_path.normalize(message or "")) + " "
    if _PRODUCT_WORD.search(text):
        return True  # names a product, in any of the ten languages
    tokens = text.split()
    if any(_shop_word(tok) for tok in tokens):
        return True
    if re.search(r"\b(do|does|did) (you|u) (have|sell|stock|keep|deliver)\b|\bhave you got\b|\bavailable\b", text):
        return True
    if any(tok in ("₹", "rs") or tok.startswith("₹") for tok in tokens):
        return True
    catalog = _catalog_words(db)
    return any(tok in catalog for tok in tokens)


def apply(db: Session, session, message: str, result, since) -> None:
    """Check one finished model turn; replace the reply when it is out of scope."""
    if result.status != "completed" or getattr(result, "view_only", False):
        return
    did_shop_work = False
    searched, found = False, False
    for e in _audit.get_trail(db, session.session_id):
        if e.timestamp < since:
            continue
        # A shop action the model proposed counts even if a rule then refused
        # it ("Could not add — spend limit" is a shop answer, not off-topic).
        if e.tool_name in _SHOP_WORK and e.event_type in ("tool_call_proposed", "policy_decision", "tool_executed"):
            did_shop_work = True
        elif e.event_type == "tool_executed" and e.tool_name == "search_products":
            searched = True
            found = found or bool((e.tool_result or {}).get("items"))
    if did_shop_work or found:
        return

    from app.voice.spoken import phrase  # late import: spoken imports nothing from here

    lang = getattr(session, "language", None) or "en-IN"
    if searched:
        new_reply, reason = phrase("not_stocked", lang), "searched the catalog and found nothing"
    elif is_about_shopping(db, message):
        return
    else:
        new_reply, reason = phrase("off_topic", lang), "not a shopping request — the assistant only helps with the shop"
    if result.reply == new_reply:
        return
    _audit.log_event(
        db, session_id=session.session_id, user_id=session.user_id, event_type="policy_decision", actor="policy",
        tool_name="reply", decision="DENY", rule_name=RULE_NAME, reason=reason,
    )
    old = result.reply
    result.reply = new_reply
    result.spoken_reply = new_reply
    # The refused text must not stay in the history the model sees next turn.
    from app.repositories import agent_session_repo

    for m in reversed(agent_session_repo.list_messages(db, session.session_id)):
        if m.role == "assistant" and m.content == old:
            m.content = new_reply
            break
    db.commit()
