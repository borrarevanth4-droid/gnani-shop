from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.agent import harness
from app.agent.harness import SessionOwnershipError
from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.core import rate_limit
from app.core.config import settings
from app.auth.routing import AuthRequirement, SecureAPIRoute, requires
from app.database import get_db
from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    PaymentInfoOut,
    PendingActionOut,
    ProductSuggestionOut,
    UpsellOfferOut,
)

router = APIRouter(tags=["agent"], route_class=SecureAPIRoute)


def to_response(result) -> ChatResponse:
    return ChatResponse(
        reply=result.reply,
        status=result.status,
        pending=PendingActionOut(**result.pending) if result.pending else None,
        cart=result.cart,
        payment=PaymentInfoOut(**result.payment) if result.payment else None,
        upsell=UpsellOfferOut(**result.upsell) if result.upsell else None,
        product_suggestion=ProductSuggestionOut(**result.product_suggestion) if result.product_suggestion else None,
    )



@router.post("/api/agent/chat", response_model=ChatResponse)
@requires(AuthRequirement.BUYER, AuthRequirement.AGENT)
def chat(
    payload: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", None)
    rate_limit.check(principal.credential_id or principal.user_id, "chat", settings.rate_limit_chat_per_minute)
    try:
        result = harness.handle_chat(
            db, payload.session_id, principal.user_id, payload.message, payload.budget_paise, request_id,
            language=payload.language,
        )
    except SessionOwnershipError:
        raise HTTPException(status_code=403, detail="This session belongs to a different principal.")
    return to_response(result)


@router.post("/api/agent/confirm", response_model=ChatResponse)
@requires(AuthRequirement.BUYER, AuthRequirement.AGENT)
def confirm(
    payload: ConfirmRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", None)
    if principal.type == "agent" and payload.approve:
        # REQUIRE_CONFIRMATION means "a human decides". An agent key may
        # withdraw (decline) its own pending action, but never approve it —
        # the owner approves in Gnani Shop (POST /api/agents/{id}/confirm).
        # Mode B autopay never comes through here: it is decided inside the
        # harness, under AgentAutopayRule.
        raise HTTPException(
            status_code=403,
            detail="Only the agent's owner can approve this. It is waiting for them in Gnani Shop → Agents.",
        )
    try:
        result = harness.handle_confirm(db, payload.session_id, principal.user_id, payload.approve, request_id)
    except SessionOwnershipError:
        raise HTTPException(status_code=403, detail="This session belongs to a different principal.")
    return to_response(result)
