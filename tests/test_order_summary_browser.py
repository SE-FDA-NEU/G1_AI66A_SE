"""Issue #159: production order page, real API and isolated persisted receipts."""

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from sqlmodel import Session

from src.models.cart_item import CartItem
from src.models.order import Order
from tests import test_atomic_cancellation as cancellation
from tests.cart_db import BUYER_ID, add_product, change_product
from tests.test_checkout import headers
from tests.test_checkout_vouchers import add_voucher, place, quote, seed_example

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
api = cancellation.api
engine = cancellation.engine
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://order-summary.test"
PLACED_AT = datetime(2026, 1, 2, 15, 4, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        executable = os.environ.get("BROWSER_PATH")
        if executable:
            value = playwright.chromium.launch(executable_path=executable)
        else:
            try:
                value = playwright.chromium.launch()
            except sync_api.Error:
                value = playwright.chromium.launch(channel="chrome")
        yield value
        value.close()


def checkout_quote(api, engine, codes, key):
    response = quote(api, engine, codes)
    assert response.status_code == 200, response.text
    response = place(
        api,
        engine,
        codes | {"quote_revision": response.json()["data"]["quote_revision"]},
        key=key,
    )
    assert response.status_code == 201, response.text
    order_id = response.json()["data"]["id"]
    with Session(engine) as session:
        session.get(Order, order_id).created_at = PLACED_AT
        session.commit()
    return order_id


def discounted_order(api, engine):
    seed_example(engine)
    change_product(engine, "VOU-A", image_url=None)
    change_product(engine, "VOU-B", image_url=None)
    return checkout_quote(api, engine, {
        "shop_vouchers": [{"seller_id": 1, "code": "SHOPA30K"}],
        "platform_voucher": "PLAT10",
        "shipping_voucher": "FREESHIP15",
    }, "summary-discounted")


def plain_order(api, engine):
    product_id = add_product(engine, "SUMMARY-PLAIN", price=70_000)
    with Session(engine) as session:
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=1))
        session.commit()
    response = place(api, engine, {}, key="summary-plain")
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


