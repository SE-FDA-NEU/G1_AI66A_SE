"""#227: private unread totals and atomic, idempotent mark-all-read."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from src.models.notification import Notification
from src.models.order import Order
from src.services import notifications
from tests import test_cart_api as cart_api

api, engine = cart_api.api, cart_api.engine
COUNT_PATH = "/api/v1/notifications/unread-count"
ALL_PATH = "/api/v1/notifications/mark-all-read"
READ_TIME = datetime(2026, 11, 1, tzinfo=UTC)


def seed_notifications(engine, user_id=2, unread=2, read=1):
    with Session(engine) as session:
        order = Order(buyer_id=2, total_amount=100, status="COMPLETED",
                      recipient_name="Buyer", delivery_address="Test", phone_number="0123456789")
        session.add(order)
        session.flush()
        rows = [Notification(recipient_user_id=user_id, order_id=order.id,
                             event_key=f"badge:{order.id}:{index}", message=f"Update {index}",
                             target_path="/products", read_at=None if index < unread else READ_TIME)
                for index in range(unread + read)]
        session.add_all(rows)
        session.commit()
        return [row.id for row in rows]


def stored_reads(engine):
    with Session(engine) as session:
        return {row.id: row.read_at for row in session.exec(select(Notification))}


@pytest.mark.parametrize("count", [0, 1, 99, 100, 125])
def test_unread_count_is_exact_and_not_limited_to_displayed_rows(api, engine, count):
    seed_notifications(engine, unread=count)
    seed_notifications(engine, user_id=3, unread=7)

    response = api.get(COUNT_PATH, headers=cart_api.BUYER)

    assert response.status_code == 200
    assert response.json() == {"unread_count": count}
    listing = api.get("/api/v1/notifications", headers=cart_api.BUYER).json()
    assert listing["unread_count"] == count
    assert len(listing["data"]) == min(100, count + 1)


@pytest.mark.parametrize("method,path", [("GET", COUNT_PATH), ("POST", ALL_PATH)])
def test_guest_cannot_count_or_mark_notifications(api, method, path):
    response = api.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR_AUTH_REQUIRED"


def test_single_read_then_mark_all_only_updates_current_recipient(api, engine):
    own_ids = seed_notifications(engine, unread=125)
    seed_notifications(engine, user_id=3, unread=3)
    before = stored_reads(engine)
    assert api.patch(f"/api/v1/notifications/{own_ids[0]}/read",
                     headers=cart_api.BUYER).status_code == 200
    assert api.get(COUNT_PATH, headers=cart_api.BUYER).json()["unread_count"] == 124
    after_single = stored_reads(engine)
    assert api.patch(f"/api/v1/notifications/{own_ids[0]}/read",
                     headers=cart_api.BUYER).status_code == 200
    assert stored_reads(engine) == after_single

    response = api.post(ALL_PATH, headers=cart_api.BUYER)

    assert response.status_code == 200
    assert response.json() == {"unread_count": 0}
    after_all = stored_reads(engine)
    assert all(after_all[row_id] is not None for row_id in own_ids)
    assert after_all[own_ids[0]] == after_single[own_ids[0]]
    assert after_all[own_ids[-1]] == before[own_ids[-1]]
    assert len({after_all[row_id] for row_id in own_ids[1:-1]}) == 1
    assert all(value == after_all[row_id] for row_id, value in before.items()
               if row_id not in own_ids)
    assert api.post(ALL_PATH, headers=cart_api.BUYER).json() == {"unread_count": 0}
    assert stored_reads(engine) == after_all


def test_foreign_notification_cannot_be_marked_read(api, engine):
    foreign_id = seed_notifications(engine, user_id=3)[0]
    before = stored_reads(engine)
    response = api.patch(f"/api/v1/notifications/{foreign_id}/read", headers=cart_api.BUYER)
    assert response.status_code == 404
    assert stored_reads(engine) == before


@pytest.mark.parametrize("role,user_id", [("seller", 1), ("buyer", 3)])
def test_recipient_role_does_not_change_count_ownership(api, engine, role, user_id):
    seed_notifications(engine, user_id=user_id, unread=2)
    seed_notifications(engine, user_id=2, unread=5)
    headers = cart_api.bearer(user_id, role)
    assert api.get(COUNT_PATH, headers=headers).json() == {"unread_count": 2}
    assert api.post(ALL_PATH, headers=headers).json() == {"unread_count": 0}
    assert api.get(COUNT_PATH, headers=cart_api.BUYER).json() == {"unread_count": 5}


def test_failed_mark_all_rolls_back_every_notification(engine, monkeypatch):
    seed_notifications(engine)
    before = stored_reads(engine)

    def fail_commit():
        raise SQLAlchemyError("injected commit failure")

    with Session(engine) as session:
        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(SQLAlchemyError):
            notifications.mark_all_notifications_read(session, 2)
        assert {row.id: row.read_at for row in session.exec(select(Notification))} == before
    assert stored_reads(engine) == before
