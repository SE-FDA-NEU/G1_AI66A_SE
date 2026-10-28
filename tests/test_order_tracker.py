"""Tests for order status transitions, tracking milestones, atomic cancellation,
concurrency, self-purchase blocking, and idempotency (P0 Order Tracker).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, delete, select
from starlette.testclient import TestClient

from src.auth import create_access_token, hash_password
from src.database import engine
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.orders import CheckoutRequest
from src.services.orders import checkout


@pytest.fixture
def tracker_fixture():
    with Session(engine) as session:
        session.exec(delete(OrderHistory))
        session.exec(delete(OrderItem))
        session.exec(delete(CartItem))
        session.exec(delete(ProductVariant))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(ProductMetadata))
        session.exec(delete(Product).where(Product.code.like("TRK-%")))
        session.exec(delete(User).where(User.email.like("trk-%@example.com")))

        seller_a = User(
            name="Tracker Seller A",
            email="trk-seller-a@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        seller_b = User(
            name="Tracker Seller B",
            email="trk-seller-b@example.com",
            role="seller",
            password_hash=hash_password("password"),
        )
        buyer = User(
            name="Tracker Buyer",
            email="trk-buyer@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add_all([seller_a, seller_b, buyer])
        session.flush()

        prod_a = Product(
            code="TRK-A",
            seller_id=seller_a.id,
            name="Tracked Product A",
            price=150_000,
            stock_quantity=10,
            version=1,
            is_active=True,
        )
        prod_b = Product(
            code="TRK-B",
            seller_id=seller_b.id,
            name="Tracked Product B",
            price=250_000,
            stock_quantity=10,
            version=1,
            is_active=True,
        )
        session.add_all([prod_a, prod_b])
        session.flush()

        meta_a = ProductMetadata(
            product_id=prod_a.id,
            rating=0.0,
            sales_count=0,
            created_at=datetime.now(UTC),
        )
        meta_b = ProductMetadata(
            product_id=prod_b.id,
            rating=0.0,
            sales_count=0,
            created_at=datetime.now(UTC),
        )
        session.add_all([meta_a, meta_b])
        session.commit()

        data = {
            "seller_a_id": seller_a.id,
            "seller_b_id": seller_b.id,
            "buyer_id": buyer.id,
            "seller_a_token": create_access_token(seller_a),
            "seller_b_token": create_access_token(seller_b),
            "buyer_token": create_access_token(buyer),
            "product_a_id": prod_a.id,
            "product_b_id": prod_b.id,
        }

    yield data

    with Session(engine) as session:
        session.exec(delete(OrderHistory))
        session.exec(delete(OrderItem))
        session.exec(delete(CartItem))
        session.exec(delete(ProductVariant))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(ProductMetadata))
        session.exec(delete(Product).where(Product.code.like("TRK-%")))
        session.exec(delete(User).where(User.email.like("trk-%@example.com")))
        session.commit()


def _create_single_order(tracker_fixture, initial_status="PENDING", quantity=2):
    with Session(engine) as session:
        order = Order(
            buyer_id=tracker_fixture["buyer_id"],
            total_amount=quantity * 150_000,
            status=initial_status,
            recipient_name="Tracker Buyer",
            delivery_address="456 Tracking Way",
            phone_number="0987654321",
            created_at=datetime.now(UTC),
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,
            seller_id=tracker_fixture["seller_a_id"],
            status=initial_status,
            created_at=datetime.now(UTC),
        )
        session.add(so)
        session.flush()

        oi = OrderItem(
            seller_order_id=so.id,
            product_id=tracker_fixture["product_a_id"],
            quantity=quantity,
            unit_price=150_000,
        )
        session.add(oi)

        # deduct stock to simulate checkout
        prod = session.get(Product, tracker_fixture["product_a_id"])
        prod.stock_quantity -= quantity
        prod.version += 1
        session.add(prod)

        meta = session.get(ProductMetadata, tracker_fixture["product_a_id"])
        if meta:
            meta.sales_count += quantity
            session.add(meta)

        session.commit()
        return order.id, so.id


# -----------------------------------------------------------------------------
# AC 1: Allowed order-state transitions from PENDING & history audit
# -----------------------------------------------------------------------------
def test_seller_confirms_pending_order(client: TestClient, tracker_fixture):
    order_id, so_id = _create_single_order(tracker_fixture, initial_status="PENDING")
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    res = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "CONFIRMED"

    with Session(engine) as session:
        hist = session.exec(select(OrderHistory).where(OrderHistory.seller_order_id == so_id)).all()
        assert len(hist) == 1
        assert hist[0].from_status == "PENDING"
        assert hist[0].to_status == "CONFIRMED"
        assert hist[0].changed_by_user_id == tracker_fixture["seller_a_id"]

        parent = session.get(Order, order_id)
        assert parent.status == "CONFIRMED"


def test_seller_cancels_pending_order_and_restores_stock(client: TestClient, tracker_fixture):
    order_id, so_id = _create_single_order(tracker_fixture, initial_status="PENDING", quantity=3)
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    res = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "CANCELLED"},
    )
    assert res.status_code == 200, res.text

    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 10  # 10 - 3 + 3 = 10
        meta = session.get(ProductMetadata, tracker_fixture["product_a_id"])
        assert meta.sales_count == 0

        hist = session.exec(select(OrderHistory).where(OrderHistory.seller_order_id == so_id)).all()
        assert len(hist) == 1
        assert hist[0].to_status == "CANCELLED"


def test_buyer_cancels_pending_order(client: TestClient, tracker_fixture):
    order_id, so_id = _create_single_order(tracker_fixture, initial_status="PENDING", quantity=2)
    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}

    res = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "CANCELLED"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "CANCELLED"

    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 10
        so = session.get(SellerOrder, so_id)
        assert so.status == "CANCELLED"


def test_buyer_cancellation_validates_every_multi_seller_sub_order(
    client: TestClient, tracker_fixture
):
    with Session(engine) as session:
        order = Order(
            buyer_id=tracker_fixture["buyer_id"],
            total_amount=400_000,
            status="CONFIRMED",
            recipient_name="Tracker Buyer",
            delivery_address="456 Tracking Way",
            phone_number="0987654321",
            created_at=datetime.now(UTC),
        )
        session.add(order)
        session.flush()
        seller_order_a = SellerOrder(
            order_id=order.id,
            seller_id=tracker_fixture["seller_a_id"],
            status="CONFIRMED",
        )
        seller_order_b = SellerOrder(
            order_id=order.id,
            seller_id=tracker_fixture["seller_b_id"],
            status="PENDING",
        )
        session.add_all([seller_order_a, seller_order_b])
        session.flush()
        session.add_all(
            [
                OrderItem(
                    seller_order_id=seller_order_a.id,
                    product_id=tracker_fixture["product_a_id"],
                    quantity=2,
                    unit_price=150_000,
                ),
                OrderItem(
                    seller_order_id=seller_order_b.id,
                    product_id=tracker_fixture["product_b_id"],
                    quantity=1,
                    unit_price=250_000,
                ),
            ]
        )
        for product_id, quantity in (
            (tracker_fixture["product_a_id"], 2),
            (tracker_fixture["product_b_id"], 1),
        ):
            product = session.get(Product, product_id)
            assert product is not None
            product.stock_quantity -= quantity
            product.version += 1
            session.add(product)
        session.commit()
        order_id = order.id
        seller_order_a_id = seller_order_a.id
        seller_order_b_id = seller_order_b.id

    buyer_hdr = {"Authorization": "Bearer " + tracker_fixture["buyer_token"]}
    seller_b_hdr = {"Authorization": "Bearer " + tracker_fixture["seller_b_token"]}

    requested = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "CANCELLATION_REQUESTED"},
    )
    assert requested.status_code == 200
    cancelled_by_seller = client.patch(
        f"/api/v1/seller/orders/{seller_order_b_id}/status",
        headers=seller_b_hdr,
        json={"status": "CANCELLED"},
    )
    assert cancelled_by_seller.status_code == 200

    with Session(engine) as session:
        before = {
            "parent": session.get(Order, order_id).status,
            "seller_a": session.get(SellerOrder, seller_order_a_id).status,
            "seller_b": session.get(SellerOrder, seller_order_b_id).status,
            "stock_a": session.get(Product, tracker_fixture["product_a_id"]).stock_quantity,
            "stock_b": session.get(Product, tracker_fixture["product_b_id"]).stock_quantity,
            "history": [
                (row.seller_order_id, row.from_status, row.to_status)
                for row in session.exec(select(OrderHistory)).all()
            ],
        }

    rejected = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "CANCELLED"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "ERR_INVALID_TRANSITION"

    with Session(engine) as session:
        assert session.get(Order, order_id).status == before["parent"]
        assert session.get(SellerOrder, seller_order_a_id).status == before["seller_a"]
        assert session.get(SellerOrder, seller_order_b_id).status == before["seller_b"]
        assert (
            session.get(Product, tracker_fixture["product_a_id"]).stock_quantity
            == before["stock_a"]
        )
        assert (
            session.get(Product, tracker_fixture["product_b_id"]).stock_quantity
            == before["stock_b"]
        )
        after_history = [
            (row.seller_order_id, row.from_status, row.to_status)
            for row in session.exec(select(OrderHistory)).all()
        ]
        assert after_history == before["history"]


def test_disallowed_transition_from_pending_rejected(client: TestClient, tracker_fixture):
    _, so_id = _create_single_order(tracker_fixture, initial_status="PENDING")
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    res = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "COMPLETED"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "ERR_INVALID_TRANSITION"


# -----------------------------------------------------------------------------
# AC 2: Tracking milestones & buyer confirmation action
# -----------------------------------------------------------------------------
def test_shipping_milestone_and_buyer_confirmation(client: TestClient, tracker_fixture):
    order_id, so_id = _create_single_order(tracker_fixture, initial_status="CONFIRMED")
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}
    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}

    # Seller ships with tracking number
    res_ship = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "SHIPPED", "tracking_number": "VN-TRACK-999"},
    )
    assert res_ship.status_code == 200
    data_ship = res_ship.json()["data"]
    assert data_ship["status"] == "SHIPPED"
    assert data_ship["tracking_number"] == "VN-TRACK-999"
    assert data_ship["shipped_at"] is not None

    # Seller marks delivered
    res_deliv = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "DELIVERED"},
    )
    assert res_deliv.status_code == 200
    data_deliv = res_deliv.json()["data"]
    assert data_deliv["status"] == "DELIVERED"
    assert data_deliv["delivered_at"] is not None

    # Buyer views order receipt and verifies milestones
    res_receipt = client.get(f"/api/v1/orders/{order_id}", headers=buyer_hdr)
    assert res_receipt.status_code == 200
    r_data = res_receipt.json()["data"]
    assert r_data["status"] == "DELIVERED"
    assert r_data["tracking_number"] == "VN-TRACK-999"
    assert r_data["shipped_at"] is not None
    assert r_data["delivered_at"] is not None

    # Buyer confirmation action
    res_confirm = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "COMPLETED"},
    )
    assert res_confirm.status_code == 200
    assert res_confirm.json()["data"]["status"] == "COMPLETED"
    assert res_confirm.json()["data"]["completed_at"] is not None

    with Session(engine) as session:
        so = session.get(SellerOrder, so_id)
        assert so.status == "COMPLETED"
        assert so.completed_at is not None
        hist = session.exec(select(OrderHistory).where(OrderHistory.seller_order_id == so_id)).all()
        to_statuses = [h.to_status for h in hist]
        assert "SHIPPED" in to_statuses
        assert "DELIVERED" in to_statuses
        assert "COMPLETED" in to_statuses


# -----------------------------------------------------------------------------
# AC 3: Buyer requests cancellation after confirmation; Seller approves/rejects
# -----------------------------------------------------------------------------
def test_buyer_cancellation_request_and_seller_rejection(client: TestClient, tracker_fixture):
    order_id, so_id = _create_single_order(tracker_fixture, initial_status="CONFIRMED", quantity=2)
    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    # Buyer requests cancellation
    res_req = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "CANCELLATION_REQUESTED"},
    )
    assert res_req.status_code == 200
    assert res_req.json()["data"]["status"] == "CANCELLATION_REQUESTED"

    # Stock should NOT be restored yet
    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 8  # was 10 - 2

    # Seller rejects cancellation by reverting to CONFIRMED
    res_reject = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res_reject.status_code == 200
    assert res_reject.json()["data"]["status"] == "CONFIRMED"

    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 8  # Still 8, stock untouched


def test_buyer_cancellation_request_and_seller_approval_restores_stock_once(
    client: TestClient, tracker_fixture
):
    order_id, so_id = _create_single_order(
        tracker_fixture, initial_status="CONFIRMED", quantity=2
    )
    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}
    seller_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    # Buyer requests cancellation
    client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=buyer_hdr,
        json={"status": "CANCELLATION_REQUESTED"},
    )

    # Seller approves cancellation
    res_approve = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "CANCELLED"},
    )
    assert res_approve.status_code == 200

    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 10  # Restored exactly once (8 + 2 = 10)
        assert prod.version == 3

    # Attempt to cancel again must be rejected
    res_repeat = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "CANCELLED"},
    )
    assert res_repeat.status_code == 400
    assert res_repeat.json()["error"]["code"] == "ERR_INVALID_TRANSITION"

    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_a_id"])
        assert prod.stock_quantity == 10  # Never incremented twice


# -----------------------------------------------------------------------------
# AC 4: Concurrent checkouts competing for limited stock roll back without overselling
# -----------------------------------------------------------------------------
def test_concurrent_checkouts_prevent_overselling(tmp_path):
    from tests.cart_db import add_product, create_cart_engine
    test_db = create_cart_engine(tmp_path / "concurrent_checkout.db")

    add_product(test_db, "TRK-RACE", stock=1)
    with Session(test_db) as session:
        prod = session.exec(select(Product).where(Product.code == "TRK-RACE")).one()
        # buyer 2 and buyer 3 already exist in cart_db
        session.add(CartItem(buyer_id=2, product_id=prod.id, quantity=1))
        session.add(CartItem(buyer_id=3, product_id=prod.id, quantity=1))
        session.commit()

    body = CheckoutRequest(
        recipient_name="Competitor",
        delivery_address="Race track",
        phone_number="0912345678",
    )

    results = []

    def run_checkout(b_id, key):
        with Session(test_db) as s:
            try:
                receipt_data, created = checkout(s, b_id, body, key)
                results.append((b_id, 201 if created else 200, None))
            except Exception as exc:
                results.append((b_id, getattr(exc, "status", 500), getattr(exc, "code", str(exc))))

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_checkout, 2, "race-key-1")
        f2 = executor.submit(run_checkout, 3, "race-key-2")
        f1.result()
        f2.result()

    successes = [r for r in results if r[1] in (200, 201)]
    conflicts = [r for r in results if r[1] == 409]

    assert len(successes) == 1, f"Expected 1 winner, got: {results}"
    assert len(conflicts) == 1, f"Expected 1 conflict, got: {results}"

    with Session(test_db) as session:
        prod = session.exec(select(Product).where(Product.code == "TRK-RACE")).one()
        assert prod.stock_quantity == 0  # No overselling!


# -----------------------------------------------------------------------------
# AC 5: Resource ownership verification & blocking self-purchases
# -----------------------------------------------------------------------------
def test_unauthorized_seller_cannot_update_order(client: TestClient, tracker_fixture):
    _, so_id = _create_single_order(tracker_fixture)
    seller_b_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_b_token']}"}

    res = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_b_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ERR_RESOURCE_OWNER"


def test_unauthorized_seller_cannot_update_product(client: TestClient, tracker_fixture):
    seller_b_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_b_token']}"}

    res = client.patch(
        f"/api/v1/seller/products/{tracker_fixture['product_a_id']}",
        headers=seller_b_hdr,
        json={"name": "Hacked Name"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ERR_RESOURCE_OWNER"


def test_self_purchase_is_blocked_at_cart_and_checkout(client: TestClient, tracker_fixture):
    # Create a product owned by the buyer to test self-purchase as a buyer
    with Session(engine) as session:
        own_product = Product(
            code="TRK-OWN",
            seller_id=tracker_fixture["buyer_id"],
            name="Buyer Own Product",
            price=50_000,
            stock_quantity=5,
            is_active=True,
        )
        session.add(own_product)
        session.commit()

    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}

    # Buyer attempts to add their own product to cart
    res_cart = client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-OWN", "quantity": 1},
    )
    assert res_cart.status_code == 400
    assert res_cart.json()["error"]["code"] == "ERR_SELF_PURCHASE"

    # Direct checkout service attempt with self-purchase
    with Session(engine) as session:
        prod = session.exec(select(Product).where(Product.code == "TRK-OWN")).one()
        session.add(
            CartItem(
                buyer_id=tracker_fixture["buyer_id"],
                product_id=prod.id,
                quantity=1,
            )
        )
        session.commit()

        body = CheckoutRequest(
            recipient_name="Self Buyer",
            delivery_address="Home",
            phone_number="0912345678",
        )
        with pytest.raises(Exception) as exc_info:
            checkout(session, tracker_fixture["buyer_id"], body, "self-purchase-key")
        assert getattr(exc_info.value, "code", "") == "ERR_SELF_PURCHASE"


# -----------------------------------------------------------------------------
# AC 6: Idempotent checkout retry returns existing order
# -----------------------------------------------------------------------------
def test_idempotent_checkout_retry(client: TestClient, tracker_fixture):
    buyer_hdr = {
        "Authorization": f"Bearer {tracker_fixture['buyer_token']}",
        "Idempotency-Key": "idemp-key-test-1",
    }
    # Add product B to cart
    client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {tracker_fixture['buyer_token']}"},
        json={"product_code": "TRK-B", "quantity": 1},
    )

    body = {
        "recipient_name": "Idemp Buyer",
        "delivery_address": "Repeat Ave",
        "phone_number": "0912345678",
    }
    res1 = client.post("/api/v1/orders", headers=buyer_hdr, json=body)
    assert res1.status_code == 201
    order1 = res1.json()["data"]

    # Retry same key
    res2 = client.post("/api/v1/orders", headers=buyer_hdr, json=body)
    assert res2.status_code == 200
    order2 = res2.json()["data"]
    assert order1["id"] == order2["id"]

    # Check stock was only decremented once
    with Session(engine) as session:
        prod = session.get(Product, tracker_fixture["product_b_id"])
        assert prod.stock_quantity == 9  # 10 - 1


# -----------------------------------------------------------------------------
# Related screen / route: /order/:id & /orders/:id
# -----------------------------------------------------------------------------
def test_order_tracker_routes_and_assets(client: TestClient):
    res1 = client.get("/order/1")
    assert res1.status_code == 200
    assert "Order Tracker" in res1.text
    assert "/static/order.js" in res1.text
    assert "/static/order.css" in res1.text

    res2 = client.get("/orders/1")
    assert res2.status_code == 200
    assert "Order Tracker" in res2.text

    css = client.get("/static/order.css")
    assert css.status_code == 200

    js = client.get("/static/order.js")
    assert js.status_code == 200
    assert "Confirm Receipt" in js.text or "confirm-delivery-btn" in js.text


def test_both_roles_can_track_order_and_execute_transitions(client: TestClient, tracker_fixture):
    """Both buyer and seller can track the order via /api/v1/orders/{id}
    and perform role-allowed updates.
    """
    seller_a_token = tracker_fixture["seller_a_token"]
    seller_b_token = tracker_fixture["seller_b_token"]
    buyer_token = tracker_fixture["buyer_token"]

    seller_a_hdr = {"Authorization": f"Bearer {seller_a_token}"}
    seller_b_hdr = {"Authorization": f"Bearer {seller_b_token}"}
    buyer_hdr = {
        "Authorization": f"Bearer {buyer_token}",
        "Idempotency-Key": "track-flow-test-key",
    }

    # Buyer places order for Seller A's product
    with Session(engine) as session:
        session.add(
            CartItem(
                buyer_id=tracker_fixture["buyer_id"],
                product_id=tracker_fixture["product_a_id"],
                quantity=1,
            )
        )
        session.commit()

    order_res = client.post(
        "/api/v1/orders",
        headers=buyer_hdr,
        json={
            "recipient_name": "Test Flow Buyer",
            "delivery_address": "456 Test Way",
            "phone_number": "0912345678",
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["data"]["id"]

    # 1. Buyer can get order tracker receipt
    buyer_get = client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert buyer_get.status_code == 200
    assert buyer_get.json()["data"]["status"] == "PENDING"

    # 2. Owning seller (Seller A) can also get order tracker receipt
    seller_a_get = client.get(f"/api/v1/orders/{order_id}", headers=seller_a_hdr)
    assert seller_a_get.status_code == 200
    assert seller_a_get.json()["data"]["status"] == "PENDING"

    # 3. Non-participating seller (Seller B) cannot view this order
    seller_b_get = client.get(f"/api/v1/orders/{order_id}", headers=seller_b_hdr)
    assert seller_b_get.status_code == 404

    # 4. Seller confirms order directly via /api/v1/orders/{order_id}/status
    seller_confirm = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "CONFIRMED"},
    )
    assert seller_confirm.status_code == 200
    assert seller_confirm.json()["data"]["status"] == "CONFIRMED"

    # 5. Seller ships order with tracking number directly via /api/v1/orders/{order_id}/status
    seller_ship = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "SHIPPED", "tracking_number": "TRACK-VN-999"},
    )
    assert seller_ship.status_code == 200
    assert seller_ship.json()["data"]["status"] == "SHIPPED"
    assert seller_ship.json()["data"]["tracking_number"] == "TRACK-VN-999"
    assert seller_ship.json()["data"]["shipped_at"] is not None

    # 6. Seller delivers order
    seller_deliver = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "DELIVERED"},
    )
    assert seller_deliver.status_code == 200
    assert seller_deliver.json()["data"]["status"] == "DELIVERED"
    assert seller_deliver.json()["data"]["delivered_at"] is not None

    # 7. Buyer confirms delivery receipt -> COMPLETED
    buyer_complete = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"status": "COMPLETED"},
    )
    assert buyer_complete.status_code == 200
    assert buyer_complete.json()["data"]["status"] == "COMPLETED"
    assert buyer_complete.json()["data"]["completed_at"] is not None

    # 8. Buyer can list their orders
    buyer_orders_list = client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert buyer_orders_list.status_code == 200
    orders_data = buyer_orders_list.json()
    assert any(o["data"]["id"] == order_id for o in orders_data)


def test_order_tracker_xss_protection_in_order_js(client: TestClient):
    """Regression test: verify order.js renders product names and codes via textContent

    and does not inject untrusted product data directly into innerHTML.
    """
    res = client.get("/static/order.js")
    assert res.status_code == 200
    js_text = res.text

    # Verify DOM creation and textContent are used for product items
    assert "strongName.textContent = item.product_name" in js_text
    assert "codeEl.textContent = item.product_code" in js_text

    # Verify no raw innerHTML interpolation of item properties
    assert "${item.product_name}" not in js_text
    assert "${item.product_code}" not in js_text

    # Verify map marker popup does not interpolate raw unescaped values into HTML
    assert "${address}" not in js_text


def test_order_api_supports_malicious_xss_payloads_safely(client: TestClient, tracker_fixture):
    """Regression test: seller products with HTML/JS payloads can be ordered

    and returned safely without corrupting API payloads or failing JSON serialization.
    """
    buyer_token = tracker_fixture["buyer_token"]

    # Set product name with XSS payload (simulating seller updating product name)
    xss_payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    prod_id = tracker_fixture["product_a_id"]
    with Session(engine) as session:
        prod = session.get(Product, prod_id)
        prod.name = f"Malicious Product {xss_payload}"
        prod_code = prod.code
        session.commit()

    # Buyer adds to cart and checks out
    add_cart = client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"product_code": prod_code, "quantity": 1},
    )
    assert add_cart.status_code in (200, 201)

    checkout_res = client.post(
        "/api/v1/orders",
        headers={
            "Authorization": f"Bearer {buyer_token}",
            "Idempotency-Key": "xss-regression-order-key",
        },
        json={
            "recipient_name": 'Buyer <svg onload=alert("xss")>',
            "delivery_address": "123 Injection St <script>",
            "phone_number": "0900000000",
        },
    )
    assert checkout_res.status_code == 201
    order_id = checkout_res.json()["data"]["id"]

    # Fetch order receipt via API
    order_detail = client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert order_detail.status_code == 200
    items = order_detail.json()["data"]["items"]
    assert len(items) >= 1
    item = next(it for it in items if it["product_id"] == prod_id)
    assert xss_payload in item["product_name"]

def test_seller_ownership_on_all_product_and_variant_mutations(client: TestClient, tracker_fixture):
    """Sellers cannot update or delete products or variants owned by another seller."""
    seller_b_token = tracker_fixture["seller_b_token"]
    buyer_token = tracker_fixture["buyer_token"]
    prod_a_id = tracker_fixture["product_a_id"]

    seller_b_hdr = {"Authorization": f"Bearer {seller_b_token}"}
    buyer_hdr = {"Authorization": f"Bearer {buyer_token}"}

    # Create a variant for product_a (owned by seller_a)
    with Session(engine) as session:
        var_a = ProductVariant(
            product_id=prod_a_id,
            seller_id=tracker_fixture["seller_a_id"],
            sku="TRK-VAR-A1",
            name="Tracked Variant A1",
            price=175_000,
            stock_quantity=5,
            version=1,
            is_active=True,
        )
        session.add(var_a)
        session.commit()
        session.refresh(var_a)
        var_a_id = var_a.id

    # 1. Seller B cannot PUT product A
    res_put = client.put(
        f"/api/v1/seller/products/{prod_a_id}",
        headers=seller_b_hdr,
        json={"name": "Hacked Name"},
    )
    assert res_put.status_code == 403
    assert res_put.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 2. Seller B cannot DELETE product A
    res_del = client.delete(
        f"/api/v1/seller/products/{prod_a_id}",
        headers=seller_b_hdr,
    )
    assert res_del.status_code == 403
    assert res_del.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 3. Seller B cannot POST a variant to product A
    res_post_var = client.post(
        f"/api/v1/seller/products/{prod_a_id}/variants",
        headers=seller_b_hdr,
        json={
            "sku": "TRK-VAR-B-HACK",
            "name": "Unauthorized Variant",
            "price": 99_000,
            "stock_quantity": 10,
        },
    )
    assert res_post_var.status_code == 403
    assert res_post_var.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 4. Seller B cannot PATCH variant of product A
    res_patch_var = client.patch(
        f"/api/v1/seller/products/{prod_a_id}/variants/{var_a_id}",
        headers=seller_b_hdr,
        json={"name": "Unauthorized Update", "expected_version": 1},
    )
    assert res_patch_var.status_code == 403
    assert res_patch_var.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 5. Seller B cannot DELETE variant of product A
    res_del_var = client.delete(
        f"/api/v1/seller/products/{prod_a_id}/variants/{var_a_id}",
        headers=seller_b_hdr,
    )
    assert res_del_var.status_code == 403
    assert res_del_var.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 6. Buyer role attempting seller product mutations gets 403
    assert client.patch(
        f"/api/v1/seller/products/{prod_a_id}",
        headers=buyer_hdr,
        json={"name": "Buyer Hack"},
    ).status_code == 403

    # 7. Unauthenticated request gets 401
    assert client.patch(
        f"/api/v1/seller/products/{prod_a_id}",
        json={"name": "Guest Hack"},
    ).status_code == 401


def test_seller_ownership_on_order_mutations_and_multi_seller_isolation(
    client: TestClient, tracker_fixture
):
    """Sellers cannot modify foreign sub-orders; multi-seller order mutations are isolated."""
    seller_a_token = tracker_fixture["seller_a_token"]
    seller_b_token = tracker_fixture["seller_b_token"]
    buyer_token = tracker_fixture["buyer_token"]

    seller_a_hdr = {"Authorization": f"Bearer {seller_a_token}"}
    seller_b_hdr = {"Authorization": f"Bearer {seller_b_token}"}
    buyer_hdr = {"Authorization": f"Bearer {buyer_token}"}

    # Buyer orders 1 item from Seller A and 1 item from Seller B
    client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-A", "quantity": 1},
    )
    client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-B", "quantity": 1},
    )
    order_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": "multi-seller-order-key"},
        json={
            "recipient_name": "Multi Buyer",
            "delivery_address": "789 Isolation Blvd",
            "phone_number": "0912345678",
        },
    )
    assert order_res.status_code == 201
    order_data = order_res.json()["data"]
    order_id = order_data["id"]
    sub_orders = order_data["sub_orders"]
    assert len(sub_orders) == 2

    so_a = next(so for so in sub_orders if so["seller_id"] == tracker_fixture["seller_a_id"])
    so_b = next(so for so in sub_orders if so["seller_id"] == tracker_fixture["seller_b_id"])

    # 1. Seller A attempts to update Seller B's sub-order -> 403 ERR_RESOURCE_OWNER
    res_cross = client.patch(
        f"/api/v1/seller/orders/{so_b['id']}/status",
        headers=seller_a_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res_cross.status_code == 403
    assert res_cross.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # Seller B attempts to update Seller A's sub-order -> 403 ERR_RESOURCE_OWNER
    res_cross_b = client.patch(
        f"/api/v1/seller/orders/{so_a['id']}/status",
        headers=seller_b_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res_cross_b.status_code == 403
    assert res_cross_b.json()["error"]["code"] == "ERR_RESOURCE_OWNER"

    # 2. Buyer attempts to update seller sub-order -> 403
    res_buyer = client.patch(
        f"/api/v1/seller/orders/{so_a['id']}/status",
        headers=buyer_hdr,
        json={"status": "CONFIRMED"},
    )
    assert res_buyer.status_code == 403

    # 3. Unauthenticated attempts get 401
    assert client.patch(
        f"/api/v1/seller/orders/{so_a['id']}/status",
        json={"status": "CONFIRMED"},
    ).status_code == 401

    # 4. Seller A confirms their own sub-order via /api/v1/orders/{order_id}/status
    confirm_res = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "CONFIRMED"},
    )
    assert confirm_res.status_code == 200

    # Verify sub-order A is CONFIRMED, but sub-order B remains PENDING
    with Session(engine) as session:
        db_so_a = session.get(SellerOrder, so_a["id"])
        db_so_b = session.get(SellerOrder, so_b["id"])
        assert db_so_a.status == "CONFIRMED"
        assert db_so_b.status == "PENDING"


def test_block_self_purchase_with_variants_and_multi_item_cart(client: TestClient, tracker_fixture):
    """Self-purchase is blocked for variants, and cart rollbacks prevent partial orders."""
    buyer_id = tracker_fixture["buyer_id"]
    buyer_hdr = {"Authorization": f"Bearer {tracker_fixture['buyer_token']}"}

    # Create a product and variant where seller_id == buyer_id
    with Session(engine) as session:
        own_product = Product(
            code="TRK-OWN-VAR",
            seller_id=buyer_id,
            name="Own Product With Variant",
            price=80_000,
            stock_quantity=10,
            version=1,
            is_active=True,
        )
        session.add(own_product)
        session.commit()
        session.refresh(own_product)
        own_prod_id = own_product.id

        own_variant = ProductVariant(
            product_id=own_prod_id,
            seller_id=buyer_id,
            sku="TRK-OWN-V1",
            name="Own Variant 1",
            price=85_000,
            stock_quantity=5,
            version=1,
            is_active=True,
        )
        session.add(own_variant)
        session.commit()
        session.refresh(own_variant)
        own_var_id = own_variant.id

    # 1. Adding own variant to cart is blocked with 400 ERR_SELF_PURCHASE
    res_add_var = client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-OWN-VAR", "variant_id": own_var_id, "quantity": 1},
    )
    assert res_add_var.status_code == 400
    assert res_add_var.json()["error"]["code"] == "ERR_SELF_PURCHASE"

    # 2. Multi-item cart containing Seller A's product and own product rolls back cleanly
    client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-A", "quantity": 1},
    )
    # Inject own product into CartItem
    with Session(engine) as session:
        session.add(
            CartItem(
                buyer_id=buyer_id,
                product_id=own_prod_id,
                variant_id=own_var_id,
                quantity=1,
            )
        )
        session.commit()

    # Attempt checkout
    checkout_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": "self-purchase-mixed-cart-key"},
        json={
            "recipient_name": "Self Buyer",
            "delivery_address": "Home",
            "phone_number": "0912345678",
        },
    )
    assert checkout_res.status_code == 400
    assert checkout_res.json()["error"]["code"] == "ERR_SELF_PURCHASE"

    # Verify atomic rollback: Seller A's stock was NOT decremented, 0 orders created
    with Session(engine) as session:
        prod_a = session.get(Product, tracker_fixture["product_a_id"])
        assert prod_a.stock_quantity == 10
        orders = session.exec(select(Order).where(Order.buyer_id == buyer_id)).all()
        assert len(orders) == 0


def test_checkout_idempotency_conflicts_and_state_preservation(client: TestClient, tracker_fixture):
    """Idempotency keys must be valid; conflicts return 409; replays preserve current state."""
    buyer_token = tracker_fixture["buyer_token"]
    buyer_hdr = {"Authorization": f"Bearer {buyer_token}"}
    seller_a_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}

    client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-A", "quantity": 1},
    )

    valid_body = {
        "recipient_name": "Idemp Test",
        "delivery_address": "123 Valid St",
        "phone_number": "0912345678",
    }

    # 1. Invalid keys (whitespace or untrimmed) return 400 ERR_INVALID_KEY
    res_ws = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": "   "},
        json=valid_body,
    )
    assert res_ws.status_code == 400
    assert res_ws.json()["error"]["code"] == "ERR_INVALID_KEY"

    res_pad = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": " padded-key "},
        json=valid_body,
    )
    assert res_pad.status_code == 400
    assert res_pad.json()["error"]["code"] == "ERR_INVALID_KEY"

    # 2. Place order successfully with 201
    idemp_key = "idemp-preserve-state-key-1"
    create_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": idemp_key},
        json=valid_body,
    )
    assert create_res.status_code == 201
    order_id = create_res.json()["data"]["id"]

    # 3. Replay with same key but altered payload returns 409 ERR_IDEMPOTENCY_CONFLICT
    conflict_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": idemp_key},
        json={**valid_body, "delivery_address": "999 Altered St"},
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["error"]["code"] == "ERR_IDEMPOTENCY_CONFLICT"

    # 4. Another buyer using same key returns 409 ERR_IDEMPOTENCY_CONFLICT
    with Session(engine) as session:
        buyer2 = User(
            name="Second Buyer",
            email="trk-buyer-second@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add(buyer2)
        session.commit()
        buyer2_token = create_access_token(buyer2)

    conflict_buyer = client.post(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {buyer2_token}", "Idempotency-Key": idemp_key},
        json=valid_body,
    )
    assert conflict_buyer.status_code == 409
    assert conflict_buyer.json()["error"]["code"] == "ERR_IDEMPOTENCY_CONFLICT"

    # 5. Seller transitions order to CONFIRMED and SHIPPED
    client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "CONFIRMED"},
    )
    client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "SHIPPED", "tracking_number": "TRK-IDEMP-001"},
    )

    # 6. Replay with original key and original payload returns 200 with current SHIPPED status
    replay_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": idemp_key},
        json=valid_body,
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["data"]["id"] == order_id
    assert replay_res.json()["data"]["status"] == "SHIPPED"
    assert replay_res.json()["data"]["tracking_number"] == "TRK-IDEMP-001"


def test_insufficient_stock_returns_409_and_preserves_inventory(
    client: TestClient, tracker_fixture
):
    """When stock is insufficient, checkout returns HTTP 409 and leaves inventory intact."""
    buyer_token = tracker_fixture["buyer_token"]
    buyer_hdr = {"Authorization": f"Bearer {buyer_token}"}
    prod_id = tracker_fixture["product_a_id"]

    # Set product A stock to 2
    with Session(engine) as session:
        prod = session.get(Product, prod_id)
        prod.stock_quantity = 2
        prod.version = 1
        session.commit()

    # Buyer puts 3 in cart
    with Session(engine) as session:
        session.add(CartItem(buyer_id=tracker_fixture["buyer_id"], product_id=prod_id, quantity=3))
        session.commit()

    # Attempt checkout with 3 items when only 2 in stock
    res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": "insufficient-stock-key-1"},
        json={
            "recipient_name": "Greedy Buyer",
            "delivery_address": "123 Shortage Way",
            "phone_number": "0912345678",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ERR_STOCK_EXCEEDED"

    # Verify stock remains exactly 2, cart item is preserved, 0 orders created
    with Session(engine) as session:
        check_prod = session.get(Product, prod_id)
        assert check_prod.stock_quantity == 2
        cart_items = session.exec(
            select(CartItem).where(CartItem.buyer_id == tracker_fixture["buyer_id"])
        ).all()
        assert len(cart_items) == 1
        orders = session.exec(
            select(Order).where(Order.buyer_id == tracker_fixture["buyer_id"])
        ).all()
        assert len(orders) == 0


def test_atomic_variant_stock_depletion_and_restoration(client: TestClient, tracker_fixture):
    """Variant stock is atomically deducted and restored on cancellation."""
    buyer_token = tracker_fixture["buyer_token"]
    buyer_hdr = {"Authorization": f"Bearer {buyer_token}"}
    seller_a_hdr = {"Authorization": f"Bearer {tracker_fixture['seller_a_token']}"}
    prod_id = tracker_fixture["product_a_id"]

    with Session(engine) as session:
        var = ProductVariant(
            product_id=prod_id,
            seller_id=tracker_fixture["seller_a_id"],
            sku="TRK-VAR-ATOMIC-1",
            name="Atomic Variant",
            price=120_000,
            stock_quantity=2,
            version=1,
            is_active=True,
        )
        session.add(var)
        session.commit()
        session.refresh(var)
        var_id = var.id

    # Buyer adds 2 of variant to cart
    client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": "TRK-A", "variant_id": var_id, "quantity": 2},
    )

    # Checkout variant items
    order_res = client.post(
        "/api/v1/orders",
        headers={**buyer_hdr, "Idempotency-Key": "atomic-variant-key-1"},
        json={
            "recipient_name": "Variant Buyer",
            "delivery_address": "456 Variant Lane",
            "phone_number": "0912345678",
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["data"]["id"]

    # Verify variant stock is now 0 in DB
    with Session(engine) as session:
        check_var = session.get(ProductVariant, var_id)
        assert check_var.stock_quantity == 0

    # Second buyer attempts to checkout the now-exhausted variant
    with Session(engine) as session:
        buyer2 = User(
            name="Second Variant Buyer",
            email="trk-buyer-var2@example.com",
            role="buyer",
            password_hash=hash_password("password"),
        )
        session.add(buyer2)
        session.flush()
        session.add(
            CartItem(buyer_id=buyer2.id, product_id=prod_id, variant_id=var_id, quantity=1)
        )
        session.commit()
        buyer2_token = create_access_token(buyer2)

    res_fail = client.post(
        "/api/v1/orders",
        headers={
            "Authorization": f"Bearer {buyer2_token}",
            "Idempotency-Key": "atomic-var-fail-key",
        },
        json={
            "recipient_name": "Buyer 2",
            "delivery_address": "Home",
            "phone_number": "0912345678",
        },
    )
    assert res_fail.status_code == 409
    assert res_fail.json()["error"]["code"] == "ERR_STOCK_EXCEEDED"

    # Seller cancels order 1 -> stock restored
    cancel_res = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "CANCELLED"},
    )
    assert cancel_res.status_code == 200

    with Session(engine) as session:
        restored_var = session.get(ProductVariant, var_id)
        assert restored_var.stock_quantity == 2

    # Attempting to cancel order 1 again fails and does not double-restore stock
    second_cancel = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers=seller_a_hdr,
        json={"status": "CANCELLED"},
    )
    assert second_cancel.status_code == 400
    assert second_cancel.json()["error"]["code"] == "ERR_INVALID_TRANSITION"

    with Session(engine) as session:
        still_two = session.get(ProductVariant, var_id)
        assert still_two.stock_quantity == 2


def test_concurrent_atomic_stock_depletion_three_buyers_for_single_unit(tmp_path):
    """When 3 buyers race for 1 unit, exactly 1 wins and 2 receive 409 without overselling."""
    from tests.cart_db import add_product, create_cart_engine
    test_db = create_cart_engine(tmp_path / "race_3way.db")

    add_product(test_db, "TRK-RACE-3WAY", stock=1)
    with Session(test_db) as session:
        prod = session.exec(select(Product).where(Product.code == "TRK-RACE-3WAY")).one()
        session.add(User(id=4, name="Buyer 3", email="buyer3@test.local", role="buyer"))
        session.commit()
        for b_id in (2, 3, 4):
            session.add(CartItem(buyer_id=b_id, product_id=prod.id, quantity=1))
        session.commit()

    body = CheckoutRequest(
        recipient_name="Winner",
        delivery_address="1 Finish Line",
        phone_number="0912345678",
    )

    results = []

    def run_race_checkout(buyer_id, key):
        with Session(test_db) as s:
            try:
                receipt_data, created = checkout(s, buyer_id, body, key)
                results.append((buyer_id, 201 if created else 200, None))
            except Exception as exc:
                results.append(
                    (buyer_id, getattr(exc, "status", 500), getattr(exc, "code", str(exc)))
                )

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run_race_checkout, b_id, f"race-3way-key-{i}")
            for i, b_id in enumerate((2, 3, 4))
        ]
        for f in futures:
            f.result()

    successes = [r for r in results if r[1] in (200, 201)]
    conflicts = [r for r in results if r[1] == 409]

    assert len(successes) == 1, f"Expected exactly 1 winner, got {results}"
    assert len(conflicts) == 2, f"Expected 2 conflicts, got {results}"

    with Session(test_db) as session:
        final_prod = session.exec(select(Product).where(Product.code == "TRK-RACE-3WAY")).one()
        assert final_prod.stock_quantity == 0


