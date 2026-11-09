"""The payment provider slot.

Every way of paying implements one small interface. Nothing outside
app/payments/ knows which providers exist — the order service, the agent and
the routers all go through `app.payments.service.pay_order`, which looks the
provider up by name here. Adding a real gateway later means adding one class
and one registry line; no agent, policy or order code changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.order import Order


@dataclass
class ProviderOutcome:
    """What a provider reports back. `committed` = the buyer is now bound to
    this order (money moved, or a COD promise was made). `money_moved` is
    separate on purpose: Cash on Delivery commits without moving money."""

    committed: bool
    money_moved: bool
    reference: str | None = None
    error_code: str | None = None
    message: str = ""
    details: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    #: stable machine name, stored on Order.payment_method
    name: str
    #: shown to buyers
    display_name: str
    #: may an agent with autopay (Mode B) use this method on its own?
    agent_autopay_allowed: bool = False

    @abstractmethod
    def charge(self, db: Session, order: Order) -> ProviderOutcome:
        """Attempt to settle `order`. Must be idempotent per order."""
