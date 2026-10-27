"""Buyer-owned delivery addresses; orders keep independent snapshots."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class UserAddress(SQLModel, table=True):
    __tablename__ = "user_addresses"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_address_version"),
        Index(
            "ux_user_addresses_one_default",
            "user_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default"),
        ),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    recipient_name: str = Field(max_length=100)
    phone_number: str = Field(max_length=20)
    province: str = Field(max_length=100)
    district: str = Field(max_length=100)
    ward: str = Field(max_length=100)
    detailed_address: str = Field(max_length=500)
    is_default: bool = False
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
