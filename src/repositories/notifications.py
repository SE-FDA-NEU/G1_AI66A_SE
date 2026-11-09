"""Recipient-scoped unread queries; the calling service owns the transaction."""

from datetime import datetime

from sqlalchemy import func, update
from sqlmodel import Session, select

from src.models.notification import Notification


def count_unread(session: Session, recipient_user_id: int) -> int:
    return session.exec(select(func.count(Notification.id)).where(
        Notification.recipient_user_id == recipient_user_id,
        Notification.read_at.is_(None),
    )).one()


def mark_all_read(session: Session, recipient_user_id: int, read_at: datetime) -> None:
    session.execute(update(Notification).where(
        Notification.recipient_user_id == recipient_user_id,
        Notification.read_at.is_(None),
    ).values(read_at=read_at))
