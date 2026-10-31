from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ReturnDispute(SQLModel, table=True):
    __tablename__ = "return_disputes"
    __table_args__ = (
        UniqueConstraint("seller_order_id", name="uq_return_disputes_seller_order_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    seller_order_id: int = Field(foreign_key="seller_orders.id", index=True)
    return_request_id: int | None = Field(
        default=None, foreign_key="return_requests.id", nullable=True
    )
    buyer_id: int = Field(foreign_key="users.id")
    seller_id: int = Field(foreign_key="users.id")
    reason: str = Field(max_length=500)
    evidence: str = Field(default="", max_length=1000)
    status: str = Field(default="PENDING", max_length=20)
    decision_notes: str | None = Field(default=None, max_length=1000)
    decided_by_user_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    is_restockable: bool = Field(default=False)
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = Field(default=None, nullable=True)
