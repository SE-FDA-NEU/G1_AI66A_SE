"""Milestone 4: test cases TC-USxx-nn for the six P0 stories (see docs/testing.md).

Expected values are fixed from the requirements (limits, prices, statuses), not
read back from production constants. Each test uses a temporary SQLite file.
"""

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.testclient import TestClient

from src.auth import hash_password
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.product import Product
from src.models.user import User
from src.services.order_states import is_allowed_transition
from tests.cart_db import enable_foreign_keys

SELLER, BUYER, OTHER_BUYER, OTHER_SELLER = 1, 2, 3, 4
ACCOUNTS = [(SELLER, "seller"), (BUYER, "buyer"), (OTHER_BUYER, "buyer"), (OTHER_SELLER, "seller")]
DELIVERY = {
    "recipient_name": "M4 Buyer",
    "delivery_address": "123 Test Street",
    "phone_number": "0912345678",
}


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm4.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    encoded = hash_password("password")
    with Session(engine) as session:
        session.add_all(
            User(id=u, name=f"M4 {u}", email=f"m4-{u}@test.local", role=r, password_hash=encoded)
            for u, r in ACCOUNTS
        )
        session.commit()
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        headers = {}
        for u, _ in ACCOUNTS:
            res = client.post(
                "/api/v1/auth/login", json={"email": f"m4-{u}@test.local", "password": "password"}
            )
            assert res.status_code == 200
            headers[u] = {"Authorization": f"Bearer {res.json()['access_token']}"}
        yield client, engine, headers
    engine.dispose()


