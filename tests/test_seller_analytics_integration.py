"""Chrome -> production page -> FastAPI -> isolated SQLite; no canned API responses.

Runs against today's legacy API and automatically checks the financial contract after
#142 lands. Set ANALYTICS_REQUIRE_FINANCIAL=1 when verifying a #142 candidate so a
legacy response cannot accidentally count as financial integration evidence.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import Session
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import BUYER_ID, SELLER_ID, create_cart_engine

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
ORIGIN = "http://analytics.test"


@pytest.fixture(scope="module")
def analytics_browser():
    with sync_api.sync_playwright() as playwright:
        executable = os.environ.get("BROWSER_PATH")
        if not executable:
            executable = next(
                (
                    str(path)
                    for path in (
                        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
                    )
                    if path.is_file()
                ),
                None,
            )
        if executable:
            browser = playwright.chromium.launch(executable_path=executable)
        else:
            try:
                browser = playwright.chromium.launch()
            except sync_api.Error:
                browser = playwright.chromium.launch(channel="chrome")
        yield browser
        browser.close()


@pytest.fixture
def analytics_data(tmp_path):
    engine = create_cart_engine(tmp_path / "analytics-ui.db")
    with Session(engine) as session:
        session.add(User(id=4, name="Other seller", email="other-seller@test.local", role="seller"))
        session.flush()
        products = {}
        for code, seller in (("A", SELLER_ID), ("B", SELLER_ID), ("C", 4)):
            product = Product(
                code=f"A143-{code}",
                name=f"Analytics {code}",
                seller_id=seller,
                price=999999,
                stock_quantity=100,
            )
            session.add(product)
            session.flush()
            products[code] = product
        # 5 owned orders in range: gross 700k, completed 500k, pending 150k, cancelled 1/5.
        # Completed orders were created BEFORE the range; completion dates include them.
        rows = [
            ("A", "COMPLETED", 300000, 3, "2026-09-28", "2026-10-01", "RELEASED"),
            ("B", "COMPLETED", 200000, 1, "2026-09-29", "2026-10-02", "RELEASED"),
            ("A", "PENDING", 90000, 1, "2026-10-01", None, "HELD"),
            ("A", "RETURN_REQUESTED", 60000, 1, "2026-10-02", None, "PAUSED"),
            ("A", "CANCELLED", 50000, 1, "2026-10-02", None, "VOIDED"),
            ("A", "COMPLETED", 900000, 9, "2026-08-01", "2026-11-01", "RELEASED"),
            ("C", "COMPLETED", 9900000, 99, "2026-10-01", "2026-10-01", "RELEASED"),
        ]
        for code, status, amount, quantity, created, completed, escrow in rows:
            created_at = datetime.fromisoformat(created).replace(tzinfo=UTC)
            completed_at = (
                datetime.fromisoformat(completed).replace(tzinfo=UTC) if completed else None
            )
            order = Order(
                buyer_id=BUYER_ID,
                total_amount=amount,
                status=status,
                recipient_name="Test buyer",
                delivery_address="Test street",
                phone_number="0912345678",
                created_at=created_at,
                completed_at=completed_at,
                escrow_status=escrow,
            )
            session.add(order)
            session.flush()
            shop = SellerOrder(
                order_id=order.id,
                seller_id=products[code].seller_id,
                status=status,
                subtotal=amount,
                total_amount=amount,
                created_at=created_at,
                completed_at=completed_at,
                escrow_status=escrow,
            )
            session.add(shop)
            session.flush()
            session.add(
                OrderItem(
                    seller_order_id=shop.id,
                    product_id=products[code].id,
                    quantity=quantity,
                    unit_price=amount // quantity,
                )
            )
        session.commit()
        tokens = {
            role: create_access_token(session.get(User, user_id))
            for role, user_id in (("seller", SELLER_ID), ("buyer", BUYER_ID))
        }
    yield engine, tokens
    engine.dispose()


class AnalyticsSite:
    """Route browser HTTP calls through the actual ASGI app, preserving bearer auth."""

    def __init__(self, page, client):
        self.page, self.client = page, client
        self.queries = []
        self.summary = None
        page.route(f"{ORIGIN}/**", self.handle)

    def handle(self, route):
        url = urlsplit(route.request.url)
        response = self.client.get(
            url.path + (f"?{url.query}" if url.query else ""), headers=route.request.headers
        )
        if url.path.startswith("/api/v1/seller/analytics"):
            self.queries.append(url)
            assert response.status_code == 200, response.text
            if url.path == "/api/v1/seller/analytics":
                self.summary = response.json()
        route.fulfill(
            status=response.status_code, headers=dict(response.headers), body=response.content
        )

    def apply(self, start="2026-09-30", end="2026-10-02", group="day"):
        self.page.locator("#analytics-from").fill(start)
        self.page.locator("#analytics-to").fill(end)
        self.page.locator("#analytics-group").select_option(group)
        self.page.get_by_role("button", name="Apply filters").click()
        expect(self.page.locator("#analytics-report")).to_be_visible()
        expect(self.page.locator("#analytics-applied-range")).to_contain_text(f"{start} to {end}")


@pytest.fixture
def analytics_site(analytics_browser, analytics_data):
    engine, tokens = analytics_data
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        page = analytics_browser.new_page()
        page.add_init_script(f"localStorage.setItem('access_token', {tokens['seller']!r});")
        site = AnalyticsSite(page, client)
        page.goto(f"{ORIGIN}/seller/analytics")
        expect(page.locator("#analytics-report")).to_be_visible()
        yield site, tokens
        page.close()


@pytest.mark.parametrize("group,width", [("day", 390), ("month", 768), ("day", 1280)])
def test_dashboard_renders_real_backend_metrics_and_ranking(analytics_site, group, width):
    site, _ = analytics_site
    page = site.page
    page.set_viewport_size({"width": width, "height": 1000})
    site.apply(group=group)

    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    summary_query = next(
        url for url in reversed(site.queries) if url.path == "/api/v1/seller/analytics"
    )
    query = parse_qs(summary_query.query)
    assert query["from"] == query["from_date"] == ["2026-09-30"]
    assert query["to"] == query["to_date"] == ["2026-10-02"]
    assert query["period"] == ["daily" if group == "day" else "monthly"]
    assert query["group_by"] == [group]
    assert "seller_id" not in query
    expect(page.locator("#metric-completed_revenue")).to_have_text("500.000 VND")
    expect(page.locator("#analytics-chart svg")).to_be_visible()
    expect(page.locator("#analytics-date-basis")).to_contain_text(
        "completion date when available, otherwise creation date"
    )
    rows = page.locator("#analytics-ranking-body tr")
    expect(rows).to_have_count(2)
    assert rows.nth(0).locator("td").all_text_contents() == [
        "1",
        "Analytics A (A143-A)",
        "3",
        "300.000 VND",
    ]
    assert rows.nth(1).locator("td").all_text_contents() == [
        "2",
        "Analytics B (A143-B)",
        "1",
        "200.000 VND",
    ]
    financial = "gross_order_value" in site.summary["meta"]
    if os.environ.get("ANALYTICS_REQUIRE_FINANCIAL") == "1":
        assert financial, "This integration run requires the actual #142 financial API"
    if financial:
        assert site.summary["meta"]["cancellation_rate"] == 20
        for key, expected in (
            ("gross_order_value", "700.000 VND"),
            ("pending_escrow_revenue", "150.000 VND"),
            ("cancellation_rate", "20%"),
        ):
            expect(page.locator(f"#metric-{key}")).to_have_text(expected)
        expect(page.locator("#analytics-compatibility")).to_be_hidden()
        page.locator("#analytics-chart-metric").select_option("cancellation_rate")
        expect(page.locator("#analytics-values-body tr")).to_have_count(3 if group == "day" else 2)
        expect(page.locator("#analytics-values-body")).to_contain_text(
            "33.33%" if group == "day" else "20%"
        )
    else:
        for key in ("gross_order_value", "pending_escrow_revenue", "cancellation_rate"):
            expect(page.locator(f"#metric-{key}")).to_have_text("Not available")
        expect(page.locator("#completed-revenue-label")).to_contain_text("legacy")
        expect(page.locator("#analytics-compatibility")).to_be_visible()


def test_real_backend_empty_report_and_buyer_account_switch(analytics_site):
    site, tokens = analytics_site
    site.apply(start="2026-07-01", end="2026-07-02")
    expect(site.page.locator("#analytics-ranking-empty")).to_be_visible()
    expect(site.page.locator("#analytics-chart-empty")).to_be_visible()
    expect(site.page.locator("#metric-completed_revenue")).to_have_text("0 VND")
    sent = len(site.queries)
    site.page.evaluate(
        """token => {
        localStorage.setItem('access_token', token);
        window.dispatchEvent(new StorageEvent('storage', {key: 'access_token'}));
    }""",
        tokens["buyer"],
    )
    expect(site.page.locator("#analytics-error")).to_contain_text("Only active seller accounts")
    expect(site.page.locator("#analytics-report")).to_be_hidden()
    assert len(site.queries) == sent
