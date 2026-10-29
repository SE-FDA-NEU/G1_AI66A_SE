"""Return decisions settle only collected payments and leave no partial writes (#140)."""

import pytest
from sqlmodel import Session, select

import src.services.returns as returns
from src.database import engine
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.schemas.returns import ReturnDecisionRequest
from tests import test_return_refund as return_fixtures

# Reuse the seeded delivered order from the return/refund tests.
client = return_fixtures.client
test_setup = return_fixtures.test_setup
_auth = return_fixtures._auth

APPROVE_RESTOCK = {"action": "APPROVE", "decision_notes": "Accepted", "is_restockable": True}


def _set_payment(seller_order_id, payment_status):
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, seller_order_id)
        seller_order.payment_status = payment_status
        session.add(seller_order)
        session.commit()


def _submit(client, setup):
    response = client.post(
        f"/api/v1/orders/{setup['order_id']}/returns",
        headers=_auth(setup["buyer_a"]),
        json={"reason": "Broken on arrival", "evidence": "Photo of the damage"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _decide(client, setup, request_id, body, actor="seller_a"):
    return client.post(
        f"/api/v1/return-requests/{request_id}/decision",
        headers=_auth(setup[actor]),
        json=body,
    )


def _state(setup):
    """Everything a decision may write, read through a fresh session."""
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, setup["seller_order_id"])
        order = session.get(Order, setup["order_id"])
        request = session.exec(select(ReturnRequest)).one()
        return {
            "seller_order": seller_order.model_dump(),
            "order": order.model_dump(),
            "request": request.model_dump(),
            "stock": session.get(Product, setup["product_id"]).stock_quantity,
            "history": len(session.exec(select(OrderHistory)).all()),
            "notifications": len(session.exec(select(Notification)).all()),
        }


def test_approving_unpaid_return_voids_escrow_without_claiming_refund(client, test_setup):
    _set_payment(test_setup["seller_order_id"], "UNPAID")
    request_id = _submit(client, test_setup)

    response = _decide(client, test_setup, request_id, APPROVE_RESTOCK)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert (data["seller_order_status"], data["payment_status"], data["escrow_status"]) == (
        "RETURNED_REFUNDED",
        "UNPAID",
        "VOIDED",
    )
    with Session(engine) as session:
        message = session.exec(
            select(Notification.message).where(Notification.event_key.like("%:approved"))
        ).one()
    assert message.endswith("No payment was collected, so nothing is refunded.")


def test_rejecting_unpaid_return_keeps_escrow_held(client, test_setup):
    _set_payment(test_setup["seller_order_id"], "UNPAID")
    request_id = _submit(client, test_setup)

    response = _decide(client, test_setup, request_id, {"action": "REJECT"})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert (data["seller_order_status"], data["escrow_status"]) == ("COMPLETED", "HELD")
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        assert seller_order.completed_at is not None


def test_rejecting_paid_return_releases_escrow(client, test_setup):
    request_id = _submit(client, test_setup)

    response = _decide(client, test_setup, request_id, {"action": "REJECT"})

    assert response.json()["data"]["escrow_status"] == "RELEASED"


def test_unreconciled_payment_cannot_be_approved(client, test_setup):
    request_id = _submit(client, test_setup)
    _set_payment(test_setup["seller_order_id"], "REFUND_PENDING")
    before = _state(test_setup)

    response = _decide(client, test_setup, request_id, APPROVE_RESTOCK)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ERR_INVALID_PAYMENT_STATE"
    assert _state(test_setup) == before


def test_seller_order_moved_on_cannot_be_decided(client, test_setup):
    request_id = _submit(client, test_setup)
    with Session(engine) as session:
        seller_order = session.get(SellerOrder, test_setup["seller_order_id"])
        seller_order.status = "COMPLETED"
        session.add(seller_order)
        session.commit()
    before = _state(test_setup)

    response = _decide(client, test_setup, request_id, APPROVE_RESTOCK)

    assert response.status_code == 400
    assert _state(test_setup) == before


@pytest.mark.parametrize("actor", ["buyer_a", "buyer_b", "seller_b"])
def test_only_owning_seller_or_admin_can_decide(client, test_setup, actor):
    request_id = _submit(client, test_setup)
    before = _state(test_setup)

    response = _decide(client, test_setup, request_id, APPROVE_RESTOCK, actor=actor)

    assert response.status_code == 403
    assert _state(test_setup) == before


def test_notification_failure_rolls_back_the_whole_decision(client, test_setup, monkeypatch):
    request_id = _submit(client, test_setup)
    before = _state(test_setup)
    original = returns.create_notification

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected notification failure")

    monkeypatch.setattr(returns, "create_notification", fail)
    with Session(engine) as session, pytest.raises(RuntimeError, match="injected"):
        returns.decide_return_request(
            session,
            session.merge(test_setup["seller_a"]),
            request_id,
            ReturnDecisionRequest(**APPROVE_RESTOCK),
        )

    assert _state(test_setup) == before
    monkeypatch.undo()
    assert _decide(client, test_setup, request_id, APPROVE_RESTOCK).status_code == 200


def test_restockable_return_restores_the_ordered_variant(client, test_setup):
    with Session(engine) as session:
        variant = ProductVariant(
            product_id=test_setup["product_id"],
            seller_id=test_setup["seller_a"].id,
            sku="RET-V1",
            name="Blue",
            price=150_000,
            stock_quantity=3,
        )
        session.add(variant)
        session.flush()
        item = session.exec(
            select(OrderItem).where(OrderItem.seller_order_id == test_setup["seller_order_id"])
        ).one()
        item.variant_id = variant.id
        session.add(item)
        session.commit()
        variant_id = variant.id
    request_id = _submit(client, test_setup)

    response = _decide(client, test_setup, request_id, APPROVE_RESTOCK)

    assert response.status_code == 200, response.text
    with Session(engine) as session:
        assert session.get(ProductVariant, variant_id).stock_quantity == 5
        assert session.get(Product, test_setup["product_id"]).stock_quantity == 10
        # The shared fixture deletes products, not variants.
        for item in session.exec(select(OrderItem).where(OrderItem.variant_id == variant_id)):
            session.delete(item)
        session.delete(session.get(ProductVariant, variant_id))
        session.commit()
