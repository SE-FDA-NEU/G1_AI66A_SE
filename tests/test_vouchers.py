"""Tests for vouchers and voucher_usages persistence, validation, concurrency, and restoration.

Story: #108, Task: #133.
Specification: docs/us16-promotions.md
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.database import migrate_db
from src.models.order import Order
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from src.models.voucher_usage import VoucherUsage
from src.services.vouchers import (
    VoucherError,
    calculate_discount,
    consume_voucher,
    normalize_voucher_code,
    restore_seller_order_vouchers,
    restore_voucher_usage,
    validate_voucher,
)
from tests.cart_db import (
    BUYER_ID,
    OTHER_BUYER_ID,
    SELLER_ID,
    add_product,
    create_cart_engine,
)


@pytest.fixture
def db(tmp_path: Path):
    """Provide a fresh SQLite test engine for isolated voucher tests."""
    return create_cart_engine(tmp_path / "voucher_test.db")


def _make_voucher(
    session: Session,
    code: str,
    *,
    scope: str = "PLATFORM",
    seller_id: int | None = None,
    discount_type: str = "FIXED_AMOUNT",
    discount_value: int = 20_000,
    max_discount: int | None = None,
    min_order_value: int = 100_000,
    usage_limit: int | None = 10,
    per_user_limit: int | None = 2,
    used_count: int = 0,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> Voucher:
    now = datetime.now(UTC)
    v = Voucher(
        code=normalize_voucher_code(code),
        scope=scope,
        seller_id=seller_id if scope == "SHOP" else None,
        discount_type=discount_type,
        discount_value=discount_value,
        max_discount=max_discount,
        min_order_value=min_order_value,
        usage_limit=usage_limit,
        per_user_limit=per_user_limit,
        used_count=used_count,
        starts_at=starts_at or (now - timedelta(days=1)),
        ends_at=ends_at or (now + timedelta(days=30)),
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def _make_order(
    session: Session,
    order_id: int,
    *,
    buyer_id: int = BUYER_ID,
    total_amount: int = 200_000,
    status: str = "PAID",
) -> Order:
    order = Order(
        id=order_id,
        buyer_id=buyer_id,
        total_amount=total_amount,
        status=status,
        recipient_name="Test Buyer",
        delivery_address="123 Street, District 1, HCMC",
        phone_number="0901234567",
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


# ===========================================================================
# 1. Eligibility Checklist & Actionable Error Codes (Section 3.2)
# ===========================================================================


def test_validation_err_voucher_not_found(db):
    """Rule 1: Unknown voucher code raises 404 ERR_VOUCHER_NOT_FOUND."""
    with Session(db) as session:
        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "DOESNOTEXIST", slot="PLATFORM", basis=200_000)
        assert exc.value.status_code == 404
        assert exc.value.code == "ERR_VOUCHER_NOT_FOUND"


def test_validation_err_voucher_scope_mismatch(db):
    """Rule 2: Mismatched slot or other seller's voucher raises 409 ERR_VOUCHER_SCOPE_MISMATCH."""
    with Session(db) as session:
        # Platform voucher requested in SHOP slot
        _make_voucher(session, "PLAT_V1", scope="PLATFORM", discount_type="FIXED_AMOUNT")
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "PLAT_V1", slot="SHOP", basis=200_000, seller_id=SELLER_ID
            )
        assert exc.value.code == "ERR_VOUCHER_SCOPE_MISMATCH"

        # Shop voucher requested in PLATFORM slot
        _make_voucher(
            session,
            "SHOP_V1",
            scope="SHOP",
            seller_id=SELLER_ID,
            discount_type="FIXED_AMOUNT",
        )
        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "SHOP_V1", slot="PLATFORM", basis=200_000)
        assert exc.value.code == "ERR_VOUCHER_SCOPE_MISMATCH"

        # Shop voucher for Seller A requested for Seller B
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "SHOP_V1", slot="SHOP", basis=200_000, seller_id=999
            )
        assert exc.value.code == "ERR_VOUCHER_SCOPE_MISMATCH"

        # Free shipping voucher requested in PLATFORM slot instead of SHIPPING slot
        _make_voucher(
            session,
            "SHIP_V1",
            scope="PLATFORM",
            discount_type="FREE_SHIPPING",
            discount_value=0,
        )
        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "SHIP_V1", slot="PLATFORM", basis=200_000)
        assert exc.value.code == "ERR_VOUCHER_SCOPE_MISMATCH"


