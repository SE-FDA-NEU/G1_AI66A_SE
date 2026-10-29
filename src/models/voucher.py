from datetime import UTC, datetime

from pydantic import field_validator
from sqlalchemy import CheckConstraint, event
from sqlalchemy.orm import validates
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Voucher(SQLModel, table=True):
    __tablename__ = "vouchers"
    __table_args__ = (UniqueConstraint("code", name="uq_vouchers_code"),)

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
            "(discount_type = 'FIXED_AMOUNT' AND discount_value > 0) "
            "OR (discount_type = 'PERCENTAGE' AND discount_value >= 1 AND discount_value <= 10000) "
            "OR (discount_type = 'FREE_SHIPPING' AND discount_value = 0)",
            name="ck_vouchers_discount_value_bounds",
        ),
        CheckConstraint(
            "(max_discount IS NULL OR max_discount > 0) "
            "AND ((discount_type IN ('PERCENTAGE', 'FREE_SHIPPING')) OR max_discount IS NULL)",
            name="ck_vouchers_max_discount",
        ),
        CheckConstraint(
            "(usage_limit IS NULL OR usage_limit > 0) "
            "AND (per_user_limit IS NULL OR per_user_limit > 0)",
            name="ck_vouchers_limits",
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

    def __init__(self, **data):
        for field in ("starts_at", "ends_at"):
            val = data.get(field)
            if isinstance(val, str):
                try:
                    val = datetime.fromisoformat(val)
                except ValueError:
                    pass
            if isinstance(val, datetime):
                if val.tzinfo is None:
                    val = val.replace(tzinfo=UTC)
                else:
                    val = val.astimezone(UTC)
                data[field] = val
        super().__init__(**data)

    @validates("starts_at", "ends_at")
    def _validate_voucher_dates(self, key, value):
        if value is None:
            return value
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return value

    @field_validator("starts_at", "ends_at", mode="after")
    @classmethod
    def _normalize_utc(cls, v: datetime) -> datetime:
        if v is None:
            return v
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


@event.listens_for(Voucher, "before_insert")
@event.listens_for(Voucher, "before_update")
def _ensure_voucher_utc(mapper, connection, target):
    for attr in ("starts_at", "ends_at"):
        val = getattr(target, attr, None)
        if isinstance(val, datetime):
            if val.tzinfo is None:
                setattr(target, attr, val.replace(tzinfo=UTC))
            else:
                setattr(target, attr, val.astimezone(UTC))



