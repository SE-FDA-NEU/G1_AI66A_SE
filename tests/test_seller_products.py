"""US06 seller product creation (#81): API, ownership, validation, codes and rollback.

Every test builds its own SQLite file (see tests/cart_db.py) and reads committed rows back
through a new session, never from objects the service still holds.
"""

import re
import socket
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select
from starlette.testclient import TestClient

import src.services.seller_products as service
from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.product import Product
from src.models.user import User
from src.schemas.seller_products import (
    DESCRIPTION_MAX_LENGTH,
    IMAGE_URL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    PRICE_MAX,
    STOCK_MAX,
    VALIDATION_MESSAGE,
    ProductCreate,
)
from src.services.seller_products import (
    MAX_CODE_ATTEMPTS,
    SellerProductError,
    create_product,
    generate_product_code,
)
from tests.cart_db import BUYER_ID, SELLER_ID, add_product, create_cart_engine

OTHER_SELLER_ID = 4
URL = "/api/v1/seller/products"
CODE_PATTERN = re.compile(r"^P-[0-9A-F]{18}$")
MISSING = object()

VALID = {
    "name": "Training Mouse",
    "description": "Wireless mouse for study and office work.",
    "price": 180_000,
    "stock_quantity": 10,
    "image_url": "https://example.com/mouse.jpg",
}


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "seller_products.db")
    with Session(value) as session:
        session.add(
            User(id=OTHER_SELLER_ID, name="Seller B", email="seller-b@test.local", role="seller")
        )
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


def headers(engine, user_id=SELLER_ID, **token_options):
    with Session(engine) as session:
        token = create_access_token(session.get(User, user_id), **token_options)
    return {"Authorization": f"Bearer {token}"}


def stored(engine) -> list[Product]:
    """Committed products, read through a new session."""
    with Session(engine) as session:
        return list(session.exec(select(Product).order_by(Product.id)).all())


def with_patch(patch: dict) -> dict:
    body = {**VALID, **patch}
    return {name: value for name, value in body.items() if value is not MISSING}


# Task 1: create a listing owned by the authenticated seller


def test_seller_creates_an_active_listing_with_trimmed_values(api, engine):
    body = {**VALID, "name": "  Training Mouse  ", "description": "\n Wireless mouse. \t"}
    response = api.post(URL, json=body, headers=headers(engine))

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert CODE_PATTERN.match(data["code"])
    assert data == {
        "id": data["id"],
        "code": data["code"],
        "seller_id": SELLER_ID,
        "name": "Training Mouse",
        "description": "Wireless mouse.",
        "price": 180_000,
        "stock_quantity": 10,
        "reserved_stock": 0,
        "image_url": "https://example.com/mouse.jpg",
        "is_active": True,
        "version": 1,
    }
    [product] = stored(engine)
    assert product.model_dump() == data


def test_each_seller_owns_the_listings_they_create(api, engine):
    first = api.post(URL, json=VALID, headers=headers(engine, SELLER_ID)).json()["data"]
    second = api.post(URL, json=VALID, headers=headers(engine, OTHER_SELLER_ID)).json()["data"]

    assert (first["seller_id"], second["seller_id"]) == (SELLER_ID, OTHER_SELLER_ID)
    assert first["code"] != second["code"]
    assert [(p.code, p.seller_id) for p in stored(engine)] == [
        (first["code"], SELLER_ID),
        (second["code"], OTHER_SELLER_ID),
    ]


@pytest.mark.parametrize(
    "field, value",
    [
        ("seller_id", OTHER_SELLER_ID),
        ("code", "P-CHOSEN"),
        ("reserved_stock", 0),
        ("version", 1),
        ("is_active", False),
        ("id", 99),
    ],
)
def test_server_owned_fields_cannot_be_sent(api, engine, field, value):
    response = api.post(URL, json={**VALID, field: value}, headers=headers(engine))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ERR_VALIDATION"
    assert error["fields"] == {"_form": [f"{field} is set by the server and cannot be sent."]}
    assert stored(engine) == []


