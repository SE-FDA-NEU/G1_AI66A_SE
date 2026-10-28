"""Product catalog endpoint backed by the real database."""

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from src.database import SessionDep
from src.errors import error_detail
from src.models.category import Category
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.schemas.product_variants import VariantResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["Products"])

CATALOG_ERROR_MESSAGE = "Unable to load products right now. Please try again later."
ALLOWED_SORTS = {"newest", "bestselling", "price_asc", "price_desc", "rating_desc"}


class ProductMeta(BaseModel):
    """Pagination metadata conforming to US01 and US11 specifications."""

    current_page: int = Field(ge=1, description="Current page number")
    limit: int = Field(ge=1, le=100, description="Items per page")
    page_size: int = Field(ge=1, le=100, description="Items per page (canonical name)")
    total: int = Field(ge=0, description="Total number of items")
    total_items: int = Field(ge=0, description="Total number of items (US11 alias)")
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
    category_id: int | None = None
    seller_id: int | None = None
    rating: float = 0.0
    review_count: int = 0
    sales_count: int = 0
    variants: list[VariantResponse] = Field(default_factory=list)
    has_variants: bool = False


def get_category_and_descendant_ids(session: Session, category_id: int) -> list[int]:
    """Retrieve the specified category and all descendant category IDs recursively."""
    target = session.get(Category, category_id)
    if target is None or not target.is_active:
        return []

    all_categories = session.exec(
        select(Category.id, Category.parent_id).where(Category.is_active.is_(True))
    ).all()
    children_map: dict[int, list[int]] = defaultdict(list)
    for cat_id, parent_id in all_categories:
        if cat_id is not None and parent_id is not None:
            children_map[parent_id].append(cat_id)

    result = []
    queue = [category_id]
    while queue:
        current = queue.pop(0)
        result.append(current)
        if current in children_map:
            queue.extend(children_map[current])

    return result


def product_response(
    product: Product,
    meta: ProductMetadata | None = None,
    variants: list[ProductVariant] | None = None,
) -> ProductResponse:
    """Map a product and its discovery metadata to the public representation."""
    has_variants = variants is not None
    available_stock = (
        sum(max(variant.stock_quantity - variant.reserved_stock, 0) for variant in variants)
        if has_variants
        else max(product.stock_quantity - product.reserved_stock, 0)
    )
    display_price = (
        min((variant.price for variant in variants), default=product.price)
        if has_variants
        else product.price
    )
    return ProductResponse(
        id=str(product.id),
        code=product.code,
        name=product.name,
        description=product.description,
        price=float(display_price),
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
        category_id=meta.category_id if meta else None,
        seller_id=product.seller_id,
        rating=float(meta.rating if meta and meta.rating is not None else 0.0),
        review_count=int(meta.review_count if meta else 0),
        sales_count=int(meta.sales_count if meta and meta.sales_count is not None else 0),
        has_variants=has_variants,
    )


@router.get("/{product_code}", response_model=ProductResponse)
def get_product(
    session: SessionDep,
    product_code: str = Path(min_length=1, max_length=20),
) -> ProductResponse:
    try:
        row = session.exec(
            select(Product, ProductMetadata)
            .outerjoin(ProductMetadata, Product.id == ProductMetadata.product_id)
            .where(
                Product.code == product_code,
                Product.is_active.is_(True),
            )
        ).first()
        all_variants = (
            session.exec(
                select(ProductVariant)
                .where(ProductVariant.product_id == row[0].id)
                .order_by(ProductVariant.id)
            ).all()
            if row is not None
            else []
        )
    except SQLAlchemyError as exc:
        logger.exception("Product query failed for code %s", product_code)
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", CATALOG_ERROR_MESSAGE),
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found."),
        )
    product, meta = row
    result = (
        product_response(
            product,
            meta,
            [variant for variant in all_variants if variant.is_active],
        )
        if all_variants
        else product_response(product, meta)
    )
    result.variants = [
        VariantResponse.from_model(variant) for variant in all_variants if variant.is_active
    ]
    return result


