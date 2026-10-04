from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    __tablename__ = "products"

    __table_args__ = (
        CheckConstraint(
            "price > 0",
            name="ck_products_price_positive",
        ),
        CheckConstraint(
            "stock_quantity >= 0",
            name="ck_products_stock_nonnegative",
        ),
        CheckConstraint(
            "reserved_stock >= 0",
            name="ck_products_reserved_nonnegative",
        ),
        CheckConstraint(
            "reserved_stock <= stock_quantity",
            name="ck_products_reserved_lte_stock",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_products_version_positive",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    code: str = Field(
        index=True,
        unique=True,
        max_length=20,
    )

    seller_id: int = Field(
        foreign_key="users.id",
        index=True,
    )

    name: str = Field(
        index=True,
        min_length=1,
        max_length=200,
    )

    description: str = ""

    price: int = Field(gt=0)

    stock_quantity: int = Field(default=0, ge=0)

    reserved_stock: int = Field(default=0, ge=0)

    image_url: str | None = None

    is_active: bool = True

    version: int = Field(default=1, ge=1)
