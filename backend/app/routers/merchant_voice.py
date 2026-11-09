"""Merchant-side Gnani features.

  GET    /api/merchant/voice/insights        how buyers use voice: languages, speed, fallbacks, cost
  GET    /api/merchant/voice/profile         the shop's cloned voice (if any)
  POST   /api/merchant/voice/profile         create it from 5–30 s of the merchant's own voice + consent
  POST   /api/merchant/voice/profile/preview speak a sentence in the cloned voice
  DELETE /api/merchant/voice/profile         delete it
  POST   /api/merchant/calls                 upload phone-order recordings → Gnani batch job
  GET    /api/merchant/calls                 list batches
  GET    /api/merchant/calls/{id}            refresh status; when done, transcripts + demand signals

All MERCHANT-only. Voice cloning refuses without explicit consent, and the
consent is stored with the profile and in the audit log. Only the merchant's
own voice, for their own shop.
"""

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.auth.routing import AuthRequirement, SecureAPIRoute, requires
from app.core import rate_limit
from app.core.logging import logger
from app.database import get_db
from app.models.audit_event import AuditEvent
from app.models.demand_signal import DemandSignal
from app.models.voice import CallBatch, VoiceProfile
from app.services import product_service
from app.voice.gateway import VoiceGatewayError, voice_gateway
from app.voice.languages import BY_CODE

router = APIRouter(tags=["merchant-voice"], route_class=SecureAPIRoute)
_audit = AuditService()

CONSENT_TEXT = (
    "I confirm this recording is my own voice, and I allow Gnani Shop to create a synthetic copy of it "
    "to speak announcements and offers for my own shop only."
)
TERMINAL_BATCH = {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}


# ------------------------------------------------------------------ insights


@router.get("/api/merchant/voice/insights")
@requires(AuthRequirement.MERCHANT)
def voice_insights(db: Session = Depends(get_db)) -> dict:
    """Computed from the audit log alone — the same single source of truth
    every other report in this project reads."""
    voice_types = ("voice_transcribed", "voice_gate_decision", "voice_synthesized", "voice_fallback_to_text",
                   "audio_tags_stripped")
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.event_type.in_(voice_types))))
    heard = [e for e in events if e.event_type == "voice_transcribed"]
    gate = [e for e in events if e.event_type == "voice_gate_decision"]
    spoken = [e for e in events if e.event_type == "voice_synthesized"]
    fallbacks = [e for e in events if e.event_type == "voice_fallback_to_text"]

    lang_counts = Counter((e.tool_args or {}).get("language") or "unknown" for e in heard)
    gate_denials = Counter(e.rule_name for e in gate if e.decision == "DENY")
    voices = Counter((e.tool_args or {}).get("voice") or "unknown" for e in spoken)
    stt_latencies = sorted(e.latency_ms for e in heard if e.latency_ms is not None)
    proc = sorted((e.tool_args or {}).get("processing_time_ms") or 0 for e in heard)
    audio_seconds = sum(((e.tool_args or {}).get("audio_seconds") or 0) for e in heard)
    tts_chars = sum(((e.tool_args or {}).get("characters") or 0) for e in spoken)

    def pct(values: list[int], q: float) -> int | None:
        if not values:
            return None
        return values[min(len(values) - 1, int(q * (len(values) - 1) + 0.5))]

    total_turns = len(heard) + len(fallbacks)
    return {
        "voice_turns": total_turns,
        "languages": [
            {"code": code, "name": BY_CODE[code].english_name if code in BY_CODE else code,
             "native_name": BY_CODE[code].native_name if code in BY_CODE else code, "turns": n}
            for code, n in lang_counts.most_common()
        ],
        "stt_round_trip_ms": {"p50": pct(stt_latencies, 0.5), "p95": pct(stt_latencies, 0.95)},
        "stt_model_processing_ms": {"p50": pct(proc, 0.5), "p95": pct(proc, 0.95)},
        "gate_refusals": [{"rule": r, "count": n} for r, n in gate_denials.most_common()],
        "fallback_to_text": len(fallbacks),
        "fallback_rate": round(len(fallbacks) / total_turns, 3) if total_turns else 0.0,
        "voices_used": [{"voice": v, "replies": n} for v, n in voices.most_common()],
        "audio_seconds_transcribed": round(audio_seconds, 1),
        "characters_spoken": tts_chars,
        "cost_paise": sum((e.cost_paise or 0) for e in heard + spoken),
    }


