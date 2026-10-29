"""Append and retrieve audit rows without committing the surrounding transition."""

from sqlmodel import Session, select

from src.models.order_history import OrderHistory


def append_history(session: Session, event: OrderHistory) -> None:
    session.add(event)
    # Assign the ID now; notification event keys are derived from it.
    session.flush()


def list_history(session: Session, seller_order_ids: list[int]) -> list[OrderHistory]:
    if not seller_order_ids:
        return []
    return list(
        session.exec(
            select(OrderHistory)
            .where(OrderHistory.seller_order_id.in_(seller_order_ids))
            .order_by(OrderHistory.created_at, OrderHistory.id)
        ).all()
    )
