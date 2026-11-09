import pytest

from app.orders.state_machine import InvalidTransitionError, OrderStatus, can_transition, require_transition

ALLOWED = [
    (OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT),
    (OrderStatus.PENDING, OrderStatus.FAILED),
    (OrderStatus.PENDING, OrderStatus.CANCELLED),
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID),
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.CONFIRMED_COD),
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.FAILED),
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED),
    (OrderStatus.FAILED, OrderStatus.AWAITING_PAYMENT),  # retry
    (OrderStatus.FAILED, OrderStatus.PAID),  # retry straight from the wallet
    (OrderStatus.FAILED, OrderStatus.CONFIRMED_COD),  # retry as Cash on Delivery
    (OrderStatus.FAILED, OrderStatus.CANCELLED),
    (OrderStatus.CONFIRMED_COD, OrderStatus.PAID),  # cash collected on delivery
    (OrderStatus.CONFIRMED_COD, OrderStatus.CANCELLED),
]

FORBIDDEN = [
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.PENDING),  # no going backwards
    (OrderStatus.PAID, OrderStatus.FAILED),  # a paid order is never downgraded
    (OrderStatus.PAID, OrderStatus.AWAITING_PAYMENT),
    (OrderStatus.PAID, OrderStatus.CONFIRMED_COD),
    (OrderStatus.CONFIRMED_COD, OrderStatus.FAILED),  # a COD commitment does not "fail"
    (OrderStatus.CANCELLED, OrderStatus.AWAITING_PAYMENT),  # cancelled is terminal
    (OrderStatus.PENDING, OrderStatus.PAID),  # must pass through AWAITING_PAYMENT first
]


@pytest.mark.parametrize("current,target", ALLOWED)
def test_allowed_transitions(current, target):
    assert can_transition(current, target)
    require_transition(current, target)


@pytest.mark.parametrize("current,target", FORBIDDEN)
def test_forbidden_transitions(current, target):
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError):
        require_transition(current, target)
