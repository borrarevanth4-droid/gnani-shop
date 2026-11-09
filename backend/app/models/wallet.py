"""Gnani Shop Wallet — demo money, stored as an append-only ledger.

There is no "balance" column to drift out of sync: a wallet's balance is,
by definition, the sum of its ledger entries. Same philosophy as the audit
log (app/audit/repository.py): the record of what happened is the only
source of truth, and anything derivable from it stays derived.

Double-spend protection is a real UNIQUE constraint, not an application
check: every entry carries an `idempotency_key`, and a debit for an order is
always keyed `debit:order:<id>`, so a second debit for the same order can
only ever collide with the first (see app/payments/wallet.py).
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One wallet per buyer. The row exists mainly as something to lock
    # (SELECT ... FOR UPDATE on Postgres) while a debit is being decided.
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    entries: Mapped[list["WalletEntry"]] = relationship(back_populates="wallet", order_by="WalletEntry.id")


class WalletEntry(Base):
    __tablename__ = "wallet_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    # Signed: positive = money in (starting balance, top-up, refund),
    # negative = money out (an order debit).
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "opening" | "topup" | "debit" | "refund"
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    wallet: Mapped["Wallet"] = relationship(back_populates="entries")
