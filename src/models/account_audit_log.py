from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AccountAuditLog(SQLModel, table=True):
    __tablename__ = "account_audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    admin_id: int = Field(foreign_key="users.id")
    action: str = Field(default="STATUS_CHANGE", max_length=50)
    old_status: str = Field(max_length=20)
    new_status: str = Field(max_length=20)
    reason: str = Field(default="", max_length=500)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
