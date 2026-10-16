"""Seller product creation endpoint (US06). The owner is always the authenticated seller."""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.schemas.seller_products import ProductCreate, SellerProductResponse
from src.services.seller_products import SellerProductError, create_product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seller/products", tags=["Seller products"])

# The validation handler in src/main.py answers this route with field-level errors.
SELLER_PRODUCTS_PATH = "/api/v1/seller/products"
CREATE_DATABASE_ERROR_MESSAGE = "Unable to create the product right now. Please try again later."


@router.post(
    "",
    response_model=SellerProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing, invalid or expired token"},
        status.HTTP_403_FORBIDDEN: {"description": "ERR_SELLER_REQUIRED"},
        status.HTTP_409_CONFLICT: {"description": "ERR_CONCURRENCY_CONFLICT"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "ERR_VALIDATION with messages grouped in error.fields"
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "ERR_DATABASE_FAILURE"},
    },
)
def create_seller_product(
    body: ProductCreate, seller: SellerUser, session: SessionDep
) -> SellerProductResponse:
    """Create an active listing; a stock of 0 is valid and shown as out of stock."""
    try:
        product = create_product(session, seller.id, body)
    except SellerProductError as error:
        raise HTTPException(
            status_code=error.status, detail=error_detail(error.code, error.message)
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Seller product creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail("ERR_DATABASE_FAILURE", CREATE_DATABASE_ERROR_MESSAGE),
        ) from error
    return SellerProductResponse(data=product)
