"""US21 #152: production UI and real admin APIs in Chrome, with isolated SQLite."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from sqlmodel import Session, select
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.category import Category
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.user import User
from src.models.voucher import Voucher
from tests.cart_db import BUYER_ID, SELLER_ID, create_cart_engine

browser_api = pytest.importorskip("playwright.sync_api")
expect = browser_api.expect
ORIGIN = "http://admin.test"
ADMIN_ID = 4


@pytest.fixture(scope="module")
def admin_browser():
    with browser_api.sync_playwright() as playwright:
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
            except browser_api.Error:
                browser = playwright.chromium.launch(channel="chrome")
        yield browser
        browser.close()


class AdminSite:
    def __init__(self, page, client, engine, tokens):
        self.page, self.client, self.engine, self.tokens = page, client, engine, tokens
        self.calls, self.errors = [], []
        self.fail_next = None
        self.hold_next = None
        self.held = None
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.route("**/*", self.handle)

    def handle(self, route):
        request = route.request
        url = urlsplit(request.url)
        if not request.url.startswith(ORIGIN + "/"):
            route.abort()
            return
        key = (request.method, url.path)
        self.calls.append((key, request.post_data))
        if key == self.fail_next:
            self.fail_next = None
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps(
                    {"error": {"code": "ERR_DATABASE_FAILURE", "message": "Service unavailable."}}
                ),
            )
        elif key == self.hold_next:
            self.hold_next = None
            self.held = route
        else:
            self.forward(route)

    def forward(self, route):
        request = route.request
        url = urlsplit(request.url)
        response = self.client.request(
            request.method,
            url.path + (f"?{url.query}" if url.query else ""),
            headers=request.headers,
            content=request.post_data,
        )
        route.fulfill(
            status=response.status_code, headers=dict(response.headers), body=response.content
        )

    def mutations(self, method, path):
        return [body for (key, body) in self.calls if key == (method, path)]

    def tab(self, name):
        self.page.locator(f'.nav-tab[data-tab="{name}"]').click()
        expect(self.page.locator(f"#{name}-tbody")).to_have_attribute("aria-busy", "false")


@pytest.fixture
def site(tmp_path, admin_browser):
    engine = create_cart_engine(tmp_path / "admin-browser.db")
    with Session(engine) as session:
        admin = User(id=ADMIN_ID, name="Test administrator", email="admin@test.local", role="admin")
        session.add(admin)
        category = Category(name="Tools", slug="tools")
        session.add(category)
        session.flush()
        product = Product(
            code="ADMIN152",
            seller_id=SELLER_ID,
            name="Policy test product",
            price=100000,
            stock_quantity=5,
        )
        session.add(product)
        session.flush()
        session.add(ProductMetadata(product_id=product.id, category_id=category.id))
        session.add(
            Voucher(
                code="EXISTING10",
                scope="PLATFORM",
                seller_id=None,
                discount_type="PERCENTAGE",
                discount_value=1000,
                min_order_value=0,
                starts_at=datetime(2020, 1, 1, tzinfo=UTC),
                ends_at=datetime(2050, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()
        tokens = {
            key: create_access_token(session.get(User, key))
            for key in (ADMIN_ID, BUYER_ID, SELLER_ID)
        }
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    context = admin_browser.new_context(
        viewport={"width": 1280, "height": 900}, timezone_id="Asia/Bangkok"
    )
    page = context.new_page()
    page.add_init_script(f"localStorage.setItem('access_token', {json.dumps(tokens[ADMIN_ID])});")
    with TestClient(app, raise_server_exceptions=False) as client:
        value = AdminSite(page, client, engine, tokens)
        page.goto(ORIGIN + "/admin")
        expect(page.locator("#catalog-tbody")).to_contain_text("Policy test product")
        yield value
        assert value.errors == []
    context.close()
    engine.dispose()


def artifact(page, name):
    directory = os.environ.get("ADMIN_UI_ARTIFACTS")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / name), full_page=True)


def new_category(site, name="New category", slug="new-category", populate=True):
    site.tab("categories")
    site.page.locator("#btn-new-category").click()
    dialog = site.page.get_by_role("dialog", name="Add Category")
    if populate:
        dialog.get_by_label("Category Name").fill(name)
        dialog.get_by_label("Slug").fill(slug)
    return dialog


def new_voucher(site, code="TEST152", kind="PERCENTAGE"):
    site.tab("vouchers")
    site.page.locator("#btn-new-voucher").click()
    dialog = site.page.get_by_role("dialog", name="Create Platform Voucher")
    dialog.locator("#voucher-code").fill(code)
    dialog.locator("#voucher-type").select_option(kind)
    dialog.locator("#voucher-starts").fill("2030-01-02T08:00")
    dialog.locator("#voucher-ends").fill("2030-01-03T08:00")
    return dialog


def test_category_crud_and_keyboard_modal_use_real_persistence(site):
    page = site.page
    expect(page.locator("#admin-alert")).to_have_attribute("role", "status")
    expect(page.locator("#admin-error")).to_have_attribute("role", "alert")
    artifact(page, "catalog-desktop.png")
    dialog = new_category(site, populate=False)
    expect(dialog.locator("#category-name")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(dialog.get_by_role("button", name="Save Category")).to_be_focused()
    page.keyboard.press("Tab")
    expect(dialog.locator("#category-name")).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(page.locator("#btn-new-category")).to_be_focused()
    dialog = new_category(site)
    dialog.get_by_role("button", name="Save Category").click()
    expect(dialog).not_to_be_visible()
    expect(page.locator("#admin-alert")).to_contain_text("created successfully")
    page.get_by_role("button", name="Edit category New category", exact=True).click()
    dialog = page.get_by_role("dialog", name="Edit Category")
    dialog.get_by_label("Category Name").fill("Updated category")
    dialog.get_by_role("button", name="Save Category").click()
    delete = page.get_by_role("button", name="Delete category Updated category", exact=True)
    page.once("dialog", lambda confirm: confirm.dismiss())
    delete.click()
    with Session(site.engine) as session:
        category = session.exec(select(Category).where(Category.slug == "new-category")).one()
        category_id = category.id
    assert site.mutations("DELETE", f"/api/v1/admin/categories/{category_id}") == []
    page.once("dialog", lambda confirm: confirm.accept())
    delete.click()
    expect(page.locator("#categories-tbody")).not_to_contain_text("Updated category")
    with Session(site.engine) as session:
        assert session.get(Category, category_id) is None


@pytest.mark.parametrize(
    ("kind", "amount"),
    [
        ("PERCENTAGE", 1000),
        ("FIXED_AMOUNT", 1),
        ("FREE_SHIPPING", 0),
    ],
)
def test_voucher_creation_validation_utc_and_status_confirmation(site, kind, amount):
    page = site.page
    dialog = new_voucher(site, kind=kind)
    if kind == "FIXED_AMOUNT":
        expect(dialog.locator("#voucher-max")).to_be_disabled()
        dialog.locator("#voucher-max").evaluate("field => {field.value = '2500';}")
    else:
        dialog.locator("#voucher-max").fill("2500")
    if kind != "FREE_SHIPPING":
        dialog.locator("#voucher-val").fill(str(amount))
    else:
        expect(dialog.locator("#voucher-val")).to_be_disabled()
    dialog.locator("#voucher-ends").fill("2030-01-01T08:00")
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    assert dialog.locator("#voucher-ends").evaluate("field => field.validationMessage")
    assert site.mutations("POST", "/api/v1/admin/vouchers") == []
    dialog.locator("#voucher-ends").fill("2030-01-03T08:00")
    page.once("dialog", lambda confirm: confirm.dismiss())
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    assert site.mutations("POST", "/api/v1/admin/vouchers") == []
    expect(dialog).to_be_visible()
    page.once("dialog", lambda confirm: confirm.accept())
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator("#vouchers-tbody")).to_contain_text("TEST152")
    with Session(site.engine) as session:
        voucher = session.exec(select(Voucher).where(Voucher.code == "TEST152")).one()
        assert voucher.scope == "PLATFORM" and voucher.seller_id is None
        assert voucher.discount_value == amount
        assert voucher.max_discount == (None if kind == "FIXED_AMOUNT" else 2500)
        assert voucher.starts_at == datetime(2030, 1, 2, 8, tzinfo=UTC)
        assert voucher.ends_at == datetime(2030, 1, 3, 8, tzinfo=UTC)
        voucher_id = voucher.id
    toggle = page.locator(f"#voucher-toggle-{voucher_id}")
    page.once("dialog", lambda confirm: confirm.dismiss())
    toggle.click()
    assert site.mutations("PATCH", f"/api/v1/admin/vouchers/{voucher_id}") == []
    page.once("dialog", lambda confirm: confirm.accept())
    toggle.click()
    expect(toggle).to_have_text("Activate")
    assert len(site.mutations("PATCH", f"/api/v1/admin/vouchers/{voucher_id}")) == 1


def test_errors_retain_input_and_failed_reads_have_retry(site):
    page = site.page
    site.fail_next = ("GET", "/api/v1/admin/categories")
    site.tab("categories")
    expect(page.locator("#categories-tbody")).to_contain_text("Could not load records")
    page.get_by_role("button", name="Retry", exact=True).click()
    expect(page.locator("#categories-tbody")).to_contain_text("Tools")
    dialog = new_voucher(site, code="EXISTING10")
    page.once("dialog", lambda confirm: confirm.accept())
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    expect(dialog.locator(".form-feedback")).to_contain_text("already exists")
    expect(dialog.locator(".form-feedback")).to_be_focused()
    expect(dialog.locator("#voucher-code")).to_have_value("EXISTING10")
    expect(dialog.get_by_role("button", name="Create Voucher", exact=True)).to_be_enabled()
    artifact(page, "voucher-error.png")
    dialog.locator("#voucher-code").fill("RECOVERED152")
    site.fail_next = ("POST", "/api/v1/admin/vouchers")
    page.once("dialog", lambda confirm: confirm.accept())
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    expect(dialog.locator(".form-feedback")).to_contain_text("Service unavailable")
    expect(dialog.locator("#voucher-code")).to_have_value("RECOVERED152")
    page.once("dialog", lambda confirm: confirm.accept())
    dialog.get_by_role("button", name="Create Voucher", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator("#admin-alert")).to_contain_text("RECOVERED152 created successfully")
    # The shared modal helper must also preserve legacy dialogs' error feedback.
    page.locator('.nav-tab[data-tab="users"]').click()
    row = page.locator("#users-tbody tr").filter(has_text="seller@test.local")
    row.get_by_role("button", name="Moderate", exact=True).click()
    legacy = page.get_by_role("dialog", name="Manage User Account Status")
    legacy.get_by_label("Moderation Reason").fill("Policy review")
    site.fail_next = ("PATCH", f"/api/v1/admin/users/{SELLER_ID}/status")
    legacy.get_by_role("button", name="Apply Status", exact=True).click()
    expect(legacy.locator(".form-feedback")).to_contain_text("Status change failed")
    expect(legacy.locator(".form-feedback")).to_be_focused()
    expect(legacy.get_by_label("Moderation Reason")).to_have_value("Policy review")
    page.keyboard.press("Escape")
    expect(legacy).not_to_be_visible()


def test_pending_save_prevents_duplicate_and_modal_dismissal(site):
    page = site.page
    dialog = new_category(site)
    site.hold_next = ("POST", "/api/v1/admin/categories")
    dialog.get_by_role("button", name="Save Category").click()
    expect(dialog.locator("form")).to_have_attribute("aria-busy", "true")
    expect(dialog.locator(".form-progress")).to_have_text("Saving changes...")
    expect(dialog.get_by_role("button", name="Save Category")).to_be_disabled()
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    dialog.locator("form").evaluate(
        "form => form.dispatchEvent(new Event('submit', {cancelable:true}))"
    )
    assert len(site.mutations("POST", "/api/v1/admin/categories")) == 1
    assert site.held is not None
    site.forward(site.held)
    expect(dialog).not_to_be_visible()
    expect(page.locator("#btn-new-category")).to_be_enabled()


def test_catalog_confirmation_empty_state_and_mobile_layout(site):
    page = site.page
    toggle = page.get_by_role("button", name="Deactivate product ADMIN152", exact=True)
    page.once("dialog", lambda confirm: confirm.dismiss())
    toggle.click()
    assert not any(key[0] == "PATCH" for key, _ in site.calls)
    page.once("dialog", lambda confirm: confirm.accept())
    toggle.click()
    expect(
        page.get_by_role("button", name="Reactivate product ADMIN152", exact=True)
    ).to_be_visible()
    with Session(site.engine) as session:
        assert session.exec(select(Product)).one().is_active is False
    page.locator("#catalog-search").fill("No matching product")
    expect(page.locator("#catalog-tbody")).to_contain_text("No matching records")
    page.set_viewport_size({"width": 390, "height": 844})
    site.tab("categories")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifact(page, "categories-mobile.png")
    dialog = new_voucher(site)
    assert dialog.evaluate("node => node.getBoundingClientRect().right <= innerWidth")
    expect(dialog.locator("#voucher-code")).to_be_visible()


@pytest.mark.parametrize("actor", [None, BUYER_ID, SELLER_ID])
def test_non_admin_page_does_not_load_admin_data(site, actor):
    context = site.page.context.browser.new_context()
    page = context.new_page()
    if actor is not None:
        page.add_init_script(
            f"localStorage.setItem('access_token', {json.dumps(site.tokens[actor])});"
        )
    view = AdminSite(page, site.client, site.engine, site.tokens)
    page.goto(ORIGIN + "/admin")
    expect(page.locator("#admin-unauthorized-banner")).to_be_visible()
    expect(page.locator("#admin-portal-content")).not_to_be_visible()
    assert not any(path.startswith("/api/v1/admin/") for (_, path), _ in view.calls)
    assert view.errors == []
    context.close()


def test_account_switch_blocks_an_already_open_admin_form(site):
    dialog = new_category(site)
    site.page.evaluate(
        "token => localStorage.setItem('access_token', token)", site.tokens[BUYER_ID]
    )
    dialog.get_by_role("button", name="Save Category").click()
    expect(site.page.locator("#admin-unauthorized-banner")).to_be_visible()
    expect(dialog).not_to_be_visible()
    assert site.mutations("POST", "/api/v1/admin/categories") == []
    expect(site.page.locator("#categories-tbody")).to_be_empty()


def test_late_admin_response_is_discarded_after_account_switch(site):
    site.hold_next = ("GET", "/api/v1/admin/categories")
    site.page.locator('.nav-tab[data-tab="categories"]').click()
    expect(site.page.locator("#categories-tbody")).to_have_attribute("aria-busy", "true")
    site.page.evaluate(
        "token => localStorage.setItem('access_token', token)", site.tokens[BUYER_ID]
    )
    assert site.held is not None
    site.forward(site.held)
    expect(site.page.locator("#admin-unauthorized-banner")).to_be_visible()
    expect(site.page.locator("#categories-tbody")).to_be_empty()


def test_old_filter_response_cannot_replace_a_newer_empty_result(site):
    page = site.page
    site.hold_next = ("GET", "/api/v1/admin/products")
    page.locator("#catalog-search").fill("Policy")
    expect(page.locator("#catalog-tbody")).to_have_attribute("aria-busy", "true")
    assert site.held is not None
    page.locator("#catalog-search").fill("No such product")
    expect(page.locator("#catalog-tbody")).to_contain_text("No matching records")
    site.forward(site.held)
    expect(page.locator("#catalog-tbody")).to_contain_text("No matching records")
    expect(page.locator("#catalog-tbody")).not_to_contain_text("Policy test product")


@pytest.mark.parametrize(("name", "slug"), [("   ", "valid-slug"), ("Name", "Bad Slug")])
def test_invalid_category_fields_never_send_a_mutation(site, name, slug):
    dialog = new_category(site, name=name, slug=slug)
    dialog.get_by_role("button", name="Save Category").click()
    assert site.mutations("POST", "/api/v1/admin/categories") == []
    expect(dialog).to_be_visible()
    assert dialog.locator("form").evaluate("form => !form.checkValidity()")