def new_product(env, name="M4 Item", price=100_000, stock=10, seller=SELLER):
    client, _, headers = env
    res = client.post(
        "/api/v1/seller/products",
        headers=headers[seller],
        json={
            "name": name,
            "description": "M4 test listing",
            "price": price,
            "stock_quantity": stock,
            "image_url": "https://example.com/m4.jpg",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


def add_to_cart(env, code, quantity, buyer=BUYER):
    client, _, headers = env
    return client.post(
        "/api/v1/cart/items", headers=headers[buyer], json={"product_code": code, "quantity": quantity}
    )


def checkout(env, key="m4-key", buyer=BUYER):
    client, _, headers = env
    return client.post("/api/v1/orders", headers={**headers[buyer], "Idempotency-Key": key}, json=DELIVERY)


def stock_of(engine, product_id):
    with Session(engine) as session:
        return session.get(Product, product_id).stock_quantity


# ---------------------------------------------------------------- US01 Catalog
def test_tc_us01_01_active_product_is_listed(env):
    client, _, _ = env
    product = new_product(env, name="M4 Catalog Visible")
    codes = [p["code"] for p in client.get("/api/v1/products?search=M4%20Catalog").json()["data"]]
    assert product["code"] in codes


def test_tc_us01_02_inactive_product_is_hidden(env):
    client, _, headers = env
    product = new_product(env, name="M4 Catalog Hidden")
    assert client.delete(f"/api/v1/seller/products/{product['id']}", headers=headers[SELLER]).status_code == 200
    codes = [p["code"] for p in client.get("/api/v1/products?search=M4%20Catalog").json()["data"]]
    assert product["code"] not in codes


@pytest.mark.parametrize(
    "count, first_page, total",
    [
        (19, 19, 19),  # TC-US01-03 just below page size
        (20, 20, 20),  # TC-US01-04 exactly page size
        (21, 20, 21),  # TC-US01-05 just above page size: a second page exists
    ],
)
def test_tc_us01_03_to_05_page_size_boundary(env, count, first_page, total):
    client, _, _ = env
    for i in range(count):
        new_product(env, name=f"M4 Page {i:02d}", stock=1)
    base = "/api/v1/products?search=M4%20Page&page_size=20"
    body = client.get(base).json()
    assert len(body["data"]) == first_page
    assert body["meta"]["total"] == total
    if total > 20:
        assert len(client.get(base + "&page=2").json()["data"]) == total - 20


# ----------------------------------------------------------- US02 Product detail
def test_tc_us02_01_existing_product_detail(env):
    client, _, _ = env
    product = new_product(env, price=123_000)
    body = client.get(f"/api/v1/products/{product['code']}").json()
    assert body["price"] == 123_000 and body["code"] == product["code"]


def test_tc_us02_02_unknown_product_is_404(env):
    client, _, _ = env
    assert client.get("/api/v1/products/NOPE-404").status_code == 404


@pytest.mark.parametrize("stock", [0, 1])  # TC-US02-03 out of stock, TC-US02-04 last unit
def test_tc_us02_03_04_stock_boundary_is_reported(env, stock):
    client, _, _ = env
    product = new_product(env, stock=stock)
    body = client.get(f"/api/v1/products/{product['code']}").json()
    assert body["stock_quantity"] == stock


# --------------------------------------------------------------------- US03 Cart
def test_tc_us03_01_add_valid_quantity(env):
    res = add_to_cart(env, new_product(env)["code"], 2)
    assert res.status_code == 201
    assert res.json()["data"]["cart_total"] == 200_000


@pytest.mark.parametrize(
    "quantity, ok",
    [
        (9, True),  # TC-US03-02 below the stock of 10
        (10, True),  # TC-US03-03 equal to stock
        (11, False),  # TC-US03-04 above stock: rejected, cart unchanged
    ],
)
def test_tc_us03_02_to_04_stock_boundary(env, quantity, ok):
    _, engine, _ = env
    product = new_product(env, stock=10)
    res = add_to_cart(env, product["code"], quantity)
    with Session(engine) as session:
        lines = session.exec(select(CartItem)).all()
    if ok:
        assert res.status_code == 201 and [l.quantity for l in lines] == [quantity]
    else:
        assert res.status_code in (409, 422) and lines == []


@pytest.mark.parametrize("quantity", [0, -1])  # TC-US03-05 / TC-US03-06
def test_tc_us03_05_06_non_positive_quantity_is_refused(env, quantity):
    res = add_to_cart(env, new_product(env)["code"], quantity)
    assert res.status_code == 400


# ----------------------------------------------------------------- US04 Checkout
def test_tc_us04_01_valid_checkout_creates_order_and_reduces_stock(env):
    _, engine, _ = env
    product = new_product(env, price=100_000, stock=5)
    add_to_cart(env, product["code"], 2)
    res = checkout(env)
    assert res.status_code == 201
    assert res.json()["data"]["total_amount"] == 200_000
    assert stock_of(engine, product["id"]) == 3


def test_tc_us04_02_empty_cart_is_refused(env):
    _, engine, _ = env
    res = checkout(env)
    assert res.status_code in (400, 409, 422)
    with Session(engine) as session:
        assert session.exec(select(Order)).all() == []


def test_tc_us04_03_stock_reduced_after_adding_is_refused_and_nothing_saved(env):
    _, engine, _ = env
    product = new_product(env, stock=3)
    add_to_cart(env, product["code"], 3)
    with Session(engine) as session:
        row = session.get(Product, product["id"])
        row.stock_quantity = 2  # another buyer bought one meanwhile
        session.add(row)
        session.commit()
    res = checkout(env)
    assert res.status_code == 409
    with Session(engine) as session:
        assert session.exec(select(Order)).all() == []
    assert stock_of(engine, product["id"]) == 2


def test_tc_us04_04_stock_exactly_equal_to_quantity_succeeds(env):
    _, engine, _ = env
    product = new_product(env, stock=2)
    add_to_cart(env, product["code"], 2)
    assert checkout(env).status_code == 201
    assert stock_of(engine, product["id"]) == 0


def test_tc_us04_05_same_idempotency_key_creates_one_order(env):
    _, engine, _ = env
    product = new_product(env, stock=5)
    add_to_cart(env, product["code"], 1)
    first, second = checkout(env, key="same"), checkout(env, key="same")
    assert first.status_code == 201 and second.status_code == 200
    with Session(engine) as session:
        assert len(session.exec(select(Order)).all()) == 1


# ------------------------------------------------------- US06 Seller creates product
VALID = {"name": "M4 Seller Item", "description": "ok", "price": 50_000, "stock_quantity": 5,
         "image_url": "https://example.com/a.jpg"}


def create(env, user, **changes):
    client, _, headers = env
    return client.post("/api/v1/seller/products", headers=headers[user], json={**VALID, **changes})


def test_tc_us06_01_seller_creates_valid_product(env):
    res = create(env, SELLER)
    assert res.status_code == 201 and res.json()["data"]["price"] == 50_000


def test_tc_us06_02_buyer_cannot_create_product(env):
    assert create(env, BUYER).status_code == 403


@pytest.mark.parametrize(
    "price, ok",
    [
        (-1, False),  # TC-US06-03 negative
        (0, False),  # TC-US06-04 zero is not a sale price
        (1, True),  # TC-US06-05 smallest valid price
        (1_000_000_000, True),  # TC-US06-06 maximum price
        (1_000_000_001, False),  # TC-US06-07 above maximum
    ],
)
def test_tc_us06_03_to_07_price_boundary(env, price, ok):
    assert (create(env, SELLER, price=price).status_code == 201) is ok


@pytest.mark.parametrize(
    "stock, ok",
    [(-1, False), (0, True), (1_000_000, True), (1_000_001, False)],  # TC-US06-08..11
)
def test_tc_us06_08_to_11_stock_boundary(env, stock, ok):
    assert (create(env, SELLER, stock_quantity=stock).status_code == 201) is ok


# ------------------------------------------------------------- US08 Seller orders
def place_order(env):
    product = new_product(env, stock=5)
    add_to_cart(env, product["code"], 1)
    assert checkout(env).status_code == 201
    client, _, headers = env
    rows = client.get("/api/v1/seller/orders", headers=headers[SELLER]).json()["data"]
    return rows[0]["id"]


def set_status(env, sub_id, status, seller=SELLER):
    client, _, headers = env
    return client.patch(
        f"/api/v1/seller/orders/{sub_id}/status", headers=headers[seller], json={"status": status}
    )


def test_tc_us08_01_seller_sees_own_order(env):
    client, _, headers = env
    sub_id = place_order(env)
    rows = client.get("/api/v1/seller/orders", headers=headers[SELLER]).json()["data"]
    assert [r["id"] for r in rows] == [sub_id]


def test_tc_us08_02_other_seller_sees_nothing_and_cannot_update(env):
    client, _, headers = env
    sub_id = place_order(env)
    assert client.get("/api/v1/seller/orders", headers=headers[OTHER_SELLER]).json()["data"] == []
    assert set_status(env, sub_id, "CONFIRMED", seller=OTHER_SELLER).status_code in (403, 404)


def test_tc_us08_03_valid_transition_succeeds(env):
    sub_id = place_order(env)
    res = set_status(env, sub_id, "CONFIRMED")
    assert res.status_code == 200 and res.json()["data"]["status"] == "CONFIRMED"


def test_tc_us08_04_invalid_transition_is_refused_and_status_unchanged(env):
    client, _, headers = env
    sub_id = place_order(env)
    set_status(env, sub_id, "CONFIRMED")
    assert set_status(env, sub_id, "DELIVERED").status_code == 400
    rows = client.get("/api/v1/seller/orders", headers=headers[SELLER]).json()["data"]
    assert rows[0]["status"] == "CONFIRMED"


@pytest.mark.parametrize(
    "current, target, allowed",
    [  # TC-US08-05 decision table for the seller state machine
        ("PENDING", "CONFIRMED", True),
        ("PENDING", "COMPLETED", False),
        ("CONFIRMED", "SHIPPED", True),
        ("CONFIRMED", "DELIVERED", False),
        ("SHIPPED", "DELIVERED", True),
        ("COMPLETED", "CANCELLED", False),
        ("CANCELLED", "CONFIRMED", False),
    ],
)
def test_tc_us08_05_transition_decision_table(current, target, allowed):
    assert is_allowed_transition("seller", current, target) is allowed


@pytest.mark.parametrize("count, first_page", [(19, 19), (20, 20), (21, 20)])  # TC-US08-06..08
def test_tc_us08_06_to_08_pagination_boundary(env, count, first_page):
    client, engine, headers = env
    from src.models.seller_order import SellerOrder

    place_order(env)
    with Session(engine) as session:
        template = session.exec(select(SellerOrder)).first()
        for _ in range(count - 1):
            parent = session.get(Order, template.order_id)
            clone = Order(**{**parent.model_dump(exclude={"id"}), "request_key": f"clone-{_}"})
            session.add(clone)
            session.flush()
            session.add(SellerOrder(**{**template.model_dump(exclude={"id"}), "order_id": clone.id}))
        session.commit()
    res = client.get("/api/v1/seller/orders?limit=20", headers=headers[SELLER]).json()
    assert len(res["data"]) == first_page and res["meta"]["total"] == count
