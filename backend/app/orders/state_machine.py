"""The order state machine. Pure — no DB, no I/O — so every transition rule
is testable without a running server.

PENDING               → order row exists, nothing else has happened yet
AWAITING_PAYMENT      → order is ready; waiting for the buyer to pick Wallet
                        or Cash on Delivery and tap Pay (Mode A), or for an
                        agent's autopay to run (Mode B)
PAID                  → wallet debited (or cash collected on delivery); terminal
CONFIRMED_COD         → buyer chose Cash on Delivery: the order is placed,
                        but no money has moved yet. Becomes PAID when the
                        merchant records the cash as collected.
FAILED                → the payment attempt failed (e.g. not enough wallet
                        balance). NOT terminal — the buyer can retry with the
                        same or another method, against the same order.
CANCELLED             → abandoned before payment; terminal
"""

from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAID = "PAID"
    CONFIRMED_COD = "CONFIRMED_COD"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InvalidTransitionError(Exception):
    def __init__(self, current: "OrderStatus", target: "OrderStatus"):
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition order from {current.value} to {target.value}")


ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.AWAITING_PAYMENT, OrderStatus.FAILED, OrderStatus.CANCELLED}),
    OrderStatus.AWAITING_PAYMENT: frozenset(
        {OrderStatus.PAID, OrderStatus.CONFIRMED_COD, OrderStatus.FAILED, OrderStatus.CANCELLED}
    ),
    # A failed attempt can be retried directly — same order, same or a
    # different payment method — or abandoned.
    OrderStatus.FAILED: frozenset(
        {OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID, OrderStatus.CONFIRMED_COD, OrderStatus.CANCELLED}
    ),
    # Cash on Delivery: the merchant records the cash as collected (→ PAID),
    # or the order is cancelled before delivery.
    OrderStatus.CONFIRMED_COD: frozenset({OrderStatus.PAID, OrderStatus.CANCELLED}),
    OrderStatus.PAID: frozenset(),  # terminal: a paid order can never be downgraded
    OrderStatus.CANCELLED: frozenset(),  # terminal
}

# Statuses where the buyer has committed to this exact cart — a second
# payment for the same cart must be refused (DuplicatePaymentRule).
COMMITTED_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.PAID, OrderStatus.CONFIRMED_COD})


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def require_transition(current: OrderStatus, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
