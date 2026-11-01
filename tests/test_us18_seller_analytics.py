"""Tests for US18 – Seller Analytics endpoints.

Covers:
  GET /api/v1/seller/analytics              — time-based revenue summary
  GET /api/v1/seller/analytics/best-sellers — top products
  GET /api/v1/seller/analytics/low-stock    — low stock alerts

Scenarios:
  1. Revenue summary grouping (daily / weekly / monthly)
  2. Best sellers ranked by units / revenue
  3. Low-stock alerts with configurable threshold
  4. Auth / access-control (seller-only)
  5. Edge cases: empty data, bad params
  6. Revenue period semantics: attribution to seller-order completion date

Isolation strategy
------------------
The fixture tracks the IDs of every row it inserts and deletes **only those
rows** in teardown — no wholesale DELETE on shared tables.  This guarantees
that other tests (or application data) running against the same in-memory
database are not affected.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, delete, select
from starlette.testclient import TestClient

from src.auth import create_access_token, hash_password
from src.database import engine
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE = "/api/v1/seller/analytics"

_US18_EMAILS = [
    "us18-seller@example.com",
    "us18-buyer@example.com",
    "us18-seller2@example.com",
]
_US18_CODE_PREFIX = "US18-"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_order(session, buyer_id, total, status, created_at):
    order = Order(
        buyer_id=buyer_id,
        total_amount=total,
        status=status,
        recipient_name="Test Buyer",
        delivery_address="123 Street",
        phone_number="0123456789",
        created_at=created_at,
    )
    session.add(order)
    session.flush()
    return order


def _make_seller_order(
    session,
    order_id,
    seller_id,
    status,
    created_at,
    completed_at=None,
    total_amount=0,
    escrow_status="HELD",
):
    if status == "COMPLETED" and completed_at is None:
        completed_at = created_at
    so = SellerOrder(
        order_id=order_id,
        seller_id=seller_id,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        total_amount=total_amount,
        escrow_status=escrow_status,
    )
    session.add(so)
    session.flush()
    return so


def _make_item(session, seller_order_id, product_id, qty, price):
    item = OrderItem(
        seller_order_id=seller_order_id,
        product_id=product_id,
        quantity=qty,
        unit_price=price,
    )
    session.add(item)
    return item


# ---------------------------------------------------------------------------
# Main fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def us18_data():
    """Insert isolated test rows; teardown deletes only those rows by ID.

    No wholesale DELETE is issued on shared tables, so parallel or sequential
    tests that touch the same tables are unaffected.
    """
    # ---- tracked IDs for targeted teardown --------------------------------
    order_ids: list[int] = []
    seller_order_ids: list[int] = []
    product_ids: list[int] = []
    user_ids: list[int] = []

    with Session(engine) as session:
        # Targeted pre-cleanup: remove any leftover rows from an interrupted run
        # safely in reverse foreign-key dependency order
        leftover_user_ids = session.exec(
            select(User.id).where(User.email.in_(_US18_EMAILS))
        ).all()
        if leftover_user_ids:
            leftover_orders = session.exec(
                select(Order.id).where(Order.buyer_id.in_(leftover_user_ids))
            ).all()
            leftover_sos = session.exec(
                select(SellerOrder.id).where(
                    (SellerOrder.seller_id.in_(leftover_user_ids))
                    | (SellerOrder.order_id.in_(leftover_orders))
                )
            ).all()
            if leftover_sos:
                session.exec(
                    delete(OrderHistory).where(
                        OrderHistory.seller_order_id.in_(leftover_sos)
                    )
                )
                session.exec(
                    delete(OrderItem).where(
                        OrderItem.seller_order_id.in_(leftover_sos)
                    )
                )
                session.exec(
                    delete(SellerOrder).where(SellerOrder.id.in_(leftover_sos))
                )
            if leftover_orders:
                session.exec(
                    delete(Notification).where(
                        Notification.order_id.in_(leftover_orders)
                    )
                )
                session.exec(
                    delete(Order).where(Order.id.in_(leftover_orders))
                )
            session.exec(
                delete(Product).where(Product.seller_id.in_(leftover_user_ids))
            )
            session.exec(
                delete(User).where(User.id.in_(leftover_user_ids))
            )

        leftover_prod_ids = session.exec(
            select(Product.id).where(Product.code.like(f"{_US18_CODE_PREFIX}%"))
        ).all()
        if leftover_prod_ids:
            session.exec(
                delete(OrderItem).where(
                    OrderItem.product_id.in_(leftover_prod_ids)
                )
            )
            session.exec(
                delete(Product).where(Product.id.in_(leftover_prod_ids))
            )
        session.commit()

        # --- users ---------------------------------------------------------
        seller = User(
            name="US18 Seller",
            email="us18-seller@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        seller2 = User(
            name="US18 Seller 2",
            email="us18-seller2@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer = User(
            name="US18 Buyer",
            email="us18-buyer@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add_all([seller, seller2, buyer])
        session.flush()
        user_ids.extend([seller.id, seller2.id, buyer.id])

        # --- products ------------------------------------------------------
        product_a = Product(
            code="US18-PA",
            seller_id=seller.id,
            name="Widget Alpha",
            price=100_000,
            stock_quantity=50,
            reserved_stock=0,
            is_active=True,
        )
        product_b = Product(
            code="US18-PB",
            seller_id=seller.id,
            name="Widget Beta",
            price=200_000,
            stock_quantity=3,
            reserved_stock=1,
            is_active=True,
        )
        # available_stock = 0  (stock=2, reserved=2)
        product_c = Product(
            code="US18-PC",
            seller_id=seller.id,
            name="Widget Gamma (out)",
            price=50_000,
            stock_quantity=2,
            reserved_stock=2,
            is_active=True,
        )
        # Inactive — must NOT appear in low-stock
        product_inactive = Product(
            code="US18-PD",
            seller_id=seller.id,
            name="Widget Inactive",
            price=10_000,
            stock_quantity=0,
            reserved_stock=0,
            is_active=False,
        )
        # Owned by seller2 — must NOT appear in seller's analytics
        product_other = Product(
            code="US18-PE",
            seller_id=seller2.id,
            name="Other Seller Widget",
            price=99_000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all(
            [product_a, product_b, product_c, product_inactive, product_other]
        )
        session.flush()
        product_ids.extend(
            [product_a.id, product_b.id, product_c.id,
             product_inactive.id, product_other.id]
        )

        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)

        # Order 1 (COMPLETED, today): 2×PA + 1×PB → revenue = 400 000
        o1 = _make_order(
            session, buyer.id,
            2 * product_a.price + product_b.price,
            "COMPLETED", today,
        )
        so1 = _make_seller_order(
            session, o1.id, seller.id, "COMPLETED", today, total_amount=400_000
        )
        _make_item(session, so1.id, product_a.id, 2, product_a.price)
        _make_item(session, so1.id, product_b.id, 1, product_b.price)
        order_ids.append(o1.id)
        seller_order_ids.append(so1.id)

        # Order 2 (COMPLETED, yesterday): 5×PA → revenue = 500 000
        o2 = _make_order(
            session, buyer.id,
            5 * product_a.price,
            "COMPLETED", yesterday,
        )
        so2 = _make_seller_order(
            session, o2.id, seller.id, "COMPLETED", yesterday, total_amount=500_000
        )
        _make_item(session, so2.id, product_a.id, 5, product_a.price)
        order_ids.append(o2.id)
        seller_order_ids.append(so2.id)

        # Order 3 (PENDING, today): 1×PA — must NOT count in revenue
        o3 = _make_order(
            session, buyer.id,
            product_a.price,
            "PENDING", today,
        )
        so3 = _make_seller_order(
            session, o3.id, seller.id, "PENDING", today, total_amount=100_000
        )
        _make_item(session, so3.id, product_a.id, 1, product_a.price)
        order_ids.append(o3.id)
        seller_order_ids.append(so3.id)

        session.commit()

        yield {
            "seller": seller,
            "seller2": seller2,
            "buyer": buyer,
            "product_a": product_a,
            "product_b": product_b,
            "product_c": product_c,
            "product_other": product_other,
            "order_ids": order_ids,
            "seller_order_ids": seller_order_ids,
            "product_ids": product_ids,
            "user_ids": user_ids,
        }

    # ---- targeted teardown (only rows we created) -------------------------
    with Session(engine) as session:
        session.exec(
            delete(OrderHistory).where(
                OrderHistory.seller_order_id.in_(seller_order_ids)
            )
        )
        session.exec(
            delete(Notification).where(
                Notification.order_id.in_(order_ids)
            )
        )
        session.exec(
            delete(OrderItem).where(
                OrderItem.seller_order_id.in_(seller_order_ids)
            )
        )
        session.exec(
            delete(SellerOrder).where(SellerOrder.id.in_(seller_order_ids))
        )
        session.exec(delete(Order).where(Order.id.in_(order_ids)))
        session.exec(
            delete(Product).where(Product.id.in_(product_ids))
        )
        session.exec(delete(User).where(User.id.in_(user_ids)))
        session.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _auth(seller: User) -> dict:
    token = create_access_token(seller)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Scenario 1 – Revenue analytics (time-based)
# ---------------------------------------------------------------------------


class TestRevenueAnalytics:
    """AC: Sellers can view revenue and order counts by day/week/month."""

    def test_returns_200_with_data_and_meta(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        resp = client.get(BASE, headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert isinstance(body["data"], list)

    def test_meta_contains_expected_keys(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(BASE, headers=_auth(seller)).json()
        meta = body["meta"]
        for key in (
            "from", "to", "period",
            "total_revenue", "total_orders", "total_items_sold",
        ):
            assert key in meta

    def test_daily_period_items_have_correct_fields(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}?period=daily", headers=_auth(seller)).json()
        if body["data"]:
            item = body["data"][0]
            for key in (
                "period", "period_start", "period_end",
                "revenue", "orders", "items_sold",
            ):
                assert key in item

    def test_weekly_period_accepted(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?period=weekly", headers=_auth(seller))
        assert resp.status_code == 200
        assert resp.json()["meta"]["period"] == "weekly"

    def test_monthly_period_accepted(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?period=monthly", headers=_auth(seller))
        assert resp.status_code == 200
        assert resp.json()["meta"]["period"] == "monthly"

    def test_group_by_returns_financial_metrics(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date().isoformat()
        response = client.get(
            f"{BASE}?from={today}&to={today}&group_by=daily",
            headers=_auth(seller),
        )
        assert response.status_code == 200
        body = response.json()
        bucket = body["data"][0]
        assert {
            "gross_order_value",
            "completed_revenue",
            "pending_escrow_revenue",
            "cancellation_rate",
        } <= bucket.keys()
        assert body["meta"]["group_by"] == "daily"

    def test_financial_metrics_have_expected_values(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date().isoformat()
        body = client.get(
            f"{BASE}?from={today}&to={today}&period=daily",
            headers=_auth(seller),
        ).json()
        bucket = body["data"][0]
        # Order 1: 400_000 (COMPLETED), Order 3: 100_000 (PENDING, HELD)
        assert bucket["gross_order_value"] == 500_000
        assert bucket["completed_revenue"] == 400_000
        assert bucket["pending_escrow_revenue"] == 100_000
        assert bucket["cancellation_rate"] == 0.0
        assert isinstance(bucket["cancellation_rate"], float)
        assert bucket["revenue"] == 400_000
        assert bucket["orders"] == 1
        assert bucket["items_sold"] == 3
        # Meta totals
        assert body["meta"]["gross_order_value"] == 500_000
        assert body["meta"]["completed_revenue"] == 400_000
        assert body["meta"]["pending_escrow_revenue"] == 100_000
        assert body["meta"]["cancellation_rate"] == 0.0
        assert isinstance(body["meta"]["cancellation_rate"], float)

    def test_zero_and_nonzero_cancellation_rate(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date().isoformat()
        # 1. Zero cancellation rate: 2 orders (1 completed, 1 pending) -> 0.0%
        body = client.get(
            f"{BASE}?from={today}&to={today}&period=daily",
            headers=_auth(seller),
        ).json()
        assert body["data"][0]["cancellation_rate"] == 0.0
        assert isinstance(body["data"][0]["cancellation_rate"], float)
        assert body["meta"]["cancellation_rate"] == 0.0
        assert isinstance(body["meta"]["cancellation_rate"], float)

        # 2. Non-zero cancellation rate: cancel 1 order -> 1 cancelled out of 2 = 50.0%
        seller_order_id = us18_data["seller_order_ids"][2]
        with Session(engine) as session:
            so = session.get(SellerOrder, seller_order_id)
            so.status = "CANCELLED"
            session.add(so)
            session.commit()
        try:
            body = client.get(
                f"{BASE}?from={today}&to={today}&period=daily",
                headers=_auth(seller),
            ).json()
            assert body["data"][0]["cancellation_rate"] == 50.0
            assert isinstance(body["data"][0]["cancellation_rate"], float)
            assert body["meta"]["cancellation_rate"] == 50.0
            assert isinstance(body["meta"]["cancellation_rate"], float)
        finally:
            with Session(engine) as session:
                so = session.get(SellerOrder, seller_order_id)
                so.status = "PENDING"
                session.add(so)
                session.commit()

    def test_escrow_handling_statuses(self, client: TestClient, us18_data):
        """Verify escrow revenue includes only uncompleted HELD/PAUSED orders."""
        seller = us18_data["seller"]
        buyer = us18_data["buyer"]
        now = datetime.now(UTC)
        today = now.date().isoformat()

        tracked_orders = []
        tracked_sos = []
        with Session(engine) as session:
            # 1. PROCESSING with PAUSED escrow -> included in pending escrow
            o_paused = _make_order(session, buyer.id, 120_000, "PROCESSING", now)
            so_paused = _make_seller_order(
                session,
                o_paused.id,
                seller.id,
                "PROCESSING",
                now,
                total_amount=120_000,
                escrow_status="PAUSED",
            )
            # 2. SHIPPED with RELEASED escrow -> excluded from pending escrow
            o_released = _make_order(session, buyer.id, 80_000, "SHIPPED", now)
            so_released = _make_seller_order(
                session,
                o_released.id,
                seller.id,
                "SHIPPED",
                now,
                total_amount=80_000,
                escrow_status="RELEASED",
            )
            # 3. CANCELLED with HELD escrow -> excluded from pending escrow
            o_cancelled = _make_order(session, buyer.id, 60_000, "CANCELLED", now)
            so_cancelled = _make_seller_order(
                session,
                o_cancelled.id,
                seller.id,
                "CANCELLED",
                now,
                total_amount=60_000,
                escrow_status="HELD",
            )
            session.commit()
            tracked_orders.extend([o_paused.id, o_released.id, o_cancelled.id])
            tracked_sos.extend([so_paused.id, so_released.id, so_cancelled.id])

        try:
            body = client.get(
                f"{BASE}?from={today}&to={today}&period=daily",
                headers=_auth(seller),
            ).json()
            bucket = body["data"][0]
            # Baseline pending was 100_000 (Order 3, HELD).
            # o_paused (120_000, PAUSED) is added -> 220_000
            # o_released (RELEASED) and o_cancelled (CANCELLED) are excluded.
            assert bucket["pending_escrow_revenue"] == 220_000
            # Gross order value includes all 5 orders: 500k + 120k + 80k + 60k = 760_000
            assert bucket["gross_order_value"] == 760_000
            # Cancellation rate: 1 cancelled out of 5 orders = 20.0%
            assert bucket["cancellation_rate"] == 20.0
        finally:
            with Session(engine) as session:
                session.exec(delete(SellerOrder).where(SellerOrder.id.in_(tracked_sos)))
                session.exec(delete(Order).where(Order.id.in_(tracked_orders)))
                session.commit()

    def test_weekly_metrics_use_the_weekly_bucket(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        body = client.get(
            f"{BASE}?period=weekly&from={monday}&to={sunday}",
            headers=_auth(seller),
        ).json()
        assert body["meta"]["group_by"] == "weekly"
        assert body["meta"]["period"] == "weekly"
        assert len(body["data"]) == 1
        bucket = body["data"][0]
        # Yesterday Order 2: 500k COMPLETED, Today Order 1: 400k COMPLETED, Order 3: 100k PENDING
        assert bucket["gross_order_value"] == 1_000_000
        assert bucket["completed_revenue"] == 900_000
        assert bucket["pending_escrow_revenue"] == 100_000
        assert bucket["revenue"] == 900_000
        assert bucket["orders"] == 2
        assert bucket["items_sold"] == 8
        assert bucket["cancellation_rate"] == 0.0
        assert body["meta"]["gross_order_value"] == 1_000_000
        assert body["meta"]["completed_revenue"] == 900_000
        assert body["meta"]["pending_escrow_revenue"] == 100_000

    def test_monthly_metrics_use_monthly_bucket(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        first_day = today.replace(day=1)
        # End of current month
        if today.month == 12:
            last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        body = client.get(
            f"{BASE}?period=monthly&from={first_day}&to={last_day}",
            headers=_auth(seller),
        ).json()
        assert body["meta"]["period"] == "monthly"
        assert body["meta"]["group_by"] == "monthly"
        bucket = next(b for b in body["data"] if b["period_start"] == first_day.isoformat())
        if today.day == 1:
            # On the 1st of the month, yesterday's Order 2 (500k) belongs to the previous month;
            # this month contains Order 1 (400k COMPLETED) and Order 3 (100k PENDING)
            assert bucket["gross_order_value"] == 500_000
            assert bucket["completed_revenue"] == 400_000
            assert bucket["pending_escrow_revenue"] == 100_000
            assert bucket["revenue"] == 400_000
            assert bucket["orders"] == 1
            assert bucket["items_sold"] == 3
            assert bucket["cancellation_rate"] == 0.0
        else:
            # Yesterday Order 2: 500k COMPLETED, Today Order 1: 400k COMPLETED,
            # Order 3: 100k PENDING
            assert bucket["gross_order_value"] == 1_000_000
            assert bucket["completed_revenue"] == 900_000
            assert bucket["pending_escrow_revenue"] == 100_000
            assert bucket["revenue"] == 900_000
            assert bucket["orders"] == 2
            assert bucket["items_sold"] == 8
            assert bucket["cancellation_rate"] == 0.0

    def test_seller_isolation_multiseller_data(self, client: TestClient, us18_data):
        """Seller A must not see Seller B's orders and Seller B must not see Seller A's."""
        seller1 = us18_data["seller"]
        seller2 = us18_data["seller2"]
        buyer = us18_data["buyer"]
        prod_other = us18_data["product_other"]
        today = datetime.now(UTC)
        today_date = today.date().isoformat()

        # Add an order for seller 2
        with Session(engine) as session:
            o2 = _make_order(session, buyer.id, 250_000, "COMPLETED", today)
            so2 = _make_seller_order(
                session, o2.id, seller2.id, "COMPLETED", today, total_amount=250_000
            )
            _make_item(session, so2.id, prod_other.id, 1, prod_other.price)
            session.commit()
            o2_id = o2.id
            so2_id = so2.id

        try:
            # Seller 1 views analytics: sees only own orders (Order 1: 400k, Order 3: 100k)
            r1 = client.get(
                f"{BASE}?from={today_date}&to={today_date}",
                headers=_auth(seller1),
            )
            b1 = r1.json()
            assert b1["meta"]["gross_order_value"] == 500_000
            assert b1["meta"]["completed_revenue"] == 400_000
            assert b1["meta"]["pending_escrow_revenue"] == 100_000
            assert b1["meta"]["total_revenue"] == 400_000

            # Seller 2 views analytics: sees only own order (250k)
            r2 = client.get(
                f"{BASE}?from={today_date}&to={today_date}",
                headers=_auth(seller2),
            )
            b2 = r2.json()
            assert b2["meta"]["gross_order_value"] == 250_000
            assert b2["meta"]["completed_revenue"] == 250_000
            assert b2["meta"]["pending_escrow_revenue"] == 0
            assert b2["meta"]["total_revenue"] == prod_other.price
        finally:
            with Session(engine) as session:
                session.exec(delete(OrderItem).where(OrderItem.seller_order_id == so2_id))
                session.exec(delete(SellerOrder).where(SellerOrder.id == so2_id))
                session.exec(delete(Order).where(Order.id == o2_id))
                session.commit()

    def test_invalid_group_by_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        response = client.get(
            f"{BASE}?group_by=yearly",
            headers=_auth(seller),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "ERR_INVALID_GROUPING"

    def test_date_range_exceeding_731_days_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?from=2020-01-01&to=2025-01-01", headers=_auth(seller))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "ERR_INVALID_DATE_RANGE"

    def test_invalid_period_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?period=yearly", headers=_auth(seller))
        assert resp.status_code == 400

    def test_only_completed_orders_counted(
        self, client: TestClient, us18_data
    ):
        """PENDING orders must not inflate the revenue figures."""
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        from_str = today.isoformat()
        body = client.get(
            f"{BASE}?period=daily&from={from_str}&to={from_str}",
            headers=_auth(seller),
        ).json()
        today_bucket = next(
            (b for b in body["data"] if b["period_start"] == from_str), None
        )
        # Order 1 (COMPLETED, today): 2×100k + 1×200k = 400k
        # Order 3 (PENDING, today):  1×100k — must NOT be counted
        assert today_bucket is not None
        assert today_bucket["revenue"] == 400_000
        assert today_bucket["orders"] == 1

    def test_date_range_filter_works(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        body = client.get(
            f"{BASE}?period=daily&from={yesterday}&to={yesterday}",
            headers=_auth(seller),
        ).json()
        assert len(body["data"]) == 1
        # Order 2 (COMPLETED, yesterday): 5×100k = 500k
        assert body["data"][0]["revenue"] == 500_000

    def test_from_after_to_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(
            f"{BASE}?from=2025-12-31&to=2025-01-01",
            headers=_auth(seller),
        )
        assert resp.status_code == 400

    def test_invalid_date_format_returns_400(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?from=not-a-date", headers=_auth(seller))
        assert resp.status_code == 400

    def test_total_revenue_sums_all_periods(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)
        body = client.get(
            f"{BASE}?period=daily"
            f"&from={yesterday.isoformat()}&to={today.isoformat()}",
            headers=_auth(seller),
        ).json()
        period_sum = sum(b["revenue"] for b in body["data"])
        assert body["meta"]["total_revenue"] == period_sum


# ---------------------------------------------------------------------------
# Scenario 2 – Best sellers
# ---------------------------------------------------------------------------


class TestBestSellers:
    """AC: Sellers can view their top-selling products in a period."""

    def test_returns_200_with_data_and_meta(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}/best-sellers", headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

    def test_item_fields_present(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers", headers=_auth(seller)
        ).json()
        if body["data"]:
            item = body["data"][0]
            for key in (
                "product_id", "product_code", "product_name",
                "units_sold", "revenue",
            ):
                assert key in item

    def test_sorted_by_units_by_default(self, client: TestClient, us18_data):
        """product_a: 7 units (5+2) > product_b: 1 unit."""
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers?sort_by=units", headers=_auth(seller)
        ).json()
        codes = [item["product_code"] for item in body["data"]]
        assert codes.index("US18-PA") < codes.index("US18-PB")

    def test_sorted_by_revenue(self, client: TestClient, us18_data):
        """PA: 7×100k=700k, PB: 1×200k=200k → PA leads by revenue."""
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers?sort_by=revenue", headers=_auth(seller)
        ).json()
        codes = [item["product_code"] for item in body["data"]]
        assert codes.index("US18-PA") < codes.index("US18-PB")

    def test_limit_respected(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers?limit=1", headers=_auth(seller)
        ).json()
        assert len(body["data"]) <= 1

    def test_invalid_sort_by_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(
            f"{BASE}/best-sellers?sort_by=random", headers=_auth(seller)
        )
        assert resp.status_code == 400

    def test_does_not_include_other_sellers_products(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers", headers=_auth(seller)
        ).json()
        codes = [item["product_code"] for item in body["data"]]
        assert "US18-PE" not in codes

    def test_pending_orders_not_counted(self, client: TestClient, us18_data):
        """Total units for PA = 2+5 = 7, not 8 (the PENDING order's qty)."""
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers", headers=_auth(seller)
        ).json()
        pa = next(
            (i for i in body["data"] if i["product_code"] == "US18-PA"), None
        )
        assert pa is not None
        assert pa["units_sold"] == 7

    def test_meta_contains_sort_and_limit(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers?sort_by=revenue&limit=5",
            headers=_auth(seller),
        ).json()
        assert body["meta"]["sort_by"] == "revenue"
        assert body["meta"]["limit"] == 5


