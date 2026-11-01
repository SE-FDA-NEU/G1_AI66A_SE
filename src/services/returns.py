"""Return and refund service logic."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.models.order import Order
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.repositories import returns as repository
from src.schemas.returns import CreateReturnRequest, ReturnDecisionRequest, ReturnRequestData
from src.services.inventory import restore_order_item_stock
from src.services.notifications import create_notification
from src.services.order_history import record_transition
from src.services.payments import (
    PaymentError,
    pause_settlement,
    refund_seller_order,
    resume_settlement,
    sync_parent_payment,
    try_release,
    void_settlement,
)

# Payment states a return decision can settle without reconciliation.
RECONCILED_PAYMENTS = frozenset({"PAID", "UNPAID", "FAILED"})


class ReturnError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code, self.message, self.status = code, message, status


def _to_return_data(
    ret_req: ReturnRequest,
    seller_order: SellerOrder,
    order: Order,
) -> ReturnRequestData:
    return ReturnRequestData(
        id=ret_req.id,  # type: ignore
        order_id=ret_req.order_id,
        seller_order_id=ret_req.seller_order_id,
        buyer_id=ret_req.buyer_id,
        reason=ret_req.reason,
        evidence=ret_req.evidence,
        status=ret_req.status,
        decision_notes=ret_req.decision_notes,
        decided_by_user_id=ret_req.decided_by_user_id,
        is_restockable=ret_req.is_restockable,
        created_at=ret_req.created_at,
        decided_at=ret_req.decided_at,
        escrow_status=seller_order.escrow_status,
        payment_status=seller_order.payment_status,
        seller_order_status=seller_order.status,
    )


def sync_parent_order_state(
    session: Session, order: Order, *, occurred_at: datetime | None = None
) -> None:
    """Derive parent order status, payment status, and escrow status from all seller orders."""
    child_orders = session.exec(select(SellerOrder).where(SellerOrder.order_id == order.id)).all()
    if not child_orders:
        return

    statuses = {child.status for child in child_orders}

    # 1. Derive parent order.status
    if statuses == {"COMPLETED"}:
        order.status = "COMPLETED"
        if not order.completed_at:
            order.completed_at = occurred_at or datetime.now(UTC)
    elif statuses == {"CANCELLED"}:
        order.status = "CANCELLED"
    elif statuses == {"RETURNED_REFUNDED"}:
        order.status = "RETURNED_REFUNDED"
    elif "RETURN_REQUESTED" in statuses:
        order.status = "RETURN_REQUESTED"
    elif statuses == {"DELIVERED"}:
        order.status = "DELIVERED"
        if not order.delivered_at:
            order.delivered_at = occurred_at or datetime.now(UTC)
    elif statuses == {"SHIPPED"}:
        order.status = "SHIPPED"
        if not order.shipped_at:
            order.shipped_at = occurred_at or datetime.now(UTC)
    elif statuses == {"CONFIRMED"}:
        order.status = "CONFIRMED"
    elif "CANCELLATION_REQUESTED" in statuses:
        order.status = "CANCELLATION_REQUESTED"
    elif (statuses - {"CANCELLED", "RETURNED_REFUNDED"}) == {"DELIVERED"}:
        order.status = "DELIVERED"
    elif (statuses - {"CANCELLED", "RETURNED_REFUNDED"}) == {"COMPLETED"}:
        order.status = "COMPLETED"
    elif statuses & {"PROCESSING", "CONFIRMED", "SHIPPED", "DELIVERED", "COMPLETED"}:
        order.status = "PROCESSING"
    else:
        order.status = "PENDING"

    # 2. Payment and escrow summaries belong to the payment service (US20).
    sync_parent_payment(session, order)


def submit_return_request(
    session: Session,
    current_user: User,
    order_id: int,
    payload: CreateReturnRequest,
) -> ReturnRequestData:
    if getattr(current_user, "status", "ACTIVE") != "ACTIVE":
        raise ReturnError("ERR_ACCOUNT_RESTRICTED", "This account is restricted.", 403)
    order = session.get(Order, order_id)
    if order is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
    if order.buyer_id != current_user.id:
        raise ReturnError("ERR_FORBIDDEN", "You do not own this order.", 403)

    if payload.seller_order_id is not None:
        seller_order = session.exec(
            select(SellerOrder).where(
                SellerOrder.id == payload.seller_order_id,
                SellerOrder.order_id == order.id,
            )
        ).first()
        if seller_order is None:
            raise ReturnError("ERR_ORDER_NOT_FOUND", "Seller order not found.", 404)
    else:
        sub_orders = session.exec(select(SellerOrder).where(SellerOrder.order_id == order.id)).all()
        if len(sub_orders) == 1:
            seller_order = sub_orders[0]
        elif len(sub_orders) == 0:
            raise ReturnError("ERR_ORDER_NOT_FOUND", "No seller orders found for this order.", 404)
        else:
            raise ReturnError("ERR_BAD_REQUEST", "Please specify seller_order_id.", 400)

    # Check existing pending requests before attempting write
    existing = session.exec(
        select(ReturnRequest).where(
            ReturnRequest.seller_order_id == seller_order.id,
            ReturnRequest.status == "PENDING",
        )
    ).first()
    if existing is not None or seller_order.status == "RETURN_REQUESTED":
        raise ReturnError(
            "ERR_CONFLICT",
            "A return request is already pending review for this order.",
            409,
        )

    if seller_order.status != "DELIVERED":
        raise ReturnError(
            "ERR_INVALID_TRANSITION",
            (
                "Return request is only allowed for delivered orders "
                f"(current: {seller_order.status})."
            ),
            400,
        )

    # Atomic conditional state transition on SellerOrder to prevent race conditions
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            SellerOrder.status == "DELIVERED",
        )
        .values(
            status="RETURN_REQUESTED",
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise ReturnError(
            "ERR_CONFLICT",
            "A return request is already pending review for this order.",
            409,
        )
    session.refresh(seller_order)
    pause_settlement(session, seller_order)

    ret_req = ReturnRequest(
        order_id=order.id,
        seller_order_id=seller_order.id,
        buyer_id=current_user.id,
        reason=payload.reason,
        evidence=payload.evidence,
        status="PENDING",
    )
    session.add(ret_req)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        integrity_message = str(exc)
        if not (
            "uq_return_requests_seller_order_pending" in integrity_message
            or "return_requests.seller_order_id" in integrity_message
        ):
            raise
        raise ReturnError(
            "ERR_CONFLICT",
            "A return request is already pending review for this order.",
            409,
        ) from exc

    session.refresh(seller_order)

    # Derive parent order state from all child seller orders
    sync_parent_order_state(session, order)

    record_transition(
        session,
        seller_order_id=seller_order.id,
        from_status="DELIVERED",
        to_status="RETURN_REQUESTED",
        actor=current_user,
        note=f"Buyer submitted return request: {payload.reason}",
    )

    create_notification(
        session,
        recipient_user_id=seller_order.seller_id,
        order_id=order.id,
        event_key=f"return_request:{ret_req.id}:created",
        message=(
            f"Buyer requested return for order #{order.id} "
            f"(sub-order #{seller_order.id}). Reason: {payload.reason}"
        ),
        target_path="/seller/orders",
    )

    session.commit()
    session.refresh(ret_req)
    session.refresh(seller_order)
    session.refresh(order)
    return _to_return_data(ret_req, seller_order, order)


def get_return_request(
    session: Session,
    current_user: User,
    return_request_id: int,
) -> ReturnRequestData:
    ret_req = session.get(ReturnRequest, return_request_id)
    if ret_req is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Return request not found.", 404)

    seller_order = session.get(SellerOrder, ret_req.seller_order_id)
    order = session.get(Order, ret_req.order_id)
    if seller_order is None or order is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Associated order not found.", 404)

    if current_user.role == "admin":
        pass
    elif current_user.role == "buyer" and ret_req.buyer_id == current_user.id:
        pass
    elif current_user.role == "seller" and seller_order.seller_id == current_user.id:
        pass
    else:
        raise ReturnError(
            "ERR_FORBIDDEN",
            "You are not authorized to view this return request.",
            403,
        )

    return _to_return_data(ret_req, seller_order, order)


def list_order_return_requests(
    session: Session,
    current_user: User,
    order_id: int,
) -> list[ReturnRequestData]:
    order = session.get(Order, order_id)
    if order is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)

    sub_orders = session.exec(select(SellerOrder).where(SellerOrder.order_id == order.id)).all()
    sub_order_map = {so.id: so for so in sub_orders}

    if current_user.role == "admin":
        pass
    elif current_user.role == "buyer" and order.buyer_id == current_user.id:
        pass
    elif current_user.role == "seller" and any(
        so.seller_id == current_user.id for so in sub_orders
    ):
        pass
    else:
        raise ReturnError(
            "ERR_FORBIDDEN",
            "You are not authorized to view this order's return requests.",
            403,
        )

    query = select(ReturnRequest).where(ReturnRequest.order_id == order.id)
    if current_user.role == "seller":
        owned_sub_ids = [so.id for so in sub_orders if so.seller_id == current_user.id]
        query = query.where(ReturnRequest.seller_order_id.in_(owned_sub_ids))

    records = session.exec(query.order_by(ReturnRequest.created_at.desc())).all()
    return [_to_return_data(r, sub_order_map[r.seller_order_id], order) for r in records]


def _update_seller_order(
    session: Session, seller_order: SellerOrder, values: dict[str, object]
) -> None:
    """Compare-and-set from the state the decision was based on."""
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            SellerOrder.status == "RETURN_REQUESTED",
            SellerOrder.payment_status == seller_order.payment_status,
            SellerOrder.escrow_status == seller_order.escrow_status,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise ReturnError(
            "ERR_CONCURRENCY_CONFLICT",
            "The seller order changed. Please refresh and retry.",
            409,
        )
    session.refresh(seller_order)


def check_return_settlement(seller_order: SellerOrder, action: str) -> None:
    """Reject a decision before any write; shared by seller and admin dispute paths."""
    if seller_order.status != "RETURN_REQUESTED":
        raise ReturnError(
            "ERR_INVALID_TRANSITION",
            "The seller order is no longer awaiting a return decision.",
            400,
        )
    if action == "APPROVE" and seller_order.payment_status not in RECONCILED_PAYMENTS:
        raise ReturnError(
            "ERR_INVALID_PAYMENT_STATE",
            "Payment needs reconciliation before the return can be approved.",
            409,
        )


def settle_return(
    session: Session, seller_order: SellerOrder, action: str, now: datetime, actor_id: int
) -> bool:
    """Apply the US20 section 6 return rows; returns whether a payment was refunded."""
    check_return_settlement(seller_order, action)
    try:
        if action == "APPROVE":
            _update_seller_order(session, seller_order, {"status": "RETURNED_REFUNDED"})
            # Only a collected payment is refunded; the escrow is voided either way.
            refunded = refund_seller_order(session, seller_order, actor_id)
            void_settlement(session, seller_order)
            return refunded
        _update_seller_order(
            session,
            seller_order,
            {"status": "COMPLETED", "completed_at": seller_order.completed_at or now},
        )
        resume_settlement(session, seller_order)
        try_release(session, seller_order)
        return False
    except PaymentError as exc:
        raise ReturnError(exc.code, exc.message, exc.status) from exc


def restock_return_items(session: Session, seller_order_id: int) -> None:
    """Restore the purchased inventory unit and counters without committing."""
    for item in repository.purchased_items(session, seller_order_id):
        restore_order_item_stock(session, item)
        repository.reduce_sold_count(session, item)


def decide_return_request(
    session: Session,
    current_user: User,
    return_request_id: int,
    decision: ReturnDecisionRequest,
) -> ReturnRequestData:
    if getattr(current_user, "status", "ACTIVE") != "ACTIVE":
        raise ReturnError("ERR_ACCOUNT_RESTRICTED", "This account is restricted.", 403)
    ret_req = session.get(ReturnRequest, return_request_id)
    if ret_req is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Return request not found.", 404)

    seller_order = session.get(SellerOrder, ret_req.seller_order_id)
    order = session.get(Order, ret_req.order_id)
    if seller_order is None or order is None:
        raise ReturnError("ERR_ORDER_NOT_FOUND", "Associated order not found.", 404)

    if current_user.role == "admin":
        pass
    elif current_user.role == "seller" and seller_order.seller_id == current_user.id:
        pass
    else:
        raise ReturnError(
            "ERR_FORBIDDEN",
            "You are not authorized to review or decide this return request.",
            403,
        )

    if ret_req.status != "PENDING":
        raise ReturnError(
            "ERR_INVALID_TRANSITION",
            "Return request has already been resolved.",
            400,
        )

    check_return_settlement(seller_order, decision.action)

    old_status = seller_order.status
    now = datetime.now(UTC)
    target_status = "APPROVED" if decision.action == "APPROVE" else "REJECTED"

    # Atomic conditional update on ReturnRequest to serialize concurrent approvals/rejections
    changed = session.exec(
        update(ReturnRequest)
        .where(
            ReturnRequest.id == ret_req.id,
            ReturnRequest.status == "PENDING",
        )
        .values(
            status=target_status,
            decided_by_user_id=current_user.id,
            decided_at=now,
            decision_notes=decision.decision_notes,
            is_restockable=decision.is_restockable if decision.action == "APPROVE" else False,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise ReturnError(
            "ERR_INVALID_TRANSITION",
            "Return request has already been resolved.",
            400,
        )

    refunds_payment = settle_return(session, seller_order, decision.action, now, current_user.id)

    if decision.action == "APPROVE":
        if decision.is_restockable:
            restock_return_items(session, seller_order.id)
            note = "Return approved. Inventory restored."
        else:
            note = "Return approved. Inventory not increased."

        record_transition(
            session,
            seller_order_id=seller_order.id,
            from_status=old_status,
            to_status="RETURNED_REFUNDED",
            actor=current_user,
            note=note,
            occurred_at=now,
        )

        create_notification(
            session,
            recipient_user_id=order.buyer_id,
            order_id=order.id,
            event_key=f"return_request:{ret_req.id}:approved",
            message=(
                f"Your return request for order #{order.id} (sub-order #{seller_order.id}) "
                "has been approved. "
                + (
                    "The payment has been refunded."
                    if refunds_payment
                    else "No payment was collected, so nothing is refunded."
                )
            ),
            target_path=f"/orders/{order.id}",
        )
    else:  # REJECT
        note = f"Return rejected: {decision.decision_notes or 'Not approved.'}"
        record_transition(
            session,
            seller_order_id=seller_order.id,
            from_status=old_status,
            to_status="COMPLETED",
            actor=current_user,
            note=note,
            occurred_at=now,
        )

        create_notification(
            session,
            recipient_user_id=order.buyer_id,
            order_id=order.id,
            event_key=f"return_request:{ret_req.id}:rejected",
            message=(
                f"Your return request for order #{order.id} (sub-order #{seller_order.id}) "
                f"was rejected. Reason: {decision.decision_notes or 'Request rejected.'}"
            ),
            target_path=f"/orders/{order.id}",
        )

    # Derive parent milestones from the same instant as the decision history.
    sync_parent_order_state(session, order, occurred_at=now)

    session.commit()
    session.refresh(ret_req)
    session.refresh(seller_order)
    session.refresh(order)
    return _to_return_data(ret_req, seller_order, order)
