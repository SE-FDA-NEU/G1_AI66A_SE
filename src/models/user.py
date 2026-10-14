from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    email: str = Field(max_length=255, unique=True, index=True)
    password_hash: str = Field(default="", max_length=255)
    role: str = Field(max_length=20)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
