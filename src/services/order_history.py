"""Audit snapshots for existing transitions; no HTTP or transaction ownership."""

from collections import defaultdict
from datetime import UTC, datetime

from sqlmodel import Session

from src.models.order_history import OrderHistory
from src.models.user import User
from src.repositories.order_history import append_history, list_history
from src.schemas.order_history import OrderHistoryEntry, order_timestamp_utc


def record_transition(
    session: Session,
    *,
    seller_order_id: int,
    from_status: str,
    to_status: str,
    actor: User,
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> OrderHistory:
    """Snapshot the authenticated actor's role when the transition happens."""
    event = OrderHistory(
        seller_order_id=seller_order_id,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=actor.id,
        actor_role=actor.role,
        note=note,
        created_at=(
            order_timestamp_utc(occurred_at) if occurred_at is not None else datetime.now(UTC)
        ),
    )
    append_history(session, event)
    return event


def history_by_seller_order(
    session: Session,
    seller_order_ids: list[int],
) -> dict[int, list[OrderHistoryEntry]]:
    """Read only the order IDs already authorized by the owning use case."""
    grouped: dict[int, list[OrderHistoryEntry]] = defaultdict(list)
    for event in list_history(session, seller_order_ids):
        grouped[event.seller_order_id].append(OrderHistoryEntry.model_validate(event))
    return dict(grouped)
