"""Focused gaps in the existing #151 admin backend, on isolated SQLite files."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select
from starlette.testclient import TestClient

import src.database as database
from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.account_audit_log import AccountAuditLog
from src.models.category import Category
from src.models.category_audit_log import CategoryAuditLog
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.payment_event import PaymentEvent
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.return_dispute import ReturnDispute
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from src.repositories import admin_disputes as dispute_repository
from src.services import admin_disputes, payments, returns
from src.services.payments import record_payment_result, start_payment
from tests.cart_db import BUYER_ID, SELLER_ID, create_cart_engine

ADMIN_ID = 4


@pytest.fixture
def backend(tmp_path, request):
    payment = getattr(request, "param", "PAID")
    engine = create_cart_engine(tmp_path / "admin151.db")
    with Session(engine) as session:
        session.add(User(id=ADMIN_ID, name="Admin", email="admin@test.local", role="admin"))
        product = Product(
            code="ADMIN-151",
            seller_id=SELLER_ID,
            name="Test product",
            price=100000,
            stock_quantity=8,
        )
        session.add(product)
        session.flush()
        session.add(ProductMetadata(product_id=product.id, sales_count=2))
        order = Order(
            buyer_id=BUYER_ID,
            total_amount=200000,
            status="DELIVERED",
            recipient_name="Buyer",
            delivery_address="Test street",
            phone_number="0912345678",
            payment_status="PAID" if payment == "LEGACY" else "UNPAID",
        )
        session.add(order)
        session.flush()
        shop = SellerOrder(
            order_id=order.id,
            seller_id=SELLER_ID,
            status="DELIVERED",
            subtotal=200000,
            total_amount=200000,
            payment_status="PAID" if payment == "LEGACY" else "UNPAID",
        )
        session.add(shop)
        session.flush()
        session.add(
            OrderItem(seller_order_id=shop.id, product_id=product.id, quantity=2, unit_price=100000)
        )
        if payment != "LEGACY":
            start_payment(session, order, [shop], "VIETQR")
            if payment != "UNPAID":
                record_payment_result(
                    session, order.id, payment, "DEMO_OPERATOR", "fixture-payment", ADMIN_ID
                )
        session.commit()
        ids = {"order": order.id, "shop": shop.id, "product": product.id}
        tokens = {
            user_id: {"Authorization": f"Bearer {create_access_token(session.get(User, user_id))}"}
            for user_id in (SELLER_ID, BUYER_ID, ADMIN_ID)
        }
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, engine, ids, tokens
    engine.dispose()


def open_dispute(backend, **changes):
    client, _, ids, tokens = backend
    return client.post(
        "/api/v1/admin/disputes",
        headers=tokens[ADMIN_ID],
        params={
            "order_id": ids["order"],
            "seller_order_id": ids["shop"],
            "reason": "Damaged product",
            "evidence": "photo.jpg",
            **changes,
        },
    )


def test_escalation_pauses_escrow_and_records_authenticated_actor(backend):
    _, engine, ids, _ = backend

    response = open_dispute(backend)

    assert response.status_code == 201, response.text
    assert response.json()["created_by_user_id"] == ADMIN_ID
    with Session(engine) as session:
        shop = session.get(SellerOrder, ids["shop"])
        order = session.get(Order, ids["order"])
        assert (shop.status, shop.escrow_status) == ("RETURN_REQUESTED", "PAUSED")
        assert (order.status, order.escrow_status) == ("RETURN_REQUESTED", "PAUSED")
        [event] = session.exec(select(OrderHistory)).all()
        assert (event.from_status, event.to_status, event.changed_by_user_id, event.actor_role) == (
            "DELIVERED",
            "RETURN_REQUESTED",
            ADMIN_ID,
            "admin",
        )
        dispute = session.exec(select(ReturnDispute)).one()
        assert dispute.created_at == event.created_at


def test_category_changes_record_before_after_and_keep_delete_audit(backend):
    client, engine, _, tokens = backend
    owner = tokens[ADMIN_ID]
    created = client.post(
        "/api/v1/admin/categories", headers=owner, json={"name": "Root", "slug": "admin151-root"}
    )
    assert created.status_code == 201
    category_id = created.json()["id"]
    assert (
        client.put(
            f"/api/v1/admin/categories/{category_id}", headers=owner, json={"name": "Renamed"}
        ).status_code
        == 200
    )
    assert (
        client.delete(f"/api/v1/admin/categories/{category_id}", headers=owner).status_code == 204
    )
    assert inspect(engine).has_table("category_audit_logs")
    response = client.get("/api/v1/admin/category-audits", headers=owner)
    assert response.status_code == 200
    events = list(reversed(response.json()))
    assert [row["action"] for row in events] == ["CREATE", "UPDATE", "DELETE"]
    assert all(row["admin_id"] == ADMIN_ID and row["category_id"] == category_id for row in events)
    assert events[0]["before"] is None
    assert events[1]["before"]["name"] == "Root"
    assert events[1]["after"]["name"] == "Renamed"
    assert events[2]["before"]["name"] == "Renamed" and events[2]["after"] is None


def persisted_state(backend):
    _, engine, _, _ = backend
    models = (
        User,
        Category,
        CategoryAuditLog,
        AccountAuditLog,
        Product,
        ProductMetadata,
        ProductVariant,
        Order,
        SellerOrder,
        OrderItem,
        ReturnRequest,
        ReturnDispute,
        OrderHistory,
        Notification,
        PaymentEvent,
    )
    with Session(engine) as session:
        return {
            model.__tablename__: [
                row.model_dump()
                for row in session.exec(select(model).order_by(*model.__table__.primary_key))
            ]
            for model in models
        }


def decide(backend, dispute_id, **body):
    client, _, _, tokens = backend
    return client.post(
        f"/api/v1/admin/disputes/{dispute_id}/decision",
        headers=tokens[ADMIN_ID],
        json={"action": "APPROVE", **body},
    )


def submit_buyer_return(backend):
    client, _, ids, tokens = backend
    response = client.post(
        f"/api/v1/orders/{ids['order']}/returns",
        headers=tokens[BUYER_ID],
        json={"seller_order_id": ids["shop"], "reason": "Damaged", "evidence": "photo.jpg"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


@pytest.mark.parametrize("actor", [None, BUYER_ID, SELLER_ID])
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/admin/category-audits", None),
        ("POST", "/api/v1/admin/categories", {"name": "Denied", "slug": "denied"}),
        ("POST", "/api/v1/categories", {"name": "Denied", "slug": "denied"}),
        ("PATCH", "/api/v1/admin/users/2/status", {"status": "SUSPENDED"}),
        ("GET", "/api/v1/admin/users", None),
        ("POST", "/api/v1/admin/disputes", None),
        ("GET", "/api/v1/admin/disputes", None),
        ("POST", "/api/v1/admin/disputes/1/decision", {"action": "APPROVE"}),
    ],
)
def test_admin_workflow_rejects_direct_non_admin_requests(backend, actor, method, path, body):
    client, _, _, tokens = backend
    before = persisted_state(backend)

    response = client.request(method, path, json=body, headers=tokens.get(actor, {}))

    assert response.status_code == (401 if actor is None else 403), response.text
    assert response.json()["error"]["code"] == (
        "ERR_AUTH_REQUIRED" if actor is None else "ERR_ADMIN_REQUIRED"
    )
    assert persisted_state(backend) == before


@pytest.mark.parametrize("status", ["RESTRICTED", "SUSPENDED"])
def test_admin_role_does_not_bypass_current_account_status(backend, status):
    client, engine, _, tokens = backend
    with Session(engine) as session:
        admin = session.get(User, ADMIN_ID)
        admin.status = status
        session.add(admin)
        session.commit()
    before = persisted_state(backend)

    response = client.get("/api/v1/admin/category-audits", headers=tokens[ADMIN_ID])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"
    assert persisted_state(backend) == before


@pytest.mark.parametrize("prefix", ["/api/v1/categories", "/api/v1/admin/categories"])
def test_both_category_routes_write_audits_and_reject_invalid_changes(backend, prefix):
    client, engine, _, tokens = backend
    owner = tokens[ADMIN_ID]
    response = client.post(prefix, headers=owner, json={"name": "Root", "slug": "root"})
    assert response.status_code == 201, response.text
    category_id = response.json()["id"]
    # A no-op is not another administrative change.
    method = "PATCH" if prefix == "/api/v1/categories" else "PUT"
    same = client.request(method, f"{prefix}/{category_id}", headers=owner, json={"name": "Root"})
    assert same.status_code == 200
    with Session(engine) as session:
        assert len(session.exec(select(CategoryAuditLog)).all()) == 1
    before = persisted_state(backend)
    for body in ({"parent_id": category_id}, {"name": "   "}, {"admin_id": 2}):
        response = client.request(method, f"{prefix}/{category_id}", headers=owner, json=body)
        assert response.status_code in (400, 422), response.text
        assert persisted_state(backend) == before
    duplicate = client.post(prefix, headers=owner, json={"name": "Other", "slug": "root"})
    assert duplicate.status_code == 409
    assert persisted_state(backend) == before
    deleted = client.delete(f"{prefix}/{category_id}", headers=owner)
    assert deleted.status_code == (200 if method == "PATCH" else 204), deleted.text
    with Session(engine) as session:
        logs = session.exec(select(CategoryAuditLog).order_by(CategoryAuditLog.id)).all()
        assert [row.action for row in logs] == [
            "CREATE",
            "DEACTIVATE" if method == "PATCH" else "DELETE",
        ]
        if method == "PATCH":
            assert session.get(Category, category_id).is_active is False
    history = client.get("/api/v1/admin/category-audits", headers=owner, params={"limit": 1})
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["created_at"].endswith("Z")


@pytest.mark.parametrize("prefix", ["/api/v1/categories", "/api/v1/admin/categories"])
@pytest.mark.parametrize("mutation", ["create", "update", "delete"])
def test_audit_failure_rolls_back_category_change_instead_of_reporting_slug_conflict(
    backend, prefix, mutation
):
    client, engine, _, tokens = backend
    owner = tokens[ADMIN_ID]
    if mutation != "create":
        created = client.post(prefix, headers=owner, json={"name": "Original", "slug": "original"})
        assert created.status_code == 201
        category_id = created.json()["id"]
        with Session(engine) as session:
            metadata = session.exec(select(ProductMetadata)).one()
            metadata.category_id = category_id
            session.add(metadata)
            session.commit()
    before = persisted_state(backend)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_category_audit BEFORE INSERT ON category_audit_logs "
            "BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"
        )

    if mutation == "create":
        response = client.post(
            prefix, headers=owner, json={"name": "No partial", "slug": "no-partial"}
        )
    elif mutation == "update":
        method = "PATCH" if prefix == "/api/v1/categories" else "PUT"
        response = client.request(
            method, f"{prefix}/{category_id}", headers=owner, json={"name": "Changed"}
        )
    else:
        response = client.delete(f"{prefix}/{category_id}", headers=owner)

    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
    assert persisted_state(backend) == before


def test_legacy_category_reparenting_is_also_audited(backend):
    client, engine, _, tokens = backend
    owner = tokens[ADMIN_ID]
    root = client.post(
        "/api/v1/admin/categories", headers=owner, json={"name": "Root", "slug": "root"}
    ).json()["id"]
    child = client.post(
        "/api/v1/admin/categories",
        headers=owner,
        json={"name": "Child", "slug": "child", "parent_id": root},
    ).json()["id"]

    response = client.delete(f"/api/v1/admin/categories/{root}", headers=owner)

    assert response.status_code == 204
    with Session(engine) as session:
        assert session.get(Category, child).parent_id is None
        log = session.exec(
            select(CategoryAuditLog).where(
                CategoryAuditLog.category_id == child, CategoryAuditLog.action == "UPDATE"
            )
        ).one()
        assert f'"parent_id": {root}' in log.before_json
        assert '"parent_id": null' in log.after_json


@pytest.mark.parametrize("parent_kind", ["inactive", "cycle"])
def test_legacy_category_route_rejects_invalid_ancestor_chains(backend, parent_kind):
    client, engine, _, tokens = backend
    with Session(engine) as session:
        parent = Category(
            name="Invalid parent", slug="invalid-parent", is_active=parent_kind != "inactive"
        )
        session.add(parent)
        session.flush()
        if parent_kind == "cycle":
            parent.parent_id = parent.id
            session.add(parent)
        session.commit()
        parent_id = parent.id
    before = persisted_state(backend)

    response = client.post(
        "/api/v1/admin/categories",
        headers=tokens[ADMIN_ID],
        json={"name": "Child", "slug": "child", "parent_id": parent_id},
    )

    assert response.status_code == 400
    assert persisted_state(backend) == before


@pytest.mark.parametrize("target", [BUYER_ID, SELLER_ID])
@pytest.mark.parametrize("status", ["RESTRICTED", "SUSPENDED"])
def test_account_moderation_audits_actor_and_blocks_existing_tokens(backend, target, status):
    client, engine, ids, tokens = backend
    response = client.patch(
        f"/api/v1/admin/users/{target}/status",
        headers=tokens[ADMIN_ID],
        json={"status": status, "reason": "  Policy violation  "},
    )
    assert response.status_code == 200, response.text
    [audit] = response.json()["recent_audits"]
    assert (audit["admin_id"], audit["old_status"], audit["new_status"], audit["reason"]) == (
        ADMIN_ID,
        "ACTIVE",
        status,
        "Policy violation",
    )
    assert audit["created_at"].endswith("Z")
    repeated = client.patch(
        f"/api/v1/admin/users/{target}/status", headers=tokens[ADMIN_ID], json={"status": status}
    )
    assert repeated.status_code == 200
    assert len(repeated.json()["recent_audits"]) == 1
    before = persisted_state(backend)
    if target == BUYER_ID:
        denied = client.post(
            "/api/v1/cart/items",
            headers=tokens[target],
            json={"product_code": "ADMIN-151", "quantity": 1},
        )
    else:
        denied = client.patch(
            f"/api/v1/seller/products/{ids['product']}",
            headers=tokens[target],
            json={"name": "Forbidden edit"},
        )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"
    assert persisted_state(backend) == before
    with Session(engine) as session:
        assert session.get(Product, ids["product"]).is_active is (
            target != SELLER_ID or status != "SUSPENDED"
        )


def test_account_audit_failure_rolls_back_status_and_seller_deactivation(backend):
    client, engine, _, tokens = backend
    before = persisted_state(backend)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_account_audit BEFORE INSERT ON account_audit_logs "
            "BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"
        )

    response = client.patch(
        f"/api/v1/admin/users/{SELLER_ID}/status",
        headers=tokens[ADMIN_ID],
        json={"status": "SUSPENDED", "reason": "Policy"},
    )

    assert response.status_code == 500
    assert persisted_state(backend) == before


def test_account_moderation_rejects_self_restriction_and_actor_spoofing(backend):
    client, _, _, tokens = backend
    before = persisted_state(backend)
    denied = client.patch(
        f"/api/v1/admin/users/{ADMIN_ID}/status",
        headers=tokens[ADMIN_ID],
        json={"status": "SUSPENDED"},
    )
    assert denied.status_code == 400
    spoofed = client.patch(
        f"/api/v1/admin/users/{BUYER_ID}/status",
        headers=tokens[ADMIN_ID],
        json={"status": "SUSPENDED", "admin_id": BUYER_ID},
    )
    assert spoofed.status_code == 422
    assert persisted_state(backend) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", " "),
        ("reason", "x" * 501),
        ("evidence", " "),
        ("evidence", "x" * 1001),
    ],
)
def test_escalation_rejects_invalid_text_without_partial_writes(backend, field, value):
    before = persisted_state(backend)
    response = open_dispute(backend, **{field: value})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "ERR_VALIDATION"
    assert persisted_state(backend) == before


def test_escalation_links_only_pending_request_and_does_not_duplicate_buyer_history(backend):
    client, engine, _, tokens = backend
    request_id = submit_buyer_return(backend)
    response = open_dispute(
        backend, reason="x" * 500, evidence="x" * 1000, created_by_user_id=BUYER_ID
    )
    assert response.status_code == 201, response.text
    assert response.json()["return_request_id"] == request_id
    assert response.json()["created_by_user_id"] == ADMIN_ID
    listed = client.get("/api/v1/admin/disputes", headers=tokens[ADMIN_ID]).json()
    assert listed[0]["created_by_user_id"] == ADMIN_ID
    with Session(engine) as session:
        [history] = session.exec(select(OrderHistory)).all()
        assert history.changed_by_user_id == BUYER_ID


@pytest.mark.parametrize("status", ["PENDING", "SHIPPED", "COMPLETED", "RETURNED_REFUNDED"])
def test_escalation_rejects_unavailable_states(backend, status):
    _, engine, ids, _ = backend
    with Session(engine) as session:
        order = session.get(SellerOrder, ids["shop"])
        order.status = status
        session.add(order)
        session.commit()
    before = persisted_state(backend)
    response = open_dispute(backend)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_INVALID_DISPUTE_STATE"
    assert persisted_state(backend) == before


def test_escalation_duplicate_and_order_mismatch_do_not_change_state(backend):
    _, engine, _, _ = backend
    with Session(engine) as session:
        other = Order(
            buyer_id=3,
            total_amount=0,
            status="DELIVERED",
            recipient_name="Other",
            delivery_address="Other street",
            phone_number="0912345678",
        )
        session.add(other)
        session.commit()
        other_id = other.id
    before = persisted_state(backend)
    mismatch = open_dispute(backend, order_id=other_id)
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "ERR_SUB_ORDER_MISMATCH"
    assert persisted_state(backend) == before
    assert open_dispute(backend).status_code == 201
    before = persisted_state(backend)
    duplicate = open_dispute(backend)
    assert duplicate.status_code == 409
    assert persisted_state(backend) == before


@pytest.mark.parametrize("failure", ["insert", "history", "commit", "lost-claim"])
def test_escalation_failure_rolls_back_dispute_order_history_and_parent(
    backend, monkeypatch, failure
):
    _, engine, _, _ = backend
    before = persisted_state(backend)
    if failure == "lost-claim":
        monkeypatch.setattr(dispute_repository, "pause_review", lambda *args: False)
    else:
        table = "return_disputes" if failure == "insert" else "order_history"
        if failure == "commit":

            def fail_commit(session):
                raise OperationalError("COMMIT", {}, Exception("injected failure"))

            monkeypatch.setattr(Session, "commit", fail_commit)
        else:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    f"CREATE TRIGGER reject_escalation BEFORE INSERT ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
                )
    response = open_dispute(backend)
    assert response.status_code == (409 if failure == "lost-claim" else 500), response.text
    assert persisted_state(backend) == before


@pytest.mark.parametrize(
    ("backend", "action", "expected_payment", "expected_escrow"),
    [
        ("PAID", "APPROVE", "REFUNDED", "VOIDED"),
        ("UNPAID", "APPROVE", "UNPAID", "VOIDED"),
        ("FAILED", "APPROVE", "FAILED", "VOIDED"),
        ("PAID", "REJECT", "PAID", "RELEASED"),
        ("UNPAID", "REJECT", "UNPAID", "HELD"),
    ],
    indirect=["backend"],
)
@pytest.mark.parametrize("restock", [False, True])
def test_dispute_decisions_share_payment_inventory_and_audit_rules(
    backend, monkeypatch, action, expected_payment, expected_escrow, restock
):
    _, engine, ids, _ = backend
    now = datetime(2030, 1, 2, 7, 30, 0, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(tz):
            return now

    monkeypatch.setattr(admin_disputes, "datetime", Clock)
    monkeypatch.setattr(payments, "datetime", Clock)
    monkeypatch.setattr(returns, "datetime", Clock)
    request_id = submit_buyer_return(backend)
    created = open_dispute(backend)
    assert created.status_code == 201
    dispute_id = created.json()["id"]

    response = decide(
        backend, dispute_id, action=action, is_restockable=restock, decision_notes="  Reviewed  "
    )

    assert response.status_code == 200, response.text
    data = response.json()
    approved = action == "APPROVE"
    assert (
        data["status"],
        data["decided_by_user_id"],
        data["decision_notes"],
        data["is_restockable"],
    ) == ("APPROVED" if approved else "REJECTED", ADMIN_ID, "Reviewed", approved and restock)
    assert data["decided_at"] == "2030-01-02T07:30:00Z"
    with Session(engine) as session:
        dispute = session.get(ReturnDispute, dispute_id)
        request = session.get(ReturnRequest, request_id)
        shop = session.get(SellerOrder, ids["shop"])
        parent = session.get(Order, ids["order"])
        assert (shop.status, shop.payment_status, shop.escrow_status) == (
            "RETURNED_REFUNDED" if approved else "COMPLETED",
            expected_payment,
            expected_escrow,
        )
        assert (parent.status, parent.payment_status, parent.escrow_status) == (
            shop.status,
            expected_payment,
            expected_escrow,
        )
        assert (
            request.status,
            request.decided_by_user_id,
            request.decided_at,
            request.is_restockable,
        ) == (dispute.status, ADMIN_ID, dispute.decided_at, approved and restock)
        history = session.exec(select(OrderHistory).order_by(OrderHistory.id.desc())).first()
        assert (history.changed_by_user_id, history.actor_role, history.created_at) == (
            ADMIN_ID,
            "admin",
            dispute.decided_at,
        )
        if not approved:
            assert shop.completed_at == parent.completed_at == history.created_at
        assert session.get(Product, ids["product"]).stock_quantity == (
            10 if approved and restock else 8
        )
        meta = session.exec(select(ProductMetadata)).one()
        assert meta.sales_count == (0 if approved and restock else 2)
        notifications = session.exec(
            select(Notification).where(Notification.event_key.like("dispute:%"))
        ).all()
        assert {row.recipient_user_id for row in notifications} == {BUYER_ID, SELLER_ID}
        assert all(row.created_at == dispute.decided_at for row in notifications)
        refunds = session.exec(select(PaymentEvent).where(PaymentEvent.kind == "REFUND")).all()
        if expected_payment == "REFUNDED":
            assert len(refunds) == 1
            assert (refunds[0].actor_user_id, refunds[0].amount) == (ADMIN_ID, 200000)
            assert shop.refunded_amount == 200000
        else:
            assert refunds == []
            assert shop.refunded_amount == 0
    before = persisted_state(backend)
    assert decide(backend, dispute_id, action=action, is_restockable=True).status_code == 400
    assert persisted_state(backend) == before


def test_dispute_restock_restores_only_the_purchased_variant(backend):
    _, engine, ids, _ = backend
    with Session(engine) as session:
        variant = ProductVariant(
            product_id=ids["product"],
            seller_id=SELLER_ID,
            sku="RET-151",
            name="Blue",
            price=100000,
            stock_quantity=3,
            is_active=False,
        )
        session.add(variant)
        session.flush()
        item = session.exec(select(OrderItem)).one()
        item.variant_id = variant.id
        session.add(item)
        session.commit()
        variant_id = variant.id
    dispute_id = open_dispute(backend).json()["id"]
    response = decide(backend, dispute_id, is_restockable=True)
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        assert session.get(ProductVariant, variant_id).stock_quantity == 5
        assert session.get(Product, ids["product"]).stock_quantity == 8


@pytest.mark.parametrize("backend", ["LEGACY"], indirect=True)
@pytest.mark.parametrize("action", ["APPROVE", "REJECT"])
def test_admin_dispute_does_not_invent_legacy_refunds_or_settlement(backend, action):
    _, engine, ids, _ = backend
    created = open_dispute(backend)
    assert created.status_code == 201, created.text

    response = decide(backend, created.json()["id"], action=action)

    assert response.status_code == 200, response.text
    with Session(engine) as session:
        parent = session.get(Order, ids["order"])
        child = session.get(SellerOrder, ids["shop"])
        assert parent.payment_method is None
        assert parent.payment_status == child.payment_status == "PAID"
        assert child.refunded_amount == 0
        assert child.settled_at is None
        assert child.escrow_status == ("VOIDED" if action == "APPROVE" else "HELD")
        assert session.exec(select(PaymentEvent)).all() == []


@pytest.mark.parametrize(
    "invalid", ["payment", "state", "request", "ownership", "dispute-ownership", "body"]
)
def test_invalid_adjudication_preserves_all_state(backend, invalid):
    _, engine, ids, _ = backend
    request_id = submit_buyer_return(backend)
    dispute_id = open_dispute(backend).json()["id"]
    with Session(engine) as session:
        shop = session.get(SellerOrder, ids["shop"])
        dispute = session.get(ReturnDispute, dispute_id)
        request = session.get(ReturnRequest, request_id)
        if invalid == "payment":
            shop.payment_status = "REFUND_PENDING"
        elif invalid == "state":
            shop.status = "COMPLETED"
        elif invalid == "request":
            request.status = "REJECTED"
        elif invalid == "ownership":
            request.buyer_id = 3
        elif invalid == "dispute-ownership":
            dispute.buyer_id = 3
        session.add_all([shop, dispute, request])
        session.commit()
    before = persisted_state(backend)
    response = decide(
        backend, dispute_id, **({"decided_by_user_id": 2} if invalid == "body" else {})
    )
    assert response.status_code == (
        409 if invalid == "payment" else 422 if invalid == "body" else 400
    )
    assert persisted_state(backend) == before


@pytest.mark.parametrize(
    "failure",
    [
        "restock",
        "history",
        "notification",
        "refund-event",
        "commit",
        "request-claim",
        "dispute-claim",
    ],
)
def test_adjudication_failure_rolls_back_every_side_effect(backend, monkeypatch, failure):
    _, engine, _, _ = backend
    submit_buyer_return(backend)
    dispute_id = open_dispute(backend).json()["id"]
    before = persisted_state(backend)
    if failure.endswith("claim"):
        method = "claim_request" if failure == "request-claim" else "claim_dispute"
        monkeypatch.setattr(dispute_repository, method, lambda *args: False)
    elif failure == "commit":

        def fail_commit(session):
            raise OperationalError("COMMIT", {}, Exception("injected failure"))

        monkeypatch.setattr(Session, "commit", fail_commit)
    else:
        table = {
            "restock": "products",
            "history": "order_history",
            "notification": "notifications",
            "refund-event": "payment_events",
        }[failure]
        operation = "UPDATE" if failure == "restock" else "INSERT"
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TRIGGER reject_adjudication BEFORE {operation} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
            )
    response = decide(backend, dispute_id, is_restockable=True)
    assert response.status_code == (400 if failure.endswith("claim") else 500), response.text
    assert persisted_state(backend) == before


def test_escalation_compare_and_set_preserves_a_concurrently_changed_seller_order(backend):
    _, engine, ids, _ = backend
    with Session(engine) as stale:
        seller_order = stale.get(SellerOrder, ids["shop"])
        with Session(engine) as concurrent:
            changed = concurrent.get(SellerOrder, ids["shop"])
            changed.status = "COMPLETED"
            concurrent.add(changed)
            concurrent.commit()

        assert dispute_repository.pause_review(stale, seller_order) is False
        stale.rollback()

    with Session(engine) as session:
        assert session.get(SellerOrder, ids["shop"]).status == "COMPLETED"
        assert session.exec(select(ReturnDispute)).all() == []
        assert session.exec(select(OrderHistory)).all() == []


def test_migration_keeps_legacy_actor_unknown_and_creates_empty_category_audit(
    backend, monkeypatch
):
    _, engine, _, _ = backend
    dispute_id = open_dispute(backend).json()["id"]
    with Session(engine) as session:
        before = session.get(ReturnDispute, dispute_id).model_dump(exclude={"created_by_user_id"})
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE return_disputes_legacy (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            seller_order_id INTEGER NOT NULL UNIQUE REFERENCES seller_orders(id),
            return_request_id INTEGER REFERENCES return_requests(id),
            buyer_id INTEGER NOT NULL REFERENCES users(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            reason VARCHAR(500) NOT NULL, evidence VARCHAR(1000) NOT NULL,
            status VARCHAR(20) NOT NULL, decision_notes VARCHAR(1000),
            decided_by_user_id INTEGER REFERENCES users(id),
            is_restockable BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
            decided_at DATETIME
        )""")
        columns = ", ".join(before)
        connection.exec_driver_sql(
            f"INSERT INTO return_disputes_legacy ({columns}) SELECT {columns} FROM return_disputes"
        )
        connection.exec_driver_sql("DROP TABLE return_disputes")
        connection.exec_driver_sql("ALTER TABLE return_disputes_legacy RENAME TO return_disputes")
        connection.exec_driver_sql("DROP TABLE category_audit_logs")
    monkeypatch.setattr(database, "engine", engine)

    database.init_db()
    database.init_db()

    with Session(engine) as session:
        migrated = session.get(ReturnDispute, dispute_id)
        assert migrated.created_by_user_id is None
        assert migrated.model_dump(exclude={"created_by_user_id"}) == before
        assert session.exec(select(CategoryAuditLog)).all() == []
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []


def test_fixed_platform_voucher_rejects_cap_without_a_partial_write(backend):
    client, engine, _, tokens = backend
    response = client.post(
        "/api/v1/admin/vouchers",
        headers=tokens[ADMIN_ID],
        json={
            "code": "FIXED-CAP",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 10000,
            "max_discount": 5000,
            "starts_at": "2030-01-01T00:00:00Z",
            "ends_at": "2030-02-01T00:00:00Z",
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "ERR_INVALID_DISCOUNT"
    with Session(engine) as session:
        assert session.exec(select(Voucher)).all() == []
