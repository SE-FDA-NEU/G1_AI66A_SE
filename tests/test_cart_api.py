"""Tests for the cart API: authentication, HTTP contract and buyer isolation (US03, #79)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

import src.services.cart as cart_module
from src.api.cart import CART_DATABASE_ERROR_MESSAGE, ERROR_STATUS
from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.user import User
from src.services.cart import CartErrorCode, CartService
from tests.cart_db import (
    BUYER_ID,
    OTHER_BUYER_ID,
    SELLER_ID,
    add_product,
    change_product,
    create_cart_engine,
    stored_lines,
)

CART_ENDPOINTS = [
    ("GET", "/api/v1/cart", None),
    ("POST", "/api/v1/cart/items", {"product_code": "P-100", "quantity": 1}),
    ("PATCH", "/api/v1/cart/items/P-100", {"quantity": 1}),
    ("DELETE", "/api/v1/cart/items/P-100", None),
]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_cart_engine(tmp_path / "cart.db")
    yield engine
    engine.dispose()


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    """A client whose requests, including token checks, all use the test database."""
    app = create_app()

    def test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as client:
        yield client


def bearer(user_id: int, role: str) -> dict[str, str]:
    token = create_access_token(User(id=user_id, name="Test", email="t@test.local", role=role))
    return {"Authorization": f"Bearer {token}"}


BUYER = bearer(BUYER_ID, "buyer")
OTHER_BUYER = bearer(OTHER_BUYER_ID, "buyer")


def add_item(api: TestClient, code: str, quantity: int, headers: dict[str, str]):
    return api.post(
        "/api/v1/cart/items", json={"product_code": code, "quantity": quantity}, headers=headers
    )


def error_code(response) -> str:
    return response.json()["error"]["code"]


def lines(response) -> list[tuple[str, int, int]]:
    return [
        (item["product_code"], item["quantity"], item["line_total"])
        for item in response.json()["data"]["items"]
    ]


@pytest.mark.parametrize(("method", "path", "body"), CART_ENDPOINTS)
def test_guest_must_log_in(api: TestClient, method: str, path: str, body: dict | None) -> None:
    response = api.request(method, path, json=body)

    assert response.status_code == 401
    assert error_code(response) == "ERR_AUTH_REQUIRED"


def test_invalid_token_is_refused(api: TestClient) -> None:
    response = api.get("/api/v1/cart", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    assert error_code(response) == "ERR_INVALID_TOKEN"


@pytest.mark.parametrize(("method", "path", "body"), CART_ENDPOINTS)
def test_seller_has_no_cart(api: TestClient, method: str, path: str, body: dict | None) -> None:
    response = api.request(method, path, json=body, headers=bearer(SELLER_ID, "seller"))

    assert response.status_code == 403
    assert error_code(response) == "ERR_BUYER_REQUIRED"


def test_buyer_without_lines_gets_an_empty_cart(api: TestClient) -> None:
    response = api.get("/api/v1/cart", headers=BUYER)

    assert response.status_code == 200
    assert response.json() == {"data": {"items": [], "cart_total": 0}}


def test_add_creates_a_line_then_increases_it(api: TestClient, engine: Engine) -> None:
    product_id = add_product(engine, "P-100", price=150_000)

    created = add_item(api, "P-100", 2, BUYER)
    increased = add_item(api, "P-100", 1, BUYER)

    assert created.status_code == 201
    assert created.json() == {
        "data": {
            "items": [
                {
                    "product_id": product_id,
                    "product_code": "P-100",
                    "name": "Product P-100",
                    "image_url": "/images/p-100.jpg",
                    "unit_price": 150_000,
                    "quantity": 2,
                    "line_total": 300_000,
                    "available_stock": 10,
                    "availability": "available",
                }
            ],
            "cart_total": 300_000,
        }
    }
    assert increased.status_code == 200
    assert lines(increased) == [("P-100", 3, 450_000)]
    assert stored_lines(engine, BUYER_ID) == [("P-100", 3)]


def test_quantity_change_survives_a_reload(api: TestClient, engine: Engine) -> None:
    add_product(engine, "P-100", price=100_000)
    add_item(api, "P-100", 2, BUYER)

    updated = api.patch("/api/v1/cart/items/P-100", json={"quantity": 3}, headers=BUYER)
    reloaded = api.get("/api/v1/cart", headers=BUYER)

    assert updated.status_code == 200
    assert lines(reloaded) == [("P-100", 3, 300_000)]
    assert reloaded.json()["data"]["cart_total"] == 300_000


def test_quantity_above_stock_is_refused_and_the_previous_one_kept(
    api: TestClient, engine: Engine
) -> None:
    add_product(engine, "P-100", stock=10, reserved=3)
    add_item(api, "P-100", 2, BUYER)

    response = api.patch("/api/v1/cart/items/P-100", json={"quantity": 8}, headers=BUYER)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "ERR_STOCK_EXCEEDED",
            "message": "Cannot add more than 7 items (available stock limit)",
        }
    }
    assert lines(api.get("/api/v1/cart", headers=BUYER)) == [("P-100", 2, 200_000)]


def test_delete_removes_the_line_and_recalculates_the_total(
    api: TestClient, engine: Engine
) -> None:
    add_product(engine, "P-100", price=100_000)
    add_product(engine, "P-101", price=50_000)
    for code in ("P-100", "P-101"):
        add_item(api, code, 1, BUYER)

    first = api.delete("/api/v1/cart/items/P-100", headers=BUYER)
    last = api.delete("/api/v1/cart/items/P-101", headers=BUYER)

    assert first.status_code == 200
    assert lines(first) == [("P-101", 1, 50_000)]
    assert first.json()["data"]["cart_total"] == 50_000
    assert last.json() == {"data": {"items": [], "cart_total": 0}}
    assert stored_lines(engine, BUYER_ID) == []


@pytest.mark.parametrize("quantity", [0, -1])
def test_non_positive_quantity_is_a_bad_request(
    api: TestClient, engine: Engine, quantity: int
) -> None:
    add_product(engine, "P-100")

    response = add_item(api, "P-100", quantity, BUYER)

    assert response.status_code == 400
    assert error_code(response) == "ERR_INVALID_QUANTITY"
    assert stored_lines(engine, BUYER_ID) == []


@pytest.mark.parametrize(
    "body",
    [
        {"product_code": "P-100", "quantity": True},
        {"product_code": "P-100", "quantity": 1.5},
        {"product_code": "P-100", "quantity": "2"},
        {"product_code": "P-100"},
        {"quantity": 1},
    ],
)
def test_malformed_body_is_a_validation_error(api: TestClient, engine: Engine, body: dict) -> None:
    add_product(engine, "P-100")

    response = api.post("/api/v1/cart/items", json=body, headers=BUYER)

    assert response.status_code == 422
    assert error_code(response) == "ERR_VALIDATION"
    assert stored_lines(engine, BUYER_ID) == []


def test_product_code_over_20_characters_is_a_validation_error(api: TestClient) -> None:
    response = api.patch(f"/api/v1/cart/items/{'P' * 21}", json={"quantity": 1}, headers=BUYER)

    assert response.status_code == 422
    assert error_code(response) == "ERR_VALIDATION"


def test_unknown_and_withdrawn_products_are_refused(api: TestClient, engine: Engine) -> None:
    add_product(engine, "P-100")
    change_product(engine, "P-100", is_active=False)

    unknown = add_item(api, "P-999", 1, BUYER)
    withdrawn = add_item(api, "P-100", 1, BUYER)

    assert (unknown.status_code, error_code(unknown)) == (404, "ERR_PRODUCT_NOT_FOUND")
    assert (withdrawn.status_code, error_code(withdrawn)) == (409, "ERR_PRODUCT_UNAVAILABLE")


def test_change_to_a_line_not_in_the_cart_is_not_found(api: TestClient, engine: Engine) -> None:
    add_product(engine, "P-100")

    patch = api.patch("/api/v1/cart/items/P-100", json={"quantity": 1}, headers=BUYER)
    delete = api.delete("/api/v1/cart/items/P-100", headers=BUYER)

    assert (patch.status_code, error_code(patch)) == (404, "ERR_CART_ITEM_NOT_FOUND")
    assert (delete.status_code, error_code(delete)) == (404, "ERR_CART_ITEM_NOT_FOUND")


def test_buyers_only_see_and_change_their_own_cart(api: TestClient, engine: Engine) -> None:
    add_product(engine, "P-100")
    add_item(api, "P-100", 2, BUYER)

    other_cart = api.get("/api/v1/cart", headers=OTHER_BUYER)
    other_patch = api.patch("/api/v1/cart/items/P-100", json={"quantity": 5}, headers=OTHER_BUYER)
    other_delete = api.delete("/api/v1/cart/items/P-100", headers=OTHER_BUYER)

    assert other_cart.json() == {"data": {"items": [], "cart_total": 0}}
    assert other_patch.status_code == 404
    assert other_delete.status_code == 404
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]
    assert stored_lines(engine, OTHER_BUYER_ID) == []


def test_concurrent_insert_of_the_same_line_is_a_conflict(
    api: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_product(engine, "P-100")
    add_item(api, "P-100", 2, BUYER)
    monkeypatch.setattr(cart_module, "find_cart_item_for_product", lambda *_args: None)

    response = add_item(api, "P-100", 1, BUYER)

    assert response.status_code == 409
    assert error_code(response) == "ERR_CONCURRENCY_CONFLICT"
    assert stored_lines(engine, BUYER_ID) == [("P-100", 2)]


def test_database_failure_is_a_500_without_sql_details(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_get_cart(*_args) -> None:
        raise SQLAlchemyError("SELECT * FROM cart_items -- simulated failure")

    monkeypatch.setattr(CartService, "get_cart", broken_get_cart)

    response = api.get("/api/v1/cart", headers=BUYER)

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "ERR_DATABASE_FAILURE", "message": CART_DATABASE_ERROR_MESSAGE}
    }


def test_every_service_error_has_an_http_status() -> None:
    assert set(ERROR_STATUS) == set(CartErrorCode)
