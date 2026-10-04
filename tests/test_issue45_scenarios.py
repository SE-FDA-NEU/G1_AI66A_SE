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
    """AC 1: When a guest visits the marketplace, active products stored in
    the database are fetched and returned via GET /api/v1/products.
    """

    def test_products_endpoint_returns_200(self, seeded_client: TestClient):
        response = seeded_client.get("/api/v1/products")
        assert response.status_code == 200

    def test_response_contains_data_and_meta_keys(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products").json()
        assert "data" in body, "Response must contain 'data' key"
        assert "meta" in body, "Response must contain 'meta' key"
        assert isinstance(body["data"], list)
        assert isinstance(body["meta"], dict)

    def test_products_are_returned_from_database(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products").json()
        assert len(body["data"]) > 0, "Seeded database must return at least 1 product"

    def test_product_record_has_expected_fields(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products").json()
        first = body["data"][0]
        expected_fields = {"id", "code", "name", "price", "stock_quantity", "stock_status"}
        missing = expected_fields - set(first.keys())
        assert not missing, f"Product record missing required fields: {missing}"

    def test_meta_reflects_real_total(self, seeded_client: TestClient):
        with Session(engine) as session:
            stmt = select(Product).where(Product.is_active.is_(True))
            count_in_db = len(session.exec(stmt).all())
        body = seeded_client.get("/api/v1/products?limit=100").json()
        assert body["meta"]["total"] == count_in_db

    def test_product_prices_are_positive_numbers(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products").json()
        for prod in body["data"]:
            assert isinstance(prod["price"], (int, float))
            assert prod["price"] > 0, f"Product {prod['name']} has non-positive price"


# ===========================================================================
# Scenario 2 — At least 10 seeded products
# ===========================================================================

class TestScenario2AtLeastTenSeedProducts:
    """AC 2: Database seed must contain at least 10 products, and the
    API must return them with realistic catalog data.
    """

    def test_at_least_10_products_in_database(self, seeded_client: TestClient):
        with Session(engine) as session:
            stmt = select(Product).where(Product.is_active.is_(True))
            total_active = len(session.exec(stmt).all())
        assert total_active >= 10, f"Expected >= 10 products, found {total_active}"

    def test_at_least_10_products_displayed_on_default_page(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products?limit=20").json()
        assert len(body["data"]) >= 10, (
            f"Expected >= 10 products in response data, got {len(body['data'])}"
        )

    def test_displayed_products_match_database_records(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products?limit=100").json()
        with Session(engine) as session:
            stmt = select(Product).where(Product.is_active.is_(True))
            db_codes = {p.code for p in session.exec(stmt).all()}
        api_codes = {p["code"] for p in body["data"]}
        assert api_codes == db_codes, "API codes do not match database codes"

    def test_products_have_unique_ids(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products?limit=100").json()
        ids = [p["id"] for p in body["data"]]
        assert len(ids) == len(set(ids)), "Product IDs must all be unique"


# ===========================================================================
# Scenario 3 — No hard-coded product array
# ===========================================================================

class TestScenario3NoHardCodedProductArray:
    """AC 3: Verify the API dynamically queries the database, NOT returning
    a static or hard-coded list of items.
    """

    def test_products_endpoint_hits_database(self, client: TestClient):
        with Session(engine) as session:
            custom_product = Product(
                code="DYNAMIC-999",
                name="Dynamic Custom Item",
                description="Should only appear when in DB",
                price=99000,
                stock_quantity=5,
                is_active=True,
            )
            session.add(custom_product)
            session.commit()

        body = client.get("/api/v1/products").json()
        names = [p["name"] for p in body["data"]]
        assert "Dynamic Custom Item" in names, "Dynamic database row not returned by API"

    def test_empty_db_returns_zero_products(self, empty_client: TestClient):
        body = empty_client.get("/api/v1/products").json()
        assert body["data"] == [], (
            "Empty database must return empty list; if items appear, they are hardcoded"
        )
        assert body["meta"]["total"] == 0

    def test_product_count_changes_reflect_in_response(self, client: TestClient):
        with Session(engine) as session:
            for i in range(3):
                session.add(Product(
                    code=f"ITEM-{i}",
                    name=f"Item {i}",
                    price=10000 * (i + 1),
                    stock_quantity=10,
                    is_active=True,
                ))
            session.commit()

        res1 = client.get("/api/v1/products").json()
        assert res1["meta"]["total"] == 3

        with Session(engine) as session:
            session.add(Product(
                code="ITEM-EXTRA",
                name="Extra Item",
                price=50000,
                stock_quantity=10,
                is_active=True,
            ))
            session.commit()

        res2 = client.get("/api/v1/products").json()
        assert res2["meta"]["total"] == 4, (
            "Adding a DB record must immediately increment total (proof of dynamic DB query)"
        )


# ===========================================================================
# Scenario 4 — Empty database
# ===========================================================================

class TestScenario4EmptyDatabase:
    """AC 4: When the products table is completely empty, the API must return
    HTTP 200 with an empty data array and total=0 without crashing or 500.
    """

    def test_empty_db_returns_200_not_500(self, empty_client: TestClient):
        response = empty_client.get("/api/v1/products")
        assert response.status_code == 200, (
            f"Expected 200 on empty DB, got {response.status_code}"
        )

    def test_empty_db_returns_empty_data_list(self, empty_client: TestClient):
        body = empty_client.get("/api/v1/products").json()
        assert body["data"] == [], f"Expected empty list, got: {body['data']}"

    def test_empty_db_meta_total_is_zero(self, empty_client: TestClient):
        body = empty_client.get("/api/v1/products").json()
        assert body["meta"]["total"] == 0

    def test_empty_db_meta_total_pages_is_zero(self, empty_client: TestClient):
        body = empty_client.get("/api/v1/products").json()
        assert body["meta"]["total_pages"] == 0

    def test_empty_db_response_structure_is_valid(self, empty_client: TestClient):
        body = empty_client.get("/api/v1/products").json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["current_page"] == 1
        assert body["meta"]["limit"] == 20

    def test_pagination_on_empty_db_does_not_crash(self, empty_client: TestClient):
        for page in (1, 2, 99):
            response = empty_client.get(f"/api/v1/products?page={page}&limit=10")
            assert response.status_code == 200
            body = response.json()
            assert body["data"] == []
            assert body["meta"]["total"] == 0


# ===========================================================================
# Pagination Correctness
# ===========================================================================

class TestPaginationCorrectness:
    """Validate boundary cases and pagination math."""

    def test_pagination_limit_respected(self, seeded_client: TestClient):
        for limit in (1, 5, 10):
            body = seeded_client.get(f"/api/v1/products?page=1&limit={limit}").json()
            assert len(body["data"]) <= limit
            assert body["meta"]["limit"] == limit

    def test_pagination_page_2_returns_correct_slice(self, seeded_client: TestClient):
        p1 = seeded_client.get("/api/v1/products?page=1&limit=5").json()
        p2 = seeded_client.get("/api/v1/products?page=2&limit=5").json()
        ids_p1 = {x["id"] for x in p1["data"]}
        ids_p2 = {x["id"] for x in p2["data"]}
        assert ids_p1.isdisjoint(ids_p2), "Pages 1 and 2 must not have overlapping products"

    def test_total_pages_calculated_correctly(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products?limit=5").json()
        total = body["meta"]["total"]
        expected_pages = math.ceil(total / 5)
        assert body["meta"]["total_pages"] == expected_pages

    def test_meta_current_page_matches_request(self, seeded_client: TestClient):
        body = seeded_client.get("/api/v1/products?page=2&limit=5").json()
        assert body["meta"]["current_page"] == 2
