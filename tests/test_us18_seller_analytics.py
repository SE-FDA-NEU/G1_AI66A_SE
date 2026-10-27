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
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, delete
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
# Fixtures
# ---------------------------------------------------------------------------

BASE = "/api/v1/seller/analytics"


@pytest.fixture()
def us18_data():
    """Create an isolated seller, buyer, products and completed orders for testing."""
    with Session(engine) as session:
        # Clean up in dependency order
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(Product).where(Product.code.like("US18-%")))
        session.exec(
            delete(User).where(
                User.email.in_([
                    "us18-seller@example.com",
                    "us18-buyer@example.com",
                    "us18-seller2@example.com",
                ])
            )
        )

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

        # Products for seller
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
        # Low stock product (available = 0)
        product_c = Product(
            code="US18-PC",
            seller_id=seller.id,
            name="Widget Gamma (out)",
            price=50_000,
            stock_quantity=2,
            reserved_stock=2,
            is_active=True,
        )
        # Inactive product — should NOT appear in low-stock
        product_inactive = Product(
            code="US18-PD",
            seller_id=seller.id,
            name="Widget Inactive",
            price=10_000,
            stock_quantity=0,
            reserved_stock=0,
            is_active=False,
        )
        # Product owned by seller2 — must NOT appear in seller's analytics
        product_other = Product(
            code="US18-PE",
            seller_id=seller2.id,
            name="Other Seller Widget",
            price=99_000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([product_a, product_b, product_c, product_inactive, product_other])
        session.flush()

        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)

        def _make_completed_order(order_date, items):
            """Helper: create an Order + SellerOrder(COMPLETED) + OrderItems."""
            order = Order(
                buyer_id=buyer.id,
                total_amount=sum(q * p for q, p in items),
                status="COMPLETED",
                recipient_name="Test Buyer",
                delivery_address="123 Street",
                phone_number="0123456789",
                created_at=order_date,
            )
            session.add(order)
            session.flush()
            so = SellerOrder(
                order_id=order.id,
                seller_id=seller.id,
                status="COMPLETED",
                created_at=order_date,
            )
            session.add(so)
            session.flush()
            for (qty, price), prod in zip(items, [product_a, product_b]):
                session.add(
                    OrderItem(
                        seller_order_id=so.id,
                        product_id=prod.id,
                        quantity=qty,
                        unit_price=price,
                    )
                )
            return order, so

        # Order 1: today, 2× product_a + 1× product_b
        _make_completed_order(today, [(2, product_a.price), (1, product_b.price)])
        # Order 2: yesterday, 5× product_a
        _make_completed_order(yesterday, [(5, product_a.price)])

        # PENDING order (should NOT count in revenue)
        pending_order = Order(
            buyer_id=buyer.id,
            total_amount=product_a.price,
            status="PENDING",
            recipient_name="Test Buyer",
            delivery_address="123 Street",
            phone_number="0123456789",
            created_at=today,
        )
        session.add(pending_order)
        session.flush()
        pending_so = SellerOrder(
            order_id=pending_order.id,
            seller_id=seller.id,
            status="PENDING",
        )
        session.add(pending_so)
        session.flush()
        session.add(
            OrderItem(
                seller_order_id=pending_so.id,
                product_id=product_a.id,
                quantity=1,
                unit_price=product_a.price,
            )
        )

        session.commit()

        yield {
            "seller": seller,
            "seller2": seller2,
            "buyer": buyer,
            "product_a": product_a,
            "product_b": product_b,
            "product_c": product_c,
        }

    # Teardown
    with Session(engine) as session:
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(Product).where(Product.code.like("US18-%")))
        session.exec(
            delete(User).where(
                User.email.in_([
                    "us18-seller@example.com",
                    "us18-buyer@example.com",
                    "us18-seller2@example.com",
                ])
            )
        )
        session.commit()


def _seller_token(seller: User) -> str:
    return create_access_token(seller)


def _auth(seller: User) -> dict:
    return {"Authorization": f"Bearer {_seller_token(seller)}"}


# ---------------------------------------------------------------------------
# Scenario 1 – Revenue analytics (time-based)
# ---------------------------------------------------------------------------


