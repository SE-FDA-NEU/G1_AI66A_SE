"""Payment states, escrow release and seller settlement (#148, docs/us20-payments.md)."""

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

import src.services.order_workflow as workflow
from src.database import migrate_db
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.payment_event import PaymentEvent
from src.models.seller_order import SellerOrder
from src.payments import main as operator_command
from src.schemas.orders import CheckoutRequest
from src.services.orders import checkout
from src.services.payments import (
    COMMISSION_RATE_BPS,
    PaymentError,
    calculate_seller_net,
    record_payment_result,
    summarize_escrow,
    summarize_payment,
)
from tests import test_atomic_cancellation as cancellation
from tests.cart_db import BUYER_ID, SELLER_ID, add_product
from tests.test_checkout import BODY, headers

api = cancellation.api
engine = cancellation.engine


def place(engine, method=None, *, price=100_000, quantity=2, key="pay"):
    product_id = add_product(engine, f"PAY-{key}", price=price, stock=10)
    with Session(engine) as session:
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=quantity))
        session.commit()
        body = BODY | ({"payment_method": method} if method else {})
        order, _ = checkout(session, BUYER_ID, CheckoutRequest(**body), key)
        return order.id, order.sub_orders[0].id


def state(engine, seller_order_id):
    with Session(engine) as session:
        child = session.get(SellerOrder, seller_order_id)
        parent = session.get(Order, child.order_id)
        events = session.exec(
            select(PaymentEvent.event_key, PaymentEvent.kind).order_by(PaymentEvent.id)
        ).all()
        return {
            "child": (child.status, child.payment_status, child.escrow_status),
            "parent": (parent.payment_status, parent.escrow_status),
            "refunded": child.refunded_amount,
            "settled": child.settled_at is not None,
            "events": events,
        }


def seller(engine, child_id, *statuses):
    with Session(engine) as session:
        for status in statuses:
            workflow.seller_status_change(session, SELLER_ID, status, sub_order_id=child_id)


def pay(engine, order_id, result="PAID", key="demo-1"):
    with Session(engine) as session:
        record_payment_result(session, order_id, result, "DEMO_OPERATOR", key)
        session.commit()


# --- Section 4: seller net ------------------------------------------------------------


@pytest.mark.parametrize(
    ("basis", "commission", "net"),
    [
        (270_000, 13_500, 256_500),
        (200_000, 10_000, 190_000),
        (180_000, 9_000, 171_000),
        (10_001, 500, 9_501),
        (0, 0, 0),
    ],
)
def test_seller_net_floors_commission(basis, commission, net):
    assert calculate_seller_net(basis, 500) == (commission, net)


def test_checkout_snapshots_commission_without_platform_discounts(engine):
    order_id, child_id = place(engine, "VIETQR", price=90_000)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        order = session.get(Order, order_id)
        assert (order.payment_method, order.payment_status, order.escrow_status) == (
            "VIETQR",
            "UNPAID",
            "HELD",
        )
        assert child.commission_rate_bps == COMMISSION_RATE_BPS
        assert (child.commission_amount, child.seller_net_amount) == calculate_seller_net(
            180_000, child.commission_rate_bps
        )


@pytest.mark.parametrize("method", ["COD", "VIETQR", "WALLET", "CARD"])
def test_each_method_is_stored_unpaid(engine, method):
    order_id, child_id = place(engine, method)

    with Session(engine) as session:
        assert session.get(Order, order_id).payment_method == method
    assert state(engine, child_id)["child"] == ("PENDING", "UNPAID", "HELD")


def test_body_without_method_is_recorded_as_cod(engine):
    order_id, _ = place(engine)

    with Session(engine) as session:
        assert session.get(Order, order_id).payment_method == "COD"


def test_unknown_method_is_a_field_error(api, engine):
    response = api.post(
        "/api/v1/orders", json=BODY | {"payment_method": "CASH"}, headers=headers(engine)
    )

    assert response.status_code == 422


# --- Sections 2 and 5: states and the release guard ------------------------------------


def test_cod_is_paid_on_delivery_and_released_once_on_completion(engine):
    _, child_id = place(engine, "COD")
    seller(engine, child_id, "PROCESSING", "SHIPPED", "DELIVERED")

    delivered = state(engine, child_id)
    assert delivered["child"] == ("DELIVERED", "PAID", "HELD")
    assert delivered["events"] == [(f"cod:seller-order:{child_id}", "PAYMENT_RESULT")]

    seller(engine, child_id, "COMPLETED")
    completed = state(engine, child_id)
    assert completed["child"] == ("COMPLETED", "PAID", "RELEASED")
    assert completed["parent"] == ("PAID", "RELEASED")
    assert completed["settled"] and len(completed["events"]) == 1


