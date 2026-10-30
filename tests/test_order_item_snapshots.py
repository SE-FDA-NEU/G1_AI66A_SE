"""Purchase facts survive listing changes, soft deletion, replay and migration (#147)."""

from collections import Counter

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session, migrate_db
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import BUYER_ID, OTHER_BUYER_ID, SELLER_ID, create_cart_engine

BODY = {
    "recipient_name": "Snapshot Buyer",
    "delivery_address": "1 Test Street",
    "phone_number": "0912345678",
}
ORIGINAL_PRODUCT_IMAGE = "https://example.test/original-product.jpg"
ORIGINAL_VARIANT_IMAGE = "https://example.test/original-option.jpg"
EDITED_IMAGE = "https://example.test/edited.jpg"
SNAPSHOT_FIELDS = ("product_name", "variant_name", "image_url", "unit_price")
IMAGE_CASES = ("base-image", "base-null", "variant-image", "variant-fallback", "variant-null")


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "snapshots.db")
    with Session(value) as session:
        session.add(User(id=4, name="Other shop", email="other-shop@test.local", role="seller"))
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


def headers(engine, user_id=BUYER_ID, key="snapshot-request"):
    with Session(engine) as session:
        token = create_access_token(session.get(User, user_id))
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def seed_listing(engine, image_case="variant-image", *, seller_id=SELLER_ID, code="SNAP-147"):
    variant_selected = image_case.startswith("variant")
    product_image = None if image_case.endswith("null") else ORIGINAL_PRODUCT_IMAGE
    variant_image = ORIGINAL_VARIANT_IMAGE if image_case == "variant-image" else None
    with Session(engine) as session:
        product = Product(
            code=code,
            seller_id=seller_id,
            name="Original linen shirt",
            price=120000,
            stock_quantity=10,
            image_url=product_image,
        )
        session.add(product)
        session.flush()
        variant_id = None
        if variant_selected:
            variant = ProductVariant(
                product_id=product.id,
                seller_id=seller_id,
                sku=code,
                name="Navy / M",
                price=80000,
                stock_quantity=10,
                image_url=variant_image,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id
        session.commit()
        product_id = product.id
    expected = (
        "Original linen shirt",
        "Navy / M" if variant_selected else None,
        variant_image or product_image,
        80000 if variant_selected else 120000,
    )
    return {
        "product_id": product_id,
        "variant_id": variant_id,
        "code": code,
        "seller_id": seller_id,
        "expected": expected,
    }


def add_to_cart(api, engine, listing):
    response = api.post(
        "/api/v1/cart/items",
        headers=headers(engine),
        json={"product_code": listing["code"], "variant_id": listing["variant_id"], "quantity": 2},
    )
    assert response.status_code == 201, response.text


def checkout_body(api, engine, quoted):
    if not quoted:
        return BODY.copy()
    response = api.post("/api/v1/orders/quote", headers=headers(engine), json={})
    assert response.status_code == 200, response.text
    return BODY | {"quote_revision": response.json()["data"]["quote_revision"]}


def assert_purchase_line(line, expected):
    assert tuple(line[field] for field in SNAPSHOT_FIELDS) == expected
    assert line["quantity"] == 2
    assert line.get("line_total", line.get("total_price")) == expected[-1] * 2


def stored_items(engine):
    with Session(engine) as session:
        return [
            item.model_dump() for item in session.exec(select(OrderItem).order_by(OrderItem.id))
        ]


def assert_historical_views(api, engine, order_id, expected):
    for actor in (BUYER_ID, SELLER_ID):
        response = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine, actor))
        assert response.status_code == 200, response.text
        [line] = response.json()["data"]["items"]
        assert_purchase_line(line, expected)
    buyer_orders = api.get("/api/v1/orders", headers=headers(engine))
    assert buyer_orders.status_code == 200
    [line] = next(row["data"] for row in buyer_orders.json() if row["data"]["id"] == order_id)[
        "items"
    ]
    assert_purchase_line(line, expected)
    seller_orders = api.get("/api/v1/seller/orders", headers=headers(engine, SELLER_ID))
    assert seller_orders.status_code == 200
    [line] = next(row for row in seller_orders.json()["data"] if row["order_id"] == order_id)[
        "items"
    ]
    assert_purchase_line(line, expected)


