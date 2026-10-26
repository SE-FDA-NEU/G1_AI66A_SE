from datetime import UTC, datetime

import pytest
from sqlmodel import Session, delete
from starlette.testclient import TestClient

from src.auth import hash_password
from src.database import engine
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User


@pytest.fixture
def seller_order_data():
    with Session(engine) as session:
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(Product).where(Product.code.like("US08-%")))

        seller_a = User(
            name="US08 Seller A",
            email="us08-seller-a@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        seller_b = User(
            name="US08 Seller B",
            email="us08-seller-b@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer = User(
            name="US08 Buyer",
            email="us08-buyer@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add_all([seller_a, seller_b, buyer])
        session.flush()

        product_a = Product(
            code="US08-A",
            seller_id=seller_a.id,
            name="Seller A product",
            price=100,
            stock_quantity=5,
        )
        product_b = Product(
            code="US08-B",
            seller_id=seller_b.id,
            name="Seller B product",
            price=200,
            stock_quantity=5,
        )
        session.add_all([product_a, product_b])
        session.flush()

        parent = Order(
            buyer_id=buyer.id,
            total_amount=300,
            status="PENDING",
            recipient_name="US08 Buyer",
            delivery_address="Test address",
            phone_number="0123456789",
            created_at=datetime.now(UTC),
        )
        session.add(parent)
        session.flush()
        seller_order_a = SellerOrder(order_id=parent.id, seller_id=seller_a.id, status="PENDING")
        seller_order_b = SellerOrder(order_id=parent.id, seller_id=seller_b.id, status="PENDING")
        session.add_all([seller_order_a, seller_order_b])
        session.flush()
        session.add_all(
            [
                OrderItem(
                    seller_order_id=seller_order_a.id,
                    product_id=product_a.id,
                    quantity=2,
                    unit_price=100,
                ),
                OrderItem(
                    seller_order_id=seller_order_b.id,
                    product_id=product_b.id,
                    quantity=1,
                    unit_price=200,
                ),
            ]
        )
        session.commit()
        result = {
            "seller_a": seller_a.email,
            "seller_b": seller_b.email,
            "seller_order_a": seller_order_a.id,
            "seller_order_b": seller_order_b.id,
            "product_a": product_a.id,
            "buyer": buyer.email,
            "order_id": parent.id,
        }

    yield result

    with Session(engine) as session:
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(Product).where(Product.code.like("US08-%")))
        session.exec(delete(User).where(User.email.like("us08-%@example.com")))
        session.commit()


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_seller_order_listing_is_scoped_to_authenticated_seller(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_a"])

    response = client.get(
        "/api/v1/seller/orders",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["id"] == seller_order_data["seller_order_a"]
    assert [item["product_code"] for item in body["data"][0]["items"]] == ["US08-A"]


def test_valid_transition_creates_history_and_updates_parent(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_a"])

    response = client.patch(
        f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "PROCESSING"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PROCESSING"
    with Session(engine) as session:
        history = session.exec(select_history()).all()
        assert [(row.from_status, row.to_status) for row in history] == [("PENDING", "PROCESSING")]
        parent = session.get(Order, 1)
        assert parent is not None
        assert parent.status == "PROCESSING"


def test_invalid_transition_returns_business_error(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_a"])
    response = client.patch(
        f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "SHIPPED"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_INVALID_TRANSITION"


def test_other_seller_cannot_update_owned_order(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_b"])
    response = client.patch(
        f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "PROCESSING"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ERR_RESOURCE_OWNER"


def test_cancellation_restores_stock_once(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_a"])
    url = f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status"
    response = client.patch(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "CANCELLED"},
    )
    assert response.status_code == 200
    second_response = client.patch(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "CANCELLED"},
    )
    assert second_response.status_code == 400
    with Session(engine) as session:
        product = session.get(Product, seller_order_data["product_a"])
        assert product is not None
        assert product.stock_quantity == 7
        assert product.version == 2
        history = session.exec(select_history()).all()
        assert len(history) == 1
        assert (history[0].from_status, history[0].to_status) == ("PENDING", "CANCELLED")


def test_completion_sets_completed_at(
    client: TestClient,
    seller_order_data,
) -> None:
    token = _token(client, seller_order_data["seller_a"])
    url = f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status"
    for status in ("PROCESSING", "SHIPPED", "COMPLETED"):
        response = client.patch(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"status": status},
        )
        assert response.status_code == 200

    with Session(engine) as session:
        seller_order = session.get(SellerOrder, seller_order_data["seller_order_a"])
        assert seller_order is not None
        assert seller_order.completed_at is not None


def test_status_notification_identifies_sub_order_in_multi_seller_checkout(
    client: TestClient,
    seller_order_data,
) -> None:
    seller_token = _token(client, seller_order_data["seller_a"])
    buyer_token = _token(client, seller_order_data["buyer"])
    url = f"/api/v1/seller/orders/{seller_order_data['seller_order_a']}/status"

    for status in ("PROCESSING", "SHIPPED", "COMPLETED"):
        response = client.patch(
            url,
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"status": status},
        )
        assert response.status_code == 200

    notifications = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {buyer_token}"},
    ).json()["data"]
    expected_message = (
        f"Seller order #{seller_order_data['seller_order_a']} "
        f"in your order #{seller_order_data['order_id']} is now completed."
    )
    completed_notification = next(
        notification
        for notification in notifications
        if notification["message"] == expected_message
    )
    assert completed_notification["message"] == expected_message

    with Session(engine) as session:
        parent = session.get(Order, seller_order_data["order_id"])
        other_seller_order = session.get(SellerOrder, seller_order_data["seller_order_b"])
        assert parent is not None and parent.status == "PROCESSING"
        assert other_seller_order is not None and other_seller_order.status == "PENDING"


def test_cancellations_increment_shared_product_stock_atomically(
    client: TestClient,
    seller_order_data,
) -> None:
    with Session(engine) as session:
        session.add(
            OrderItem(
                seller_order_id=seller_order_data["seller_order_b"],
                product_id=seller_order_data["product_a"],
                quantity=2,
                unit_price=100,
            )
        )
        session.commit()

    seller_a_token = _token(client, seller_order_data["seller_a"])
    seller_b_token = _token(client, seller_order_data["seller_b"])
    for order_id, token in (
        (seller_order_data["seller_order_a"], seller_a_token),
        (seller_order_data["seller_order_b"], seller_b_token),
    ):
        response = client.patch(
            f"/api/v1/seller/orders/{order_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "CANCELLED"},
        )
        assert response.status_code == 200

    with Session(engine) as session:
        product = session.get(Product, seller_order_data["product_a"])
        assert product is not None
        assert product.stock_quantity == 9
        assert product.version == 3


def test_end_date_includes_the_selected_day(
    client: TestClient,
    seller_order_data,
) -> None:
    with Session(engine) as session:
        parent = session.get(Order, 1)
        assert parent is not None
        parent.created_at = datetime(2026, 10, 17, 23, 59, 59, tzinfo=UTC)
        session.add(parent)
        session.commit()

    token = _token(client, seller_order_data["seller_a"])
    response = client.get(
        "/api/v1/seller/orders?to=2026-10-17",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1


def select_history():
    from sqlmodel import select

    return select(OrderHistory).order_by(OrderHistory.id)
