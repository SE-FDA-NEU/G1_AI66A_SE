from datetime import UTC, datetime

import pytest
from sqlmodel import Session, delete, select

from src.auth import hash_password
from src.database import engine
from src.models.cart_item import CartItem
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.review import Review
from src.models.seller_order import SellerOrder
from src.models.user import User

PRODUCT_CODE = "US15-REVIEW"
SELLER_EMAIL = "us15-seller@example.com"
BUYER_EMAIL = "us15-buyer@example.com"
OTHER_BUYER_EMAIL = "us15-other-buyer@example.com"


def _remove_us15_data(session: Session) -> None:
    users = select(User.id).where(
        User.email.in_([SELLER_EMAIL, BUYER_EMAIL, OTHER_BUYER_EMAIL])
    )
    orders = select(Order.id).where(Order.buyer_id.in_(users))
    seller_orders = select(SellerOrder.id).where(SellerOrder.order_id.in_(orders))
    session.exec(delete(Notification).where(Notification.order_id.in_(orders)))
    product_ids = select(Product.id).where(Product.code == PRODUCT_CODE)
    session.exec(delete(Review).where(Review.product_id.in_(product_ids)))
    session.exec(delete(CartItem).where(CartItem.buyer_id.in_(users)))
    session.exec(delete(OrderItem).where(OrderItem.seller_order_id.in_(seller_orders)))
    session.exec(delete(OrderHistory).where(OrderHistory.seller_order_id.in_(seller_orders)))
    session.exec(delete(SellerOrder).where(SellerOrder.order_id.in_(orders)))
    session.exec(delete(Order).where(Order.buyer_id.in_(users)))
    session.exec(delete(Product).where(Product.code == PRODUCT_CODE))
    session.exec(delete(User).where(User.email.in_([SELLER_EMAIL, BUYER_EMAIL, OTHER_BUYER_EMAIL])))


@pytest.fixture
def us15_data():
    with Session(engine) as session:
        _remove_us15_data(session)
        seller = User(
            name="US15 Seller",
            email=SELLER_EMAIL,
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer = User(
            name="US15 Buyer",
            email=BUYER_EMAIL,
            role="buyer",
            password_hash=hash_password("password"),
        )
        other_buyer = User(
            name="US15 Other Buyer",
            email=OTHER_BUYER_EMAIL,
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add_all([seller, buyer, other_buyer])
        session.flush()
        product = Product(
            code=PRODUCT_CODE,
            seller_id=seller.id,
            name="US15 Review Product",
            price=100,
            stock_quantity=10,
        )
        session.add(product)
        session.flush()

        def order_with_item(owner: User, status: str) -> tuple[Order, SellerOrder, OrderItem]:
            order = Order(
                buyer_id=owner.id,
                total_amount=100,
                status=status,
                recipient_name=owner.name,
                delivery_address="US15 test address",
                phone_number="0123456789",
            )
            session.add(order)
            session.flush()
            seller_order = SellerOrder(
                order_id=order.id,
                seller_id=seller.id,
                status=status,
                completed_at=datetime.now(UTC) if status == "COMPLETED" else None,
            )
            session.add(seller_order)
            session.flush()
            item = OrderItem(
                seller_order_id=seller_order.id,
                product_id=product.id,
                quantity=1,
                unit_price=100,
            )
            session.add(item)
            session.flush()
            return order, seller_order, item

        completed_order, completed_seller_order, completed_item = order_with_item(
            buyer, "COMPLETED"
        )
        second_completed_item = OrderItem(
            seller_order_id=completed_seller_order.id,
            product_id=product.id,
            quantity=1,
            unit_price=100,
        )
        session.add(second_completed_item)
        session.flush()
        pending_order, pending_seller_order, pending_item = order_with_item(buyer, "PENDING")
        foreign_order, _, foreign_item = order_with_item(other_buyer, "COMPLETED")
        session.commit()
        result = {
            "seller_id": seller.id,
            "buyer_id": buyer.id,
            "seller_order_id": pending_seller_order.id,
            "completed_order_id": completed_order.id,
            "completed_item_id": completed_item.id,
            "second_completed_item_id": second_completed_item.id,
            "pending_item_id": pending_item.id,
            "foreign_order_id": foreign_order.id,
            "foreign_item_id": foreign_item.id,
            "product_id": product.id,
        }
    yield result
    with Session(engine) as session:
        _remove_us15_data(session)
        session.commit()


def _token(client, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_only_owner_can_review_completed_order_item_and_aggregate_updates(
    client, us15_data
) -> None:
    buyer_token = _token(client, BUYER_EMAIL)
    payload = {
        "order_item_id": us15_data["completed_item_id"],
        "rating": 5,
        "comment": "Arrived as described.",
        "media_url": "https://example.com/review-photo.jpg",
    }
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(buyer_token),
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["rating"] == 5
    assert body["comment"] == payload["comment"]
    assert body["media_url"] == payload["media_url"]

    duplicate = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(buyer_token),
        json=payload,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ERR_REVIEW_ALREADY_EXISTS"

    second_review = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(buyer_token),
        json={
            "order_item_id": us15_data["second_completed_item_id"],
            "rating": 3,
        },
    )
    assert second_review.status_code == 201

    detail = client.get(f"/api/v1/products/{PRODUCT_CODE}")
    reviews = client.get(f"/api/v1/products/{PRODUCT_CODE}/reviews")
    assert detail.json()["rating"] == 4
    assert detail.json()["review_count"] == 2
    assert any(item["comment"] == payload["comment"] for item in reviews.json()["data"])
    assert reviews.json()["review_count"] == 2
    with Session(engine) as session:
        metadata = session.get(ProductMetadata, us15_data["product_id"])
        assert metadata is not None
        assert metadata.rating == 4
        assert metadata.review_count == 2


@pytest.mark.parametrize(
    ("order_item_key", "expected_status", "expected_code"),
    [
        ("pending_item_id", 409, "ERR_REVIEW_NOT_COMPLETED"),
        ("foreign_item_id", 404, "ERR_REVIEW_NOT_ELIGIBLE"),
    ],
)
def test_ineligible_order_items_are_not_saved(
    client, us15_data, order_item_key: str, expected_status: int, expected_code: str
) -> None:
    token = _token(client, BUYER_EMAIL)
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(token),
        json={"order_item_id": us15_data[order_item_key], "rating": 4},
    )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    with Session(engine) as session:
        assert session.exec(select(Review)).all() == []


@pytest.mark.parametrize("invalid_rating", [0, 6, True, "5", 2.5])
def test_review_rating_validation_and_reviewable_items(
    client, us15_data, invalid_rating
) -> None:
    token = _token(client, BUYER_EMAIL)
    invalid = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(token),
        json={"order_item_id": us15_data["completed_item_id"], "rating": invalid_rating},
    )
    assert invalid.status_code == 422

    eligible = client.get(
        f"/api/v1/products/{PRODUCT_CODE}/reviewable-items",
        headers=_auth(token),
    )
    assert eligible.status_code == 200
    assert {item["order_item_id"] for item in eligible.json()["data"]} == {
        us15_data["completed_item_id"],
        us15_data["second_completed_item_id"],
    }


def test_only_product_owner_can_reply_and_reply_is_shown(client, us15_data) -> None:
    buyer_token = _token(client, BUYER_EMAIL)
    review_response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(buyer_token),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 4},
    )
    review_id = review_response.json()["data"]["id"]
    seller_notifications = client.get(
        "/api/v1/notifications",
        headers=_auth(_token(client, SELLER_EMAIL)),
    )
    assert seller_notifications.json()["unread_count"] == 1
    assert seller_notifications.json()["data"][0]["target_path"] == (
        f"/products/{PRODUCT_CODE}"
    )

    wrong_seller = _token(client, "test.seller@marketplace.local")
    denied = client.patch(
        f"/api/v1/seller/reviews/{review_id}/reply",
        headers=_auth(wrong_seller),
        json={"reply": "Thanks for the feedback."},
    )
    assert denied.status_code == 403

    owner_token = _token(client, SELLER_EMAIL)
    replied = client.patch(
        f"/api/v1/seller/reviews/{review_id}/reply",
        headers=_auth(owner_token),
        json={"reply": "Thanks for the feedback."},
    )
    assert replied.status_code == 200
    assert replied.json()["data"]["seller_reply"] == "Thanks for the feedback."
    assert replied.json()["data"]["seller_replied_at"] is not None
    public_reviews = client.get(f"/api/v1/products/{PRODUCT_CODE}/reviews")
    assert public_reviews.json()["data"][0]["seller_reply"] == "Thanks for the feedback."
    buyer_notifications = client.get(
        "/api/v1/notifications",
        headers=_auth(buyer_token),
    )
    assert buyer_notifications.json()["unread_count"] == 1
    assert buyer_notifications.json()["data"][0]["message"] == (
        "The seller replied to your review of US15 Review Product."
    )
    assert buyer_notifications.json()["data"][0]["target_path"] == (
        f"/products/{PRODUCT_CODE}"
    )


