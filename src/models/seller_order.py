from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class SellerOrder(SQLModel, table=True):
    __tablename__ = "seller_orders"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "seller_id",
            name="uq_seller_orders_order_seller",
        ),
        CheckConstraint("subtotal >= 0", name="ck_seller_orders_subtotal_non_negative"),
        CheckConstraint("shop_discount >= 0", name="ck_seller_orders_shop_discount_non_negative"),
        CheckConstraint(
            "platform_discount >= 0",
            name="ck_seller_orders_platform_discount_non_negative",
        ),
        CheckConstraint(
            "shipping_fee >= 0",
            name="ck_seller_orders_shipping_fee_non_negative",
        ),
        CheckConstraint(
            "shipping_discount >= 0",
            name="ck_seller_orders_shipping_discount_non_negative",
        ),
        CheckConstraint("total_amount >= 0", name="ck_seller_orders_total_amount_non_negative"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= total_amount",
            name="ck_seller_orders_refunded_amount_range",
        ),
        CheckConstraint(
            "commission_amount >= 0 AND seller_net_amount >= 0",
            name="ck_seller_orders_settlement_non_negative",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    order_id: int = Field(
        foreign_key="orders.id",
        index=True,
    )

    seller_id: int = Field(
        foreign_key="users.id",
        index=True,
    )

    status: str = Field(max_length=30)

    payment_status: str = Field(default="UNPAID", max_length=30)

    escrow_status: str = Field(default="HELD", max_length=30)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )

    tracking_number: str | None = Field(default=None, max_length=100)

    shipped_at: datetime | None = None

    delivered_at: datetime | None = None

    completed_at: datetime | None = None

    subtotal: int = Field(default=0, ge=0)
    shop_discount: int = Field(default=0, ge=0)
    platform_discount: int = Field(default=0, ge=0)
    shipping_fee: int = Field(default=0, ge=0)
    shipping_discount: int = Field(default=0, ge=0)
    total_amount: int = Field(default=0, ge=0)
    pricing_policy_version: str = Field(default="LEGACY", max_length=20)
    # US20 settlement snapshot (#148); see docs/us20-payments.md sections 4 and 5.
    refunded_amount: int = Field(default=0, ge=0)
    commission_rate_bps: int = Field(default=0, ge=0)
    commission_amount: int = Field(default=0, ge=0)
    seller_net_amount: int = Field(default=0, ge=0)
    settled_at: datetime | None = None
