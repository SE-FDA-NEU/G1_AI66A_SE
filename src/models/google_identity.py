from sqlmodel import Field, SQLModel


class GoogleIdentity(SQLModel, table=True):
    """Stable provider identity, separate from a user's mutable email address."""

    __tablename__ = "google_identities"

    subject: str = Field(primary_key=True, max_length=255)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
