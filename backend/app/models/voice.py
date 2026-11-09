"""Tables for the merchant voice features.

VoiceProfile — the merchant's "Shop Voice": a Gnani voice-clone embedding,
created only with explicit consent (stored with the row and in the audit
log). The reference audio itself is never stored, only the embedding Gnani
returns.

CallBatch — one Gnani batch transcription job over uploaded phone-order
recordings ("Call Insights"). Transcripts are kept so the merchant can read
them; demand signals extracted from them carry no caller identity.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # {"embedding": str, "shape": [1, 768], "dtype": "torch.bfloat16"} — exactly
    # the `speaker_embedding` object Gnani's synthesis endpoint accepts.
    embedding: Mapped[dict] = mapped_column(JSON, nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_seconds: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


class CallBatch(Base):
    __tablename__ = "call_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gnani_job_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="STARTED")
    file_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Per file: {"file": ..., "language": ..., "full_transcript": ..., "segments": [{speaker_id, text, start, end}]}
    transcripts: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    demand_signals_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
