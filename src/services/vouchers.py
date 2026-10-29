"""Voucher validation, calculation, consumption, and restoration service.

Follows the contract and rules specified in docs/us16-promotions.md.
"""

from datetime import UTC, datetime

from sqlalchemy import func, text
from sqlmodel import Session, select

from src.models.seller_order import SellerOrder
from src.models.voucher import Voucher
from src.models.voucher_usage import VoucherUsage


class VoucherError(Exception):
    """Business rule or validation error for a voucher."""

    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def normalize_voucher_code(code: str) -> str:
    """Normalize a voucher code by trimming whitespace and converting to uppercase."""
    return code.strip().upper()


def calculate_discount(voucher: Voucher, basis: int, shipping_fee: int = 0) -> int:
    """Calculate the discount amount for a voucher against basis or shipping fee.

    Rules from docs/us16-promotions.md:
    - FIXED_AMOUNT: min(basis, voucher.discount_value)
    - PERCENTAGE: (basis * voucher.discount_value) // 10000.
      If max_discount is set and > 0, capped at max_discount.
    - FREE_SHIPPING: min(shipping_fee, voucher.max_discount or shipping_fee).
    """
    if basis < 0 or shipping_fee < 0:
        return 0

    if voucher.discount_type == "FIXED_AMOUNT":
        return max(0, min(basis, voucher.discount_value))
    elif voucher.discount_type == "PERCENTAGE":
        raw_discount = (basis * voucher.discount_value) // 10000
        if voucher.max_discount is not None and voucher.max_discount > 0:
            return max(0, min(raw_discount, voucher.max_discount))
        return max(0, raw_discount)
    elif voucher.discount_type == "FREE_SHIPPING":
        target = shipping_fee
        if voucher.max_discount is not None and voucher.max_discount > 0:
            return max(0, min(target, voucher.max_discount))
        return max(0, target)
    return 0


