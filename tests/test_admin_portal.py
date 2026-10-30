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
from src.models.product_variant import ProductVariant
from src.models.return_dispute import ReturnDispute
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher


@pytest.fixture
def portal_setup():
    """Seed clean state with an admin, seller, and buyer."""
    with Session(engine) as session:
        adm_users = session.exec(select(User.id).where(User.email.like("adm-%@example.com"))).all()
        session.exec(delete(ReturnDispute))
        session.exec(delete(ReturnRequest))
        session.exec(delete(AccountAuditLog))
        session.exec(delete(OrderHistory))
        session.exec(delete(Notification))
        session.exec(delete(OrderItem))
        session.exec(delete(SellerOrder))
        session.exec(delete(Order))
        session.exec(delete(CartItem))

        if adm_users:
            adm_prods = session.exec(
                select(Product.id).where(
                    Product.seller_id.in_(adm_users) | Product.code.like("ADM-%")
                )
            ).all()
            if adm_prods:
                session.exec(delete(ProductMetadata).where(ProductMetadata.product_id.in_(adm_prods)))
                session.exec(delete(ProductVariant).where(ProductVariant.product_id.in_(adm_prods)))
                session.exec(delete(Product).where(Product.id.in_(adm_prods)))
            session.exec(
                delete(Voucher).where(
                    Voucher.seller_id.in_(adm_users) | Voucher.code.like("ADM%")
                )
            )
        else:
            session.exec(
                delete(ProductMetadata).where(
                    ProductMetadata.product_id.in_(
                        select(Product.id).where(Product.code.like("ADM-%"))
                    )
                )
            )
            session.exec(
                delete(ProductVariant).where(
                    ProductVariant.product_id.in_(
                        select(Product.id).where(Product.code.like("ADM-%"))
                    )
                )
            )
            session.exec(delete(Product).where(Product.code.like("ADM-%")))
            session.exec(delete(Voucher).where(Voucher.code.like("ADM%")))

        session.exec(delete(Category).where(Category.slug.like("adm-%")))
        session.exec(delete(User).where(User.email.like("adm-%@example.com")))
        session.commit()

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

    # Normalize voucher timestamps with different offsets before storage (P2 regression)
    tz_res = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "ADMTZDIFF",
            "discount_type": "PERCENTAGE",
            "discount_value": 1000,
            "starts_at": "2026-10-29T15:00:00+07:00",
            "ends_at": "2026-10-29T09:00:00Z",
            "is_active": True,
        },
    )
    assert tz_res.status_code == 201
    tz_data = tz_res.json()
    assert tz_data["code"] == "ADMTZDIFF"

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


# ===========================================================================
# Regression Tests for Reviewer Feedback
# ===========================================================================

