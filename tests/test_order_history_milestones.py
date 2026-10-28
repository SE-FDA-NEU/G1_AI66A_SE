"""Task #127: audit snapshots, shipping milestones and authorized history reads."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from src.auth import create_access_token
from src.database import get_session, migrate_db
from src.main import create_app
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.order_status import OrderStatusChange
from src.services.order_history import record_transition


@pytest.fixture
def audit_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        users = [
            User(id=i, name=role, email=f"{i}@history.local", role=role)
            for i, role in enumerate(["buyer", "seller", "seller", "buyer", "seller"], start=1)
        ]
        session.add_all(users)
        session.flush()
        session.add(
            Order(
                id=1,
                buyer_id=1,
                status="CONFIRMED",
                total_amount=200,
                recipient_name="Buyer",
                delivery_address="Test street",
                phone_number="0912345678",
            )
        )
        session.flush()
        session.add_all(
            [
                SellerOrder(id=1, order_id=1, seller_id=2, status="CONFIRMED"),
                SellerOrder(id=2, order_id=1, seller_id=3, status="CONFIRMED"),
            ]
        )
        session.flush()
        session.add_all([
            Product(id=i, code=f"AUDIT-{i}", name=f"Shop {i}", seller_id=i + 1,
                    price=100, stock_quantity=9)
            for i in (1, 2)
        ])
        session.flush()
        session.add_all([
            OrderItem(seller_order_id=i, product_id=i, quantity=1, unit_price=100)
            for i in (1, 2)
        ])
        session.add_all([
            ProductMetadata(product_id=i, sales_count=1) for i in (1, 2)
        ])
        session.commit()
        headers = {
            user.id: {"Authorization": f"Bearer {create_access_token(user)}"} for user in users
        }

    def sessions():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client, engine, headers
    engine.dispose()


@pytest.mark.parametrize("endpoint", ["/api/v1/seller/orders/1/status", "/api/v1/orders/1/status"])
def test_shipping_records_actor_note_and_exact_milestone(audit_data, endpoint):
    client, engine, headers = audit_data
    response = client.patch(
        endpoint,
        headers=headers[2],
        json={
            "status": "SHIPPED",
            "tracking_number": "  VN-127  ",
            "note": "  Handed to carrier  ",
        },
    )
    assert response.status_code == 200
    with Session(engine) as session:
        event = session.exec(select(OrderHistory)).one()
        shipment = session.get(SellerOrder, 1)
        assert (event.from_status, event.to_status) == ("CONFIRMED", "SHIPPED")
        assert event.changed_by_user_id == 2
        assert event.actor_role == "seller"
        assert event.note == "Handed to carrier"
        assert shipment.tracking_number == "VN-127"
        assert shipment.shipped_at == event.created_at
        assert shipment.delivered_at is None

    receipt = client.get("/api/v1/orders/1", headers=headers[1]).json()["data"]
    shipment = next(row for row in receipt["sub_orders"] if row["id"] == 1)
    assert shipment["tracking_number"] == "VN-127"
    assert shipment["shipped_at"] == shipment["history"][0]["created_at"]
    assert shipment["history"][0]["actor_role"] == "seller"


def test_delivery_keeps_shipping_snapshot_and_buyer_confirmation_is_audited(audit_data):
    client, engine, headers = audit_data
    for seller, sub_order in [(2, 1), (3, 2)]:
        for status in ["SHIPPED", "DELIVERED"]:
            response = client.patch(
                f"/api/v1/seller/orders/{sub_order}/status",
                headers=headers[seller],
                json={"status": status, "tracking_number": "VN-127"},
            )
            assert response.status_code == 200
    before = client.get("/api/v1/orders/1", headers=headers[1]).json()["data"]["sub_orders"][0]
    response = client.post("/api/v1/orders/1/confirm", headers=headers[1])
    assert response.status_code == 200
    shipment = response.json()["data"]["sub_orders"][0]
    assert shipment["shipped_at"] == before["shipped_at"]
    assert shipment["delivered_at"] == before["delivered_at"]
    assert [row["to_status"] for row in shipment["history"]] == [
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
    ]
    assert shipment["history"][-1]["changed_by_user_id"] == 1
    assert shipment["history"][-1]["actor_role"] == "buyer"
    with Session(engine) as session:
        delivery = session.exec(
            select(OrderHistory).where(
                OrderHistory.seller_order_id == 1,
                OrderHistory.to_status == "DELIVERED",
            )
        ).one()
        assert session.get(SellerOrder, 1).delivered_at == delivery.created_at


def test_history_is_scoped_to_the_authenticated_shop(audit_data):
    client, _engine, headers = audit_data
    for seller in (2, 3):
        assert (
            client.patch(
                "/api/v1/orders/1/status", headers=headers[seller], json={"status": "PROCESSING"}
            ).status_code
            == 200
        )
    buyer = client.get("/api/v1/orders/1", headers=headers[1]).json()["data"]
    assert len(buyer["sub_orders"]) == 2
    assert {item["seller_order_id"] for item in buyer["items"]} == {1, 2}
    seller = client.get("/api/v1/orders/1", headers=headers[2]).json()["data"]
    assert [row["id"] for row in seller["sub_orders"]] == [1]
    assert [row["seller_order_id"] for row in seller["sub_orders"][0]["history"]] == [1]
    listed = client.get("/api/v1/seller/orders", headers=headers[2]).json()["data"]
    assert listed[0]["history"] == seller["sub_orders"][0]["history"]
    assert client.get("/api/v1/orders/1", headers=headers[4]).status_code == 404
    assert client.get("/api/v1/orders/1").status_code == 401


def test_invalid_or_foreign_transitions_create_no_history(audit_data):
    client, engine, headers = audit_data
    for actor, status in [(3, "SHIPPED"), (2, "DELIVERED")]:
        response = client.patch(
            "/api/v1/seller/orders/1/status", headers=headers[actor], json={"status": status}
        )
        assert response.status_code in (400, 403)
    with Session(engine) as session:
        assert session.exec(select(OrderHistory)).all() == []
        assert session.get(SellerOrder, 1).shipped_at is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("tracking_number", "x" * 101),
        ("tracking_number", "   "),
        ("note", "x" * 1001),
        ("actor_role", "admin"),
        ("changed_by_user_id", 3),
    ],
)
def test_invalid_audit_input_is_rejected_without_writes(audit_data, field, value):
    client, engine, headers = audit_data
    response = client.patch(
        "/api/v1/seller/orders/1/status",
        headers=headers[2],
        json={"status": "SHIPPED", field: value},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ERR_VALIDATION"
    with Session(engine) as session:
        assert session.exec(select(OrderHistory)).all() == []
        assert session.get(SellerOrder, 1).status == "CONFIRMED"


@pytest.mark.parametrize(
    "field,length",
    [
        ("tracking_number", 99),
        ("tracking_number", 100),
        ("note", 999),
        ("note", 1000),
    ],
)
def test_audit_input_accepts_values_at_and_below_the_limits(field, length):
    request = OrderStatusChange.model_validate({"status": "SHIPPED", field: "x" * length})
    assert getattr(request, field) == "x" * length


def test_history_order_is_stable_when_events_share_a_timestamp(audit_data):
    client, engine, headers = audit_data
    instant = datetime(2026, 10, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                OrderHistory(
                    id=2,
                    seller_order_id=1,
                    from_status="PROCESSING",
                    to_status="SHIPPED",
                    changed_by_user_id=2,
                    actor_role="seller",
                    created_at=instant,
                ),
                OrderHistory(
                    id=1,
                    seller_order_id=1,
                    from_status="CONFIRMED",
                    to_status="PROCESSING",
                    changed_by_user_id=2,
                    actor_role="seller",
                    created_at=instant,
                ),
            ]
        )
        session.commit()
    data = client.get("/api/v1/orders/1", headers=headers[1]).json()["data"]
    assert [event["id"] for event in data["sub_orders"][0]["history"]] == [1, 2]


def test_actor_role_is_a_snapshot_not_a_join_to_the_current_role(audit_data):
    client, engine, headers = audit_data
    assert (
        client.patch(
            "/api/v1/orders/1/status", headers=headers[2], json={"status": "PROCESSING"}
        ).status_code
        == 200
    )
    with Session(engine) as session:
        actor = session.get(User, 2)
        actor.role = "buyer"
        session.add(actor)
        session.commit()
    history = client.get("/api/v1/orders/1", headers=headers[1]).json()["data"]["sub_orders"][0][
        "history"
    ]
    assert history[0]["actor_role"] == "seller"


@pytest.mark.parametrize("role", ["buyer", "seller", "admin"])
def test_audit_service_snapshots_authenticated_actor_without_committing(monkeypatch, role):
    actor = User(id=7, name="Actor", email="actor@history.local", role=role)
    instant = datetime(2026, 10, 28, 8, 30, tzinfo=UTC)
    recorded = []
    transaction = object()
    monkeypatch.setattr(
        "src.services.order_history.append_history",
        lambda session, event: recorded.append((session, event)),
    )
    record_transition(
        transaction,
        seller_order_id=1,
        from_status="CONFIRMED",
        to_status="SHIPPED",
        actor=actor,
        note="Test note",
        occurred_at=instant,
    )
    session, event = recorded[0]
    assert session is transaction
    assert (event.changed_by_user_id, event.actor_role) == (7, role)
    assert event.created_at == instant
    assert event.note == "Test note"


@pytest.mark.parametrize("endpoint", ["/api/v1/seller/orders/1/status", "/api/v1/orders/1/status"])
def test_history_failure_rolls_back_status_and_shipping_milestone(
    audit_data, monkeypatch, endpoint
):
    client, engine, headers = audit_data

    def fail_history(_session, _event):
        raise SQLAlchemyError("Injected audit persistence failure")

    monkeypatch.setattr("src.services.order_history.append_history", fail_history)
    response = client.patch(endpoint, headers=headers[2], json={"status": "SHIPPED"})
    assert response.status_code == 500
    with Session(engine) as session:
        assert session.get(SellerOrder, 1).status == "CONFIRMED"
        assert session.get(SellerOrder, 1).shipped_at is None
        assert session.exec(select(OrderHistory)).all() == []


def test_seller_receipt_never_uses_another_shops_shipping_milestones(audit_data):
    client, _engine, headers = audit_data
    assert (
        client.patch(
            "/api/v1/orders/1/status",
            headers=headers[3],
            json={"status": "SHIPPED", "tracking_number": "OTHER-SHOP"},
        ).status_code
        == 200
    )
    response = client.get("/api/v1/orders/1", headers=headers[2]).json()["data"]
    assert response["tracking_number"] is None
    assert response["shipped_at"] is None
    assert response["sub_orders"][0]["history"] == []


def test_legacy_history_migration_is_repeatable_and_preserves_unknown_role(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE order_history (id INTEGER PRIMARY KEY, "
                "seller_order_id INTEGER, from_status TEXT, to_status TEXT, "
                "changed_by_user_id INTEGER, note TEXT, created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO order_history VALUES "
                "(1, 1, 'PENDING', 'CONFIRMED', 2, 'Legacy event', '2026-10-01')"
            )
        )
        migrate_db(connection)
        migrate_db(connection)
        assert "actor_role" in {
            column["name"] for column in inspect(connection).get_columns("order_history")
        }
        row = connection.execute(text("SELECT * FROM order_history")).one()
        assert tuple(row) == (1, 1, "PENDING", "CONFIRMED", 2, "Legacy event", "2026-10-01", None)
    with Session(engine) as session:
        legacy = session.get(OrderHistory, 1)
        assert legacy.actor_role is None
        assert legacy.created_at == datetime(2026, 10, 1)
        record_transition(
            session, seller_order_id=1, from_status="CONFIRMED", to_status="SHIPPED",
            actor=User(id=2, name="Seller", email="legacy@history.local", role="seller"),
            occurred_at=datetime(2026, 10, 29, tzinfo=UTC),
        )
        session.commit()
    with engine.begin() as connection:
        migrate_db(connection)
        assert connection.execute(
            text("SELECT actor_role FROM order_history ORDER BY id")
        ).scalars().all() == [None, "seller"]
    engine.dispose()


def test_seller_receipt_excludes_other_shops_fulfillment_items(audit_data):
    client, _engine, headers = audit_data
    shipped = client.patch(
        "/api/v1/orders/1/status", headers=headers[3],
        json={"status": "SHIPPED", "tracking_number": "OTHER-SHOP"},
    )
    assert shipped.status_code == 200
    assert {item["seller_order_id"] for item in shipped.json()["data"]["items"]} == {2}
    for method, path, body in [
        ("GET", "/api/v1/orders/1", None),
        ("PATCH", "/api/v1/orders/1/status", {"status": "PROCESSING"}),
    ]:
        response = client.request(method, path, headers=headers[2], json=body)
        assert response.status_code == 200
        data = response.json()["data"]
        assert {item["seller_order_id"] for item in data["items"]} == {1}
        assert [row["id"] for row in data["sub_orders"]] == [1]
        assert "OTHER-SHOP" not in response.text


def test_seller_completion_uses_one_utc_instant_for_parent_child_and_history(
    audit_data, monkeypatch
):
    client, engine, headers = audit_data
    instant = datetime(2026, 10, 29, 1, 2, 3, tzinfo=UTC)

    class AdvancingClock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            value = instant + timedelta(seconds=cls.calls)
            cls.calls += 1
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    with Session(engine) as session:
        first, second = session.get(SellerOrder, 1), session.get(SellerOrder, 2)
        first.status = "DELIVERED"
        second.status = "COMPLETED"
        session.add_all([first, second])
        session.commit()
    monkeypatch.setattr("src.services.order_workflow.datetime", AdvancingClock)
    response = client.patch(
        "/api/v1/seller/orders/1/status", headers=headers[2], json={"status": "COMPLETED"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    with Session(engine) as session:
        parent = session.get(Order, 1)
        child = session.get(SellerOrder, 1)
        history = session.exec(select(OrderHistory)).one()
        assert parent.completed_at == child.completed_at == history.created_at
    assert data["ordered_at"].endswith("Z")
    assert data["completed_at"] == data["history"][0]["created_at"]


def test_audit_service_converts_offset_timestamp_to_utc(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "src.services.order_history.append_history",
        lambda _session, event: recorded.append(event),
    )
    record_transition(
        object(), seller_order_id=1, from_status="CONFIRMED", to_status="SHIPPED",
        actor=User(id=2, name="Seller", email="utc@history.local", role="seller"),
        occurred_at=datetime(2026, 10, 29, 8, 30, tzinfo=timezone(timedelta(hours=7))),
    )
    assert recorded[0].created_at.tzinfo == UTC
    assert recorded[0].created_at == datetime(2026, 10, 29, 1, 30, tzinfo=UTC)


def _stored_audit_state(engine):
    """Observe committed business and audit data through a fresh session."""
    with Session(engine) as session:
        return {
            model.__tablename__: [row.model_dump() for row in session.exec(
                select(model).order_by(*model.__table__.primary_key.columns)
            ).all()]
            for model in (Order, SellerOrder, OrderHistory, Product, ProductMetadata, Notification)
        }


@pytest.mark.parametrize("failure", ["history_insert", "commit"])
@pytest.mark.parametrize("endpoint,actor,initial,target", [
    ("/api/v1/seller/orders/1/status", 2, "CONFIRMED", "SHIPPED"),
    ("/api/v1/orders/1/status", 2, "CONFIRMED", "SHIPPED"),
    ("/api/v1/seller/orders/1/status", 2, "CONFIRMED", "CANCELLED"),
    ("/api/v1/orders/1/status", 2, "CONFIRMED", "CANCELLED"),
    ("/api/v1/orders/1/status", 1, "PENDING", "CANCELLED"),
    ("/api/v1/orders/1/status", 1, "DELIVERED", "COMPLETED"),
])
def test_database_failure_rolls_back_the_whole_transition(
    audit_data, monkeypatch, failure, endpoint, actor, initial, target
):
    client, engine, headers = audit_data
    with Session(engine) as session:
        for row in [session.get(Order, 1), *session.exec(select(SellerOrder)).all()]:
            row.status = initial
            if initial == "DELIVERED":
                row.shipped_at = datetime(2026, 10, 27, tzinfo=UTC)
                row.delivered_at = datetime(2026, 10, 28, tzinfo=UTC)
                row.tracking_number = "ORIGINAL"
            session.add(row)
        session.commit()
    before = _stored_audit_state(engine)
    flushed = []
    if failure == "history_insert":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER reject_history BEFORE INSERT ON order_history "
                "BEGIN SELECT RAISE(ABORT, 'Injected audit insert failure'); END"
            )
    else:
        def fail_commit(session):
            # Fail after status, history, milestones and other side effects reached the DB.
            session.flush()
            flushed.extend(session.exec(select(OrderHistory)).all())
            raise SQLAlchemyError("Injected failure before transaction commit")

        monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.patch(
        endpoint, headers=headers[actor],
        json={"status": target, "tracking_number": "NEW-TRACKING"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ERR_DATABASE_FAILURE"
    if failure == "commit":
        assert flushed
    assert _stored_audit_state(engine) == before


@pytest.mark.parametrize("actor,path,status", [
    (4, "/api/v1/orders/1", 404),
    (5, "/api/v1/orders/1", 404),
    (1, "/api/v1/seller/orders", 403),
])
def test_unauthorized_history_reads_reveal_no_order_data(audit_data, actor, path, status):
    client, _engine, headers = audit_data
    shipped = client.patch(
        "/api/v1/seller/orders/1/status", headers=headers[2],
        json={"status": "SHIPPED", "tracking_number": "PRIVATE-TRACKING"},
    )
    assert shipped.status_code == 200
    response = client.get(path, headers=headers[actor])
    assert response.status_code == status
    assert "data" not in response.json()
    assert "PRIVATE-TRACKING" not in response.text
    assert "actor_role" not in response.text
    assert client.get("/api/v1/orders", headers=headers[4]).json() == []
    assert client.get("/api/v1/seller/orders", headers=headers[5]).json()["data"] == []


@pytest.mark.parametrize("actor,path,status", [
    (4, "/api/v1/orders/1/status", 404),
    (5, "/api/v1/orders/1/status", 403),
    (3, "/api/v1/seller/orders/1/status", 403),
    (1, "/api/v1/seller/orders/1/status", 403),
])
def test_foreign_status_updates_leave_all_audit_data_unchanged(audit_data, actor, path, status):
    client, engine, headers = audit_data
    before = _stored_audit_state(engine)
    response = client.patch(path, headers=headers[actor], json={"status": "SHIPPED"})
    assert response.status_code == status
    assert _stored_audit_state(engine) == before


@pytest.mark.parametrize("path", ["/api/v1/orders/1/status", "/api/v1/seller/orders/1/status"])
def test_invalid_transition_leaves_all_audit_data_unchanged(audit_data, path):
    client, engine, headers = audit_data
    before = _stored_audit_state(engine)
    response = client.patch(path, headers=headers[2], json={"status": "DELIVERED"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_INVALID_TRANSITION"
    assert _stored_audit_state(engine) == before


@pytest.mark.parametrize("method,path,actor,role,with_note,expected_children", [
    ("PATCH", "/api/v1/seller/orders/1/status", 2, "seller", True, {1}),
    ("PATCH", "/api/v1/orders/1/status", 2, "seller", True, {1}),
    ("PATCH", "/api/v1/orders/1/status", 1, "buyer", True, {1, 2}),
    ("POST", "/api/v1/orders/1/cancel", 1, "buyer", False, {1, 2}),
])
def test_atomic_cancellation_workflow_preserves_actor_and_note(
    audit_data, method, path, actor, role, with_note, expected_children
):
    client, engine, headers = audit_data
    with Session(engine) as session:
        for row in [session.get(Order, 1), *session.exec(select(SellerOrder)).all()]:
            row.status = "PENDING"
            session.add(row)
        session.commit()
    body = {"status": "CANCELLED", "note": "  Reviewed cancellation  "} if with_note else None
    response = client.request(method, path, headers=headers[actor], json=body)
    assert response.status_code == 200
    with Session(engine) as session:
        events = session.exec(select(OrderHistory).order_by(OrderHistory.id)).all()
        assert {row.seller_order_id for row in events} == expected_children
        for row in events:
            assert (row.from_status, row.to_status) == ("PENDING", "CANCELLED")
            assert (row.changed_by_user_id, row.actor_role) == (actor, role)
            if with_note:
                assert row.note == "Reviewed cancellation"
            else:
                assert "Stock restored." in row.note
            assert session.get(SellerOrder, row.seller_order_id).payment_status == "REFUNDED"
    visible = response.json()["data"]
    sub_orders = visible["sub_orders"] if "sub_orders" in visible else [visible]
    for row in sub_orders:
        if row["id"] in expected_children:
            assert row["history"][-1]["actor_role"] == role
            assert row["history"][-1]["created_at"].endswith("Z")
