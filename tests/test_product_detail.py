from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete

from src.auth import create_access_token, hash_password
from src.database import engine
from src.models.cart_item import CartItem
from src.models.product import Product
from src.models.user import User


@pytest.fixture(autouse=True)
def clean_detail_data():
    """Keep product-detail and cart tests isolated."""
    with Session(engine) as session:
        session.exec(delete(CartItem))
        session.exec(delete(Product))
        session.exec(delete(User).where(User.id == 20))
        session.commit()
        session.add(
            User(
                id=20,
                name="Detail Buyer",
                email="detail.buyer@marketplace.local",
                role="buyer",
                password_hash=hash_password("password"),
            )
        )
        session.add_all(
            [
                Product(
                    code="DETAIL-1",
                    seller_id=1,
                    name="Detail product",
                    description="A full product description.",
                    price=125,
                    stock_quantity=6,
                    image_url="/detail.jpg",
                    is_active=True,
                ),
                Product(
                    code="EMPTY-1",
                    seller_id=1,
                    name="Empty product",
                    price=125,
                    stock_quantity=0,
                    is_active=True,
                ),
                Product(
                    code="HIDDEN-1",
                    seller_id=1,
                    name="Hidden product",
                    price=125,
                    stock_quantity=5,
                    is_active=False,
                ),
            ]
        )
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(CartItem))
        session.exec(delete(Product))
        session.exec(delete(User).where(User.id == 20))
        session.commit()


def buyer_headers() -> dict[str, str]:
    with Session(engine) as session:
        buyer = session.get(User, 20)
        assert buyer is not None
        return {"Authorization": f"Bearer {create_access_token(buyer)}"}


