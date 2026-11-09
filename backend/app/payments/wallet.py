"""Gnani Shop Wallet: demo money with real accounting rules.

- The balance is derived from the ledger (app/models/wallet.py), never stored.
- A debit is keyed by order id under a UNIQUE constraint, so the same order
  can never be charged twice — not by a double tap, a retry, or a race.
- A debit that would take the balance below zero is refused, never partial.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order
from app.models.wallet import Wallet, WalletEntry
from app.payments.provider import PaymentProvider, ProviderOutcome


def get_or_create_wallet(db: Session, user_id: str) -> Wallet:
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if wallet is not None:
        return wallet
    wallet = Wallet(user_id=user_id)
    db.add(wallet)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if settings.wallet_starting_balance_paise > 0:
        db.add(
            WalletEntry(
                wallet_id=wallet.id,
                amount_paise=settings.wallet_starting_balance_paise,
                kind="opening",
                idempotency_key=f"opening:{user_id}",
                note="Demo starting balance",
            )
        )
    db.commit()
    db.refresh(wallet)
    return wallet


def balance_paise(db: Session, user_id: str) -> int:
    wallet = get_or_create_wallet(db, user_id)
    total = db.scalar(select(func.coalesce(func.sum(WalletEntry.amount_paise), 0)).where(WalletEntry.wallet_id == wallet.id))
    return int(total or 0)


def list_entries(db: Session, user_id: str, *, limit: int = 50) -> list[WalletEntry]:
    wallet = get_or_create_wallet(db, user_id)
    stmt = (
        select(WalletEntry).where(WalletEntry.wallet_id == wallet.id).order_by(WalletEntry.id.desc()).limit(limit)
    )
    return list(db.scalars(stmt))


class TopUpError(Exception):
    pass


def top_up(db: Session, user_id: str, amount_paise: int, *, request_key: str) -> int:
    """Adds demo money. `request_key` makes a retried top-up a no-op."""
    if amount_paise <= 0:
        raise TopUpError("Top-up amount must be positive.")
    if amount_paise > settings.wallet_max_topup_paise:
        raise TopUpError(f"A single top-up is limited to ₹{settings.wallet_max_topup_paise / 100:.0f}.")
    wallet = get_or_create_wallet(db, user_id)
    db.add(
        WalletEntry(
            wallet_id=wallet.id,
            amount_paise=amount_paise,
            kind="topup",
            idempotency_key=f"topup:{user_id}:{request_key}"[:80],
            note="Demo top-up",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # same request_key seen before: already applied
    return balance_paise(db, user_id)


class WalletProvider(PaymentProvider):
    name = "wallet"
    display_name = "Gnani Shop Wallet"
    agent_autopay_allowed = True

    def charge(self, db: Session, order: Order) -> ProviderOutcome:
        wallet = get_or_create_wallet(db, order.user_id)
        key = f"debit:order:{order.id}"

        existing = db.scalar(select(WalletEntry).where(WalletEntry.idempotency_key == key))
        if existing is not None:
            # Already charged for this order — report the original debit, never a second one.
            return ProviderOutcome(
                committed=True,
                money_moved=True,
                reference=f"wlt_{existing.id}",
                message="This order was already paid from the wallet — no second charge was made.",
                details={"duplicate": True},
            )

        # Lock the wallet row while deciding (a no-op on SQLite, a real row
        # lock on Postgres) so two different orders can't both pass the
        # balance check against the same money.
        db.execute(select(Wallet).where(Wallet.id == wallet.id).with_for_update())
        before = balance_paise(db, order.user_id)
        if before < order.amount_paise:
            return ProviderOutcome(
                committed=False,
                money_moved=False,
                error_code="insufficient_balance",
                message=(
                    f"Not enough wallet balance: ₹{before / 100:.2f} available, "
                    f"₹{order.amount_paise / 100:.2f} needed."
                ),
                details={"balance_paise": before},
            )

        entry = WalletEntry(
            wallet_id=wallet.id,
            amount_paise=-order.amount_paise,
            kind="debit",
            order_id=order.id,
            idempotency_key=key,
            note=f"Order #{order.id}",
        )
        db.add(entry)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            winner = db.scalar(select(WalletEntry).where(WalletEntry.idempotency_key == key))
            return ProviderOutcome(
                committed=True,
                money_moved=True,
                reference=f"wlt_{winner.id}" if winner else None,
                message="This order was already paid from the wallet — no second charge was made.",
                details={"duplicate": True},
            )
        db.refresh(entry)
        return ProviderOutcome(
            committed=True,
            money_moved=True,
            reference=f"wlt_{entry.id}",
            message=f"Paid ₹{order.amount_paise / 100:.2f} from your Gnani Shop Wallet.",
            details={"balance_before_paise": before, "balance_after_paise": before - order.amount_paise},
        )