@router.get("", response_model=ProductListResponse)
def list_products(
    session: SessionDep,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit"),
    search: str | None = Query(
        default=None,
        max_length=200,
        description="Search keyword matching product name or description",
    ),
    category_id: int | None = Query(
        default=None,
        ge=1,
        description="Category filter (includes child/descendant categories)",
    ),
    seller_id: int | None = Query(
        default=None,
        ge=1,
        description="Seller filter by seller user ID",
    ),
    min_price: int | None = Query(
        default=None,
        ge=0,
        description="Minimum price in VND",
    ),
    max_price: int | None = Query(
        default=None,
        ge=0,
        description="Maximum price in VND",
    ),
    min_rating: float | None = Query(
        default=None,
        ge=0.0,
        le=5.0,
        description="Minimum rating (0.0 to 5.0)",
    ),
    in_stock: bool | None = Query(
        default=True,
        description="Filter for in-stock products (defaults to True for buyer catalog)",
    ),
    sort: str | None = Query(
        default=None,
        description="Sort order: newest, bestselling, price_asc, price_desc, rating_desc",
    ),
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Keyword matching name or description; takes precedence over search",
    ),
    sort_by: str | None = Query(
        default=None,
        description="newest, bestselling, price_asc, price_desc, rating_desc; overrides sort",
    ),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="Items per page (default 20); takes precedence over limit",
    ),
) -> ProductListResponse:
    """Return matching products, retaining search/sort/limit for existing clients."""
    search = q if q is not None else search
    sort = sort_by if sort_by is not None else sort
    limit = page_size if page_size is not None else limit
    # AC4: Field-level validation on price bounds
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "ERR_VALIDATION",
                "Minimum price cannot be greater than maximum price.",
            ),
        )

    # AC3: Sort validation
    if sort is not None and sort not in ALLOWED_SORTS:
        allowed_str = ", ".join(sorted(ALLOWED_SORTS))
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "ERR_VALIDATION",
                f"Invalid sort option '{sort}'. Allowed options: {allowed_str}.",
            ),
        )

    try:
        # Base filter: active products
        filters = [Product.is_active.is_(True)]

        # Stock availability filter
        if in_stock is True:
            has_any_variant = (
                select(ProductVariant.id).where(ProductVariant.product_id == Product.id).exists()
            )
            has_available_variant = (
                select(ProductVariant.id)
                .where(
                    ProductVariant.product_id == Product.id,
                    ProductVariant.is_active.is_(True),
                    ProductVariant.stock_quantity > ProductVariant.reserved_stock,
                )
                .exists()
            )
            filters.append(
                or_(
                    (~has_any_variant & (Product.stock_quantity > Product.reserved_stock)),
                    has_available_variant,
                )
            )
        # When in_stock is False (or None), all active products are returned
        # (both in-stock and out-of-stock)

        # AC1: Keyword search across product name OR description
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Product.name.ilike(term),
                    Product.description.ilike(term),
                )
            )

        # AC2: Category filter with recursive descendant hierarchy
        if category_id is not None:
            descendant_ids = get_category_and_descendant_ids(session, category_id)
            if descendant_ids:
                filters.append(ProductMetadata.category_id.in_(descendant_ids))
            else:
                filters.append(Product.id == -1)

        # AC2: Seller filter
        if seller_id is not None:
            filters.append(Product.seller_id == seller_id)

        # AC2: Price range filter
        variant_price = (
            select(func.min(ProductVariant.price))
            .where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
            )
            .scalar_subquery()
        )
        display_price = func.coalesce(variant_price, Product.price)
        if min_price is not None:
            filters.append(display_price >= min_price)
        if max_price is not None:
            filters.append(display_price <= max_price)

        # AC2: Minimum rating filter
        if min_rating is not None:
            filters.append(func.coalesce(ProductMetadata.rating, 0.0) >= min_rating)

        # AC3: Sorting order clauses
        if sort == "newest":
            order_clauses = [
                ProductMetadata.created_at.desc(),
                Product.id.desc(),
            ]
        elif sort == "bestselling":
            order_clauses = [
                func.coalesce(ProductMetadata.sales_count, 0).desc(),
                Product.id.desc(),
            ]
        elif sort == "price_asc":
            order_clauses = [display_price.asc(), Product.id.asc()]
        elif sort == "price_desc":
            order_clauses = [display_price.desc(), Product.id.desc()]
        elif sort == "rating_desc":
            order_clauses = [
                func.coalesce(ProductMetadata.rating, 0.0).desc(),
                Product.id.desc(),
            ]
        else:
            order_clauses = [Product.id.asc()]

        total = session.exec(
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(ProductMetadata, Product.id == ProductMetadata.product_id)
            .where(*filters)
        ).one()
        total_pages = (total + limit - 1) // limit
        effective_page = min(page, total_pages) if total_pages else 1
        offset = (effective_page - 1) * limit if total_pages else 0

        rows = session.exec(
            select(Product, ProductMetadata)
            .outerjoin(ProductMetadata, Product.id == ProductMetadata.product_id)
            .where(*filters)
            .order_by(*order_clauses)
            .offset(offset)
            .limit(limit)
        ).all()
        product_ids = [product.id for product, _meta in rows if product.id is not None]
        all_variants = (
            session.exec(
                select(ProductVariant).where(ProductVariant.product_id.in_(product_ids))
            ).all()
            if product_ids
            else []
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("Product catalog query failed")
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", CATALOG_ERROR_MESSAGE),
        ) from exc

    variants_by_product: dict[int, list[ProductVariant]] = defaultdict(list)
    for variant in all_variants:
        if variant.is_active:
            variants_by_product.setdefault(variant.product_id, []).append(variant)
    any_variant_ids = {variant.product_id for variant in all_variants}
    return ProductListResponse(
        data=[
            product_response(
                product,
                meta,
                variants_by_product.get(product.id, []) if product.id in any_variant_ids else None,
            )
            for product, meta in rows
        ],
        meta=ProductMeta(
            current_page=effective_page,
            limit=limit,
            page_size=limit,
            total=total,
            total_items=total,
            total_pages=total_pages,
        ),
    )
