from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity_positive",
        ),
        CheckConstraint(
            "unit_price > 0",
            name="ck_order_items_unit_price_positive",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    seller_order_id: int = Field(
        foreign_key="seller_orders.id",
        index=True,
    )

    product_id: int = Field(
        foreign_key="products.id",
        index=True,
    )

    variant_id: int | None = Field(default=None, foreign_key="product_variants.id", index=True)

    product_name_snapshot: str | None = Field(default=None, max_length=200)
    variant_name_snapshot: str | None = Field(default=None, max_length=100)
    product_image_snapshot: str | None = Field(default=None, max_length=2048)

    quantity: int = Field(gt=0)

    unit_price: int = Field(gt=0)
