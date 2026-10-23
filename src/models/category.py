"""Category database model for product classification and hierarchy."""

from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(
        index=True,
        max_length=100,
    )

    slug: str = Field(
        index=True,
        unique=True,
        max_length=100,
    )

    parent_id: int | None = Field(
        default=None,
        foreign_key="categories.id",
        nullable=True,
        index=True,
    )