class TestRevenueAnalytics:
    """AC: Sellers can view revenue and order counts by day/week/month."""

    def test_returns_200_with_data_and_meta(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(BASE, headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert isinstance(body["data"], list)

    def test_meta_contains_expected_keys(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(BASE, headers=_auth(seller)).json()
        meta = body["meta"]
        assert "from" in meta
        assert "to" in meta
        assert "period" in meta
        assert "total_revenue" in meta
        assert "total_orders" in meta
        assert "total_items_sold" in meta

    def test_daily_period_items_have_correct_fields(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}?period=daily", headers=_auth(seller)).json()
        if body["data"]:
            item = body["data"][0]
            for key in ("period", "period_start", "period_end", "revenue", "orders", "items_sold"):
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

    def test_invalid_period_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?period=yearly", headers=_auth(seller))
        assert resp.status_code == 400

    def test_only_completed_orders_counted(self, client: TestClient, us18_data):
        """PENDING orders must not inflate the revenue figures."""
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        from_str = today.isoformat()
        to_str = today.isoformat()
        body = client.get(
            f"{BASE}?period=daily&from={from_str}&to={to_str}",
            headers=_auth(seller),
        ).json()
        today_bucket = next(
            (b for b in body["data"] if b["period_start"] == from_str), None
        )
        # Today: order 1 = 2×100k + 1×200k = 400k (COMPLETED)
        # PENDING order has 1×100k but must NOT be counted
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
        # Yesterday: 5×100k = 500k
        assert body["data"][0]["revenue"] == 500_000

    def test_from_after_to_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?from=2025-12-31&to=2025-01-01", headers=_auth(seller))
        assert resp.status_code == 400

    def test_invalid_date_format_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}?from=not-a-date", headers=_auth(seller))
        assert resp.status_code == 400

    def test_total_revenue_sums_all_periods(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)
        body = client.get(
            f"{BASE}?period=daily&from={yesterday.isoformat()}&to={today.isoformat()}",
            headers=_auth(seller),
        ).json()
        period_sum = sum(b["revenue"] for b in body["data"])
        assert body["meta"]["total_revenue"] == period_sum


# ---------------------------------------------------------------------------
# Scenario 2 – Best sellers
# ---------------------------------------------------------------------------


class TestBestSellers:
    """AC: Sellers can view their top-selling products in a period."""

    def test_returns_200_with_data_and_meta(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}/best-sellers", headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

    def test_item_fields_present(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers", headers=_auth(seller)).json()
        if body["data"]:
            item = body["data"][0]
            for key in ("product_id", "product_code", "product_name", "units_sold", "revenue"):
                assert key in item

    def test_sorted_by_units_by_default(self, client: TestClient, us18_data):
        """product_a: 7 units total (5+2) > product_b: 1 unit."""
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers?sort_by=units", headers=_auth(seller)).json()
        codes = [item["product_code"] for item in body["data"]]
        assert codes.index("US18-PA") < codes.index("US18-PB")

    def test_sorted_by_revenue(self, client: TestClient, us18_data):
        """product_a: 7×100k = 700k, product_b: 1×200k = 200k → PA leads by revenue too."""
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers?sort_by=revenue", headers=_auth(seller)).json()
        codes = [item["product_code"] for item in body["data"]]
        assert codes.index("US18-PA") < codes.index("US18-PB")

    def test_limit_respected(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers?limit=1", headers=_auth(seller)).json()
        assert len(body["data"]) <= 1

    def test_invalid_sort_by_returns_400(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}/best-sellers?sort_by=random", headers=_auth(seller))
        assert resp.status_code == 400

    def test_does_not_include_other_sellers_products(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers", headers=_auth(seller)).json()
        codes = [item["product_code"] for item in body["data"]]
        assert "US18-PE" not in codes

    def test_pending_orders_not_counted(self, client: TestClient, us18_data):
        """Total units for PA = 2+5 = 7, not 8 (the PENDING order's qty)."""
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers", headers=_auth(seller)).json()
        pa = next((i for i in body["data"] if i["product_code"] == "US18-PA"), None)
        assert pa is not None
        assert pa["units_sold"] == 7

    def test_meta_contains_sort_and_limit(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers?sort_by=revenue&limit=5", headers=_auth(seller)).json()
        assert body["meta"]["sort_by"] == "revenue"
        assert body["meta"]["limit"] == 5


# ---------------------------------------------------------------------------
# Scenario 3 – Low-stock alerts
# ---------------------------------------------------------------------------


class TestLowStockAlerts:
    """AC: Sellers can see products approaching zero available stock."""

    def test_returns_200_with_data_and_meta(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        resp = client.get(f"{BASE}/low-stock", headers=_auth(seller))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

    def test_item_fields_present(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock", headers=_auth(seller)).json()
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
        body = client.get(f"{BASE}/low-stock", headers=_auth(seller)).json()
        for item in body["data"]:
            assert item["available_stock"] == item["stock_quantity"] - item["reserved_stock"]

    def test_default_threshold_is_five(self, client: TestClient, us18_data):
        """Products with available_stock > 5 must not appear."""
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock", headers=_auth(seller)).json()
        for item in body["data"]:
            assert item["available_stock"] <= 5

    def test_custom_threshold(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        # product_b has available=2, product_c has available=0
        body_t0 = client.get(f"{BASE}/low-stock?threshold=0", headers=_auth(seller)).json()
        codes_t0 = {i["product_code"] for i in body_t0["data"]}
        assert "US18-PC" in codes_t0   # available = 0
        assert "US18-PB" not in codes_t0   # available = 2 > 0

        body_t2 = client.get(f"{BASE}/low-stock?threshold=2", headers=_auth(seller)).json()
        codes_t2 = {i["product_code"] for i in body_t2["data"]}
        assert "US18-PC" in codes_t2
        assert "US18-PB" in codes_t2   # available = 2 ≤ 2

    def test_inactive_products_excluded(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock?threshold=100", headers=_auth(seller)).json()
        codes = {i["product_code"] for i in body["data"]}
        assert "US18-PD" not in codes   # is_active=False

    def test_other_seller_products_excluded(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock?threshold=1000", headers=_auth(seller)).json()
        codes = {i["product_code"] for i in body["data"]}
        assert "US18-PE" not in codes   # owned by seller2

    def test_results_ordered_by_available_stock_ascending(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock?threshold=5", headers=_auth(seller)).json()
        stocks = [item["available_stock"] for item in body["data"]]
        assert stocks == sorted(stocks)

    def test_threshold_zero_shows_only_zero_available(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock?threshold=0", headers=_auth(seller)).json()
        for item in body["data"]:
            assert item["available_stock"] == 0

    def test_meta_contains_threshold_and_count(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/low-stock?threshold=3", headers=_auth(seller)).json()
        assert body["meta"]["threshold"] == 3
        assert body["meta"]["count"] == len(body["data"])


# ---------------------------------------------------------------------------
# Scenario 4 – Authentication & Access Control
# ---------------------------------------------------------------------------


class TestAuthAndAccess:
    """AC: These endpoints are seller-only."""

    def test_no_token_returns_401(self, client: TestClient, us18_data):
        for path in [BASE, f"{BASE}/best-sellers", f"{BASE}/low-stock"]:
            resp = client.get(path)
            assert resp.status_code == 401, f"Expected 401 on {path}"

    def test_buyer_token_returns_403(self, client: TestClient, us18_data):
        buyer = us18_data["buyer"]
        token = create_access_token(buyer)
        headers = {"Authorization": f"Bearer {token}"}
        for path in [BASE, f"{BASE}/best-sellers", f"{BASE}/low-stock"]:
            resp = client.get(path, headers=headers)
            assert resp.status_code == 403, f"Expected 403 on {path}"

    def test_seller2_sees_only_own_data(self, client: TestClient, us18_data):
        """seller2 has no orders or low-stock products; endpoints must return empty data."""
        seller2 = us18_data["seller2"]
        headers = _auth(seller2)
        # Revenue
        body = client.get(BASE, headers=headers).json()
        assert body["meta"]["total_revenue"] == 0
        # Best sellers
        body = client.get(f"{BASE}/best-sellers", headers=headers).json()
        assert body["data"] == []
        # Low stock — seller2 has product_other (available=10) which is > threshold 5
        body = client.get(f"{BASE}/low-stock", headers=headers).json()
        assert body["data"] == []


# ---------------------------------------------------------------------------
# Scenario 5 – Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """AC: Handle boundary conditions gracefully."""

    def test_analytics_no_orders_returns_zero_totals(self, client: TestClient, us18_data):
        seller2 = us18_data["seller2"]
        body = client.get(BASE, headers=_auth(seller2)).json()
        assert body["meta"]["total_revenue"] == 0
        assert body["meta"]["total_orders"] == 0
        assert body["meta"]["total_items_sold"] == 0

    def test_best_sellers_no_orders_returns_empty(self, client: TestClient, us18_data):
        seller2 = us18_data["seller2"]
        body = client.get(f"{BASE}/best-sellers", headers=_auth(seller2)).json()
        assert body["data"] == []

    def test_low_stock_no_products_returns_empty(self, client: TestClient, us18_data):
        """seller2 only has product_other with available_stock=10 > default threshold 5."""
        seller2 = us18_data["seller2"]
        body = client.get(f"{BASE}/low-stock", headers=_auth(seller2)).json()
        assert body["data"] == []

    def test_limit_1_returns_at_most_one_best_seller(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(f"{BASE}/best-sellers?limit=1", headers=_auth(seller)).json()
        assert len(body["data"]) <= 1

    def test_analytics_future_date_range_returns_zero_revenue(self, client: TestClient, us18_data):
        seller = us18_data["seller"]
        body = client.get(
            f"{BASE}?from=2099-01-01&to=2099-12-31",
            headers=_auth(seller),
        ).json()
        assert body["meta"]["total_revenue"] == 0