# ---------------------------------------------------------------------------
# Scenario 3 – Low-stock alerts
# ---------------------------------------------------------------------------


class TestLowStockAlerts:
    """AC: Sellers can see products approaching zero available stock."""

    def test_returns_200_with_data_and_meta(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}/low-stock", headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

    def test_item_fields_present(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock", headers=_auth(seller)
        ).json()
        if body["data"]:
            item = body["data"][0]
            for key in (
                "product_id", "product_code", "product_name",
                "stock_quantity", "reserved_stock", "available_stock",
            ):
                assert key in item

    def test_available_stock_is_correct(self, client: TestClient, us18_data):
        """available_stock = stock_quantity - reserved_stock."""
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock", headers=_auth(seller)
        ).json()
        for item in body["data"]:
            assert (
                item["available_stock"]
                == item["stock_quantity"] - item["reserved_stock"]
            )

    def test_default_threshold_is_five(self, client: TestClient, us18_data):
        """Products with available_stock > 5 must not appear."""
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock", headers=_auth(seller)
        ).json()
        for item in body["data"]:
            assert item["available_stock"] <= 5

    def test_custom_threshold(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        # threshold=0: only PC (available=0); PB (available=2) excluded
        body_t0 = client.get(
            f"{BASE}/low-stock?threshold=0", headers=_auth(seller)
        ).json()
        codes_t0 = {i["product_code"] for i in body_t0["data"]}
        assert "US18-PC" in codes_t0
        assert "US18-PB" not in codes_t0

        # threshold=2: both PC (0) and PB (2) included
        body_t2 = client.get(
            f"{BASE}/low-stock?threshold=2", headers=_auth(seller)
        ).json()
        codes_t2 = {i["product_code"] for i in body_t2["data"]}
        assert "US18-PC" in codes_t2
        assert "US18-PB" in codes_t2

    def test_inactive_products_excluded(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock?threshold=100", headers=_auth(seller)
        ).json()
        codes = {i["product_code"] for i in body["data"]}
        assert "US18-PD" not in codes  # is_active=False

    def test_other_seller_products_excluded(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock?threshold=1000", headers=_auth(seller)
        ).json()
        codes = {i["product_code"] for i in body["data"]}
        assert "US18-PE" not in codes  # owned by seller2

    def test_results_ordered_by_available_stock_ascending(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock?threshold=5", headers=_auth(seller)
        ).json()
        stocks = [item["available_stock"] for item in body["data"]]
        assert stocks == sorted(stocks)

    def test_threshold_zero_shows_only_zero_available(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock?threshold=0", headers=_auth(seller)
        ).json()
        for item in body["data"]:
            assert item["available_stock"] == 0

    def test_meta_contains_threshold_and_count(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/low-stock?threshold=3", headers=_auth(seller)
        ).json()
        assert body["meta"]["threshold"] == 3
        assert body["meta"]["count"] == len(body["data"])


# ---------------------------------------------------------------------------
# Scenario 4 – Authentication & Access Control
# ---------------------------------------------------------------------------


class TestAuthAndAccess:
    """AC: These endpoints are seller-only."""

    def test_no_token_returns_401(self, client: TestClient, us18_data):
        paths = [BASE, f"{BASE}/best-sellers", f"{BASE}/low-stock"]
        for path in paths:
            resp = client.get(path)
            assert resp.status_code == 401, f"Expected 401 on {path}"

    def test_buyer_token_returns_403(self, client: TestClient, us18_data):
        buyer = us18_data["buyer"]
        token = create_access_token(buyer)
        headers = {"Authorization": f"Bearer {token}"}
        paths = [BASE, f"{BASE}/best-sellers", f"{BASE}/low-stock"]
        for path in paths:
            resp = client.get(path, headers=headers)
            assert resp.status_code == 403, f"Expected 403 on {path}"

    def test_seller2_sees_only_own_data(
        self, client: TestClient, us18_data
    ):
        """seller2 has no completed orders; all endpoints return zero/empty."""
        seller2 = us18_data["seller2"]
        headers = _auth(seller2)
        body = client.get(BASE, headers=headers).json()
        assert body["meta"]["total_revenue"] == 0
        body = client.get(f"{BASE}/best-sellers", headers=headers).json()
        assert body["data"] == []
        # seller2's only product has available_stock=10 > default threshold 5
        body = client.get(f"{BASE}/low-stock", headers=headers).json()
        assert body["data"] == []


# ---------------------------------------------------------------------------
# Scenario 5 – Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """AC: Handle boundary conditions gracefully."""

    def test_analytics_no_orders_returns_zero_totals(
        self, client: TestClient, us18_data
    ):
        seller2 = us18_data["seller2"]
        body = client.get(BASE, headers=_auth(seller2)).json()
        assert body["meta"]["total_revenue"] == 0
        assert body["meta"]["total_orders"] == 0
        assert body["meta"]["total_items_sold"] == 0

    def test_best_sellers_no_orders_returns_empty(
        self, client: TestClient, us18_data
    ):
        seller2 = us18_data["seller2"]
        body = client.get(
            f"{BASE}/best-sellers", headers=_auth(seller2)
        ).json()
        assert body["data"] == []

    def test_low_stock_no_products_returns_empty(
        self, client: TestClient, us18_data
    ):
        """seller2's only product has available_stock=10 > threshold 5."""
        seller2 = us18_data["seller2"]
        body = client.get(
            f"{BASE}/low-stock", headers=_auth(seller2)
        ).json()
        assert body["data"] == []

    def test_limit_1_returns_at_most_one_best_seller(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}/best-sellers?limit=1", headers=_auth(seller)
        ).json()
        assert len(body["data"]) <= 1

    def test_analytics_future_date_range_returns_zero_revenue(
        self, client: TestClient, us18_data
    ):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}?from=2099-01-01&to=2099-12-31",
            headers=_auth(seller),
        ).json()
        assert body["meta"]["total_revenue"] == 0


