"""Every cell of the US20 section 6.1 matrix: state found -> event -> result (#148 review).

Rows are reached through the real workflow and APIs; each cell then applies one event.
Cells the workflow never delivers ("—" in the contract) must be rejected without writes.
Invariants I1-I6 and I8 are checked after every step.
"""

import pytest
from sqlmodel import Session, select

from src.models.payment_event import PaymentEvent
from src.models.seller_order import SellerOrder
from tests import test_payment_event_order as order_flow
from tests.cart_db import BUYER_ID, SELLER_ID
from tests.test_payment_event_order import Flow, check_invariants, run_together

api = order_flow.api
engine = order_flow.engine

# Rows of section 6.1, as the steps that reach them from a new prepaid order.
ROWS = {
    "pending-unpaid": [],
    "pending-paid": ["pay"],
    "delivered-unpaid": ["deliver"],
    "delivered-paid": ["pay", "deliver"],
    "completed-unpaid": ["deliver", "complete"],
    "return-unpaid": ["deliver", "request_return"],
    "return-paid": ["pay", "deliver", "request_return"],
    "released": ["pay", "deliver", "complete"],
    "cancelled-unpaid": ["cancel"],
    "returned-unpaid": ["deliver", "request_return", "approve"],
    "cancelled-refunded": ["pay", "cancel"],
}

REJECTED = "rejected"
# (row, event) -> (status, payment, escrow, refund events, settled) or REJECTED.
MATRIX = {
    ("pending-unpaid", "late_pay"): ("PENDING", "PAID", "HELD", 0, False),
    ("pending-unpaid", "fail"): ("PENDING", "FAILED", "HELD", 0, False),
    ("pending-unpaid", "cancel"): ("CANCELLED", "UNPAID", "VOIDED", 0, False),
    ("pending-unpaid", "complete"): REJECTED,
    ("pending-paid", "late_pay"): ("PENDING", "PAID", "HELD", 0, False),
    ("pending-paid", "fail"): ("PENDING", "PAID", "HELD", 0, False),
    ("pending-paid", "cancel"): ("CANCELLED", "REFUNDED", "VOIDED", 1, False),
    ("delivered-unpaid", "late_pay"): ("DELIVERED", "PAID", "HELD", 0, False),
    ("delivered-unpaid", "fail"): ("DELIVERED", "FAILED", "HELD", 0, False),
    ("delivered-unpaid", "cancel"): REJECTED,
    ("delivered-unpaid", "complete"): ("COMPLETED", "UNPAID", "HELD", 0, False),
    ("delivered-paid", "late_pay"): ("DELIVERED", "PAID", "HELD", 0, False),
    ("delivered-paid", "fail"): ("DELIVERED", "PAID", "HELD", 0, False),
    ("delivered-paid", "cancel"): REJECTED,
    ("delivered-paid", "complete"): ("COMPLETED", "PAID", "RELEASED", 0, True),
    ("completed-unpaid", "late_pay"): ("COMPLETED", "PAID", "RELEASED", 0, True),
    ("completed-unpaid", "fail"): ("COMPLETED", "FAILED", "HELD", 0, False),
    ("completed-unpaid", "cancel"): REJECTED,
    ("return-unpaid", "late_pay"): ("RETURN_REQUESTED", "PAID", "PAUSED", 0, False),
    ("return-unpaid", "approve"): ("RETURNED_REFUNDED", "UNPAID", "VOIDED", 0, False),
    ("return-unpaid", "reject"): ("COMPLETED", "UNPAID", "HELD", 0, False),
    ("return-unpaid", "cancel"): REJECTED,
    ("return-paid", "late_pay"): ("RETURN_REQUESTED", "PAID", "PAUSED", 0, False),
    ("return-paid", "fail"): ("RETURN_REQUESTED", "PAID", "PAUSED", 0, False),
    ("return-paid", "approve"): ("RETURNED_REFUNDED", "REFUNDED", "VOIDED", 1, False),
    ("return-paid", "reject"): ("COMPLETED", "PAID", "RELEASED", 0, True),
    ("released", "late_pay"): ("COMPLETED", "PAID", "RELEASED", 0, True),
    ("released", "fail"): ("COMPLETED", "PAID", "RELEASED", 0, True),
    ("released", "cancel"): REJECTED,
    ("released", "complete"): REJECTED,
    ("cancelled-unpaid", "late_pay"): ("CANCELLED", "REFUNDED", "VOIDED", 1, False),
    ("cancelled-unpaid", "fail"): ("CANCELLED", "UNPAID", "VOIDED", 0, False),
    ("cancelled-unpaid", "complete"): REJECTED,
    ("returned-unpaid", "late_pay"): ("RETURNED_REFUNDED", "REFUNDED", "VOIDED", 1, False),
    ("returned-unpaid", "fail"): ("RETURNED_REFUNDED", "UNPAID", "VOIDED", 0, False),
    ("cancelled-refunded", "late_pay"): ("CANCELLED", "REFUNDED", "VOIDED", 1, False),
    ("cancelled-refunded", "fail"): ("CANCELLED", "REFUNDED", "VOIDED", 1, False),
    ("cancelled-refunded", "cancel"): REJECTED,
}