def test_buyer_confirmation_from_shipped_collects_cod_and_releases(api, engine):
    order_id, child_id = place(engine, "COD")
    seller(engine, child_id, "PROCESSING", "SHIPPED")

    response = api.post(f"/api/v1/orders/{order_id}/confirm", headers=headers(engine))

    assert response.status_code == 200, response.text
    assert state(engine, child_id)["child"] == ("COMPLETED", "PAID", "RELEASED")


def test_prepaid_order_completed_before_payment_releases_when_paid(engine):
    order_id, child_id = place(engine, "VIETQR")
    seller(engine, child_id, "PROCESSING", "SHIPPED", "DELIVERED", "COMPLETED")
    assert state(engine, child_id)["child"] == ("COMPLETED", "UNPAID", "HELD")

    pay(engine, order_id)

    assert state(engine, child_id)["child"] == ("COMPLETED", "PAID", "RELEASED")


def test_failed_payment_never_overrides_paid_and_duplicates_change_nothing(engine):
    order_id, child_id = place(engine, "WALLET")
    pay(engine, order_id, "FAILED", "attempt-1")
    assert state(engine, child_id)["parent"][0] == "FAILED"
    pay(engine, order_id, "RETRY", "retry-1")
    pay(engine, order_id, "PAID", "attempt-2")
    pay(engine, order_id, "PAID", "attempt-2")
    pay(engine, order_id, "FAILED", "late-failure")

    after = state(engine, child_id)
    assert after["child"][1] == after["parent"][0] == "PAID"
    with Session(engine) as session:
        late = session.exec(
            select(PaymentEvent).where(PaymentEvent.event_key == "late-failure")
        ).one()
        assert late.from_status == late.to_status == "PAID"
        assert len(session.exec(select(PaymentEvent)).all()) == 4


def test_retry_needs_a_failed_attempt(engine):
    order_id, child_id = place(engine, "CARD")

    pay(engine, order_id, "RETRY", "retry-early")

    assert state(engine, child_id)["child"][1] == "UNPAID"


# --- Section 6: cancellation, late payment and returns ---------------------------------


def test_paid_cancellation_refunds_once_across_routes(api, engine):
    order_id, child_id = place(engine, "VIETQR")
    pay(engine, order_id)

    first = api.post(f"/api/v1/orders/{order_id}/cancel", headers=headers(engine))
    second = api.patch(
        f"/api/v1/seller/orders/{child_id}/status",
        json={"status": "CANCELLED"},
        headers=headers(engine, SELLER_ID),
    )

    assert first.status_code == 200 and second.status_code == 400
    after = state(engine, child_id)
    assert after["child"] == ("CANCELLED", "REFUNDED", "VOIDED")
    assert after["refunded"] == 200_000
    assert [kind for _, kind in after["events"]].count("REFUND") == 1


def test_payment_after_cancellation_is_refunded_and_never_settled(engine):
    order_id, child_id = place(engine, "VIETQR")
    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    pay(engine, order_id)

    after = state(engine, child_id)
    assert after["child"] == ("CANCELLED", "REFUNDED", "VOIDED")
    assert not after["settled"]


def test_return_under_review_holds_escrow_until_rejected(api, engine):
    order_id, child_id = place(engine, "VIETQR")
    seller(engine, child_id, "PROCESSING", "SHIPPED", "DELIVERED")
    created = api.post(
        f"/api/v1/orders/{order_id}/returns",
        json={"reason": "Broken", "evidence": "Photo"},
        headers=headers(engine),
    )
    assert created.status_code == 201, created.text

    pay(engine, order_id)
    assert state(engine, child_id)["child"] == ("RETURN_REQUESTED", "PAID", "PAUSED")

    rejected = api.post(
        f"/api/v1/return-requests/{created.json()['data']['id']}/decision",
        json={"action": "REJECT"},
        headers=headers(engine, SELLER_ID),
    )
    assert rejected.status_code == 200, rejected.text
    assert state(engine, child_id)["child"] == ("COMPLETED", "PAID", "RELEASED")


# --- Section 8 and 10: receipts and legacy orders --------------------------------------


