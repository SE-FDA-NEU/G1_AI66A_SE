"""Pydantic schemas for the platform admin portal."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Category Schemas
# ---------------------------------------------------------------------------
class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None


class CategoryAdminResponse(BaseModel):
    id: int
    name: str
    slug: str
    parent_id: int | None = None
    product_count: int = 0


# ---------------------------------------------------------------------------
# User & Account Moderation Schemas
# ---------------------------------------------------------------------------
class UpdateUserStatusRequest(BaseModel):
    status: Literal["ACTIVE", "RESTRICTED", "SUSPENDED"]
    reason: str = Field(default="", max_length=500)


class AccountAuditLogResponse(BaseModel):
    id: int
    user_id: int
    admin_id: int
    admin_name: str | None = None
    action: str
    old_status: str
    new_status: str
    reason: str
    created_at: datetime


class UserAdminResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: datetime
    recent_audits: list[AccountAuditLogResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Platform Voucher Schemas
# ---------------------------------------------------------------------------
class CreateVoucherRequest(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    discount_type: Literal["FIXED_AMOUNT", "PERCENTAGE", "FREE_SHIPPING"]
    discount_value: int = Field(default=0, ge=0)
    max_discount: int | None = Field(default=None, ge=1)
    min_order_value: int = Field(default=0, ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int | None = Field(default=None, ge=1)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True


class UpdateVoucherRequest(BaseModel):
    is_active: bool | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int | None = Field(default=None, ge=1)
    ends_at: datetime | None = None


class VoucherAdminResponse(BaseModel):
    id: int
    code: str
    scope: str
    seller_id: int | None
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


# ---------------------------------------------------------------------------
# Catalog Moderation Schemas
# ---------------------------------------------------------------------------
class UpdateProductModerationRequest(BaseModel):
    is_active: bool
    moderation_notes: str | None = Field(default=None, max_length=500)


class ProductAdminResponse(BaseModel):
    id: int
    code: str
    seller_id: int
    seller_name: str | None = None
    name: str
    description: str
    price: int
    stock_quantity: int
    is_active: bool
    category_id: int | None = None
    category_name: str | None = None


# ---------------------------------------------------------------------------
# Dispute Adjudication Schemas
# ---------------------------------------------------------------------------
class DisputeDecisionRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    decision_notes: str = Field(default="", max_length=1000)
    is_restockable: bool = False


class ReturnDisputeResponse(BaseModel):
    id: int
    order_id: int
    seller_order_id: int
    buyer_id: int
    buyer_name: str | None = None
    seller_id: int
    seller_name: str | None = None
    reason: str
    evidence: str
    status: str
    decision_notes: str | None = None
    decided_by_user_id: int | None = None
    decided_by_name: str | None = None
    is_restockable: bool = False
    created_at: datetime
    decided_at: datetime | None = None