def test_validation_err_voucher_inactive(db):
    """Rule 3: Inactive voucher raises 409 ERR_VOUCHER_INACTIVE."""
    with Session(db) as session:
        _make_voucher(session, "INACTIVE1", is_active=False)
        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "INACTIVE1", slot="PLATFORM", basis=200_000)
        assert exc.value.code == "ERR_VOUCHER_INACTIVE"


def test_validation_err_voucher_not_started_and_boundary(db):
    """Rule 4: Clock before starts_at fails; starts_at passes with microsecond precision."""
    starts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    ends = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)

    with Session(db) as session:
        _make_voucher(session, "TIME_V1", starts_at=starts, ends_at=ends)

        # 1 microsecond before start fails
        before = starts - timedelta(microseconds=1)
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "TIME_V1", slot="PLATFORM", basis=200_000, now=before
            )
        assert exc.value.code == "ERR_VOUCHER_NOT_STARTED"

        # Exactly at starts_at passes
        v, discount = validate_voucher(
            session, "TIME_V1", slot="PLATFORM", basis=200_000, now=starts
        )
        assert v.code == "TIME_V1"
        assert discount == 20_000


def test_validation_err_voucher_expired_and_boundary(db):
    """Rule 5: Injected clock at or after ends_at fails; 1 microsecond before ends_at passes."""
    starts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    ends = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)

    with Session(db) as session:
        _make_voucher(session, "EXP_V1", starts_at=starts, ends_at=ends)

        # 1 microsecond before ends_at passes
        almost_end = ends - timedelta(microseconds=1)
        v, discount = validate_voucher(
            session, "EXP_V1", slot="PLATFORM", basis=200_000, now=almost_end
        )
        assert v.code == "EXP_V1"
        assert discount > 0

        # Exactly at ends_at is already expired
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "EXP_V1", slot="PLATFORM", basis=200_000, now=ends
            )
        assert exc.value.code == "ERR_VOUCHER_EXPIRED"

        # After ends_at is expired
        after = ends + timedelta(seconds=1)
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "EXP_V1", slot="PLATFORM", basis=200_000, now=after
            )
        assert exc.value.code == "ERR_VOUCHER_EXPIRED"


def test_validation_err_voucher_min_order_actionable(db):
    """Rule 6: Basis < min_order_value raises 409 ERR_VOUCHER_MIN_ORDER with missing amount."""
    with Session(db) as session:
        _make_voucher(session, "MIN_ORDER_V", min_order_value=300_000)

        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "MIN_ORDER_V", slot="PLATFORM", basis=250_000)
        assert exc.value.code == "ERR_VOUCHER_MIN_ORDER"
        # Must give actionable feedback about missing amount (50,000)
        assert "50,000" in exc.value.message


def test_validation_err_voucher_usage_limit(db):
    """Rule 7: Global usage_limit reached raises 409 ERR_VOUCHER_USAGE_LIMIT."""
    with Session(db) as session:
        _make_voucher(session, "GLOBAL_LIMIT", usage_limit=5, used_count=5)

        with pytest.raises(VoucherError) as exc:
            validate_voucher(session, "GLOBAL_LIMIT", slot="PLATFORM", basis=200_000)
        assert exc.value.code == "ERR_VOUCHER_USAGE_LIMIT"


