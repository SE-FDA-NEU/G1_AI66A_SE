from datetime import UTC, datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class Voucher(SQLModel, table=True):
    __tablename__ = "vouchers"

    __table_args__ = (
        CheckConstraint(
            "(scope = 'SHOP' AND seller_id IS NOT NULL) "
            "OR (scope = 'PLATFORM' AND seller_id IS NULL)",
            name="ck_vouchers_scope_seller",
        ),
        CheckConstraint(
            "discount_type IN ('FIXED_AMOUNT', 'PERCENTAGE', 'FREE_SHIPPING')",
            name="ck_vouchers_discount_type",
        ),
        CheckConstraint(
            "(discount_type != 'FREE_SHIPPING') OR (scope = 'PLATFORM')",
            name="ck_vouchers_free_shipping_platform",
        ),
        CheckConstraint(
            "starts_at < ends_at",
            name="ck_vouchers_dates",
        ),
        CheckConstraint(
            "used_count >= 0 AND (usage_limit IS NULL OR used_count <= usage_limit)",
            name="ck_vouchers_used_count",
        ),
        CheckConstraint(
            "min_order_value >= 0",
            name="ck_vouchers_min_order_value",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=32, unique=True, index=True)
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
