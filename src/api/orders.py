from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlmodel import select

from src.auth import BuyerUser, CurrentUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.seller_order import SellerOrder
from src.schemas.orders import CheckoutInput, OrderResponse
from src.services.orders import CheckoutError, checkout, receipt

router = APIRouter(prefix="/orders", tags=["Orders"])

TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"CONFIRMED", "PROCESSING", "CANCELLED"},
    "CONFIRMED": {"PROCESSING", "SHIPPED", "CANCELLATION_REQUESTED", "CANCELLED"},
    "PROCESSING": {"CONFIRMED", "SHIPPED", "CANCELLATION_REQUESTED", "CANCELLED"},
    "CANCELLATION_REQUESTED": {"CANCELLED", "CONFIRMED", "PROCESSING"},
    "SHIPPED": {"DELIVERED", "COMPLETED"},
    "DELIVERED": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class OrderStatusUpdateRequest(BaseModel):
    status: Literal[
        "PENDING",
        "CONFIRMED",
        "PROCESSING",
        "CANCELLATION_REQUESTED",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
        "CANCELLED",
    ]
    tracking_number: str | None = None


# Backward-compatibility alias
BuyerStatusUpdateRequest = OrderStatusUpdateRequest


@router.post("", response_model=OrderResponse, status_code=201)
def place_order(
    body: CheckoutInput,
    buyer: BuyerUser,
    session: SessionDep,
    response: Response,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)],
) -> OrderResponse:
    if not key.strip() or key != key.strip():
        raise HTTPException(400, detail=error_detail("ERR_INVALID_KEY", "Invalid idempotency key."))
    try:
        data, created = checkout(session, buyer.id, body, key)
        response.status_code = 201 if created else 200
        return OrderResponse(data=data)
    except CheckoutError as exc:
        raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc


@router.get("", response_model=list[OrderResponse])
def list_buyer_orders(buyer: BuyerUser, session: SessionDep) -> list[OrderResponse]:
    orders = session.exec(
        select(Order).where(Order.buyer_id == buyer.id).order_by(Order.created_at.desc())
    ).all()
    return [OrderResponse(data=receipt(session, buyer.id, o.id)) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, user: CurrentUser, session: SessionDep) -> OrderResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))
    if order.buyer_id == user.id:
        return OrderResponse(data=receipt(session, buyer_id=user.id, order_id=order_id))
    if user.role == "seller":
        sub_order = session.exec(
            select(SellerOrder).where(
                SellerOrder.order_id == order_id,
                SellerOrder.seller_id == user.id,
            )
        ).first()
        if sub_order is not None:
            return OrderResponse(
                data=receipt(session, buyer_id=None, order_id=order_id, seller_id=user.id)
            )
    raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))