def test_validation_err_voucher_user_limit(db):
    """Rule 8: Per-user limit reached raises 409 ERR_VOUCHER_USER_LIMIT."""
    with Session(db) as session:
        v = _make_voucher(session, "USER_LIMIT_V", per_user_limit=1, usage_limit=10)
        _make_order(session, 101, buyer_id=BUYER_ID)

        # Buyer has 1 APPLIED usage
        usage = VoucherUsage(
            voucher_id=v.id,  # type: ignore[arg-type]
            buyer_id=BUYER_ID,
            order_id=101,
            code=v.code,
            discount_amount=20_000,
            status="APPLIED",
        )
        session.add(usage)
        session.commit()

        # Same buyer is rejected
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session,
                "USER_LIMIT_V",
                slot="PLATFORM",
                basis=200_000,
                buyer_id=BUYER_ID,
            )
        assert exc.value.code == "ERR_VOUCHER_USER_LIMIT"

        # Different buyer is accepted
        v_ok, _ = validate_voucher(
            session,
            "USER_LIMIT_V",
            slot="PLATFORM",
            basis=200_000,
            buyer_id=OTHER_BUYER_ID,
        )
        assert v_ok.code == "USER_LIMIT_V"


def test_validation_err_voucher_not_applicable(db):
    """Rule 9: Computed discount == 0 raises 409 ERR_VOUCHER_NOT_APPLICABLE."""
    with Session(db) as session:
        # Free shipping voucher when shipping_fee is 0
        _make_voucher(
            session,
            "SHIP_ZERO",
            scope="PLATFORM",
            discount_type="FREE_SHIPPING",
            discount_value=0,
            min_order_value=0,
        )
        with pytest.raises(VoucherError) as exc:
            validate_voucher(
                session, "SHIP_ZERO", slot="SHIPPING", basis=200_000, shipping_fee=0
            )
        assert exc.value.code == "ERR_VOUCHER_NOT_APPLICABLE"


# ===========================================================================
# 2. Discount Calculation Details (Section 2.1 & 2.2 Boundary Cases)
# ===========================================================================


def test_calculate_discount_fixed_amount_and_boundary(db):
    """Fixed amount discount: min(basis, value) per Section 2.2."""
    with Session(db) as session:
        v = _make_voucher(session, "FIXED50K", discount_type="FIXED_AMOUNT", discount_value=50_000)

        # Basis 100k -> 50k
        assert calculate_discount(v, basis=100_000) == 50_000

        # Basis 40k -> capped at basis 40k
        assert calculate_discount(v, basis=40_000) == 40_000


def test_calculate_discount_percentage_bps_and_cap(db):
    """Percentage discount in bps: floor division and max_discount cap."""
    with Session(db) as session:
        # 10% (1000 bps) with max_discount 50k
        v10 = _make_voucher(
            session,
            "PCT10",
            discount_type="PERCENTAGE",
            discount_value=1000,
            max_discount=50_000,
        )
        assert calculate_discount(v10, basis=300_000) == 30_000
        assert calculate_discount(v10, basis=600_000) == 50_000  # capped at 50k

        # Floor division test: 333 bps on 10,001 -> 333
        v_floor = _make_voucher(
            session, "PCT_FLOOR", discount_type="PERCENTAGE", discount_value=333
        )
        assert calculate_discount(v_floor, basis=10_001) == 333

        # Percentage cap from section 2.2: 1500 bps (15%), max 20k on 300k basis -> 20k
        v_cap = _make_voucher(
            session,
            "PCT_CAP",
            discount_type="PERCENTAGE",
            discount_value=1500,
            max_discount=20_000,
        )
        assert calculate_discount(v_cap, basis=300_000) == 20_000


def test_calculate_discount_free_shipping(db):
    """Free shipping discount: min(shipping_fee, max_discount or shipping_fee)."""
    with Session(db) as session:
        v_ship = _make_voucher(
            session,
            "FREESHIP15",
            scope="PLATFORM",
            discount_type="FREE_SHIPPING",
            discount_value=0,
            max_discount=15_000,
        )
        assert calculate_discount(v_ship, basis=200_000, shipping_fee=20_000) == 15_000
        assert calculate_discount(v_ship, basis=200_000, shipping_fee=10_000) == 10_000


