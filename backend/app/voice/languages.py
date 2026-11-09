"""The 10 Indian languages Gnani Vachana supports, and its voice catalogs.

Plain data, no logic beyond lookups — the single source of truth the
gateway, the language router, the frontend (via GET /api/voice/languages)
and the tests all read. Sourced from Gnani's docs:
  STT languages:  https://docs.gnani.ai/api/STT/languages
  Voice catalog:  https://docs.gnani.ai/api/TTS/available-voices
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # BCP-47 code Gnani uses, e.g. "te-IN"
    english_name: str
    native_name: str
    script: str


LANGUAGES: tuple[Language, ...] = (
    Language("hi-IN", "Hindi", "हिन्दी", "Devanagari"),
    Language("en-IN", "English", "English", "Latin"),
    Language("ta-IN", "Tamil", "தமிழ்", "Tamil"),
    Language("te-IN", "Telugu", "తెలుగు", "Telugu"),
    Language("kn-IN", "Kannada", "ಕನ್ನಡ", "Kannada"),
    Language("ml-IN", "Malayalam", "മലയാളം", "Malayalam"),
    Language("mr-IN", "Marathi", "मराठी", "Devanagari"),
    Language("bn-IN", "Bengali", "বাংলা", "Bengali"),
    Language("gu-IN", "Gujarati", "ગુજરાતી", "Gujarati"),
    Language("pa-IN", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi"),
)

BY_CODE: dict[str, Language] = {lang.code: lang for lang in LANGUAGES}
SUPPORTED_CODES: frozenset[str] = frozenset(BY_CODE)
DEFAULT_LANGUAGE = "en-IN"

# Hinglish is not an STT language (Prisma's en-IN setting already accepts
# Hindi–English mixed speech) but Timbre v2.5 has a dedicated voice for it.
HINGLISH_TTS_CODE = "hi-en"


def is_supported(code: str | None) -> bool:
    return code in SUPPORTED_CODES


def normalize(code: str | None) -> str:
    """Any value we might receive (None, "hi", "HI-in", "hi-en") → one of the
    10 supported codes. Unknown → English, never an exception: a language we
    can't name must not break a voice turn."""
    if not code:
        return DEFAULT_LANGUAGE
    c = code.strip()
    if c.lower() == HINGLISH_TTS_CODE:
        return "hi-IN"
    if "-" not in c:
        c = f"{c.lower()}-IN"
    c = c[:2].lower() + "-" + c[3:].upper() if len(c) >= 5 else c
    return c if c in SUPPORTED_CODES else DEFAULT_LANGUAGE


# --- Timbre v3.0: 13 voices, every voice speaks all 10 languages -----------

TIMBRE_V3 = "timbre-v3.0"
TIMBRE_V25 = "timbre-v2.5"

V3_VOICES: dict[str, str] = {
    "Shivani": "female", "Lakshmi": "female", "Kalpana": "female", "Chetana": "female",
    "Vasudha": "female", "Riyaa": "female", "Tarika": "female",
    "Avinash": "male", "Shubham": "male", "Prakash": "male", "Devansh": "male",
    "Yashraj": "male", "Harshad": "male",
}

# --- Timbre v2.5: 42 voices, each with one preferred language ---------------

V25_VOICES_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    "en-IN": ("Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish"),
    "hi-IN": ("Nalini", "Bhavna", "Yashvi", "Urmila", "Jwala", "Chitra", "Ambuja", "Deepak", "Roopesh",
              "Vikrant", "Hemraj", "Jalaj", "Omkar"),
    HINGLISH_TTS_CODE: ("Poorvi",),
    "ta-IN": ("Asmita", "Trisha", "Brinda", "Vedika", "Noopur"),
    "te-IN": ("Suhana", "Lehara", "Lavanya", "Yukti", "Varuni"),
    "kn-IN": ("Saanvi", "Kavin"),
    "ml-IN": ("Reshma", "Riyaan"),
    "mr-IN": ("Zahira", "Ishaan"),
    "bn-IN": ("Kirra", "Dhruva"),
    "gu-IN": ("Falak", "Veera"),
    "pa-IN": ("Mehuli", "Zayan"),
}

V25_MALE = frozenset({"Deepak", "Dhruva", "Girish", "Hemraj", "Ishaan", "Jalaj", "Kavin", "Omkar", "Pranav",
                      "Riyaan", "Roopesh", "Shlok", "Veera", "Vikrant", "Zayan"})

V25_PREFERRED_LANGUAGE: dict[str, str] = {
    voice: lang for lang, voices in V25_VOICES_BY_LANGUAGE.items() for voice in voices
}

# Voice cloning (merchant "Shop Voice"): model id for synthesis with an embedding.
VOICE_CLONE_MODEL = "vachana-vc-v1"

# The 13 audio tags Timbre v3.0 understands (https://docs.gnani.ai/api/TTS/tts-audio-tags).
AUDIO_TAGS: frozenset[str] = frozenset({
    "laugh", "giggle", "sigh", "exhales", "sniffles", "yawns", "coughs", "clears throat",
    "whispers", "shouting", "excited", "slow", "pauses",
})


def voice_gender(voice: str) -> str | None:
    if voice in V3_VOICES:
        return V3_VOICES[voice]
    if voice in V25_PREFERRED_LANGUAGE:
        return "male" if voice in V25_MALE else "female"
    return None


def voice_is_valid(model: str, voice: str) -> bool:
    if model == TIMBRE_V3:
        return voice in V3_VOICES
    if model == TIMBRE_V25:
        return voice in V25_PREFERRED_LANGUAGE
    return False


def v25_voice_for(language: str, gender: str = "female") -> str:
    """The first v2.5 voice whose preferred language matches, matching gender
    when possible — v2.5 voices sound best in their own language."""
    voices = V25_VOICES_BY_LANGUAGE.get(language) or V25_VOICES_BY_LANGUAGE[DEFAULT_LANGUAGE]
    for v in voices:
        if voice_gender(v) == gender:
            return v
    return voices[0]


def catalog() -> dict:
    """Everything the frontend's language chips and voice picker need."""
    return {
        "languages": [
            {"code": lang.code, "english_name": lang.english_name, "native_name": lang.native_name, "script": lang.script}
            for lang in LANGUAGES
        ],
        "stt": {
            "models": ["prisma-v3.0", "prisma-v2.5"],
            "auto_detect": "indic-auto",
            "formats": ["transcribe", "verbatim", "codemix", "transliterate"],
        },
        "tts": {
            TIMBRE_V3: {
                "voices": [{"name": v, "gender": g} for v, g in V3_VOICES.items()],
                "languages": "all 10, every voice",
                "audio_tags": sorted(AUDIO_TAGS),
            },
            TIMBRE_V25: {
                "voices": [
                    {"name": v, "gender": voice_gender(v), "preferred_language": lang}
                    for lang, voices in V25_VOICES_BY_LANGUAGE.items()
                    for v in voices
                ],
                "languages": "one preferred language per voice (+ Hinglish: Poorvi)",
                "audio_tags": [],
            },
        },
        "voice_clone_model": VOICE_CLONE_MODEL,
    }
