"""US12 #104: API-to-database acceptance and partial-checkout regressions."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlmodel import Session, create_engine, select

import src.database as database
from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import add_product, change_product, create_cart_engine, stored_stock

DELIVERY = {"recipient_name": "Buyer", "delivery_address": "123 Main", "phone_number": "0912345678"}


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "us12.db")
    add_product(value, "P-100", price=100)
    add_product(value, "P-200", price=200)
    add_product(value, "P-300", price=300)
    with Session(value) as session:
        session.add(User(id=4, name="Second shop", email="shop2@test.local", role="seller"))
        session.commit()
        product = session.exec(select(Product).where(Product.code == "P-300")).one()
        product.seller_id = 4
        session.add(product)
        session.commit()
    yield value
    value.dispose()


@pytest.fixture
def api(engine) -> Iterator[TestClient]:
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client


def auth(buyer=2, key="us12-order"):
    user = User(id=buyer, name="Buyer", email="b@test.local", role="buyer")
    return {"Authorization": f"Bearer {create_access_token(user)}", "Idempotency-Key": key}


def add(api, code="P-100", buyer=2):
    response = api.post(
        "/api/v1/cart/items", headers=auth(buyer), json={"product_code": code, "quantity": 1}
    )
    assert response.status_code == 201
    return next(
        line["cart_item_id"]
        for line in response.json()["data"]["items"]
        if line["product_code"] == code
    )


def select_item(api, row_id, selected, buyer=2):
    return api.patch(
        f"/api/v1/cart/items/{row_id}/select", headers=auth(buyer), json={"is_selected": selected}
    )


def cart(api):
    response = api.get("/api/v1/cart", headers=auth())
    assert response.status_code == 200
    return response.json()["data"]


def order_counts(engine):
    with Session(engine) as session:
        return [len(session.exec(select(model)).all()) for model in (Order, SellerOrder, OrderItem)]


def test_selection_and_shop_metadata_survive_reload(api, engine):
    first = add(api)
    add(api, "P-200")
    add(api, "P-300")
    assert select_item(api, first, False).status_code == 200
    snapshot = cart(api)
    assert snapshot["cart_total"] == 600
    assert snapshot["selected_total"] == 500
    assert snapshot["supports_partial_checkout"] is True
    assert [(line["seller_id"], line["seller_name"]) for line in snapshot["items"]] == [
        (1, "Seller"),
        (1, "Seller"),
        (4, "Second shop"),
    ]
    with Session(engine) as session:
        assert session.get(CartItem, first).is_selected is False
    response = api.patch("/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": True})
    assert response.status_code == 200
    assert response.json()["data"]["selected_total"] == 600
    response = api.patch("/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": False})
    assert response.json()["data"]["selected_total"] == 300


def test_selection_is_owned_by_buyer(api, engine):
    own = add(api)
    other = add(api, buyer=3)
    response = select_item(api, other, False)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ERR_CART_ITEM_NOT_FOUND"
    assert select_item(api, own, False).status_code == 200
    with Session(engine) as session:
        assert session.get(CartItem, other).is_selected is True
    response = api.patch("/api/v1/cart/select-shop/4", headers=auth(), json={"is_selected": True})
    assert response.status_code == 404


@pytest.mark.parametrize("endpoint", ["items/1/select", "select-shop/1"])
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"is_selected": 1},
        {"is_selected": "false"},
        {"is_selected": None},
        {"is_selected": True, "buyer_id": 3},
    ],
)
def test_selection_requires_strict_boolean_and_no_extra_fields(api, endpoint, body):
    response = api.patch(f"/api/v1/cart/{endpoint}", headers=auth(), json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes", [{"is_active": False}, {"stock_quantity": 0}, {"reserved_stock": 10}]
)
def test_unavailable_rows_deselected_and_not_reselected_on_restock(api, engine, changes):
    first = add(api)
    add(api, "P-200")
    change_product(engine, "P-100", **changes)
    snapshot = cart(api)
    assert snapshot["items"][0]["is_selected"] is False
    assert snapshot["selected_total"] == 200
    with Session(engine) as session:
        assert session.get(CartItem, first).is_selected is False
    assert select_item(api, first, True).status_code == 409
    response = api.patch("/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": True})
    assert response.json()["data"]["selected_total"] == 200
    change_product(engine, "P-100", is_active=True, stock_quantity=10, reserved_stock=0)
    assert cart(api)["items"][0]["is_selected"] is False


@pytest.mark.parametrize("price", [80, 120])
def test_price_at_add_is_immutable_across_price_and_quantity_changes(api, engine, price):
    first = add(api)
    change_product(engine, "P-100", price=price)
    response = api.patch("/api/v1/cart/items/P-100", headers=auth(), json={"quantity": 2})
    line = response.json()["data"]["items"][0]
    assert (line["price_at_add"], line["unit_price"], line["price_changed"]) == (100, price, True)
    assert response.json()["data"]["selected_total"] == 2 * price
    with Session(engine) as session:
        assert session.get(CartItem, first).price_at_add == 100


def test_mixed_shop_checkout_preserves_unselected_rows_and_idempotent_replay(api, engine):
    add(api)
    unselected = add(api, "P-200")
    add(api, "P-300")
    assert select_item(api, unselected, False).status_code == 200
    # Unavailable unselected rows must not block the selected order.
    change_product(engine, "P-200", stock_quantity=0)
    response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 400
    assert {line["product_code"] for line in order["items"]} == {"P-100", "P-300"}
    assert order_counts(engine) == [1, 2, 2]
    with Session(engine) as session:
        rows = session.exec(select(CartItem).where(CartItem.buyer_id == 2)).all()
        assert [(row.id, row.quantity, row.is_selected, row.price_at_add) for row in rows] == [
            (unselected, 1, False, 200)
        ]
    assert stored_stock(engine, "P-100") == (9, 0)
    assert stored_stock(engine, "P-300") == (9, 0)
    # Changing selection after success cannot change a replayed order.
    change_product(engine, "P-200", stock_quantity=10)
    assert select_item(api, unselected, True).status_code == 200
    replay = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert replay.status_code == 200
    assert replay.json()["data"] == order
    assert order_counts(engine) == [1, 2, 2]
    assert cart(api)["items"][0]["cart_item_id"] == unselected


def test_no_selection_creates_no_order_and_does_not_touch_stock(api, engine):
    row = add(api)
    select_item(api, row, False)
    response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_EMPTY_CART"
    assert order_counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert cart(api)["items"][0]["is_selected"] is False


def test_failed_selected_checkout_rolls_back_every_selected_row(api, engine):
    add(api)
    add(api, "P-200")
    unselected = add(api, "P-300")
    select_item(api, unselected, False)
    change_product(engine, "P-200", stock_quantity=0)
    response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert response.status_code == 409
    assert order_counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    with Session(engine) as session:
        rows = session.exec(select(CartItem).order_by(CartItem.id)).all()
        assert [row.is_selected for row in rows] == [True, True, False]
        assert len(rows) == 3


def test_deselection_during_checkout_is_a_conflict_and_rolls_back(api, engine):
    add(api)
    fired = False

    def deselect(connection, cursor, statement, parameters, context, executemany):
        nonlocal fired
        if statement.startswith("DELETE FROM cart_items") and not fired:
            fired = True
            cursor.execute("UPDATE cart_items SET is_selected=0 WHERE buyer_id=2")

    event.listen(engine, "before_cursor_execute", deselect)
    try:
        response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
        assert response.status_code == 409
    finally:
        event.remove(engine, "before_cursor_execute", deselect)
    assert fired
    assert order_counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert cart(api)["items"][0]["is_selected"] is True


def test_legacy_cart_migration_is_repeatable_and_keeps_first_baseline(tmp_path, monkeypatch):
    value = create_engine(f"sqlite:///{tmp_path / 'legacy-cart.db'}")
    with value.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, price INTEGER)"))
        connection.execute(text("INSERT INTO products VALUES (1, 100)"))
        connection.execute(
            text(
                "CREATE TABLE cart_items "
                "(id INTEGER PRIMARY KEY, product_id INTEGER, quantity INTEGER)"
            )
        )
        connection.execute(text("INSERT INTO cart_items VALUES (1, 1, 2)"))
    monkeypatch.setattr(database, "engine", value)
    try:
        database.migrate_db()
        with value.begin() as connection:
            assert connection.execute(
                text("SELECT is_selected, price_at_add FROM cart_items")
            ).one() == (1, 100)
            connection.execute(text("UPDATE products SET price=120"))
            connection.execute(text("UPDATE cart_items SET is_selected=0"))
        database.migrate_db()
        with value.connect() as connection:
            assert connection.execute(
                text("SELECT is_selected, price_at_add FROM cart_items")
            ).one() == (0, 100)
    finally:
        value.dispose()


def test_reused_id_cannot_change_another_buyers_selection(api, engine):
    from src.services.cart import CartService

    original_id = add(api)
    replaced = False

    def replace_before_update(connection, cursor, statement, parameters, context, executemany):
        nonlocal replaced
        if statement.startswith("UPDATE cart_items SET is_selected") and not replaced:
            replaced = True
            with Session(engine) as other:
                CartService(other).remove_item(2, "P-100")
            with Session(engine) as other:
                result = CartService(other).add_item(3, "P-200", 1)
                assert result.cart.items[0].cart_item_id == original_id

    event.listen(engine, "before_cursor_execute", replace_before_update)
    try:
        response = select_item(api, original_id, False)
        assert response.status_code == 404
    finally:
        event.remove(engine, "before_cursor_execute", replace_before_update)
    assert replaced
    with Session(engine) as session:
        replacement = session.get(CartItem, original_id)
        assert replacement.buyer_id == 3
        assert replacement.is_selected is True
