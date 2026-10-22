"""Category and discovery metadata API endpoints."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.database import SessionDep
from src.models.category import Category
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/categories", tags=["Categories"])


class CategoryResponse(BaseModel):
    """Public category representation."""

    id: int
    name: str
    slug: str
    parent_id: int | None = None


class SellerSummaryResponse(BaseModel):
    """Public seller representation for filter selection."""

    id: int
    name: str


@router.get("", response_model=list[CategoryResponse])
def list_categories(session: SessionDep) -> list[CategoryResponse]:
    """Return all categories for navigation and filter controls."""
    try:
        categories = session.exec(select(Category).order_by(Category.id)).all()
        return [
            CategoryResponse(
                id=cat.id,  # type: ignore[arg-type]
                name=cat.name,
                slug=cat.slug,
                parent_id=cat.parent_id,
            )
            for cat in categories
            if cat.id is not None
        ]
    except SQLAlchemyError:
        logger.exception("Failed to query categories")
        return []
