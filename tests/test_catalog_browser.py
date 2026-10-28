"""Catalog page checks in a real browser (#116): native number inputs and selects.

DOM doubles cannot reproduce how a number input reports text it cannot parse, or how a
select keeps its choice when its options are rebuilt, so these run the real page in Chromium.
The page, its static files and the API are served by request interception: no server or
database is needed. Skipped when Playwright is not installed.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://catalog.test"
PRICE_ERROR = "Enter prices as whole numbers of 0 ₫ or more."
OPTIONS = {
    "/api/v1/categories": [
        {"id": 1, "name": "Electronics", "parent_id": None},
        {"id": 4, "name": "Laptops", "parent_id": 1},
    ],
    "/api/v1/sellers": [{"id": 7, "name": "Shop Seven"}],
}
PRODUCTS = {
    "data": [
        {
            "id": "1",
            "code": "P-1",
            "name": "Desk Lamp",
            "description": None,
            "price": 150000,
            "thumbnail_url": None,
            "image_url": None,
            "stock_quantity": 3,
            "stock_status": "low_stock",
            "rating": 0,
        }
    ],
    "meta": {
        "current_page": 1,
        "limit": 20,
        "page_size": 20,
        "total": 1,
        "total_items": 1,
        "total_pages": 1,
    },
}


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except sync_api.Error:
            # CI runners ship Google Chrome but not Playwright's own Chromium build.
            chromium = playwright.chromium.launch(channel="chrome")
        yield chromium
        chromium.close()


class Catalog:
    """Serves /products, recording catalog queries and optionally holding the option lists."""

    def __init__(self, page, html: str | None = None, hold_options: bool = False):
        self.page = page
        self.html = html or (ROOT / "src/web/pages/products.html").read_text(encoding="utf-8")
        self.hold_options = hold_options
        self.held = []
        self.queries = []
        page.route(f"{ORIGIN}/**", self.handle)

    def handle(self, route):
        url = urlsplit(route.request.url)
        if url.path == "/products":
            route.fulfill(body=self.html, content_type="text/html")
        elif url.path.startswith("/static/"):
            route.fulfill(path=ROOT / "src/web" / url.path.lstrip("/"))
        elif url.path == "/api/v1/products":
            self.queries.append(parse_qs(url.query))
            route.fulfill(json=PRODUCTS)
        elif url.path in OPTIONS and self.hold_options:
            self.held.append((route, url.path))
        elif url.path in OPTIONS:
            route.fulfill(json=OPTIONS[url.path])
        else:
            route.fulfill(status=404)

    def release_options(self, options):
        for route, path in self.held:
            route.fulfill(json=options[path])
        self.held.clear()

    def open(self):
        self.page.goto(f"{ORIGIN}/products")
        expect(self.page.locator("#products-grid")).to_be_visible()


def test_unparseable_price_text_blocks_the_search(browser):
    """`-` or `1e` leaves a number input's value empty; it must not search without that bound."""
    page = browser.new_page()
    catalog = Catalog(page)
    catalog.open()
    sent = len(catalog.queries)
    price = page.locator("#filter-min-price")
    for typed in ("-", "1e"):
        price.fill("")
        price.press_sequentially(typed)
        assert price.evaluate("input => input.value === '' && input.validity.badInput")
        page.click("#apply-filters")
        expect(page.locator("#price-error")).to_have_text(PRICE_ERROR)
        price.press("Enter")
        expect(page.locator("#price-error")).to_have_text(PRICE_ERROR)

    # The browser's step="1000" check no longer blocks Enter; the page's own rule applies.
    price.fill("155500")
    with page.expect_request("**/api/v1/products?*"):
        price.press("Enter")
    expect(page.locator("#price-error")).to_be_hidden()
    assert len(catalog.queries) == sent + 1, "The unreadable attempts sent no request"
    assert catalog.queries[-1]["min_price"] == ["155500"]
    page.close()


def restored_page() -> str:
    """The page as back navigation may restore it: category 4 and seller 7 already chosen."""
    html = (ROOT / "src/web/pages/products.html").read_text(encoding="utf-8")
    for default, restored in (
        (
            '<option value="">All categories</option>',
            '<option value="">All categories</option>\n'
            '            <option value="4" selected>Laptops</option>',
        ),
        (
            '<option value="">All sellers</option>',
            '<option value="">All sellers</option>\n'
            '            <option value="7" selected>Shop Seven</option>',
        ),
    ):
        assert html.count(default) == 1
        html = html.replace(default, restored)
    return html


def test_restored_choices_survive_delayed_option_lists(browser):
    page = browser.new_page()
    catalog = Catalog(page, html=restored_page(), hold_options=True)
    catalog.open()
    assert catalog.queries[0]["category_id"] == ["4"]
    assert catalog.queries[0]["seller_id"] == ["7"]

    catalog.release_options(OPTIONS)
    expect(page.locator("#filter-category option")).to_have_count(3)
    expect(page.locator("#filter-seller option")).to_have_count(2)
    expect(page.locator("#filter-category")).to_have_value("4")
    expect(page.locator("#filter-seller")).to_have_value("7")
    assert len(catalog.queries) == 1, "Results already match the kept choices"
    page.close()


def test_restored_choice_without_an_option_reloads_unfiltered(browser):
    page = browser.new_page()
    catalog = Catalog(page, html=restored_page(), hold_options=True)
    catalog.open()
    assert catalog.queries[0]["category_id"] == ["4"]

    without_category_4 = {**OPTIONS, "/api/v1/categories": OPTIONS["/api/v1/categories"][:1]}
    with page.expect_request("**/api/v1/products?*"):
        catalog.release_options(without_category_4)
    expect(page.locator("#filter-category")).to_have_value("")
    expect(page.locator("#filter-seller")).to_have_value("7")
    expect(page.locator("#products-grid")).to_be_visible()
    assert "category_id" not in catalog.queries[-1]
    assert catalog.queries[-1]["seller_id"] == ["7"]
    page.close()
