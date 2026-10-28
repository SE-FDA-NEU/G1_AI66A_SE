"""Read-only audit entries exposed alongside authorized seller orders."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator


def order_timestamp_utc(value: datetime) -> datetime:
    """SQLite stores naive UTC; preserve the instant of timezone-aware values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class OrderHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_order_id: int
    from_status: str
    to_status: str
    changed_by_user_id: int
    actor_role: str | None
    note: str | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return order_timestamp_utc(value)
