from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"

    __table_args__ = (
        Index(
            "uq_cart_items_buyer_product_base",
            "buyer_id",
            "product_id",
            unique=True,
            sqlite_where=text("variant_id IS NULL"),
            postgresql_where=text("variant_id IS NULL"),
        ),
        Index(
            "uq_cart_items_buyer_product_variant",
            "buyer_id",
            "product_id",
            "variant_id",
            unique=True,
            sqlite_where=text("variant_id IS NOT NULL"),
            postgresql_where=text("variant_id IS NOT NULL"),
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

    variant_id: int | None = Field(default=None, foreign_key="product_variants.id", index=True)

    quantity: int = Field(gt=0)

    is_selected: bool = Field(default=True)
    # Nullable only for legacy/imported rows; migration/read initializes their baseline.
    price_at_add: int | None = Field(default=None, gt=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
