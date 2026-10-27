"""Return and refund service logic."""

import time
from datetime import UTC, datetime

from sqlalchemy import case, update
from sqlmodel import Session, select

from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.returns import CreateReturnRequest, ReturnDecisionRequest, ReturnRequestData
from src.services.notifications import create_notification


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


def submit_return_request(
    session: Session,
    current_user: User,
    order_id: int,
    payload: CreateReturnRequest,
) -> ReturnRequestData:
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
        sub_orders = session.exec(
            select(SellerOrder).where(SellerOrder.order_id == order.id)
        ).all()
        if len(sub_orders) == 1:
            seller_order = sub_orders[0]
        elif len(sub_orders) == 0:
            raise ReturnError("ERR_ORDER_NOT_FOUND", "No seller orders found for this order.", 404)
        else:
            raise ReturnError("ERR_BAD_REQUEST", "Please specify seller_order_id.", 400)

    existing = session.exec(
        select(ReturnRequest).where(
            ReturnRequest.seller_order_id == seller_order.id,
            ReturnRequest.status == "PENDING",
        )
    ).first()
    if existing is not None:
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

    ret_req = ReturnRequest(
        order_id=order.id,
        seller_order_id=seller_order.id,
        buyer_id=current_user.id,
        reason=payload.reason,
        evidence=payload.evidence,
        status="PENDING",
    )
    session.add(ret_req)
    session.flush()

    seller_order.status = "RETURN_REQUESTED"
    seller_order.escrow_status = "PAUSED"
    session.add(seller_order)

    order.status = "RETURN_REQUESTED"
    order.escrow_status = "PAUSED"
    session.add(order)

    session.add(
        OrderHistory(
            seller_order_id=seller_order.id,
            from_status="DELIVERED",
            to_status="RETURN_REQUESTED",
            changed_by_user_id=current_user.id,
            note=f"Buyer submitted return request: {payload.reason}",
        )
    )

    create_notification(
        session,
        recipient_user_id=seller_order.seller_id,
        order_id=order.id,
        event_key=f"return_request:{ret_req.id}:created:{int(time.time() * 1000)}",
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

    sub_orders = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == order.id)
    ).all()
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


def decide_return_request(
    session: Session,
    current_user: User,
    return_request_id: int,
    decision: ReturnDecisionRequest,
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

    old_status = seller_order.status
    now = datetime.now(UTC)

    if decision.action == "APPROVE":
        ret_req.status = "APPROVED"
        ret_req.decided_by_user_id = current_user.id
        ret_req.decided_at = now
        ret_req.decision_notes = decision.decision_notes
        ret_req.is_restockable = decision.is_restockable

        seller_order.status = "RETURNED_REFUNDED"
        seller_order.payment_status = "REFUNDED"
        seller_order.escrow_status = "REFUNDED"

        order.status = "RETURNED_REFUNDED"
        order.payment_status = "REFUNDED"
        order.escrow_status = "REFUNDED"

        if decision.is_restockable:
            items = session.exec(
                select(OrderItem, Product)
                .join(Product, Product.id == OrderItem.product_id)
                .where(OrderItem.seller_order_id == seller_order.id)
            ).all()
            for item, product in items:
                session.exec(
                    update(Product)
                    .where(Product.id == product.id)
                    .values(
                        stock_quantity=Product.stock_quantity + item.quantity,
                        version=Product.version + 1,
                    )
                    .execution_options(synchronize_session=False)
                )
                session.exec(
                    update(ProductMetadata)
                    .where(ProductMetadata.product_id == product.id)
                    .values(
                        sales_count=case(
                            (ProductMetadata.sales_count - item.quantity < 0, 0),
                            else_=ProductMetadata.sales_count - item.quantity,
                        )
                    )
                    .execution_options(synchronize_session=False)
                )
            note = "Return approved. Inventory restored."
        else:
            note = "Return approved. Inventory not increased."

        session.add(
            OrderHistory(
                seller_order_id=seller_order.id,
                from_status=old_status,
                to_status="RETURNED_REFUNDED",
                changed_by_user_id=current_user.id,
                note=note,
            )
        )

        create_notification(
            session,
            recipient_user_id=order.buyer_id,
            order_id=order.id,
            event_key=f"return_request:{ret_req.id}:approved",
            message=(
                f"Your return request for order #{order.id} has been approved. "
                "The payment has been refunded."
            ),
            target_path=f"/orders/{order.id}",
        )
    else:  # REJECT
        ret_req.status = "REJECTED"
        ret_req.decided_by_user_id = current_user.id
        ret_req.decided_at = now
        ret_req.decision_notes = decision.decision_notes

        seller_order.status = "COMPLETED"
        seller_order.escrow_status = "RELEASED"

        order.status = "COMPLETED"
        order.escrow_status = "RELEASED"

        note = f"Return rejected: {decision.decision_notes or 'Not approved.'}"
        session.add(
            OrderHistory(
                seller_order_id=seller_order.id,
                from_status=old_status,
                to_status="COMPLETED",
                changed_by_user_id=current_user.id,
                note=note,
            )
        )

        create_notification(
            session,
            recipient_user_id=order.buyer_id,
            order_id=order.id,
            event_key=f"return_request:{ret_req.id}:rejected",
            message=(
                f"Your return request for order #{order.id} was rejected. "
                f"Reason: {decision.decision_notes or 'Request rejected.'}"
            ),
            target_path=f"/orders/{order.id}",
        )

    session.add(ret_req)
    session.add(seller_order)
    session.add(order)
    session.commit()
    session.refresh(ret_req)
    session.refresh(seller_order)
    session.refresh(order)
    return _to_return_data(ret_req, seller_order, order)