# ===========================================================================
# 3. Database Schema Constraints & Integrity
# ===========================================================================


def test_db_constraint_shop_voucher_requires_seller_id(db):
    """ck_vouchers_scope_seller: SHOP scope without seller_id raises IntegrityError."""
    with Session(db) as session:
        now = datetime.now(UTC)
        v = Voucher(
            code="INVALID_SHOP",
            scope="SHOP",
            seller_id=None,  # Invalid: SHOP requires seller_id
            discount_type="FIXED_AMOUNT",
            discount_value=10_000,
            starts_at=now,
            ends_at=now + timedelta(days=1),
        )
        session.add(v)
        with pytest.raises(IntegrityError):
            session.commit()


def test_db_constraint_platform_voucher_forbids_seller_id(db):
    """ck_vouchers_scope_seller: PLATFORM scope with seller_id raises IntegrityError."""
    with Session(db) as session:
        now = datetime.now(UTC)
        v = Voucher(
            code="INVALID_PLAT",
            scope="PLATFORM",
            seller_id=SELLER_ID,  # Invalid: PLATFORM requires seller_id IS NULL
            discount_type="FIXED_AMOUNT",
            discount_value=10_000,
            starts_at=now,
            ends_at=now + timedelta(days=1),
        )
        session.add(v)
        with pytest.raises(IntegrityError):
            session.commit()


def test_db_constraint_free_shipping_only_on_platform(db):
    """ck_vouchers_free_shipping_platform: FREE_SHIPPING cannot be SHOP scope."""
    with Session(db) as session:
        now = datetime.now(UTC)
        v = Voucher(
            code="SHOP_FREESHIP",
            scope="SHOP",
            seller_id=SELLER_ID,
            discount_type="FREE_SHIPPING",  # Invalid for SHOP
            discount_value=0,
            starts_at=now,
            ends_at=now + timedelta(days=1),
        )
        session.add(v)
        with pytest.raises(IntegrityError):
            session.commit()


def test_db_constraint_dates_order(db):
    """ck_vouchers_dates: starts_at >= ends_at raises IntegrityError."""
    with Session(db) as session:
        now = datetime.now(UTC)
        v = Voucher(
            code="BAD_DATES",
            scope="PLATFORM",
            discount_type="FIXED_AMOUNT",
            discount_value=10_000,
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=1),  # ends before starts
        )
        session.add(v)
        with pytest.raises(IntegrityError):
            session.commit()


def test_db_constraint_unique_voucher_per_order(db):
    """uq_voucher_usages_voucher_order: Same voucher twice in same order raises IntegrityError."""
    with Session(db) as session:
        v = _make_voucher(session, "UNIQ_ORDER_V")
        _make_order(session, 500, buyer_id=BUYER_ID)

        u1 = VoucherUsage(
            voucher_id=v.id,  # type: ignore[arg-type]
            buyer_id=BUYER_ID,
            order_id=500,
            code=v.code,
            discount_amount=10_000,
            status="APPLIED",
        )
        session.add(u1)
        session.commit()

        u2 = VoucherUsage(
            voucher_id=v.id,  # type: ignore[arg-type]
            buyer_id=BUYER_ID,
            order_id=500,  # duplicate order_id + voucher_id
            code=v.code,
            discount_amount=10_000,
            status="APPLIED",
        )
        session.add(u2)
        with pytest.raises(IntegrityError):
            session.commit()


# ===========================================================================
# 4. Consumption, Concurrency, and Atomic Rollback (Section 7)
# ===========================================================================


