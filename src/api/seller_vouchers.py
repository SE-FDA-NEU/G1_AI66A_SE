from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.voucher import Voucher
from src.schemas.seller_vouchers import (
    SellerVoucherCreate,
    SellerVoucherResponse,
    SellerVoucherUpdate,
)

router = APIRouter(prefix="/seller/vouchers", tags=["Seller vouchers"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _response(voucher: Voucher) -> SellerVoucherResponse:
    return SellerVoucherResponse.model_validate(voucher, from_attributes=True)


def _validate_discount(discount_type: str, discount_value: int) -> None:
    if discount_type == "PERCENTAGE" and not 0 < discount_value <= 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_DISCOUNT",
                "Percentage discount value must be between 1 and 10000 bps.",
            ),
        )
    if discount_type == "FIXED_AMOUNT" and discount_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_DISCOUNT",
                "Fixed amount discount must be greater than 0.",
            ),
        )


def _validate_dates(starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
    starts = _as_utc(starts_at)
    ends = _as_utc(ends_at)
    if starts >= ends:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_DATES", "Voucher end date must be after start date."
            ),
        )
    return starts, ends


@router.get("", response_model=list[SellerVoucherResponse])
def list_seller_vouchers(seller: SellerUser, session: SessionDep) -> list[SellerVoucherResponse]:
    vouchers = session.exec(
        select(Voucher)
        .where(Voucher.scope == "SHOP", Voucher.seller_id == seller.id)
        .order_by(Voucher.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_response(voucher) for voucher in vouchers]


@router.post("", response_model=SellerVoucherResponse, status_code=status.HTTP_201_CREATED)
def create_seller_voucher(
    payload: SellerVoucherCreate,
    seller: SellerUser,
    session: SessionDep,
) -> SellerVoucherResponse:
    code = payload.code.strip().upper()
    if session.exec(select(Voucher).where(Voucher.code == code)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "ERR_VOUCHER_EXISTS", f"A voucher with code '{code}' already exists."
            ),
        )
    starts_at, ends_at = _validate_dates(payload.starts_at, payload.ends_at)
    discount_value = 0 if payload.discount_type == "FREE_SHIPPING" else payload.discount_value
    _validate_discount(payload.discount_type, discount_value)
    now = datetime.now(UTC)
    voucher = Voucher(
        code=code,
        scope="SHOP",
        seller_id=seller.id,
        discount_type=payload.discount_type,
        discount_value=discount_value,
        max_discount=payload.max_discount,
        min_order_value=payload.min_order_value,
        usage_limit=payload.usage_limit,
        per_user_limit=payload.per_user_limit,
        starts_at=starts_at,
        ends_at=ends_at,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return _response(voucher)


@router.patch("/{voucher_id}", response_model=SellerVoucherResponse)
def update_seller_voucher(
    voucher_id: int,
    payload: SellerVoucherUpdate,
    seller: SellerUser,
    session: SessionDep,
) -> SellerVoucherResponse:
    voucher = session.get(Voucher, voucher_id)
    if voucher is None or voucher.scope != "SHOP" or voucher.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("ERR_VOUCHER_NOT_FOUND", "Shop voucher not found."),
        )

    values = payload.model_dump(exclude_unset=True)
    discount_type = values.get("discount_type", voucher.discount_type)
    discount_value = values.get("discount_value", voucher.discount_value)
    if discount_type == "FREE_SHIPPING":
        discount_value = 0
    _validate_discount(discount_type, discount_value)

    starts_at = values.get("starts_at", voucher.starts_at)
    ends_at = values.get("ends_at", voucher.ends_at)
    starts_at, ends_at = _validate_dates(starts_at, ends_at)
    usage_limit = values.get("usage_limit", voucher.usage_limit)
    if usage_limit is not None and usage_limit < voucher.used_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "ERR_INVALID_USAGE_LIMIT",
                "Usage limit cannot be less than already used count.",
            ),
        )

    for field in ("max_discount", "min_order_value", "per_user_limit", "is_active"):
        if field in values:
            setattr(voucher, field, values[field])
    voucher.discount_type = discount_type
    voucher.discount_value = discount_value
    voucher.usage_limit = usage_limit
    voucher.starts_at = starts_at
    voucher.ends_at = ends_at
    voucher.updated_at = datetime.now(UTC)
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return _response(voucher)
