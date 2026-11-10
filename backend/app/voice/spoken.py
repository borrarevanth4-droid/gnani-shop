"""Turning an agent reply into something good to *listen* to.

Three deterministic steps — no AI anywhere in this file:

1. `strip_model_tags`: remove any audio tag the language model wrote. Only
   our own templates may add tags, so the model can never make the voice
   whisper, shout or laugh on its own (AudioTagControl — same principle as
   "the model proposes, code decides").
2. `speakable`: drop markdown, links and emoji; keep ₹ amounts as-is because
   Timbre reads "₹173.50" as rupees and paise natively.
3. `compose`: add a tag from a fixed template for specific moments — an
   excited "order placed", a pause before reading back an amount — and only
   for timbre-v3.0, the one model that understands tags.

Also holds the localized phrases for the moments that matter most in voice,
so a Tamil speaker hears Tamil even when the rulebook's reason is English.
These are fixed strings, written once and reviewable by a native speaker.
"""

import re

from app.voice.languages import AUDIO_TAGS, TIMBRE_V3, normalize

_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z _-]{0,30})\s*>")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
MAX_SPOKEN_CHARS = 600


def strip_model_tags(text: str) -> tuple[str, list[str]]:
    """Removes every <tag>-shaped token. Returns (clean text, tags removed)
    so the removal can be audited."""
    removed = [m.group(1).strip().lower() for m in _TAG_RE.finditer(text or "")]
    return _TAG_RE.sub("", text or "").strip(), removed


def speakable(text: str) -> str:
    t = _MD_LINK.sub(r"\1", text or "")
    t = _URL.sub("", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)  # bullet markers
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\n", ", ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) > MAX_SPOKEN_CHARS:
        cut = t[:MAX_SPOKEN_CHARS]
        end = max(cut.rfind("."), cut.rfind("।"), cut.rfind("?"), cut.rfind("!"))
        t = cut[: end + 1] if end > 200 else cut
    return t


def compose(text: str, *, moment: str | None, model: str) -> str:
    """Adds a template tag for a known moment, only on timbre-v3.0."""
    if model != TIMBRE_V3 or not moment:
        return text
    tag = {"order_paid": "excited", "order_cod": "excited", "confirm_amount": "pauses"}.get(moment)
    if tag is None or tag not in AUDIO_TAGS:
        return text
    if tag == "pauses":
        # A beat before the amount the buyer must check.
        return re.sub(r"(₹\s?[\d,]+(\.\d+)?)", r"<pauses> \1", text, count=1)
    return f"<{tag}> {text}"


# --- Localized phrases for key voice moments --------------------------------
# {amount} is always a "₹123.45" string, which Timbre reads correctly in every
# language. Keep these short: they are spoken, not read.

