"""Finishing a payment — the human tap (Mode A).

BUYER-only, on purpose: this is the one HTTP endpoint that moves money, and an
agent key can never reach it. An agent whose owner switched on autopay
(Mode B) pays through the harness instead, after the policy engine has
re-validated the cart — see app/agent/harness.py and app/payments/service.py.
The voice endpoints never reach here either.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_principal
from app.auth.principal import Principal
from app.auth.routing import AuthRequirement, SecureAPIRoute, requires
from app.database import get_db
from app.orders import repository as order_repo
from app.payments import service as payment_service
from app.payments import wallet as wallet_service
from app.schemas.payments import (
    PaymentMethodOut,
    PaymentResultOut,
    PayRequest,
    TopUpRequest,
    WalletEntryOut,
    WalletOut,
)

router = APIRouter(tags=["payments"], route_class=SecureAPIRoute)


@router.get("/api/payments/methods", response_model=list[PaymentMethodOut])
@requires(AuthRequirement.BUYER, AuthRequirement.AGENT)
def list_methods() -> list[PaymentMethodOut]:
    return [PaymentMethodOut(**m) for m in payment_service.available_methods()]


@router.post("/api/payments/pay", response_model=PaymentResultOut)
@requires(AuthRequirement.BUYER)
def pay(
    payload: PayRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> PaymentResultOut:
    order = order_repo.get_by_id(db, payload.order_id)
    if order is None or order.user_id != principal.user_id:
        # Same 404 whether it doesn't exist or isn't yours.
        raise HTTPException(status_code=404, detail="No such order.")
    result = payment_service.pay_order(
        db,
        order,
        method=payload.method,
        authorized_by=payment_service.AUTHORIZED_BY_HUMAN,
        request_id=getattr(request.state, "request_id", None),
    )
    return PaymentResultOut(**result.as_dict())


@router.get("/api/wallet", response_model=WalletOut)
@requires(AuthRequirement.BUYER)
def get_wallet(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> WalletOut:
    entries = wallet_service.list_entries(db, principal.user_id)
    return WalletOut(
        balance_paise=wallet_service.balance_paise(db, principal.user_id),
        entries=[
            WalletEntryOut(
                id=e.id, amount_paise=e.amount_paise, kind=e.kind, order_id=e.order_id, note=e.note,
                created_at=e.created_at.isoformat(),
            )
            for e in entries
        ],
    )


@router.post("/api/wallet/topup", response_model=WalletOut)
@requires(AuthRequirement.BUYER)
def top_up(
    payload: TopUpRequest, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> WalletOut:
    try:
        wallet_service.top_up(db, principal.user_id, payload.amount_paise, request_key=payload.request_key)
    except wallet_service.TopUpError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return get_wallet(principal, db)
