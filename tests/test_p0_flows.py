"""Issue #83: HTTP/database integration across P0 stories, not human usability evidence."""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.testclient import TestClient

from src.auth import hash_password
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import enable_foreign_keys

ACCOUNTS = [(1, "seller"), (2, "buyer"), (3, "buyer"), (4, "seller")]
DELIVERY = {
    "recipient_name": "P0 Buyer",
    "delivery_address": "123 Test Street",
    "phone_number": "0912345678",
}


@pytest.fixture
def flow(tmp_path):
    from sqlalchemy import event

    engine = create_engine(f"sqlite:///{tmp_path / 'p0.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    encoded = hash_password("password")
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id=uid,
                    name=f"P0 {uid}",
                    email=f"p0-{uid}@test.local",
                    role=role,
                    password_hash=encoded,
                )
                for uid, role in ACCOUNTS
            ]
        )
        session.commit()
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        headers = {}
        for uid, _ in ACCOUNTS:
            response = client.post(
                "/api/v1/auth/login", json={"email": f"p0-{uid}@test.local", "password": "password"}
            )
            assert response.status_code == 200
            headers[uid] = {"Authorization": f"Bearer {response.json()['access_token']}"}
        yield client, engine, headers
    engine.dispose()


def purchase(flow):
    client, engine, headers = flow
    products = []
    for seller, price in [(1, 100_000), (4, 300_000)]:
        result = client.post(
            "/api/v1/seller/products",
            headers=headers[seller],
            json={
                "name": f"P0 Flow Item {seller}",
                "description": "Integration test listing",
                "price": price,
                "stock_quantity": 5,
                "image_url": "https://example.com/p0.jpg",
            },
        )
        assert result.status_code == 201, result.text
        products.append(result.json()["data"])
    root = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert root.status_code == 307 and root.headers["location"] == "/products"
    assert client.get("/products").status_code == 200
    catalog = client.get("/api/v1/products?search=P0%20Flow%20Item").json()
    assert {p["code"] for p in catalog["data"]} == {p["code"] for p in products}
    for product in products:
        code = product["code"]
        assert client.get(f"/products/{code}").status_code == 200
        assert client.get(f"/api/v1/products/{code}").json()["price"] == product["price"]
        assert (
            client.post(
                "/api/v1/cart/items", headers=headers[2], json={"product_code": code, "quantity": 1}
            ).status_code
            == 201
        )
    code = products[0]["code"]
    changed = client.patch(f"/api/v1/cart/items/{code}", headers=headers[2], json={"quantity": 2})
    assert changed.json()["data"]["cart_total"] == 500_000
    assert client.get("/checkout").status_code == 200
    submitted = {**headers[2], "Idempotency-Key": "p0-end-to-end"}
    result = client.post("/api/v1/orders", headers=submitted, json=DELIVERY)
    assert result.status_code == 201, result.text
    order = result.json()["data"]
    assert order["total_amount"] == 500_000 and len(order["items"]) == 2
    assert client.get(f"/checkout/confirmation/{order['id']}").status_code == 200
    assert client.get(f"/api/v1/orders/{order['id']}", headers=headers[2]).json()["data"] == order
    assert client.get(f"/api/v1/orders/{order['id']}", headers=headers[3]).status_code == 404
    assert client.post("/api/v1/orders", headers=submitted, json=DELIVERY).status_code == 200
    assert client.get("/api/v1/cart", headers=headers[2]).json()["data"]["items"] == []
    with Session(engine) as session:
        assert len(session.exec(select(Order)).all()) == 1
        assert len(session.exec(select(SellerOrder)).all()) == 2
        assert len(session.exec(select(OrderItem)).all()) == 2
        assert session.exec(select(CartItem)).all() == []
        for product, stock in zip(products, [3, 4], strict=True):
            row = session.get(Product, product["id"])
            assert row.stock_quantity == stock and row.version == 2
    return order, products


def test_p0_seller_creation_to_buyer_receipt(flow):
    purchase(flow)


@pytest.mark.parametrize("terminal", ["COMPLETED", "CANCELLED"])
def test_p0_receipt_to_seller_fulfilment(flow, terminal):
    client, engine, headers = flow
    # Remains visible as a skipped dependency until PR #96 is integrated.
    if "/api/v1/seller/orders" not in client.get("/openapi.json").json()["paths"]:
        pytest.skip("US08 route absent: merge PR #96, update branch, and rerun #83")
    order, products = purchase(flow)
    assert client.get("/seller/orders").status_code == 200
    for seller in [1, 4]:
        listing = client.get("/api/v1/seller/orders", headers=headers[seller]).json()
        assert listing["meta"]["total"] == 1
        suborder = listing["data"][0]
        assert suborder["order_id"] == order["id"]
        other = 4 if seller == 1 else 1
        url = f"/api/v1/seller/orders/{suborder['id']}/status"
        assert (
            client.patch(url, headers=headers[other], json={"status": "PROCESSING"}).status_code
            == 403
        )
        assert (
            client.patch(url, headers=headers[seller], json={"status": "SHIPPED"}).status_code
            == 400
        )
        steps = ["CANCELLED"] if terminal == "CANCELLED" else ["PROCESSING", "SHIPPED", "COMPLETED"]
        for status in steps:
            updated = client.patch(url, headers=headers[seller], json={"status": status})
            assert updated.status_code == 200, updated.text
            assert updated.json()["data"]["status"] == status
        assert (
            client.patch(url, headers=headers[seller], json={"status": terminal}).status_code == 400
        )
    receipt = client.get(f"/api/v1/orders/{order['id']}", headers=headers[2]).json()["data"]
    assert receipt["status"] == terminal
    with Session(engine) as session:
        for product, stock in zip(products, [3, 4], strict=True):
            row = session.get(Product, product["id"])
            assert row.stock_quantity == (5 if terminal == "CANCELLED" else stock)
        suborders = session.exec(select(SellerOrder)).all()
        assert all(row.status == terminal for row in suborders)
        if terminal == "COMPLETED":
            assert all(row.completed_at is not None for row in suborders)
