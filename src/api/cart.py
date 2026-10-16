"""Buyer cart mutation endpoints used by the product detail flow."""

import logging
import time

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlmodel import select

from src.auth import BuyerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.cart_item import CartItem
from src.models.product import Product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cart", tags=["Cart"])

CART_ERROR_MESSAGE = "Unable to update cart right now. Please try again later."


class AddCartItemRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=20)
    quantity: StrictInt


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    product_code: str
    quantity: int


class CartItemResult(BaseModel):
    data: CartItemResponse


@router.post("/items", response_model=CartItemResult)
def add_cart_item(
    request: AddCartItemRequest,
    session: SessionDep,
    user: BuyerUser,
    response: Response,
) -> CartItemResult:
    """Add quantity to a buyer's cart line after validating current availability."""
    if request.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail=error_detail("ERR_INVALID_QUANTITY", "Quantity must be greater than zero."),
        )

    max_retries = 5
    for attempt in range(max_retries):
        try:
            product = session.exec(
                select(Product).where(
                    Product.code == request.product_code,
                    Product.is_active.is_(True),
                )
            ).first()
            if product is None:
                raise HTTPException(
                    status_code=404,
                    detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
                )

            available_stock = max(product.stock_quantity - product.reserved_stock, 0)
            if available_stock <= 0:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail(
                        "ERR_STOCK_EXCEEDED",
                        f"Only {available_stock} item(s) are currently available.",
                    ),
                )

            cart_item = session.exec(
                select(CartItem).where(
                    CartItem.buyer_id == user.id,
                    CartItem.product_id == product.id,
                )
            ).first()

            if cart_item is None:
                if request.quantity > available_stock:
                    raise HTTPException(
                        status_code=409,
                        detail=error_detail(
                            "ERR_STOCK_EXCEEDED",
                            f"Only {available_stock} item(s) are currently available.",
                        ),
                    )
                try:
                    new_item = CartItem(
                        buyer_id=user.id,
                        product_id=product.id,
                        quantity=request.quantity,
                    )
                    session.add(new_item)
                    session.commit()
                    session.refresh(new_item)
                    response.status_code = status.HTTP_201_CREATED
                    return CartItemResult(
                        data=CartItemResponse(
                            id=new_item.id,
                            product_id=product.id,
                            product_code=product.code,
                            quantity=new_item.quantity,
                        )
                    )
                except IntegrityError:
                    session.rollback()
                    # Another concurrent request inserted this line first; retry to update it
                    continue

            # Existing cart line
            requested_total = cart_item.quantity + request.quantity
            if requested_total > available_stock:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail(
                        "ERR_STOCK_EXCEEDED",
                        f"Only {available_stock} item(s) are currently available.",
                    ),
                )

            # Atomic increment in database guarded by current available stock limit
            stmt = (
                update(CartItem)
                .where(
                    CartItem.id == cart_item.id,
                    CartItem.quantity + request.quantity <= available_stock,
                )
                .values(quantity=CartItem.quantity + request.quantity)
            )
            result = session.execute(stmt)
            if result.rowcount == 0:
                # Stock limit was reached or line was concurrently modified
                session.rollback()
                continue

            session.commit()
            session.refresh(cart_item)
            response.status_code = status.HTTP_200_OK
            return CartItemResult(
                data=CartItemResponse(
                    id=cart_item.id,
                    product_id=product.id,
                    product_code=product.code,
                    quantity=cart_item.quantity,
                )
            )
        except HTTPException:
            session.rollback()
            raise
        except (IntegrityError, OperationalError) as exc:
            session.rollback()
            if attempt == max_retries - 1:
                logger.exception("Database concurrency conflict exhausted retries: %s", exc)
                raise HTTPException(
                    status_code=500,
                    detail=error_detail("ERR_DATABASE_FAILURE", CART_ERROR_MESSAGE),
                ) from exc
            time.sleep(0.01 * (attempt + 1))
            continue
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("Database error during cart item addition: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=error_detail("ERR_DATABASE_FAILURE", CART_ERROR_MESSAGE),
            ) from exc

    session.rollback()
    raise HTTPException(
        status_code=500,
        detail=error_detail("ERR_DATABASE_FAILURE", CART_ERROR_MESSAGE),
    )
