"""One transaction for cancellation, inventory, tracked refunds and notifications."""

import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import case, update
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product_metadata import ProductMetadata
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.services.inventory import restore_order_item_stock
from src.services.notifications import notify_transition
from src.services.order_history import record_transition
from src.services.order_states import is_allowed_transition
from src.services.orders import CheckoutError
from src.services.payments import (
    PaymentError,
    collect_cod,
    refund_seller_order,
    try_release,
    void_settlement,
)
from src.services.returns import sync_parent_order_state


class WorkflowError(CheckoutError):
    pass


def _transaction(session: Session, operation: Callable[[], None]) -> None:
    """Auth may already have started the transaction; commit only after every effect."""
    for attempt in range(5):
        try:
            operation()
            session.commit()
            return
        except OperationalError as exc:
            session.rollback()
            busy = (getattr(exc.orig, "sqlite_errorcode", 0) or 0) & 255 in (5, 6)
            if not busy:
                raise
            if attempt == 4:
                raise WorkflowError(
                    "ERR_CONCURRENCY_CONFLICT", "The order changed. Please retry.", 409
                ) from exc
            time.sleep(0.01 * (attempt + 1))
        except Exception:
            session.rollback()
            raise


def _apply_status(
    session: Session,
    parent: Order,
    child: SellerOrder,
    actor_id: int,
    status: str,
    *,
    buyer: bool = False,
    tracking_number: str | None = None,
    audit_note: str | None = None,
) -> None:
    actor = session.get(User, actor_id)
    if actor is None:
        raise WorkflowError("ERR_RESOURCE_OWNER", "The order actor could not be loaded.", 403)
    old_status = child.status
    if not is_allowed_transition("buyer" if buyer else "seller", old_status, status):
        raise WorkflowError(
            "ERR_INVALID_TRANSITION",
            f"Transition from {old_status} to {status} is not allowed.",
            400,
        )
    values: dict[str, object] = {"status": status}
    now = datetime.now(UTC)
    if status in {"SHIPPED", "DELIVERED", "COMPLETED"}:
        values[
            {"SHIPPED": "shipped_at", "DELIVERED": "delivered_at", "COMPLETED": "completed_at"}[
                status
            ]
        ] = now
    if status == "SHIPPED" and tracking_number:
        values["tracking_number"] = tracking_number
    if status == "CANCELLED" and child.payment_status not in {"PAID", "UNPAID", "FAILED"}:
        raise WorkflowError(
            "ERR_INVALID_PAYMENT_STATE", "Payment needs reconciliation before cancellation."
        )
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == child.id,
            SellerOrder.status == old_status,
            SellerOrder.payment_status == child.payment_status,
            SellerOrder.escrow_status == child.escrow_status,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise WorkflowError(
            "ERR_CONCURRENCY_CONFLICT", "The seller order changed. Please refresh and retry."
        )
    session.refresh(child)

    # Payment and escrow effects belong to the payment service, in this transaction.
    refunded = False
    try:
        if status == "CANCELLED":
            refunded = refund_seller_order(session, child, actor_id)
            void_settlement(session, child)
        elif status in {"DELIVERED", "COMPLETED"}:
            collect_cod(session, parent, child, actor_id)
            if status == "COMPLETED":
                try_release(session, child)
    except PaymentError as exc:
        raise WorkflowError(exc.code, exc.message, exc.status) from exc

    note = None
    if status == "CANCELLED":
        items = session.exec(
            select(OrderItem).where(OrderItem.seller_order_id == child.id).order_by(OrderItem.id)
        ).all()
        for item in items:
            restore_order_item_stock(session, item)
            session.exec(
                update(ProductMetadata)
                .where(ProductMetadata.product_id == item.product_id)
                .values(
                    sales_count=case(
                        (ProductMetadata.sales_count < item.quantity, 0),
                        else_=ProductMetadata.sales_count - item.quantity,
                    )
                )
                .execution_options(synchronize_session=False)
            )
        note = "Cancelled by buyer. Stock restored." if buyer else "Stock restored."
        if old_status == "CANCELLATION_REQUESTED":
            note = "Cancellation approved by seller. Stock restored."
        if refunded:
            note += " Tracked payment marked refunded."
    elif status == "CANCELLATION_REQUESTED":
        note = "Cancellation requested by buyer." if buyer else "Cancellation requested."
    elif old_status == "CANCELLATION_REQUESTED":
        note = "Cancellation rejected by seller."
    elif status == "SHIPPED":
        note = f"Shipped. Tracking: {tracking_number}" if tracking_number else "Shipped."
    elif status == "DELIVERED":
        note = "Delivered."
    elif status == "CONFIRMED":
        note = "Confirmed by seller."
    history = record_transition(
        session,
        seller_order_id=child.id,
        from_status=old_status,
        to_status=status,
        actor=actor,
        note=audit_note if audit_note is not None else note,
        occurred_at=now,
    )
    # Notify the other party: the seller when the buyer acts, otherwise the buyer.
    if buyer:
        action = "cancelled" if status == "CANCELLED" else "requested cancellation of"
        notify_transition(
            session,
            history,
            recipient_user_id=child.seller_id,
            order_id=parent.id,
            message=f"The buyer {action} seller order #{child.id} in order #{parent.id}.",
            target_path="/seller/orders",
        )
    else:
        notify_transition(
            session,
            history,
            recipient_user_id=parent.buyer_id,
            order_id=parent.id,
            message=f"Seller order #{child.id} in your order #{parent.id} is now {status.lower()}.",
            target_path=f"/orders/{parent.id}",
        )

