"""Payment events in either order and concurrently (US20 sections 6.2 and 6.3, #148 review).

Each scenario checks invariants I1–I6 and I8 after every step, not only at the end. The
exhaustive matrix of section 6.1 remains tracked in #150.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlmodel import Session, func, select

import src.services.order_workflow as workflow
from src.models.order import Order
from src.models.payment_event import PaymentEvent
from src.models.seller_order import SellerOrder
from src.services.payments import record_payment_result, summarize_escrow, summarize_payment
from tests import test_payments as payments
from tests.cart_db import BUYER_ID, SELLER_ID
from tests.test_checkout import headers

api = payments.api
engine = payments.engine


def check_invariants(engine):
    with Session(engine) as session:
        for order in session.exec(select(Order)):
            children = session.exec(
                select(SellerOrder).where(SellerOrder.order_id == order.id)
            ).all()
            events = session.exec(
                select(PaymentEvent).where(PaymentEvent.order_id == order.id)
            ).all()
            if order.payment_method is None:  # I8
                assert events == []
                assert all(c.escrow_status != "RELEASED" for c in children)
                continue
            for child in children:
                refunds = [
                    e for e in events if e.seller_order_id == child.id and e.kind == "REFUND"
                ]
                if child.escrow_status == "RELEASED":  # I1
                    assert child.status == "COMPLETED" and child.payment_status == "PAID"
                    assert child.settled_at is not None
                if child.status in ("CANCELLED", "RETURNED_REFUNDED"):  # I2
                    assert child.escrow_status == "VOIDED"
                assert len(refunds) <= 1  # I3
                assert child.refunded_amount == (refunds[0].amount if refunds else 0)
                assert (child.payment_status == "REFUNDED") == bool(refunds)  # I4
                assert child.refunded_amount <= child.total_amount  # I5
            assert order.payment_status == summarize_payment(children)  # I6
            assert order.escrow_status == summarize_escrow(children)


class Flow:
    """One prepaid order whose steps can be replayed in any order."""

    def __init__(self, api, engine):
        self.api, self.engine = api, engine
        self.order_id, self.child_id = payments.place(engine, "VIETQR")
        self.return_id = None
        check_invariants(engine)

    def step(self, action):
        getattr(self, action)()
        check_invariants(self.engine)

    def pay(self):
        payments.pay(self.engine, self.order_id, key="demo-paid")

    def cancel(self):
        with Session(self.engine) as session:
            workflow.buyer_cancellation(session, BUYER_ID, self.order_id, "CANCELLED")

    def deliver(self):
        payments.seller(self.engine, self.child_id, "PROCESSING", "SHIPPED", "DELIVERED")

    def complete(self):
        payments.seller(self.engine, self.child_id, "COMPLETED")

    def request_return(self):
        response = self.api.post(
            f"/api/v1/orders/{self.order_id}/returns",
            json={"reason": "Broken", "evidence": "Photo"},
            headers=headers(self.engine),
        )
        assert response.status_code == 201, response.text
        self.return_id = response.json()["data"]["id"]

    def _decide(self, action):
        response = self.api.post(
            f"/api/v1/return-requests/{self.return_id}/decision",
            json={"action": action, "is_restockable": False},
            headers=headers(self.engine, SELLER_ID),
        )
        assert response.status_code == 200, response.text

    def approve(self):
        self._decide("APPROVE")

    def reject(self):
        self._decide("REJECT")

    def final(self):
        with Session(self.engine) as session:
            child = session.get(SellerOrder, self.child_id)
            kinds = session.exec(select(PaymentEvent.kind)).all()
            return (
                (child.status, child.payment_status, child.escrow_status),
                kinds.count("REFUND"),
                child.settled_at is not None,
            )


# Section 6.2: the same end state in either order.
PAIRS = {
    "payment and cancellation": (
        [],
        ["pay"],
        ["cancel"],
        (("CANCELLED", "REFUNDED", "VOIDED"), 1, False),
    ),
    "payment and completion": (
        ["deliver"],
        ["pay"],
        ["complete"],
        (("COMPLETED", "PAID", "RELEASED"), 0, True),
    ),
    "payment and return approval": (
        ["deliver", "request_return"],
        ["pay"],
        ["approve"],
        (("RETURNED_REFUNDED", "REFUNDED", "VOIDED"), 1, False),
    ),
    "payment and return rejection": (
        ["deliver", "request_return"],
        ["pay"],
        ["reject"],
        (("COMPLETED", "PAID", "RELEASED"), 0, True),
    ),
}


@pytest.mark.parametrize("reverse", [False, True], ids=["first-then-second", "second-then-first"])
@pytest.mark.parametrize("pair", PAIRS)
def test_events_reach_the_same_state_in_either_order(api, engine, pair, reverse):
    setup, first, second, expected = PAIRS[pair]
    flow = Flow(api, engine)
    for action in setup + (second + first if reverse else first + second):
        flow.step(action)

    assert flow.final() == expected


def test_same_payment_result_twice_is_identical_to_once(api, engine):
    flow = Flow(api, engine)
    flow.step("pay")
    once = flow.final()
    flow.step("pay")

    assert flow.final() == once
    with Session(engine) as session:
        assert session.exec(select(func.count(PaymentEvent.id))).one() == 1


def test_released_order_is_never_released_or_refunded_again(api, engine):
    """R5: events after release change nothing."""
    flow = Flow(api, engine)
    for action in ("pay", "deliver", "complete"):
        flow.step(action)
    with Session(engine) as session:
        settled_at = session.get(SellerOrder, flow.child_id).settled_at

    flow.step("pay")
    with Session(engine) as session, pytest.raises(workflow.WorkflowError):
        workflow.buyer_cancellation(session, BUYER_ID, flow.order_id, "CANCELLED")
    check_invariants(engine)

    assert flow.final() == (("COMPLETED", "PAID", "RELEASED"), 0, True)
    with Session(engine) as session:
        assert session.get(SellerOrder, flow.child_id).settled_at == settled_at


def run_together(engine, *actions):
    """Start each action on its own connection at the same moment."""
    barrier = Barrier(len(actions))

    def run(action):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                action(session)
                session.commit()
                return "ok"
            except Exception as exc:  # noqa: BLE001 - the loser's error is the result
                session.rollback()
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def test_concurrent_cancellations_refund_exactly_once(api, engine):
    """R2: two refund attempts on independent connections commit one REFUND event."""
    flow = Flow(api, engine)
    flow.step("pay")

    results = run_together(
        engine,
        lambda s: workflow.buyer_cancellation(s, BUYER_ID, flow.order_id, "CANCELLED"),
        lambda s: workflow.seller_status_change(
            s, SELLER_ID, "CANCELLED", sub_order_id=flow.child_id
        ),
    )

    assert "ok" in results
    check_invariants(engine)
    assert flow.final() == (("CANCELLED", "REFUNDED", "VOIDED"), 1, False)


def test_concurrent_payment_and_cancellation_match_either_order(api, engine):
    flow = Flow(api, engine)

    results = run_together(
        engine,
        lambda s: record_payment_result(s, flow.order_id, "PAID", "DEMO_OPERATOR", "demo-paid"),
        lambda s: workflow.buyer_cancellation(s, BUYER_ID, flow.order_id, "CANCELLED"),
    )

    check_invariants(engine)
    if results == ["ok", "ok"]:
        assert flow.final() == PAIRS["payment and cancellation"][3]
    else:
        # A writer that lost the SQLite lock changed nothing; replaying it converges.
        for name, result in zip(("pay", "cancel"), results, strict=True):
            if result != "ok":
                flow.step(name)
        assert flow.final() == PAIRS["payment and cancellation"][3]
