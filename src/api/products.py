"""Product catalog endpoint backed by the real database."""

import logging

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.database import SessionDep
from src.errors import error_detail
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


def product_response(product: Product) -> ProductResponse:
    """Map a product to the public product representation."""
    available_stock = max(product.stock_quantity - product.reserved_stock, 0)
    return ProductResponse(
        id=str(product.id),
        code=product.code,
        name=product.name,
        description=product.description,
        price=float(product.price),
        thumbnail_url=product.image_url,
        image_url=product.image_url,
        stock_quantity=available_stock,
        stock_status=(
            "out_of_stock"
            if available_stock == 0
            else "low_stock"
            if available_stock <= 5
            else "in_stock"
        ),
    )


@router.get("/{product_code}", response_model=ProductResponse)
def get_product(
    session: SessionDep,
    product_code: str = Path(min_length=1, max_length=20),
) -> ProductResponse:
    """Return an active product by its public code, including out-of-stock products."""
    product = session.exec(
        select(Product).where(
            Product.code == product_code,
            Product.is_active.is_(True),
        )
    ).first()
    if product is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
        )
    return product_response(product)


@router.get("", response_model=ProductListResponse)
def list_products(
    session: SessionDep,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
    search: str | None = Query(
        default=None,
        max_length=200,
        description="Case-insensitive product-name search",
    ),
) -> ProductListResponse:
    """Return available products from the database with stable pagination."""
    # A failed query must surface as an error, never as an empty catalog.
    try:
        filters = [
            Product.is_active.is_(True),
            Product.stock_quantity > Product.reserved_stock,
        ]
        if search and search.strip():
            filters.append(Product.name.ilike(f"%{search.strip()}%"))

        total = session.exec(select(func.count()).select_from(Product).where(*filters)).one()
        total_pages = (total + limit - 1) // limit
        effective_page = min(page, total_pages) if total_pages else 1
        products = session.exec(
            select(Product)
            .where(*filters)
            .order_by(Product.id)
            .offset((effective_page - 1) * limit)
            .limit(limit)
        ).all()
    except SQLAlchemyError as exc:
        logger.exception("Product catalog query failed")
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", CATALOG_ERROR_MESSAGE),
        ) from exc
    return ProductListResponse(
        data=[
            product_response(product)
            for product in products
        ],
        meta=ProductMeta(
            current_page=effective_page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )
