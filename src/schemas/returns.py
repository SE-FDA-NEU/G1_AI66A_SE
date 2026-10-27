from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateReturnRequest(BaseModel):
    """Payload for submitting a return/refund request."""

    model_config = ConfigDict(extra="forbid")

    seller_order_id: int | None = Field(
        default=None,
        description="Target sub-order ID (optional if order has only one seller)",
    )
    reason: str = Field(
        min_length=3,
        max_length=500,
        description="Reason for return/refund",
    )
    evidence: str = Field(
        min_length=3,
        max_length=2000,
        description="Supporting evidence, photos, or description of issue",
    )


class ReturnDecisionRequest(BaseModel):
    """Payload for approving or rejecting a return request."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["APPROVE", "REJECT"] = Field(description="Decision: APPROVE or REJECT")
    decision_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional reviewer notes or feedback",
    )
    is_restockable: bool = Field(
        default=False,
        description="Whether returned item is confirmed restockable into inventory",
    )


class ReturnRequestData(BaseModel):
    id: int
    order_id: int
    seller_order_id: int
    buyer_id: int
    reason: str
    evidence: str
    status: str
    decision_notes: str | None = None
    decided_by_user_id: int | None = None
    is_restockable: bool = False
    created_at: datetime
    decided_at: datetime | None = None
    escrow_status: str
    payment_status: str
    seller_order_status: str


class ReturnRequestResponse(BaseModel):
    data: ReturnRequestData


class ReturnRequestListResponse(BaseModel):
    data: list[ReturnRequestData]