def test_product_detail_returns_active_product_including_available_stock(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/products/DETAIL-1")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "DETAIL-1"
    assert body["name"] == "Detail product"
    assert body["description"] == "A full product description."
    assert body["price"] == 125.0
    assert body["thumbnail_url"] == "/detail.jpg"
    assert body["image_url"] == "/detail.jpg"
    assert body["stock_quantity"] == 6
    assert body["stock_status"] == "in_stock"


@pytest.mark.parametrize("code", ["HIDDEN-1", "MISSING-1"])
def test_product_detail_hides_inactive_and_unknown_products(
    client: TestClient,
    code: str,
) -> None:
    response = client.get(f"/api/v1/products/{code}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ERR_PRODUCT_NOT_FOUND"


def test_out_of_stock_product_remains_visible_but_unavailable(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/products/EMPTY-1")

    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 0
    assert response.json()["stock_status"] == "out_of_stock"


def test_buyer_can_add_product_to_database_backed_cart(client: TestClient) -> None:
    response = client.post(
        "/api/v1/cart/items",
        headers=buyer_headers(),
        json={"product_code": "DETAIL-1", "quantity": 2},
    )

    assert response.status_code == 201
    line = response.json()["data"]["items"][0]
    assert line["product_code"] == "DETAIL-1"
    assert line["quantity"] == 2
    with Session(engine) as session:
        item = session.exec(select_cart_item()).one()
        assert item.quantity == 2


def select_cart_item():
    """Keep the test query local and explicit."""
    from sqlmodel import select

    return select(CartItem).where(CartItem.buyer_id == 20)


def test_guest_cannot_add_product_to_cart(client: TestClient) -> None:
    response = client.post(
        "/api/v1/cart/items",
        json={"product_code": "DETAIL-1", "quantity": 1},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR_AUTH_REQUIRED"


def test_product_detail_page_is_served(client: TestClient) -> None:
    response = client.get("/products/DETAIL-1")

    assert response.status_code == 200
    assert 'id="product-detail"' in response.text
    assert 'src="/static/product-detail.js"' in response.text
    assert 'id="cart-link"' in response.text


@pytest.mark.parametrize("invalid_val", [True, "2", 2.5])
def test_quantity_validation_rejects_incorrect_types(client: TestClient, invalid_val) -> None:
    response = client.post(
        "/api/v1/cart/items",
        headers=buyer_headers(),
        json={"product_code": "DETAIL-1", "quantity": invalid_val},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


@pytest.mark.parametrize("invalid_qty", [0, -1, -5])
def test_quantity_validation_rejects_non_positive_integers(
    client: TestClient, invalid_qty: int
) -> None:
    response = client.post(
        "/api/v1/cart/items",
        headers=buyer_headers(),
        json={"product_code": "DETAIL-1", "quantity": invalid_qty},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_INVALID_QUANTITY"


def test_database_failure_returns_json_error_contract() -> None:
    from sqlalchemy.exc import SQLAlchemyError

    from src.database import get_session
    from src.main import create_app

    with Session(engine) as s:
        seeded_buyer = s.get(User, 20)

    class BrokenSession:
        def get(self, model, ident):
            if model == User:
                return seeded_buyer
            raise SQLAlchemyError("simulated database failure")

        def exec(self, *_args, **_kwargs):
            raise SQLAlchemyError("simulated database failure")

        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("simulated database failure")

        def commit(self):
            raise SQLAlchemyError("simulated database failure")

        def rollback(self):
            pass

    def broken_session():
        yield BrokenSession()

    app = create_app()
    app.dependency_overrides[get_session] = broken_session

    try:
        with TestClient(app) as test_client:
            # 1. GET product detail database failure
            resp_prod = test_client.get("/api/v1/products/DETAIL-1")
            assert resp_prod.status_code == 500
            assert resp_prod.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
            assert "Unable to load products right now" in resp_prod.json()["error"]["message"]

            # 2. POST cart items database failure
            resp_cart = test_client.post(
                "/api/v1/cart/items",
                headers=buyer_headers(),
                json={"product_code": "DETAIL-1", "quantity": 1},
            )
            assert resp_cart.status_code == 500
            assert resp_cart.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
            assert "Unable to update cart" in resp_cart.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


def setup_concurrency_db(tmp_path: Path, stock_qty: int = 6, initial_cart_qty: int = 0):
    from sqlmodel import create_engine

    from src.database import get_session
    from src.main import create_app

    db_path = tmp_path / "concurrent_test.db"
    file_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    with file_engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    SQLModel.metadata.create_all(file_engine)

    with Session(file_engine) as session:
        seller = User(
            id=1,
            name="Test Seller",
            email="seller@test.local",
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer = User(
            id=20,
            name="Detail Buyer",
            email="detail.buyer@marketplace.local",
            role="buyer",
            password_hash=hash_password("password"),
        )
        product = Product(
            id=1,
            code="DETAIL-1",
            seller_id=1,
            name="Detail product",
            description="A full product description.",
            price=125,
            stock_quantity=stock_qty,
            is_active=True,
        )
        session.add_all([seller, buyer, product])
        if initial_cart_qty > 0:
            session.add(CartItem(buyer_id=20, product_id=1, quantity=initial_cart_qty))
        session.commit()
        token = create_access_token(buyer)

    app = create_app()

    def get_test_session():
        with Session(file_engine) as s:
            yield s

    app.dependency_overrides[get_session] = get_test_session
    headers = {"Authorization": f"Bearer {token}"}
    return file_engine, app, headers


def test_concurrent_cart_additions_preserve_all_updates(tmp_path: Path) -> None:
    """Two concurrent additions to existing line (1 + 2 and 2) must yield 5."""
    from concurrent.futures import ThreadPoolExecutor

    file_engine, app, headers = setup_concurrency_db(
        tmp_path, stock_qty=10, initial_cart_qty=1
    )

    with TestClient(app) as test_client:
        def add_two():
            return test_client.post(
                "/api/v1/cart/items",
                headers=headers,
                json={"product_code": "DETAIL-1", "quantity": 2},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(add_two)
            f2 = executor.submit(add_two)
            r1 = f1.result()
            r2 = f2.result()

    assert r1.status_code == 200
    assert r2.status_code == 200

    with Session(file_engine) as session:
        item = session.exec(select_cart_item()).one()
        assert item.quantity == 5


def test_concurrent_cart_inserts_handle_conflict_gracefully(tmp_path: Path) -> None:
    """Two concurrent inserts for a previously absent line must not produce unhandled 500."""
    from concurrent.futures import ThreadPoolExecutor

    file_engine, app, headers = setup_concurrency_db(
        tmp_path, stock_qty=10, initial_cart_qty=0
    )

    with TestClient(app) as test_client:
        def add_two():
            return test_client.post(
                "/api/v1/cart/items",
                headers=headers,
                json={"product_code": "DETAIL-1", "quantity": 2},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(add_two)
            f2 = executor.submit(add_two)
            r1 = f1.result()
            r2 = f2.result()

    statuses = {r1.status_code, r2.status_code}
    assert statuses == {201, 200}

    with Session(file_engine) as session:
        item = session.exec(select_cart_item()).one()
        assert item.quantity == 4


def test_concurrent_additions_respect_stock_limit(tmp_path: Path) -> None:
    """Concurrent additions that together would exceed stock must reject the excess request."""
    from concurrent.futures import ThreadPoolExecutor

    file_engine, app, headers = setup_concurrency_db(
        tmp_path, stock_qty=3, initial_cart_qty=1
    )

    with TestClient(app) as test_client:
        def add_two():
            return test_client.post(
                "/api/v1/cart/items",
                headers=headers,
                json={"product_code": "DETAIL-1", "quantity": 2},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(add_two)
            f2 = executor.submit(add_two)
            r1 = f1.result()
            r2 = f2.result()

    status_codes = sorted([r1.status_code, r2.status_code])
    assert status_codes == [200, 409]

    conflict_response = r1 if r1.status_code == 409 else r2
    assert conflict_response.json()["error"]["code"] == "ERR_STOCK_EXCEEDED"

    with Session(file_engine) as session:
        item = session.exec(select_cart_item()).one()
        assert item.quantity == 3


def select_product(code: str):
    from sqlmodel import select

    return select(Product).where(Product.code == code)


def test_cart_route_served_and_detail_script_provides_cart_navigation(
    client: TestClient,
) -> None:
    """The /cart route is served and detail script provides cart route and quantity restoration."""
    cart_resp = client.get("/cart")
    assert cart_resp.status_code == 200
    assert 'id="cart"' in cart_resp.text
    assert 'id="cart-link"' in cart_resp.text

    script_resp = client.get("/static/product-detail.js")
    assert script_resp.status_code == 200
    assert "view-cart-link" in script_resp.text
    assert "/cart" in script_resp.text
    assert "getPreservedQuantity" in script_resp.text
    assert "quantityValue" in script_resp.text

