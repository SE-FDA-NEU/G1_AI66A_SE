"""Allowed order-state transitions shared by buyer and seller order APIs."""

from typing import Literal

ActorRole = Literal["buyer", "seller"]

ORDER_STATUSES = frozenset(
    {
        "PENDING",
        "CONFIRMED",
        "PROCESSING",
        "CANCELLATION_REQUESTED",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        "CANCELLED",
    }
)

SELLER_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"CONFIRMED", "PROCESSING", "CANCELLED"}),
    "CONFIRMED": frozenset(
        {"PROCESSING", "SHIPPED", "CANCELLED"}
    ),
    "PROCESSING": frozenset(
        {"CONFIRMED", "SHIPPED", "CANCELLED"}
    ),
    "CANCELLATION_REQUESTED": frozenset({"CANCELLED", "CONFIRMED", "PROCESSING"}),
    "SHIPPED": frozenset({"DELIVERED", "COMPLETED"}),
    "DELIVERED": frozenset({"COMPLETED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}

BUYER_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"CANCELLED"}),
    "CONFIRMED": frozenset({"CANCELLATION_REQUESTED"}),
    "PROCESSING": frozenset({"CANCELLATION_REQUESTED"}),
    "SHIPPED": frozenset({"COMPLETED"}),
    "DELIVERED": frozenset({"COMPLETED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}

TRANSITIONS_BY_ROLE: dict[ActorRole, dict[str, frozenset[str]]] = {
    "buyer": BUYER_TRANSITIONS,
    "seller": SELLER_TRANSITIONS,
}


def is_allowed_transition(actor_role: ActorRole, current: str, target: str) -> bool:
    """Return whether an actor may move an order from current to target state."""
    return target in TRANSITIONS_BY_ROLE[actor_role].get(current, frozenset())