def test_guests_buyers_and_invalid_tokens_cannot_create(api, engine):
    expired = headers(engine, expires_in=-1)
    cases = [
        ({}, 401, "ERR_AUTH_REQUIRED"),
        ({"Authorization": "Bearer not-a-token"}, 401, "ERR_INVALID_TOKEN"),
        (expired, 401, "ERR_INVALID_TOKEN"),
        (headers(engine, BUYER_ID), 403, "ERR_SELLER_REQUIRED"),
    ]
    for request_headers, status, code in cases:
        for body in (VALID, {**VALID, "price": 0}):
            response = api.post(URL, json=body, headers=request_headers)
            assert response.status_code == status, response.text
            assert response.json()["error"]["code"] == code
    assert stored(engine) == []


def test_a_deleted_seller_token_is_rejected(api, engine):
    token_headers = headers(engine, OTHER_SELLER_ID)
    with Session(engine) as session:
        session.delete(session.get(User, OTHER_SELLER_ID))
        session.commit()

    response = api.post(URL, json=VALID, headers=token_headers)

    assert response.status_code == 401
    assert stored(engine) == []


# Task 1: field-level validation


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("name", MISSING, "Product name is required."),
        ("name", None, "Product name is required."),
        ("name", "   ", "Product name is required."),
        ("name", 123, "Product name must be text."),
        ("name", "x" * (NAME_MAX_LENGTH + 1), "Product name must be at most 200 characters."),
        ("description", MISSING, "Description is required."),
        ("description", None, "Description is required."),
        ("description", "\n\t ", "Description is required."),
        ("description", ["text"], "Description must be text."),
        (
            "description",
            "x" * (DESCRIPTION_MAX_LENGTH + 1),
            "Description must be at most 3000 characters.",
        ),
        ("price", MISSING, "Price is required."),
        ("price", None, "Price is required."),
        ("price", 0, "Price must be greater than 0 ₫."),
        ("price", -1, "Price must be greater than 0 ₫."),
        ("price", 1.5, "Price must be a whole number of VND."),
        ("price", 1.0, "Price must be a whole number of VND."),
        ("price", True, "Price must be a whole number of VND."),
        ("price", "180000", "Price must be a whole number of VND."),
        ("price", PRICE_MAX + 1, "Price must be at most 1.000.000.000 ₫."),
        ("price", 2**70, "Price must be at most 1.000.000.000 ₫."),
        ("stock_quantity", MISSING, "Stock quantity is required."),
        ("stock_quantity", None, "Stock quantity is required."),
        ("stock_quantity", -1, "Stock quantity must be 0 or more."),
        ("stock_quantity", 2.5, "Stock quantity must be a whole number."),
        ("stock_quantity", False, "Stock quantity must be a whole number."),
        ("stock_quantity", "5", "Stock quantity must be a whole number."),
        ("stock_quantity", STOCK_MAX + 1, "Stock quantity must be at most 1.000.000."),
        ("image_url", MISSING, "Image URL is required."),
        ("image_url", None, "Image URL is required."),
        ("image_url", "  ", "Image URL is required."),
        ("image_url", "mouse.jpg", "Image URL must be an absolute http:// or https:// address."),
        (
            "image_url",
            "/images/p-100.jpg",
            "Image URL must be an absolute http:// or https:// address.",
        ),
        (
            "image_url",
            "ftp://example.com/mouse.jpg",
            "Image URL must be an absolute http:// or https:// address.",
        ),
        (
            "image_url",
            "javascript:alert(1)",
            "Image URL must be an absolute http:// or https:// address.",
        ),
        ("image_url", "https://", "Image URL must be an absolute http:// or https:// address."),
        (
            "image_url",
            "https://exa mple.com/a.jpg",
            "Image URL must be an absolute http:// or https:// address.",
        ),
        (
            "image_url",
            "https://example.com:99999/a.jpg",
            "Image URL must be an absolute http:// or https:// address.",
        ),
        (
            "image_url",
            "https://example.com/" + "a" * IMAGE_URL_MAX_LENGTH,
            "Image URL must be at most 2048 characters.",
        ),
    ],
)
def test_invalid_field_is_reported_beside_that_field_and_nothing_is_written(
    api, engine, field, value, message
):
    response = api.post(URL, json=with_patch({field: value}), headers=headers(engine))

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "ERR_VALIDATION",
            "message": VALIDATION_MESSAGE,
            "fields": {field: [message]},
        }
    }
    assert stored(engine) == []