# ------------------------------------------------------------------ Shop Voice (cloning)


class VoiceProfileOut(BaseModel):
    display_name: str
    consent_text: str
    reference_seconds: float | None
    created_at: datetime


def _profile(db: Session, user_id: str) -> VoiceProfile | None:
    return db.scalar(select(VoiceProfile).where(VoiceProfile.owner_user_id == user_id))


@router.get("/api/merchant/voice/profile")
@requires(AuthRequirement.MERCHANT)
def get_profile(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    p = _profile(db, principal.user_id)
    return {
        "consent_text": CONSENT_TEXT,
        "profile": VoiceProfileOut(display_name=p.display_name, consent_text=p.consent_text,
                                   reference_seconds=p.reference_seconds, created_at=p.created_at).model_dump()
        if p else None,
    }


@router.post("/api/merchant/voice/profile")
@requires(AuthRequirement.MERCHANT)
async def create_profile(
    request: Request,
    audio: UploadFile = File(...),
    display_name: str = Form(..., min_length=1, max_length=80),
    consent: bool = Form(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    if not consent:
        raise HTTPException(status_code=400, detail="Voice cloning needs your explicit consent.")
    rate_limit.check(principal.user_id, "voice-clone", 3)
    data = await audio.read()
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Upload 5–30 seconds of clear speech (max 10 MB).")
    from starlette.concurrency import run_in_threadpool

    from app.voice.gateway import _wav_seconds

    seconds = _wav_seconds(data)
    if seconds is not None and not (4.5 <= seconds <= 31):
        raise HTTPException(status_code=400, detail=f"Recording is {seconds:.1f}s — Gnani needs 5 to 30 seconds.")
    try:
        embedding = await run_in_threadpool(voice_gateway.clone_embedding, data, audio.filename or "reference.wav")
    except VoiceGatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))

    existing = _profile(db, principal.user_id)
    if existing is not None:
        db.delete(existing)
        db.flush()
    db.add(VoiceProfile(owner_user_id=principal.user_id, display_name=display_name, embedding=embedding,
                        consent_given=True, consent_text=CONSENT_TEXT, reference_seconds=seconds))
    db.commit()
    _audit.log_event(
        db, session_id=f"shop-voice:{principal.user_id}", user_id=principal.user_id, event_type="voice_clone_created",
        actor="merchant", decision="ALLOW", model_used="vachana-vc-v1",
        tool_args={"display_name": display_name, "reference_seconds": seconds, "consent": True},
        reason=f"Consent recorded: {CONSENT_TEXT}", request_id=getattr(request.state, "request_id", None),
    )
    return get_profile(principal, db)


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.post("/api/merchant/voice/profile/preview")
@requires(AuthRequirement.MERCHANT)
def preview_profile(req: PreviewRequest, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)) -> Response:
    p = _profile(db, principal.user_id)
    if p is None:
        raise HTTPException(status_code=404, detail="No shop voice yet — record one first.")
    rate_limit.check(principal.user_id, "voice", 20)
    try:
        result = voice_gateway.synthesize(req.text, speaker_embedding=p.embedding, sample_rate=24000)
    except VoiceGatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return Response(content=result.audio, media_type=result.content_type)


