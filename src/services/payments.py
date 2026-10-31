"""US20 payment status, escrow and seller settlement (#148, docs/us20-payments.md).

Every write of `payment_status`, `escrow_status`, `refunded_amount` and `settled_at`
goes through this module. Functions take the caller's session and may flush; they never
commit or roll back, so each workflow keeps its single transaction. Changes are
conditional updates on the state the caller read, and results are deduplicated by the
unique `payment_events.event_key`.

No payment provider is integrated this sprint: COD is tracked when the seller order is
delivered, and VIETQR/WALLET/CARD are tracked demo methods whose results are recorded
by the local operator command (`python -m src.payments`).
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import exists, update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from src.models.order import Order
from src.models.payment_event import PaymentEvent
from src.models.seller_order import SellerOrder
from src.services.order_errors import OrderError

PaymentMethod = Literal["COD", "VIETQR", "WALLET", "CARD"]
PAYMENT_METHODS = frozenset({"COD", "VIETQR", "WALLET", "CARD"})
PAYMENT_STATUSES = frozenset({"UNPAID", "PAID", "FAILED", "REFUND_PENDING", "REFUNDED"})
ESCROW_STATUSES = frozenset({"HELD", "PAUSED", "RELEASED", "VOIDED"})
DEFAULT_PAYMENT_METHOD = "COD"

# Decision D1 (pending confirmation in #112): one named rate, snapshotted per seller order.
COMMISSION_RATE_BPS = 500
BASIS_POINTS = 10_000

# Section 2.2: every other payment status change is rejected.
PAYMENT_TRANSITIONS = frozenset(
    {
        ("UNPAID", "PAID"),
        ("UNPAID", "FAILED"),
        ("FAILED", "UNPAID"),
        ("PAID", "REFUND_PENDING"),
        ("REFUND_PENDING", "REFUNDED"),
        ("REFUND_PENDING", "PAID"),
    }
)
TERMINAL_STATUSES = frozenset({"CANCELLED", "RETURNED_REFUNDED"})
PaymentResult = Literal["PAID", "FAILED", "RETRY"]


class PaymentError(OrderError):
    """A payment change the state machine does not allow."""


def _invalid(message: str) -> PaymentError:
    return PaymentError("ERR_INVALID_TRANSITION", message, 409)


def is_legacy(order: Order) -> bool:
    """Orders placed before US20 have no method; their stored PAID is not evidence (I8)."""
    return order.payment_method is None


def calculate_seller_net(basis: int, rate_bps: int) -> tuple[int, int]:
    """Section 4: commission is floored; platform-funded discounts are never deducted."""
    if basis < 0 or not 0 <= rate_bps <= BASIS_POINTS:
        raise ValueError("Basis must be >= 0 and the rate within 0-10000 bps.")
    commission = basis * rate_bps // BASIS_POINTS
    return commission, basis - commission


def _record_event(
    session: Session,
    seller_order: SellerOrder | None,
    order_id: int,
    *,
    event_key: str,
    kind: str,
    source: str,
    from_status: str,
    to_status: str,
    amount: int,
    actor_id: int | None,
) -> bool:
    """Insert the event first; False means a duplicate key, so the caller writes nothing."""
    result = session.exec(
        insert(PaymentEvent)
        .values(
            order_id=order_id,
            seller_order_id=seller_order.id if seller_order else None,
            event_key=event_key,
            kind=kind,
            source=source,
            from_status=from_status,
            to_status=to_status,
            amount=amount,
            actor_user_id=actor_id,
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["event_key"])
    )
    return result.rowcount == 1


def _change(session: Session, seller_order: SellerOrder, expected: dict, values: dict) -> bool:
    """Compare-and-set on the seller order; False when another transaction got there first."""
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            *(getattr(SellerOrder, name) == value for name, value in expected.items()),
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount == 1:
        session.refresh(seller_order)
        return True
    return False


def _set_payment(
    session: Session, seller_order: SellerOrder, to_status: str, **values: object
) -> bool:
    from_status = seller_order.payment_status
    if to_status not in PAYMENT_STATUSES or (from_status, to_status) not in PAYMENT_TRANSITIONS:
        raise _invalid(f"Payment status cannot change from {from_status} to {to_status}.")
    return _change(
        session,
        seller_order,
        {"payment_status": from_status},
        {"payment_status": to_status, **values},
    )


def start_payment(
    session: Session, order: Order, seller_orders: list[SellerOrder], method: str
) -> None:
    """Section 3: store the method, the initial states and each seller's settlement snapshot."""
    if method not in PAYMENT_METHODS:
        raise _invalid(f"Unsupported payment method {method}.")
    order.payment_method = method
    order.payment_status = "UNPAID"
    order.escrow_status = "HELD"
    session.add(order)
    for seller_order in seller_orders:
        commission, net = calculate_seller_net(
            seller_order.subtotal - seller_order.shop_discount, COMMISSION_RATE_BPS
        )
        seller_order.payment_status = "UNPAID"
        seller_order.escrow_status = "HELD"
        seller_order.commission_rate_bps = COMMISSION_RATE_BPS
        seller_order.commission_amount = commission
        seller_order.seller_net_amount = net
        session.add(seller_order)
    session.flush()
    for seller_order in seller_orders:
        if seller_order.total_amount == 0:
            # Nothing to collect, whatever the method.
            _apply_paid(
                session,
                order,
                seller_order,
                "ZERO_TOTAL",
                f"zero-total:seller-order:{seller_order.id}",
                None,
            )
    sync_parent_payment(session, order)


