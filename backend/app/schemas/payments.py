from typing import Literal

from pydantic import BaseModel, Field


class PayRequest(BaseModel):
    order_id: int
    method: Literal["wallet", "cod"]


class PaymentResultOut(BaseModel):
    status: str  # final order status: "PAID" | "CONFIRMED_COD" | "FAILED" | ...
    order_id: int
    amount_paise: int
    method: str
    authorized_by: str
    reference: str | None = None
    money_moved: bool
    message: str
    wallet_balance_paise: int | None = None


class PaymentMethodOut(BaseModel):
    name: str
    display_name: str
    agent_autopay_allowed: bool


class WalletEntryOut(BaseModel):
    id: int
    amount_paise: int
    kind: str
    order_id: int | None
    note: str | None
    created_at: str


class WalletOut(BaseModel):
    balance_paise: int
    is_demo_money: bool = True
    entries: list[WalletEntryOut]


class TopUpRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    # Client-generated; makes a retried top-up a no-op.
    request_key: str = Field(min_length=6, max_length=60)