def test_seller_cannot_undo_admin_moderation_and_catalog_enforces_deactivation(
    client: TestClient, portal_setup
):
    """[P1] Sellers cannot override administrator moderation;
    catalog, cart, and checkout enforce it.
    """
    admin_hdr = _auth(portal_setup["admin_token"])
    seller_hdr = _auth(portal_setup["seller_token"])
    buyer_hdr = _auth(portal_setup["buyer_token"])

    # 1. Create a product as seller
    p_res = client.post(
        "/api/v1/seller/products",
        headers=seller_hdr,
        json={
            "name": "Moderation Target Keyboard",
            "description": "Will be moderated",
            "price": 500000,
            "stock_quantity": 10,
            "image_url": "https://example.com/keyboard.jpg",
        },
    )
    assert p_res.status_code == 201
    prod_id = p_res.json()["data"]["id"]
    prod_code = p_res.json()["data"]["code"]

    # Product is public
    cat_res = client.get(f"/api/v1/products/{prod_code}")
    assert cat_res.status_code == 200

    # 2. Administrator deactivates product for rules violation
    mod_res = client.patch(
        f"/api/v1/admin/products/{prod_id}/status",
        headers=admin_hdr,
        json={"is_active": False, "moderation_notes": "Violates safety policy"},
    )
    assert mod_res.status_code == 200
    assert mod_res.json()["is_active"] is False
    assert mod_res.json()["is_moderated_deactivated"] is True

    # 3. Seller attempts to reactivate product via PATCH -> 403 Forbidden
    seller_patch = client.patch(
        f"/api/v1/seller/products/{prod_id}",
        headers=seller_hdr,
        json={"is_active": True},
    )
    assert seller_patch.status_code == 403
    assert seller_patch.json()["error"]["code"] == "ERR_PRODUCT_MODERATED"

    # Seller attempts to edit name while keeping is_active True -> 403 Forbidden
    seller_put = client.put(
        f"/api/v1/seller/products/{prod_id}",
        headers=seller_hdr,
        json={"name": "Sneaky Name Change", "is_active": True},
    )
    assert seller_put.status_code == 403
    assert seller_put.json()["error"]["code"] == "ERR_PRODUCT_MODERATED"

    # 4. Catalog query excludes moderated product
    catalog_list = client.get("/api/v1/products?limit=100").json()
    assert prod_code not in [p["code"] for p in catalog_list["data"]]

    # Detail query returns 404
    assert client.get(f"/api/v1/products/{prod_code}").status_code == 404

    # 5. Cart addition is rejected
    cart_res = client.post(
        "/api/v1/cart/items",
        headers=buyer_hdr,
        json={"product_code": prod_code, "quantity": 1},
    )
    assert cart_res.status_code == 409
    assert cart_res.json()["error"]["code"] in ("ERR_PRODUCT_UNAVAILABLE", "ERR_UNAVAILABLE")

    # 6. Administrator reactivates product
    react_res = client.patch(
        f"/api/v1/admin/products/{prod_id}/status",
        headers=admin_hdr,
        json={"is_active": True, "moderation_notes": "Violation resolved"},
    )
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True
    assert react_res.json()["is_moderated_deactivated"] is False

    # Now seller can manage is_active again
    seller_deact = client.patch(
        f"/api/v1/seller/products/{prod_id}",
        headers=seller_hdr,
        json={"is_active": False},
    )
    assert seller_deact.status_code == 200
    assert seller_deact.json()["data"]["is_active"] is False