class OrderPage:
    """Intercept only transport; requests still reach the production FastAPI handlers."""

    def __init__(self, browser, api, engine, *, width=1280, buyer_id=BUYER_ID):
        self.api = api
        self.fail_detail = False
        self.errors = []
        self.context = browser.new_context(
            viewport={"width": width, "height": 900},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="en-GB",
        )
        token = headers(engine, buyer_id)["Authorization"].removeprefix("Bearer ")
        self.context.add_init_script(f"localStorage.setItem('access_token', '{token}')")
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/*", self.handle)
        self.page.set_default_timeout(5000)

    def handle(self, route):
        url = urlsplit(route.request.url)
        if url.netloc != urlsplit(ORIGIN).netloc:
            route.abort()
            return
        if self.fail_detail and url.path.startswith("/api/v1/orders/"):
            route.fulfill(status=503, json={"error": {"message": "Temporarily unavailable"}})
            return
        response = self.api.request(
            route.request.method,
            url.path + (f"?{url.query}" if url.query else ""),
            headers={
                key: value for key, value in route.request.headers.items()
                if key.lower() in {"authorization", "content-type"}
            },
            content=route.request.post_data,
        )
        route.fulfill(
            status=response.status_code,
            body=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    def open(self, order_id):
        self.page.goto(f"{ORIGIN}/order/{order_id}")

    def close(self):
        self.context.close()


def assert_money(page, selector, amount):
    # Independent expected amount; let the browser supply only locale separators.
    expected = page.evaluate(
        "amount => new Intl.NumberFormat('vi-VN', {style:'currency', currency:'VND'})"
        ".format(amount)", amount,
    )
    expect(page.locator(selector)).to_have_text(expected)


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_persisted_date_time_and_multishop_price_breakdown(browser, api, engine, width):
    order_id = discounted_order(api, engine)
    change_product(engine, "VOU-A", price=999_999, name="Edited after purchase")
    receipt = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine)).json()["data"]
    view = OrderPage(browser, api, engine, width=width)
    try:
        view.open(order_id)
        page = view.page
        expect(page.locator("#summary-metrics-bar")).to_be_visible()
        expect(page.locator("#badge-payment-method")).to_have_text("Payment: Cash on delivery")
        expect(page.locator("#badge-payment-status")).to_have_text(
            "Payment status: Awaiting payment",
        )
        expect(page.locator("#order-placed-val")).to_contain_text("22:04")
        expect(page.locator("#order-placed-val")).to_contain_text("2026")
        expect(page.locator("#order-placed-val")).to_contain_text("GMT+7")
        expect(page.locator("#order-placed-val")).to_have_attribute(
            "datetime", receipt["created_at"],
        )
        for selector, amount in {
            "#order-total-val": 433_000,
            "#order-total": 433_000,
            "#order-subtotal": 500_000,
            "#order-shop-discount": -30_000,
            "#order-platform-discount": -47_000,
            "#order-shipping-fee": 40_000,
            "#order-shipping-discount": -30_000,
        }.items():
            assert_money(page, selector, amount)
        expect(page.locator("#order-price-breakdown")).to_be_visible()
        expect(page.locator("#order-breakdown-unavailable")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert view.errors == []
        if os.environ.get("UPDATE_ORDER_SUMMARY_SCREENSHOTS") == "1" and width != 768:
            directory = ROOT / "docs/images/order-summary"
            directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(directory / f"summary-{width}.png"), full_page=True)
        page.reload()
        expect(page.locator("#order-placed-val")).to_contain_text("22:04")
        assert_money(page, "#order-total", 433_000)
    finally:
        view.close()


def test_zero_total_is_displayed_without_replacing_it_with_item_subtotal(browser, api, engine):
    product_id = add_product(engine, "SUMMARY-FREE", price=50_000)
    with Session(engine) as session:
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=1))
        session.commit()
    add_voucher(engine, "FREEITEM", discount_value=50_000)
    add_voucher(engine, "FREESHIP", discount_type="FREE_SHIPPING", discount_value=0,
                max_discount=20_000)
    order_id = checkout_quote(api, engine, {
        "platform_voucher": "FREEITEM", "shipping_voucher": "FREESHIP",
    }, "summary-zero")
    view = OrderPage(browser, api, engine)
    try:
        view.open(order_id)
        expect(view.page.locator("#items-card")).to_be_visible()
        assert_money(view.page, "#order-total", 0)
        assert_money(view.page, "#order-total-val", 0)
        assert_money(view.page, "#order-subtotal", 50_000)
        assert_money(view.page, "#order-platform-discount", -50_000)
        assert_money(view.page, "#order-shop-discount", 0)
        assert_money(view.page, "#order-shipping-fee", 20_000)
        assert_money(view.page, "#order-shipping-discount", -20_000)
    finally:
        view.close()


def test_switching_to_legacy_pricing_clears_previous_breakdown(browser, api, engine):
    first = discounted_order(api, engine)
    second = plain_order(api, engine)
    view = OrderPage(browser, api, engine)
    try:
        view.open(first)
        expect(view.page.locator("#order-price-breakdown")).to_be_visible()
        view.page.select_option("#order-select", str(second))
        expect(view.page.locator("#order-id-val")).to_have_text(f"#{second}")
        assert_money(view.page, "#order-total", 70_000)
        expect(view.page.locator("#order-price-breakdown")).to_be_hidden()
        expect(view.page.locator("#order-breakdown-unavailable")).to_be_visible()
        view.page.select_option("#order-select", str(first))
        expect(view.page.locator("#order-id-val")).to_have_text(f"#{first}")
        assert_money(view.page, "#order-total", 433_000)
        expect(view.page.locator("#order-price-breakdown")).to_be_visible()
    finally:
        view.close()


def test_failed_read_keeps_summary_hidden_until_retry_succeeds(browser, api, engine):
    order_id = plain_order(api, engine)
    view = OrderPage(browser, api, engine)
    try:
        view.fail_detail = True
        view.open(order_id)
        expect(view.page.locator("#error-message")).to_have_text("Temporarily unavailable")
        expect(view.page.locator("#summary-metrics-bar")).to_be_hidden()
        view.fail_detail = False
        view.page.click("#retry-btn")
        expect(view.page.locator("#summary-metrics-bar")).to_be_visible()
        assert_money(view.page, "#order-total-val", 70_000)
    finally:
        view.close()


def test_another_buyer_cannot_see_order_summary(browser, api, engine):
    order_id = plain_order(api, engine)
    view = OrderPage(browser, api, engine, buyer_id=3)
    try:
        view.open(order_id)
        expect(view.page.locator("#error-message")).to_have_text("Order not found.")
        expect(view.page.locator("#summary-metrics-bar")).to_be_hidden()
        expect(view.page.locator("#items-card")).to_be_hidden()
    finally:
        view.close()
