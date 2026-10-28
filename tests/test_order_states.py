import pytest

from src.services.order_states import is_allowed_transition


@pytest.mark.parametrize(
    ("actor", "current", "target"),
    [
        ("seller", "PENDING", "CONFIRMED"),
        ("seller", "CONFIRMED", "SHIPPED"),
        ("seller", "CANCELLATION_REQUESTED", "CANCELLED"),
        ("buyer", "PENDING", "CANCELLED"),
        ("buyer", "CONFIRMED", "CANCELLATION_REQUESTED"),
        ("buyer", "DELIVERED", "COMPLETED"),
    ],
)
def test_allowed_order_transitions(actor, current, target):
    assert is_allowed_transition(actor, current, target)


@pytest.mark.parametrize(
    ("actor", "current", "target"),
    [
        ("seller", "PENDING", "COMPLETED"),
        ("seller", "SHIPPED", "PENDING"),
        ("seller", "CONFIRMED", "CANCELLATION_REQUESTED"),
        ("buyer", "PENDING", "CANCELLATION_REQUESTED"),
        ("buyer", "CONFIRMED", "CANCELLED"),
        ("buyer", "DELIVERED", "CANCELLED"),
    ],
)
def test_disallowed_order_transitions(actor, current, target):
    assert not is_allowed_transition(actor, current, target)
