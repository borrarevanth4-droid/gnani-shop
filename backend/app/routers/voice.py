"""Voice endpoints — every Gnani Vachana feature the app exposes.

Buyer:
  POST /api/voice/turn          push-to-talk: one recorded clip → one agent turn
  POST /api/voice/tts           text → WAV (Timbre sync)
  POST /api/voice/tts/stream    text → streamed PCM chunks (Timbre SSE), NDJSON
  WS   /api/voice/stream        realtime conversation (app/voice/realtime.py)
Anyone signed in:
  POST /api/voice/lab/transcribe  the Voice Lab: one clip, Prisma's output formats side by side
Public:
  GET  /api/voice/languages     the 10 languages, both voice catalogs, audio tags
  GET  /api/voice/status        is Gnani configured / currently reachable

Structural guarantee: nothing in this file imports the payment service or
calls harness.handle_confirm. Speech can fill a cart and *ask* to pay; a tap
on the screen is what approves and pays.
"""

import base64
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.harness import SessionOwnershipError
from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.auth.routing import AuthRequirement, SecureAPIRoute, public, requires
from app.core import rate_limit
from app.core.config import settings
from app.database import get_db
from app.voice import languages as langs
from app.voice import service as voice_service
from app.voice.gateway import VoiceGatewayError, voice_gateway
from app.voice.keyterms import build_keyterms

router = APIRouter(tags=["voice"], route_class=SecureAPIRoute)

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~2.5 min of 16 kHz WAV; Prisma REST itself caps at 30 s
MAX_TTS_CHARS = 800


def _rate_key(p: Principal) -> str:
    return p.credential_id or p.user_id


async def _read_audio(audio: UploadFile) -> bytes:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large — keep clips under 30 seconds.")
    return data


# ------------------------------------------------------------------ public


@router.get("/api/voice/languages")
@public
def voice_languages() -> dict:
    return {**langs.catalog(), "defaults": {
        "stt_model": settings.gnani_stt_model,
        "stt_language": settings.gnani_stt_language,
        "stt_format": settings.gnani_stt_format,
        "tts_model": settings.gnani_tts_model,
        "tts_voice": settings.gnani_tts_voice,
        "tts_sample_rate": settings.gnani_tts_sample_rate,
    }}


@router.get("/api/voice/status")
@public
def voice_status() -> dict:
    return voice_gateway.status()


# ------------------------------------------------------------------ push-to-talk turn


class VoiceTurnOut(BaseModel):
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
    stt: dict = Field(default_factory=dict)
    fell_back_to_text: bool = False
    error: str | None = None


@router.post("/api/voice/turn", response_model=VoiceTurnOut)
@requires(AuthRequirement.BUYER)
async def voice_turn(
    request: Request,
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    budget_paise: int | None = Form(None),
    tts_model: str | None = Form(None),
    language_hint: str | None = Form(None),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> VoiceTurnOut:
    rate_limit.check(_rate_key(principal), "voice", settings.rate_limit_voice_per_minute)
    data = await _read_audio(audio)
    from starlette.concurrency import run_in_threadpool

    try:
        result = await run_in_threadpool(
            voice_service.run_voice_turn,
            db,
            session_id=session_id,
            user_id=principal.user_id,
            audio=data,
            budget_paise=budget_paise,
            request_id=getattr(request.state, "request_id", None),
            tts_model=tts_model if tts_model in (langs.TIMBRE_V3, langs.TIMBRE_V25) else None,
            language_hint=language_hint if langs.is_supported(language_hint) else None,
        )
    except SessionOwnershipError:
        raise HTTPException(status_code=403, detail="This session belongs to a different principal.")
    return VoiceTurnOut(**result.__dict__)


# ------------------------------------------------------------------ text to speech


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TTS_CHARS)
    voice: str | None = None
    model: str | None = None
    language: str | None = None
    speed: float = Field(default=1.0, ge=0.85, le=1.15)
    session_id: str | None = None


def _resolve_voice(req: TtsRequest) -> tuple[str, str, str]:
    """(model, voice, language) — validated against Gnani's catalog, so a
    bad combination is fixed here instead of becoming a 400 from Gnani."""
    model = req.model if req.model in (langs.TIMBRE_V3, langs.TIMBRE_V25) else settings.gnani_tts_model
    language = req.language if (req.language == langs.HINGLISH_TTS_CODE or langs.is_supported(req.language)) else None
    voice = req.voice or settings.gnani_tts_voice
    if model == langs.TIMBRE_V25:
        if not langs.voice_is_valid(model, voice):
            voice = langs.v25_voice_for(language or langs.DEFAULT_LANGUAGE, langs.voice_gender(voice) or "female")
        # v2.5 voices have one preferred language; Hinglish only has Poorvi.
        if language is None:
            language = langs.V25_PREFERRED_LANGUAGE.get(voice, langs.DEFAULT_LANGUAGE)
    else:
        if not langs.voice_is_valid(model, voice):
            voice = settings.gnani_tts_voice
        if language == langs.HINGLISH_TTS_CODE:
            language = "hi-IN"
    # Always explicit — under "auto", Devanagari text is read as Hindi even
    # when it is Marathi, and Latin text is always read as English.
    return model, voice, language or langs.DEFAULT_LANGUAGE