def validate_voucher(
    session: Session,
    code: str,
    *,
    slot: str,
    basis: int,
    seller_id: int | None = None,
    buyer_id: int | None = None,
    shipping_fee: int = 0,
    now: datetime | None = None,
) -> tuple[Voucher, int]:
    """Validate a voucher for eligibility against slot, seller, dates, minimum, and limits.

    Evaluates rows in exact order from docs/us16-promotions.md section 3.2:
    1. ERR_VOUCHER_NOT_FOUND (404)
    2. ERR_VOUCHER_SCOPE_MISMATCH (409)
    3. ERR_VOUCHER_INACTIVE (409)
    4. ERR_VOUCHER_NOT_STARTED (409)
    5. ERR_VOUCHER_EXPIRED (409)
    6. ERR_VOUCHER_MIN_ORDER (409)
    7. ERR_VOUCHER_USAGE_LIMIT (409)
    8. ERR_VOUCHER_USER_LIMIT (409)
    9. ERR_VOUCHER_NOT_APPLICABLE (409)

    Returns (voucher, computed_discount).
    Raises VoucherError on any rejection.
    """
    normalized = normalize_voucher_code(code)
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    # 1. Check if voucher exists
    voucher = session.exec(select(Voucher).where(Voucher.code == normalized)).first()
    if voucher is None:
        raise VoucherError(
            "ERR_VOUCHER_NOT_FOUND",
            f"Voucher code '{normalized}' was not found.",
            status_code=404,
        )

    # 2. Check scope and slot matching
    if slot == "SHOP":
        if voucher.scope != "SHOP":
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Voucher '{normalized}' is a platform voucher and "
                "cannot be applied as a shop voucher.",
                status_code=409,
            )
        if seller_id is None or voucher.seller_id != seller_id:
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Voucher '{normalized}' is not valid for seller {seller_id}.",
                status_code=409,
            )
        if voucher.discount_type not in ("FIXED_AMOUNT", "PERCENTAGE"):
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Discount type '{voucher.discount_type}' is not allowed for shop vouchers.",
                status_code=409,
            )
    elif slot == "PLATFORM":
        if voucher.scope != "PLATFORM":
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Voucher '{normalized}' is a shop voucher and cannot be applied platform-wide.",
                status_code=409,
            )
        if voucher.discount_type == "FREE_SHIPPING":
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Voucher '{normalized}' is a free shipping voucher "
                "and must be applied in the shipping slot.",
                status_code=409,
            )
        if voucher.discount_type not in ("FIXED_AMOUNT", "PERCENTAGE"):
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Discount type '{voucher.discount_type}' is not allowed for platform vouchers.",
                status_code=409,
            )
    elif slot == "SHIPPING":
        if voucher.scope != "PLATFORM" or voucher.discount_type != "FREE_SHIPPING":
            raise VoucherError(
                "ERR_VOUCHER_SCOPE_MISMATCH",
                f"Voucher '{normalized}' is not a free shipping voucher.",
                status_code=409,
            )
    else:
        raise VoucherError(
            "ERR_VOUCHER_SCOPE_MISMATCH",
            f"Invalid voucher slot '{slot}'.",
            status_code=409,
        )

    # 3. Active status
    if not voucher.is_active:
        raise VoucherError(
            "ERR_VOUCHER_INACTIVE",
            f"Voucher '{normalized}' is currently inactive.",
            status_code=409,
        )

    # 4. Start date (now < starts_at)
    v_starts = (
        voucher.starts_at if voucher.starts_at.tzinfo else voucher.starts_at.replace(tzinfo=UTC)
    )
    if current_time < v_starts:
        raise VoucherError(
            "ERR_VOUCHER_NOT_STARTED",
            f"Voucher '{normalized}' is not valid until {voucher.starts_at.isoformat()}.",
            status_code=409,
        )

    # 5. End date (now >= ends_at)
    v_ends = (
        voucher.ends_at if voucher.ends_at.tzinfo else voucher.ends_at.replace(tzinfo=UTC)
    )
    if current_time >= v_ends:
        raise VoucherError(
            "ERR_VOUCHER_EXPIRED",
            f"Voucher '{normalized}' expired at {voucher.ends_at.isoformat()}.",
            status_code=409,
        )

    # 6. Minimum order value
    if basis < voucher.min_order_value:
        missing = voucher.min_order_value - basis
        raise VoucherError(
            "ERR_VOUCHER_MIN_ORDER",
            f"Order basis of {basis:,} ₫ does not meet the minimum requirement of "
            f"{voucher.min_order_value:,} ₫ (add {missing:,} ₫ more to qualify).",
            status_code=409,
        )

    # 7. Global usage limit
    if voucher.usage_limit is not None and voucher.used_count >= voucher.usage_limit:
        raise VoucherError(
            "ERR_VOUCHER_USAGE_LIMIT",
            f"Voucher '{normalized}' has reached its total usage limit.",
            status_code=409,
        )

    # 8. Per-user usage limit
    if voucher.per_user_limit is not None and buyer_id is not None:
        user_usages_count = session.exec(
            select(func.count())
            .select_from(VoucherUsage)
            .where(
                VoucherUsage.voucher_id == voucher.id,
                VoucherUsage.buyer_id == buyer_id,
                VoucherUsage.status == "APPLIED",
            )
        ).one()
        if user_usages_count >= voucher.per_user_limit:
            raise VoucherError(
                "ERR_VOUCHER_USER_LIMIT",
                f"You have reached the per-user usage limit for voucher '{normalized}'.",
                status_code=409,
            )

    # 9. Computed discount must be > 0
    discount = calculate_discount(voucher, basis=basis, shipping_fee=shipping_fee)
    if discount <= 0:
        raise VoucherError(
            "ERR_VOUCHER_NOT_APPLICABLE",
            f"Voucher '{normalized}' yields zero discount on this order.",
            status_code=409,
        )

    return voucher, discount


def consume_voucher(
    session: Session,
    voucher: Voucher,
    *,
    buyer_id: int,
    order_id: int,
    seller_order_id: int | None = None,
    discount_amount: int,
    now: datetime | None = None,
) -> VoucherUsage:
    """Atomically consume a voucher inside checkout.

    Runs conditional atomic update on used_count:
    UPDATE vouchers SET used_count = used_count + 1
    WHERE id = :id AND is_active = 1
      AND (usage_limit IS NULL OR used_count < usage_limit)

    Rowcount != 1 raises ERR_VOUCHER_USAGE_LIMIT.
    Checks per_user_limit inside the transaction after the update; if exceeded,
    raises ERR_VOUCHER_USER_LIMIT (which rolls back the increment when the transaction aborts).
    Inserts VoucherUsage and flushes.
    """
    stmt = text(
        "UPDATE vouchers SET used_count = used_count + 1 "
        "WHERE id = :id AND is_active = 1 "
        "AND (usage_limit IS NULL OR used_count < usage_limit)"
    )
    result = session.execute(stmt, {"id": voucher.id})
    if result.rowcount != 1:
        raise VoucherError(
            "ERR_VOUCHER_USAGE_LIMIT",
            f"Voucher '{voucher.code}' has reached its total usage limit.",
            status_code=409,
        )

    # Check per_user_limit after conditional update
    if voucher.per_user_limit is not None:
        user_usages_count = session.exec(
            select(func.count())
            .select_from(VoucherUsage)
            .where(
                VoucherUsage.voucher_id == voucher.id,
                VoucherUsage.buyer_id == buyer_id,
                VoucherUsage.status == "APPLIED",
            )
        ).one()
        if user_usages_count >= voucher.per_user_limit:
            raise VoucherError(
                "ERR_VOUCHER_USER_LIMIT",
                f"You have reached the per-user usage limit for voucher '{voucher.code}'.",
                status_code=409,
            )

    current_time = now or datetime.now(UTC)
    usage = VoucherUsage(
        voucher_id=voucher.id,  # type: ignore[arg-type]
        buyer_id=buyer_id,
        order_id=order_id,
        seller_order_id=seller_order_id,
        code=voucher.code,
        discount_amount=discount_amount,
        status="APPLIED",
        created_at=current_time,
    )
    session.add(usage)
    session.flush()
    session.refresh(voucher)
    return usage