def _apply_paid(
    session: Session,
    order: Order,
    seller_order: SellerOrder,
    source: str,
    event_key: str,
    actor_id: int | None,
) -> bool:
    if seller_order.payment_status != "UNPAID":
        return False
    if not _record_event(
        session,
        seller_order,
        order.id,
        event_key=event_key,
        kind="PAYMENT_RESULT",
        source=source,
        from_status="UNPAID",
        to_status="PAID",
        amount=seller_order.total_amount,
        actor_id=actor_id,
    ):
        return False
    if not _set_payment(session, seller_order, "PAID"):
        raise PaymentError("ERR_CONCURRENCY_CONFLICT", "The payment changed. Please retry.")
    if seller_order.status in TERMINAL_STATUSES:
        # Section 6: a payment that arrives after cancellation or return is refunded once.
        refund_seller_order(session, seller_order, actor_id)
    else:
        try_release(session, seller_order)
    return True


def collect_cod(
    session: Session, order: Order, seller_order: SellerOrder, actor_id: int | None
) -> bool:
    """Decision D2: COD is paid when this seller order is delivered (or completed)."""
    if order.payment_method != "COD":
        return False
    return _apply_paid(
        session,
        order,
        seller_order,
        "COD_COLLECTED",
        f"cod:seller-order:{seller_order.id}",
        actor_id,
    )


def record_payment_result(
    session: Session,
    order_id: int,
    result: str,
    source: str,
    event_key: str,
    actor_id: int | None = None,
) -> Order:
    """A prepaid result for the whole order (section 7); duplicates change nothing."""
    order = session.get(Order, order_id)
    if order is None:
        raise PaymentError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
    if is_legacy(order):
        raise _invalid("Orders placed before payment tracking cannot record payment results.")
    if result not in ("PAID", "FAILED", "RETRY"):
        raise _invalid(f"Unsupported payment result {result}.")
    children = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == order.id).order_by(SellerOrder.id)
    ).all()
    before = order.payment_status
    if result == "PAID":
        targets = [c for c in children if c.payment_status == "UNPAID"]
    else:
        source_status, to_status = (
            ("UNPAID", "FAILED") if result == "FAILED" else ("FAILED", "UNPAID")
        )
        targets = [
            c
            for c in children
            if c.payment_status == source_status and c.status not in TERMINAL_STATUSES
        ]
    to_parent = {"PAID": "PAID", "FAILED": "FAILED", "RETRY": "UNPAID"}[result]
    # Ignored results are still written, with from = to, so the audit trail is complete.
    if not _record_event(
        session,
        None,
        order.id,
        event_key=event_key,
        kind="PAYMENT_RESULT",
        source=source,
        from_status=before,
        to_status=to_parent if targets else before,
        amount=sum(c.total_amount for c in targets) if result == "PAID" else 0,
        actor_id=actor_id,
    ):
        return order
    for child in targets:
        if result == "PAID":
            if not _set_payment(session, child, "PAID"):
                raise PaymentError("ERR_CONCURRENCY_CONFLICT", "The payment changed. Please retry.")
            if child.status in TERMINAL_STATUSES:
                refund_seller_order(session, child, actor_id)
            else:
                try_release(session, child)
        elif not _set_payment(session, child, to_status):
            raise PaymentError("ERR_CONCURRENCY_CONFLICT", "The payment changed. Please retry.")
    sync_parent_payment(session, order)
    return order