def test_account_restriction_enforced_across_order_status_and_return_decisions(
    client: TestClient, portal_setup
):
    """[P1] Account restrictions cannot be bypassed through mutation endpoints using CurrentUser."""
    admin_hdr = _auth(portal_setup["admin_token"])
    seller_hdr = _auth(portal_setup["seller_token"])
    buyer_hdr = _auth(portal_setup["buyer_token"])

    # Setup an order with sub-order
    with Session(engine) as session:
        prod = Product(
            code="ADM-RESTRICT-PROD",
            seller_id=portal_setup["seller_id"],
            name="Restricted Test Product",
            price=200000,
            stock_quantity=10,
            is_active=True,
        )
        session.add(prod)
        session.flush()

        order = Order(
            buyer_id=portal_setup["buyer_id"],
            status="DELIVERED",
            total_amount=200000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="DELIVERED",
            subtotal=200000,
        )
        session.add(so)
        session.flush()

        ret_req = ReturnRequest(
            order_id=order.id,  # type: ignore[arg-type]
            seller_order_id=so.id,  # type: ignore[arg-type]
            buyer_id=portal_setup["buyer_id"],
            reason="Item defective",
            evidence="Evidence link",
            status="PENDING",
        )
        session.add(ret_req)
        session.commit()
        ret_id = ret_req.id
        so_id = so.id
        ord_id = order.id

    # 1. Administrator restricts the seller
    restrict_seller = client.patch(
        f"/api/v1/admin/users/{portal_setup['seller_id']}/status",
        headers=admin_hdr,
        json={"status": "RESTRICTED", "reason": "Suspicious activity"},
    )
    assert restrict_seller.status_code == 200

    # Seller gets 403 on /seller/orders/{id}/status
    res_seller_order = client.patch(
        f"/api/v1/seller/orders/{so_id}/status",
        headers=seller_hdr,
        json={"status": "COMPLETED"},
    )
    assert res_seller_order.status_code == 403
    assert res_seller_order.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    # Seller also gets 403 on /orders/{id}/status (cannot bypass!)
    res_order_status = client.patch(
        f"/api/v1/orders/{ord_id}/status",
        headers=seller_hdr,
        json={"status": "COMPLETED"},
    )
    assert res_order_status.status_code == 403
    assert res_order_status.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    # Seller also gets 403 on return request decision
    res_return_decision = client.post(
        f"/api/v1/return-requests/{ret_id}/decision",
        headers=seller_hdr,
        json={"action": "APPROVE", "decision_notes": "Trying to approve while restricted"},
    )
    assert res_return_decision.status_code == 403
    assert res_return_decision.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    # 2. Administrator restricts the buyer
    restrict_buyer = client.patch(
        f"/api/v1/admin/users/{portal_setup['buyer_id']}/status",
        headers=admin_hdr,
        json={"status": "RESTRICTED", "reason": "Chargeback abuse"},
    )
    assert restrict_buyer.status_code == 200

    # Buyer cannot confirm delivery or cancel order
    res_confirm = client.post(f"/api/v1/orders/{ord_id}/confirm", headers=buyer_hdr)
    assert res_confirm.status_code == 403
    assert res_confirm.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    res_cancel = client.post(f"/api/v1/orders/{ord_id}/cancel", headers=buyer_hdr)
    assert res_cancel.status_code == 403
    assert res_cancel.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"

    res_return = client.post(
        f"/api/v1/orders/{ord_id}/returns",
        headers=buyer_hdr,
        json={"reason": "Cannot return while restricted"},
    )
    assert res_return.status_code == 403
    assert res_return.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"


def test_dispute_approval_settles_return_lifecycle_payment_escrow_and_atomic_claim(
    client: TestClient, portal_setup
):
    """[P1] Dispute decisions complete the existing return/refund lifecycle atomically."""
    admin_hdr = _auth(portal_setup["admin_token"])
    seller_hdr = _auth(portal_setup["seller_token"])

    with Session(engine) as session:
        prod = Product(
            code="ADM-DISP-SETTLE",
            seller_id=portal_setup["seller_id"],
            name="Settle Product",
            price=300000,
            stock_quantity=15,
            is_active=True,
        )
        session.add(prod)
        session.flush()

        order = Order(
            buyer_id=portal_setup["buyer_id"],
            status="RETURN_REQUESTED",
            payment_method="VIETQR",
            payment_status="PAID",
            escrow_status="PAUSED",
            total_amount=300000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="RETURN_REQUESTED",
            payment_status="PAID",
            escrow_status="PAUSED",
            subtotal=300000,
            total_amount=300000,
        )
        session.add(so)
        session.flush()

        item = OrderItem(
            order_id=order.id,  # type: ignore[arg-type]
            seller_order_id=so.id,  # type: ignore[arg-type]
            product_id=prod.id,  # type: ignore[arg-type]
            quantity=2,
            unit_price=150000,
            subtotal=300000,
        )
        session.add(item)
        session.flush()

        ret_req = ReturnRequest(
            order_id=order.id,  # type: ignore[arg-type]
            seller_order_id=so.id,  # type: ignore[arg-type]
            buyer_id=portal_setup["buyer_id"],
            reason="Damaged product",
            evidence="photo.jpg",
            status="PENDING",
        )
        session.add(ret_req)
        session.commit()
        ret_id = ret_req.id
        so_id = so.id
        ord_id = order.id

    # 1. Create dispute linking to sub-order with return request
    disp_res = client.post(
        f"/api/v1/admin/disputes?order_id={ord_id}&seller_order_id={so_id}&reason=Escalated+claim&evidence=docs.pdf",
        headers=admin_hdr,
    )
    assert disp_res.status_code == 201
    dispute_id = disp_res.json()["id"]
    assert disp_res.json()["return_request_id"] == ret_id

    # 2. Administrator adjudicates dispute as APPROVE with restock=True
    dec_res = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={
            "action": "APPROVE",
            "decision_notes": "Admin verified damage",
            "is_restockable": True,
        },
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["status"] == "APPROVED"

    # Verify atomic update on ReturnRequest
    with Session(engine) as session:
        updated_ret = session.get(ReturnRequest, ret_id)
        assert updated_ret.status == "APPROVED"
        assert updated_ret.decided_by_user_id == portal_setup["admin_id"]

        updated_so = session.get(SellerOrder, so_id)
        assert updated_so.status == "RETURNED_REFUNDED"
        assert updated_so.payment_status == "REFUNDED"
        assert updated_so.escrow_status == "VOIDED"  # US20 D5
        assert updated_so.refunded_amount == 300000

        updated_ord = session.get(Order, ord_id)
        assert updated_ord.status == "RETURNED_REFUNDED"
        assert updated_ord.payment_status == "REFUNDED"
        assert updated_ord.escrow_status == "VOIDED"

    # 3. Seller or anyone attempting to decide the ReturnRequest again fails with 400
    second_decision = client.post(
        f"/api/v1/return-requests/{ret_id}/decision",
        headers=seller_hdr,
        json={"action": "REJECT", "decision_notes": "Attempt double decision"},
    )
    assert second_decision.status_code == 400
    assert second_decision.json()["error"]["code"] == "ERR_INVALID_TRANSITION"

    # Deciding dispute again fails with 400
    second_dispute_decision = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={"action": "APPROVE", "decision_notes": "Again", "is_restockable": True},
    )
    assert second_dispute_decision.status_code == 400
    assert second_dispute_decision.json()["error"]["code"] == "ERR_DISPUTE_RESOLVED"