PHRASES: dict[str, dict[str, str]] = {
    "didnt_catch": {
        "hi-IN": "माफ़ कीजिए, मैं ठीक से सुन नहीं पाई। कृपया फिर से बोलिए।",
        "en-IN": "Sorry, I didn't catch that. Please say it again.",
        "ta-IN": "மன்னிக்கவும், சரியாக கேட்கவில்லை. மீண்டும் சொல்லுங்கள்.",
        "te-IN": "క్షమించండి, సరిగ్గా వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి.",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.",
        "ml-IN": "ക്ഷമിക്കണം, ശരിയായി കേട്ടില്ല. ദയവായി വീണ്ടും പറയൂ.",
        "mr-IN": "माफ करा, मला नीट ऐकू आले नाही. कृपया पुन्हा सांगा.",
        "bn-IN": "দুঃখিত, ঠিক শুনতে পাইনি। আবার বলুন।",
        "gu-IN": "માફ કરશો, બરાબર સંભળાયું નહીં. કૃપા કરીને ફરી બોલો.",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਠੀਕ ਤਰ੍ਹਾਂ ਸੁਣ ਨਹੀਂ ਸਕੀ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ।",
    },
    "confirm_amount": {
        "hi-IN": "आपका कुल {amount} है। आगे बढ़ने के लिए कृपया स्क्रीन पर टैप करके पुष्टि करें।",
        "en-IN": "Your total is {amount}. Please tap on the screen to confirm.",
        "ta-IN": "உங்கள் மொத்தம் {amount}. உறுதிப்படுத்த திரையில் தட்டவும்.",
        "te-IN": "మీ మొత్తం {amount}. నిర్ధారించడానికి దయచేసి స్క్రీన్‌పై ట్యాప్ చేయండి.",
        "kn-IN": "ನಿಮ್ಮ ಒಟ್ಟು ಮೊತ್ತ {amount}. ದೃಢೀಕರಿಸಲು ದಯವಿಟ್ಟು ಪರದೆಯ ಮೇಲೆ ಟ್ಯಾಪ್ ಮಾಡಿ.",
        "ml-IN": "നിങ്ങളുടെ ആകെ തുക {amount}. സ്ഥിരീകരിക്കാൻ സ്ക്രീനിൽ ടാപ്പ് ചെയ്യുക.",
        "mr-IN": "तुमची एकूण रक्कम {amount} आहे. पुष्टी करण्यासाठी कृपया स्क्रीनवर टॅप करा.",
        "bn-IN": "আপনার মোট {amount}। নিশ্চিত করতে স্ক্রিনে ট্যাপ করুন।",
        "gu-IN": "તમારો કુલ {amount} છે. ખાતરી કરવા માટે કૃપા કરીને સ્ક્રીન પર ટેપ કરો.",
        "pa-IN": "ਤੁਹਾਡਾ ਕੁੱਲ {amount} ਹੈ। ਪੁਸ਼ਟੀ ਕਰਨ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਸਕ੍ਰੀਨ 'ਤੇ ਟੈਪ ਕਰੋ।",
    },
    "choose_payment": {
        "hi-IN": "ऑर्डर तैयार है, कुल {amount}। वॉलेट या कैश ऑन डिलीवरी पर टैप कीजिए।",
        "en-IN": "Your order is ready, total {amount}. Tap Wallet or Cash on Delivery.",
        "ta-IN": "உங்கள் ஆர்டர் தயார், மொத்தம் {amount}. வாலெட் அல்லது கேஷ் ஆன் டெலிவரி தட்டவும்.",
        "te-IN": "మీ ఆర్డర్ సిద్ధంగా ఉంది, మొత్తం {amount}. వాలెట్ లేదా క్యాష్ ఆన్ డెలివరీ ట్యాప్ చేయండి.",
        "kn-IN": "ನಿಮ್ಮ ಆರ್ಡರ್ ಸಿದ್ಧವಾಗಿದೆ, ಒಟ್ಟು {amount}. ವಾಲೆಟ್ ಅಥವಾ ಕ್ಯಾಶ್ ಆನ್ ಡೆಲಿವರಿ ಟ್ಯಾಪ್ ಮಾಡಿ.",
        "ml-IN": "നിങ്ങളുടെ ഓർഡർ തയ്യാറാണ്, ആകെ {amount}. വാലറ്റ് അല്ലെങ്കിൽ ക്യാഷ് ഓൺ ഡെലിവറി ടാപ്പ് ചെയ്യുക.",
        "mr-IN": "तुमची ऑर्डर तयार आहे, एकूण {amount}. वॉलेट किंवा कॅश ऑन डिलिव्हरी वर टॅप करा.",
        "bn-IN": "আপনার অর্ডার প্রস্তুত, মোট {amount}। ওয়ালেট বা ক্যাশ অন ডেলিভারি ট্যাপ করুন।",
        "gu-IN": "તમારો ઓર્ડર તૈયાર છે, કુલ {amount}. વૉલેટ અથવા કેશ ઓન ડિલિવરી પર ટેપ કરો.",
        "pa-IN": "ਤੁਹਾਡਾ ਆਰਡਰ ਤਿਆਰ ਹੈ, ਕੁੱਲ {amount}। ਵਾਲਿਟ ਜਾਂ ਕੈਸ਼ ਆਨ ਡਿਲਿਵਰੀ 'ਤੇ ਟੈਪ ਕਰੋ।",
    },
    "order_paid": {
        "hi-IN": "बढ़िया! आपका ऑर्डर हो गया, {amount} वॉलेट से चुकाए गए।",
        "en-IN": "Done! Your order is placed and {amount} was paid from your wallet.",
        "ta-IN": "முடிந்தது! உங்கள் ஆர்டர் செய்யப்பட்டது, {amount} வாலெட்டிலிருந்து செலுத்தப்பட்டது.",
        "te-IN": "అయిపోయింది! మీ ఆర్డర్ పూర్తయింది, {amount} వాలెట్ నుండి చెల్లించబడింది.",
        "kn-IN": "ಆಯಿತು! ನಿಮ್ಮ ಆರ್ಡರ್ ಆಗಿದೆ, {amount} ವಾಲೆಟ್‌ನಿಂದ ಪಾವತಿಸಲಾಗಿದೆ.",
        "ml-IN": "കഴിഞ്ഞു! നിങ്ങളുടെ ഓർഡർ ചെയ്തു, {amount} വാലറ്റിൽ നിന്ന് അടച്ചു.",
        "mr-IN": "झाले! तुमची ऑर्डर झाली, {amount} वॉलेटमधून भरले.",
        "bn-IN": "হয়ে গেছে! আপনার অর্ডার হয়েছে, {amount} ওয়ালেট থেকে দেওয়া হয়েছে।",
        "gu-IN": "થઈ ગયું! તમારો ઓર્ડર થઈ ગયો, {amount} વૉલેટમાંથી ચૂકવાયા.",
        "pa-IN": "ਹੋ ਗਿਆ! ਤੁਹਾਡਾ ਆਰਡਰ ਹੋ ਗਿਆ, {amount} ਵਾਲਿਟ ਤੋਂ ਭਰੇ ਗਏ।",
    },
    "order_cod": {
        "hi-IN": "बढ़िया! आपका ऑर्डर हो गया। डिलीवरी पर {amount} नकद दीजिए।",
        "en-IN": "Done! Your order is placed. Please pay {amount} in cash on delivery.",
        "ta-IN": "முடிந்தது! உங்கள் ஆர்டர் செய்யப்பட்டது. டெலிவரியின் போது {amount} பணமாக செலுத்துங்கள்.",
        "te-IN": "అయిపోయింది! మీ ఆర్డర్ పూర్తయింది. డెలివరీ సమయంలో {amount} నగదు చెల్లించండి.",
        "kn-IN": "ಆಯಿತು! ನಿಮ್ಮ ಆರ್ಡರ್ ಆಗಿದೆ. ಡೆಲಿವರಿ ಸಮಯದಲ್ಲಿ {amount} ನಗದು ಪಾವತಿಸಿ.",
        "ml-IN": "കഴിഞ്ഞു! നിങ്ങളുടെ ഓർഡർ ചെയ്തു. ഡെലിവറി സമയത്ത് {amount} പണമായി നൽകുക.",
        "mr-IN": "झाले! तुमची ऑर्डर झाली. डिलिव्हरीच्या वेळी {amount} रोख द्या.",
        "bn-IN": "হয়ে গেছে! আপনার অর্ডার হয়েছে। ডেলিভারির সময় {amount} নগদ দিন।",
        "gu-IN": "થઈ ગયું! તમારો ઓર્ડર થઈ ગયો. ડિલિવરી વખતે {amount} રોકડા આપો.",
        "pa-IN": "ਹੋ ਗਿਆ! ਤੁਹਾਡਾ ਆਰਡਰ ਹੋ ਗਿਆ। ਡਿਲਿਵਰੀ ਵੇਲੇ {amount} ਨਕਦ ਦਿਓ।",
    },
    "spoken_injection": {
        "hi-IN": "मैं दुकान के नियमों को बदल या अनदेखा नहीं कर सकती। आप क्या खरीदना चाहेंगे?",
        "en-IN": "I can't change or ignore the shop's rules. What would you like to buy?",
        "ta-IN": "கடையின் விதிகளை மாற்றவோ புறக்கணிக்கவோ முடியாது. நீங்கள் என்ன வாங்க விரும்புகிறீர்கள்?",
        "te-IN": "షాప్ నియమాలను మార్చలేను, విస్మరించలేను. మీరు ఏమి కొనాలనుకుంటున్నారు?",
        "kn-IN": "ಅಂಗಡಿಯ ನಿಯಮಗಳನ್ನು ಬದಲಾಯಿಸಲು ಅಥವಾ ನಿರ್ಲಕ್ಷಿಸಲು ಆಗುವುದಿಲ್ಲ. ನೀವು ಏನು ಖರೀದಿಸಲು ಬಯಸುತ್ತೀರಿ?",
        "ml-IN": "കടയുടെ നിയമങ്ങൾ മാറ്റാനോ അവഗണിക്കാനോ കഴിയില്ല. നിങ്ങൾക്ക് എന്താണ് വാങ്ങേണ്ടത്?",
        "mr-IN": "मी दुकानाचे नियम बदलू किंवा दुर्लक्षित करू शकत नाही. तुम्हाला काय घ्यायचे आहे?",
        "bn-IN": "আমি দোকানের নিয়ম বদলাতে বা উপেক্ষা করতে পারি না। আপনি কী কিনতে চান?",
        "gu-IN": "હું દુકાનના નિયમો બદલી કે અવગણી શકતી નથી. તમે શું ખરીદવા માંગો છો?",
        "pa-IN": "ਮੈਂ ਦੁਕਾਨ ਦੇ ਨਿਯਮ ਬਦਲ ਜਾਂ ਅਣਡਿੱਠੇ ਨਹੀਂ ਕਰ ਸਕਦੀ। ਤੁਸੀਂ ਕੀ ਖਰੀਦਣਾ ਚਾਹੋਗੇ?",
    },
    "added": {
        "hi-IN": "कार्ट में जोड़ दिया: {items}।",
        "en-IN": "Added to your cart: {items}.",
        "ta-IN": "கார்ட்டில் சேர்த்துவிட்டேன்: {items}.",
        "te-IN": "కార్ట్‌లో వేశాను: {items}.",
        "kn-IN": "ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿದ್ದೇನೆ: {items}.",
        "ml-IN": "കാർട്ടിൽ ചേർത്തു: {items}.",
        "mr-IN": "कार्टमध्ये टाकले: {items}.",
        "bn-IN": "কার্টে যোগ করেছি: {items}।",
        "gu-IN": "કાર્ટમાં ઉમેર્યું: {items}.",
        "pa-IN": "ਕਾਰਟ ਵਿੱਚ ਪਾ ਦਿੱਤਾ: {items}।",
    },
    "removed": {
        "hi-IN": "कार्ट से हटा दिया: {items}।",
        "en-IN": "Removed from your cart: {items}.",
        "ta-IN": "கார்ட்டிலிருந்து நீக்கிவிட்டேன்: {items}.",
        "te-IN": "కార్ట్ నుండి తీసేశాను: {items}.",
        "kn-IN": "ಕಾರ್ಟ್‌ನಿಂದ ತೆಗೆದಿದ್ದೇನೆ: {items}.",
        "ml-IN": "കാർട്ടിൽ നിന്ന് മാറ്റി: {items}.",
        "mr-IN": "कार्टमधून काढले: {items}.",
        "bn-IN": "কার্ট থেকে সরিয়েছি: {items}।",
        "gu-IN": "કાર્ટમાંથી દૂર કર્યું: {items}.",
        "pa-IN": "ਕਾਰਟ ਵਿੱਚੋਂ ਹਟਾ ਦਿੱਤਾ: {items}।",
    },
    "not_stocked": {
        "hi-IN": "माफ़ कीजिए, यह अभी हमारी दुकान में नहीं है। कुछ और चाहिए?",
        "en-IN": "Sorry, we don't stock that right now. Anything else?",
        "ta-IN": "மன்னிக்கவும், இது இப்போது எங்கள் கடையில் இல்லை. வேறு ஏதாவது வேண்டுமா?",
        "te-IN": "క్షమించండి, అది ప్రస్తుతం మా షాప్‌లో లేదు. ఇంకేమైనా కావాలా?",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ಅದು ಈಗ ನಮ್ಮ ಅಂಗಡಿಯಲ್ಲಿ ಇಲ್ಲ. ಬೇರೆ ಏನಾದರೂ ಬೇಕೆ?",
        "ml-IN": "ക്ഷമിക്കണം, അത് ഇപ്പോൾ ഞങ്ങളുടെ കടയിൽ ഇല്ല. വേറെ എന്തെങ്കിലും വേണോ?",
        "mr-IN": "माफ करा, ते सध्या आमच्या दुकानात नाही. आणखी काही हवे आहे का?",
        "bn-IN": "দুঃখিত, এটা এখন আমাদের দোকানে নেই। আর কিছু লাগবে?",
        "gu-IN": "માફ કરશો, તે હમણાં અમારી દુકાનમાં નથી. બીજું કંઈ જોઈએ છે?",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਇਹ ਹੁਣ ਸਾਡੀ ਦੁਕਾਨ ਵਿੱਚ ਨਹੀਂ ਹੈ। ਹੋਰ ਕੁਝ ਚਾਹੀਦਾ ਹੈ?",
    },
    "cart_has": {
        "hi-IN": "आपके कार्ट में है: {items}।",
        "en-IN": "Your cart has: {items}.",
        "ta-IN": "உங்கள் கார்ட்டில் உள்ளவை: {items}.",
        "te-IN": "మీ కార్ట్‌లో ఉన్నవి: {items}.",
        "kn-IN": "ನಿಮ್ಮ ಕಾರ್ಟ್‌ನಲ್ಲಿ ಇರುವುದು: {items}.",
        "ml-IN": "നിങ്ങളുടെ കാർട്ടിൽ ഉള്ളത്: {items}.",
        "mr-IN": "तुमच्या कार्टमध्ये आहे: {items}.",
        "bn-IN": "আপনার কার্টে আছে: {items}।",
        "gu-IN": "તમારા કાર્ટમાં છે: {items}.",
        "pa-IN": "ਤੁਹਾਡੇ ਕਾਰਟ ਵਿੱਚ ਹੈ: {items}।",
    },
    "cart_empty": {
        "hi-IN": "आपका कार्ट अभी खाली है।",
        "en-IN": "Your cart is empty.",
        "ta-IN": "உங்கள் கார்ட் இப்போது காலியாக உள்ளது.",
        "te-IN": "మీ కార్ట్ ఇప్పుడు ఖాళీగా ఉంది.",
        "kn-IN": "ನಿಮ್ಮ ಕಾರ್ಟ್ ಈಗ ಖಾಲಿ ಇದೆ.",
        "ml-IN": "നിങ്ങളുടെ കാർട്ട് ഇപ്പോൾ ശൂന്യമാണ്.",
        "mr-IN": "तुमचे कार्ट सध्या रिकामे आहे.",
        "bn-IN": "আপনার কার্ট এখন খালি।",
        "gu-IN": "તમારું કાર્ટ હમણાં ખાલી છે.",
        "pa-IN": "ਤੁਹਾਡਾ ਕਾਰਟ ਹੁਣ ਖਾਲੀ ਹੈ।",
    },
    # Spoken versions: natural sentences with the items inside, no colon —
    # Timbre pauses at "X: Y." and live listening tests lost everything after it.
    "added_say": {
        "hi-IN": "{items} कार्ट में जोड़ दिया।",
        "en-IN": "Added {items} to your cart.",
        "ta-IN": "{items} கார்ட்டில் சேர்த்துவிட்டேன்.",
        "te-IN": "{items} కార్ట్‌లో వేశాను.",
        "kn-IN": "{items} ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿದ್ದೇನೆ.",
        "ml-IN": "{items} കാർട്ടിൽ ചേർത്തു.",
        "mr-IN": "{items} कार्टमध्ये टाकले.",
        "bn-IN": "{items} কার্টে যোগ করেছি।",
        "gu-IN": "{items} કાર્ટમાં ઉમેર્યું.",
        "pa-IN": "{items} ਕਾਰਟ ਵਿੱਚ ਪਾ ਦਿੱਤਾ।",
    },
    "removed_say": {
        "hi-IN": "{items} कार्ट से हटा दिया।",
        "en-IN": "Removed {items} from your cart.",
        "ta-IN": "{items} கார்ட்டிலிருந்து நீக்கிவிட்டேன்.",
        "te-IN": "{items} కార్ట్ నుండి తీసేశాను.",
        "kn-IN": "{items} ಕಾರ್ಟ್‌ನಿಂದ ತೆಗೆದಿದ್ದೇನೆ.",
        "ml-IN": "{items} കാർട്ടിൽ നിന്ന് മാറ്റി.",
        "mr-IN": "{items} कार्टमधून काढले.",
        "bn-IN": "{items} কার্ট থেকে সরিয়েছি।",
        "gu-IN": "{items} કાર્ટમાંથી દૂર કર્યું.",
        "pa-IN": "{items} ਕਾਰਟ ਵਿੱਚੋਂ ਹਟਾ ਦਿੱਤਾ।",
    },
    "cart_has_say": {
        "hi-IN": "आपके कार्ट में {items} है।",
        "en-IN": "Your cart has {items}.",
        "ta-IN": "உங்கள் கார்ட்டில் {items} உள்ளது.",
        "te-IN": "మీ కార్ట్‌లో {items} ఉన్నాయి.",
        "kn-IN": "ನಿಮ್ಮ ಕಾರ್ಟ್‌ನಲ್ಲಿ {items} ಇದೆ.",
        "ml-IN": "നിങ്ങളുടെ കാർട്ടിൽ {items} ഉണ്ട്.",
        "mr-IN": "तुमच्या कार्टमध्ये {items} आहे.",
        "bn-IN": "আপনার কার্টে {items} আছে।",
        "gu-IN": "તમારા કાર્ટમાં {items} છે.",
        "pa-IN": "ਤੁਹਾਡੇ ਕਾਰਟ ਵਿੱਚ {items} ਹੈ।",
    },
    "we_have": {
        "hi-IN": "हमारे पास {items} और भी बहुत कुछ है। आपको क्या चाहिए?",
        "en-IN": "We have {items}, and more. What would you like?",
        "ta-IN": "எங்களிடம் {items} மற்றும் பல உள்ளன. உங்களுக்கு என்ன வேண்டும்?",
        "te-IN": "మా దగ్గర {items} ఇంకా చాలా ఉన్నాయి. మీకు ఏమి కావాలి?",
        "kn-IN": "ನಮ್ಮ ಬಳಿ {items} ಮತ್ತು ಇನ್ನೂ ಹಲವು ಇವೆ. ನಿಮಗೆ ಏನು ಬೇಕು?",
        "ml-IN": "ഞങ്ങളുടെ പക്കൽ {items} തുടങ്ങി പലതും ഉണ്ട്. നിങ്ങൾക്ക് എന്താണ് വേണ്ടത്?",
        "mr-IN": "आमच्याकडे {items} आणि बरेच काही आहे. तुम्हाला काय हवे आहे?",
        "bn-IN": "আমাদের কাছে {items} আর অনেক কিছু আছে। আপনার কী লাগবে?",
        "gu-IN": "અમારી પાસે {items} અને ઘણું બધું છે. તમને શું જોઈએ છે?",
        "pa-IN": "ਸਾਡੇ ਕੋਲ {items} ਅਤੇ ਹੋਰ ਬਹੁਤ ਕੁਝ ਹੈ। ਤੁਹਾਨੂੰ ਕੀ ਚਾਹੀਦਾ ਹੈ?",
    },
    "language_set": {
        "hi-IN": "ठीक है, अब मैं हिन्दी में बात करूँगी।",
        "en-IN": "Okay, I'll speak in English now.",
        "ta-IN": "சரி, இனி தமிழில் பேசுகிறேன்.",
        "te-IN": "సరే, ఇప్పటి నుండి తెలుగులో మాట్లాడతాను.",
        "kn-IN": "ಸರಿ, ಈಗಿನಿಂದ ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ.",
        "ml-IN": "ശരി, ഇനി മലയാളത്തിൽ സംസാരിക്കാം.",
        "mr-IN": "ठीक आहे, आता मी मराठीत बोलेन.",
        "bn-IN": "ঠিক আছে, এখন থেকে বাংলায় কথা বলব।",
        "gu-IN": "સારું, હવેથી હું ગુજરાતીમાં વાત કરીશ.",
        "pa-IN": "ਠੀਕ ਹੈ, ਹੁਣ ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਾਂਗੀ।",
    },
    "help": {
        "hi-IN": "माफ़ कीजिए, मैं समझ नहीं पाई। आप सामान का नाम और कितना चाहिए बोलिए, जैसे 'दो पैकेट मैगी'।",
        "en-IN": "Sorry, I didn't get that. Tell me the item and how many, like 'two packets of Maggi'.",
        "ta-IN": "மன்னிக்கவும், புரியவில்லை. பொருளின் பெயரும் எத்தனை வேண்டும் என்றும் சொல்லுங்கள், உதாரணமாக 'இரண்டு பால்'.",
        "te-IN": "క్షమించండి, అర్థం కాలేదు. వస్తువు పేరు, ఎన్ని కావాలో చెప్పండి, ఉదాహరణకు 'రెండు ప్యాకెట్ల పాలు'.",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ಅರ್ಥವಾಗಲಿಲ್ಲ. ವಸ್ತುವಿನ ಹೆಸರು ಮತ್ತು ಎಷ್ಟು ಬೇಕು ಎಂದು ಹೇಳಿ, ಉದಾಹರಣೆಗೆ 'ಎರಡು ಹಾಲು'.",
        "ml-IN": "ക്ഷമിക്കണം, മനസ്സിലായില്ല. സാധനത്തിന്റെ പേരും എത്ര വേണമെന്നും പറയൂ, ഉദാഹരണത്തിന് 'രണ്ട് പാൽ'.",
        "mr-IN": "माफ करा, समजले नाही. वस्तूचे नाव आणि किती हवे ते सांगा, जसे 'दोन दूध'.",
        "bn-IN": "দুঃখিত, বুঝতে পারিনি। জিনিসের নাম আর কতগুলো চাই বলুন, যেমন 'দুটো দুধ'।",
        "gu-IN": "માફ કરશો, સમજાયું નહીં. વસ્તુનું નામ અને કેટલું જોઈએ તે કહો, જેમ કે 'બે દૂધ'.",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਸਮਝ ਨਹੀਂ ਆਇਆ। ਚੀਜ਼ ਦਾ ਨਾਮ ਅਤੇ ਕਿੰਨਾ ਚਾਹੀਦਾ ਦੱਸੋ, ਜਿਵੇਂ 'ਦੋ ਦੁੱਧ'।",
    },
    "cart_total": {
        "hi-IN": "अब कुल {amount} है।",
        "en-IN": "Your cart total is {amount}.",
        "ta-IN": "இப்போது மொத்தம் {amount}.",
        "te-IN": "ఇప్పుడు మొత్తం {amount}.",
        "kn-IN": "ಈಗ ಒಟ್ಟು {amount}.",
        "ml-IN": "ഇപ്പോൾ ആകെ {amount}.",
        "mr-IN": "आता एकूण {amount}.",
        "bn-IN": "এখন মোট {amount}।",
        "gu-IN": "હવે કુલ {amount}.",
        "pa-IN": "ਹੁਣ ਕੁੱਲ {amount}।",
    },
    "voice_unavailable": {
        "hi-IN": "अभी आवाज़ सेवा उपलब्ध नहीं है, कृपया टाइप करें।",
        "en-IN": "Voice is unavailable right now, please type instead.",
        "ta-IN": "இப்போது குரல் சேவை கிடைக்கவில்லை, தயவுசெய்து தட்டச்சு செய்யுங்கள்.",
        "te-IN": "ప్రస్తుతం వాయిస్ అందుబాటులో లేదు, దయచేసి టైప్ చేయండి.",
        "kn-IN": "ಈಗ ಧ್ವನಿ ಸೇವೆ ಲಭ್ಯವಿಲ್ಲ, ದಯವಿಟ್ಟು ಟೈಪ್ ಮಾಡಿ.",
        "ml-IN": "ഇപ്പോൾ വോയ്സ് ലഭ്യമല്ല, ദയവായി ടൈപ്പ് ചെയ്യുക.",
        "mr-IN": "आत्ता आवाज सेवा उपलब्ध नाही, कृपया टाइप करा.",
        "bn-IN": "এখন ভয়েস পরিষেবা পাওয়া যাচ্ছে না, দয়া করে টাইপ করুন।",
        "gu-IN": "હમણાં અવાજ સેવા ઉપલબ્ધ નથી, કૃપા કરીને ટાઇપ કરો.",
        "pa-IN": "ਹੁਣ ਆਵਾਜ਼ ਸੇਵਾ ਉਪਲਬਧ ਨਹੀਂ ਹੈ, ਕਿਰਪਾ ਕਰਕੇ ਟਾਈਪ ਕਰੋ।",
    },
}


def phrase(key: str, language: str | None, **values: str) -> str:
    table = PHRASES[key]
    template = table.get(normalize(language)) or table["en-IN"]
    return template.format(**values)


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}".replace(".00", "")
