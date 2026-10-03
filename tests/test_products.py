"""Tests for products API endpoints."""

from fastapi.testclient import TestClient


def test_list_products_default(client: TestClient) -> None:
    """Test GET /api/v1/products with default parameters."""
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert "meta" in data
    assert data["meta"]["current_page"] == 1
    assert data["meta"]["limit"] == 20
    assert data["meta"]["total"] == 0
    assert data["meta"]["total_pages"] == 0


def test_list_products_custom_pagination(client: TestClient) -> None:
    """Test GET /api/v1/products with custom pagination parameters."""
    response = client.get("/api/v1/products?page=2&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["current_page"] == 2
    assert data["meta"]["limit"] == 10
