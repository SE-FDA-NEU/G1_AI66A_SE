from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DiscountType = Literal["FIXED_AMOUNT", "PERCENTAGE", "FREE_SHIPPING"]


class SellerVoucherCreate(BaseModel):
    code: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    discount_type: DiscountType
    discount_value: int = Field(default=0, ge=0)
    max_discount: int | None = Field(default=None, ge=1)
    min_order_value: int = Field(default=0, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int | None = Field(default=None, ge=1)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True


class SellerVoucherUpdate(BaseModel):
    discount_type: DiscountType | None = None
    discount_value: int | None = Field(default=None, ge=0)
    max_discount: int | None = Field(default=None, ge=1)
    min_order_value: int | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class SellerVoucherResponse(BaseModel):
    id: int
    code: str
    scope: str
    seller_id: int
    discount_type: str
    discount_value: int
    max_discount: int | None
    min_order_value: int
    usage_limit: int | None
    per_user_limit: int | None
    used_count: int
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime
