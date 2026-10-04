from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SellerOrder(SQLModel, table=True):
    __tablename__ = "seller_orders"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "seller_id",
            name="uq_seller_orders_order_seller",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    order_id: int = Field(
        foreign_key="orders.id",
        index=True,
    )

    seller_id: int = Field(
        foreign_key="users.id",
        index=True,
    )

    status: str = Field(max_length=30)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )

    completed_at: datetime | None = None
