"""The no-model order parser across all 10 languages (+ Hinglish/Tinglish/Tanglish).

ADD sentences must be understood (with the right products); remove / don't-want /
question / payment sentences must NEVER be read as an add — they go to the model
or the remove path. Sentences come from a live test across every language.
"""

import pytest

from app.agent import fast_path

BRANDS = {"maggi", "amul", "tata", "aashirvaad", "parle-g", "coca-cola"}
BRAND_ONLY = {"maggi": "GRO-008"}

ADD = [
    ('hi', 'मुझे दो किलो चीनी और एक लीटर दूध चाहिए'),
    ('hi', 'एक पैकेट नमक और दो ब्रेड दे दो'),
    ('hi', 'तीन अंडे और एक किलो प्याज़ डाल दीजिए'),
    ('hi', 'दो किलो आलू चाहिए'),
    ('hi', 'एक मैगी और एक पनीर भी जोड़ दो'),
    ('hinglish', 'do kilo pyaaz aur ek doodh daal do'),
    ('hinglish', 'ek bread aur do anda chahiye'),
    ('hinglish', 'teen Maggi packet add kar do'),
    ('en', 'I need two kg onions and one litre milk'),
    ('en', 'add a bread and six eggs please'),
    ('en', 'give me 2 packets of salt'),
    ('en', 'one kilo sugar and one paneer'),
    ('te', 'రెండు కిలోల చక్కెర మరియు ఒక బ్రెడ్ కావాలి'),
    ('te', 'ఒక కిలో టమాటాలు వేయండి'),
    ('te', 'మూడు ప్యాకెట్ల మ్యాగీ కావాలి'),
    ('te', 'ఒక పనీర్ మరియు ఒక లీటర్ పాలు ఇవ్వండి'),
    ('tinglish', 'rendu kilo ullipayalu oka bread kavali'),
    ('ta', 'இரண்டு கிலோ வெங்காயம் வேண்டும்'),
    ('ta', 'ஒரு லிட்டர் பால் மற்றும் ஒரு ரொட்டி கொடுங்கள்'),
    ('ta', 'ஒரு கிலோ சர்க்கரை சேர்க்கவும்'),
    ('ta', 'ஆறு முட்டை வேணும்'),
    ('kn', 'ಎರಡು ಕಿಲೋ ಈರುಳ್ಳಿ ಮತ್ತು ಒಂದು ಹಾಲು ಬೇಕು'),
    ('kn', 'ಒಂದು ಕಿಲೋ ಸಕ್ಕರೆ ಸೇರಿಸಿ'),
    ('kn', 'ಒಂದು ಬ್ರೆಡ್ ಕೊಡಿ'),
    ('kn', 'ಆರು ಮೊಟ್ಟೆ ಬೇಕು'),
    ('ml', 'രണ്ട് കിലോ ഉള്ളിയും ഒരു ലിറ്റർ പാലും വേണം'),
    ('ml', 'ഒരു കിലോ പഞ്ചസാര വേണം'),
    ('ml', 'ഒരു ബ്രെഡ് തരൂ'),
    ('ml', 'ആറ് മുട്ടയും ഒരു പനീറും വേണം'),
    ('ml', 'ഒരു കിലോ തക്കാളി ചേർക്കൂ'),
    ('mr', 'मला दोन किलो साखर आणि एक पनीर हवं आहे'),
    ('mr', 'एक लिटर दूध द्या'),
    ('mr', 'दोन किलो कांदे आणि सहा अंडी हवी आहेत'),
    ('mr', 'एक ब्रेड टाका'),
    ('bn', 'আমাকে এক কেজি আলু আর ছয়টা ডিম দিন'),
    ('bn', 'দুই কেজি পেঁয়াজ আর এক লিটার দুধ চাই'),
    ('bn', 'একটা পাউরুটি দাও'),
    ('bn', 'এক কেজি চিনি দিন'),
    ('gu', 'મને એક કિલો ખાંડ અને એક લિટર દૂધ જોઈએ છે'),
    ('gu', 'બે કિલો ડુંગળી આપો'),
    ('gu', 'એક બ્રેડ અને છ ઈંડા જોઈએ'),
    ('gu', 'એક કિલો બટાકા ઉમેરો'),
    ('pa', 'ਮੈਨੂੰ ਦੋ ਪੈਕੇਟ ਮੈਗੀ ਅਤੇ ਇੱਕ ਲੀਟਰ ਦੁੱਧ ਚਾਹੀਦਾ ਹੈ'),
    ('pa', 'ਇੱਕ ਕਿਲੋ ਖੰਡ ਦਿਓ'),
    ('pa', 'ਦੋ ਕਿਲੋ ਪਿਆਜ਼ ਅਤੇ ਛੇ ਅੰਡੇ ਚਾਹੀਦੇ ਹਨ'),
    ('pa', 'ਇੱਕ ਬ੍ਰੈੱਡ ਪਾ ਦਿਓ'),
]

