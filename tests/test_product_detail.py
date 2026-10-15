"""Tests for product detail and add-to-cart behavior."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

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
    assert response.json()["data"]["product_code"] == "DETAIL-1"
    assert response.json()["data"]["quantity"] == 2
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
