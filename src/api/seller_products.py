"""Seller product creation endpoint (US06). The owner is always the authenticated seller."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.schemas.seller_products import (
    ProductCreate,
    SellerInventoryListResponse,
    SellerInventoryProduct,
    SellerProduct,
    SellerProductResponse,
)
from src.services.seller_products import SellerProductError, create_product


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: int | None = None
    stock_quantity: int | None = None
    image_url: str | None = None
    is_active: bool | None = None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seller/products", tags=["Seller products"])
inventory_router = APIRouter(prefix="/seller/inventory", tags=["Seller inventory"])

# The validation handler in src/main.py answers this route with field-level errors.
SELLER_PRODUCTS_PATH = "/api/v1/seller/products"
CREATE_DATABASE_ERROR_MESSAGE = "Unable to create the product right now. Please try again later."


@inventory_router.get("", response_model=SellerInventoryListResponse)
def list_seller_inventory(
    seller: SellerUser,
    session: SessionDep,
) -> SellerInventoryListResponse:
    """List products owned by authenticated seller with moderation status."""
    results = session.exec(
        select(Product, ProductMetadata.is_moderated_deactivated)
        .outerjoin(ProductMetadata, ProductMetadata.product_id == Product.id)
        .where(Product.seller_id == seller.id)
        .order_by(Product.id.desc())
    ).all()
    items = []
    for prod, is_mod in results:
        items.append(
            SellerInventoryProduct(
                id=prod.id,
                code=prod.code,
                seller_id=prod.seller_id,
                name=prod.name,
                description=prod.description or "",
                price=prod.price,
                stock_quantity=prod.stock_quantity,
                reserved_stock=prod.reserved_stock,
                image_url=prod.image_url,
                is_active=prod.is_active,
                is_moderated_deactivated=bool(is_mod),
                version=prod.version,
            )
        )
    return SellerInventoryListResponse(data=items)


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


@router.patch("/{product_id}", response_model=SellerProductResponse)
@router.put("/{product_id}", response_model=SellerProductResponse)
def update_seller_product(
    product_id: int,
    body: ProductUpdate,
    seller: SellerUser,
    session: SessionDep,
) -> SellerProductResponse:
    """Update a seller-owned product listing; unauthorized owners are rejected."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
        )
    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("ERR_RESOURCE_OWNER", "You do not own this product."),
        )
    if body.name is not None:
        product.name = body.name
    if body.description is not None:
        product.description = body.description
    if body.price is not None:
        if body.price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("ERR_VALIDATION", "Price must be positive."),
            )
        product.price = body.price
    if body.stock_quantity is not None:
        if body.stock_quantity < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail("ERR_VALIDATION", "Stock quantity must be non-negative."),
            )
        product.stock_quantity = body.stock_quantity
    if body.image_url is not None:
        product.image_url = body.image_url
    meta = session.exec(
        select(ProductMetadata).where(ProductMetadata.product_id == product.id)
    ).first()
    is_moderated = meta.is_moderated_deactivated if meta else False
    if is_moderated:
        if body.is_active is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_detail(
                    "ERR_PRODUCT_MODERATED",
                    "This product was deactivated by administrator moderation "
                    "and cannot be reactivated by the seller.",
                ),
            )
        product.is_active = False
    elif body.is_active is not None:
        product.is_active = body.is_active
    product.version += 1
    session.add(product)
    session.commit()
    session.refresh(product)
    return SellerProductResponse(data=SellerProduct.model_validate(product, from_attributes=True))


@router.delete("/{product_id}", response_model=SellerProductResponse)
def deactivate_seller_product(
    product_id: int, seller: SellerUser, session: SessionDep
) -> SellerProductResponse:
    """Withdraw a listing without deleting the product row referenced by order history."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
        )
    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("ERR_RESOURCE_OWNER", "You do not own this product."),
        )
    product.is_active = False
    product.version += 1
    session.add(product)
    session.commit()
    session.refresh(product)
    return SellerProductResponse(data=SellerProduct.model_validate(product, from_attributes=True))
