from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session, migrate_db
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.orders import CheckoutRequest
from src.services.inventory import restore_order_item_stock
from src.services.orders import CheckoutError, checkout, receipt
from tests.cart_db import (
    BUYER_ID,
    OTHER_BUYER_ID,
    SELLER_ID,
    add_product,
    create_cart_engine,
)


@pytest.fixture
def engine(tmp_path: Path):
    value = create_cart_engine(tmp_path / "us19.db")
    with Session(value) as session:
        session.add(User(id=4, name="Admin", email="admin@test.local", role="admin"))
        session.commit()
    yield value
    value.dispose()


@pytest.fixture
def api(engine):
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client


def auth(engine, user_id: int) -> dict[str, str]:
    with Session(engine) as session:
        token = create_access_token(session.get(User, user_id))
    return {"Authorization": f"Bearer {token}"}


def test_admin_categories_enforce_hierarchy_permissions_and_soft_deactivation(api, engine):
    buyer = auth(engine, BUYER_ID)
    admin = auth(engine, 4)
    assert (
        api.post(
            "/api/v1/categories", json={"name": "Root", "slug": "root"}, headers=buyer
        ).status_code
        == 403
    )

    root = api.post("/api/v1/categories", json={"name": "Root", "slug": "root"}, headers=admin)
    assert root.status_code == 201
    root_id = root.json()["id"]
    child = api.post(
        "/api/v1/categories",
        json={"name": "Child", "slug": "child", "parent_id": root_id},
        headers=admin,
    )
    assert child.status_code == 201
    child_id = child.json()["id"]

    cycle = api.patch(f"/api/v1/categories/{root_id}", json={"parent_id": child_id}, headers=admin)
    assert cycle.status_code == 422
    assert api.delete(f"/api/v1/categories/{root_id}", headers=admin).status_code == 409
    assert api.delete(f"/api/v1/categories/{child_id}", headers=admin).status_code == 200
    assert api.delete(f"/api/v1/categories/{root_id}", headers=admin).status_code == 200
    assert api.get("/api/v1/categories").json() == []
    assert api.get("/api/v1/categories/admin", headers=admin).json()[0]["is_active"] is False
    reactivated = api.patch(
        f"/api/v1/categories/{root_id}", json={"is_active": True}, headers=admin
    )
    assert reactivated.status_code == 200
    assert len(api.get("/api/v1/categories").json()) == 1