def refund_seller_order(session: Session, seller_order: SellerOrder, actor_id: int | None) -> bool:
    """Decision D3: refund the whole seller-order total, exactly once (R1, R2)."""
    order = session.get(Order, seller_order.order_id)
    if order is None or is_legacy(order) or seller_order.payment_status != "PAID":
        return False
    amount = seller_order.total_amount
    if not _record_event(
        session,
        seller_order,
        order.id,
        event_key=f"refund:seller-order:{seller_order.id}",
        kind="REFUND",
        source="TRACKED_REFUND",
        from_status="PAID",
        to_status="REFUNDED",
        amount=amount,
        actor_id=actor_id,
    ):
        return False
    # Tracked mode: the refund succeeds in this transaction, so both steps run here.
    if not _set_payment(session, seller_order, "REFUND_PENDING") or not _set_payment(
        session, seller_order, "REFUNDED", refunded_amount=amount
    ):
        raise PaymentError("ERR_CONCURRENCY_CONFLICT", "The payment changed. Please retry.")
    return True


def void_settlement(session: Session, seller_order: SellerOrder) -> None:
    """Cancelled or returned seller orders are never settled (I2)."""
    if seller_order.escrow_status == "RELEASED":
        raise _invalid("Released escrow cannot be voided.")
    if seller_order.escrow_status != "VOIDED":
        _change(
            session,
            seller_order,
            {"escrow_status": seller_order.escrow_status},
            {"escrow_status": "VOIDED"},
        )


def pause_settlement(session: Session, seller_order: SellerOrder) -> bool:
    """A return under review holds the escrow (R4)."""
    return _change(session, seller_order, {"escrow_status": "HELD"}, {"escrow_status": "PAUSED"})


def resume_settlement(session: Session, seller_order: SellerOrder) -> None:
    """A rejected return goes back to HELD; the caller then runs the release guard."""
    _change(session, seller_order, {"escrow_status": "PAUSED"}, {"escrow_status": "HELD"})


def try_release(session: Session, seller_order: SellerOrder) -> bool:
    """Section 5 release guard: the rowcount decides whether the release happened."""
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            SellerOrder.status == "COMPLETED",
            SellerOrder.payment_status == "PAID",
            SellerOrder.escrow_status == "HELD",
            exists().where(Order.id == SellerOrder.order_id, Order.payment_method.is_not(None)),
        )
        .values(escrow_status="RELEASED", settled_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount == 1:
        session.refresh(seller_order)
        return True
    return False


def summarize_payment(children: list[SellerOrder]) -> str:
    """Section 2.2 parent summary; uncollected cancelled shares do not affect the others."""
    counted = [
        c
        for c in children
        if not (c.status in TERMINAL_STATUSES and c.payment_status in ("UNPAID", "FAILED"))
    ] or children
    values = {c.payment_status for c in counted}
    if "REFUND_PENDING" in values:
        return "REFUND_PENDING"
    if values == {"REFUNDED"}:
        return "REFUNDED"
    for status in ("UNPAID", "FAILED"):
        if status in values:
            return status
    return "PAID"


def summarize_escrow(children: list[SellerOrder]) -> str:
    """Section 2.3 display summary; never used for settlement or analytics."""
    values = {c.escrow_status for c in children}
    if "PAUSED" in values:
        return "PAUSED"
    if len(values) == 1 and values <= {"RELEASED", "VOIDED"}:
        return values.pop()
    if "HELD" in values:
        return "HELD"
    return "PARTIALLY_SETTLED"


def sync_parent_payment(session: Session, order: Order) -> None:
    """Rebuild, never increment, the parent summary from all seller orders (I6)."""
    session.flush()
    children = session.exec(select(SellerOrder).where(SellerOrder.order_id == order.id)).all()
    if not children:
        return
    if not is_legacy(order):
        order.payment_status = summarize_payment(children)
    order.escrow_status = summarize_escrow(children)
    session.add(order)