def test_status_transition_notifies_only_buyer_and_retry_does_not_duplicate(
    client, us15_data
) -> None:
    seller_token = _token(client, SELLER_EMAIL)
    buyer_token = _token(client, BUYER_EMAIL)
    url = f"/api/v1/seller/orders/{us15_data['seller_order_id']}/status"
    for status in ("PROCESSING", "SHIPPED", "COMPLETED"):
        response = client.patch(url, headers=_auth(seller_token), json={"status": status})
        assert response.status_code == 200

    retry = client.patch(url, headers=_auth(seller_token), json={"status": "COMPLETED"})
    assert retry.status_code == 400
    buyer_notifications = client.get("/api/v1/notifications", headers=_auth(buyer_token))
    seller_notifications = client.get("/api/v1/notifications", headers=_auth(seller_token))
    assert buyer_notifications.status_code == 200
    assert buyer_notifications.json()["unread_count"] == 3
    assert len(buyer_notifications.json()["data"]) == 3
    assert seller_notifications.json()["data"] == []

    notification_id = buyer_notifications.json()["data"][0]["id"]
    marked = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=_auth(buyer_token),
    )
    assert marked.status_code == 200
    assert marked.json()["data"]["read_at"] is not None
    assert client.get("/api/v1/notifications", headers=_auth(buyer_token)).json()[
        "unread_count"
    ] == 2


def test_notification_cannot_be_read_by_another_user(client, us15_data) -> None:
    seller_token = _token(client, SELLER_EMAIL)
    buyer_token = _token(client, BUYER_EMAIL)
    response = client.patch(
        f"/api/v1/seller/orders/{us15_data['seller_order_id']}/status",
        headers=_auth(seller_token),
        json={"status": "PROCESSING"},
    )
    assert response.status_code == 200
    notification = client.get("/api/v1/notifications", headers=_auth(buyer_token)).json()["data"][0]
    denied = client.patch(
        f"/api/v1/notifications/{notification['id']}/read",
        headers=_auth(seller_token),
    )
    assert denied.status_code == 404


def test_checkout_notifies_seller_once_when_idempotent_request_is_replayed(
    client, us15_data
) -> None:
    buyer_token = _token(client, BUYER_EMAIL)
    seller_token = _token(client, SELLER_EMAIL)
    with Session(engine) as session:
        session.add(
            CartItem(
                buyer_id=us15_data["buyer_id"],
                product_id=us15_data["product_id"],
                quantity=1,
                is_selected=True,
                price_at_add=100,
            )
        )
        session.commit()

    headers = {**_auth(buyer_token), "Idempotency-Key": "us15-checkout-replay"}
    body = {
        "recipient_name": "US15 Buyer",
        "delivery_address": "US15 delivery address",
        "phone_number": "0123456789",
    }
    first = client.post("/api/v1/orders", headers=headers, json=body)
    replay = client.post("/api/v1/orders", headers=headers, json=body)
    assert first.status_code == 201
    assert replay.status_code == 200

    seller_notifications = client.get("/api/v1/notifications", headers=_auth(seller_token))
    assert seller_notifications.json()["unread_count"] == 1
    notification = seller_notifications.json()["data"][0]
    assert notification["target_path"] == "/seller/orders"
    assert notification["message"] == (
        f"New order #{first.json()['data']['id']} is waiting for processing."
    )


def test_review_and_notification_pages_are_served(client) -> None:
    product_page = client.get(f"/products/{PRODUCT_CODE}")
    notifications_page = client.get("/notifications")
    assert product_page.status_code == 200
    assert 'id="review-form"' in product_page.text
    assert 'href="/notifications"' in product_page.text
    assert notifications_page.status_code == 200
    assert 'id="notifications-list"' in notifications_page.text
