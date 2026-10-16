"""US04 transaction tests use independent sessions on real SQLite files."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.orders import CheckoutRequest
from src.services.orders import CheckoutError, checkout, receipt
from tests.cart_db import add_product, create_cart_engine, stored_lines, stored_stock

BODY = {
    "recipient_name": "Buyer",
    "delivery_address": "123 Main Street",
    "phone_number": "0912345678",
}


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "checkout.db")
    yield value
    value.dispose()


def fill(engine, buyer=2, code="P-100", quantity=1):
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == code)).one()
        session.add(CartItem(buyer_id=buyer, product_id=product.id, quantity=quantity))
        session.commit()


def place(engine, buyer=2, key="request-1", body=None):
    with Session(engine) as session:
        return checkout(session, buyer, CheckoutRequest(**(body or BODY)), key)


def counts(engine):
    with Session(engine) as session:
        return [len(session.exec(select(model)).all()) for model in (Order, SellerOrder, OrderItem)]


def test_multi_seller_checkout_and_price_snapshots(engine):
    add_product(engine, "P-100", price=100, stock=8, reserved=2)
    add_product(engine, "P-200", price=300)
    with Session(engine) as session:
        session.add(User(id=4, name="Seller 2", email="seller2@test.local", role="seller"))
        session.commit()
        product = session.exec(select(Product).where(Product.code == "P-200")).one()
        product.seller_id = 4
        session.add(product)
        session.commit()
    fill(engine, quantity=2)
    fill(engine, code="P-200")
    result, created = place(engine)
    assert created and result.total_amount == 500 and result.status == "PENDING"
    assert counts(engine) == [1, 2, 2]
    assert stored_lines(engine, 2) == []
    assert stored_stock(engine, "P-100") == (6, 2)
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == "P-100")).one()
        assert product.version == 2
        product.price = 999
        session.add(product)
        session.commit()
        assert receipt(session, 2, result.id).total_amount == 500
        assert sorted(i.unit_price for i in receipt(session, 2, result.id).items) == [100, 300]


@pytest.mark.parametrize(
    "changes", [{"is_active": False}, {"stock_quantity": 0}, {"reserved_stock": 10}]
)
def test_invalid_second_item_rolls_back_everything(engine, changes):
    add_product(engine, "P-100")
    add_product(engine, "P-200")
    fill(engine)
    fill(engine, code="P-200")
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == "P-200")).one()
        for name, value in changes.items():
            setattr(product, name, value)
        session.add(product)
        session.commit()
    with pytest.raises(CheckoutError):
        place(engine)
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert len(stored_lines(engine, 2)) == 2


def test_failure_after_writes_rolls_back_and_session_remains_usable(engine, monkeypatch):
    import src.services.orders as module

    add_product(engine, "P-100")
    fill(engine)
    original = module.receipt
    monkeypatch.setattr(
        module,
        "receipt",
        lambda *_: (_ for _ in ()).throw(SQLAlchemyError("failure before commit")),
    )
    with Session(engine) as session:
        with pytest.raises(SQLAlchemyError):
            checkout(session, 2, CheckoutRequest(**BODY), "failure")
        session.commit()
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_lines(engine, 2) == [("P-100", 1)]
    monkeypatch.setattr(module, "receipt", original)
    assert place(engine)[1]


def test_replay_before_empty_cart_check_and_payload_conflict(engine):
    add_product(engine, "P-100")
    fill(engine)
    first, _ = place(engine)
    replay, created = place(engine)
    assert replay == first and not created
    with pytest.raises(CheckoutError, match="another request"):
        place(engine, body={**BODY, "delivery_address": "Different address"})
    with pytest.raises(CheckoutError):
        place(engine, buyer=3)
    assert counts(engine) == [1, 1, 1]
    assert stored_stock(engine, "P-100") == (9, 0)


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_requests_on_separate_connections(engine, same_request):
    add_product(engine, "P-100", stock=1)
    fill(engine)
    if not same_request:
        fill(engine, buyer=3)
    barrier = Barrier(2)

    def worker(buyer, key):
        barrier.wait(timeout=10)
        try:
            return place(engine, buyer, key)
        except CheckoutError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(worker, 2, "same" if same_request else "buyer2")
        b = pool.submit(worker, 2 if same_request else 3, "same" if same_request else "buyer3")
        results = [a.result(timeout=20), b.result(timeout=20)]
    assert counts(engine) == [1, 1, 1]
    assert stored_stock(engine, "P-100") == (0, 0)
    if same_request:
        assert all(isinstance(r, tuple) for r in results)
        assert results[0][0].id == results[1][0].id
        assert sum(r[1] for r in results) == 1
    else:
        assert sum(isinstance(r, tuple) for r in results) == 1
        assert len(stored_lines(engine, 2)) + len(stored_lines(engine, 3)) == 1


@pytest.fixture
def api(engine):
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client


def headers(engine, buyer=2, key="api-key"):
    with Session(engine) as session:
        token = create_access_token(session.get(User, buyer))
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def test_api_create_replay_and_ownership(api, engine):
    add_product(engine, "P-100")
    fill(engine)
    response = api.post("/api/v1/orders", json=BODY, headers=headers(engine))
    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert "request_key" not in order and "request_hash" not in order
    assert api.post("/api/v1/orders", json=BODY, headers=headers(engine)).status_code == 200
    assert api.get(f"/api/v1/orders/{order['id']}", headers=headers(engine)).status_code == 200
    other = api.get(f"/api/v1/orders/{order['id']}", headers=headers(engine, buyer=3))
    assert other.status_code == 404 and other.json()["error"]["code"] == "ERR_ORDER_NOT_FOUND"
    assert api.get("/api/v1/orders/999", headers=headers(engine)).status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        {"recipient_name": " "},
        {"delivery_address": ""},
        {"phone_number": "abc1234"},
        {"phone_number": "123"},
        {"total_amount": 1},
        {"recipient_name": "x" * 101},
    ],
)
def test_api_validation_does_not_write(api, engine, patch):
    response = api.post("/api/v1/orders", json={**BODY, **patch}, headers=headers(engine))
    assert response.status_code == 422
    assert counts(engine) == [0, 0, 0]


def test_auth_empty_cart_key_and_pages(api, engine):
    assert api.post("/api/v1/orders", json=BODY).status_code == 401
    assert (
        api.post("/api/v1/orders", json=BODY, headers=headers(engine, buyer=1)).status_code == 403
    )
    assert api.post("/api/v1/orders", json=BODY, headers=headers(engine)).status_code == 400
    assert (
        api.post("/api/v1/orders", json=BODY, headers=headers(engine, key=" ")).status_code == 400
    )
    for url in (
        "/checkout",
        "/checkout/confirmation/1",
        "/static/checkout.js",
        "/static/confirmation.js",
        "/static/checkout.css",
    ):
        assert api.get(url).status_code == 200


def test_existing_database_migration_is_repeatable(tmp_path, monkeypatch):
    from sqlmodel import create_engine

    import src.database as database

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy.begin() as connection:
        connection.execute(
            text("CREATE TABLE orders (id INTEGER PRIMARY KEY, total_amount INTEGER)")
        )
        connection.execute(text("INSERT INTO orders VALUES (1, 100)"))
    monkeypatch.setattr(database, "engine", legacy)
    database.migrate_db()
    database.migrate_db()
    with legacy.begin() as connection:
        assert connection.execute(text("SELECT request_key, request_hash FROM orders")).one() == (
            None,
            None,
        )
        connection.execute(text("UPDATE orders SET request_key='unique' WHERE id=1"))
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), legacy.begin() as connection:
        connection.execute(text("INSERT INTO orders (id, request_key) VALUES (2, 'unique')"))
    legacy.dispose()


def test_stale_product_version_aborts_checkout(engine, monkeypatch):
    add_product(engine, "P-100")
    fill(engine)
    original = Session.get

    def stale(session, model, identity, **kwargs):
        obj = original(session, model, identity, **kwargs)
        if model is Product:
            # Simulate another inventory writer after this request read its version.
            session.connection().execute(
                text("UPDATE products SET version = version + 1 WHERE id = :id"), {"id": identity}
            )
        return obj

    monkeypatch.setattr(Session, "get", stale)
    with pytest.raises(CheckoutError):
        place(engine)
    assert counts(engine) == [0, 0, 0]
    assert stored_lines(engine, 2) == [("P-100", 1)]
    assert stored_stock(engine, "P-100") == (10, 0)


def test_cart_quantity_change_aborts_checkout(engine):
    add_product(engine, "P-100")
    fill(engine)
    fired = False

    def change_line(connection, cursor, statement, parameters, context, executemany):
        nonlocal fired
        if statement.startswith("DELETE FROM cart_items") and not fired:
            fired = True
            cursor.execute("UPDATE cart_items SET quantity=2 WHERE buyer_id=2")

    event.listen(engine, "before_cursor_execute", change_line)
    try:
        with pytest.raises(CheckoutError, match="Cart changed"):
            place(engine)
    finally:
        event.remove(engine, "before_cursor_execute", change_line)
    assert fired
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_lines(engine, 2) == [("P-100", 1)]


def test_unrelated_constraint_failure_is_not_retried(engine):
    add_product(engine, "P-100")
    fill(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER reject_item BEFORE INSERT ON order_items "
                "BEGIN SELECT RAISE(ABORT, 'simulated constraint failure'); END"
            )
        )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        place(engine)
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_lines(engine, 2) == [("P-100", 1)]
