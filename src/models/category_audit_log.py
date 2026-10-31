"""Retain category change facts even after the legacy admin DELETE removes its row."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class CategoryAuditLog(SQLModel, table=True):
    __tablename__ = "category_audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    # Deliberately not a category FK: legacy deletion must not erase audit history.
    category_id: int = Field(index=True)
    admin_id: int = Field(foreign_key="users.id", index=True)
    action: str = Field(max_length=20)
    before_json: str | None = None
    after_json: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
