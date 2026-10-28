from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import select

from src.auth import ActiveCurrentUser, BuyerUser, CurrentUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.seller_order import SellerOrder
from src.schemas.orders import CheckoutInput, OrderResponse
from src.services.order_states import is_allowed_transition
from src.services.order_workflow import WorkflowError, buyer_cancellation, seller_status_change
from src.services.orders import CheckoutError, checkout, receipt

router = APIRouter(prefix="/orders", tags=["Orders"])


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
    user: ActiveCurrentUser,
    session: SessionDep,
) -> OrderResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))

    new_status = request.status
    now = datetime.now(UTC)

    # 1. Seller flow
    if user.role == "seller":
        try:
            seller_status_change(
                session,
                user.id,
                new_status,
                order_id=order_id,
                tracking_number=request.tracking_number,
            )
        except WorkflowError as exc:
            raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc
        return OrderResponse(
            data=receipt(session, buyer_id=None, order_id=order_id, seller_id=user.id)
        )

    # 2. Buyer flow
    if order.buyer_id != user.id:
        raise HTTPException(404, detail=error_detail("ERR_ORDER_NOT_FOUND", "Order not found."))

    if new_status in {"CANCELLED", "CANCELLATION_REQUESTED"}:
        try:
            buyer_cancellation(session, user.id, order_id, new_status)
        except WorkflowError as exc:
            raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc
        return OrderResponse(data=receipt(session, user.id, order_id))

    elif new_status == "COMPLETED":
        if not is_allowed_transition("buyer", order.status, new_status):
            raise HTTPException(
                400,
                detail=error_detail(
                    "ERR_INVALID_TRANSITION",
                    "Confirmation is only available once the order has been delivered.",
                ),
            )
        sub_orders = session.exec(select(SellerOrder).where(SellerOrder.order_id == order_id)).all()
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
    user: ActiveCurrentUser,
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
    user: ActiveCurrentUser,
    session: SessionDep,
) -> OrderResponse:
    return update_buyer_order_status(
        order_id=order_id,
        request=OrderStatusUpdateRequest(status="COMPLETED"),
        user=user,
        session=session,
    )
