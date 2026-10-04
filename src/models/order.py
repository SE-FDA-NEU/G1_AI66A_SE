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

    total_amount: int = Field(ge=0)

    status: str = Field(max_length=30)

    recipient_name: str = Field(max_length=100)

    delivery_address: str

    phone_number: str = Field(max_length=20)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )