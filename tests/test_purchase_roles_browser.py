"""#220: purchase controls follow account roles in the production catalog/detail pages."""

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import Session, select

from src.auth import create_access_token
from src.models.cart_item import CartItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.user import User
from tests import test_cart_api as cart_api
from tests.cart_db import BUYER_ID, SELLER_ID, add_product

browser_api = pytest.importorskip("playwright.sync_api")
expect = browser_api.expect
engine = cart_api.engine
api = cart_api.api
ORIGIN = "http://purchase-roles.test"
OTHER_SELLER_ID = 4
ADMIN_ID = 5
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def browser():
    with browser_api.sync_playwright() as playwright:
        executable = os.environ.get("BROWSER_PATH")
        if not executable:
            executable = next((str(path) for path in (
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            ) if path.is_file()), None)
        try:
            value = playwright.chromium.launch(**(
                {"executable_path": executable} if executable else {}
            ))
        except browser_api.Error:
            value = playwright.chromium.launch(channel="chrome")
        yield value
        value.close()


class Shop:
    """Production pages/API over intercepted transport, with per-test SQLite data."""

    def __init__(self, page, api, tokens):
        self.page, self.api, self.tokens = page, api, tokens
        self.calls, self.errors = [], []
        self.hold_cart = False
        self.held = None
        self.opened = False
        page.route("**/*", self.handle)
        page.on("pageerror", lambda error: self.errors.append(str(error)))

    def handle(self, route):
        request = route.request
        url = urlsplit(request.url)
        if url.netloc != urlsplit(ORIGIN).netloc:
            route.abort()
            return
        self.calls.append((request.method, url.path, request.post_data))
        if self.hold_cart and request.method == "POST" and url.path == "/api/v1/cart/items":
            self.held = route
        else:
            self.forward(route)

    def forward(self, route):
        request = route.request
        url = urlsplit(request.url)
        response = self.api.request(
            request.method, url.path + (f"?{url.query}" if url.query else ""),
            headers=request.headers, content=request.post_data,
        )
        route.fulfill(status=response.status_code, body=response.content,
                      content_type=response.headers.get("content-type"))

    def open(self, path, actor):
        if self.opened:
            self.page.evaluate("""token => {
                if (token) localStorage.setItem('access_token', token);
                else localStorage.removeItem('access_token');
            }""", self.tokens.get(actor))
        else:
            self.page.add_init_script(
                "if (!sessionStorage.getItem('test-auth-initialized')) {"
                "sessionStorage.setItem('test-auth-initialized', '1'); localStorage.clear();" + (
                    f"localStorage.setItem('access_token', {json.dumps(self.tokens[actor])});"
                    if actor else ""
                ) + "}"
            )
            self.opened = True
        self.page.goto(ORIGIN + path)

    def switch(self, actor):
        self.page.evaluate("""token => {
            const oldValue = localStorage.getItem('access_token');
            if (token) localStorage.setItem('access_token', token);
            else localStorage.removeItem('access_token');
            window.dispatchEvent(new StorageEvent('storage', {
                key:'access_token', oldValue, newValue:token,
            }));
        }""", self.tokens.get(actor))

    def cart_posts(self):
        return [json.loads(body) for method, path, body in self.calls
                if method == "POST" and path == "/api/v1/cart/items"]


@pytest.fixture
def shop(browser, api, engine):
    with Session(engine) as session:
        session.add_all([
            User(id=OTHER_SELLER_ID, name="Other seller", email="other-shop@test.local",
                 role="seller"),
            User(id=ADMIN_ID, name="Admin", email="admin@test.local", role="admin"),
        ])
        session.commit()
        tokens = {role: create_access_token(session.get(User, user_id)) for role, user_id in {
            "buyer": BUYER_ID, "seller": SELLER_ID, "admin": ADMIN_ID,
        }.items()}
    add_product(engine, "BUY-SELF", price=50_000)
    other = add_product(engine, "BUY-OTHER", price=70_000)
    add_product(engine, "BUY-EMPTY", stock=0)
    options = add_product(engine, "BUY-VARIANTS")
    with Session(engine) as session:
        session.get(Product, other).seller_id = OTHER_SELLER_ID
        for product in session.exec(select(Product)):
            product.image_url = None
        session.add_all([
            ProductVariant(product_id=options, seller_id=SELLER_ID, sku="IN-STOCK",
                           name="In stock option", price=80_000, stock_quantity=4),
            ProductVariant(product_id=options, seller_id=SELLER_ID, sku="EMPTY",
                           name="Empty option", price=90_000, stock_quantity=0),
        ])
        session.commit()
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    value = Shop(context.new_page(), api, tokens)
    yield value
    assert value.errors == []
    context.close()


def screenshot(page, name):
    if directory := os.environ.get("PURCHASE_UI_ARTIFACTS"):
        path = ROOT / directory
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / name), full_page=True)


@pytest.mark.parametrize("actor", ["seller", "admin"])
@pytest.mark.parametrize("path", ["/products", "/products/BUY-SELF", "/products/BUY-OTHER"])
def test_non_buyers_never_see_or_submit_purchase_controls(shop, actor, path):
    shop.open(path, actor)
    page = shop.page
    expect(page.locator("#logout-button")).to_be_visible()
    expect(page.locator("#cart-link")).to_be_hidden()
    if path != "/products":
        expect(page.locator("#product-detail")).to_be_visible()
        expect(page.locator("#add-to-cart-form")).to_be_hidden()
        expect(page.locator("#product-quantity")).to_be_hidden()
        expect(page.locator("#add-to-cart")).to_be_disabled()
        page.locator("#add-to-cart-form").evaluate(
            "form => form.dispatchEvent(new Event('submit', {cancelable:true}))"
        )
    assert shop.cart_posts() == []
    if actor == "seller":
        expect(page.locator("#seller-orders-link")).to_be_visible()
        if path == "/products":
            expect(page.locator("#products-grid")).to_be_visible()
            screenshot(page, "seller-catalog-desktop.png")


def test_buyer_adds_real_cart_line_and_duplicate_submit_is_locked(shop, engine):
    shop.open("/products/BUY-OTHER", "buyer")
    page = shop.page
    expect(page.locator("#cart-link")).to_be_visible()
    page.locator("#product-quantity").fill("2")
    shop.hold_cart = True
    page.click("#add-to-cart")
    expect(page.locator("#add-to-cart")).to_be_disabled()
    page.locator("#add-to-cart-form").evaluate(
        "form => form.dispatchEvent(new Event('submit', {cancelable:true}))"
    )
    assert len(shop.cart_posts()) == 1
    shop.forward(shop.held)
    page.wait_for_url(ORIGIN + "/cart")
    with Session(engine) as session:
        [line] = session.exec(select(CartItem)).all()
        assert (line.buyer_id, line.quantity) == (BUYER_ID, 2)


def test_guest_login_keeps_quantity_and_variant(shop, engine):
    shop.open("/products/BUY-VARIANTS", None)
    page = shop.page
    expect(page.locator("#add-to-cart")).to_be_enabled()
    selected = page.locator("#product-variant").input_value()
    page.locator("#product-quantity").fill("2")
    page.click("#add-to-cart")
    page.wait_for_url("**/login?*")
    destination = parse_qs(urlsplit(page.url).query)["return_to"][0]
    assert parse_qs(urlsplit(destination).query) == {"quantity": ["2"], "variant_id": [selected]}
    assert shop.cart_posts() == []
    shop.open(destination, "buyer")
    expect(page.locator("#product-quantity")).to_have_value("2")
    expect(page.locator("#product-variant")).to_have_value(selected)
    page.click("#add-to-cart")
    page.wait_for_url(ORIGIN + "/cart")
    with Session(engine) as session:
        [line] = session.exec(select(CartItem)).all()
        assert (line.buyer_id, line.quantity, line.variant_id) == (BUYER_ID, 2, int(selected))


def test_role_and_stock_stay_consistent_after_variant_changes(shop):
    shop.open("/products/BUY-VARIANTS", "buyer")
    page = shop.page
    expect(page.locator("#add-to-cart")).to_be_enabled()
    options = page.locator("#product-variant option").evaluate_all(
        "rows => rows.map(row => row.value)",
    )
    page.select_option("#product-variant", options[1])
    expect(page.locator("#add-to-cart")).to_be_disabled()
    page.select_option("#product-variant", options[0])
    expect(page.locator("#add-to-cart")).to_be_enabled()
    shop.switch("seller")
    page.select_option("#product-variant", options[1])
    page.select_option("#product-variant", options[0])
    expect(page.locator("#add-to-cart-form")).to_be_hidden()
    expect(page.locator("#add-to-cart")).to_be_disabled()
    shop.switch("buyer")
    expect(page.locator("#add-to-cart")).to_be_enabled()


