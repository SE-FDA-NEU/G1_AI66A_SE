"""Tests for products API endpoints."""

import logging
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, delete, select

from src.api.products import CATALOG_ERROR_MESSAGE
from src.database import engine, get_session
from src.models.product import Product
from src.seed import build_products, seed_products


@pytest.fixture
def empty_catalog() -> Generator[None, None, None]:
    """Remove every product row after the test so tests stay independent."""
    yield
    with Session(engine) as session:
        session.exec(delete(Product))
        session.commit()


def test_list_products_default(client: TestClient) -> None:
    """Test GET /api/v1/products with default parameters."""
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
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
        assert first["data"][0]["thumbnail_url"] == "/first.jpg"
        assert isinstance(first["data"][0]["id"], str)
        assert first["data"][0]["stock_status"] == "out_of_stock"
        assert first["meta"]["total"] == 2
        assert first["meta"]["total_pages"] == 2
        second = client.get("/api/v1/products?page=2&limit=1").json()
        assert [item["code"] for item in second["data"]] == ["TEST-3"]
        beyond = client.get("/api/v1/products?page=3&limit=1").json()
        assert beyond["data"] == []
        assert beyond["meta"]["total"] == 2
        assert beyond["meta"]["current_page"] == 3
        assert beyond["meta"]["total_pages"] == 2
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


@pytest.mark.parametrize("query", ["page=0", "limit=0", "limit=101"])
def test_list_products_rejects_invalid_pagination(client: TestClient, query: str) -> None:
    """Out-of-range page or limit values are rejected by validation."""
    response = client.get(f"/api/v1/products?{query}")
    assert response.status_code == 422


def test_list_products_reflects_database_changes(client: TestClient, empty_catalog: None) -> None:
    """Rows added or edited in the database appear in the next API response."""
    with Session(engine) as session:
        session.add(Product(code="EDIT-1", name="Original", price=100, stock_quantity=10))
        session.commit()
    added = client.get("/api/v1/products").json()["data"]
    assert [(item["name"], item["price"]) for item in added] == [("Original", 100.0)]

    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == "EDIT-1")).one()
        product.name = "Renamed"
        product.price = 250
        session.add(product)
        session.commit()
    edited = client.get("/api/v1/products").json()["data"]
    assert [(item["name"], item["price"]) for item in edited] == [("Renamed", 250.0)]


def test_seeded_catalog_pages_do_not_overlap(client: TestClient, empty_catalog: None) -> None:
    """Walking every page returns each seeded product once, with consistent metadata."""
    seed_products()
    expected_total = len(build_products())
    total_pages = -(-expected_total // 20)
    page_numbers = range(1, total_pages + 2)  # includes one page past the end

    pages = [client.get(f"/api/v1/products?page={n}&limit=20").json() for n in page_numbers]

    codes = [item["code"] for page in pages for item in page["data"]]
    assert len(codes) == len(set(codes)) == expected_total
    assert [page["meta"]["current_page"] for page in pages] == list(page_numbers)
    assert all(page["meta"]["total"] == expected_total for page in pages)
    assert all(page["meta"]["total_pages"] == total_pages for page in pages)
    assert pages[-1]["data"] == []


def test_list_products_database_failure_returns_500(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing query is logged and returns a generic 500, never an empty catalog."""
    broken_engine = create_engine("sqlite://", poolclass=StaticPool)  # has no products table

    def broken_session() -> Generator[Session, None, None]:
        with Session(broken_engine) as session:
            yield session

    client.app.dependency_overrides[get_session] = broken_session
    try:
        with caplog.at_level(logging.ERROR, logger="src.api.products"):
            response = client.get("/api/v1/products")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": CATALOG_ERROR_MESSAGE}
    assert "Product catalog query failed" in caplog.text