@pytest.mark.parametrize(
    "patch",
    [
        {"stock_quantity": 0},
        {"price": 1},
        {"price": PRICE_MAX, "stock_quantity": STOCK_MAX},
        {"name": "n" * NAME_MAX_LENGTH, "description": "d" * DESCRIPTION_MAX_LENGTH},
        {"image_url": "http://example.com/" + "a" * (IMAGE_URL_MAX_LENGTH - 19)},
        {"image_url": "HTTPS://Example.COM:8443/ảnh sản phẩm.jpg".replace(" ", "%20")},
    ],
)
def test_boundary_values_are_accepted(api, engine, patch):
    response = api.post(URL, json={**VALID, **patch}, headers=headers(engine))

    assert response.status_code == 201, response.text
    [product] = stored(engine)
    for field, value in patch.items():
        assert getattr(product, field) == value


def test_every_invalid_field_is_reported_in_one_response(api, engine):
    body = {"name": "", "description": "ok", "price": 0, "stock_quantity": -1, "image_url": "x"}
    response = api.post(URL, json=body, headers=headers(engine))

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert set(fields) == {"name", "price", "stock_quantity", "image_url"}
    assert stored(engine) == []


@pytest.mark.parametrize(
    "content, message",
    [
        (b"{not json", "The request body is not valid JSON."),
        (b"[]", "Send the product as a JSON object"),
        (b'"Training Mouse"', "Send the product as a JSON object"),
        (b"", "Send the product as a JSON object"),
    ],
)
def test_a_body_that_is_not_a_product_object_gets_a_form_error(api, engine, content, message):
    request_headers = {**headers(engine), "Content-Type": "application/json"}
    response = api.post(URL, content=content, headers=request_headers)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ERR_VALIDATION"
    assert list(error["fields"]) == ["_form"]
    assert error["message"].startswith(message)
    assert stored(engine) == []


def test_unknown_fields_are_refused_without_naming_them(api, engine):
    response = api.post(URL, json={**VALID, "x-secret-key": 1}, headers=headers(engine))

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "_form": ["The request contains fields that are not accepted."]
    }
    assert "x-secret-key" not in response.text


def test_validation_errors_never_echo_submitted_values(api, engine):
    body = {
        "name": "SECRET-NAME-" + "x" * NAME_MAX_LENGTH,
        "description": None,
        "price": "SECRET-PRICE",
        "stock_quantity": "SECRET-STOCK",
        "image_url": "ftp://SECRET-HOST/x.jpg",
    }
    response = api.post(URL, json=body, headers=headers(engine))

    assert response.status_code == 422
    assert "SECRET" not in response.text
    assert "input" not in response.text


def test_other_routes_keep_their_validation_error_shape(api, engine):
    buyer = headers(engine, BUYER_ID)
    cart = api.post(
        "/api/v1/cart/items", json={"product_code": "P-1", "quantity": "2"}, headers=buyer
    )
    order = api.post(
        "/api/v1/orders",
        json={"recipient_name": "Buyer", "delivery_address": "Street", "phone_number": "x"},
        headers={**buyer, "Idempotency-Key": "key"},
    )
    catalog = api.get("/api/v1/products?page=0")
    login = api.post("/api/v1/auth/login", json={"email": "no-at-sign", "password": "x"})

    assert cart.json() == {
        "error": {"code": "ERR_VALIDATION", "message": "The request contains invalid fields."}
    }
    assert order.json() == {
        "error": {"code": "ERR_VALIDATION", "message": "Invalid checkout fields: phone_number."}
    }
    for response in (catalog, login):
        assert response.status_code == 422
        assert response.json()["error"] == {
            "code": "ERR_VALIDATION",
            "message": "The request contains invalid fields.",
        }
    assert api.get(URL, headers=headers(engine)).status_code == 405