def test_variant_dispute_restores_variant_stock_unit_and_decrements_sales_count(
    client: TestClient, portal_setup
):
    """[P1] Variant returns restore stock to the variant inventory unit, not product base stock."""
    admin_hdr = _auth(portal_setup["admin_token"])

    with Session(engine) as session:
        prod = Product(
            code="ADM-VAR-PROD",
            seller_id=portal_setup["seller_id"],
            name="Variant Base Product",
            price=250000,
            stock_quantity=20,  # Base stock = 20
            is_active=True,
        )
        session.add(prod)
        session.flush()

        meta = ProductMetadata(
            product_id=prod.id,  # type: ignore[arg-type]
            sales_count=10,
        )
        session.add(meta)
        session.flush()

        variant = ProductVariant(
            product_id=prod.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            sku="ADM-VAR-SKU-1",
            name="Blue / Large",
            price=250000,
            stock_quantity=3,  # Variant stock = 3
            is_active=True,
        )
        session.add(variant)
        session.flush()

        order = Order(
            buyer_id=portal_setup["buyer_id"],
            status="DELIVERED",
            total_amount=500000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="DELIVERED",
            subtotal=500000,
        )
        session.add(so)
        session.flush()

        # Two-unit variant return
        item = OrderItem(
            order_id=order.id,  # type: ignore[arg-type]
            seller_order_id=so.id,  # type: ignore[arg-type]
            product_id=prod.id,  # type: ignore[arg-type]
            variant_id=variant.id,
            quantity=2,
            unit_price=250000,
            subtotal=500000,
        )
        session.add(item)
        session.commit()
        prod_id = prod.id
        var_id = variant.id
        ord_id = order.id
        so_id = so.id

    # Create and approve dispute with restock
    disp_res = client.post(
        f"/api/v1/admin/disputes?order_id={ord_id}&seller_order_id={so_id}&reason=Defect&evidence=pic.jpg",
        headers=admin_hdr,
    )
    assert disp_res.status_code == 201
    dispute_id = disp_res.json()["id"]

    approve_res = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=admin_hdr,
        json={"action": "APPROVE", "decision_notes": "Restocking variant", "is_restockable": True},
    )
    assert approve_res.status_code == 200

    # Verify inventory: variant stock increased by 2 (3 -> 5), base stock untouched (remains 20)
    with Session(engine) as session:
        p_db = session.get(Product, prod_id)
        v_db = session.get(ProductVariant, var_id)
        m_stmt = select(ProductMetadata).where(ProductMetadata.product_id == prod_id)
        m_db = session.exec(m_stmt).first()

        assert p_db.stock_quantity == 20, "Base product stock must not be incremented!"
        assert v_db.stock_quantity == 5, "Variant stock must increase from 3 to 5 (3 + 2)!"
        assert m_db.sales_count == 8, "Sales count must decrease by 2 (10 - 2)!"