def test_receipt_shows_payment_to_buyer_and_settlement_to_seller(api, engine):
    order_id, child_id = place(engine, "VIETQR")
    pay(engine, order_id)

    buyer = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine)).json()["data"]
    shop = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine, SELLER_ID)).json()["data"]

    assert (buyer["payment_method"], buyer["payment_status"], buyer["paid_amount"]) == (
        "VIETQR",
        "PAID",
        200_000,
    )
    assert buyer["sub_orders"][0]["commission_amount"] is None
    assert buyer["sub_orders"][0]["seller_net_amount"] is None
    assert shop["sub_orders"][0]["seller_net_amount"] == 190_000


def make_legacy(engine, order_id):
    with Session(engine) as session:
        session.exec(text(f"UPDATE orders SET payment_method = NULL WHERE id = {order_id}"))
        session.exec(text("UPDATE seller_orders SET payment_status = 'PAID'"))
        session.commit()


def test_legacy_order_is_never_settled_or_refunded(api, engine):
    order_id, child_id = place(engine, "COD")
    make_legacy(engine, order_id)

    receipt = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine)).json()["data"]
    assert (receipt["payment_method"], receipt["payment_status"], receipt["paid_amount"]) == (
        None,
        None,
        None,
    )
    assert receipt["sub_orders"][0]["payment_status"] is None
    with Session(engine) as session, pytest.raises(PaymentError):
        record_payment_result(session, order_id, "PAID", "DEMO_OPERATOR", "legacy")

    seller(engine, child_id, "PROCESSING", "SHIPPED", "DELIVERED", "COMPLETED")
    assert state(engine, child_id)["child"] == ("COMPLETED", "PAID", "HELD")
    assert state(engine, child_id)["events"] == []


def test_legacy_cancellation_voids_without_a_refund(engine):
    order_id, child_id = place(engine, "COD")
    make_legacy(engine, order_id)
    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    after = state(engine, child_id)
    assert after["child"] == ("CANCELLED", "PAID", "VOIDED")
    assert after["events"] == [] and after["refunded"] == 0


# --- Summaries, migration and the operator command -------------------------------------


@pytest.mark.parametrize(
    ("children", "expected"),
    [
        ([("PENDING", "REFUND_PENDING"), ("PENDING", "PAID")], "REFUND_PENDING"),
        ([("CANCELLED", "REFUNDED"), ("RETURNED_REFUNDED", "REFUNDED")], "REFUNDED"),
        ([("CANCELLED", "REFUNDED"), ("PENDING", "PAID")], "PAID"),
        ([("CANCELLED", "UNPAID"), ("PENDING", "PAID")], "PAID"),
        ([("DELIVERED", "PAID"), ("PENDING", "UNPAID")], "UNPAID"),
        ([("PENDING", "FAILED")], "FAILED"),
    ],
)
def test_parent_payment_summary(children, expected):
    rows = [SellerOrder(order_id=1, seller_id=1, status=s, payment_status=p) for s, p in children]
    assert summarize_payment(rows) == expected


@pytest.mark.parametrize(
    ("escrows", "expected"),
    [
        (["PAUSED", "RELEASED"], "PAUSED"),
        (["RELEASED", "RELEASED"], "RELEASED"),
        (["VOIDED", "VOIDED"], "VOIDED"),
        (["HELD", "VOIDED"], "HELD"),
        (["RELEASED", "VOIDED"], "PARTIALLY_SETTLED"),
    ],
)
def test_parent_escrow_summary(escrows, expected):
    rows = [SellerOrder(order_id=1, seller_id=1, status="X", escrow_status=e) for e in escrows]
    assert summarize_escrow(rows) == expected


def test_migration_maps_old_values_and_is_repeatable(engine):
    order_id, child_id = place(engine, "COD")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE seller_orders SET status = 'CANCELLED', escrow_status = 'HELD'; ")
        )
        connection.execute(
            text(
                "UPDATE orders SET payment_status = 'PARTIALLY_REFUNDED', "
                "escrow_status = 'REFUNDED'"
            )
        )
    for _ in range(2):
        with engine.begin() as connection:
            migrate_db(connection)

    with Session(engine) as session:
        assert session.get(SellerOrder, child_id).escrow_status == "VOIDED"
        order = session.get(Order, order_id)
        assert (order.payment_status, order.escrow_status) == ("PAID", "VOIDED")


def test_operator_command_rejects_an_unknown_order(capsys):
    assert (
        operator_command(
            ["record-result", "--order", "999999", "--result", "PAID", "--event-key", "missing"]
        )
        == 1
    )
    assert "ERR_ORDER_NOT_FOUND" in capsys.readouterr().err
