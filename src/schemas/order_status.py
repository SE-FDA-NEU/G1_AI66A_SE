"""Shared input contract for the two existing status-update routes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal[
        "PENDING",
        "CONFIRMED",
        "PROCESSING",
        "CANCELLATION_REQUESTED",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        "CANCELLED",
    ]
    tracking_number: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=1000)
