"""Initial product endpoints skeleton supporting US01 walking skeleton."""

from typing import Any, Dict, List

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/products", tags=["Products"])


class ProductMeta(BaseModel):
    """Pagination metadata conforming to US01 specification."""

    current_page: int = Field(ge=1, description="Current page number")
    limit: int = Field(ge=1, le=100, description="Items per page")
    total: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")


class ProductListResponse(BaseModel):
    """Product list payload structure."""

    data: List[Dict[str, Any]] = Field(default_factory=list, description="List of products")
    meta: ProductMeta


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
) -> ProductListResponse:
    """Browse catalog endpoint skeleton for US01 (Sprint 2 walking skeleton foundation)."""
    return ProductListResponse(
        data=[],
        meta=ProductMeta(
            current_page=page,
            limit=limit,
            total=0,
            total_pages=0,
        ),
    )