def change_listing(api, engine, listing, mutation):
    product_url = f"/api/v1/seller/products/{listing['product_id']}"
    owner = headers(engine, listing["seller_id"])
    if listing["variant_id"] is not None:
        url = f"{product_url}/variants"
        response = api.get(url, headers=owner)
        assert response.status_code == 200
        version = next(
            row["version"] for row in response.json()["data"] if row["id"] == listing["variant_id"]
        )
        if mutation == "delete":
            response = api.delete(f"{url}/{listing['variant_id']}", headers=owner)
        else:
            changes = (
                {"name": "Edited option", "price": 999000, "image_url": EDITED_IMAGE}
                if mutation == "edit"
                else {"is_active": False}
            )
            response = api.patch(
                f"{url}/{listing['variant_id']}",
                headers=owner,
                json={"expected_version": version} | changes,
            )
        assert response.status_code == 200, response.text
    if mutation == "delete":
        response = api.delete(product_url, headers=owner)
    else:
        changes = (
            {"name": "Edited listing", "price": 888000, "image_url": EDITED_IMAGE}
            if mutation == "edit"
            else {"is_active": False}
        )
        response = api.patch(product_url, headers=owner, json=changes)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("image_case", IMAGE_CASES)
@pytest.mark.parametrize("quoted", [False, True], ids=["legacy", "quote"])
@pytest.mark.parametrize("mutation", ["edit", "deactivate", "delete"])
def test_purchase_snapshots_survive_catalog_changes_and_replay(
    api, engine, image_case, quoted, mutation
):
    listing = seed_listing(engine, image_case)
    add_to_cart(api, engine, listing)
    body = checkout_body(api, engine, quoted)

    response = api.post("/api/v1/orders", headers=headers(engine), json=body)

    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert_purchase_line(order["items"][0], listing["expected"])
    assert order["total_amount"] == listing["expected"][-1] * 2 + (20000 if quoted else 0)
    [stored] = before = stored_items(engine)
    assert (
        stored["product_name_snapshot"],
        stored["variant_name_snapshot"],
        stored["product_image_snapshot"],
        stored["unit_price"],
    ) == listing["expected"]
    assert stored["snapshot_initialized"] is True
    change_listing(api, engine, listing, mutation)
    assert_historical_views(api, engine, order["id"], listing["expected"])
    replay = api.post("/api/v1/orders", headers=headers(engine), json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["items"] == order["items"]
    assert replay.json()["data"]["total_amount"] == order["total_amount"]
    with engine.begin() as connection:
        migrate_db(connection)
        migrate_db(connection)
    assert stored_items(engine) == before
    assert_historical_views(api, engine, order["id"], listing["expected"])
    if mutation != "edit":
        with Session(engine) as session:
            assert session.get(Product, listing["product_id"]).is_active is False
            if listing["variant_id"] is not None:
                assert session.get(ProductVariant, listing["variant_id"]).is_active is False


def test_each_shop_only_reads_its_own_historical_lines(api, engine):
    first = seed_listing(engine)
    second = seed_listing(engine, "base-image", seller_id=4, code="SNAP-OTHER")
    for listing in (first, second):
        add_to_cart(api, engine, listing)
    response = api.post("/api/v1/orders", headers=headers(engine), json=BODY)
    assert response.status_code == 201
    order_id = response.json()["data"]["id"]
    for listing in (first, second):
        change_listing(api, engine, listing, "edit")
        result = api.get(
            f"/api/v1/orders/{order_id}", headers=headers(engine, listing["seller_id"])
        )
        assert result.status_code == 200
        [line] = result.json()["data"]["items"]
        assert line["product_id"] == listing["product_id"]
        assert_purchase_line(line, listing["expected"])
    denied = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine, OTHER_BUYER_ID))
    assert denied.status_code == 404
    buyer = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine))
    assert buyer.status_code == 200
    assert Counter(
        tuple(line[field] for field in SNAPSHOT_FIELDS) for line in buyer.json()["data"]["items"]
    ) == Counter(listing["expected"] for listing in (first, second))


@pytest.mark.parametrize("entity", ["product", "variant"])
def test_referenced_inventory_cannot_be_physically_deleted(api, engine, entity):
    listing = seed_listing(engine, "base-image" if entity == "product" else "variant-image")
    add_to_cart(api, engine, listing)
    response = api.post("/api/v1/orders", headers=headers(engine), json=BODY)
    assert response.status_code == 201
    before = stored_items(engine)
    model = Product if entity == "product" else ProductVariant
    with Session(engine) as session:
        session.delete(session.get(model, listing[f"{entity}_id"]))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    assert stored_items(engine) == before
    assert_historical_views(api, engine, response.json()["data"]["id"], listing["expected"])