def test_an_unreachable_image_url_is_stored_without_downloading_it(api, engine, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("product creation must not download the image")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    image_url = "https://images.invalid/missing-mouse.jpg"

    response = api.post(URL, json={**VALID, "image_url": image_url}, headers=headers(engine))

    assert response.status_code == 201, response.text
    assert [p.image_url for p in stored(engine)] == [image_url]


# Task 1 and 4: unique product codes


def test_generated_codes_fit_the_column_and_do_not_repeat():
    codes = {generate_product_code() for _ in range(2000)}

    assert len(codes) == 2000
    assert all(CODE_PATTERN.match(code) and len(code) == 20 for code in codes)


def test_a_code_collision_is_retried_with_a_new_code(api, engine, monkeypatch):
    add_product(engine, "P-TAKEN")
    codes = iter(["P-TAKEN", "P-FRESH"])
    monkeypatch.setattr(service, "generate_product_code", lambda: next(codes))

    response = api.post(URL, json=VALID, headers=headers(engine, OTHER_SELLER_ID))

    assert response.status_code == 201, response.text
    assert response.json()["data"]["code"] == "P-FRESH"
    assert [(p.code, p.seller_id) for p in stored(engine)] == [
        ("P-TAKEN", SELLER_ID),
        ("P-FRESH", OTHER_SELLER_ID),
    ]


def test_repeated_code_collisions_end_in_a_conflict_without_a_row(api, engine, monkeypatch):
    add_product(engine, "P-TAKEN")
    calls = []

    def taken():
        calls.append(1)
        return "P-TAKEN"

    monkeypatch.setattr(service, "generate_product_code", taken)

    response = api.post(URL, json=VALID, headers=headers(engine))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ERR_CONCURRENCY_CONFLICT"
    assert len(calls) == MAX_CODE_ATTEMPTS
    assert [p.code for p in stored(engine)] == ["P-TAKEN"]


def test_concurrent_creations_on_separate_connections_get_distinct_codes(engine):
    workers = 6
    barrier = Barrier(workers)

    def create(index):
        barrier.wait(timeout=10)
        with Session(engine) as session:
            body = ProductCreate(**{**VALID, "name": f"Concurrent {index}"})
            return create_product(session, SELLER_ID, body)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(create, range(workers)))

    codes = {product.code for product in results}
    assert len(codes) == workers
    assert {p.code for p in stored(engine)} == codes


# Task 1 and 4: rollback


def test_failure_before_commit_rolls_back_and_the_session_stays_usable(engine, monkeypatch):
    add_product(engine, "P-OLD")
    original_commit = Session.commit

    def failing_commit(session):
        raise OperationalError("COMMIT", {}, Exception("disk I/O error"))

    with Session(engine) as session:
        monkeypatch.setattr(Session, "commit", failing_commit)
        with pytest.raises(OperationalError):
            create_product(session, SELLER_ID, ProductCreate(**VALID))
        monkeypatch.setattr(Session, "commit", original_commit)
        assert [p.code for p in session.exec(select(Product)).all()] == ["P-OLD"]
        created = create_product(session, SELLER_ID, ProductCreate(**VALID))

    assert [p.code for p in stored(engine)] == ["P-OLD", created.code]


def test_a_database_failure_answers_500_without_details(api, engine, monkeypatch):
    def failing_commit(session):
        raise OperationalError("INSERT INTO products", {}, Exception("database is locked"))

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = api.post(URL, json=VALID, headers=headers(engine))
    monkeypatch.undo()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
    assert "INSERT" not in response.text and "locked" not in response.text
    assert stored(engine) == []


def test_an_unrelated_constraint_failure_is_not_treated_as_a_code_collision(
    engine, monkeypatch
):
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER reject_product BEFORE INSERT ON products "
                "BEGIN SELECT RAISE(ABORT, 'simulated constraint failure'); END"
            )
        )
    calls = []
    monkeypatch.setattr(
        service, "generate_product_code", lambda: calls.append(1) or f"P-{len(calls)}"
    )

    with Session(engine) as session, pytest.raises(IntegrityError):
        create_product(session, SELLER_ID, ProductCreate(**VALID))

    assert len(calls) == 1
    assert stored(engine) == []


def test_a_seller_missing_from_the_database_is_not_retried(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(
        service, "generate_product_code", lambda: calls.append(1) or f"P-{len(calls)}"
    )

    with Session(engine) as session, pytest.raises(IntegrityError):
        create_product(session, 999, ProductCreate(**VALID))

    assert len(calls) == 1
    assert stored(engine) == []


def test_service_error_carries_the_conflict_status():
    error = SellerProductError("ERR_CONCURRENCY_CONFLICT", "message")

    assert (error.status, error.code, error.message) == (409, "ERR_CONCURRENCY_CONFLICT", "message")
