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
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import add_product, change_product, create_cart_engine, stored_stock

DELIVERY = {
    "recipient_name": "Buyer",
    "delivery_address": "123 Main",
    "phone_number": "0912345678",
}


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


def add(api, code="P-100", buyer=2, quantity=1):
    response = api.post(
        "/api/v1/cart/items",
        headers=auth(buyer),
        json={"product_code": code, "quantity": quantity},
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


def cart(api, buyer=2):
    response = api.get("/api/v1/cart", headers=auth(buyer))
    assert response.status_code == 200
    return response.json()["data"]


def ensure_seller(engine, seller_id: int = 5, name: str = "Third shop") -> None:
    with Session(engine) as session:
        if session.get(User, seller_id) is None:
            session.add(
                User(id=seller_id, name=name, email=f"shop{seller_id}@test.local", role="seller")
            )
            session.commit()


def add_custom_product(
    engine,
    code: str,
    seller_id: int = 1,
    *,
    price: int = 100,
    stock: int = 10,
    reserved: int = 0,
    active: bool = True,
) -> int:
    with Session(engine) as session:
        product = Product(
            code=code,
            seller_id=seller_id,
            name=f"Product {code}",
            price=price,
            stock_quantity=stock,
            reserved_stock=reserved,
            image_url=f"/images/{code.lower()}.jpg",
            is_active=active,
        )
        session.add(product)
        session.commit()
        return product.id


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


def test_select_shop_rolls_back_all_rows_when_an_update_fails(engine, monkeypatch):
    from src.services import cart as cart_service

    with Session(engine) as session:
        first_product = session.exec(select(Product).where(Product.code == "P-100")).one()
        second_product = session.exec(select(Product).where(Product.code == "P-200")).one()
        session.add_all(
            [
                CartItem(
                    buyer_id=2,
                    product_id=first_product.id,
                    quantity=1,
                    is_selected=False,
                    price_at_add=100,
                ),
                CartItem(
                    buyer_id=2,
                    product_id=second_product.id,
                    quantity=1,
                    is_selected=False,
                    price_at_add=200,
                ),
            ]
        )
        session.commit()

    original = cart_service.update_line_fields
    calls = 0

    def fail_second_update(session, line, **values):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated database update failure")
        return original(session, line, **values)

    monkeypatch.setattr(cart_service, "update_line_fields", fail_second_update)
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="simulated"):
            cart_service.CartService(session).select_shop(2, 1, True)
    with Session(engine) as session:
        rows = session.exec(
            select(CartItem).where(CartItem.buyer_id == 2).order_by(CartItem.id)
        ).all()
        assert [row.is_selected for row in rows] == [False, False]


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
    change_product(engine, "P-100", price=150)
    current_cart = cart(api)
    assert current_cart["selected_total"] == 450
    response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == current_cart["selected_total"] == 450
    assert order["total_amount"] == sum(line["line_total"] for line in order["items"])
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


# ==============================================================================
# Partial-Checkout Edge Cases (#104)
# ==============================================================================