class MatrixFlow(Flow):
    def late_pay(self):
        order_flow.payments.pay(self.engine, self.order_id, key="matrix-paid")

    def fail(self):
        order_flow.payments.pay(self.engine, self.order_id, "FAILED", key="matrix-failed")

    def cancel(self):
        # Before shipment the buyer cancels; afterwards only the seller route could try.
        with Session(self.engine) as session:
            child = session.get(SellerOrder, self.child_id)
            if child.status == "PENDING":
                order_flow.workflow.buyer_cancellation(
                    session, BUYER_ID, self.order_id, "CANCELLED"
                )
            else:
                order_flow.workflow.seller_status_change(
                    session, SELLER_ID, "CANCELLED", sub_order_id=self.child_id
                )

    def complete(self):
        with Session(self.engine) as session:
            order_flow.workflow.seller_status_change(
                session, SELLER_ID, "COMPLETED", sub_order_id=self.child_id
            )

    def snapshot(self):
        with Session(self.engine) as session:
            child = session.get(SellerOrder, self.child_id)
            refunds = session.exec(
                select(PaymentEvent).where(
                    PaymentEvent.seller_order_id == self.child_id, PaymentEvent.kind == "REFUND"
                )
            ).all()
            return (
                child.status,
                child.payment_status,
                child.escrow_status,
                len(refunds),
                child.settled_at is not None,
            )


@pytest.mark.parametrize(("row", "event"), list(MATRIX), ids=[f"{r}:{e}" for r, e in MATRIX])
def test_matrix_cell(api, engine, row, event):
    flow = MatrixFlow(api, engine)
    for action in ROWS[row]:
        flow.step(action)
    before = flow.snapshot()
    expected = MATRIX[(row, event)]

    if expected == REJECTED:
        with pytest.raises(order_flow.workflow.WorkflowError):
            getattr(flow, event)()
        check_invariants(engine)
        assert flow.snapshot() == before
        return
    flow.step(event)

    assert flow.snapshot() == expected


def test_every_row_is_covered():
    assert {row for row, _ in MATRIX} == set(ROWS)


# Section 6.2 pairs not yet run concurrently in test_payment_event_order.py.
CONCURRENT = {
    "payment and completion": (["deliver"], "complete", ("COMPLETED", "PAID", "RELEASED", 0, True)),
    "payment and return approval": (
        ["deliver", "request_return"],
        "approve",
        ("RETURNED_REFUNDED", "REFUNDED", "VOIDED", 1, False),
    ),
    "payment and return rejection": (
        ["deliver", "request_return"],
        "reject",
        ("COMPLETED", "PAID", "RELEASED", 0, True),
    ),
}


@pytest.mark.parametrize("pair", CONCURRENT)
def test_payment_concurrent_with_workflow_event(api, engine, pair):
    setup, other, expected = CONCURRENT[pair]
    flow = MatrixFlow(api, engine)
    for action in setup:
        flow.step(action)

    # The API-based return decision uses its own session; run it on the second thread.
    results = run_together(
        engine,
        lambda session: order_flow.record_payment_result(
            session, flow.order_id, "PAID", "DEMO_OPERATOR", "matrix-paid"
        ),
        lambda session: getattr(flow, other)(),
    )

    check_invariants(engine)
    # A writer that lost the SQLite lock changed nothing; replaying it converges.
    for action, result in zip(("late_pay", other), results, strict=True):
        if result != "ok":
            flow.step(action)
    assert flow.snapshot() == expected


def test_same_payment_result_concurrently_is_recorded_once(api, engine):
    flow = MatrixFlow(api, engine)

    results = run_together(
        engine,
        *[
            lambda session: order_flow.record_payment_result(
                session, flow.order_id, "PAID", "DEMO_OPERATOR", "matrix-paid"
            )
        ]
        * 2,
    )

    assert "ok" in results
    check_invariants(engine)
    with Session(engine) as session:
        assert len(session.exec(select(PaymentEvent)).all()) == 1
    assert flow.snapshot() == ("PENDING", "PAID", "HELD", 0, False)
