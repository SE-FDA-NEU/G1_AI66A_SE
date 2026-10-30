from datetime import UTC, datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class PaymentEvent(SQLModel, table=True):
    """One recorded payment or refund result; the event key deduplicates retries."""

    __tablename__ = "payment_events"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_events_amount_non_negative"),
        CheckConstraint("kind IN ('PAYMENT_RESULT', 'REFUND')", name="ck_payment_events_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", ondelete="CASCADE", index=True)
    seller_order_id: int | None = Field(
        default=None, foreign_key="seller_orders.id", ondelete="CASCADE", index=True
    )
    event_key: str = Field(max_length=128, unique=True, index=True)
    kind: str = Field(max_length=20)
    source: str = Field(max_length=20)
    from_status: str = Field(max_length=30)
    to_status: str = Field(max_length=30)
    amount: int = Field(default=0, ge=0)
    actor_user_id: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
