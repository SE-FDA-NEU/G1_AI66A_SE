"""Tests for the /cart page and its static assets (US03, #79)."""

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

STATE_REGIONS = ("cart-loading", "cart-content", "cart-empty", "cart-error")


class ElementsById(HTMLParser):
    """Collect the tag and attributes of every element that has an id."""

    def __init__(self) -> None:
        super().__init__()
        self.found: dict[str, tuple[str, dict[str, str | None]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.found[attributes["id"]] = (tag, attributes)


def parse_cart_page(client: TestClient) -> dict[str, tuple[str, dict[str, str | None]]]:
    parser = ElementsById()
    parser.feed(client.get("/cart").text)
    return parser.found


def test_cart_page_serves_html_wired_to_its_assets(client: TestClient) -> None:
    response = client.get("/cart")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/static/products.css"' in response.text
    assert 'href="/static/cart.css"' in response.text
    assert 'src="/static/cart.js"' in response.text


def test_cart_page_starts_in_the_loading_state(client: TestClient) -> None:
    elements = parse_cart_page(client)

    visible = [region for region in STATE_REGIONS if "hidden" not in elements[region][1]]
    assert visible == ["cart-loading"]
    assert elements["cart-status"][1]["role"] == "status"


def test_cart_page_offers_empty_error_and_checkout_actions(client: TestClient) -> None:
    html = client.get("/cart").text
    elements = parse_cart_page(client)

    assert "Your cart is empty." in html
    assert '<a class="button" href="/products">Continue shopping</a>' in html
    assert elements["cart-empty-total"][0] == "strong"
    assert elements["cart-retry"][0] == "button"
    assert elements["checkout-button"][0] == "button"
    assert elements["logout-button"][0] == "button"


def test_cart_script_sends_the_token_and_returns_to_the_cart_after_login(
    client: TestClient,
) -> None:
    script = client.get("/static/cart.js").text

    assert "Authorization: `Bearer ${token}`" in script
    assert 'encodeURIComponent("/cart")' in script


def test_catalog_navigation_links_to_the_cart(client: TestClient) -> None:
    assert '<a id="cart-link" href="/cart">Cart</a>' in client.get("/products").text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/cart.css", "text/css"),
        ("/static/cart.js", "javascript"),
    ],
)
def test_cart_page_assets_are_served(client: TestClient, path: str, content_type: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
