"""Buyer-facing boundaries for seller-only browser workspaces."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "seller-products.html",
    "seller-product-new.html",
    "seller-orders.html",
    "seller-analytics.html",
)


@pytest.mark.parametrize("page", PAGES)
def test_seller_workspace_pages_load_the_non_seller_guard(client, page: str) -> None:
    response = client.get(
        {
            "seller-products.html": "/seller/products",
            "seller-product-new.html": "/seller/products/new",
            "seller-orders.html": "/seller/orders",
            "seller-analytics.html": "/seller/analytics",
        }[page]
    )

    assert response.status_code == 200
    assert 'src="/static/seller-access.js"' in response.text


def test_non_seller_guard_redirects_known_non_seller_tokens() -> None:
    guard = (ROOT / "src" / "web" / "static" / "seller-access.js").read_text(
        encoding="utf-8"
    )

    assert 'payload.role !== "seller"' in guard
    assert 'window.location.replace("/products")' in guard
