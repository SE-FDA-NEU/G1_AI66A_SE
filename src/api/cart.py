"""Buyer cart mutation endpoints used by the product detail flow."""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from src.auth import BuyerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.cart_item import CartItem
from src.models.product import Product

router = APIRouter(prefix="/cart", tags=["Cart"])


class AddCartItemRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=20)
    quantity: int = Field(gt=0)


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
    cart_item = session.exec(
        select(CartItem).where(
            CartItem.buyer_id == user.id,
            CartItem.product_id == product.id,
        )
    ).first()
    requested_total = request.quantity + (cart_item.quantity if cart_item else 0)
    if available_stock == 0 or requested_total > available_stock:
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "ERR_STOCK_EXCEEDED",
                f"Only {available_stock} item(s) are currently available.",
            ),
        )

    created = cart_item is None
    if cart_item is None:
        cart_item = CartItem(
            buyer_id=user.id,
            product_id=product.id,
            quantity=request.quantity,
        )
        session.add(cart_item)
    else:
        cart_item.quantity = requested_total
    session.commit()
    session.refresh(cart_item)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return CartItemResult(
        data=CartItemResponse(
            id=cart_item.id,
            product_id=product.id,
            product_code=product.code,
            quantity=cart_item.quantity,
        )
    )
