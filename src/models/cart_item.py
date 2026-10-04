from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"

    __table_args__ = (
        UniqueConstraint(
            "buyer_id",
            "product_id",
            name="uq_cart_items_buyer_product",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_cart_items_quantity_positive",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    buyer_id: int = Field(
        foreign_key="users.id",
        index=True,
    )

    product_id: int = Field(
        foreign_key="products.id",
        index=True,
    )

    quantity: int = Field(gt=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