def test_duplicate_disputes_prevented(client: TestClient, portal_setup):
    """[P1] Creating two disputes for the same sub-order is rejected with 409."""
    admin_hdr = _auth(portal_setup["admin_token"])

    with Session(engine) as session:
        prod = Product(
            code="ADM-DUP-PROD",
            seller_id=portal_setup["seller_id"],
            name="Dup Product",
            price=100000,
            stock_quantity=5,
            is_active=True,
        )
        session.add(prod)
        session.flush()

        order = Order(
            buyer_id=portal_setup["buyer_id"],
            status="DELIVERED",
            total_amount=100000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order)
        session.flush()

        so = SellerOrder(
            order_id=order.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="DELIVERED",
            subtotal=100000,
        )
        session.add(so)
        session.commit()
        ord_id = order.id
        so_id = so.id

    # 1. First dispute succeeds -> 201
    r1 = client.post(
        f"/api/v1/admin/disputes?order_id={ord_id}&seller_order_id={so_id}&reason=First+claim&evidence=e1",
        headers=admin_hdr,
    )
    assert r1.status_code == 201

    # 2. Second dispute on same sub-order is rejected -> 409 Conflict
    r2 = client.post(
        f"/api/v1/admin/disputes?order_id={ord_id}&seller_order_id={so_id}&reason=Second+claim&evidence=e2",
        headers=admin_hdr,
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "ERR_DISPUTE_EXISTS"


def test_dispute_creation_validates_order_hierarchy_and_permitted_states(
    client: TestClient, portal_setup
):
    """[P1] Dispute creation rejects mismatched parent-child orders and invalid sub-order states."""
    admin_hdr = _auth(portal_setup["admin_token"])

    with Session(engine) as session:
        # Order A
        order_a = Order(
            buyer_id=portal_setup["buyer_id"],
            status="DELIVERED",
            total_amount=100000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order_a)
        # Order B
        order_b = Order(
            buyer_id=portal_setup["buyer_id"],
            status="CANCELLED",
            total_amount=100000,
            delivery_address="123 Test St",
            recipient_name="Buyer",
            phone_number="0901234567",
        )
        session.add(order_b)
        session.flush()

        so_a = SellerOrder(
            order_id=order_a.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="DELIVERED",
            subtotal=100000,
        )
        session.add(so_a)

        so_b = SellerOrder(
            order_id=order_b.id,  # type: ignore[arg-type]
            seller_id=portal_setup["seller_id"],
            status="CANCELLED",
            subtotal=100000,
        )
        session.add(so_b)
        session.commit()
        ord_b_id = order_b.id
        so_a_id = so_a.id
        so_b_id = so_b.id

    # 1. Mismatched order and sub-order (order B with sub-order A) -> 400
    res_mismatch = client.post(
        f"/api/v1/admin/disputes?order_id={ord_b_id}&seller_order_id={so_a_id}&reason=Mismatch&evidence=e",
        headers=admin_hdr,
    )
    assert res_mismatch.status_code == 400
    assert res_mismatch.json()["error"]["code"] == "ERR_SUB_ORDER_MISMATCH"

    # 2. Cancelled sub-order -> 400 (cannot reset cancelled order to RETURN_REQUESTED)
    res_invalid_state = client.post(
        f"/api/v1/admin/disputes?order_id={ord_b_id}&seller_order_id={so_b_id}&reason=Invalid&evidence=e",
        headers=admin_hdr,
    )
    assert res_invalid_state.status_code == 400
    assert res_invalid_state.json()["error"]["code"] == "ERR_INVALID_DISPUTE_STATE"


def test_update_voucher_expiry_with_timezone_aware_timestamp(client: TestClient, portal_setup):
    """[P2] Updating voucher expiry with timezone-aware timestamp does not raise 500."""
    admin_hdr = _auth(portal_setup["admin_token"])

    # 1. Create a platform voucher
    v_res = client.post(
        "/api/v1/admin/vouchers",
        headers=admin_hdr,
        json={
            "code": "ADMTZTEST",
            "discount_type": "PERCENTAGE",
            "discount_value": 1500,
            "min_order_value": 100000,
            "starts_at": "2026-10-01T00:00:00Z",
            "ends_at": "2026-11-01T00:00:00Z",
        },
    )
    assert v_res.status_code == 201
    voucher_id = v_res.json()["id"]

    # 2. Update ends_at with a timezone-aware timestamp with offset (+07:00)
    update_res = client.patch(
        f"/api/v1/admin/vouchers/{voucher_id}",
        headers=admin_hdr,
        json={"ends_at": "2026-12-31T23:59:59+07:00"},
    )
    assert update_res.status_code == 200
    assert "2026-12-31" in update_res.json()["ends_at"]


def test_category_validation_normalizes_whitespace_before_length_and_slug_check(
    client: TestClient, portal_setup
):
    """[P2] Category validation strips whitespace before length and slug regex check."""
    admin_hdr = _auth(portal_setup["admin_token"])

    # Whitespace-only name and slug -> 422
    r1 = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "   ", "slug": "   "},
    )
    assert r1.status_code == 422

    # Invalid slug pattern -> 422
    r2 = client.post(
        "/api/v1/admin/categories",
        headers=admin_hdr,
        json={"name": "Electronics Item", "slug": "Invalid Slug!"},
    )
    assert r2.status_code == 422