def test_variants_are_shop_owned_and_checkout_keeps_purchase_snapshots(api, engine):
    product_id = add_product(engine, "P-VARIANT", price=500_000, stock=10)
    seller = auth(engine, SELLER_ID)
    buyer = auth(engine, BUYER_ID)
    url = f"/api/v1/seller/products/{product_id}/variants"
    first = api.post(
        url,
        json={
            "sku": "case-black",
            "name": "Black",
            "price": 90_000,
            "stock_quantity": 2,
            "image_url": "https://example.test/black.jpg",
        },
        headers=seller,
    )
    second = api.post(
        url,
        json={"sku": "CASE-WHITE", "name": "White", "price": 120_000, "stock_quantity": 1},
        headers=seller,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    duplicate = api.post(
        url,
        json={"sku": "case-black", "name": "Duplicate", "price": 1, "stock_quantity": 1},
        headers=seller,
    )
    assert duplicate.status_code == 409
    oversell = api.post(
        "/api/v1/cart/items",
        json={
            "product_code": "P-VARIANT",
            "variant_id": first.json()["data"]["id"],
            "quantity": 3,
        },
        headers=auth(engine, BUYER_ID),
    )
    assert oversell.status_code == 409

    detail = api.get("/api/v1/products/P-VARIANT").json()
    assert detail["has_variants"] is True
    assert [item["name"] for item in detail["variants"]] == ["Black", "White"]
    assert detail["price"] == 90_000
    assert (
        api.post(
            "/api/v1/cart/items",
            json={"product_code": "P-VARIANT", "quantity": 1},
            headers=buyer,
        ).status_code
        == 409
    )

    for variant in (first.json()["data"], second.json()["data"]):
        response = api.post(
            "/api/v1/cart/items",
            json={
                "product_code": "P-VARIANT",
                "variant_id": variant["id"],
                "quantity": 1,
            },
            headers=buyer,
        )
        assert response.status_code == 201, response.text
    cart = api.get("/api/v1/cart", headers=buyer).json()["data"]
    assert [(item["variant_name"], item["unit_price"]) for item in cart["items"]] == [
        ("Black", 90_000),
        ("White", 120_000),
    ]

    body = CheckoutRequest(
        recipient_name="Buyer",
        delivery_address="1 Test Street",
        phone_number="0912345678",
    )
    with Session(engine) as session:
        order, created = checkout(session, BUYER_ID, body, "us19-variant-order")
        assert created is True
        assert order.total_amount == 210_000
        order_id = order.id

    assert (
        api.delete(f"{url}/{first.json()['data']['id']}", headers=seller).json()["data"][
            "is_active"
        ]
        is False
    )
    assert (
        api.delete(f"/api/v1/seller/products/{product_id}", headers=seller).json()["data"][
            "is_active"
        ]
        is False
    )

    with Session(engine) as session:
        product = session.get(Product, product_id)
        assert product is not None
        product.name = "Renamed listing"
        product.image_url = "https://example.test/new-product.jpg"
        session.add(product)
        variants = session.exec(select(ProductVariant).order_by(ProductVariant.id)).all()
        variants[0].name = "Renamed black"
        variants[0].price = 999_000
        variants[0].image_url = "https://example.test/new-black.jpg"
        session.add(variants[0])
        session.commit()

        saved_receipt = receipt(session, BUYER_ID, order_id)
        assert [
            (line.product_name, line.variant_name, line.unit_price, line.image_url)
            for line in saved_receipt.items
        ] == [
            ("Product P-VARIANT", "Black", 90_000, "https://example.test/black.jpg"),
            ("Product P-VARIANT", "White", 120_000, "/images/p-variant.jpg"),
        ]
        purchased = session.exec(
            select(OrderItem)
            .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
            .where(SellerOrder.order_id == order_id)
            .order_by(OrderItem.id)
        ).all()
        for item in purchased:
            restore_order_item_stock(session, item)
        session.commit()
        variants = session.exec(select(ProductVariant).order_by(ProductVariant.id)).all()
        assert [variant.stock_quantity for variant in variants] == [2, 1]


def test_other_shop_cannot_manage_variant(api, engine):
    product_id = add_product(engine, "P-OWNER")
    with Session(engine) as session:
        session.add(User(id=5, name="Other Seller", email="other-seller@test.local", role="seller"))
        session.commit()
    response = api.post(
        f"/api/v1/seller/products/{product_id}/variants",
        json={"sku": "OWNER-1", "name": "Option", "price": 10, "stock_quantity": 1},
        headers=auth(engine, 5),
    )
    assert response.status_code == 403


def test_legacy_cart_and_order_rows_migrate_without_losing_history(tmp_path: Path):
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'legacy-us19.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "email TEXT NOT NULL, role TEXT NOT NULL, created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "price INTEGER NOT NULL, image_url TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "slug TEXT NOT NULL, parent_id INTEGER)"
            )
        )
        connection.execute(text("CREATE TABLE product_variants (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE cart_items (id INTEGER PRIMARY KEY, buyer_id INTEGER NOT NULL, "
                "product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_cart_items_buyer_product UNIQUE (buyer_id, product_id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE order_items (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
                "quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO products VALUES (7, 'Old name', 123, 'old-image.jpg')")
        )
        connection.execute(text("INSERT INTO categories VALUES (3, 'Category', 'category', NULL)"))
        connection.execute(
            text("INSERT INTO cart_items VALUES (11, 2, 7, 3, '2026-01-01 00:00:00')")
        )
        connection.execute(text("INSERT INTO order_items VALUES (21, 7, 2, 123)"))
        migrate_db(connection)

    with engine.connect() as connection:
        cart_columns = {column["name"] for column in inspect(connection).get_columns("cart_items")}
        assert {"variant_id", "is_selected", "price_at_add"} <= cart_columns
        cart = connection.execute(
            text(
                "SELECT id, buyer_id, product_id, quantity, is_selected, price_at_add "
                "FROM cart_items"
            )
        ).one()
        assert tuple(cart) == (11, 2, 7, 3, 1, 123)
        indexes = {index["name"] for index in inspect(connection).get_indexes("cart_items")}
        assert "uq_cart_items_buyer_product_base" in indexes
        assert "uq_cart_items_buyer_product_variant" in indexes
        snapshot = connection.execute(
            text(
                "SELECT product_name_snapshot, product_image_snapshot, variant_id "
                "FROM order_items WHERE id=21"
            )
        ).one()
        assert tuple(snapshot) == ("Old name", "old-image.jpg", None)
        category = connection.execute(
            text("SELECT is_active FROM categories WHERE id=3")
        ).scalar_one()
        assert category == 1
    engine.dispose()


def test_concurrent_variant_checkouts_cannot_oversell(tmp_path: Path):
    engine = create_cart_engine(tmp_path / "variant-race.db")
    product_id = add_product(engine, "P-RACE", stock=10)
    with Session(engine) as session:
        variant = ProductVariant(
            product_id=product_id,
            seller_id=SELLER_ID,
            sku="RACE-1",
            name="Limited",
            price=500,
            stock_quantity=1,
        )
        session.add(variant)
        session.flush()
        session.add_all(
            [
                CartItem(
                    buyer_id=BUYER_ID,
                    product_id=product_id,
                    variant_id=variant.id,
                    quantity=1,
                ),
                CartItem(
                    buyer_id=OTHER_BUYER_ID,
                    product_id=product_id,
                    variant_id=variant.id,
                    quantity=1,
                ),
            ]
        )
        session.commit()
        variant_id = variant.id

    body = CheckoutRequest(
        recipient_name="Buyer",
        delivery_address="1 Test Street",
        phone_number="0912345678",
    )

    def attempt(buyer_id: int, key: str) -> bool:
        with Session(engine) as session:
            try:
                checkout(session, buyer_id, body, key)
                return True
            except CheckoutError:
                return False

    requests = [(BUYER_ID, "variant-race-a"), (OTHER_BUYER_ID, "variant-race-b")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: attempt(*args), requests))
    assert results.count(True) == 1
    with Session(engine) as session:
        saved = session.get(ProductVariant, variant_id)
        assert saved is not None
        assert saved.stock_quantity == 0
    engine.dispose()
