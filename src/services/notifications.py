from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from src.models.notification import Notification


def create_notification(
    session: Session,
    recipient_user_id: int,
    order_id: int,
    event_key: str,
    message: str,
    target_path: str,
) -> None:
    session.exec(
        insert(Notification)
        .values(
            recipient_user_id=recipient_user_id,
            order_id=order_id,
            event_key=event_key,
            message=message,
            target_path=target_path,
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
    )


def list_notifications(session: Session, recipient_user_id: int) -> tuple[list[Notification], int]:
    notifications = session.exec(
        select(Notification)
        .where(Notification.recipient_user_id == recipient_user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
    ).all()
    unread_count = session.exec(
        select(func.count(Notification.id))
        .where(
            Notification.recipient_user_id == recipient_user_id,
            Notification.read_at.is_(None),
        )
    ).one()
    return notifications, unread_count


def mark_notification_read(
    session: Session, recipient_user_id: int, notification_id: int
) -> Notification | None:
    notification = session.exec(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == recipient_user_id,
        )
    ).first()
    if notification is not None and notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.add(notification)
        session.commit()
        session.refresh(notification)
    return notification