@router.delete("/api/merchant/voice/profile")
@requires(AuthRequirement.MERCHANT)
def delete_profile(request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    p = _profile(db, principal.user_id)
    if p is not None:
        db.delete(p)
        db.commit()
        _audit.log_event(
            db, session_id=f"shop-voice:{principal.user_id}", user_id=principal.user_id,
            event_type="voice_clone_deleted", actor="merchant", decision="ALLOW",
            reason="Merchant deleted the shop voice.", request_id=getattr(request.state, "request_id", None),
        )
    return {"deleted": p is not None}


# ------------------------------------------------------------------ Call Insights (batch STT)


def _batch_out(b: CallBatch) -> dict:
    return {
        "id": b.id, "gnani_job_id": b.gnani_job_id, "status": b.status, "files": b.file_names,
        "transcripts": b.transcripts or [], "demand_signals_created": b.demand_signals_created, "error": b.error,
        "created_at": b.created_at, "completed_at": b.completed_at,
    }


@router.post("/api/merchant/calls")
@requires(AuthRequirement.MERCHANT)
async def upload_calls(
    request: Request,
    files: list[UploadFile] = File(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    if not files or len(files) > 10:
        raise HTTPException(status_code=400, detail="Upload between 1 and 10 recordings.")
    rate_limit.check(principal.user_id, "calls", 5)
    payload: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        if not data or len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename}: empty or over 10 MB.")
        payload.append((f.filename or f"call-{len(payload) + 1}.wav", data))
    from starlette.concurrency import run_in_threadpool

    try:
        job = await run_in_threadpool(voice_gateway.batch_create_and_start, payload)
    except VoiceGatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
    batch = CallBatch(owner_user_id=principal.user_id, gnani_job_id=job.job_id, status=job.status,
                      file_names=[n for n, _ in payload])
    db.add(batch)
    db.commit()
    db.refresh(batch)
    _audit.log_event(
        db, session_id=f"calls:{batch.id}", user_id=principal.user_id, event_type="call_batch_started",
        actor="merchant", model_used="prisma-v3.0", tool_args={"files": batch.file_names, "job_id": job.job_id},
        reason=f"{len(payload)} recording(s) sent to Gnani batch transcription with speaker separation.",
        request_id=getattr(request.state, "request_id", None),
    )
    return _batch_out(batch)


@router.get("/api/merchant/calls")
@requires(AuthRequirement.MERCHANT)
def list_calls(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(CallBatch).where(CallBatch.owner_user_id == principal.user_id)
                      .order_by(CallBatch.created_at.desc()).limit(20))
    return [_batch_out(b) for b in rows]


@router.get("/api/merchant/calls/{batch_id}")
@requires(AuthRequirement.MERCHANT)
def refresh_call_batch(batch_id: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    batch = db.get(CallBatch, batch_id)
    if batch is None or batch.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="No such batch.")
    if batch.status in TERMINAL_BATCH and batch.transcripts is not None:
        return _batch_out(batch)
    try:
        job = voice_gateway.batch_status(batch.gnani_job_id)
        batch.status = job.status
        if job.status in TERMINAL_BATCH:
            raw = voice_gateway.batch_transcripts(batch.gnani_job_id)
            batch.transcripts = [
                {
                    "file": t.get("original_path"),
                    "language": t.get("language_code"),
                    "duration_seconds": t.get("duration_seconds"),
                    "full_transcript": t.get("full_transcript", ""),
                    "segments": [
                        {"speaker": s.get("speaker_id"), "text": s.get("text"), "start": s.get("start_time"),
                         "end": s.get("end_time")}
                        for s in (t.get("segments") or [])
                    ],
                }
                for t in raw
            ]
            batch.completed_at = datetime.now(timezone.utc)
            batch.demand_signals_created = _demand_from_calls(db, batch)
    except VoiceGatewayError as e:
        batch.error = str(e)
    db.commit()
    return _batch_out(batch)


def _demand_from_calls(db: Session, batch: CallBatch) -> int:
    """Each call's transcript goes through the SAME demand extraction as chat
    (one LLM call, English category), and lands as an ordinary DemandSignal —
    so phone orders feed the same anonymous "N buyers asked for X" alerts.
    No caller identity is stored: the session id is just the batch and file."""
    from app.demand.capture import _extract

    created = 0
    for i, t in enumerate(batch.transcripts or []):
        text = (t.get("full_transcript") or "").strip()
        if not text:
            continue
        try:
            has_intent, category, attributes = _extract(text[:2000])
        except Exception as e:  # noqa: BLE001 — best effort, never fails the refresh
            logger.warning("call demand extraction failed", extra={"batch_id": batch.id, "error": str(e)})
            continue
        if not has_intent:
            continue
        # Do we stock it? Same deterministic catalog search the agent uses.
        match = product_service.list_products(db, category=None, search=category, min_price_paise=None,
                                              max_price_paise=None, page=1, page_size=1).items if category else []
        if match and match[0].stock <= 0:
            outcome, sku = "OUT_OF_STOCK", match[0].sku
        elif match:
            outcome, sku = "MATCHED", match[0].sku
        else:
            outcome, sku = "NO_MATCH", None
        db.add(DemandSignal(session_id=f"call:{batch.id}:{i}", raw_query=text[:500], category=category,
                            extracted_attributes=attributes, matched_sku=sku, outcome=outcome))
        created += 1
    return created
