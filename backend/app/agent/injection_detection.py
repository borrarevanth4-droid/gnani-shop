"""Heuristic detection of prompt-injection-shaped text — in catalog data
(tool output) and, for voice, in what was heard. English, romanised Hinglish,
and native-script phrasings in all 10 of Gnani's languages.

This is defense-in-depth, NOT the actual security boundary. The real
guarantee is structural, in two independent places:

1. Tool results are passed to the model as clearly delimited, labelled
   `role: "tool"` messages (see app/agent/harness.py::_build_messages) —
   never spliced into the system prompt. The wire format itself marks this
   content as data, not instructions.
2. The policy engine evaluates the *proposed cart state*, deterministically,
   regardless of what the model does with any text it read. Even a model
   that fully "complies" with an injected instruction still has every
   proposed action re-checked in code — that's what
   tests/test_prompt_injection.py proves.

This scanner exists for the third leg: making an attempt visible in the
audit trail even when it fails, so "the system doesn't care" isn't just
asserted, it's logged.
"""

import re

_SUSPICIOUS_PATTERNS = [
    r"ignore (all )?(the )?(previous|prior|above)( \w+){0,3} instructions",
    r"disregard (all )?(the )?(previous|prior|above)",
    r"new instructions?:",
    r"you are now\b",
    r"system prompt",
    r"authoriz(ed|e)\s+unlimited",
    r"act as (an?|the)\s",
    r"\bdo anything now\b",
    r"without confirmation",
    r"proceed to payment immediately",
    r"(ignore|forget|bypass|override|disable) (all |the |your |every )*(rules|limits|policy|policies|restrictions)",
    r"pay (it |now |immediately )*without (asking|confirmation|my permission)",
    # Romanised Hinglish — how many people actually type or speak it, and
    # what Prisma's `codemix`/`transliterate` formats produce.
    r"(pichhl[ae]|purane|saare|sab) (instructions?|nirdesh|niyam|rules?) (bhool|bhul|ignore|chhod)",
    r"(rules?|niyam|limit) (ignore|bhool|bhul|tod|todo|hata|hatao) (karo|kar do|do|jao)",
    r"bina (puchhe|poochhe|confirmation|confirm|permission|izazat)",
    r"(turant|abhi) (payment|pay|bhugtan) kar(o| do)",
]

# Native-script phrasings across Gnani's 10 languages: "ignore/forget the
# previous instructions", "break the rules", "without asking/confirmation",
# "pay immediately". Literal substrings — scripts other than Latin have no
# case, and a regex word boundary means nothing in most Indic scripts.
_NATIVE_PHRASES: tuple[str, ...] = (
    # "forget / ignore the rules" in each language
    "नियम भूल", "नियमों को भूल", "नियम विसर", "நியமங்களை மற", "விதிகளை மற", "నియమాలు మర్చిపో", "నియమాలను మర్చిపో",
    "ನಿಯಮಗಳನ್ನು ಮರೆ", "ನಿಯಮ ಮರೆ", "നിയമങ്ങൾ മറക്ക", "নিয়ম ভুলে", "নিয়মগুলো ভুলে", "નિયમો ભૂલી", "ਨਿਯਮ ਭੁੱਲ",
    # Hindi
    "पिछले निर्देश", "सारे निर्देश भूल", "निर्देशों को भूल", "नियम तोड़", "नियमों को अनदेखा", "नियम भूल जाओ",
    "बिना पूछे", "बिना पुष्टि", "तुरंत भुगतान", "सीमा हटा",
    # Marathi
    "आधीच्या सूचना", "सूचना विसर", "नियम मोड", "न विचारता", "परवानगी न घेता", "लगेच पैसे भर",
    # Tamil
    "முந்தைய வழிமுறைகளை", "விதிகளை மீறு", "விதிகளை புறக்கணி", "கேட்காமல்", "உறுதிப்படுத்தாமல்", "உடனே பணம் செலுத்து",
    # Telugu
    "మునుపటి సూచనలు", "సూచనలను మర్చిపో", "నియమాలు ఉల్లంఘించు", "నియమాలను పట్టించుకోకు", "అడగకుండా",
    "నిర్ధారణ లేకుండా", "వెంటనే చెల్లించు",
    # Kannada
    "ಹಿಂದಿನ ಸೂಚನೆಗಳನ್ನು", "ನಿಯಮಗಳನ್ನು ಮುರಿ", "ನಿಯಮಗಳನ್ನು ನಿರ್ಲಕ್ಷಿಸು", "ಕೇಳದೆ", "ದೃಢೀಕರಣವಿಲ್ಲದೆ", "ತಕ್ಷಣ ಪಾವತಿಸು",
    # Malayalam
    "മുൻ നിർദ്ദേശങ്ങൾ", "നിയമങ്ങൾ ലംഘിക്ക", "നിയമങ്ങൾ അവഗണിക്ക", "ചോദിക്കാതെ", "സ്ഥിരീകരണമില്ലാതെ", "ഉടനെ പണം അടയ്ക്ക",
    # Bengali
    "আগের নির্দেশ", "নিয়ম ভাঙ", "নিয়ম উপেক্ষা", "জিজ্ঞাসা না করে", "নিশ্চিত না করে", "এখনই টাকা দাও",
    # Gujarati
    "અગાઉની સૂચનાઓ", "નિયમો તોડ", "નિયમોને અવગણ", "પૂછ્યા વગર", "પુષ્ટિ વગર", "તરત ચૂકવણી",
    # Punjabi
    "ਪਿਛਲੀਆਂ ਹਦਾਇਤਾਂ", "ਨਿਯਮ ਤੋੜ", "ਨਿਯਮਾਂ ਨੂੰ ਨਜ਼ਰਅੰਦਾਜ਼", "ਬਿਨਾਂ ਪੁੱਛੇ", "ਪੁਸ਼ਟੀ ਤੋਂ ਬਿਨਾਂ", "ਤੁਰੰਤ ਭੁਗਤਾਨ",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SUSPICIOUS_PATTERNS]


def scan_for_injection(text: str | None) -> str | None:
    """Returns the matched snippet (for the audit reason), or None."""
    if not text:
        return None
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            return match.group(0)
    for phrase in _NATIVE_PHRASES:
        if phrase in text:
            return phrase
    return None