@pytest.mark.parametrize("path", ["/products", "/products/BUY-OTHER"])
def test_switching_accounts_refreshes_navigation_without_reload(shop, path):
    shop.open(path, "buyer")
    page = shop.page
    expect(page.locator("#cart-link")).to_be_visible()
    shop.switch("seller")
    expect(page.locator("#cart-link")).to_be_hidden()
    shop.switch("buyer")
    expect(page.locator("#cart-link")).to_be_visible()
    page.click("#logout-button")
    expect(page.locator("#login-link")).to_be_visible()


@pytest.mark.parametrize("failed", [False, True])
def test_old_cart_response_cannot_redirect_a_new_seller_session(shop, failed):
    shop.open("/products/BUY-OTHER", "buyer")
    page = shop.page
    shop.hold_cart = True
    page.click("#add-to-cart")
    expect(page.locator("#add-to-cart")).to_be_disabled()
    shop.switch("seller")
    with page.expect_event("requestfinished", predicate=lambda request:
                           request.method == "POST" and request.url.endswith("/cart/items")):
        if failed:
            shop.held.fulfill(status=503, json={"error": {"message": "Old request failed"}})
        else:
            shop.forward(shop.held)
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 0))")
    assert urlsplit(page.url).path == "/products/BUY-OTHER"
    expect(page.locator("#cart-link")).to_be_hidden()
    expect(page.locator("#add-to-cart-form")).to_be_hidden()
    expect(page.locator("#cart-status")).not_to_contain_text("Old request failed")
    assert len(shop.cart_posts()) == 1


def test_controls_start_hidden_before_page_scripts_execute(shop):
    shop.page.route("**/static/*.js", lambda route: route.abort())
    for path in ["/products", "/products/BUY-OTHER"]:
        shop.page.goto(ORIGIN + path)
        expect(shop.page.locator("#cart-link")).to_be_hidden()


@pytest.mark.parametrize("actor", ["seller", "buyer"])
def test_role_controls_fit_mobile_without_hiding_product_information(shop, actor):
    page = shop.page
    page.set_viewport_size({"width": 390, "height": 844})
    shop.open("/products/BUY-OTHER", actor)
    expect(page.locator("#product-detail")).to_be_visible()
    expect(page.locator("#product-name")).to_contain_text("BUY-OTHER")
    expect(page.locator("#product-stock")).to_contain_text("In Stock")
    if actor == "seller":
        expect(page.locator("#cart-link")).to_be_hidden()
        expect(page.locator("#add-to-cart-form")).to_be_hidden()
    else:
        expect(page.locator("#cart-link")).to_be_visible()
        expect(page.locator("#add-to-cart")).to_be_enabled()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, f"{actor}-detail-mobile.png")


def test_out_of_stock_blocks_even_a_forced_buyer_submit(shop):
    shop.open("/products/BUY-EMPTY", "buyer")
    page = shop.page
    expect(page.locator("#product-detail")).to_be_visible()
    expect(page.locator("#add-to-cart")).to_be_disabled()
    page.locator("#add-to-cart-form").evaluate(
        "form => form.dispatchEvent(new Event('submit', {cancelable:true}))",
    )
    assert shop.cart_posts() == []


def test_buyer_can_retry_a_cart_error_with_quantity_preserved(shop, engine):
    shop.open("/products/BUY-OTHER", "buyer")
    page = shop.page
    expect(page.locator("#add-to-cart")).to_be_enabled()
    page.locator("#product-quantity").fill("2")
    page.route("**/api/v1/cart/items", lambda route: route.fulfill(
        status=503, json={"error": {"message": "Service unavailable"}},
    ), times=1)
    page.click("#add-to-cart")
    expect(page.locator("#cart-status")).to_have_text("Service unavailable")
    expect(page.locator("#add-to-cart")).to_be_enabled()
    expect(page.locator("#product-quantity")).to_have_value("2")
    with Session(engine) as session:
        assert session.exec(select(CartItem)).all() == []
    page.click("#add-to-cart")
    page.wait_for_url(ORIGIN + "/cart")
    with Session(engine) as session:
        [line] = session.exec(select(CartItem)).all()
        assert (line.buyer_id, line.quantity) == (BUYER_ID, 2)
