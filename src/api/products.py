"""Product catalog endpoint backed by the real database."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.database import SessionDep
from src.models.product import Product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["Products"])

CATALOG_ERROR_MESSAGE = "Unable to load products right now. Please try again later."


class ProductMeta(BaseModel):
    """Pagination metadata conforming to US01 specification."""

    current_page: int = Field(ge=1, description="Current page number")
    limit: int = Field(ge=1, le=100, description="Items per page")
    total: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")


class ProductListResponse(BaseModel):
    """Product list payload structure."""

    data: list["ProductResponse"] = Field(default_factory=list, description="List of products")
    meta: ProductMeta


class ProductResponse(BaseModel):
    """Public product representation."""

    id: str
    code: str
    name: str
    description: str | None
    price: float
    thumbnail_url: str | None
    image_url: str | None
    stock_quantity: int
    stock_status: str = ""


@router.get("", response_model=ProductListResponse)
def list_products(
    session: SessionDep,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
) -> ProductListResponse:
    """Return active products from the database with stable pagination."""
    # A failed query must surface as an error, never as an empty catalog.
    try:
        total = session.exec(
            select(func.count()).select_from(Product).where(Product.is_active.is_(True))
        ).one()
        products = session.exec(
            select(Product)
            .where(Product.is_active.is_(True))
            .order_by(Product.id)
            .offset((page - 1) * limit)
            .limit(limit)
        ).all()
    except SQLAlchemyError as exc:
        logger.exception("Product catalog query failed")
        raise HTTPException(status_code=500, detail=CATALOG_ERROR_MESSAGE) from exc
    return ProductListResponse(
        data=[
            ProductResponse(
                id=str(product.id),
                code=product.code,
                name=product.name,
                description=product.description,
                price=float(product.price),
                thumbnail_url=product.image_url,
                image_url=product.image_url,
                stock_quantity=product.stock_quantity,
                stock_status=(
                    "out_of_stock"
                    if product.stock_quantity == 0
                    else "low_stock"
                    if product.stock_quantity <= 5
                    else "in_stock"
                ),
            )
            for product in products
        ],
        meta=ProductMeta(
            current_page=page,
            limit=limit,
            total=total,
            total_pages=(total + limit - 1) // limit,
        ),
    )
