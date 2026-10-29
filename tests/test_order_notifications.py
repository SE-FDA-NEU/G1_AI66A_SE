"""Order status notifications keyed on order history (#132)."""

from sqlmodel import Session, select

import src.services.order_workflow as workflow
from src.models.notification import Notification
from src.models.order_history import OrderHistory
from src.services.notifications import notify_transition
from tests import test_atomic_cancellation as cancellation
from tests.test_checkout import headers

# Reuse the real-SQLite fixtures from the cancellation tests.
api = cancellation.api
engine = cancellation.engine
purchase = cancellation.purchase


def notifications_for(engine, user_id):
    with Session(engine) as session:
        return session.exec(
            select(Notification)
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.id)
        ).all()


def test_repeated_status_after_rejected_request_notifies_each_event(engine):
    order_id, children, _ = purchase(engine)
    with Session(engine) as session:
        workflow.seller_status_change(session, 1, "CONFIRMED", sub_order_id=children[0])
        for _ in range(2):
            workflow.buyer_cancellation(session, 2, order_id, "CANCELLATION_REQUESTED")
            workflow.seller_status_change(session, 1, "CONFIRMED", sub_order_id=children[0])

    buyer = notifications_for(engine, 2)
    seller = [
        row for row in notifications_for(engine, 1) if row.event_key.startswith("order-history:")
    ]
    assert [row.message for row in buyer] == [
        f"Seller order #{children[0]} in your order #{order_id} is now confirmed."
    ] * 3
    assert {row.target_path for row in buyer} == {f"/orders/{order_id}"}
    assert [row.message for row in seller] == [
        f"The buyer requested cancellation of seller order #{children[0]} in order #{order_id}."
    ] * 2
    assert len({row.event_key for row in buyer + seller}) == 5


def test_replaying_a_history_event_creates_one_notification(engine):
    order_id, children, _ = purchase(engine)
    with Session(engine) as session:
        workflow.seller_status_change(session, 1, "CONFIRMED", sub_order_id=children[0])
        history = session.exec(select(OrderHistory)).one()
        for _ in range(2):
            notify_transition(session, history, 2, order_id, "Replayed.", f"/orders/{order_id}")
        session.commit()

    assert len(notifications_for(engine, 2)) == 1


def test_buyer_cancellation_notifies_each_shop_about_its_own_sub_order(engine):
    order_id, children, _ = purchase(engine, shops=2)
    with Session(engine) as session:
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")

    assert notifications_for(engine, 2) == []
    for seller_id, child_id in zip((1, 4), children, strict=True):
        messages = [
            row.message
            for row in notifications_for(engine, seller_id)
            if row.event_key.startswith("order-history:")
        ]
        assert messages == [f"The buyer cancelled seller order #{child_id} in order #{order_id}."]


def test_buyer_delivery_confirmation_notifies_seller(api, engine):
    order_id, children, _ = purchase(engine)
    with Session(engine) as session:
        for status in ("PROCESSING", "SHIPPED", "DELIVERED"):
            workflow.seller_status_change(session, 1, status, sub_order_id=children[0])

    response = api.patch(
        f"/api/v1/orders/{order_id}/status",
        json={"status": "COMPLETED"},
        headers=headers(engine, 2),
    )
    assert response.status_code == 200, response.text

    with Session(engine) as session:
        history = session.exec(
            select(OrderHistory).where(OrderHistory.to_status == "COMPLETED")
        ).one()
    notification = next(
        row for row in notifications_for(engine, 1) if row.event_key.startswith("order-history:")
    )
    assert notification.event_key == f"order-history:{history.id}:recipient:1:event:status"
    assert notification.message == (
        f"The buyer confirmed receipt of seller order #{children[0]} in order #{order_id}."
    )
    assert notification.target_path == "/seller/orders"