@router.post("/api/voice/tts")
@requires(AuthRequirement.BUYER, AuthRequirement.MERCHANT)
def tts(req: TtsRequest, request: Request, principal: Principal = Depends(get_principal),
        db: Session = Depends(get_db)) -> Response:
    rate_limit.check(_rate_key(principal), "voice", settings.rate_limit_voice_per_minute)
    model, voice, language = _resolve_voice(req)
    try:
        result = voice_gateway.synthesize(req.text, voice=voice, model=model, language=language, speed=req.speed)
    except VoiceGatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
    voice_service.log_synthesis(
        db, session_id=req.session_id or f"tts:{principal.user_id}", user_id=principal.user_id, model=model,
        voice=voice, language=language, characters=len(req.text), latency_ms=result.latency_ms,
        request_id=getattr(request.state, "request_id", None), streamed=False, cost_paise=result.cost_paise,
    )
    return Response(content=result.audio, media_type=result.content_type,
                    headers={"X-Gnani-Model": model, "X-Gnani-Voice": voice, "X-Gnani-Latency-Ms": str(result.latency_ms)})


@router.post("/api/voice/tts/stream")
@requires(AuthRequirement.BUYER, AuthRequirement.MERCHANT)
def tts_stream(req: TtsRequest, request: Request, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)) -> StreamingResponse:
    """Streams raw 16-bit mono PCM as NDJSON lines
    {"i": n, "audio": base64, "final": bool} — the browser starts playing the
    first chunk while Gnani is still synthesising the rest."""
    rate_limit.check(_rate_key(principal), "voice", settings.rate_limit_voice_per_minute)
    model, voice, language = _resolve_voice(req)
    sample_rate = settings.gnani_tts_sample_rate
    try:
        chunks = voice_gateway.synthesize_stream(req.text, voice=voice, model=model, language=language,
                                                 speed=req.speed, sample_rate=sample_rate)
        first = next(chunks)  # surfaces connection/auth errors as a clean 503 before streaming starts
    except StopIteration:
        first = None
    except VoiceGatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
    voice_service.log_synthesis(
        db, session_id=req.session_id or f"tts:{principal.user_id}", user_id=principal.user_id, model=model,
        voice=voice, language=language, characters=len(req.text), latency_ms=None,
        request_id=getattr(request.state, "request_id", None), streamed=True,
    )

    def lines():
        if first is not None:
            yield json.dumps({"i": first.index, "audio": base64.b64encode(first.audio).decode(), "final": first.is_final}) + "\n"
        try:
            for c in chunks:
                yield json.dumps({"i": c.index, "audio": base64.b64encode(c.audio).decode(), "final": c.is_final}) + "\n"
        except VoiceGatewayError as e:
            yield json.dumps({"error": str(e), "final": True}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"X-Sample-Rate": str(sample_rate), "X-Gnani-Model": model, "X-Gnani-Voice": voice,
                                      "Access-Control-Expose-Headers": "X-Sample-Rate, X-Gnani-Model, X-Gnani-Voice"})


# ------------------------------------------------------------------ Voice Lab


@router.post("/api/voice/lab/transcribe")
@requires(AuthRequirement.BUYER, AuthRequirement.MERCHANT)
async def lab_transcribe(
    audio: UploadFile = File(...),
    formats: str = Form("transcribe,verbatim,codemix,transliterate"),
    compare_keyterms: bool = Form(True),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """The same clip through Prisma v3.0 in each output format, plus (once)
    with vs. without catalog keyterms — so the differences are visible."""
    rate_limit.check(_rate_key(principal), "voice-lab", 6)
    data = await _read_audio(audio)
    wanted = [f.strip() for f in formats.split(",") if f.strip() in ("transcribe", "verbatim", "codemix", "transliterate")][:4]
    keyterms = build_keyterms(db)
    from starlette.concurrency import run_in_threadpool

    def run(fmt: str, with_keyterms: bool) -> dict:
        try:
            r = voice_gateway.transcribe(data, fmt=fmt, keyterms=keyterms if with_keyterms else None,
                                         topic=voice_service.STT_TOPIC if with_keyterms else None)
            return {"format": fmt, "keyterms": with_keyterms, "transcript": r.transcript,
                    "detected_language": r.detected_language, "processing_time_ms": int((r.processing_time_s or 0) * 1000),
                    "round_trip_ms": r.latency_ms}
        except VoiceGatewayError as e:
            return {"format": fmt, "keyterms": with_keyterms, "error": str(e)}

    results = []
    for fmt in wanted:
        results.append(await run_in_threadpool(run, fmt, True))
    if compare_keyterms and wanted:
        results.append(await run_in_threadpool(run, wanted[0], False))
    return {"model": settings.gnani_stt_model, "language_code": "indic-auto", "keyterm_count": len(keyterms),
            "results": results}
