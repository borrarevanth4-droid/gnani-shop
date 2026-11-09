"""One voice turn, end to end.

    audio ─▶ Gnani Prisma (speech → text + detected language)
          ─▶ voice gate (app/voice/policy.py: unclear? injection? → stop here)
          ─▶ the SAME agent harness typed chat uses (model proposes, rulebook decides)
          ─▶ speakable reply in the buyer's language (app/voice/spoken.py)
          ─▶ the browser plays it with Gnani Timbre (streaming, /api/voice/tts/stream)

Every step is written to the audit log. Raw audio is never stored — only
the transcript, which is what the agent acted on.

What this module deliberately cannot do: approve a pending action or pay.
It only ever calls `harness.handle_chat`. A spoken "yes, pay" while a
payment is pending gets the harness's standard "please confirm first" reply;
confirming is a tap (POST /api/agent/confirm), paying is a tap
(POST /api/payments/pay).
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent import harness
from app.audit.service import AuditService
from app.core.config import settings
from app.core.logging import logger
from app.repositories import agent_session_repo
from app.voice import spoken
from app.voice.gateway import SttResult, VoiceGatewayError, voice_gateway
from app.voice.keyterms import build_keyterms
from app.voice.languages import TIMBRE_V3, normalize
from app.voice.policy import HeardUtterance, default_voice_policy

_audit = AuditService()
_voice_policy = default_voice_policy()

STT_TOPIC = (
    "Grocery shopping at an Indian kirana store: product names, brands, quantities in kg, grams, litres and "
    "packets, prices in rupees, adding to cart, removing items, checkout and payment."
)


@dataclass
class VoiceTurnResult:
    transcript: str
    language: str
    detected_language: str | None
    gate_allowed: bool
    gate_rule: str
    reply: str
    spoken_text: str
    status: str
    cart: dict
    pending: dict | None = None
    payment: dict | None = None
    upsell: dict | None = None
    product_suggestion: dict | None = None
    stt: dict = field(default_factory=dict)
    fell_back_to_text: bool = False
    error: str | None = None


def _stt_info(r: SttResult) -> dict:
    return {
        "model": r.model,
        "format": r.format,
        "processing_time_ms": int((r.processing_time_s or 0) * 1000),
        "end_to_end_latency_ms": int((r.end_to_end_latency_s or 0) * 1000),
        "round_trip_ms": r.latency_ms,
        "audio_seconds": r.audio_seconds,
        "request_id": r.request_id,
    }


def _moment(result) -> str | None:
    if result.payment and result.payment.get("status") == "PAID":
        return "order_paid"
    if result.payment and result.payment.get("status") == "CONFIRMED_COD":
        return "order_cod"
    if result.status == "awaiting_confirmation":
        return "confirm_amount"
    return None


def _previous_text(db: Session, session_id: str) -> str | None:
    """The last thing the assistant said — Prisma uses it as context, which
    is what makes a follow-up like "add one more" transcribe correctly."""
    for m in reversed(agent_session_repo.list_messages(db, session_id)):
        if m.role == "assistant" and m.content:
            return m.content[-600:]
    return None


def run_voice_turn(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    audio: bytes,
    budget_paise: int | None,
    request_id: str | None,
    tts_model: str | None = None,
    language_hint: str | None = None,
) -> VoiceTurnResult:
    tts_model = tts_model or settings.gnani_tts_model

    # 1. Gnani hears it -------------------------------------------------------
    try:
        stt = voice_gateway.transcribe(
            audio,
            language=language_hint or settings.gnani_stt_language,
            keyterms=build_keyterms(db),
            topic=STT_TOPIC,
            previous_text=_previous_text(db, session_id),
        )
    except VoiceGatewayError as e:
        return fallback(db, session_id, user_id, request_id, language_hint, str(e))

    return act_on_transcript(
        db,
        session_id=session_id,
        user_id=user_id,
        transcript=stt.transcript,
        detected_language=stt.detected_language,
        stt_model=stt.model,
        truncated=stt.truncated,
        budget_paise=budget_paise,
        request_id=request_id,
        tts_model=tts_model,
        language_hint=language_hint,
        stt_info=_stt_info(stt),
        stt_latency_ms=stt.latency_ms,
        stt_cost_paise=stt.cost_paise,
        stt_format=stt.format,
        audio_seconds=stt.audio_seconds,
    )


def act_on_transcript(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    transcript: str,
    detected_language: str | None,
    stt_model: str,
    budget_paise: int | None,
    request_id: str | None,
    tts_model: str | None = None,
    language_hint: str | None = None,
    truncated: bool = False,
    stt_info: dict | None = None,
    stt_latency_ms: int | None = None,
    stt_cost_paise: int | None = None,
    stt_format: str | None = None,
    audio_seconds: float | None = None,
) -> VoiceTurnResult:
    """Everything after Gnani has heard the buyer — shared by push-to-talk
    (REST) and the realtime conversation (WebSocket), so both get the same
    gate, the same agent, the same rulebook and the same audit trail."""
    tts_model = tts_model or settings.gnani_tts_model
    stt_info = stt_info or {}
    language = normalize(detected_language or language_hint)
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="voice_transcribed",
        actor="user",
        model_used=stt_model,
        latency_ms=stt_latency_ms,
        cost_paise=stt_cost_paise,
        tool_args={
            "detected_language": detected_language,
            "language": language,
            "format": stt_format,
            "processing_time_ms": stt_info.get("processing_time_ms"),
            "audio_seconds": audio_seconds,
            "truncated": truncated,
            "realtime": stt_info.get("realtime", False),
        },
        reason=transcript or "(no speech recognised)",
        request_id=request_id,
    )

    # The voice gate decides whether it's fit to act on ---------------------
    gate = _voice_policy.evaluate(
        HeardUtterance(transcript=transcript, detected_language=detected_language, stt_model=stt_model,
                       truncated=truncated)
    )
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="voice_gate_decision",
        actor="policy",
        decision="ALLOW" if gate.allowed else "DENY",
        rule_name=gate.rule_name,
        reason=gate.reason,
        request_id=request_id,
    )
    if not gate.allowed:
        if gate.rule_name == "SpokenInjectionRule":
            _audit.log_event(
                db, session_id=session_id, user_id=user_id, event_type="injection_detected", actor="system",
                tool_args={"source": "voice", "language": language}, reason=gate.reason, request_id=request_id,
            )
        reply = spoken.phrase(gate.phrase_key or "didnt_catch", language)
        return VoiceTurnResult(
            transcript=transcript, language=language, detected_language=detected_language,
            gate_allowed=False, gate_rule=gate.rule_name, reply=reply, spoken_text=reply, status="completed",
            cart=harness._cart_dict(db, user_id), stt=stt_info,
        )

    # Exactly the same agent + rulebook as typed chat ------------------------
    result = harness.handle_chat(
        db, session_id, user_id, transcript, budget_paise, request_id, language=language, channel="voice"
    )

    # Make the reply good to listen to — tags only from our templates --------
    clean, removed = spoken.strip_model_tags(result.reply)
    if removed:
        _audit.log_event(
            db, session_id=session_id, user_id=user_id, event_type="audio_tags_stripped", actor="policy",
            decision="DENY", rule_name="AudioTagControl", tool_args={"tags": removed},
            reason="Audio tags written by the language model were removed; only fixed templates may add them.",
            request_id=request_id,
        )
    spoken_text = spoken.compose(spoken.speakable(clean), moment=_moment(result), model=tts_model)

    return VoiceTurnResult(
        transcript=transcript,
        language=language,
        detected_language=detected_language,
        gate_allowed=True,
        gate_rule=gate.rule_name,
        reply=clean,
        spoken_text=spoken_text,
        status=result.status,
        cart=result.cart,
        pending=result.pending,
        payment=result.payment,
        upsell=result.upsell,
        product_suggestion=result.product_suggestion,
        stt=stt_info,
    )


def fallback(db: Session, session_id: str, user_id: str, request_id: str | None, language: str | None,
             error: str) -> VoiceTurnResult:
    """Gnani unreachable: say so in the buyer's language and fall back to
    typing. Nothing else in the shop is affected."""
    logger.warning("voice turn fell back to text", extra={"session_id": session_id, "error": error})
    _audit.log_event(
        db, session_id=session_id, user_id=user_id, event_type="voice_fallback_to_text", actor="system",
        decision="FAILED", reason=error, request_id=request_id,
    )
    lang = normalize(language)
    reply = spoken.phrase("voice_unavailable", lang)
    return VoiceTurnResult(
        transcript="", language=lang, detected_language=None, gate_allowed=False, gate_rule="VoiceUnavailable",
        reply=reply, spoken_text="", status="completed", cart=harness._cart_dict(db, user_id),
        fell_back_to_text=True, error=error,
    )


def log_synthesis(db: Session, *, session_id: str, user_id: str, model: str, voice: str | None, language: str | None,
                  characters: int, latency_ms: int | None, request_id: str | None, streamed: bool,
                  cost_paise: int | None = None) -> None:
    _audit.log_event(
        db,
        session_id=session_id,
        user_id=user_id,
        event_type="voice_synthesized",
        actor="system",
        model_used=model,
        latency_ms=latency_ms,
        cost_paise=cost_paise,
        tool_args={"voice": voice, "language": language, "characters": characters, "streamed": streamed},
        request_id=request_id,
    )


__all__ = ["run_voice_turn", "act_on_transcript", "VoiceTurnResult", "log_synthesis", "TIMBRE_V3"]
