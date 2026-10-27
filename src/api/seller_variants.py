import logging

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.schemas.product_variants import (
    VariantCreate,
    VariantListResponse,
    VariantResponse,
    VariantResponseEnvelope,
    VariantUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/seller/products/{product_id}/variants", tags=["Seller variants"])


def _owned_product(session: SessionDep, product_id: int, seller_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=404, detail=error_detail("ERR_PRODUCT_NOT_FOUND", "Product not found.")
        )
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=403,
            detail=error_detail("ERR_RESOURCE_OWNER", "You do not own this product."),
        )
    return product


def _variant_response(variant: ProductVariant) -> VariantResponseEnvelope:
    return VariantResponseEnvelope(data=VariantResponse.from_model(variant))


@router.get("", response_model=VariantListResponse)
def list_seller_variants(
    product_id: int = Path(gt=0), seller: SellerUser = ..., session: SessionDep = ...
) -> VariantListResponse:
    _owned_product(session, product_id, seller.id)
    variants = session.exec(
        select(ProductVariant)
        .where(ProductVariant.product_id == product_id)
        .order_by(ProductVariant.id)
    ).all()
    return VariantListResponse(data=[VariantResponse.from_model(item) for item in variants])


@router.post("", response_model=VariantResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_seller_variant(
    body: VariantCreate,
    product_id: int = Path(gt=0),
    seller: SellerUser = ...,
    session: SessionDep = ...,
) -> VariantResponseEnvelope:
    _owned_product(session, product_id, seller.id)
    variant = ProductVariant(
        product_id=product_id,
        seller_id=seller.id,
        **body.model_dump(),
    )
    try:
        session.add(variant)
        session.commit()
        session.refresh(variant)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "ERR_VARIANT_SKU_CONFLICT", "That SKU is already used by your shop."
            ),
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Failed to create product variant")
        raise HTTPException(
            status_code=500, detail=error_detail("ERR_DATABASE_FAILURE", "Unable to save variant.")
        ) from exc
    return _variant_response(variant)


@router.patch("/{variant_id}", response_model=VariantResponseEnvelope)
def update_seller_variant(
    body: VariantUpdate,
    product_id: int = Path(gt=0),
    variant_id: int = Path(gt=0),
    seller: SellerUser = ...,
    session: SessionDep = ...,
) -> VariantResponseEnvelope:
    _owned_product(session, product_id, seller.id)
    variant = session.exec(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            ProductVariant.seller_id == seller.id,
        )
    ).first()
    if variant is None:
        raise HTTPException(
            status_code=404, detail=error_detail("ERR_VARIANT_NOT_FOUND", "Variant not found.")
        )
    changes = {
        field: value
        for field, value in body.model_dump(exclude_unset=True).items()
        if value is not None or field == "image_url"
    }
    if not changes:
        raise HTTPException(
            status_code=422,
            detail=error_detail("ERR_VALIDATION", "Provide a variant field to update."),
        )
    requested_stock = changes.get("stock_quantity")
    if isinstance(requested_stock, int) and requested_stock < variant.reserved_stock:
        raise HTTPException(
            status_code=422,
            detail=error_detail("ERR_VALIDATION", "Stock cannot be lower than reserved stock."),
        )
    try:
        changed = session.exec(
            update(ProductVariant)
            .where(
                ProductVariant.id == variant.id,
                ProductVariant.seller_id == seller.id,
                ProductVariant.version == variant.version,
            )
            .values(**changes, version=ProductVariant.version + 1)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "ERR_CONCURRENCY_CONFLICT", "The variant changed. Refresh and retry."
                ),
            )
        session.refresh(variant)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "ERR_VARIANT_SKU_CONFLICT", "That SKU is already used by your shop."
            ),
        ) from exc
    return _variant_response(variant)


@router.delete("/{variant_id}", response_model=VariantResponseEnvelope)
def deactivate_seller_variant(
    product_id: int = Path(gt=0),
    variant_id: int = Path(gt=0),
    seller: SellerUser = ...,
    session: SessionDep = ...,
) -> VariantResponseEnvelope:
    _owned_product(session, product_id, seller.id)
    variant = session.exec(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            ProductVariant.seller_id == seller.id,
        )
    ).first()
    if variant is None:
        raise HTTPException(
            status_code=404, detail=error_detail("ERR_VARIANT_NOT_FOUND", "Variant not found.")
        )
    changed = session.exec(
        update(ProductVariant)
        .where(
            ProductVariant.id == variant.id,
            ProductVariant.seller_id == seller.id,
            ProductVariant.version == variant.version,
        )
        .values(is_active=False, version=ProductVariant.version + 1)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "ERR_CONCURRENCY_CONFLICT", "The variant changed. Refresh and retry."
            ),
        )
    session.refresh(variant)
    session.commit()
    return _variant_response(variant)
