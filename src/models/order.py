from datetime import UTC, datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "total_amount >= 0",
            name="ck_orders_total_nonnegative",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    buyer_id: int = Field(
        foreign_key="users.id",
        index=True,
    )

    request_key: str | None = Field(default=None, max_length=64, unique=True, index=True)

    request_hash: str | None = Field(default=None, max_length=64)

    total_amount: int = Field(ge=0)

    status: str = Field(max_length=30)

    recipient_name: str = Field(max_length=100)

    delivery_address: str

    phone_number: str = Field(max_length=20)

    tracking_number: str | None = Field(default=None, max_length=100)

    shipped_at: datetime | None = None

    delivered_at: datetime | None = None

    completed_at: datetime | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
