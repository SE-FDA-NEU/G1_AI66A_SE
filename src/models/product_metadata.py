"""Product metadata SQLModel for catalog discovery, categorization, ratings and sorting."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ProductMetadata(SQLModel, table=True):
    __tablename__ = "product_metadata"

    product_id: int = Field(
        primary_key=True,
    )

    category_id: int | None = Field(
        default=None,
        nullable=True,
        index=True,
    )

    rating: float = Field(default=0.0)

    sales_count: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
