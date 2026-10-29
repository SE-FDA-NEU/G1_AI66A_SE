from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class Review(SQLModel, table=True):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        UniqueConstraint("order_item_id", name="uq_reviews_order_item"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_item_id: int = Field(foreign_key="order_items.id", ondelete="CASCADE", index=True)
    product_id: int = Field(foreign_key="products.id", ondelete="CASCADE", index=True)
    buyer_id: int = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    media_url: str | None = Field(default=None, max_length=2048)
    images_json: str = Field(default="[]")
    seller_reply: str | None = Field(default=None, max_length=2000)
    seller_replied_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
