"""Product catalog endpoint backed by the real database."""

from math import ceil

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database import get_db

router = APIRouter(prefix="/products", tags=["Products"])


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
    name: str
    description: str | None
    price: float
    thumbnail_url: str | None
    stock_quantity: int
    stock_status: str = ""


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
    db: Session = Depends(get_db),
) -> ProductListResponse:
    """Return a paginated list of published products from the database."""
    total = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM products
            WHERE is_published = :published AND deleted_at IS NULL
            """
        ),
        {"published": True},
    ).scalar_one()
    rows = db.execute(
        text(
            """
            SELECT id, name, description, price, thumbnail_url, stock_quantity
            FROM products
            WHERE is_published = :published AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"published": True, "limit": limit, "offset": (page - 1) * limit},
    ).mappings().all()

    products = [
        ProductResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            price=float(row["price"]),
            thumbnail_url=row["thumbnail_url"],
            stock_quantity=row["stock_quantity"],
            stock_status=(
                "out_of_stock"
                if row["stock_quantity"] == 0
                else "low_stock"
                if row["stock_quantity"] <= 5
                else "in_stock"
            ),
        )
        for row in rows
    ]

    return ProductListResponse(
        data=products,
        meta=ProductMeta(
            current_page=page,
            limit=limit,
            total=total,
            total_pages=ceil(total / limit) if total else 0,
        ),
    )
