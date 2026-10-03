"""Tests for products API endpoints."""

from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from src.database import engine
from src.models.product import Product
from src.seed import seed_products


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


def test_products_database_pagination_and_visibility(client: TestClient) -> None:
    """API reads real rows, excludes inactive rows and paginates consistently."""
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Product(code="TEST-1", name="First", price=100, image_url="/first.jpg"),
                    Product(code="TEST-2", name="Hidden", price=200, is_active=False),
                    Product(code="TEST-3", name="Third", price=300),
                ]
            )
            session.commit()

        first = client.get("/api/v1/products?limit=1").json()
        assert [item["code"] for item in first["data"]] == ["TEST-1"]
        assert first["data"][0]["image_url"] == "/first.jpg"
        assert first["meta"]["total"] == 2
        assert first["meta"]["total_pages"] == 2
        second = client.get("/api/v1/products?page=2&limit=1").json()
        assert [item["code"] for item in second["data"]] == ["TEST-3"]
        beyond = client.get("/api/v1/products?page=3&limit=1").json()
        assert beyond["data"] == []
        assert beyond["meta"]["total"] == 2
    finally:
        with Session(engine) as session:
            session.exec(delete(Product))
            session.commit()


def test_seed_is_idempotent_and_available_in_api(client: TestClient) -> None:
    """Seeding twice preserves the catalog and the API can read it."""
    try:
        seed_products()
        first = client.get("/api/v1/products?limit=100").json()
        assert first["meta"]["total"] >= 10
        seed_products()
        second = client.get("/api/v1/products?limit=100").json()
        assert second == first
        assert len({item["code"] for item in second["data"]}) == len(second["data"])
    finally:
        with Session(engine) as session:
            session.exec(delete(Product))
            session.commit()
