"""Task #127: audit snapshots, shipping milestones and authorized history reads."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from src.auth import create_access_token
from src.database import get_session, migrate_db
from src.main import create_app
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.order_status import OrderStatusChange
from src.services.order_history import record_transition


@pytest.fixture
def audit_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        users = [
            User(id=i, name=role, email=f"{i}@history.local", role=role)
            for i, role in enumerate(["buyer", "seller", "seller", "buyer"], start=1)
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
        row = connection.execute(text("SELECT actor_role, note FROM order_history")).one()
        assert row == (None, "Legacy event")
    engine.dispose()