NOT_ADD = [
    ('hi', 'मैगी हटा दो'),
    ('hi', 'दूध नहीं चाहिए'),
    ('hinglish', 'salt hata do'),
    ('hinglish', 'doodh nahi chahiye'),
    ('hinglish', 'maggi nikaal do'),
    ('ta', 'பனீர் வேண்டாம்'),
    ('tanglish', 'Paneer Venta'),
    ('tanglish', 'paneer vendam'),
    ('te', 'ఉప్పు తీసేయండి'),
    ('te', 'పాలు వద్దు'),
    ('tinglish', 'paalu vaddu'),
    ('kn', 'ಹಾಲು ಬೇಡ'),
    ('ml', 'പാൽ വേണ്ട, അത് മാറ്റൂ'),
    ('mr', 'पनीर काढून टाका'),
    ('mr', 'दूध नको'),
    ('bn', 'দুধ বাদ দিন'),
    ('bn', 'দুধ চাই না'),
    ('gu', 'દૂધ કાઢી નાખો'),
    ('gu', 'દૂધ નથી જોઈતું'),
    ('pa', 'ਮੈਗੀ ਹਟਾ ਦਿਓ'),
    ('pa', 'ਦੁੱਧ ਨਹੀਂ ਚਾਹੀਦਾ'),
    ('en', 'remove the milk'),
    ('en', 'how much is milk'),
    ('hi', 'अब पेमेंट कर दो'),
    ('bn', 'এবার পেমেন্ট করে দিন'),
    ('ml', 'പണം അടയ്ക്കൂ'),
]


@pytest.mark.parametrize("lang,sentence", ADD)
def test_add_sentences_are_understood(lang, sentence):
    plan = fast_path.parse(sentence, BRANDS, BRAND_ONLY)
    assert plan, f"{lang}: not understood: {sentence}"
    assert "tea" not in [p.tag for p in plan], "a 'want' word was mistaken for tea"


@pytest.mark.parametrize("lang,sentence", NOT_ADD)
def test_removals_questions_payments_are_never_adds(lang, sentence):
    assert fast_path.parse(sentence, BRANDS, BRAND_ONLY) is None


def test_malayalam_inflected_milk_and_onion():
    plan = fast_path.parse("രണ്ട് കിലോ ഉള്ളിയും ഒരു ലിറ്റർ പാലും വേണം", BRANDS, BRAND_ONLY)
    assert [(p.tag, p.size) for p in plan] == [("onion", (2.0, "kg")), ("milk", (1.0, "l"))]


def test_bengali_counters():
    plan = fast_path.parse("আমাকে এক কেজি আলু আর ছয়টা ডিম দিন", BRANDS, BRAND_ONLY)
    assert [(p.tag, p.quantity) for p in plan] == [("potato", None), ("eggs", 6)]


@pytest.mark.parametrize("heard,fixed", [
    ("Salt Tata दो।", "Salt hata दो।"),
    ("salt tata do", "salt hata do"),
    ("Tata दो packet chai", "Tata दो packet chai"),
    ("ek Tata salt daal do", "ek Tata salt daal do"),
])
def test_tata_do_mishearing(heard, fixed):
    assert fast_path.fix_mishearings(heard) == fixed