@pytest.mark.parametrize("quoted", [False, True], ids=["legacy", "quote"])
def test_snapshots_use_checkout_values_rather_than_values_when_added_to_cart(api, engine, quoted):
    listing = seed_listing(engine)
    add_to_cart(api, engine, listing)
    change_listing(api, engine, listing, "edit")
    body = checkout_body(api, engine, quoted)

    response = api.post("/api/v1/orders", headers=headers(engine), json=body)

    assert response.status_code == 201, response.text
    expected = ("Edited listing", "Edited option", EDITED_IMAGE, 999000)
    assert_purchase_line(response.json()["data"]["items"][0], expected)
    assert_historical_views(api, engine, response.json()["data"]["id"], expected)


@pytest.mark.parametrize(
    "field",
    ["product_name_snapshot", "variant_name_snapshot", "product_image_snapshot", "unit_price"],
)
def test_checkout_rejects_client_supplied_purchase_snapshots(api, engine, field):
    listing = seed_listing(engine)
    add_to_cart(api, engine, listing)
    response = api.post("/api/v1/orders", headers=headers(engine), json=BODY | {field: "forged"})
    assert response.status_code == 422
    assert stored_items(engine) == []
    with Session(engine) as session:
        assert session.exec(select(Order)).all() == []
        assert session.get(ProductVariant, listing["variant_id"]).stock_quantity == 10
        assert len(session.exec(select(CartItem)).all()) == 1


@pytest.mark.parametrize("quoted", [False, True], ids=["legacy", "quote"])
def test_failed_snapshot_insert_rolls_back_the_entire_checkout(api, engine, quoted):
    listing = seed_listing(engine)
    add_to_cart(api, engine, listing)
    with Session(engine) as session:
        second = ProductVariant(
            product_id=listing["product_id"],
            seller_id=SELLER_ID,
            sku="SNAP-BLOCKED",
            name="Blocked option",
            price=90000,
            stock_quantity=10,
            image_url=EDITED_IMAGE,
        )
        session.add(second)
        session.flush()
        session.add(
            CartItem(
                buyer_id=BUYER_ID,
                product_id=listing["product_id"],
                variant_id=second.id,
                quantity=1,
            )
        )
        session.commit()
    models = (
        Order,
        SellerOrder,
        OrderItem,
        Product,
        ProductVariant,
        CartItem,
        ProductMetadata,
        Notification,
    )

    def persisted_state():
        with Session(engine) as session:
            return {
                model.__tablename__: [row.model_dump() for row in session.exec(select(model))]
                for model in models
            }

    before = persisted_state()
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TRIGGER reject_snapshot BEFORE INSERT ON order_items
            WHEN NEW.variant_name_snapshot = 'Blocked option'
            BEGIN SELECT RAISE(ABORT, 'injected snapshot failure'); END
        """)
    attempts = []

    def count_inserts(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO ORDER_ITEMS"):
            attempts.append(statement)

    body = checkout_body(api, engine, quoted)
    event.listen(engine, "before_cursor_execute", count_inserts)
    try:
        response = api.post("/api/v1/orders", headers=headers(engine), json=body)
    finally:
        event.remove(engine, "before_cursor_execute", count_inserts)
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
    assert len(attempts) == 2, "A previous line must have reached persistence before failure"
    assert persisted_state() == before


@pytest.mark.parametrize("saved_image", [None, ORIGINAL_VARIANT_IMAGE], ids=["null", "image"])
def test_snapshot_column_migration_preserves_known_facts_and_is_repeatable(tmp_path, saved_image):
    engine = create_engine(f"sqlite:///{tmp_path / 'known-snapshots.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, image_url TEXT)"
        )
        connection.exec_driver_sql("""CREATE TABLE order_items (
            id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, variant_id INTEGER,
            product_name_snapshot TEXT, variant_name_snapshot TEXT, product_image_snapshot TEXT,
            quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL)""")
        connection.execute(
            text("INSERT INTO products VALUES (7, 'Latest listing', :image)"),
            {"image": EDITED_IMAGE},
        )
        connection.execute(
            text("""INSERT INTO order_items VALUES (
            21, 7, 13, 'Original linen shirt', 'Navy / M', :image, 2, 80000)"""),
            {"image": saved_image},
        )
        migrate_db(connection)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE products SET name='Edited again', image_url='new.jpg'")
        migrate_db(connection)
        migrate_db(connection)
        columns = {column["name"] for column in inspect(connection).get_columns("order_items")}
        assert "snapshot_initialized" in columns
        row = connection.execute(
            text("""SELECT id, product_id, variant_id,
            product_name_snapshot, variant_name_snapshot, product_image_snapshot,
            quantity, unit_price, snapshot_initialized FROM order_items""")
        ).one()
        assert tuple(row) == (
            21,
            7,
            13,
            "Original linen shirt",
            "Navy / M",
            saved_image,
            2,
            80000,
            1,
        )
    engine.dispose()
