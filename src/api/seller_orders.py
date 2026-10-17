"""Seller-scoped order listing and fulfilment transitions."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlmodel import select

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder

router = APIRouter(prefix="/seller/orders", tags=["Seller orders"])

STATUSES = {"PENDING", "PROCESSING", "SHIPPED", "COMPLETED", "CANCELLED"}
TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"PROCESSING", "CANCELLED"},
    "PROCESSING": {"SHIPPED"},
    "SHIPPED": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class SellerOrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_code: str
    quantity: int
    unit_price: int
    total_price: int


class SellerOrderResponse(BaseModel):
    id: int
    order_id: int
    customer_name: str
    status: str
    ordered_at: datetime
    items: list[SellerOrderItemResponse]


class SellerOrderListResponse(BaseModel):
    data: list[SellerOrderResponse]
    meta: dict[str, int]


class StatusUpdateRequest(BaseModel):
    status: Literal["PENDING", "PROCESSING", "SHIPPED", "COMPLETED", "CANCELLED"]


class StatusUpdateResponse(BaseModel):
    data: SellerOrderResponse


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=error_detail(code, message))


def _parse_date(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _bad_request(
            "ERR_INVALID_DATE",
            f"{field_name} must be an ISO date.",
        ) from exc
    return datetime.combine(parsed, time.min, tzinfo=UTC)


def _seller_order_response(
    session,
    seller_order: SellerOrder,
    parent_order: Order,
) -> SellerOrderResponse:
    rows = session.exec(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.seller_order_id == seller_order.id)
        .order_by(OrderItem.id)
    ).all()
    items = [
        SellerOrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=product.name,
            product_code=product.code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.quantity * item.unit_price,
        )
        for item, product in rows
        if item.id is not None
    ]
    return SellerOrderResponse(
        id=seller_order.id,
        order_id=seller_order.order_id,
        customer_name=parent_order.recipient_name,
        status=seller_order.status,
        ordered_at=parent_order.created_at,
        items=items,
    )


@router.get("", response_model=SellerOrderListResponse)
def list_seller_orders(
    session: SessionDep,
    seller: SellerUser,
    status: str | None = Query(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> SellerOrderListResponse:
    """Return only the authenticated seller's sub-orders and their items."""
    if status is not None:
        status = status.upper()
        if status not in STATUSES:
            raise _bad_request("ERR_INVALID_STATUS", "status must be a valid seller order status.")
    start = _parse_date(from_date, "from")
    end = _parse_date(to_date, "to")
    if start and end and start > end:
        raise _bad_request("ERR_INVALID_DATE_RANGE", "from must not be after to.")

    query = (
        select(SellerOrder, Order)
        .join(Order, Order.id == SellerOrder.order_id)
        .where(SellerOrder.seller_id == seller.id)
    )
    count_query = (
        select(func.count())
        .select_from(SellerOrder)
        .join(Order, Order.id == SellerOrder.order_id)
        .where(SellerOrder.seller_id == seller.id)
    )
    if status:
        query = query.where(SellerOrder.status == status)
        count_query = count_query.where(SellerOrder.status == status)
    if start:
        query = query.where(Order.created_at >= start)
        count_query = count_query.where(Order.created_at >= start)
    if end:
        end_of_day = end + timedelta(days=1)
        query = query.where(Order.created_at < end_of_day)
        count_query = count_query.where(Order.created_at < end_of_day)

    total = session.exec(count_query).one()
    rows = session.exec(
        query.order_by(Order.created_at.desc(), SellerOrder.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return SellerOrderListResponse(
        data=[
            _seller_order_response(session, seller_order, parent)
            for seller_order, parent in rows
        ],
        meta={"page": page, "limit": limit, "total": total},
    )


@router.patch("/{sub_order_id}/status", response_model=StatusUpdateResponse)
def update_seller_order_status(
    sub_order_id: int,
    request: StatusUpdateRequest,
    session: SessionDep,
    seller: SellerUser,
) -> StatusUpdateResponse:
    """Apply an owned status transition and record its audit event."""
    seller_order = session.get(SellerOrder, sub_order_id)
    if seller_order is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("ERR_ORDER_NOT_FOUND", "Seller order was not found."),
        )
    if seller_order.seller_id != seller.id:
        raise HTTPException(
            status_code=403,
            detail=error_detail("ERR_RESOURCE_OWNER", "You do not own this seller order."),
        )

    new_status = request.status
    if new_status not in TRANSITIONS.get(seller_order.status, set()):
        raise _bad_request(
            "ERR_INVALID_TRANSITION",
            f"Transition from {seller_order.status} to {new_status} is not allowed.",
        )

    old_status = seller_order.status
    status_values: dict[str, object] = {"status": new_status}
    if new_status == "COMPLETED":
        status_values["completed_at"] = datetime.now(UTC)
    changed = session.exec(
        update(SellerOrder)
        .where(
            SellerOrder.id == seller_order.id,
            SellerOrder.seller_id == seller.id,
            SellerOrder.status == old_status,
        )
        .values(**status_values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "ERR_CONCURRENCY_CONFLICT",
                "The seller order changed. Please refresh and try again.",
            ),
        )
    session.refresh(seller_order)

    items = session.exec(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.seller_order_id == seller_order.id)
    ).all()
    if new_status == "CANCELLED":
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

    session.add(
        OrderHistory(
            seller_order_id=seller_order.id,
            from_status=old_status,
            to_status=new_status,
            changed_by_user_id=seller.id,
            note="Stock restored." if new_status == "CANCELLED" else None,
        )
    )

    child_orders = session.exec(
        select(SellerOrder).where(SellerOrder.order_id == seller_order.order_id)
    ).all()
    statuses = {child.status for child in child_orders}
    parent = session.get(Order, seller_order.order_id)
    if parent:
        if statuses == {"COMPLETED"}:
            parent.status = "COMPLETED"
        elif statuses == {"CANCELLED"}:
            parent.status = "CANCELLED"
        elif statuses & {"PROCESSING", "SHIPPED", "COMPLETED"}:
            parent.status = "PROCESSING"
        else:
            parent.status = "PENDING"
        session.add(parent)

    session.commit()
    session.refresh(seller_order)
    if parent is None:
        raise HTTPException(
            status_code=500,
            detail=error_detail("ERR_DATABASE_FAILURE", "The parent order could not be loaded."),
        )
    return StatusUpdateResponse(
        data=_seller_order_response(session, seller_order, parent)
    )
