"""Tests for return and refund workflow (P1 Story)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, delete, select
from starlette.testclient import TestClient

from src.auth import create_access_token, hash_password
from src.database import engine
from src.main import create_app
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User


@pytest.fixture
def test_setup():
    with Session(engine) as session:
        session.exec(delete(ReturnRequest))
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(ProductMetadata))
        session.exec(delete(Product).where(Product.code.like("RET-%")))
        session.exec(delete(User).where(User.email.like("ret-%@example.com")))

        seller_a = User(
            name="Return Seller A",
            email="ret-seller-a@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        seller_b = User(
            name="Return Seller B",
            email="ret-seller-b@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer_a = User(
            name="Return Buyer A",
            email="ret-buyer-a@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        buyer_b = User(
            name="Return Buyer B",
            email="ret-buyer-b@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        admin = User(
            name="Return Admin",
            email="ret-admin@example.com",
            role="admin",
            password_hash=hash_password("password"),
        )
        session.add_all([seller_a, seller_b, buyer_a, buyer_b, admin])
        session.flush()

        prod = Product(
            code="RET-P1",
            seller_id=seller_a.id,
            name="Returnable Widget",
            price=150_000,
            stock_quantity=10,
            is_active=True,
        )
        session.add(prod)
        session.flush()

        meta = ProductMetadata(
            product_id=prod.id,
            sales_count=5,
            rating=4.5,
        )
        session.add(meta)

        order = Order(
            buyer_id=buyer_a.id,
            total_amount=300_000,
            status="DELIVERED",
            payment_status="PAID",
            escrow_status="HELD",
            recipient_name="Return Buyer A",
            delivery_address="123 Apple Way",
            phone_number="0987654321",
            created_at=datetime.now(UTC),
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,
            seller_id=seller_a.id,
            status="DELIVERED",
            payment_status="PAID",
            escrow_status="HELD",
        )
        session.add(so)
        session.flush()

        item = OrderItem(
            seller_order_id=so.id,
            product_id=prod.id,
            quantity=2,
            unit_price=150_000,
        )
        session.add(item)
        session.commit()

        yield {
            "seller_a": seller_a,
            "seller_b": seller_b,
            "buyer_a": buyer_a,
            "buyer_b": buyer_b,
            "admin": admin,
            "order_id": order.id,
            "seller_order_id": so.id,
            "product_id": prod.id,
        }

    with Session(engine) as session:
        session.exec(delete(ReturnRequest))
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(ProductMetadata))
        session.exec(delete(Product).where(Product.code.like("RET-%")))
        session.exec(delete(User).where(User.email.like("ret-%@example.com")))
        session.commit()


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _auth(user: User) -> dict[str, str]:
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_submit_return_request_success_delivered_order(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    payload = {
        "reason": "Defective hinge and crack on edge",
        "evidence": "Attached photo url: https://example.com/photo1.jpg showing crack",
    }
    res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["order_id"] == test_setup["order_id"]
    assert data["seller_order_id"] == test_setup["seller_order_id"]
    assert data["status"] == "PENDING"
    assert data["escrow_status"] == "PAUSED"
    assert data["seller_order_status"] == "RETURN_REQUESTED"

    with Session(engine) as session:
        so = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so.status == "RETURN_REQUESTED"
        assert so.escrow_status == "PAUSED"

        parent = session.get(Order, test_setup["order_id"])
        assert parent.status == "RETURN_REQUESTED"
        assert parent.escrow_status == "PAUSED"

        history = session.exec(
            select(OrderHistory).where(
                OrderHistory.seller_order_id == test_setup["seller_order_id"]
            )
        ).all()
        assert any(
            h.from_status == "DELIVERED" and h.to_status == "RETURN_REQUESTED"
            for h in history
        )

        notif = session.exec(
            select(Notification).where(
                Notification.recipient_user_id == test_setup["seller_a"].id
            )
        ).first()
        assert notif is not None
        assert "Buyer requested return" in notif.message


def test_submit_return_request_fails_if_not_delivered(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    with Session(engine) as session:
        so = session.get(SellerOrder, test_setup["seller_order_id"])
        so.status = "SHIPPED"
        session.add(so)
        session.commit()

    payload = {"reason": "Not arrived yet", "evidence": "Tracking shows in transit"}
    res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json=payload,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "ERR_INVALID_TRANSITION"


def test_submit_return_request_conflict_if_already_pending(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    payload = {"reason": "Broken screen", "evidence": "Photo attached"}
    res1 = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json=payload,
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json=payload,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "ERR_CONFLICT"


def test_submit_return_request_authorization_checks(client, test_setup):
    other_buyer_headers = _auth(test_setup["buyer_b"])
    payload = {"reason": "Not my order", "evidence": "None"}
    res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=other_buyer_headers,
        json=payload,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ERR_FORBIDDEN"

    seller_headers = _auth(test_setup["seller_a"])
    res_seller = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=seller_headers,
        json=payload,
    )
    assert res_seller.status_code == 403
    assert res_seller.json()["error"]["code"] == "ERR_BUYER_REQUIRED"

    res_anon = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        json=payload,
    )
    assert res_anon.status_code == 401


def test_approve_return_request_with_restock(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Wrong item shipped", "evidence": "Photo of box"},
    )
    assert sub_res.status_code == 201
    return_req_id = sub_res.json()["data"]["id"]

    seller_headers = _auth(test_setup["seller_a"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_headers,
        json={
            "action": "APPROVE",
            "decision_notes": "Return accepted in original unopened packaging.",
            "is_restockable": True,
        },
    )
    assert dec_res.status_code == 200
    data = dec_res.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["seller_order_status"] == "RETURNED_REFUNDED"
    assert data["payment_status"] == "REFUNDED"
    assert data["is_restockable"] is True

    with Session(engine) as session:
        prod = session.get(Product, test_setup["product_id"])
        assert prod.stock_quantity == 12
        assert prod.version == 2

        meta = session.get(ProductMetadata, test_setup["product_id"])
        assert meta.sales_count == 3

        so = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so.status == "RETURNED_REFUNDED"
        assert so.payment_status == "REFUNDED"
        assert so.escrow_status == "REFUNDED"

        buyer_notif = session.exec(
            select(Notification).where(
                Notification.recipient_user_id == test_setup["buyer_a"].id,
                Notification.event_key.like("%:approved"),
            )
        ).first()
        assert buyer_notif is not None
        assert "refunded" in buyer_notif.message.lower()


def test_approve_return_request_without_restock(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Smashed on transit", "evidence": "Broken glass fragments"},
    )
    return_req_id = sub_res.json()["data"]["id"]

    seller_headers = _auth(test_setup["seller_a"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_headers,
        json={
            "action": "APPROVE",
            "decision_notes": "Damaged beyond salvage, disposed of.",
            "is_restockable": False,
        },
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["data"]["is_restockable"] is False

    with Session(engine) as session:
        prod = session.get(Product, test_setup["product_id"])
        assert prod.stock_quantity == 10
        assert prod.version == 1


def test_reject_return_request_returns_to_completed(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Changed my mind", "evidence": "No issue"},
    )
    return_req_id = sub_res.json()["data"]["id"]

    seller_headers = _auth(test_setup["seller_a"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_headers,
        json={
            "action": "REJECT",
            "decision_notes": "Return period expired and item already used.",
        },
    )
    assert dec_res.status_code == 200
    data = dec_res.json()["data"]
    assert data["status"] == "REJECTED"
    assert data["seller_order_status"] == "COMPLETED"
    assert data["escrow_status"] == "RELEASED"

    with Session(engine) as session:
        so = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so.status == "COMPLETED"
        assert so.escrow_status == "RELEASED"

        buyer_notif = session.exec(
            select(Notification).where(
                Notification.recipient_user_id == test_setup["buyer_a"].id,
                Notification.event_key.like("%:rejected"),
            )
        ).first()
        assert buyer_notif is not None
        assert "rejected" in buyer_notif.message.lower()


def test_admin_can_decide_return_request(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Seller unresponsive", "evidence": "3 days no reply"},
    )
    return_req_id = sub_res.json()["data"]["id"]

    admin_headers = _auth(test_setup["admin"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=admin_headers,
        json={
            "action": "APPROVE",
            "decision_notes": "Admin intervention: Approved pursuant to policy.",
            "is_restockable": False,
        },
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["data"]["status"] == "APPROVED"


def test_unauthorized_seller_cannot_view_or_decide(client, test_setup):
    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Defective item", "evidence": "Photo proof"},
    )
    return_req_id = sub_res.json()["data"]["id"]

    other_seller_headers = _auth(test_setup["seller_b"])
    get_res = client.get(
        f"/api/v1/return-requests/{return_req_id}",
        headers=other_seller_headers,
    )
    assert get_res.status_code == 403
    assert get_res.json()["error"]["code"] == "ERR_FORBIDDEN"

    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=other_seller_headers,
        json={"action": "APPROVE"},
    )
    assert dec_res.status_code == 403
    assert dec_res.json()["error"]["code"] == "ERR_FORBIDDEN"


def test_order_web_routes_and_xss_protection(client, test_setup):
    res_orders = client.get(
        f"/orders/{test_setup['order_id']}",
        headers={"Accept": "text/html"},
    )
    assert res_orders.status_code == 200
    assert "<title>Order Details & Returns" in res_orders.text

    res_order = client.get(
        f"/order/{test_setup['order_id']}",
        headers={"Accept": "text/html"},
    )
    assert res_order.status_code == 200

    order_js_path = Path(__file__).resolve().parent.parent / "src" / "web" / "static" / "order.js"
    js_content = order_js_path.read_text(encoding="utf-8")
    assert "nameStrong.textContent = item.product_name" in js_content
    assert "codeCell.textContent = item.product_code" in js_content
    assert "table.innerHTML" not in js_content
    assert "itemsTableBody.innerHTML" not in js_content