def _sync_parent(session: Session, parent: Order) -> None:
    session.flush()
    sync_parent_order_state(session, parent)
    children = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == parent.id).order_by(SellerOrder.id)
    ).all()
    for child in children:
        if child.tracking_number:
            parent.tracking_number = child.tracking_number
    for field in ("shipped_at", "delivered_at", "completed_at"):
        timestamps = [
            getattr(child, field) for child in children if getattr(child, field) is not None
        ]
        if timestamps:
            # SQLite reloads UTC timestamps without tzinfo; compare actual times,
            # including an aware timestamp from the current transaction.
            latest = max(timestamps, key=lambda stamp: stamp.replace(tzinfo=stamp.tzinfo or UTC))
            setattr(parent, field, latest)
    session.add(parent)


def seller_status_change(
    session: Session,
    seller_id: int,
    status: str,
    *,
    sub_order_id: int | None = None,
    order_id: int | None = None,
    tracking_number: str | None = None,
    note: str | None = None,
) -> None:
    """Both seller APIs use the same compare-and-set and cancellation effects."""

    def operation():
        if sub_order_id is not None:
            child = session.get(SellerOrder, sub_order_id)
            if child is None:
                raise WorkflowError("ERR_ORDER_NOT_FOUND", "Seller order was not found.", 404)
            if child.seller_id != seller_id:
                raise WorkflowError("ERR_RESOURCE_OWNER", "You do not own this seller order.", 403)
            children = [child]
            parent_id = child.order_id
        else:
            parent_id = order_id
            children = session.exec(
                select(SellerOrder).where(
                    SellerOrder.order_id == parent_id, SellerOrder.seller_id == seller_id
                )
            ).all()
            if not children:
                raise WorkflowError("ERR_RESOURCE_OWNER", "You do not own this order.", 403)
        parent = session.get(Order, parent_id)
        if parent is None:
            raise WorkflowError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
        for child in children:
            _apply_status(
                session, parent, child, seller_id, status,
                tracking_number=tracking_number, audit_note=note,
            )
        _sync_parent(session, parent)

    _transaction(session, operation)


def buyer_cancellation(
    session: Session, buyer_id: int, order_id: int, status: str, *, note: str | None = None,
) -> None:
    """Cancel all pending children, or only request cancellation after confirmation."""

    def operation():
        parent = session.get(Order, order_id)
        if parent is None or parent.buyer_id != buyer_id:
            raise WorkflowError("ERR_ORDER_NOT_FOUND", "Order not found.", 404)
        children = session.exec(
            select(SellerOrder).where(SellerOrder.order_id == order_id).order_by(SellerOrder.id)
        ).all()
        active = [child for child in children if child.status != "CANCELLED"]
        targets = [
            child for child in active if is_allowed_transition("buyer", child.status, status)
        ]
        # Validate child states too: the parent may still say PENDING after a partial cancel.
        if (
            not targets
            or not is_allowed_transition("buyer", parent.status, status)
            or (status == "CANCELLED" and len(targets) != len(active))
        ):
            raise WorkflowError(
                "ERR_INVALID_TRANSITION", "The order cannot be cancelled in its current state.", 400
            )
        for child in targets:
            _apply_status(session, parent, child, buyer_id, status, buyer=True, audit_note=note)
        _sync_parent(session, parent)

    _transaction(session, operation)
