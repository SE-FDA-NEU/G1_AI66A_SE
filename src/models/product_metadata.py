"""Product metadata SQLModel for catalog discovery, categorization, ratings and sorting."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ProductMetadata(SQLModel, table=True):
    __tablename__ = "product_metadata"

    product_id: int = Field(
        primary_key=True,
        foreign_key="products.id",
        ondelete="CASCADE",
    )

    category_id: int | None = Field(
        default=None,
        foreign_key="categories.id",
        nullable=True,
        index=True,
    )

    rating: float = Field(default=0.0)

    review_count: int = Field(default=0, ge=0)

    sales_count: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
