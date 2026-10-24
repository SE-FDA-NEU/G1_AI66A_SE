"""Shopping cart endpoints (US03). Every request acts on the authenticated buyer's own cart."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from sqlalchemy.exc import SQLAlchemyError

from src.auth import BuyerUser
from src.database import SessionDep
from src.errors import error_detail
from src.schemas.cart import (
    PRODUCT_CODE_MAX_LENGTH,
    AddCartItemRequest,
    CartResponse,
    SelectCartRequest,
    UpdateCartItemRequest,
)
from src.services.cart import CartError, CartErrorCode, CartService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cart", tags=["Cart"])

CART_DATABASE_ERROR_MESSAGE = "Unable to update cart right now. Please try again later."

ERROR_STATUS: dict[CartErrorCode, int] = {
    CartErrorCode.INVALID_QUANTITY: status.HTTP_400_BAD_REQUEST,
    CartErrorCode.PRODUCT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    CartErrorCode.CART_ITEM_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    CartErrorCode.PRODUCT_UNAVAILABLE: status.HTTP_409_CONFLICT,
    CartErrorCode.STOCK_EXCEEDED: status.HTTP_409_CONFLICT,
    CartErrorCode.CONCURRENCY_CONFLICT: status.HTTP_409_CONFLICT,
}

ProductCodePath = Annotated[
    str, Path(alias="productCode", min_length=1, max_length=PRODUCT_CODE_MAX_LENGTH)
]


@contextmanager
def cart_errors_as_http() -> Iterator[None]:
    """Turn service errors into the common `{error: {code, message}}` response."""
    try:
        yield
    except CartError as error:
        raise HTTPException(
            status_code=ERROR_STATUS[error.code],
            detail=error_detail(error.code, error.message),
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Cart database operation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail("ERR_DATABASE_FAILURE", CART_DATABASE_ERROR_MESSAGE),
        ) from error


@router.get("", response_model=CartResponse)
def get_cart(buyer: BuyerUser, session: SessionDep) -> CartResponse:
    """Return the buyer's cart; a buyer without lines gets an empty cart, not 404."""
    with cart_errors_as_http():
        cart = CartService(session).get_cart(buyer.id)
    return CartResponse(data=cart)


@router.post(
    "/items",
    response_model=CartResponse,
    responses={status.HTTP_201_CREATED: {"model": CartResponse, "description": "New line"}},
)
def add_cart_item(
    request: AddCartItemRequest, buyer: BuyerUser, session: SessionDep, response: Response
) -> CartResponse:
    """Add a product, or increase its existing line: 201 for a new line, 200 otherwise."""
    with cart_errors_as_http():
        result = CartService(session).add_item(buyer.id, request.product_code, request.quantity)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return CartResponse(data=result.cart)


@router.patch("/items/{productCode}", response_model=CartResponse)
def update_cart_item(
    product_code: ProductCodePath,
    request: UpdateCartItemRequest,
    buyer: BuyerUser,
    session: SessionDep,
) -> CartResponse:
    """Replace the quantity of one line."""
    with cart_errors_as_http():
        cart = CartService(session).update_item(buyer.id, product_code, request.quantity)
    return CartResponse(data=cart)


@router.delete("/items/{productCode}", response_model=CartResponse)
def remove_cart_item(
    product_code: ProductCodePath, buyer: BuyerUser, session: SessionDep
) -> CartResponse:
    """Remove one line and return the remaining cart."""
    with cart_errors_as_http():
        cart = CartService(session).remove_item(buyer.id, product_code)
    return CartResponse(data=cart)


@router.patch("/items/{item_id}/select", response_model=CartResponse)
def select_cart_item(
    item_id: Annotated[int, Path(gt=0)],
    request: SelectCartRequest,
    buyer: BuyerUser,
    session: SessionDep,
) -> CartResponse:
    with cart_errors_as_http():
        cart = CartService(session).select_item(buyer.id, item_id, request.is_selected)
    return CartResponse(data=cart)


@router.patch("/select-shop/{seller_id}", response_model=CartResponse)
def select_cart_shop(
    seller_id: Annotated[int, Path(gt=0)],
    request: SelectCartRequest,
    buyer: BuyerUser,
    session: SessionDep,
) -> CartResponse:
    with cart_errors_as_http():
        cart = CartService(session).select_shop(buyer.id, seller_id, request.is_selected)
    return CartResponse(data=cart)
