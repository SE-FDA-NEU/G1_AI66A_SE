from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class VoucherUsage(SQLModel, table=True):
    __tablename__ = "voucher_usages"

    __table_args__ = (
        UniqueConstraint(
            "voucher_id",
            "order_id",
            name="uq_voucher_usages_voucher_order",
        ),
        CheckConstraint(
            "discount_amount >= 0",
            name="ck_voucher_usages_discount_amount_non_negative",
        ),
        CheckConstraint(
            "status IN ('APPLIED', 'RESTORED')",
            name="ck_voucher_usages_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    voucher_id: int = Field(foreign_key="vouchers.id", index=True)
    buyer_id: int = Field(foreign_key="users.id", index=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    seller_order_id: int | None = Field(
        default=None,
        foreign_key="seller_orders.id",
        nullable=True,
        index=True,
    )
    code: str = Field(max_length=32)
    discount_amount: int = Field(default=0, ge=0)
    status: str = Field(default="APPLIED", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    restored_at: datetime | None = Field(default=None, nullable=True)