def test_seller_inventory_endpoint_returns_active_and_moderated_products(
    client: TestClient, portal_setup
):
    """[P2] GET /api/v1/seller/inventory returns seller listings with accurate moderation status."""
    admin_hdr = _auth(portal_setup["admin_token"])
    seller_hdr = _auth(portal_setup["seller_token"])

    # Create 2 products
    p1 = client.post(
        "/api/v1/seller/products",
        headers=seller_hdr,
        json={
            "name": "Active Listing",
            "description": "Active",
            "price": 100000,
            "stock_quantity": 5,
            "image_url": "https://example.com/p1.jpg",
        },
    ).json()["data"]

    p2 = client.post(
        "/api/v1/seller/products",
        headers=seller_hdr,
        json={
            "name": "Deactivated Listing",
            "description": "To be deactivated",
            "price": 200000,
            "stock_quantity": 2,
            "image_url": "https://example.com/p2.jpg",
        },
    ).json()["data"]

    # Deactivate p2 via admin moderation
    client.patch(
        f"/api/v1/admin/products/{p2['id']}/status",
        headers=admin_hdr,
        json={"is_active": False, "moderation_notes": "Policy violation"},
    )

    # Fetch seller inventory via authenticated endpoint
    inv_res = client.get("/api/v1/seller/inventory", headers=seller_hdr)
    assert inv_res.status_code == 200
    data = inv_res.json()["data"]
    items = {item["id"]: item for item in data}

    assert p1["id"] in items
    assert items[p1["id"]]["is_active"] is True
    assert items[p1["id"]]["is_moderated_deactivated"] is False

    assert p2["id"] in items
    assert items[p2["id"]]["is_active"] is False
    assert items[p2["id"]]["is_moderated_deactivated"] is True

