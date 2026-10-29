"""Tests for return and refund workflow (P1 Story)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

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
from src.schemas.returns import CreateReturnRequest, ReturnDecisionRequest
from src.services.returns import ReturnError, decide_return_request, submit_return_request


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
        assert so.payment_status == "PAID"

        product = session.get(Product, test_setup["product_id"])
        assert product.stock_quantity == 10

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


@pytest.mark.parametrize(
    ("seller_status", "expected_status", "expected_code"),
    [
        ("PENDING", 400, "ERR_INVALID_TRANSITION"),
        ("CONFIRMED", 400, "ERR_INVALID_TRANSITION"),
        ("PROCESSING", 400, "ERR_INVALID_TRANSITION"),
        ("SHIPPED", 400, "ERR_INVALID_TRANSITION"),
        ("COMPLETED", 400, "ERR_INVALID_TRANSITION"),
        ("CANCELLED", 400, "ERR_INVALID_TRANSITION"),
        ("RETURNED_REFUNDED", 400, "ERR_INVALID_TRANSITION"),
        ("RETURN_REQUESTED", 409, "ERR_CONFLICT"),
    ],
)
def test_submit_return_request_rejects_every_non_delivered_state(
    client, test_setup, seller_status, expected_status, expected_code
):
    """Only DELIVERED seller orders may enter return review."""
    buyer_headers = _auth(test_setup["buyer_a"])
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        seller_order.status = seller_status
        session.add(seller_order)
        session.commit()

    res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Invalid state test", "evidence": "Evidence attached"},
    )

    assert res.status_code == expected_status
    assert res.json()["error"]["code"] == expected_code
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        assert seller_order.status == seller_status
        assert seller_order.payment_status == "PAID"
        assert seller_order.escrow_status == "HELD"
        assert session.exec(select(ReturnRequest)).all() == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", ""),
        ("reason", "ab"),
        ("reason", "r" * 501),
        ("evidence", ""),
        ("evidence", "ab"),
        ("evidence", "e" * 2001),
    ],
)
def test_submit_return_request_validates_reason_and_evidence(client, test_setup, field, value):
    """Reason and evidence boundaries reject invalid payloads without side effects."""
    buyer_headers = _auth(test_setup["buyer_a"])
    payload = {"reason": "Valid return reason", "evidence": "Valid evidence"}
    payload[field] = value

    res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json=payload,
    )

    assert res.status_code == 422
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        product = session.get(Product, test_setup["product_id"])
        assert seller_order.status == "DELIVERED"
        assert seller_order.payment_status == "PAID"
        assert seller_order.escrow_status == "HELD"
        assert product.stock_quantity == 10
        assert session.exec(select(ReturnRequest)).all() == []


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

    with Session(engine) as session:
        request_id = session.exec(select(ReturnRequest.id)).one()
        notifications = session.exec(
            select(Notification).where(
                Notification.recipient_user_id == test_setup["seller_a"].id
            )
        ).all()
    assert [n.event_key for n in notifications] == [f"return_request:{request_id}:created"]


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
        assert so.payment_status == "PAID"
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

    buyer_decision = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=buyer_headers,
        json={"action": "APPROVE"},
    )
    assert buyer_decision.status_code == 403
    assert buyer_decision.json()["error"]["code"] == "ERR_FORBIDDEN"


@pytest.mark.parametrize("action", ["APPROVE", "REJECT"])
def test_duplicate_return_decision_has_no_second_side_effect(client, test_setup, action):
    """A resolved request cannot be decided twice or restore inventory twice."""
    buyer_headers = _auth(test_setup["buyer_a"])
    submit_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={"reason": "Duplicate decision test", "evidence": "Photo evidence"},
    )
    return_req_id = submit_res.json()["data"]["id"]
    seller_headers = _auth(test_setup["seller_a"])

    first = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_headers,
        json={"action": action, "decision_notes": "First decision", "is_restockable": True},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_headers,
        json={"action": "APPROVE", "decision_notes": "Duplicate decision"},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "ERR_INVALID_TRANSITION"

    with Session(engine) as session:
        product = session.get(Product, test_setup["product_id"])
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        request = session.get(ReturnRequest, return_req_id)
        assert product.stock_quantity == (12 if action == "APPROVE" else 10)
        assert seller_order.status == (
            "RETURNED_REFUNDED" if action == "APPROVE" else "COMPLETED"
        )
        assert request.decision_notes == "First decision"


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


def test_multi_seller_order_partial_return_approval(client, test_setup):
    """Approving return for one seller in multi-seller order must not clobber other seller state."""
    with Session(engine) as session:
        # Create second product for seller B
        prod_b = Product(
            code="RET-P2",
            seller_id=test_setup["seller_b"].id,
            name="Seller B Gadget",
            price=200_000,
            stock_quantity=10,
            is_active=True,
        )
        session.add(prod_b)
        session.flush()

        # Add second seller order to existing order
        so_b = SellerOrder(
            order_id=test_setup["order_id"],
            seller_id=test_setup["seller_b"].id,
            status="DELIVERED",
            payment_status="PAID",
            escrow_status="HELD",
        )
        session.add(so_b)
        session.flush()

        item_b = OrderItem(
            seller_order_id=so_b.id,
            product_id=prod_b.id,
            quantity=1,
            unit_price=200_000,
        )
        session.add(item_b)

        # Update parent total
        order = session.get(Order, test_setup["order_id"])
        order.total_amount = 500_000
        session.add(order)
        session.commit()
        so_b_id = so_b.id

    buyer_headers = _auth(test_setup["buyer_a"])
    # Submit return for seller A only
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={
            "seller_order_id": test_setup["seller_order_id"],
            "reason": "Seller A item defective",
            "evidence": "Photos provided",
        },
    )
    assert sub_res.status_code == 201
    return_req_id = sub_res.json()["data"]["id"]

    # Verify sub-order A is RETURN_REQUESTED and escrow PAUSED
    with Session(engine) as session:
        so_a = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so_a.status == "RETURN_REQUESTED"
        assert so_a.escrow_status == "PAUSED"

        so_b = session.get(SellerOrder, so_b_id)
        assert so_b.status == "DELIVERED"
        assert so_b.escrow_status == "HELD"

        parent = session.get(Order, test_setup["order_id"])
        assert parent.status == "RETURN_REQUESTED"
        assert parent.escrow_status == "PAUSED"
        assert parent.payment_status == "PAID"

    # Seller A approves return request
    seller_a_headers = _auth(test_setup["seller_a"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_a_headers,
        json={"action": "APPROVE", "decision_notes": "Accepted return", "is_restockable": True},
    )
    assert dec_res.status_code == 200

    with Session(engine) as session:
        so_a = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so_a.status == "RETURNED_REFUNDED"
        assert so_a.payment_status == "REFUNDED"
        assert so_a.escrow_status == "REFUNDED"

        # Seller B order remains unchanged: DELIVERED, PAID, HELD
        so_b = session.get(SellerOrder, so_b_id)
        assert so_b.status == "DELIVERED"
        assert so_b.payment_status == "PAID"
        assert so_b.escrow_status == "HELD"

        # Parent order reflects partial state:
        parent = session.get(Order, test_setup["order_id"])
        assert parent.status == "DELIVERED"  # remaining sub-order is DELIVERED
        assert parent.payment_status == "PARTIALLY_REFUNDED"  # NOT fully REFUNDED
        assert parent.escrow_status == "HELD"  # NOT REFUNDED or RELEASED


def test_multi_seller_order_partial_return_rejection(client, test_setup):
    """Rejecting return for one seller in multi-seller order must not complete the whole order."""
    with Session(engine) as session:
        prod_b = Product(
            code="RET-P3",
            seller_id=test_setup["seller_b"].id,
            name="Seller B Gadget 2",
            price=200_000,
            stock_quantity=10,
            is_active=True,
        )
        session.add(prod_b)
        session.flush()

        so_b = SellerOrder(
            order_id=test_setup["order_id"],
            seller_id=test_setup["seller_b"].id,
            status="DELIVERED",
            payment_status="PAID",
            escrow_status="HELD",
        )
        session.add(so_b)
        session.flush()

        item_b = OrderItem(
            seller_order_id=so_b.id,
            product_id=prod_b.id,
            quantity=1,
            unit_price=200_000,
        )
        session.add(item_b)

        order = session.get(Order, test_setup["order_id"])
        order.total_amount = 500_000
        session.add(order)
        session.commit()
        so_b_id = so_b.id

    buyer_headers = _auth(test_setup["buyer_a"])
    sub_res = client.post(
        f"/api/v1/orders/{test_setup['order_id']}/returns",
        headers=buyer_headers,
        json={
            "seller_order_id": test_setup["seller_order_id"],
            "reason": "Change of mind",
            "evidence": "N/A",
        },
    )
    assert sub_res.status_code == 201
    return_req_id = sub_res.json()["data"]["id"]

    # Seller A rejects return request
    seller_a_headers = _auth(test_setup["seller_a"])
    dec_res = client.post(
        f"/api/v1/return-requests/{return_req_id}/decision",
        headers=seller_a_headers,
        json={"action": "REJECT", "decision_notes": "Return policy expired"},
    )
    assert dec_res.status_code == 200

    with Session(engine) as session:
        so_a = session.get(SellerOrder, test_setup["seller_order_id"])
        assert so_a.status == "COMPLETED"
        assert so_a.escrow_status == "RELEASED"

        # Seller B order remains DELIVERED and HELD
        so_b = session.get(SellerOrder, so_b_id)
        assert so_b.status == "DELIVERED"
        assert so_b.escrow_status == "HELD"

        # Parent order remains in PROCESSING (since one is COMPLETED and one is DELIVERED)
        # and escrow_status remains HELD (not completed or fully released)
        parent = session.get(Order, test_setup["order_id"])
        assert parent.status != "COMPLETED"
        assert parent.escrow_status == "HELD"


def _setup_concurrency_db(tmp_path, db_name="concurrent.db"):
    from tests.cart_db import create_cart_engine

    test_db = create_cart_engine(tmp_path / db_name)
    with test_db.connect() as conn:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_return_requests_seller_order_pending "
            "ON return_requests(seller_order_id) WHERE status = 'PENDING'"
        )
        conn.commit()

    with Session(test_db) as session:
        seller = session.get(User, 1)
        buyer = session.get(User, 2)
        prod = Product(
            code="RET-CONC",
            seller_id=seller.id,
            name="Concurrent Item",
            price=150_000,
            stock_quantity=10,
            is_active=True,
        )
        session.add(prod)
        session.flush()

        order = Order(
            buyer_id=buyer.id,
            total_amount=300_000,
            status="DELIVERED",
            payment_status="PAID",
            escrow_status="HELD",
            recipient_name="Buyer",
            delivery_address="123 Street",
            phone_number="0987654321",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,
            seller_id=seller.id,
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

        return test_db, order.id, so.id, prod.id, buyer.id, seller.id


def test_concurrent_return_submissions_prevent_duplicates(tmp_path):
    """Concurrent return submissions for same seller order yield 1 success and 1 conflict."""
    test_db, order_id, so_id, _prod_id, buyer_id, _seller_id = _setup_concurrency_db(
        tmp_path, "sub.db"
    )
    payload = CreateReturnRequest(
        seller_order_id=so_id,
        reason="Concurrent reason",
        evidence="Concurrent evidence",
    )
    barrier = Barrier(2)

    def worker():
        barrier.wait(timeout=10)
        with Session(test_db) as session:
            user = session.get(User, buyer_id)
            try:
                res = submit_return_request(session, user, order_id, payload)
                return 201, res
            except ReturnError as exc:
                return exc.status, exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker)
        f2 = pool.submit(worker)
        r1 = f1.result(timeout=15)
        r2 = f2.result(timeout=15)

    statuses = sorted([r1[0], r2[0]])
    assert statuses in ([201, 400], [201, 409])

    with Session(test_db) as session:
        requests = session.exec(
            select(ReturnRequest).where(ReturnRequest.seller_order_id == so_id)
        ).all()
        assert len(requests) == 1


def test_concurrent_return_decisions_prevent_duplicate_restock(tmp_path):
    """Concurrent return approvals must serialize and restock inventory exactly once."""
    test_db, order_id, so_id, prod_id, buyer_id, seller_id = _setup_concurrency_db(
        tmp_path, "dec.db"
    )
    with Session(test_db) as session:
        buyer = session.get(User, buyer_id)
        req = submit_return_request(
            session,
            buyer,
            order_id,
            CreateReturnRequest(
                seller_order_id=so_id,
                reason="Restock item",
                evidence="Photo proof",
            ),
        )
        return_req_id = req.id

    barrier = Barrier(2)
    decision_payload = ReturnDecisionRequest(
        action="APPROVE",
        decision_notes="Concurrent approval",
        is_restockable=True,
    )

    def worker():
        barrier.wait(timeout=10)
        with Session(test_db) as session:
            user = session.get(User, seller_id)
            try:
                res = decide_return_request(session, user, return_req_id, decision_payload)
                return 200, res
            except ReturnError as exc:
                return exc.status, exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker)
        f2 = pool.submit(worker)
        r1 = f1.result(timeout=15)
        r2 = f2.result(timeout=15)

    statuses = sorted([r1[0], r2[0]])
    assert statuses == [200, 400]

    with Session(test_db) as session:
        prod = session.get(Product, prod_id)
        # Initial stock was 10, item quantity was 2: must be exactly 12, version exactly 2
        assert prod.stock_quantity == 12
        assert prod.version == 2


