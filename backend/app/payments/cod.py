"""Cash on Delivery: commits the buyer to the order without moving money.

Deliberately NOT available to agent autopay: an agent promising that a human
will hand over cash at the door is a commitment only that human can make.
"""

from sqlalchemy.orm import Session

from app.models.order import Order
from app.payments.provider import PaymentProvider, ProviderOutcome


class CashOnDeliveryProvider(PaymentProvider):
    name = "cod"
    display_name = "Cash on Delivery"
    agent_autopay_allowed = False

    def charge(self, db: Session, order: Order) -> ProviderOutcome:
        return ProviderOutcome(
            committed=True,
            money_moved=False,
            reference=f"cod_{order.id}",
            message=f"Order #{order.id} placed — pay ₹{order.amount_paise / 100:.2f} in cash on delivery.",
        )
