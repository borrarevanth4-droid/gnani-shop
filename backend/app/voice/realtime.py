"""Realtime voice conversation — a WebSocket bridge to Gnani's streaming STT.

    browser mic ──PCM 16 kHz──▶ this server ──1024-byte frames──▶ wss://api.vachana.ai/stt/v3/stream
                                                    ◀── speech_start / processing / transcript (+ language)
    on each final transcript: voice gate → agent harness → rulebook (app/voice/service.py)
    ◀── {"type": "turn", ...} — the reply text, the speakable text and the cart; the
        browser then plays the reply through /api/voice/tts/stream (Timbre).

Browser protocol (JSON text frames, plus binary audio frames):
  client → server: binary = 16-bit little-endian mono PCM at 16 kHz (any chunk size)
                   {"type": "commit"}  close the current utterance now (push-to-talk release)
                   {"type": "stop"}    end the session
  server → client: {"type": "ready"} | {"type": "speech_start"} | {"type": "processing"}
                   {"type": "transcript", "text", "language"} | {"type": "turn", ...VoiceTurnOut}
                   {"type": "error", "message"} | {"type": "fallback", "message"}

Auth: browsers can't set headers on a WebSocket, so the buyer's JWT comes as
a `token` query parameter and is verified exactly like a Bearer header.
BUYER only. Like every other voice path, this can fill a cart and ask to pay,
but has no route to approve or pay — that stays a tap.
"""

import asyncio
import json
import uuid

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.auth.principal import _resolve_from_jwt
from app.core import rate_limit
from app.core.config import settings
from app.core.logging import logger
from app.database import SessionLocal
from app.repositories import agent_session_repo
from app.voice import service as voice_service
from app.voice.gateway import USER_AGENT, voice_gateway
from app.voice.hints import stt_language_code
from app.voice.keyterms import build_keyterms
from app.voice.languages import TIMBRE_V3, TIMBRE_V25, is_supported

router = APIRouter(tags=["voice-realtime"])

FRAME_BYTES = 1024  # Gnani requires exactly 512 samples × 16-bit per frame


def _session_factory():
    return SessionLocal()


@router.websocket("/api/voice/stream")
async def voice_stream(ws: WebSocket) -> None:
    token = ws.query_params.get("token") or ""
    session_id = ws.query_params.get("session_id") or f"voice-{uuid.uuid4().hex[:12]}"
    tts_model = ws.query_params.get("tts_model")
    tts_model = tts_model if tts_model in (TIMBRE_V3, TIMBRE_V25) else None
    hint = ws.query_params.get("language")
    hint = hint if is_supported(hint) else None
    budget = ws.query_params.get("budget_paise")
    budget_paise = int(budget) if budget and budget.isdigit() else None

    db = _session_factory()
    try:
        principal = _resolve_from_jwt(token, db) if token else None
        keyterms = build_keyterms(db) if principal else []
        owner_ok = True
        if principal is not None:
            existing = agent_session_repo.get_session(db, session_id)
            owner_ok = existing is None or existing.user_id == principal.user_id
    finally:
        db.close()
    if principal is None or principal.type != "buyer":
        await ws.close(code=1008, reason="Sign in as a buyer to use voice.")
        return
    if not owner_ok:
        await ws.close(code=1008, reason="That conversation belongs to another account.")
        return
    try:
        rate_limit.check(principal.user_id, "voice", settings.rate_limit_voice_per_minute)
    except Exception:  # noqa: BLE001
        await ws.close(code=1008, reason="Too many voice sessions — try again in a minute.")
        return

    await ws.accept()
    if not voice_gateway.configured or voice_gateway.stt_breaker.is_open():
        await ws.send_json({"type": "fallback", "message": "Voice is unavailable right now — please type."})
        await ws.close()
        return

    headers = {
        "x-api-key-id": settings.gnani_api_key,
        "model": settings.gnani_stt_model,
        "language_code": stt_language_code(hint),
        "format": settings.gnani_stt_format,
        "x-sample-rate": "16000",
        "x-idle-timeout-sec": "120",
        "x-min-silence-ms": "700",
        "keyterms": json.dumps(keyterms[:200], ensure_ascii=False),
        "topic": voice_service.STT_TOPIC,
        "User-Agent": USER_AGENT,
    }

    try:
        async with websockets.connect(
            f"{settings.gnani_ws_url}/stt/v3/stream", additional_headers=headers, open_timeout=10, max_size=2**22
        ) as gnani:
            voice_gateway.stt_breaker.record_success()
            await ws.send_json({"type": "ready", "session_id": session_id})
            await asyncio.gather(
                _browser_to_gnani(ws, gnani),
                _gnani_to_browser(ws, gnani, principal.user_id, session_id, budget_paise, tts_model, hint),
            )
    except WebSocketDisconnect:
        return
    except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as e:
        voice_gateway.stt_breaker.record_failure()
        logger.warning("realtime voice failed", extra={"session_id": session_id, "error": str(e)})
        db = _session_factory()
        try:
            await run_in_threadpool(voice_service.fallback, db, session_id, principal.user_id, None, hint, str(e))
        finally:
            db.close()
        try:
            await ws.send_json({"type": "fallback", "message": "Voice connection lost — please type or try again."})
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


async def _browser_to_gnani(ws: WebSocket, gnani) -> None:
    buffer = bytearray()
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                buffer.extend(msg["bytes"])
                while len(buffer) >= FRAME_BYTES:
                    await gnani.send(bytes(buffer[:FRAME_BYTES]))
                    del buffer[:FRAME_BYTES]
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "commit":
                    if buffer:
                        await gnani.send(bytes(buffer).ljust(FRAME_BYTES, b"\x00"))
                        buffer.clear()
                    await gnani.send(json.dumps({"type": "commit"}))
                elif data.get("type") == "stop":
                    break
    finally:
        await gnani.close()


async def _gnani_to_browser(ws: WebSocket, gnani, user_id: str, session_id: str, budget_paise: int | None,
                            tts_model: str | None, hint: str | None) -> None:
    async for raw in gnani:
        if isinstance(raw, bytes):
            continue
        frame = json.loads(raw)
        kind = frame.get("type")
        if kind in ("speech_start", "processing"):
            await ws.send_json({"type": kind})
        elif kind == "error":
            await ws.send_json({"type": "error", "message": frame.get("message", "Gnani error")})
        elif kind == "transcript":
            text = (frame.get("text") or "").strip()
            lang = frame.get("detected_language_code")
            await ws.send_json({"type": "transcript", "text": text, "language": lang})
            db = _session_factory()
            try:
                result = await run_in_threadpool(
                    lambda: voice_service.act_on_transcript(
                        db,
                        session_id=session_id,
                        user_id=user_id,
                        transcript=text,
                        detected_language=lang,
                        stt_model=settings.gnani_stt_model,
                        budget_paise=budget_paise,
                        request_id=None,
                        tts_model=tts_model,
                        language_hint=hint,
                        stt_info={"model": settings.gnani_stt_model, "realtime": True,
                                  "processing_time_ms": frame.get("latency"),
                                  "audio_seconds": (frame.get("audio_duration_ms") or 0) / 1000},
                        stt_latency_ms=frame.get("latency"),
                        stt_format=settings.gnani_stt_format,
                        audio_seconds=(frame.get("audio_duration_ms") or 0) / 1000,
                    )
                )
                await ws.send_json({"type": "turn", **json.loads(json.dumps(result.__dict__, default=str))})
            finally:
                db.close()
