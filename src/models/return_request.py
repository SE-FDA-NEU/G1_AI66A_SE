from datetime import UTC, datetime

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class ReturnRequest(SQLModel, table=True):
    """Return and refund request submitted by a buyer for a delivered order."""

    __tablename__ = "return_requests"
    __table_args__ = (
        Index(
            "uq_return_requests_seller_order_pending",
            "seller_order_id",
            unique=True,
            sqlite_where=text("status = 'PENDING'"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    seller_order_id: int = Field(foreign_key="seller_orders.id", index=True)
    buyer_id: int = Field(foreign_key="users.id", index=True)
    reason: str = Field(max_length=500)
    evidence: str = Field(max_length=2000)
    status: str = Field(default="PENDING", max_length=30)  # PENDING, APPROVED, REJECTED
    decision_notes: str | None = Field(default=None, max_length=1000)
    decided_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    is_restockable: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
