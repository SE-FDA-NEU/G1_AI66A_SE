from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: int | None = Field(default=None, primary_key=True)
    recipient_user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    order_id: int = Field(foreign_key="orders.id", ondelete="CASCADE", index=True)
    event_key: str = Field(max_length=200, unique=True, index=True)
    message: str = Field(max_length=255)
    target_path: str = Field(default="/notifications", max_length=512)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None
