"""Tests for US11: Search, Filter, Sort, and Paginate the Product Catalog (Issue #102).

Acceptance criteria covered:
- AC1: Keyword search across product names or descriptions, combinable with other filters.
- AC2: Category filter including descendant categories, seller filter, min/max price,
       min rating, and stock filters.
- AC3: Sorting by newest, bestselling, price_asc, price_desc, rating_desc with pagination
       and total_items, total_pages, current_page metadata.
- AC4: Helpful empty states for no matches and field-level validation for invalid price bounds.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, SQLModel, select

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.category import Category
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.orders import CheckoutRequest
from src.services.orders import checkout
from tests.cart_db import enable_foreign_keys


@pytest.fixture
def discovery_engine(tmp_path):
    """Isolated database engine with SQLite foreign key enforcement enabled."""
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog_discovery.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(discovery_engine) -> TestClient:
    """FastAPI test client overriding get_session with the isolated discovery engine."""
    app = create_app()

    def sessions():
        with Session(discovery_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_catalog(discovery_engine):
    """Populate a structured category tree, multiple sellers, and distinct products."""
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    with Session(discovery_engine) as session:
        # Category tree:
        # 1. Electronics (Root)
        #    └── 2. Computers (Child)
        #           ├── 3. Laptops (Grandchild)
        #           └── 4. Accessories (Grandchild)
        # 5. Office Supplies (Root)
        c1 = Category(id=1, name="Electronics", slug="electronics", parent_id=None)
        c2 = Category(id=2, name="Computers", slug="computers", parent_id=1)
        c3 = Category(id=3, name="Laptops", slug="laptops", parent_id=2)
        c4 = Category(id=4, name="Accessories", slug="accessories", parent_id=2)
        c5 = Category(id=5, name="Office Supplies", slug="office", parent_id=None)
        session.add_all([c1, c2, c3, c4, c5])

        # Ensure sellers exist in users table
        seller1 = session.get(User, 1)
        if seller1 is None:
            seller1 = User(id=1, name="Primary Seller", email="seller1@example.com", role="seller")
            session.add(seller1)
        seller2 = session.get(User, 2)
        if seller2 is None:
            seller2 = User(
                id=2, name="Secondary Seller", email="seller2@example.com", role="seller"
            )
            session.add(seller2)
        session.commit()

        # Products spanning categories, sellers, ratings, prices, sales counts, created dates
        products = [
            Product(
                id=1,
                code="P-LAP-PRO",
                seller_id=1,
                name="Pro Ultrabook Laptop",
                description="High performance aluminium laptop for developers and creatives",
                price=25000000,
                stock_quantity=10,
                reserved_stock=0,
                is_active=True,
            ),
            Product(
                id=2,
                code="P-LAP-AIR",
                seller_id=2,
                name="Slim Travel Laptop",
                description="Lightweight notebook computer with all-day battery life",
                price=18000000,
                stock_quantity=5,
                reserved_stock=0,
                is_active=True,
            ),
            Product(
                id=3,
                code="P-ACC-MOUSE",
                seller_id=1,
                name="Ergonomic Optical Mouse",
                description="Precision wireless computer mouse with silent switches",
                price=450000,
                stock_quantity=30,
                reserved_stock=2,
                is_active=True,
            ),
            Product(
                id=4,
                code="P-ACC-KEYB",
                seller_id=2,
                name="Compact Mechanical Keyboard",
                description="Backlit desktop keyboard featuring custom linear switches",
                price=1200000,
                stock_quantity=20,
                reserved_stock=0,
                is_active=True,
            ),
            Product(
                id=5,
                code="P-OFF-CHAIR",
                seller_id=1,
                name="Mesh Office Chair",
                description="Breathable ergonomic desk chair with lumbar support",
                price=3200000,
                stock_quantity=8,
                reserved_stock=0,
                is_active=True,
            ),
            Product(
                id=6,
                code="P-OFF-OUT",
                seller_id=1,
                name="Gel Pen Set",
                description="Smooth writing black ink office pens",
                price=50000,
                stock_quantity=0,  # Out of stock
                reserved_stock=0,
                is_active=True,
            ),
        ]
        session.add_all(products)

        metadata = [
            ProductMetadata(
                product_id=1,
                category_id=3,  # Grandchild of Electronics
                rating=4.9,
                sales_count=150,
                created_at=now - timedelta(days=1),
            ),
            ProductMetadata(
                product_id=2,
                category_id=3,  # Grandchild of Electronics
                rating=4.5,
                sales_count=320,
                created_at=now - timedelta(days=5),
            ),
            ProductMetadata(
                product_id=3,
                category_id=4,  # Grandchild of Electronics
                rating=4.7,
                sales_count=500,
                created_at=now - timedelta(days=2),
            ),
            ProductMetadata(
                product_id=4,
                category_id=4,  # Grandchild of Electronics
                rating=4.2,
                sales_count=90,
                created_at=now - timedelta(days=10),
            ),
            ProductMetadata(
                product_id=5,
                category_id=5,  # Office Supplies
                rating=3.8,
                sales_count=60,
                created_at=now - timedelta(days=20),
            ),
            ProductMetadata(
                product_id=6,
                category_id=5,  # Office Supplies
                rating=4.0,
                sales_count=1000,
                created_at=now - timedelta(days=30),
            ),
        ]
        session.add_all(metadata)
        session.commit()


# ==============================================================================
# AC1: Keyword search across product names or descriptions
# ==============================================================================


def test_search_matches_product_name(client: TestClient, sample_catalog):
    """Keyword matching product title returns matching items."""
    res = client.get("/api/v1/products?search=Ultrabook")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["code"] == "P-LAP-PRO"


def test_search_matches_product_description(client: TestClient, sample_catalog):
    """Keyword found in description but not in product name returns matching items."""
    res = client.get("/api/v1/products?search=creatives")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["code"] == "P-LAP-PRO"


def test_search_can_be_combined_with_category_and_price_filters(
    client: TestClient, sample_catalog
):
    """Search query combined with category and max_price filters simultaneously."""
    res = client.get("/api/v1/products?search=Laptop&category_id=1&max_price=20000000")
    assert res.status_code == 200
    body = res.json()
    # Both laptops have "Laptop" in name/desc and belong to category 1 descendants,
    # but only P-LAP-AIR has price <= 20,000,000.
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["code"] == "P-LAP-AIR"


# ==============================================================================
# AC2: Category hierarchy and multi-dimensional filters
# ==============================================================================


def test_category_filter_includes_all_descendant_categories(
    client: TestClient, sample_catalog
):
    """Filtering by top-level category (Electronics=1) includes laptops (3) and accessories (4)."""
    res = client.get("/api/v1/products?category_id=1")
    assert res.status_code == 200
    body = res.json()
    codes = {p["code"] for p in body["data"]}
    assert codes == {"P-LAP-PRO", "P-LAP-AIR", "P-ACC-MOUSE", "P-ACC-KEYB"}
    assert "P-OFF-CHAIR" not in codes


def test_category_filter_includes_intermediate_descendants(
    client: TestClient, sample_catalog
):
    """Filtering by mid-level category (Computers=2) returns both laptops and accessories."""
    res = client.get("/api/v1/products?category_id=2")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()["data"]}
    assert codes == {"P-LAP-PRO", "P-LAP-AIR", "P-ACC-MOUSE", "P-ACC-KEYB"}


def test_category_filter_leaf_category_only_returns_direct_items(
    client: TestClient, sample_catalog
):
    """Filtering by leaf category (Laptops=3) returns only laptops."""
    res = client.get("/api/v1/products?category_id=3")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()["data"]}
    assert codes == {"P-LAP-PRO", "P-LAP-AIR"}


def test_seller_filter(client: TestClient, sample_catalog):
    """Filter products by seller ID."""
    res = client.get("/api/v1/products?seller_id=2")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()["data"]}
    assert codes == {"P-LAP-AIR", "P-ACC-KEYB"}


def test_price_range_filters(client: TestClient, sample_catalog):
    """Filter by minimum and maximum price bounds."""
    res = client.get("/api/v1/products?min_price=1000000&max_price=20000000")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()["data"]}
    assert codes == {"P-LAP-AIR", "P-ACC-KEYB", "P-OFF-CHAIR"}


def test_min_rating_filter(client: TestClient, sample_catalog):
    """Filter products by minimum customer rating."""
    res = client.get("/api/v1/products?min_rating=4.5")
    assert res.status_code == 200
    codes = {p["code"] for p in res.json()["data"]}
    assert codes == {"P-LAP-PRO", "P-LAP-AIR", "P-ACC-MOUSE"}


def test_stock_filter_active_and_out_of_stock(client: TestClient, sample_catalog):
    """In-stock=true returns only in-stock products; in-stock=false returns all active products."""
    res_in_stock = client.get("/api/v1/products?category_id=5&in_stock=true")
    assert res_in_stock.status_code == 200
    assert [p["code"] for p in res_in_stock.json()["data"]] == ["P-OFF-CHAIR"]

    res_all_stock = client.get("/api/v1/products?category_id=5&in_stock=false")
    assert res_all_stock.status_code == 200
    codes = {p["code"] for p in res_all_stock.json()["data"]}
    assert codes == {"P-OFF-CHAIR", "P-OFF-OUT"}


# ==============================================================================
# AC3: Sorting options and pagination metadata
# ==============================================================================


def test_sort_newest(client: TestClient, sample_catalog):
    """Sort newest puts the most recently created items first."""
    res = client.get("/api/v1/products?sort=newest&limit=10")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    # Pro (1 day ago), Mouse (2 days ago), Air (5 days ago), Keyb (10 days ago), Chair (20 days ago)
    assert codes == ["P-LAP-PRO", "P-ACC-MOUSE", "P-LAP-AIR", "P-ACC-KEYB", "P-OFF-CHAIR"]


def test_sort_bestselling(client: TestClient, sample_catalog):
    """Sort bestselling puts highest sales_count first."""
    res = client.get("/api/v1/products?sort=bestselling&limit=10")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    # Mouse (500), Air (320), Pro (150), Keyb (90), Chair (60)
    assert codes == ["P-ACC-MOUSE", "P-LAP-AIR", "P-LAP-PRO", "P-ACC-KEYB", "P-OFF-CHAIR"]


def test_sort_price_asc_and_desc(client: TestClient, sample_catalog):
    """Sort by price ascending and descending."""
    res_asc = client.get("/api/v1/products?sort=price_asc&limit=10")
    codes_asc = [p["code"] for p in res_asc.json()["data"]]
    assert codes_asc == ["P-ACC-MOUSE", "P-ACC-KEYB", "P-OFF-CHAIR", "P-LAP-AIR", "P-LAP-PRO"]

    res_desc = client.get("/api/v1/products?sort=price_desc&limit=10")
    codes_desc = [p["code"] for p in res_desc.json()["data"]]
    assert codes_desc == ["P-LAP-PRO", "P-LAP-AIR", "P-OFF-CHAIR", "P-ACC-KEYB", "P-ACC-MOUSE"]


def test_sort_rating_desc(client: TestClient, sample_catalog):
    """Sort by highest rating descending."""
    res = client.get("/api/v1/products?sort=rating_desc&limit=10")
    codes = [p["code"] for p in res.json()["data"]]
    # Pro (4.9), Mouse (4.7), Air (4.5), Keyb (4.2), Chair (3.8)
    assert codes == ["P-LAP-PRO", "P-ACC-MOUSE", "P-LAP-AIR", "P-ACC-KEYB", "P-OFF-CHAIR"]


def test_pagination_returns_total_items_total_pages_current_page(
    client: TestClient, sample_catalog
):
    """API metadata conforms to US11 specification

    containing total_items, total_pages, current_page.
    """
    res = client.get("/api/v1/products?limit=2&page=2&sort=price_asc")
    assert res.status_code == 200
    meta = res.json()["meta"]
    assert meta["current_page"] == 2
    assert meta["limit"] == 2
    assert meta["total_items"] == 5
    assert meta["total_pages"] == 3
    # Page 2 with 2 per page: 3rd and 4th cheapest items
    codes = [p["code"] for p in res.json()["data"]]
    assert codes == ["P-OFF-CHAIR", "P-LAP-AIR"]


# ==============================================================================
# AC4: Empty states and field-level validation for invalid bounds
# ==============================================================================


def test_invalid_price_bounds_returns_field_level_validation_error(
    client: TestClient, sample_catalog
):
    """When min_price > max_price, API returns 422 validation error."""
    res = client.get("/api/v1/products?min_price=500000&max_price=100000")
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "ERR_VALIDATION"
    assert "Minimum price cannot be greater than maximum price" in body["error"]["message"]


def test_invalid_sort_parameter_returns_validation_error(
    client: TestClient, sample_catalog
):
    """Unsupported sort option returns 422 validation error."""
    res = client.get("/api/v1/products?sort=random_sort")
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "ERR_VALIDATION"


def test_filters_returning_no_products_produce_helpful_empty_response(
    client: TestClient, sample_catalog
):
    """Query that matches no product yields empty data list with 0 total items."""
    res = client.get("/api/v1/products?search=nonexistentkeyword123")
    assert res.status_code == 200
    body = res.json()
    assert body["data"] == []
    assert body["meta"]["total_items"] == 0
    assert body["meta"]["total_pages"] == 0
    assert body["meta"]["current_page"] == 1


# ==============================================================================
# Discovery helpers: categories and sellers endpoints
# ==============================================================================


def test_categories_endpoint_lists_hierarchy(client: TestClient, sample_catalog):
    """GET /api/v1/categories returns all categories for discovery controls."""
    res = client.get("/api/v1/categories")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 5
    slugs = {item["slug"] for item in items}
    assert "electronics" in slugs and "laptops" in slugs


def test_sellers_endpoint_lists_sellers(client: TestClient, sample_catalog):
    """GET /api/v1/sellers returns registered sellers."""
    res = client.get("/api/v1/sellers")
    assert res.status_code == 200
    sellers = res.json()
    assert len(sellers) >= 2
    assert any(s["name"] == "Secondary Seller" for s in sellers)
    assert all(isinstance(s["id"], int) and isinstance(s["name"], str) for s in sellers)


# ==============================================================================
# UI elements verification
# ==============================================================================


def test_products_page_contains_all_discovery_controls(client: TestClient):
    """
    Frontend HTML includes all discovery inputs, filters, sort dropdown, and empty state reset
    button.
    """
    html = client.get("/products").text
    assert 'id="products-search"' in html
    assert 'id="product-search-input"' in html
    assert 'id="filter-category"' in html
    assert 'id="filter-seller"' in html
    assert 'id="filter-min-price"' in html
    assert 'id="filter-max-price"' in html
    assert 'id="price-error"' in html
    assert 'id="filter-rating"' in html
    assert 'id="filter-in-stock"' in html
    assert 'id="catalog-sort"' in html
    assert 'id="apply-filters"' in html
    assert 'id="reset-filters"' in html
    assert 'id="products-reset-empty"' in html


# ==============================================================================
# Regression tests for code review change requests
# ==============================================================================


def test_stock_filter_false_returns_all_active_products(client: TestClient, sample_catalog):
    """Setting in_stock=false returns all active products (both in-stock and out-of-stock)."""
    # Under Office Supplies (cat 5), we have P-OFF-CHAIR (stock=2) and P-OFF-OUT (stock=0)
    res_in_stock = client.get("/api/v1/products?category_id=5&in_stock=true")
    assert res_in_stock.status_code == 200
    assert [p["code"] for p in res_in_stock.json()["data"]] == ["P-OFF-CHAIR"]

    res_all = client.get("/api/v1/products?category_id=5&in_stock=false")
    assert res_all.status_code == 200
    codes = {p["code"] for p in res_all.json()["data"]}
    assert codes == {"P-OFF-CHAIR", "P-OFF-OUT"}


def test_seller_product_creation_creates_metadata_and_integrates_discovery(
    client: TestClient, discovery_engine, sample_catalog
):
    """
    Newly created products through seller API receive ProductMetadata and integrate with
    filters.
    """
    with Session(discovery_engine) as session:
        seller = session.get(User, 1)
        token = create_access_token(seller)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "Mechanical Keyboard RGB",
        "description": "Ergonomic gaming mechanical keyboard with per-key RGB",
        "price": 1250000,
        "stock_quantity": 15,
        "image_url": "https://example.com/keyboard.jpg",
        "category_id": 4,  # Accessories
    }

    create_res = client.post("/api/v1/seller/products", json=payload, headers=headers)
    assert create_res.status_code == 201
    created_product = create_res.json()["data"]
    code = created_product["code"]

    # Verify ProductMetadata row was created in DB
    with Session(discovery_engine) as session:
        meta = session.get(ProductMetadata, created_product["id"])
        assert meta is not None
        assert meta.category_id == 4
        assert meta.sales_count == 0
        assert meta.rating == 0.0
        assert meta.created_at is not None

    # Verify discovery catalog filters include the new seller product
    cat_res = client.get("/api/v1/products?category_id=4")
    assert cat_res.status_code == 200
    cat_codes = {p["code"] for p in cat_res.json()["data"]}
    assert code in cat_codes

    # Rating filter (min_rating=0.0) must include the new product
    rating_res = client.get("/api/v1/products?min_rating=0.0&category_id=4")
    assert rating_res.status_code == 200
    rating_codes = {p["code"] for p in rating_res.json()["data"]}
    assert code in rating_codes

    # Refuse invalid non-existent category_id
    invalid_payload = {
        "name": "Invalid Category Product",
        "description": "Valid description for testing",
        "price": 500000,
        "stock_quantity": 5,
        "image_url": "https://example.com/invalid.jpg",
        "category_id": 99999,
    }
    invalid_res = client.post("/api/v1/seller/products", json=invalid_payload, headers=headers)
    assert invalid_res.status_code == 422


def test_product_metadata_foreign_key_constraints(discovery_engine, sample_catalog):
    """ProductMetadata enforces foreign key constraints on product_id and category_id."""
    # Invalid product_id
    with pytest.raises(IntegrityError):
        with Session(discovery_engine) as session:
            bad_meta = ProductMetadata(
                product_id=999999,
                category_id=1,
                rating=4.5,
                sales_count=10,
            )
            session.add(bad_meta)
            session.commit()

    # Invalid category_id
    with pytest.raises(IntegrityError):
        with Session(discovery_engine) as session:
            bad_meta = ProductMetadata(
                product_id=1,
                category_id=999999,
                rating=4.5,
                sales_count=10,
            )
            session.add(bad_meta)
            session.commit()


def test_metadata_consistency_order_checkout_and_cancellation(
    client: TestClient, discovery_engine, sample_catalog
):
    """Order checkout increments ProductMetadata.sales_count, cancellation restores it."""
    with Session(discovery_engine) as session:
        buyer = User(id=10, name="Discovery Buyer", email="buyer@test.local", role="buyer")
        session.add(buyer)
        # Create a test product with 0 sales
        product = Product(
            id=50,
            code="P-TEST-SALES",
            seller_id=1,
            name="Sales Test Device",
            description="Testing sales synchronization",
            price=100000,
            stock_quantity=20,
            reserved_stock=0,
            is_active=True,
        )
        session.add(product)
        session.commit()

        # Add cart item for buyer
        cart_item = CartItem(id=1, buyer_id=buyer.id, product_id=product.id, quantity=3)
        session.add(cart_item)
        session.commit()

        # Execute checkout
        checkout_req = CheckoutRequest(
            recipient_name="Discovery Buyer",
            delivery_address="123 Discovery Road",
            phone_number="0912345678",
        )
        receipt_data, _ = checkout(session, buyer.id, checkout_req, key="disc-checkout-key-1")
        session.commit()

        # Check metadata sales_count incremented
        meta = session.get(ProductMetadata, product.id)
        assert meta is not None
        assert meta.sales_count == 3

        # Seller cancels order
        seller = session.get(User, 1)
        seller_token = create_access_token(seller)

        seller_order = session.exec(
            select(SellerOrder).where(SellerOrder.seller_id == 1)
        ).first()
        assert seller_order is not None
        seller_order_id = seller_order.id

    seller_headers = {"Authorization": f"Bearer {seller_token}"}
    patch_res = client.patch(
        f"/api/v1/seller/orders/{seller_order_id}/status",
        json={"status": "CANCELLED"},
        headers=seller_headers,
    )
    assert patch_res.status_code == 200

    # Check sales_count restored/decremented
    with Session(discovery_engine) as session:
        meta = session.get(ProductMetadata, product.id)
        assert meta is not None
        assert meta.sales_count == 0


def test_categories_and_sellers_error_handling_contracts(client: TestClient):
    """
    Categories and sellers endpoints return 500 with ERR_DATABASE_FAILURE upon database failure.
    """
    with patch("sqlmodel.Session.exec", side_effect=SQLAlchemyError("Simulated DB down")):
        cat_res = client.get("/api/v1/categories")
        assert cat_res.status_code == 500
        assert cat_res.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
        assert "categories" in cat_res.json()["error"]["message"].lower()

        seller_res = client.get("/api/v1/sellers")
        assert seller_res.status_code == 500
        assert seller_res.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
        assert "sellers" in seller_res.json()["error"]["message"].lower()


def test_frontend_products_js_race_condition_handling(client: TestClient):
    """
    Frontend products.js uses AbortController and request ID sequence tracking for rapid filter
    changes.
    """
    script = client.get("/static/products.js").text.replace("\r\n", "\n")
    assert "activeAbortController" in script
    assert "currentRequestId" in script
    assert "activeAbortController.abort()" in script
    assert "requestId !== currentRequestId" in script
    assert "AbortError" in script


def test_frontend_products_js_request_scoped_abort_timeout(client: TestClient):
    """
    Frontend products.js timeout aborts the request-scoped controller, not the shared
    activeAbortController.
    """
    script = client.get("/static/products.js").text.replace("\r\n", "\n")
    assert "const controller = new AbortController();" in script
    assert "activeAbortController = controller;" in script
    assert "controller.abort()" in script
    assert "activeAbortController.abort()" in script  # only called to abort prior in-flight request
    # Timeout closure must call controller.abort(), not activeAbortController.abort()
    assert "setTimeout(() => {\n    controller.abort();\n  }, REQUEST_TIMEOUT_MS);" in script


def test_catalog_seed_does_not_assign_synthetic_metrics_to_existing_products(discovery_engine):
    """
    Existing products without metadata must not be assigned synthetic ratings, sales, or
    timestamps.
    """
    from src.seed import DEMO_DATE, seed_categories, seed_product_metadata

    with Session(discovery_engine) as session:
        seed_categories(session)
        # Create seller and an existing pre-discovery product
        seller = User(id=101, name="Existing Seller", email="seller101@test.local", role="seller")
        session.add(seller)
        session.flush()

        existing_prod = Product(
            id=101,
            code="P-REAL-EXISTING",
            seller_id=seller.id,
            name="Existing Real Product",
            description="Existing business product created before discovery metadata",
            price=500000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        sample_prod = Product(
            id=102,
            code="P-100",  # Seed catalog sample code
            seller_id=seller.id,
            name="Wireless Mouse",
            description="Sample catalog wireless mouse",
            price=180000,
            stock_quantity=15,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([existing_prod, sample_prod])
        session.commit()

        # Run seed_product_metadata on both
        seed_product_metadata(session, [existing_prod, sample_prod])
        session.commit()

        meta_existing = session.get(ProductMetadata, existing_prod.id)
        meta_sample = session.get(ProductMetadata, sample_prod.id)

        assert meta_existing is not None
        assert meta_sample is not None

        # Existing real product must receive clean defaults, NOT synthetic values
        assert meta_existing.rating == 0.0
        assert meta_existing.sales_count == 0
        assert meta_existing.category_id is None
        sample_created_utc = (
            meta_sample.created_at.replace(tzinfo=UTC)
            if meta_sample.created_at.tzinfo is None
            else meta_sample.created_at
        )
        assert sample_created_utc <= DEMO_DATE


def test_sort_newest_handles_null_timestamps_and_fallback_by_id(
    client: TestClient, discovery_engine
):
    """Sort newest orders by created_at DESC with Product.id DESC fallback without mixing types."""
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)
    with Session(discovery_engine) as session:
        seller = User(id=201, name="Sort Seller", email="sort_seller@test.local", role="seller")
        session.add(seller)
        session.flush()

        # Product 1: Newer timestamp
        p1 = Product(
            id=201,
            code="P-SORT-NEW",
            seller_id=seller.id,
            name="New Product",
            description="d",
            price=1000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        # Product 2: Older timestamp
        p2 = Product(
            id=202,
            code="P-SORT-OLD",
            seller_id=seller.id,
            name="Old Product",
            description="d",
            price=1000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        # Product 3: No metadata (smaller id)
        p3 = Product(
            id=203,
            code="P-SORT-NO-META-A",
            seller_id=seller.id,
            name="No Meta A",
            description="d",
            price=1000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        # Product 4: No metadata (larger id)
        p4 = Product(
            id=204,
            code="P-SORT-NO-META-B",
            seller_id=seller.id,
            name="No Meta B",
            description="d",
            price=1000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([p1, p2, p3, p4])
        session.flush()

        m1 = ProductMetadata(product_id=p1.id, rating=4.0, sales_count=10, created_at=now)
        m2 = ProductMetadata(
            product_id=p2.id, rating=4.0, sales_count=10, created_at=now - timedelta(days=5)
        )
        session.add_all([m1, m2])
        session.commit()

    res = client.get("/api/v1/products?seller_id=201&sort=newest")
    assert res.status_code == 200
    returned_codes = [p["code"] for p in res.json()["data"]]
    # Products with created_at come first (newest to oldest), then items without created_at by
    # ID desc
    assert returned_codes == ["P-SORT-NEW", "P-SORT-OLD", "P-SORT-NO-META-B", "P-SORT-NO-META-A"]


# ==============================================================================
# Comprehensive Catalog Query Tests (Story #102)
# ==============================================================================


# ------------------------------------------------------------------------------
# Combined Filters
# ------------------------------------------------------------------------------
def test_combined_query_matching_single_item(client: TestClient, sample_catalog):
    """Multiple filters simultaneously matching a specific product."""
    res = client.get(
        "/api/v1/products?search=Ergonomic&category_id=1&seller_id=1"
        "&min_price=400000&max_price=500000&min_rating=4.5&in_stock=true&sort=price_asc"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["code"] == "P-ACC-MOUSE"
    assert body["data"][0]["stock_status"] in ("in_stock", "low_stock")


def test_combined_query_failing_one_filter_returns_empty(client: TestClient, sample_catalog):
    """When one filter condition is not met among combined filters, returns empty list."""
    # Mouse has rating 4.7; requiring min_rating=4.9 should exclude it
    res = client.get(
        "/api/v1/products?search=Ergonomic&category_id=1&seller_id=1"
        "&min_price=400000&max_price=500000&min_rating=4.9&in_stock=true"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["data"] == []
    assert body["meta"]["total_items"] == 0
    assert body["meta"]["total_pages"] == 0


def test_combined_query_failing_seller_returns_empty(client: TestClient, sample_catalog):
    """Combined filters with mismatched seller return empty list."""
    # Mouse belongs to seller 1; querying seller 2 returns empty
    res = client.get(
        "/api/v1/products?search=Ergonomic&category_id=1&seller_id=2"
        "&min_price=400000&max_price=500000"
    )
    assert res.status_code == 200
    assert res.json()["data"] == []


# ------------------------------------------------------------------------------
# Descendant Categories Deep Hierarchy
# ------------------------------------------------------------------------------
def test_deep_four_level_category_descendants(client: TestClient, discovery_engine):
    """Category filter resolves recursively across 4 hierarchy levels."""
    with Session(discovery_engine) as session:
        seller = User(id=301, name="Audio Seller", email="audio@test.local", role="seller")
        session.add(seller)

        c10 = Category(id=10, name="Audio Root", slug="audio-root", parent_id=None)
        c11 = Category(id=11, name="Headphones & Speakers", slug="audio-mid", parent_id=10)
        c12 = Category(id=12, name="Wireless Audio", slug="audio-sub", parent_id=11)
        c13 = Category(id=13, name="Bluetooth Earbuds", slug="audio-leaf", parent_id=12)
        c14 = Category(id=14, name="Wired Earbuds", slug="audio-sibling", parent_id=12)
        session.add_all([c10, c11, c12, c13, c14])
        session.commit()

        p_leaf = Product(
            id=301,
            code="P-AUD-LEAF",
            seller_id=seller.id,
            name="True Wireless Earbuds",
            description="Active noise cancelling wireless earbuds",
            price=1500000,
            stock_quantity=20,
            reserved_stock=0,
            is_active=True,
        )
        session.add(p_leaf)
        session.commit()

        meta = ProductMetadata(product_id=p_leaf.id, category_id=13, rating=4.9, sales_count=50)
        session.add(meta)
        session.commit()

    # Querying root category (10) returns descendant leaf product
    res10 = client.get("/api/v1/products?category_id=10")
    assert any(p["code"] == "P-AUD-LEAF" for p in res10.json()["data"])

    # Querying intermediate level 2 (11) returns product
    res11 = client.get("/api/v1/products?category_id=11")
    assert any(p["code"] == "P-AUD-LEAF" for p in res11.json()["data"])

    # Querying intermediate level 3 (12) returns product
    res12 = client.get("/api/v1/products?category_id=12")
    assert any(p["code"] == "P-AUD-LEAF" for p in res12.json()["data"])

    # Querying leaf category (13) returns product
    res13 = client.get("/api/v1/products?category_id=13")
    assert any(p["code"] == "P-AUD-LEAF" for p in res13.json()["data"])

    # Querying sibling category (14) does NOT return leaf product
    res14 = client.get("/api/v1/products?category_id=14")
    assert not any(p["code"] == "P-AUD-LEAF" for p in res14.json()["data"])


def test_empty_category_without_products_returns_empty_catalog(
    client: TestClient, discovery_engine
):
    """Category with no assigned products returns empty list gracefully."""
    with Session(discovery_engine) as session:
        empty_cat = Category(id=40, name="Empty Category", slug="empty-cat", parent_id=None)
        session.add(empty_cat)
        session.commit()

    res = client.get("/api/v1/products?category_id=40")
    assert res.status_code == 200
    body = res.json()
    assert body["data"] == []
    assert body["meta"]["total_items"] == 0


def test_non_existent_category_id_returns_empty_catalog(client: TestClient, sample_catalog):
    """Filtering by non-existent category_id returns empty product list."""
    res = client.get("/api/v1/products?category_id=999999")
    assert res.status_code == 200
    assert res.json()["data"] == []
    assert res.json()["meta"]["total_items"] == 0


# ------------------------------------------------------------------------------
# Valid and Invalid Price Ranges
# ------------------------------------------------------------------------------
def test_price_range_exact_match(client: TestClient, sample_catalog):
    """When min_price equals max_price, returns products matching exact price."""
    res = client.get("/api/v1/products?min_price=450000&max_price=450000")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    assert codes == ["P-ACC-MOUSE"]


def test_price_range_only_min_price(client: TestClient, sample_catalog):
    """Querying min_price alone filters products with price >= min_price."""
    res = client.get("/api/v1/products?min_price=20000000")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    assert codes == ["P-LAP-PRO"]


def test_price_range_only_max_price(client: TestClient, sample_catalog):
    """Querying max_price alone filters products with price <= max_price."""
    res = client.get("/api/v1/products?max_price=450000")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    assert codes == ["P-ACC-MOUSE"]


@pytest.mark.parametrize("param", ["min_price=-10", "max_price=-50"])
def test_invalid_price_range_negative_values_rejected(client: TestClient, param):
    """Negative values for min_price or max_price trigger 422 validation error."""
    res = client.get(f"/api/v1/products?{param}")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ERR_VALIDATION"


# ------------------------------------------------------------------------------
# Supported Sort Modes and Tie-Breaking
# ------------------------------------------------------------------------------
def test_default_sort_when_sort_omitted_is_id_asc(client: TestClient, sample_catalog):
    """When sort parameter is omitted, results are ordered by Product.id ASC."""
    res = client.get("/api/v1/products?limit=10")
    assert res.status_code == 200
    ids = [int(p["id"]) for p in res.json()["data"]]
    assert ids == sorted(ids)


def test_sort_price_tie_breakers(client: TestClient, discovery_engine):
    """Products with identical prices are tie-broken by Product.id ASC/DESC."""
    with Session(discovery_engine) as session:
        seller = User(id=401, name="Price Seller", email="price@test.local", role="seller")
        session.add(seller)
        session.commit()

        p1 = Product(
            id=501,
            code="P-SAME-P1",
            seller_id=seller.id,
            name="Identical Price Item A",
            description="d",
            price=200000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        p2 = Product(
            id=502,
            code="P-SAME-P2",
            seller_id=seller.id,
            name="Identical Price Item B",
            description="d",
            price=200000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([p1, p2])
        session.commit()

    # Price ASC tie-breaks by id ASC
    res_asc = client.get("/api/v1/products?seller_id=401&sort=price_asc")
    assert res_asc.status_code == 200
    codes_asc = [p["code"] for p in res_asc.json()["data"]]
    assert codes_asc == ["P-SAME-P1", "P-SAME-P2"]

    # Price DESC tie-breaks by id DESC
    res_desc = client.get("/api/v1/products?seller_id=401&sort=price_desc")
    assert res_desc.status_code == 200
    codes_desc = [p["code"] for p in res_desc.json()["data"]]
    assert codes_desc == ["P-SAME-P2", "P-SAME-P1"]


def test_sort_rating_desc_tie_breaker(client: TestClient, discovery_engine):
    """Products with identical ratings are tie-broken by Product.id DESC."""
    with Session(discovery_engine) as session:
        seller = User(id=402, name="Rating Seller", email="rating@test.local", role="seller")
        session.add(seller)
        session.commit()

        p1 = Product(
            id=601,
            code="P-RATE-1",
            seller_id=seller.id,
            name="Item Rate 1",
            description="d",
            price=10000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        p2 = Product(
            id=602,
            code="P-RATE-2",
            seller_id=seller.id,
            name="Item Rate 2",
            description="d",
            price=10000,
            stock_quantity=5,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([p1, p2])
        session.commit()

        m1 = ProductMetadata(product_id=p1.id, rating=4.5)
        m2 = ProductMetadata(product_id=p2.id, rating=4.5)
        session.add_all([m1, m2])
        session.commit()

    res = client.get("/api/v1/products?seller_id=402&sort=rating_desc")
    assert res.status_code == 200
    codes = [p["code"] for p in res.json()["data"]]
    # Tie broken by id DESC
    assert codes == ["P-RATE-2", "P-RATE-1"]


@pytest.mark.parametrize(
    "sort_mode",
    ["newest", "bestselling", "price_asc", "price_desc", "rating_desc"],
)
def test_all_supported_sort_modes_accept_valid_requests(
    client: TestClient, sample_catalog, sort_mode
):
    """Every supported sort mode succeeds and returns 200 OK."""
    res = client.get(f"/api/v1/products?sort={sort_mode}")
    assert res.status_code == 200
    assert len(res.json()["data"]) > 0


# ------------------------------------------------------------------------------
# Pagination Boundaries
# ------------------------------------------------------------------------------
def test_pagination_boundary_first_and_last_page(client: TestClient, sample_catalog):
    """Verify first and last page pagination boundaries."""
    # First page: 2 items
    res_p1 = client.get("/api/v1/products?limit=2&page=1")
    assert res_p1.status_code == 200
    meta_p1 = res_p1.json()["meta"]
    assert meta_p1["current_page"] == 1
    assert meta_p1["total_pages"] == 3
    assert len(res_p1.json()["data"]) == 2

    # Last page: 1 remaining item
    res_p3 = client.get("/api/v1/products?limit=2&page=3")
    assert res_p3.status_code == 200
    meta_p3 = res_p3.json()["meta"]
    assert meta_p3["current_page"] == 3
    assert len(res_p3.json()["data"]) == 1


def test_pagination_page_beyond_total_pages_clamps_to_last(client: TestClient, sample_catalog):
    """Requesting page beyond total_pages clamps to total_pages."""
    res = client.get("/api/v1/products?limit=2&page=999")
    assert res.status_code == 200
    meta = res.json()["meta"]
    assert meta["current_page"] == 3
    assert len(res.json()["data"]) == 1


def test_pagination_boundary_limits(client: TestClient, sample_catalog):
    """Test limit boundary values 1 and 100."""
    # limit=1
    res1 = client.get("/api/v1/products?limit=1")
    assert res1.status_code == 200
    assert len(res1.json()["data"]) == 1
    assert res1.json()["meta"]["total_pages"] == 5

    # limit=100
    res100 = client.get("/api/v1/products?limit=100")
    assert res100.status_code == 200
    assert len(res100.json()["data"]) == 5
    assert res100.json()["meta"]["total_pages"] == 1


@pytest.mark.parametrize(
    "invalid_query",
    ["page=0", "page=-1", "limit=0", "limit=101"],
)
def test_pagination_invalid_boundary_errors(client: TestClient, invalid_query):
    """Out-of-range pagination parameters return 422 validation errors."""
    res = client.get(f"/api/v1/products?{invalid_query}")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ERR_VALIDATION"


# ------------------------------------------------------------------------------
# Empty Results & Metadata Consistency
# ------------------------------------------------------------------------------
def test_empty_results_metadata_consistency(client: TestClient, sample_catalog):
    """Empty result set has total=0, total_items=0, total_pages=0, current_page=1."""
    res = client.get("/api/v1/products?search=completely_absent_item")
    assert res.status_code == 200
    body = res.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
    assert body["meta"]["total_items"] == 0
    assert body["meta"]["total_pages"] == 0
    assert body["meta"]["current_page"] == 1


def test_metadata_consistency_stock_status_all_variants(client: TestClient, discovery_engine):
    """Product stock status calculations: in_stock (>5), low_stock (1..5), out_of_stock (0)."""
    with Session(discovery_engine) as session:
        seller = User(id=501, name="Stock Seller", email="stock@test.local", role="seller")
        session.add(seller)
        session.commit()

        p_in = Product(
            id=701,
            code="P-STK-IN",
            seller_id=seller.id,
            name="Stock High",
            price=1000,
            stock_quantity=10,
            reserved_stock=0,
            is_active=True,
        )
        p_low = Product(
            id=702,
            code="P-STK-LOW",
            seller_id=seller.id,
            name="Stock Low",
            price=1000,
            stock_quantity=4,
            reserved_stock=0,
            is_active=True,
        )
        p_out = Product(
            id=703,
            code="P-STK-OUT",
            seller_id=seller.id,
            name="Stock Out",
            price=1000,
            stock_quantity=0,
            reserved_stock=0,
            is_active=True,
        )
        session.add_all([p_in, p_low, p_out])
        session.commit()

    # Query with in_stock=false to include out-of-stock items
    res = client.get("/api/v1/products?seller_id=501&in_stock=false")
    assert res.status_code == 200
    status_map = {p["code"]: p["stock_status"] for p in res.json()["data"]}
    assert status_map["P-STK-IN"] == "in_stock"
    assert status_map["P-STK-LOW"] == "low_stock"
    assert status_map["P-STK-OUT"] == "out_of_stock"


def test_metadata_consistency_reserved_stock_affects_availability(
    client: TestClient, discovery_engine
):
    """Reserved stock reduces available stock quantity and influences stock_status."""
    with Session(discovery_engine) as session:
        seller = User(id=502, name="Reserved Seller", email="res@test.local", role="seller")
        session.add(seller)
        session.commit()

        # 10 total, 7 reserved -> 3 available (low_stock)
        p_res_low = Product(
            id=704,
            code="P-RES-LOW",
            seller_id=seller.id,
            name="Reserved Low",
            price=1000,
            stock_quantity=10,
            reserved_stock=7,
            is_active=True,
        )
        # 5 total, 5 reserved -> 0 available (out_of_stock)
        p_res_out = Product(
            id=705,
            code="P-RES-OUT",
            seller_id=seller.id,
            name="Reserved Zero",
            price=1000,
            stock_quantity=5,
            reserved_stock=5,
            is_active=True,
        )
        session.add_all([p_res_low, p_res_out])
        session.commit()

    res = client.get("/api/v1/products?seller_id=502&in_stock=false")
    assert res.status_code == 200
    by_code = {p["code"]: p for p in res.json()["data"]}

    assert by_code["P-RES-LOW"]["stock_quantity"] == 3
    assert by_code["P-RES-LOW"]["stock_status"] == "low_stock"

    assert by_code["P-RES-OUT"]["stock_quantity"] == 0
    assert by_code["P-RES-OUT"]["stock_status"] == "out_of_stock"