def test_quote_never_consumes_voucher(db):
    """Assert that quote (validation) leaves used_count and voucher_usages unchanged."""
    with Session(db) as session:
        v = _make_voucher(session, "QUOTE_SAFE", usage_limit=10, used_count=0)
        for _ in range(5):
            validate_voucher(session, "QUOTE_SAFE", slot="PLATFORM", basis=200_000)

        session.refresh(v)
        assert v.used_count == 0
        usages = session.exec(select(VoucherUsage).where(VoucherUsage.voucher_id == v.id)).all()
        assert len(usages) == 0


def test_consume_voucher_conditional_update_and_flush(db):
    """consume_voucher increments used_count and creates VoucherUsage row."""
    with Session(db) as session:
        v = _make_voucher(session, "CONSUME1", usage_limit=5, used_count=0)
        _make_order(session, 201, buyer_id=BUYER_ID)

        usage = consume_voucher(
            session,
            v,
            buyer_id=BUYER_ID,
            order_id=201,
            seller_order_id=None,
            discount_amount=20_000,
        )
        session.commit()

        session.refresh(v)
        assert v.used_count == 1
        assert usage.status == "APPLIED"
        assert usage.discount_amount == 20_000


def test_concurrent_consumption_global_limit_race(db):
    """Two concurrent threads competing for 1 remaining slot: exactly one succeeds."""
    with Session(db) as session:
        v = _make_voucher(session, "RACE_GLOBAL", usage_limit=1, used_count=0)
        voucher_id = v.id
        _make_order(session, 301, buyer_id=BUYER_ID)
        _make_order(session, 302, buyer_id=OTHER_BUYER_ID)

    def worker(buyer: int, order: int):
        with Session(db) as s:
            target = s.get(Voucher, voucher_id)
            try:
                consume_voucher(
                    s,
                    target,  # type: ignore[arg-type]
                    buyer_id=buyer,
                    order_id=order,
                    discount_amount=20_000,
                )
                s.commit()
                return True
            except VoucherError as e:
                s.rollback()
                return e.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, BUYER_ID, 301)
        f2 = executor.submit(worker, OTHER_BUYER_ID, 302)
        r1 = f1.result()
        r2 = f2.result()

    results = [r1, r2]
    assert results.count(True) == 1
    assert "ERR_VOUCHER_USAGE_LIMIT" in results

    with Session(db) as session:
        final_v = session.get(Voucher, voucher_id)
        assert final_v.used_count == 1
        usages = session.exec(
            select(VoucherUsage).where(VoucherUsage.voucher_id == voucher_id)
        ).all()
        assert len(usages) == 1


def test_concurrent_consumption_per_user_limit_race(db):
    """Two concurrent threads for same buyer competing for 1 remaining per-user limit."""
    with Session(db) as session:
        v = _make_voucher(
            session,
            "RACE_USER",
            usage_limit=10,
            per_user_limit=1,
            used_count=0,
        )
        voucher_id = v.id
        _make_order(session, 401, buyer_id=BUYER_ID)
        _make_order(session, 402, buyer_id=BUYER_ID)

    def worker(order: int):
        with Session(db) as s:
            target = s.get(Voucher, voucher_id)
            try:
                consume_voucher(
                    s,
                    target,  # type: ignore[arg-type]
                    buyer_id=BUYER_ID,
                    order_id=order,
                    discount_amount=20_000,
                )
                s.commit()
                return True
            except VoucherError as e:
                s.rollback()
                return e.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, 401)
        f2 = executor.submit(worker, 402)
        r1 = f1.result()
        r2 = f2.result()

    results = [r1, r2]
    assert results.count(True) == 1
    assert "ERR_VOUCHER_USER_LIMIT" in results

    with Session(db) as session:
        final_v = session.get(Voucher, voucher_id)
        assert final_v.used_count == 1
        usages = session.exec(
            select(VoucherUsage).where(VoucherUsage.voucher_id == voucher_id)
        ).all()
        assert len(usages) == 1