@router.patch("/{order_id}/status", response_model=OrderResponse)
def update_buyer_order_status(
    order_id: int,
    request: OrderStatusUpdateRequest,
    user: CurrentUser,
    session: SessionDep,
) -> OrderResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))

    sub_orders = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == order.id)
    ).all()

    new_status = request.status
    now = datetime.now(UTC)

    # 1. Seller flow
    if user.role == "seller":
        seller_sub_orders = [s for s in sub_orders if s.seller_id == user.id]
        if not seller_sub_orders:
            raise HTTPException(
                403,
                detail=error_detail(
                    "ERR_RESOURCE_OWNER", "You do not own any items in this order."
                ),
            )

        for sub_order in seller_sub_orders:
            if new_status not in TRANSITIONS.get(sub_order.status, set()):
                raise HTTPException(
                    400,
                    detail=error_detail(
                        "ERR_INVALID_TRANSITION",
                        f"Transition from {sub_order.status} to {new_status} is not allowed.",
                    ),
                )
            old_sub_status = sub_order.status
            sub_order.status = new_status
            if new_status == "SHIPPED":
                sub_order.shipped_at = now
                if request.tracking_number:
                    sub_order.tracking_number = request.tracking_number
            elif new_status == "DELIVERED":
                sub_order.delivered_at = now
            elif new_status == "COMPLETED":
                sub_order.completed_at = now
            elif new_status == "CANCELLED":
                # Restore inventory
                items = session.exec(
                    select(OrderItem, Product)
                    .join(Product, Product.id == OrderItem.product_id)
                    .where(OrderItem.seller_order_id == sub_order.id)
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

            note = None
            if old_sub_status == "CANCELLATION_REQUESTED":
                note = (
                    "Cancellation approved by seller. Stock restored."
                    if new_status == "CANCELLED"
                    else "Cancellation rejected by seller."
                )
            elif new_status == "CANCELLED":
                note = "Stock restored."
            elif new_status == "SHIPPED":
                note = (
                    f"Shipped. Tracking: {request.tracking_number}"
                    if request.tracking_number
                    else "Shipped."
                )
            elif new_status == "DELIVERED":
                note = "Delivered."
            elif new_status == "CONFIRMED":
                note = "Confirmed by seller."

            session.add(sub_order)
            session.add(
                OrderHistory(
                    seller_order_id=sub_order.id,
                    from_status=old_sub_status,
                    to_status=new_status,
                    changed_by_user_id=user.id,
                    note=note,
                )
            )

        # Synchronize parent order status and milestones
        child_orders = session.exec(
            select(SellerOrder).where(SellerOrder.order_id == order.id)
        ).all()
        statuses = {child.status for child in child_orders}
        if statuses == {"COMPLETED"}:
            order.status = "COMPLETED"
            order.completed_at = now
        elif statuses == {"CANCELLED"}:
            order.status = "CANCELLED"
        elif statuses == {"DELIVERED"}:
            order.status = "DELIVERED"
            order.delivered_at = now
        elif statuses == {"SHIPPED"}:
            order.status = "SHIPPED"
            order.shipped_at = now
        elif statuses == {"CONFIRMED"}:
            order.status = "CONFIRMED"
        elif statuses == {"CANCELLATION_REQUESTED"}:
            order.status = "CANCELLATION_REQUESTED"
        elif statuses & {"PROCESSING", "CONFIRMED", "SHIPPED", "DELIVERED", "COMPLETED"}:
            order.status = "PROCESSING"
        else:
            order.status = "PENDING"

        for s in child_orders:
            if s.tracking_number:
                order.tracking_number = s.tracking_number
            if s.shipped_at:
                order.shipped_at = s.shipped_at
            if s.delivered_at:
                order.delivered_at = s.delivered_at
            if s.completed_at:
                order.completed_at = s.completed_at

        session.add(order)
        session.commit()
        receipt_data = receipt(session, buyer_id=None, order_id=order.id, seller_id=user.id)
        return OrderResponse(data=receipt_data)

    # 2. Buyer flow
    if order.buyer_id != user.id:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))

    if new_status == "CANCELLED":
        if order.status != "PENDING":
            raise HTTPException(
                400,
                detail=error_detail(
                    "ERR_INVALID_TRANSITION",
                    "Only pending orders can be directly cancelled. "
                    "For confirmed orders, please request cancellation.",
                ),
            )
        for sub_order in sub_orders:
            old_sub_status = sub_order.status
            if old_sub_status != "CANCELLED":
                sub_order.status = "CANCELLED"
                session.add(sub_order)
                items = session.exec(
                    select(OrderItem, Product)
                    .join(Product, Product.id == OrderItem.product_id)
                    .where(OrderItem.seller_order_id == sub_order.id)
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
                session.add(
                    OrderHistory(
                        seller_order_id=sub_order.id,
                        from_status=old_sub_status,
                        to_status="CANCELLED",
                        changed_by_user_id=user.id,
                        note="Cancelled by buyer. Stock restored.",
                    )
                )
        order.status = "CANCELLED"
        session.add(order)
        session.commit()
        return OrderResponse(data=receipt(session, user.id, order.id))

    elif new_status == "CANCELLATION_REQUESTED":
        if order.status not in ("CONFIRMED", "PROCESSING"):
            raise HTTPException(
                400,
                detail=error_detail(
                    "ERR_INVALID_TRANSITION",
                    f"Cannot request cancellation for an order in {order.status} state.",
                ),
            )
        for sub_order in sub_orders:
            if sub_order.status in ("CONFIRMED", "PROCESSING"):
                old_sub_status = sub_order.status
                sub_order.status = "CANCELLATION_REQUESTED"
                session.add(sub_order)
                session.add(
                    OrderHistory(
                        seller_order_id=sub_order.id,
                        from_status=old_sub_status,
                        to_status="CANCELLATION_REQUESTED",
                        changed_by_user_id=user.id,
                        note="Cancellation requested by buyer.",
                    )
                )
        order.status = "CANCELLATION_REQUESTED"
        session.add(order)
        session.commit()
        return OrderResponse(data=receipt(session, user.id, order.id))

    elif new_status == "COMPLETED":
        if order.status not in ("DELIVERED", "SHIPPED"):
            raise HTTPException(
                400,
                detail=error_detail(
                    "ERR_INVALID_TRANSITION",
                    "Confirmation is only available once the order has been delivered.",
                ),
            )
        for sub_order in sub_orders:
            if sub_order.status in ("DELIVERED", "SHIPPED"):
                old_sub_status = sub_order.status
                sub_order.status = "COMPLETED"
                sub_order.completed_at = now
                session.add(sub_order)
                session.add(
                    OrderHistory(
                        seller_order_id=sub_order.id,
                        from_status=old_sub_status,
                        to_status="COMPLETED",
                        changed_by_user_id=user.id,
                        note="Delivery confirmed by buyer.",
                    )
                )
        order.status = "COMPLETED"
        order.completed_at = now
        session.add(order)
        session.commit()
        return OrderResponse(data=receipt(session, user.id, order.id))

    raise HTTPException(
        400,
        detail=error_detail("ERR_INVALID_TRANSITION", f"Unsupported status {new_status}."),
    )


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_buyer_order(
    order_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> OrderResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))
    target = "CANCELLED" if order.status == "PENDING" else "CANCELLATION_REQUESTED"
    return update_buyer_order_status(
        order_id=order_id,
        request=OrderStatusUpdateRequest(status=target),
        user=user,
        session=session,
    )


@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm_buyer_order_delivery(
    order_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> OrderResponse:
    return update_buyer_order_status(
        order_id=order_id,
        request=OrderStatusUpdateRequest(status="COMPLETED"),
        user=user,
        session=session,
    )