# ---------------------------------------------------------------------------
# Scenario 6 – Revenue period semantics
# ---------------------------------------------------------------------------


class TestRevenuePeriodSemantics:
    """Confirm revenue is attributed to SellerOrder.completed_at (completion date).

    Design specification (docs/design.md line 300 & BR7 / BR10):
    -------------------------------------------------------------
    "The selected analytics period is evaluated using seller_orders.completed_at,
    not the original marketplace order creation timestamp."

    Revenue is recognised upon order fulfillment/completion (when the seller
    completes the order), not when the order is initially placed. This prevents
    retroactively modifying past closed periods when in-flight orders complete
    later.

    The test below creates an order placed yesterday and completed today,
    verifying that the revenue appears in today's bucket (completion period)
    and NOT in yesterday's bucket.
    """

    def test_revenue_attributed_to_order_completion_date(
        self, client: TestClient, us18_data
    ):
        """An order placed yesterday and completed today must land in today's bucket."""
        seller = us18_data["seller"]
        buyer = us18_data["buyer"]
        product_a = us18_data["product_a"]

        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)

        tracked_so_ids: list[int] = []
        tracked_order_ids: list[int] = []

        with Session(engine) as session:
            # Order placed yesterday, completed today
            order = _make_order(
                session, buyer.id, 3 * product_a.price, "COMPLETED", yesterday
            )
            so = _make_seller_order(
                session,
                order.id,
                seller.id,
                "COMPLETED",
                yesterday,
                completed_at=today,
            )
            _make_item(session, so.id, product_a.id, 3, product_a.price)
            session.commit()
            tracked_order_ids.append(order.id)
            tracked_so_ids.append(so.id)

        try:
            from_str = yesterday.date().isoformat()
            to_str = today.date().isoformat()
            body = client.get(
                f"{BASE}?period=daily&from={from_str}&to={to_str}",
                headers=_auth(seller),
            ).json()

            yesterday_bucket = next(
                (b for b in body["data"] if b["period_start"] == from_str),
                None,
            )
            today_bucket = next(
                (b for b in body["data"] if b["period_start"] == to_str),
                None,
            )

            # Revenue from this order (3×100k = 300k) must appear in
            # today's bucket (completed_at), NOT yesterday's bucket.
            assert yesterday_bucket is not None
            # yesterday only had order 2 (500k) from the fixture
            assert yesterday_bucket["revenue"] == 500_000

            assert today_bucket is not None
            # today had order 1 (400k) + this order completed today (300k) = 700k
            assert today_bucket["revenue"] == 700_000

        finally:
            with Session(engine) as session:
                session.exec(
                    delete(OrderItem).where(
                        OrderItem.seller_order_id.in_(tracked_so_ids)
                    )
                )
                session.exec(
                    delete(SellerOrder).where(
                        SellerOrder.id.in_(tracked_so_ids)
                    )
                )
                session.exec(
                    delete(Order).where(Order.id.in_(tracked_order_ids))
                )
                session.commit()
