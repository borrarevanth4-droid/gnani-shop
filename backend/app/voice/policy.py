"""The voice gate — deterministic rules applied to what Gnani *heard*, before
any of it reaches the shopping agent.

Same shape as the shopping policy engine (app/policy/) and the campaign
policy engine (app/campaigns/rules.py): small rule classes, each returning a
result when it objects and None when it doesn't, DENY first. No AI, no
network, no DB — pure functions over a `HeardUtterance`, unit-testable
without audio.

What these rules can and can't do is deliberately narrow. They decide only
whether an utterance is fit to *act on*. Everything after that — the cart,
the money — is still decided by the shopping rulebook, exactly as for typed
text. A spoken "pay now" can at most make the agent *propose* a payment,
which the rulebook always turns into "ask the human", and the voice endpoints
have no path to the confirm or pay endpoints at all.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.agent.injection_detection import scan_for_injection
from app.core.config import settings
from app.voice.languages import is_supported


@dataclass(frozen=True)
class HeardUtterance:
    transcript: str
    detected_language: str | None
    stt_model: str
    truncated: bool = False


@dataclass(frozen=True)
class VoiceGateResult:
    allowed: bool
    rule_name: str
    reason: str
    # Which localized phrase to speak back when not allowed (app/voice/spoken.py).
    phrase_key: str | None = None


def _meaningful_chars(text: str) -> int:
    """Letters and digits only — in any script. Indic vowel signs and
    viramas are Unicode category M (marks), so they count too."""
    return sum(1 for ch in text if unicodedata.category(ch)[0] in ("L", "N", "M"))


# Single-word noises Prisma sometimes returns for breath/background sound.
_NOISE_ONLY = re.compile(r"^\W*(hmm+|umm*|uh+|ah+|mm+|haan|ha|ok|okay|हम्म|अं)\W*$", re.IGNORECASE)


class VoiceConfidenceRule:
    """Prisma returns no confidence score, so "did we really hear something?"
    is decided from the transcript itself: empty, too short to be a request,
    or only a filler noise → ask the person to repeat. Never guess."""

    name = "VoiceConfidenceRule"

    def evaluate(self, u: HeardUtterance) -> VoiceGateResult | None:
        text = (u.transcript or "").strip()
        if not text:
            return VoiceGateResult(False, self.name, "No speech was recognised.", "didnt_catch")
        if _meaningful_chars(text) < settings.voice_min_transcript_chars:
            return VoiceGateResult(False, self.name, f"Transcript too short to act on: {text!r}.", "didnt_catch")
        if _NOISE_ONLY.match(text):
            return VoiceGateResult(False, self.name, f"Only a filler sound was heard: {text!r}.", "didnt_catch")
        return None


class TruncatedAudioRule:
    """Prisma marks a transcript `truncated` when the clip ran past its limit.
    A cut-off request ("add five kilo atta and ...") is not safe to act on."""

    name = "TruncatedAudioRule"

    def evaluate(self, u: HeardUtterance) -> VoiceGateResult | None:
        if u.truncated:
            return VoiceGateResult(False, self.name, "The recording was cut off before the end.", "didnt_catch")
        return None


class SpokenInjectionRule:
    """Spoken text gets the same injection scan as catalog text — in all ten
    languages plus romanised Hinglish. Speech is a new way for instructions
    to arrive that the buyer never meant (a TV in the background, someone
    else in the room), so an utterance that tries to override the shop's
    rules is not passed to the agent at all."""

    name = "SpokenInjectionRule"

    def evaluate(self, u: HeardUtterance) -> VoiceGateResult | None:
        match = scan_for_injection(u.transcript)
        if match is not None:
            return VoiceGateResult(
                False, self.name, f"Heard an instruction to bypass the shop's rules: {match!r}.", "spoken_injection"
            )
        return None


class SupportedLanguageRule:
    """Never refuses: an unrecognised language is answered in English rather
    than not at all. Recorded so Voice Insights can show how often it happens."""

    name = "SupportedLanguageRule"

    def evaluate(self, u: HeardUtterance) -> VoiceGateResult | None:
        return None


class VoicePolicyEngine:
    def __init__(self, rules: list) -> None:
        self.rules = rules

    def evaluate(self, u: HeardUtterance) -> VoiceGateResult:
        for rule in self.rules:
            result = rule.evaluate(u)
            if result is not None and not result.allowed:
                return result
        note = "" if is_supported(u.detected_language) else " (language not recognised — replying in English)"
        return VoiceGateResult(True, "__default__", f"Utterance accepted{note}.")


def default_voice_policy() -> VoicePolicyEngine:
    return VoicePolicyEngine([VoiceConfidenceRule(), TruncatedAudioRule(), SpokenInjectionRule(), SupportedLanguageRule()])