def restore_voucher_usage(
    session: Session,
    usage_id: int,
    now: datetime | None = None,
) -> bool:
    """Restore a voucher usage and decrement used_count.

    UPDATE voucher_usages SET status = 'RESTORED', restored_at = :now
    WHERE id = :id AND status = 'APPLIED'

    Decrements vouchers.used_count (clamped at 0) only if 1 row was updated.
    Returns True if successfully restored, False if already restored or not found.
    """
    current_time = now or datetime.now(UTC)
    usage = session.get(VoucherUsage, usage_id)
    if not usage or usage.status != "APPLIED":
        return False

    stmt = text(
        "UPDATE voucher_usages SET status = 'RESTORED', restored_at = :now "
        "WHERE id = :id AND status = 'APPLIED'"
    )
    res = session.execute(stmt, {"id": usage_id, "now": current_time})
    if res.rowcount == 1:
        dec_stmt = text(
            "UPDATE vouchers SET used_count = MAX(0, used_count - 1) "
            "WHERE id = :voucher_id"
        )
        session.execute(dec_stmt, {"voucher_id": usage.voucher_id})
        session.flush()
        session.refresh(usage)
        return True
    return False


def restore_seller_order_vouchers(
    session: Session,
    seller_order: SellerOrder,
    now: datetime | None = None,
) -> list[VoucherUsage]:
    """Restore vouchers associated with a cancelled seller order.

    Rules from docs/us16-promotions.md section 7:
    - Shop voucher attached to seller_order.id is restored when its seller order is cancelled.
    - Platform or shipping voucher attached to parent order is restored only when every
      seller order of the order with a non-zero platform_discount (or shipping_discount)
      is cancelled.
    """
    restored: list[VoucherUsage] = []

    # 1. Restore shop voucher attached to this suborder
    shop_usages = session.exec(
        select(VoucherUsage).where(
            VoucherUsage.seller_order_id == seller_order.id,
            VoucherUsage.status == "APPLIED",
        )
    ).all()
    for u in shop_usages:
        if restore_voucher_usage(session, u.id, now=now):  # type: ignore[arg-type]
            restored.append(u)

    # 2. Check if platform voucher can be restored
    other_active_platform = session.exec(
        select(SellerOrder).where(
            SellerOrder.order_id == seller_order.order_id,
            SellerOrder.id != seller_order.id,
            SellerOrder.platform_discount > 0,
            SellerOrder.status != "CANCELLED",
        )
    ).all()
    if not other_active_platform:
        platform_usages = session.exec(
            select(VoucherUsage).where(
                VoucherUsage.order_id == seller_order.order_id,
                VoucherUsage.seller_order_id == None,  # noqa: E711
                VoucherUsage.status == "APPLIED",
            )
        ).all()
        for u in platform_usages:
            v = session.get(Voucher, u.voucher_id)
            if v and v.discount_type != "FREE_SHIPPING":
                if restore_voucher_usage(session, u.id, now=now):  # type: ignore[arg-type]
                    restored.append(u)

    # 3. Check if shipping voucher can be restored
    other_active_shipping = session.exec(
        select(SellerOrder).where(
            SellerOrder.order_id == seller_order.order_id,
            SellerOrder.id != seller_order.id,
            SellerOrder.shipping_discount > 0,
            SellerOrder.status != "CANCELLED",
        )
    ).all()
    if not other_active_shipping:
        shipping_usages = session.exec(
            select(VoucherUsage).where(
                VoucherUsage.order_id == seller_order.order_id,
                VoucherUsage.seller_order_id == None,  # noqa: E711
                VoucherUsage.status == "APPLIED",
            )
        ).all()
        for u in shipping_usages:
            v = session.get(Voucher, u.voucher_id)
            if v and v.discount_type == "FREE_SHIPPING":
                if restore_voucher_usage(session, u.id, now=now):  # type: ignore[arg-type]
                    restored.append(u)

    return restored
