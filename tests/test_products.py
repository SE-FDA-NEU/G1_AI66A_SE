"""Tests for the product catalog API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, delete

from src.api.products import CATALOG_ERROR_MESSAGE
from src.database import engine, get_session
from src.main import create_app
from src.models.product import Product
from src.seed import seed_products


@pytest.fixture(autouse=True)
def clean_products():
    """Ensure products are clean before and after each test."""
    with Session(engine) as session:
        session.exec(delete(Product))
        session.commit()

    yield

    with Session(engine) as session:
        session.exec(delete(Product))
        session.commit()


def test_list_products_default(client: TestClient) -> None:
    """Default request should return seeded products and pagination metadata."""
    seed_products()

    response = client.get("/api/v1/products")

    assert response.status_code == 200

    body = response.json()

    assert "data" in body
    assert "meta" in body
    assert body["meta"]["current_page"] == 1
    assert body["meta"]["limit"] == 20
    assert body["meta"]["total"] >= 10
    assert len(body["data"]) <= 20


def test_list_products_custom_pagination(client: TestClient) -> None:
    """Custom page and limit should be reflected in the response."""
    seed_products()

    response = client.get("/api/v1/products?page=2&limit=5")

    assert response.status_code == 200

    body = response.json()

    assert body["meta"]["current_page"] == 2
    assert body["meta"]["limit"] == 5
    assert len(body["data"]) <= 5


def test_products_database_pagination_and_visibility(
    client: TestClient,
) -> None:
    """Only active database products should appear in the catalog."""
    with Session(engine) as session:
        session.add_all(
            [
                Product(
                    code="TEST-1",
                    seller_id=1,
                    name="First",
                    price=100,
                    stock_quantity=0,
                    image_url="/first.jpg",
                    is_active=True,
                ),
                Product(
                    code="TEST-2",
                    seller_id=1,
                    name="Second",
                    price=200,
                    stock_quantity=5,
                    image_url="/second.jpg",
                    is_active=True,
                ),
                Product(
                    code="TEST-3",
                    seller_id=1,
                    name="Hidden",
                    price=300,
                    stock_quantity=10,
                    image_url="/hidden.jpg",
                    is_active=False,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/products?page=1&limit=10")

    assert response.status_code == 200

    body = response.json()

    codes = {product["code"] for product in body["data"]}

    assert "TEST-1" in codes
    assert "TEST-2" in codes
    assert "TEST-3" not in codes

    assert body["meta"]["total"] == 2


def test_seed_is_idempotent_and_available_in_api(
    client: TestClient,
) -> None:
    """Running the seed repeatedly must not duplicate products."""
    seed_products()
    seed_products()

    response = client.get("/api/v1/products?limit=100")

    assert response.status_code == 200

    body = response.json()

    assert body["meta"]["total"] == 45
    assert len(body["data"]) == 45

    codes = [product["code"] for product in body["data"]]

    assert len(codes) == len(set(codes))


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "limit=0",
        "limit=101",
    ],
)
def test_list_products_rejects_invalid_pagination(
    client: TestClient,
    query: str,
) -> None:
    """FastAPI validation should reject invalid pagination values."""
    response = client.get(f"/api/v1/products?{query}")

    assert response.status_code == 422


def test_list_products_reflects_database_changes(
    client: TestClient,
) -> None:
    """Changes in the database should immediately appear in the API."""
    with Session(engine) as session:
        product = Product(
            code="EDIT-1",
            seller_id=1,
            name="Original",
            price=100,
            stock_quantity=10,
            is_active=True,
        )

        session.add(product)
        session.commit()

    response = client.get("/api/v1/products")

    assert response.status_code == 200

    body = response.json()

    products = {
        product["code"]: product
        for product in body["data"]
    }

    assert "EDIT-1" in products
    assert products["EDIT-1"]["name"] == "Original"

    with Session(engine) as session:
        product = session.get(Product, 1)

        if product is not None:
            product.name = "Updated"
            session.add(product)
            session.commit()

    response = client.get("/api/v1/products")

    assert response.status_code == 200


def test_seeded_catalog_pages_do_not_overlap(
    client: TestClient,
) -> None:
    """Adjacent seeded catalog pages should contain different products."""
    seed_products()

    page_1 = client.get(
        "/api/v1/products?page=1&limit=10"
    ).json()

    page_2 = client.get(
        "/api/v1/products?page=2&limit=10"
    ).json()

    ids_1 = {
        product["id"]
        for product in page_1["data"]
    }

    ids_2 = {
        product["id"]
        for product in page_2["data"]
    }

    assert ids_1.isdisjoint(ids_2)


def test_list_products_database_failure_returns_500() -> None:
    """Unexpected database failures should return a controlled 500 error."""

    class BrokenSession:
        def exec(self, *_args, **_kwargs):
            raise SQLAlchemyError(
                "simulated database failure"
            )

    def broken_session():
        yield BrokenSession()

    app = create_app()

    app.dependency_overrides[get_session] = broken_session

    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/v1/products"
            )

        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "code": "ERR_DATABASE_FAILURE",
                "message": CATALOG_ERROR_MESSAGE,
            }
        }

    finally:
        app.dependency_overrides.clear()