def test_atomic_rollback_on_failure_leaves_no_traces(db):
    """Failure after consume inside a transaction leaves no usage row and un-incremented counter."""
    with Session(db) as session:
        v = _make_voucher(session, "ROLLBACK_V", usage_limit=5, used_count=2)
        voucher_id = v.id
        _make_order(session, 777, buyer_id=BUYER_ID)

        # Start consumption
        consume_voucher(
            session,
            v,
            buyer_id=BUYER_ID,
            order_id=777,
            discount_amount=20_000,
        )
        # Simulate unexpected error in checkout transaction
        session.rollback()

    with Session(db) as session:
        v_after = session.get(Voucher, voucher_id)
        assert v_after.used_count == 2
        usages = session.exec(
            select(VoucherUsage).where(VoucherUsage.voucher_id == voucher_id)
        ).all()
        assert len(usages) == 0


# ===========================================================================
# 5. Restoration Rules (Section 7)
# ===========================================================================


def test_restore_voucher_usage_decrements_used_count(db):
    """Restoring an applied usage decrements used_count and sets RESTORED status."""
    with Session(db) as session:
        v = _make_voucher(session, "RESTORE1", usage_limit=10, used_count=3)
        _make_order(session, 601, buyer_id=BUYER_ID)

        usage = consume_voucher(
            session,
            v,
            buyer_id=BUYER_ID,
            order_id=601,
            discount_amount=20_000,
        )
        session.commit()
        session.refresh(v)
        assert v.used_count == 4

        # Restore
        success = restore_voucher_usage(session, usage.id)  # type: ignore[arg-type]
        session.commit()
        assert success is True

        session.refresh(v)
        session.refresh(usage)
        assert v.used_count == 3
        assert usage.status == "RESTORED"
        assert usage.restored_at is not None

        # Rerun restore on same usage is a no-op (does not decrement again)
        rerun_success = restore_voucher_usage(session, usage.id)  # type: ignore[arg-type]
        session.commit()
        assert rerun_success is False
        session.refresh(v)
        assert v.used_count == 3


def test_restore_seller_order_vouchers_shop_and_platform_lifecycle(db):
    """Shop voucher restores on suborder cancel; platform restores only after all shops cancel."""
    with Session(db) as session:
        v_shop = _make_voucher(
            session, "SHOP_CANCEL", scope="SHOP", seller_id=SELLER_ID, used_count=1
        )
        v_plat = _make_voucher(session, "PLAT_CANCEL", scope="PLATFORM", used_count=1)

        # Add second seller for two-shop order
        other_seller = User(id=4, name="Seller 2", email="seller2@test.local", role="seller")
        session.add(other_seller)
        session.commit()

        # Parent order with 2 suborders
        _make_order(session, 800, buyer_id=BUYER_ID, total_amount=400_000)
        so1 = SellerOrder(
            id=901,
            order_id=800,
            seller_id=SELLER_ID,
            status="CONFIRMED",
            subtotal=200_000,
            shop_discount=20_000,
            platform_discount=10_000,
            total_amount=170_000,
        )
        so2 = SellerOrder(
            id=902,
            order_id=800,
            seller_id=4,  # other seller
            status="CONFIRMED",
            subtotal=200_000,
            shop_discount=0,
            platform_discount=10_000,
            total_amount=190_000,
        )
        session.add_all([so1, so2])
        session.commit()

        # Add usages
        u_shop = VoucherUsage(
            id=1001,
            voucher_id=v_shop.id,  # type: ignore[arg-type]
            buyer_id=BUYER_ID,
            order_id=800,
            seller_order_id=901,
            code=v_shop.code,
            discount_amount=20_000,
            status="APPLIED",
        )
        u_plat = VoucherUsage(
            id=1002,
            voucher_id=v_plat.id,  # type: ignore[arg-type]
            buyer_id=BUYER_ID,
            order_id=800,
            seller_order_id=None,
            code=v_plat.code,
            discount_amount=20_000,
            status="APPLIED",
        )
        session.add_all([u_shop, u_plat])
        session.commit()

        # Cancel suborder 1
        so1.status = "CANCELLED"
        session.add(so1)
        session.commit()

        restored_so1 = restore_seller_order_vouchers(session, so1)
        session.commit()
        assert len(restored_so1) == 1

        # Shop voucher is restored
        session.refresh(v_shop)
        session.refresh(u_shop)
        assert v_shop.used_count == 0
        assert u_shop.status == "RESTORED"

        # Platform voucher NOT restored yet because so2 is still CONFIRMED
        session.refresh(v_plat)
        session.refresh(u_plat)
        assert v_plat.used_count == 1
        assert u_plat.status == "APPLIED"

        # Now cancel suborder 2
        so2.status = "CANCELLED"
        session.add(so2)
        session.commit()

        restored_so2 = restore_seller_order_vouchers(session, so2)
        session.commit()
        assert len(restored_so2) == 1

        # Now platform voucher IS restored
        session.refresh(v_plat)
        session.refresh(u_plat)
        assert v_plat.used_count == 0
        assert u_plat.status == "RESTORED"