# ------------------------------------------------------------------------------
# 1. Selecting One Item
# ------------------------------------------------------------------------------
def test_edge_case_select_single_item_among_multiple_in_same_shop(api, engine):
    """Selecting only 1 item among multiple items in the same shop checks out only that item."""
    add_custom_product(engine, "P-101", seller_id=1, price=150)
    add(api, "P-100")
    id_200 = add(api, "P-200")
    id_101 = add(api, "P-101")

    assert select_item(api, id_200, False).status_code == 200
    assert select_item(api, id_101, False).status_code == 200

    c = cart(api)
    assert c["cart_total"] == 450
    assert c["selected_total"] == 100
    assert [line["is_selected"] for line in c["items"]] == [True, False, False]

    response = api.post(
        "/api/v1/orders", headers=auth(key="single-item-same-shop"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 100
    assert len(order["items"]) == 1
    assert order["items"][0]["product_code"] == "P-100"
    assert len(order["sub_orders"]) == 1
    assert order["sub_orders"][0]["seller_id"] == 1

    remaining = cart(api)
    assert len(remaining["items"]) == 2
    assert [line["product_code"] for line in remaining["items"]] == ["P-200", "P-101"]
    assert all(not line["is_selected"] for line in remaining["items"])

    assert stored_stock(engine, "P-100") == (9, 0)
    assert stored_stock(engine, "P-200") == (10, 0)
    assert stored_stock(engine, "P-101") == (10, 0)


def test_edge_case_select_single_item_in_multi_shop_cart(api, engine):
    """Selecting only 1 item from Shop 2 leaves Shop 1 items in cart and creates 1 seller order."""
    id_100 = add(api, "P-100")
    id_200 = add(api, "P-200")
    add(api, "P-300")

    assert select_item(api, id_100, False).status_code == 200
    assert select_item(api, id_200, False).status_code == 200

    c = cart(api)
    assert c["selected_total"] == 300
    assert c["cart_total"] == 600

    response = api.post(
        "/api/v1/orders", headers=auth(key="single-item-multi-shop"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 300
    assert len(order["items"]) == 1
    assert order["items"][0]["product_code"] == "P-300"
    assert len(order["sub_orders"]) == 1
    assert order["sub_orders"][0]["seller_id"] == 4

    remaining = cart(api)
    assert len(remaining["items"]) == 2
    assert {line["product_code"] for line in remaining["items"]} == {"P-100", "P-200"}
    assert all(line["seller_id"] == 1 for line in remaining["items"])

    assert stored_stock(engine, "P-300") == (9, 0)
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_stock(engine, "P-200") == (10, 0)


# ------------------------------------------------------------------------------
# 2. Selecting Whole Shop
# ------------------------------------------------------------------------------
def test_edge_case_select_whole_shop_multi_shop(api, engine):
    """Selecting whole Shop 1 checks out all Shop 1 items and creates only 1 seller order."""
    add(api, "P-100")
    add(api, "P-200")
    add(api, "P-300")

    assert api.patch(
        "/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": True}
    ).status_code == 200
    assert api.patch(
        "/api/v1/cart/select-shop/4", headers=auth(), json={"is_selected": False}
    ).status_code == 200

    c = cart(api)
    assert c["selected_total"] == 300
    assert [line["is_selected"] for line in c["items"]] == [True, True, False]

    response = api.post(
        "/api/v1/orders", headers=auth(key="whole-shop-checkout"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 300
    assert len(order["items"]) == 2
    assert {line["product_code"] for line in order["items"]} == {"P-100", "P-200"}
    assert len(order["sub_orders"]) == 1
    assert order["sub_orders"][0]["seller_id"] == 1

    remaining = cart(api)
    assert len(remaining["items"]) == 1
    assert remaining["items"][0]["product_code"] == "P-300"
    assert remaining["items"][0]["seller_id"] == 4
    assert remaining["items"][0]["is_selected"] is False

    assert stored_stock(engine, "P-100") == (9, 0)
    assert stored_stock(engine, "P-200") == (9, 0)
    assert stored_stock(engine, "P-300") == (10, 0)


def test_edge_case_select_whole_shop_skips_unavailable_items(api, engine):
    """Selecting a whole shop automatically skips unavailable rows in that shop."""
    add(api, "P-100")
    add(api, "P-200")
    change_product(engine, "P-200", stock_quantity=0)

    res = api.patch("/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": True})
    assert res.status_code == 200
    lines = res.json()["data"]["items"]
    assert lines[0]["is_selected"] is True
    assert lines[1]["is_selected"] is False
    assert res.json()["data"]["selected_total"] == 100

    response = api.post(
        "/api/v1/orders", headers=auth(key="whole-shop-skip-unavail"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 100
    assert len(order["items"]) == 1
    assert order["items"][0]["product_code"] == "P-100"

    remaining = cart(api)
    assert len(remaining["items"]) == 1
    assert remaining["items"][0]["product_code"] == "P-200"
    assert remaining["items"][0]["is_selected"] is False


def test_edge_case_deselect_whole_shop_prevents_empty_checkout(api, engine):
    """Deselecting all shops produces selected_total=0 and blocks checkout with 400."""
    add(api, "P-100")
    add(api, "P-300")

    assert api.patch(
        "/api/v1/cart/select-shop/1", headers=auth(), json={"is_selected": False}
    ).status_code == 200
    assert api.patch(
        "/api/v1/cart/select-shop/4", headers=auth(), json={"is_selected": False}
    ).status_code == 200

    assert cart(api)["selected_total"] == 0

    response = api.post(
        "/api/v1/orders", headers=auth(key="all-shops-deselected"), json=DELIVERY
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_EMPTY_CART"
    assert order_counts(engine) == [0, 0, 0]


# ------------------------------------------------------------------------------
# 3. Mixed-Shop Selection
# ------------------------------------------------------------------------------
def test_edge_case_mixed_shop_selection_across_three_shops(api, engine):
    """Mixed selection across 3 shops orders selected items and preserves unselected ones."""
    ensure_seller(engine, 5, "Third shop")
    add_custom_product(engine, "P-301", seller_id=4, price=350)
    add_custom_product(engine, "P-400", seller_id=5, price=400)

    add(api, "P-100")  # Seller 1, 100
    id_200 = add(api, "P-200")  # Seller 1, 200
    add(api, "P-300")  # Seller 4, 300
    add(api, "P-301")  # Seller 4, 350
    id_400 = add(api, "P-400")  # Seller 5, 400

    assert select_item(api, id_200, False).status_code == 200
    assert select_item(api, id_400, False).status_code == 200

    c = cart(api)
    assert c["cart_total"] == 1350
    assert c["selected_total"] == 750  # 100 + 300 + 350

    response = api.post(
        "/api/v1/orders", headers=auth(key="mixed-three-shops"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 750
    assert len(order["items"]) == 3
    assert {line["product_code"] for line in order["items"]} == {"P-100", "P-300", "P-301"}

    assert len(order["sub_orders"]) == 2
    sub_map = {so["seller_id"]: so for so in order["sub_orders"]}
    assert 1 in sub_map and 4 in sub_map and 5 not in sub_map

    remaining = cart(api)
    assert len(remaining["items"]) == 2
    assert {line["product_code"] for line in remaining["items"]} == {"P-200", "P-400"}
    assert all(not line["is_selected"] for line in remaining["items"])

    assert stored_stock(engine, "P-100") == (9, 0)
    assert stored_stock(engine, "P-300") == (9, 0)
    assert stored_stock(engine, "P-301") == (9, 0)
    assert stored_stock(engine, "P-200") == (10, 0)
    assert stored_stock(engine, "P-400") == (10, 0)


# ------------------------------------------------------------------------------
# 4. Unavailable Items
# ------------------------------------------------------------------------------
def test_edge_case_unavailable_items_refuse_direct_selection(api, engine):
    """Directly selecting unavailable items returns 409 ERR_CONFLICT in all scenarios."""
    add_custom_product(engine, "P-INACTIVE", seller_id=1, active=False)
    add_custom_product(engine, "P-OUT", seller_id=1, stock=0)
    add_custom_product(engine, "P-RESERVED", seller_id=1, stock=5, reserved=5)
    p_mod_id = add_custom_product(engine, "P-MOD", seller_id=1)
    with Session(engine) as session:
        meta = session.exec(
            select(ProductMetadata).where(ProductMetadata.product_id == p_mod_id)
        ).first()
        if meta:
            meta.is_moderated_deactivated = True
            session.add(meta)
        else:
            session.add(
                ProductMetadata(product_id=p_mod_id, is_moderated_deactivated=True)
            )
        session.commit()

    with Session(engine) as session:
        first = session.exec(select(Product).where(Product.code == "P-INACTIVE")).one()
        second = session.exec(select(Product).where(Product.code == "P-OUT")).one()
        third = session.exec(select(Product).where(Product.code == "P-RESERVED")).one()
        fourth = session.exec(select(Product).where(Product.code == "P-MOD")).one()
        session.add_all([
            CartItem(
                buyer_id=2, product_id=first.id, quantity=1, is_selected=False, price_at_add=100
            ),
            CartItem(
                buyer_id=2, product_id=second.id, quantity=1, is_selected=False, price_at_add=100
            ),
            CartItem(
                buyer_id=2, product_id=third.id, quantity=1, is_selected=False, price_at_add=100
            ),
            CartItem(
                buyer_id=2, product_id=fourth.id, quantity=1, is_selected=False, price_at_add=100
            ),
        ])
        session.commit()

    c = cart(api)
    for line in c["items"]:
        res = select_item(api, line["cart_item_id"], True)
        assert res.status_code == 409


def test_edge_case_selected_item_becoming_unavailable_deselected_on_cart_get(api, engine):
    """A selected item that loses stock is automatically deselected on next cart retrieval."""
    id_100 = add(api, "P-100")
    add(api, "P-200")

    change_product(engine, "P-100", stock_quantity=0)

    c = cart(api)
    assert c["selected_total"] == 200
    by_code = {item["product_code"]: item for item in c["items"]}
    assert by_code["P-100"]["is_selected"] is False
    assert by_code["P-100"]["availability"] == "insufficient_stock"
    assert by_code["P-200"]["is_selected"] is True

    with Session(engine) as session:
        assert session.get(CartItem, id_100).is_selected is False

    response = api.post(
        "/api/v1/orders", headers=auth(key="checkout-auto-deselected"), json=DELIVERY
    )
    assert response.status_code == 201
    assert response.json()["data"]["total_amount"] == 200


def test_edge_case_restocked_item_remains_deselected_until_user_action(api, engine):
    """Replenishing stock for a deselected item leaves it unselected until explicit buyer action."""
    id_100 = add(api, "P-100")
    change_product(engine, "P-100", stock_quantity=0)
    assert cart(api)["items"][0]["is_selected"] is False

    change_product(engine, "P-100", stock_quantity=20)
    after_restock = cart(api)
    assert after_restock["items"][0]["is_selected"] is False
    assert after_restock["items"][0]["availability"] == "available"
    assert after_restock["selected_total"] == 0

    assert select_item(api, id_100, True).status_code == 200
    assert cart(api)["items"][0]["is_selected"] is True
    assert cart(api)["selected_total"] == 100


def test_edge_case_cart_with_only_unavailable_items_fails_checkout(api, engine):
    """A cart containing only unavailable items cannot be checked out."""
    add(api, "P-100")
    add(api, "P-200")
    change_product(engine, "P-100", stock_quantity=0)
    change_product(engine, "P-200", stock_quantity=0)

    assert cart(api)["selected_total"] == 0
    response = api.post(
        "/api/v1/orders", headers=auth(key="all-unavailable-fail"), json=DELIVERY
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_EMPTY_CART"


# ------------------------------------------------------------------------------
# 5. Price Changes
# ------------------------------------------------------------------------------
def test_edge_case_price_increase_and_decrease_in_partial_checkout(api, engine):
    """Price changes update line_total and selected_total while keeping price_at_add baseline."""
    add(api, "P-100")  # added at 100
    add(api, "P-200")  # added at 200
    id_300 = add(api, "P-300")  # added at 300

    change_product(engine, "P-100", price=180)
    change_product(engine, "P-200", price=130)
    change_product(engine, "P-300", price=240)

    assert select_item(api, id_300, False).status_code == 200

    c = cart(api)
    by_code = {line["product_code"]: line for line in c["items"]}
    assert (by_code["P-100"]["price_at_add"], by_code["P-100"]["unit_price"]) == (100, 180)
    assert by_code["P-100"]["price_changed"] is True
    assert (by_code["P-200"]["price_at_add"], by_code["P-200"]["unit_price"]) == (200, 130)
    assert by_code["P-200"]["price_changed"] is True
    assert (by_code["P-300"]["price_at_add"], by_code["P-300"]["unit_price"]) == (300, 240)
    assert by_code["P-300"]["price_changed"] is True
    assert c["selected_total"] == 310  # 180 + 130

    response = api.post(
        "/api/v1/orders", headers=auth(key="price-changes-order"), json=DELIVERY
    )
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 310
    unit_prices = {item["product_code"]: item["unit_price"] for item in order["items"]}
    assert unit_prices == {"P-100": 180, "P-200": 130}

    remaining = cart(api)
    assert len(remaining["items"]) == 1
    rem_item = remaining["items"][0]
    assert rem_item["product_code"] == "P-300"
    assert rem_item["price_at_add"] == 300
    assert rem_item["unit_price"] == 240
    assert rem_item["price_changed"] is True
    assert rem_item["is_selected"] is False


def test_edge_case_quantity_update_preserves_historical_price_at_add(api, engine):
    """Increasing or changing quantity does not overwrite the historical price_at_add."""
    id_100 = add(api, "P-100")
    change_product(engine, "P-100", price=250)

    res = api.patch("/api/v1/cart/items/P-100", headers=auth(), json={"quantity": 3})
    assert res.status_code == 200
    line = res.json()["data"]["items"][0]
    assert line["price_at_add"] == 100
    assert line["unit_price"] == 250
    assert line["line_total"] == 750
    assert line["price_changed"] is True

    with Session(engine) as session:
        assert session.get(CartItem, id_100).price_at_add == 100


# ------------------------------------------------------------------------------
# 6. Failed Checkout
# ------------------------------------------------------------------------------
def test_edge_case_failed_checkout_stock_depletion_rolls_back_and_preserves_cart(api, engine):
    """When stock is depleted right before checkout, entire checkout rolls back cleanly."""
    id_100 = add(api, "P-100", quantity=2)
    id_200 = add(api, "P-200", quantity=1)
    select_item(api, id_200, False)

    change_product(engine, "P-100", stock_quantity=1)

    response = api.post(
        "/api/v1/orders", headers=auth(key="depleted-stock-checkout"), json=DELIVERY
    )
    assert response.status_code == 409
    assert order_counts(engine) == [0, 0, 0]

    assert stored_stock(engine, "P-100") == (1, 0)
    assert stored_stock(engine, "P-200") == (10, 0)

    with Session(engine) as session:
        rows = session.exec(select(CartItem).where(CartItem.buyer_id == 2)).all()
        assert len(rows) == 2
        by_id = {row.id: row for row in rows}
        assert by_id[id_100].quantity == 2
        assert by_id[id_200].quantity == 1


def test_edge_case_failed_checkout_database_error_rolls_back_cleanly(api, engine):
    """A database error during checkout preserves all selected and unselected cart rows."""
    from sqlalchemy.exc import OperationalError

    add(api, "P-100")
    id_200 = add(api, "P-200")
    select_item(api, id_200, False)

    def fail_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO orders "):
            raise OperationalError("INSERT INTO orders", {}, Exception("simulated DB crash"))

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        response = api.post(
            "/api/v1/orders", headers=auth(key="db-fail-checkout"), json=DELIVERY
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)

    assert order_counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_stock(engine, "P-200") == (10, 0)

    with Session(engine) as session:
        rows = session.exec(select(CartItem).where(CartItem.buyer_id == 2)).all()
        assert len(rows) == 2


# ------------------------------------------------------------------------------
# 7. Preservation of Unselected Cart Rows
# ------------------------------------------------------------------------------
def test_edge_case_multiple_sequential_partial_checkouts(api, engine):
    """Sequential partial checkouts from the same cart preserve remaining items until empty."""
    ensure_seller(engine, 5, "Third shop")
    add_custom_product(engine, "P-400", seller_id=5, price=400)

    add(api, "P-100", quantity=2)  # Shop 1: 100 * 2 = 200
    id_200 = add(api, "P-200", quantity=1)  # Shop 1: 200 * 1 = 200
    add(api, "P-300", quantity=3)  # Shop 2: 300 * 3 = 900
    id_400 = add(api, "P-400", quantity=1)  # Shop 3: 400 * 1 = 400

    # Step 1: Select P-100 and P-300; deselect P-200 and P-400
    select_item(api, id_200, False)
    select_item(api, id_400, False)

    res1 = api.post("/api/v1/orders", headers=auth(key="seq-step-1"), json=DELIVERY)
    assert res1.status_code == 201
    assert res1.json()["data"]["total_amount"] == 1100

    rem1 = cart(api)
    assert len(rem1["items"]) == 2
    assert {i["product_code"] for i in rem1["items"]} == {"P-200", "P-400"}
    assert stored_stock(engine, "P-100") == (8, 0)
    assert stored_stock(engine, "P-300") == (7, 0)
    assert stored_stock(engine, "P-200") == (10, 0)
    assert stored_stock(engine, "P-400") == (10, 0)

    # Step 2: Select P-200; P-400 stays unselected
    select_item(api, id_200, True)
    res2 = api.post("/api/v1/orders", headers=auth(key="seq-step-2"), json=DELIVERY)
    assert res2.status_code == 201
    assert res2.json()["data"]["total_amount"] == 200

    rem2 = cart(api)
    assert len(rem2["items"]) == 1
    assert rem2["items"][0]["product_code"] == "P-400"
    assert rem2["items"][0]["is_selected"] is False
    assert stored_stock(engine, "P-200") == (9, 0)

    # Step 3: Select P-400
    select_item(api, id_400, True)
    res3 = api.post("/api/v1/orders", headers=auth(key="seq-step-3"), json=DELIVERY)
    assert res3.status_code == 201
    assert res3.json()["data"]["total_amount"] == 400

    rem3 = cart(api)
    assert len(rem3["items"]) == 0
    assert stored_stock(engine, "P-400") == (9, 0)

    assert order_counts(engine) == [3, 4, 4]


def test_edge_case_unselected_cart_rows_isolated_across_different_buyers(api, engine):
    """One buyer's partial checkout has zero impact on another buyer's cart selections."""
    add(api, "P-100", buyer=2)
    id_200_b2 = add(api, "P-200", buyer=2)
    select_item(api, id_200_b2, False, buyer=2)

    add(api, "P-200", buyer=3)
    id_300_b3 = add(api, "P-300", buyer=3)
    select_item(api, id_300_b3, False, buyer=3)

    res = api.post("/api/v1/orders", headers=auth(buyer=2, key="b2-checkout"), json=DELIVERY)
    assert res.status_code == 201

    c_b3 = cart(api, buyer=3)
    assert len(c_b3["items"]) == 2
    assert c_b3["items"][0]["product_code"] == "P-200"
    assert c_b3["items"][0]["is_selected"] is True
    assert c_b3["items"][1]["product_code"] == "P-300"
    assert c_b3["items"][1]["is_selected"] is False

    c_b2 = cart(api, buyer=2)
    assert len(c_b2["items"]) == 1
    assert c_b2["items"][0]["product_code"] == "P-200"
    assert c_b2["items"][0]["is_selected"] is False


def test_edge_case_unselected_cart_row_with_quantity_greater_than_one(api, engine):
    """Unselected rows with quantities greater than 1 retain their exact quantity after checkout."""
    add(api, "P-100", quantity=1)
    id_200 = add(api, "P-200", quantity=7)
    select_item(api, id_200, False)

    res = api.post(
        "/api/v1/orders", headers=auth(key="multi-qty-preserve"), json=DELIVERY
    )
    assert res.status_code == 201

    remaining = cart(api)
    assert len(remaining["items"]) == 1
    assert remaining["items"][0]["product_code"] == "P-200"
    assert remaining["items"][0]["quantity"] == 7
    assert remaining["items"][0]["is_selected"] is False
    assert remaining["items"][0]["price_at_add"] == 200
    assert remaining["items"][0]["line_total"] == 1400


def add_variants(engine, code="P-100", prices=(120, 130)):
    """Variants of one product; each starts with 5 units."""
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == code)).one()
        variants = [
            ProductVariant(
                product_id=product.id,
                seller_id=product.seller_id,
                sku=f"{code}-{price}",
                name=f"Option {price}",
                price=price,
                stock_quantity=5,
            )
            for price in prices
        ]
        session.add_all(variants)
        session.commit()
        return [variant.id for variant in variants]


def add_variant(api, variant_id, code="P-100"):
    response = api.post(
        "/api/v1/cart/items",
        headers=auth(),
        json={"product_code": code, "quantity": 1, "variant_id": variant_id},
    )
    assert response.status_code == 201
    return next(
        line["cart_item_id"]
        for line in response.json()["data"]["items"]
        if line["variant_id"] == variant_id
    )


def variant_stock(engine, variant_id):
    with Session(engine) as session:
        return session.get(ProductVariant, variant_id).stock_quantity


def test_selected_variant_is_ordered_and_other_variant_rows_survive(api, engine):
    chosen, other = add_variants(engine)
    add_variant(api, chosen)
    kept = add_variant(api, other)
    assert select_item(api, kept, False).status_code == 200
    # An unavailable variant that is not selected must not block the order.
    with Session(engine) as session:
        session.get(ProductVariant, other).is_active = False
        session.commit()

    response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    assert response.status_code == 201
    order = response.json()["data"]
    assert order["total_amount"] == 120
    with Session(engine) as session:
        assert [(item.variant_id, item.quantity) for item in session.exec(select(OrderItem))] == [
            (chosen, 1)
        ]
        rows = session.exec(select(CartItem).where(CartItem.buyer_id == 2)).all()
        assert [(row.id, row.variant_id, row.is_selected) for row in rows] == [(kept, other, False)]
    assert (variant_stock(engine, chosen), variant_stock(engine, other)) == (4, 5)
    assert stored_stock(engine, "P-100") == (10, 0)


def test_cart_id_reused_for_another_variant_during_checkout_is_a_conflict(api, engine):
    from src.services.cart import CartService

    ordered, replacement = add_variants(engine)
    original_id = add_variant(api, ordered)
    replaced = False

    def replace_before_order(connection, cursor, statement, parameters, context, executemany):
        # Another request removes the line and adds a different variant after checkout has
        # read the cart; SQLite hands the new row the freed ID.
        nonlocal replaced
        if statement.startswith("INSERT INTO orders") and not replaced:
            replaced = True
            with Session(engine) as other:
                CartService(other).remove_item(2, "P-100", ordered)
            with Session(engine) as other:
                result = CartService(other).add_item(2, "P-100", 1, replacement)
                assert result.cart.items[0].cart_item_id == original_id

    event.listen(engine, "before_cursor_execute", replace_before_order)
    try:
        response = api.post("/api/v1/orders", headers=auth(), json=DELIVERY)
    finally:
        event.remove(engine, "before_cursor_execute", replace_before_order)
    assert replaced
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ERR_CONCURRENCY_CONFLICT"
    assert order_counts(engine) == [0, 0, 0]
    assert (variant_stock(engine, ordered), variant_stock(engine, replacement)) == (5, 5)
    with Session(engine) as session:
        rows = session.exec(select(CartItem).where(CartItem.buyer_id == 2)).all()
        assert [(row.id, row.variant_id, row.is_selected) for row in rows] == [
            (original_id, replacement, True)
        ]
