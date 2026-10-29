from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Voucher(SQLModel, table=True):
    __tablename__ = "vouchers"
    __table_args__ = (UniqueConstraint("code", name="uq_vouchers_code"),)

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=32, index=True)
    scope: str = Field(default="PLATFORM", max_length=20)
    seller_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    discount_type: str = Field(max_length=20)
    discount_value: int = Field(default=0)
    max_discount: int | None = Field(default=None, nullable=True)
    min_order_value: int = Field(default=0)
    usage_limit: int | None = Field(default=None, nullable=True)
    per_user_limit: int | None = Field(default=None, nullable=True)
    used_count: int = Field(default=0)
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ends_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
