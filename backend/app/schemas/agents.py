from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str
    delivery_mode: Literal["EMBEDDED", "EXTERNAL"]
    scopes: list[str]
    spend_limit_paise: int = Field(gt=0)
    standing_instruction: str | None = None


class AgentSummaryOut(BaseModel):
    id: str
    name: str
    delivery_mode: str
    scopes: list[str]
    spend_limit_paise: int
    spent_paise: int
    autopay_enabled: bool = False
    autopay_limit_paise: int = 0
    autopay_spent_paise: int = 0
    status: str
    standing_instruction: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class AgentCreateResponse(AgentSummaryOut):
    # Populated exactly once, on this response, and only for delivery_mode
    # == "EXTERNAL". Never present for EMBEDDED, never returned by any
    # other endpoint, ever — see docs/ARCHITECTURE.md.
    key: str | None = None


class AgentActionOut(BaseModel):
    timestamp: datetime
    session_id: str
    event_type: str
    tool_name: str | None
    decision: str | None
    rule_name: str | None
    reason: str | None


class AgentDetailOut(AgentSummaryOut):
    recent_actions: list[AgentActionOut]


class AgentRunRequest(BaseModel):
    """Optional, and optional on purpose: the body was added after this
    endpoint shipped, so a caller that sends none still runs the credential's
    stored standing_instruction exactly as before."""

    instruction: str | None = None


class AgentRunResult(BaseModel):
    reply: str
    status: str
    cart: dict


class AutopaySettingsRequest(BaseModel):
    enabled: bool
    # Optional: keep the current limit (or the default, the first time).
    limit_paise: int | None = Field(default=None, gt=0)


class PendingApprovalOut(BaseModel):
    session_id: str
    tool_name: str | None
    arguments: dict | None
    rule_name: str | None
    reason: str | None
    updated_at: datetime
