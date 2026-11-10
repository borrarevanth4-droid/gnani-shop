"""Which `language_code` to send Prisma v3.0.

`indic-auto` alone has to guess among ten languages from a few seconds of
audio, and short clips in one language are sometimes heard as another
(Telugu as Kannada or Tamil, for example). Prisma v3.0 also accepts one to
four language codes as *hints* — not a lock: if the speaker uses another
supported language, the transcript follows it (docs.gnani.ai, Prisma v3.0).

So when we know the buyer's language (they picked it, or the conversation
already settled on it) we send it first, plus English — which is exactly
what code-mixed speech like Tinglish or Hinglish needs: the native language
for the sentence, English for "Amul butter", "two packets", "add cheyyi".
With no known language we fall back to pure auto-detection.
"""

from app.voice.languages import DEFAULT_LANGUAGE, is_supported


def stt_language_code(preferred: str | None) -> str:
    if not preferred or not is_supported(preferred):
        return "indic-auto"
    if preferred == DEFAULT_LANGUAGE:
        # English first, Hindi second: Indian English is very often Hinglish.
        return "en-IN,hi-IN"
    return f"{preferred},{DEFAULT_LANGUAGE}"
