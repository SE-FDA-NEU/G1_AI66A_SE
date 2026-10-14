"""Tests for the /products page and its static assets."""

import pytest
from fastapi.testclient import TestClient


def test_products_page_serves_html(client: TestClient) -> None:
    """Test GET /products returns the HTML page wired to its CSS and JS assets."""
    response = client.get("/products")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/static/products.css"' in response.text
    assert 'src="/static/products.js"' in response.text


def test_login_page_serves_html(client: TestClient) -> None:
    """The login page is available and points to the shared stylesheet."""
    response = client.get("/login")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'src="/static/login.js"' in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/products.css", "text/css"),
        ("/static/products.js", "javascript"),
        ("/static/product-placeholder.svg", "image/svg+xml"),
    ],
)
def test_products_page_assets_are_served(client: TestClient, path: str, content_type: str) -> None:
    """Test the page assets are served as static files, not as API JSON responses."""
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


def test_login_script_handles_return_destination(client: TestClient) -> None:
    """The login script contains return destination resolution to preserve protected routes."""
    response = client.get("/static/login.js")
    assert response.status_code == 200
    assert "getReturnDestination" in response.text
    assert "return_to" in response.text


def test_products_script_configures_navigation_return_destination(client: TestClient) -> None:
    """The products script binds return_to on login link to preserve origin route."""
    response = client.get("/static/products.js")
    assert response.status_code == 200
    assert "return_to" in response.text
