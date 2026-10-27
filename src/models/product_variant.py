from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class ProductVariant(SQLModel, table=True):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("seller_id", "sku", name="uq_product_variants_seller_sku"),
        CheckConstraint("price > 0", name="ck_product_variants_price_positive"),
        CheckConstraint("stock_quantity >= 0", name="ck_product_variants_stock_nonnegative"),
        CheckConstraint("reserved_stock >= 0", name="ck_product_variants_reserved_nonnegative"),
        CheckConstraint(
            "reserved_stock <= stock_quantity", name="ck_product_variants_reserved_lte_stock"
        ),
        CheckConstraint("version >= 1", name="ck_product_variants_version_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    seller_id: int = Field(foreign_key="users.id", index=True)
    sku: str = Field(max_length=64)
    name: str = Field(max_length=100)
    price: int = Field(gt=0)
    stock_quantity: int = Field(default=0, ge=0)
    reserved_stock: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=2048)
    is_active: bool = True
    version: int = Field(default=1, ge=1)