# ===========================================================================
# 6. Database Migration & Legacy Backfill (Section 6)
# ===========================================================================


def test_migration_fresh_legacy_and_rerun(tmp_path: Path):
    """Test migration on fresh DB, legacy pre-US16 DB, backfill, and rerun idempotency."""
    db_file = tmp_path / "legacy_migration.db"
    engine = create_cart_engine(db_file)
    product_id = add_product(engine, "LEGACY_PROD", price=100_000)

    # 1. Recreate seller_orders with only pre-US16 columns to simulate old database
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE seller_orders"))
        conn.execute(
            text(
                "CREATE TABLE seller_orders ("
                "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                "order_id INTEGER NOT NULL, "
                "seller_id INTEGER NOT NULL, "
                "status VARCHAR(30) NOT NULL, "
                "payment_status VARCHAR(30) DEFAULT 'PAID', "
                "escrow_status VARCHAR(30) DEFAULT 'HELD', "
                "created_at DATETIME, "
                "tracking_number VARCHAR(100), "
                "shipped_at DATETIME, "
                "delivered_at DATETIME, "
                "completed_at DATETIME, "
                "FOREIGN KEY(order_id) REFERENCES orders(id), "
                "FOREIGN KEY(seller_id) REFERENCES users(id)"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO orders (id, buyer_id, total_amount, status, payment_status, "
                "escrow_status, recipient_name, delivery_address, phone_number, created_at) "
                "VALUES (1, 2, 250000, 'PAID', 'PAID', 'HELD', 'Buyer', 'Address', '0123456789', "
                "CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO seller_orders (id, order_id, seller_id, status, created_at) "
                "VALUES (1, 1, 1, 'COMPLETED', CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO order_items (seller_order_id, product_id, quantity, unit_price, "
                "snapshot_initialized) "
                "VALUES (1, :pid, 2, 100000, 0), (1, :pid, 1, 50000, 0)"
            ),
            {"pid": product_id},
        )

    # 2. Run migration with raw connection
    with engine.begin() as conn:
        migrate_db(conn)

    # 3. Check backfill
    with Session(engine) as session:
        so_migrated = session.get(SellerOrder, 1)
        assert so_migrated.subtotal == 250_000
        assert so_migrated.total_amount == 250_000
        assert so_migrated.shop_discount == 0
        assert so_migrated.platform_discount == 0
        assert so_migrated.shipping_fee == 0
        assert so_migrated.shipping_discount == 0
        assert so_migrated.pricing_policy_version == "LEGACY"

        # Check orders.total_amount equals sum of seller_orders.total_amount
        order_db = session.get(Order, 1)
        assert order_db.total_amount == so_migrated.total_amount

    # 4. Rerun migration (must be idempotent)
    with engine.begin() as conn:
        migrate_db(conn)

    with Session(engine) as session:
        so_rerun = session.get(SellerOrder, 1)
        assert so_rerun.subtotal == 250_000
        assert so_rerun.total_amount == 250_000
