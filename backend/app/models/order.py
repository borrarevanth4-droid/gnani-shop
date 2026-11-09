from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.orders.state_machine import OrderStatus


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), nullable=False)

    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=OrderStatus.PENDING.value)

    # "wallet" | "cod" — set when the buyer (or an autopay agent) picks how to
    # pay. Null until then.
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # The idempotency guarantee lives here: a real UNIQUE constraint, not an
    # application-level check. See app/orders/repository.py for how a
    # conflicting insert is handled (insert, catch IntegrityError, re-select
    # the winner — never "check then insert").
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)

    # Provider-side reference: the wallet ledger entry id ("wlt_<id>") for a
    # wallet payment, "cod_<order id>" for Cash on Delivery.
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # "captured" | "cod_confirmed" | "failed"
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # "wallet" | "cod"
    # Who authorised the money movement: "human_tap" (Mode A) or
    # "agent_autopay" (Mode B). Recorded on the row, not only in the audit log,
    # so an order screen can show it without a join.
    authorized_by: Mapped[str | None] = mapped_column(String(30), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider details for this attempt (balances before/after for a wallet
    # debit, etc.) — for debugging and the order detail view.
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="payments")
