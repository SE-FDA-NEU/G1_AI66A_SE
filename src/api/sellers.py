"""Sellers list API endpoint for discovery filters."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.database import SessionDep
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sellers", tags=["Sellers"])


class SellerSummary(BaseModel):
    """Public seller representation for filter selection."""

    id: int
    name: str


@router.get("", response_model=list[SellerSummary])
def list_sellers(session: SessionDep) -> list[SellerSummary]:
    """Return all active sellers for product discovery filter controls."""
    try:
        sellers = session.exec(
            select(User).where(User.role == "seller").order_by(User.id)
        ).all()
        return [
            SellerSummary(id=seller.id, name=seller.name)  # type: ignore[arg-type]
            for seller in sellers
            if seller.id is not None
        ]
    except SQLAlchemyError:
        logger.exception("Failed to query sellers")
        return []
