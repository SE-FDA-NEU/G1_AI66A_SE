"""Task 5 — Independent testing: verify all 4 Scenarios from Issue #45.

Scenarios verified:
  Scenario 1 — Display products from database
  Scenario 2 — At least 10 seeded products
  Scenario 3 — No hard-coded product array
  Scenario 4 — Empty database

Uses project's SQLModel database engine and fixtures from conftest.py.
"""

import math

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from src.database import engine
from src.models.product import Product
from src.seed import seed_products


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure clean database before each test and cleanup after."""
    with Session(engine) as session:
        session.exec(delete(Product))
        session.commit()

    yield

    with Session(engine) as session:
        session.exec(delete(Product))
        session.commit()


@pytest.fixture
def seeded_client(client: TestClient):
    """Client with seed products loaded (at least 10 products)."""
    seed_products()
    return client


@pytest.fixture
def empty_client(client: TestClient):
    """Client with zero products in database."""
    return client


# ===========================================================================
# Scenario 1 — Display products from database
# ===========================================================================


class TestScenario1DisplayProductsFromDatabase:
    """AC 1: Active products stored in the database are returned by the API."""

    def test_products_endpoint_returns_200(
        self,
        seeded_client: TestClient,
    ):
        response = seeded_client.get(
            "/api/v1/products"
        )

        assert response.status_code == 200

    def test_response_contains_data_and_meta_keys(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products"
        ).json()

        assert "data" in body
        assert "meta" in body

        assert isinstance(
            body["data"],
            list,
        )

        assert isinstance(
            body["meta"],
            dict,
        )

    def test_products_are_returned_from_database(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products"
        ).json()

        assert len(body["data"]) > 0

    def test_product_record_has_expected_fields(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products"
        ).json()

        first = body["data"][0]

        expected_fields = {
            "id",
            "code",
            "name",
            "price",
            "stock_quantity",
            "stock_status",
        }

        missing = (
            expected_fields
            - set(first.keys())
        )

        assert not missing

    def test_meta_reflects_real_total(
        self,
        seeded_client: TestClient,
    ):
        with Session(engine) as session:
            stmt = select(
                Product
            ).where(
                Product.is_active.is_(True)
            )

            count_in_db = len(
                session.exec(stmt).all()
            )

        body = seeded_client.get(
            "/api/v1/products?limit=100"
        ).json()

        assert (
            body["meta"]["total"]
            == count_in_db
        )

    def test_product_prices_are_positive_numbers(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products"
        ).json()

        for product in body["data"]:
            assert isinstance(
                product["price"],
                (int, float),
            )

            assert product["price"] > 0


# ===========================================================================
# Scenario 2 — At least 10 seeded products
# ===========================================================================


class TestScenario2AtLeastTenSeedProducts:
    """AC 2: Seed must contain at least 10 products."""

    def test_at_least_10_products_in_database(
        self,
        seeded_client: TestClient,
    ):
        with Session(engine) as session:
            stmt = select(
                Product
            ).where(
                Product.is_active.is_(True)
            )

            total_active = len(
                session.exec(stmt).all()
            )

        assert total_active >= 10

    def test_at_least_10_products_displayed_on_default_page(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products?limit=20"
        ).json()

        assert len(body["data"]) >= 10

    def test_displayed_products_match_database_records(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products?limit=100"
        ).json()

        with Session(engine) as session:
            stmt = select(
                Product
            ).where(
                Product.is_active.is_(True)
            )

            db_codes = {
                product.code
                for product in session.exec(
                    stmt
                ).all()
            }

        api_codes = {
            product["code"]
            for product in body["data"]
        }

        assert api_codes == db_codes

    def test_products_have_unique_ids(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products?limit=100"
        ).json()

        ids = [
            product["id"]
            for product in body["data"]
        ]

        assert len(ids) == len(set(ids))


# ===========================================================================
# Scenario 3 — No hard-coded product array
# ===========================================================================


class TestScenario3NoHardCodedProductArray:
    """AC 3: API dynamically queries the database."""

    def test_products_endpoint_hits_database(
        self,
        client: TestClient,
    ):
        with Session(engine) as session:
            custom_product = Product(
                code="DYNAMIC-999",
                seller_id=1,
                name="Dynamic Custom Item",
                description=(
                    "Should only appear when in DB"
                ),
                price=99000,
                stock_quantity=5,
                is_active=True,
            )

            session.add(custom_product)
            session.commit()

        body = client.get(
            "/api/v1/products"
        ).json()

        names = [
            product["name"]
            for product in body["data"]
        ]

        assert (
            "Dynamic Custom Item"
            in names
        )

    def test_empty_db_returns_zero_products(
        self,
        empty_client: TestClient,
    ):
        body = empty_client.get(
            "/api/v1/products"
        ).json()

        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_product_count_changes_reflect_in_response(
        self,
        client: TestClient,
    ):
        with Session(engine) as session:
            for index in range(3):
                session.add(
                    Product(
                        code=f"ITEM-{index}",
                        seller_id=1,
                        name=f"Item {index}",
                        price=(
                            10000
                            * (index + 1)
                        ),
                        stock_quantity=10,
                        is_active=True,
                    )
                )

            session.commit()

        first_response = client.get(
            "/api/v1/products"
        ).json()

        assert (
            first_response["meta"]["total"]
            == 3
        )

        with Session(engine) as session:
            session.add(
                Product(
                    code="ITEM-EXTRA",
                    seller_id=1,
                    name="Extra Item",
                    price=50000,
                    stock_quantity=10,
                    is_active=True,
                )
            )

            session.commit()

        second_response = client.get(
            "/api/v1/products"
        ).json()

        assert (
            second_response["meta"]["total"]
            == 4
        )


# ===========================================================================
# Scenario 4 — Empty database
# ===========================================================================


class TestScenario4EmptyDatabase:
    """AC 4: Empty database returns an empty catalog, not an error."""

    def test_empty_db_returns_200_not_500(
        self,
        empty_client: TestClient,
    ):
        response = empty_client.get(
            "/api/v1/products"
        )

        assert response.status_code == 200

    def test_empty_db_returns_empty_data_list(
        self,
        empty_client: TestClient,
    ):
        body = empty_client.get(
            "/api/v1/products"
        ).json()

        assert body["data"] == []

    def test_empty_db_meta_total_is_zero(
        self,
        empty_client: TestClient,
    ):
        body = empty_client.get(
            "/api/v1/products"
        ).json()

        assert body["meta"]["total"] == 0

    def test_empty_db_meta_total_pages_is_zero(
        self,
        empty_client: TestClient,
    ):
        body = empty_client.get(
            "/api/v1/products"
        ).json()

        assert (
            body["meta"]["total_pages"]
            == 0
        )

    def test_empty_db_response_structure_is_valid(
        self,
        empty_client: TestClient,
    ):
        body = empty_client.get(
            "/api/v1/products"
        ).json()

        assert "data" in body
        assert "meta" in body

        assert (
            body["meta"]["current_page"]
            == 1
        )

        assert body["meta"]["limit"] == 20

    def test_pagination_on_empty_db_does_not_crash(
        self,
        empty_client: TestClient,
    ):
        for page in (1, 2, 99):
            response = empty_client.get(
                (
                    "/api/v1/products"
                    f"?page={page}&limit=10"
                )
            )

            assert response.status_code == 200

            body = response.json()

            assert body["data"] == []
            assert body["meta"]["total"] == 0


# ===========================================================================
# Pagination Correctness
# ===========================================================================


class TestPaginationCorrectness:
    """Validate pagination boundary cases and calculations."""

    def test_pagination_limit_respected(
        self,
        seeded_client: TestClient,
    ):
        for limit in (1, 5, 10):
            body = seeded_client.get(
                (
                    "/api/v1/products"
                    f"?page=1&limit={limit}"
                )
            ).json()

            assert (
                len(body["data"])
                <= limit
            )

            assert (
                body["meta"]["limit"]
                == limit
            )

    def test_pagination_page_2_returns_correct_slice(
        self,
        seeded_client: TestClient,
    ):
        page_1 = seeded_client.get(
            "/api/v1/products?page=1&limit=5"
        ).json()

        page_2 = seeded_client.get(
            "/api/v1/products?page=2&limit=5"
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

    def test_total_pages_calculated_correctly(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products?limit=5"
        ).json()

        total = body["meta"]["total"]

        expected_pages = math.ceil(
            total / 5
        )

        assert (
            body["meta"]["total_pages"]
            == expected_pages
        )

    def test_meta_current_page_matches_request(
        self,
        seeded_client: TestClient,
    ):
        body = seeded_client.get(
            "/api/v1/products?page=2&limit=5"
        ).json()

        assert (
            body["meta"]["current_page"]
            == 2
        )
