from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class OrderHistory(SQLModel, table=True):
    """Immutable audit record for a seller-order status transition."""

    __tablename__ = "order_history"

    id: int | None = Field(default=None, primary_key=True)
    seller_order_id: int = Field(foreign_key="seller_orders.id", index=True)
    from_status: str = Field(max_length=30)
    to_status: str = Field(max_length=30)
    changed_by_user_id: int = Field(foreign_key="users.id", index=True)
    # Legacy events have no reliable historical role; do not infer it from today's user.
    actor_role: str | None = Field(default=None, max_length=20)
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
