"""Sellers list API endpoint for discovery filters."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.database import SessionDep
from src.errors import error_detail
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sellers", tags=["Sellers"])

SELLERS_ERROR_MESSAGE = "Unable to load sellers right now. Please try again later."


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
    except SQLAlchemyError as exc:
        logger.exception("Failed to query sellers")
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", SELLERS_ERROR_MESSAGE),
        ) from exc
