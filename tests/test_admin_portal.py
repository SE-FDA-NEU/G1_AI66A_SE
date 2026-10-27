"""Comprehensive tests for Platform Admin Portal (P1 Story).

Verifies category policy, platform vouchers, catalog moderation, account moderation,
return dispute adjudication, and strict security/authorization.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, delete, select
from starlette.testclient import TestClient

from src.auth import create_access_token, hash_password
from src.database import engine
from src.models.account_audit_log import AccountAuditLog
from src.models.cart_item import CartItem
from src.models.category import Category
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.return_dispute import ReturnDispute
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher


@pytest.fixture
def portal_setup():
    """Seed clean state with an admin, seller, and buyer."""
    with Session(engine) as session:
        session.exec(delete(ReturnDispute))
        session.exec(delete(AccountAuditLog))
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(CartItem))
        session.exec(delete(ProductMetadata))
        session.exec(delete(Product).where(Product.code.like("ADM-%")))
        session.exec(delete(Category).where(Category.slug.like("adm-%")))
        session.exec(delete(Voucher).where(Voucher.code.like("ADM%")))
        session.exec(delete(User).where(User.email.like("adm-%@example.com")))

        admin = User(
            name="Platform SuperAdmin",
            email="adm-admin@example.com",
            role="admin",
            status="ACTIVE",
            password_hash=hash_password("adminpass"),
        )
        seller = User(
            name="Admin Test Seller",
            email="adm-seller@example.com",
            role="seller",
            status="ACTIVE",
            password_hash=hash_password("sellerpass"),
        )
        buyer = User(
            name="Admin Test Buyer",
            email="adm-buyer@example.com",
            role="buyer",
            status="ACTIVE",
            password_hash=hash_password("buyerpass"),
        )
        session.add_all([admin, seller, buyer])
        session.commit()
        session.refresh(admin)
        session.refresh(seller)
        session.refresh(buyer)

        # Create a test product
        product = Product(
            code="ADM-P1",
            seller_id=seller.id,
            name="Admin Mod Product",
            description="Product subject to moderation",
            price=250_000,
            stock_quantity=20,
            is_active=True,
            version=1,
        )
        session.add(product)
        session.commit()
        session.refresh(product)

        # Create product metadata
        meta = ProductMetadata(
            product_id=product.id,
            rating=5.0,
            review_count=1,
            sales_count=0,
        )
        session.add(meta)
        session.commit()

        admin_token = create_access_token(admin)
        seller_token = create_access_token(seller)
        buyer_token = create_access_token(buyer)
        admin_id = admin.id
        seller_id = seller.id
        buyer_id = buyer.id
        product_id = product.id
        product_code = product.code

        session.expunge_all()

        return {
            "admin": admin,
            "seller": seller,
            "buyer": buyer,
            "admin_id": admin_id,
            "seller_id": seller_id,
            "buyer_id": buyer_id,
            "admin_token": admin_token,
            "seller_token": seller_token,
            "buyer_token": buyer_token,
            "product_id": product_id,
            "product_code": product_code,
        }


def _auth(target: User | str) -> dict[str, str]:
    if isinstance(target, str):
        return {"Authorization": f"Bearer {target}"}
    return {"Authorization": f"Bearer {create_access_token(target)}"}


# ===========================================================================
# AC 1: Category & Voucher Administration
# ===========================================================================
def test_admin_category_management_and_validation(client: TestClient, portal_setup):
    """Admin can create, update, prevent cycle, and delete categories."""
    admin_hdr = _auth(portal_setup["admin_token"])

    # Create root category
    c1_res = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "Admin Electronics", "slug": "adm-electronics", "parent_id": None},
    )
    assert c1_res.status_code == 201
    c1_data = c1_res.json()
    c1_id = c1_data["id"]

    # Prevent duplicate slug
    dup_res = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "Duplicate Electronics", "slug": "adm-electronics"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "ERR_CATEGORY_EXISTS"

    # Create child category
    c2_res = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "Admin Headphones", "slug": "adm-headphones", "parent_id": c1_id},
    )
    assert c2_res.status_code == 201
    c2_id = c2_res.json()["id"]

    # Reject non-existent parent
    invalid_parent = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "Broken", "slug": "adm-broken", "parent_id": 999999},
    )
    assert invalid_parent.status_code == 400
    assert invalid_parent.json()["error"]["code"] == "ERR_PARENT_NOT_FOUND"

    # Update category & reject self-parent cycle
    self_parent = client.put(
        f"/api/v1/admin/categories/{c1_id}",
        headers=admin_hdr,
        json={"parent_id": c1_id},
    )
    assert self_parent.status_code == 400
    assert self_parent.json()["error"]["code"] == "ERR_CATEGORY_CYCLE"

    # Reject moving parent under descendant
    descendant_cycle = client.put(
        f"/api/v1/admin/categories/{c1_id}",
        headers=admin_hdr,
        json={"parent_id": c2_id},
    )
    assert descendant_cycle.status_code == 400
    assert descendant_cycle.json()["error"]["code"] == "ERR_CATEGORY_CYCLE"

    # Valid update
    upd_res = client.put(
        f"/api/v1/admin/categories/{c2_id}",
        headers=admin_hdr,
        json={"name": "Premium Headphones"},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Premium Headphones"

    # List categories
    list_res = client.get("/api/v1/admin/categories", headers=admin_hdr)
    assert list_res.status_code == 200
    slugs = [c["slug"] for c in list_res.json()]
    assert "adm-electronics" in slugs
    assert "adm-headphones" in slugs

    # Delete category
    del_res = client.delete(f"/api/v1/admin/categories/{c2_id}", headers=admin_hdr)
    assert del_res.status_code == 204


def test_admin_platform_voucher_management(client: TestClient, portal_setup):
    """Admin can create, validate, and update platform vouchers."""
    admin_hdr = _auth(portal_setup["admin_token"])
    now = datetime.now(UTC)
    starts = (now - timedelta(days=1)).isoformat()
    ends = (now + timedelta(days=30)).isoformat()

    # Create percentage platform voucher
    v_res = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "ADMPLAT10",
            "discount_type": "PERCENTAGE",
            "discount_value": 1000,  # 10%
            "max_discount": 50_000,
            "min_order_value": 200_000,
            "usage_limit": 100,
            "per_user_limit": 2,
            "starts_at": starts,
            "ends_at": ends,
            "is_active": True,
        },
    )
    assert v_res.status_code == 201
    v_data = v_res.json()
    assert v_data["code"] == "ADMPLAT10"
    assert v_data["scope"] == "PLATFORM"
    v_id = v_data["id"]

    # Reject duplicate code
    dup = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "admplat10",  # uppercase normalization collision
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 20000,
            "starts_at": starts,
            "ends_at": ends,
        },
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ERR_VOUCHER_EXISTS"

    # Reject invalid date window (ends before starts)
    inv_date = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "ADMBADDATE",
            "discount_type": "PERCENTAGE",
            "discount_value": 500,
            "starts_at": ends,
            "ends_at": starts,
        },
    )
    assert inv_date.status_code == 400
    assert inv_date.json()["error"]["code"] == "ERR_INVALID_DATES"

    # Reject invalid percentage value (> 10000 bps)
    inv_pct = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "ADMBADPCT",
            "discount_type": "PERCENTAGE",
            "discount_value": 20000,
            "starts_at": starts,
            "ends_at": ends,
        },
    )
    assert inv_pct.status_code == 400
    assert inv_pct.json()["error"]["code"] == "ERR_INVALID_DISCOUNT"

    # Update voucher status
    upd_res = client.patch(
        f"/api/v1/admin/vouchers/{v_id}",
        headers=admin_hdr,
        json={"is_active": False},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["is_active"] is False

    # List vouchers
    list_res = client.get("/api/v1/admin/vouchers", headers=admin_hdr)
    assert list_res.status_code == 200
    codes = [v["code"] for v in list_res.json()]
    assert "ADMPLAT10" in codes


# ===========================================================================
# AC 2: Product Moderation & Sale Restriction
# ===========================================================================
def test_admin_product_moderation_removes_from_sale(client: TestClient, portal_setup):
    """Deactivating a product removes it from catalog and prevents cart additions."""
    admin_hdr = _auth(portal_setup["admin_token"])
    buyer_hdr = _auth(portal_setup["buyer_token"])
    p_id = portal_setup["product_id"]
    p_code = portal_setup["product_code"]

    # Initially active: product is in catalog
    cat_res = client.get(f"/api/v1/products?search={p_code}")
    assert cat_res.status_code == 200
    assert any(p["code"] == p_code for p in cat_res.json()["data"])

    # Admin reviews and deactivates product for violation
    mod_res = client.patch(
        f"/api/v1/admin/products/{p_id}/status",
        headers=admin_hdr,
        json={"is_active": False, "moderation_notes": "Violates marketplace listing rules"},
    )
    assert mod_res.status_code == 200
    assert mod_res.json()["is_active"] is False

    # Product is no longer offered in public catalog
    cat_after = client.get(f"/api/v1/products?search={p_code}")
    assert cat_after.status_code == 200
    assert not any(p["code"] == p_code for p in cat_after.json()["data"])

    # Direct detail lookup returns 404
    detail_res = client.get(f"/api/v1/products/{p_code}")
    assert detail_res.status_code == 404

    # Adding to cart is refused with PRODUCT_UNAVAILABLE
    cart_res = client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": p_code, "quantity": 1},
    )
    assert cart_res.status_code == 409
    assert cart_res.json()["error"]["code"] == "ERR_PRODUCT_UNAVAILABLE"

    # Admin reactivates product
    react_res = client.patch(
        f"/api/v1/admin/products/{p_id}/status",
        headers=admin_hdr,
        json={"is_active": True},
    )
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True

    # Product reappears in catalog
    cat_react = client.get(f"/api/v1/products?search={p_code}")
    assert any(p["code"] == p_code for p in cat_react.json()["data"])


# ===========================================================================
# AC 3: Account Status Management & Enforcement
# ===========================================================================
def test_admin_user_account_moderation_and_enforcement(client: TestClient, portal_setup):
    """Admin changes account status, audit log is written, and restricted accounts are blocked."""
    admin_hdr = _auth(portal_setup["admin_token"])
    seller_id = portal_setup["seller_id"]
    buyer_id = portal_setup["buyer_id"]
    admin_id = portal_setup["admin_id"]

    # 1. Suspend Seller
    mod_seller = client.patch(
        f"/api/v1/admin/users/{seller_id}/status",
        headers=admin_hdr,
        json={"status": "SUSPENDED", "reason": "Unfulfilled customer orders"},
    )
    assert mod_seller.status_code == 200
    assert mod_seller.json()["status"] == "SUSPENDED"

    # Verify audit log was recorded
    with Session(engine) as session:
        logs = session.exec(
            select(AccountAuditLog).where(AccountAuditLog.user_id == seller_id)
        ).all()
        assert len(logs) == 1
        assert logs[0].admin_id == admin_id
        assert logs[0].old_status == "ACTIVE"
        assert logs[0].new_status == "SUSPENDED"
        assert logs[0].reason == "Unfulfilled customer orders"

    # Suspended seller cannot create listings
    seller_hdr = _auth(portal_setup["seller_token"])
    create_p = client.post(
        "/api/v1/seller/products",
        headers=seller_hdr,
        json={
            "code": "ADM-FAIL",
            "name": "Should Fail",
            "price": 100_000,
            "stock_quantity": 10,
        },
    )
    assert create_p.status_code == 403
    assert create_p.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    # 2. Suspend Buyer
    mod_buyer = client.patch(
        f"/api/v1/admin/users/{buyer_id}/status",
        headers=admin_hdr,
        json={"status": "RESTRICTED", "reason": "Payment dispute escalation"},
    )
    assert mod_buyer.status_code == 200
    assert mod_buyer.json()["status"] == "RESTRICTED"

    # Restricted buyer cannot perform cart actions
    buyer_hdr = _auth(portal_setup["buyer_token"])
    cart_act = client.get("/api/v1/cart", headers=buyer_hdr)
    assert cart_act.status_code == 403
    assert cart_act.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    # 3. Self-moderation check: Admin cannot suspend themselves
    self_mod = client.patch(
        f"/api/v1/admin/users/{admin_id}/status",
        headers=admin_hdr,
        json={"status": "SUSPENDED", "reason": "Self test"},
    )
    assert self_mod.status_code == 400
    assert self_mod.json()["error"]["code"] == "ERR_SELF_MODERATION"


# ===========================================================================
# AC 4: Dispute Adjudication Workflow
# ===========================================================================
def test_admin_return_dispute_approval_and_restock(client: TestClient, portal_setup):
    """Admin approves dispute: order transitions to RETURNED_REFUNDED, stock restores."""
    admin_hdr = _auth(portal_setup["admin_token"])
    buyer_id = portal_setup["buyer_id"]
    seller_id = portal_setup["seller_id"]
    admin_id = portal_setup["admin_id"]
    product_id = portal_setup["product_id"]

    # Create delivered order & seller order
    with Session(engine) as session:
        order = Order(
            buyer_id=buyer_id,
            total_amount=500_000,
            status="DELIVERED",
            recipient_name="Buyer",
            delivery_address="123 Admin Way",
            phone_number="0987654321",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,
            seller_id=seller_id,
            status="DELIVERED",
        )
        session.add(so)
        session.flush()

        item = OrderItem(
            seller_order_id=so.id,
            product_id=product_id,
            quantity=2,
            unit_price=250_000,
        )
        session.add(item)
        session.commit()
        order_id = order.id
        so_id = so.id

    # Create dispute / escalation
    disp_res = client.post(
        f"/api/v1/admin/disputes?order_id={order_id}&seller_order_id={so_id}"
        "&reason=Item damaged in transit&evidence=Photos uploaded",
        headers=admin_hdr,
    )
    assert disp_res.status_code == 201
    dispute_id = disp_res.json()["id"]

    # Verify sub-order transitions to RETURN_REQUESTED
    with Session(engine) as session:
        so_db = session.get(SellerOrder, so_id)
        assert so_db.status == "RETURN_REQUESTED"

    # Admin approves dispute with restocking
    dec_res = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={
            "action": "APPROVE",
            "decision_notes": "Photos verify transit damage. Refund approved.",
            "is_restockable": True,
        },
    )
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["status"] == "APPROVED"
    assert dec_data["decided_by_user_id"] == admin_id
    assert dec_data["decided_at"] is not None

    # Verify side effects: sub-order RETURNED_REFUNDED, stock restored
    with Session(engine) as session:
        so_after = session.get(SellerOrder, so_id)
        assert so_after.status == "RETURNED_REFUNDED"

        order_after = session.get(Order, order_id)
        assert order_after.status == "RETURNED_REFUNDED"

        prod_after = session.get(Product, product_id)
        # Initial was 20, item quantity was 2 -> 22
        assert prod_after.stock_quantity == 22
        assert prod_after.version == 2

    # Attempting to decide resolved dispute returns 400
    dec_again = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={"action": "REJECT", "decision_notes": "Second try"},
    )
    assert dec_again.status_code == 400
    assert dec_again.json()["error"]["code"] == "ERR_DISPUTE_RESOLVED"


def test_admin_return_dispute_rejection(client: TestClient, portal_setup):
    """Admin rejects dispute: order transitions to COMPLETED."""
    admin_hdr = _auth(portal_setup["admin_token"])
    buyer_id = portal_setup["buyer_id"]
    seller_id = portal_setup["seller_id"]

    with Session(engine) as session:
        order = Order(
            buyer_id=buyer_id,
            total_amount=250_000,
            status="DELIVERED",
            recipient_name="Buyer",
            delivery_address="123 Street",
            phone_number="0987654321",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,
            seller_id=seller_id,
            status="DELIVERED",
        )
        session.add(so)
        session.commit()
        order_id = order.id
        so_id = so.id

    disp_res = client.post(
        f"/api/v1/admin/disputes?order_id={order_id}&seller_order_id={so_id}"
        "&reason=Customer change of mind&evidence=None",
        headers=admin_hdr,
    )
    dispute_id = disp_res.json()["id"]

    dec_res = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={"action": "REJECT", "decision_notes": "Return window expired per store policy."},
    )
    assert dec_res.status_code == 200

    with Session(engine) as session:
        so_after = session.get(SellerOrder, so_id)
        assert so_after.status == "COMPLETED"

        order_after = session.get(Order, order_id)
        assert order_after.status == "COMPLETED"


# ===========================================================================
# AC 5: Direct Endpoint Access by Non-Admins is Rejected
# ===========================================================================
@pytest.mark.parametrize("route,method", [
    ("/api/v1/admin/categories", "GET"),
    ("/api/v1/admin/categories", "POST"),
    ("/api/v1/admin/vouchers", "GET"),
    ("/api/v1/admin/vouchers", "POST"),
    ("/api/v1/admin/users", "GET"),
    ("/api/v1/admin/products", "GET"),
    ("/api/v1/admin/disputes", "GET"),
])
def test_non_admin_calls_to_admin_endpoints_rejected(
    client: TestClient, portal_setup, route, method
):
    """Direct calls to any admin endpoint by guests, buyers, or sellers are rejected."""
    # 1. Unauthenticated guest -> 401
    guest_res = client.request(method, route, json={})
    assert guest_res.status_code == 401
    assert guest_res.json()["error"]["code"] == "ERR_AUTH_REQUIRED"

    # 2. Buyer account -> 403
    buyer_hdr = _auth(portal_setup["buyer_token"])
    buyer_res = client.request(method, route, headers=buyer_hdr, json={})
    assert buyer_res.status_code == 403
    assert buyer_res.json()["error"]["code"] == "ERR_ADMIN_REQUIRED"

    # 3. Seller account -> 403
    seller_hdr = _auth(portal_setup["seller_token"])
    seller_res = client.request(method, route, headers=seller_hdr, json={})
    assert seller_res.status_code == 403
    assert seller_res.json()["error"]["code"] == "ERR_ADMIN_REQUIRED"


# ===========================================================================
# Web Route Tests
# ===========================================================================
def test_admin_portal_and_seller_products_pages_served(client: TestClient):
    """Admin portal and seller products HTML pages are served correctly."""
    r1 = client.get("/admin")
    assert r1.status_code == 200
    assert "Platform Admin Portal" in r1.text

    r2 = client.get("/admin/portal")
    assert r2.status_code == 200

    r3 = client.get("/seller/products")
    assert r3.status_code == 200
    assert "My Store Products" in r3.text
