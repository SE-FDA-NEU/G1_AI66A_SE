"""Public page shells and assets; private analytics remain on seller-only APIs."""

import pytest


@pytest.mark.parametrize("path", ["/seller/analytics", "/seller/analytics/products"])
def test_analytics_page_loads_production_assets_without_private_data(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="analytics-report" hidden' in response.text
    assert 'id="analytics-filters"' in response.text
    for asset in ("seller-analytics.js", "analytics-chart.js", "seller-analytics.css"):
        assert f'/static/{asset}' in response.text
        asset_response = client.get(f"/static/{asset}")
        assert asset_response.status_code == 200
        assert len(asset_response.content) > 0


@pytest.mark.parametrize("path", ["/seller/orders", "/seller/products"])
def test_existing_seller_workspace_links_to_analytics(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert 'href="/seller/analytics"' in response.text
