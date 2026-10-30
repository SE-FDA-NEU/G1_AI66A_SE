"""Product metadata SQLModel for catalog discovery, categorization, ratings and sorting."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class ProductMetadata(SQLModel, table=True):
    __tablename__ = "product_metadata"
    __table_args__ = (
        CheckConstraint(
            "rating >= 0 AND rating <= 5",
            name="ck_product_metadata_rating_range",
        ),
        CheckConstraint(
            "review_count >= 0",
            name="ck_product_metadata_review_count_nonnegative",
        ),
        CheckConstraint(
            "sales_count >= 0",
            name="ck_product_metadata_sales_count_nonnegative",
        ),
    )

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

    rating: float = Field(default=0.0, ge=0, le=5)

    review_count: int = Field(default=0, ge=0)

    sales_count: int = Field(default=0, ge=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    is_moderated_deactivated: bool = Field(default=False)
