"""Seller-scoped order listing and fulfilment transitions."""

from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.schemas.order_history import OrderHistoryEntry, order_timestamp_utc
from src.schemas.order_status import OrderStatusChange
from src.services.order_history import history_by_seller_order
from src.services.order_states import ORDER_STATUSES
from src.services.order_workflow import WorkflowError, seller_status_change

router = APIRouter(prefix="/seller/orders", tags=["Seller orders"])

STATUSES = ORDER_STATUSES | {"RETURN_REQUESTED", "RETURNED_REFUNDED"}


class SellerOrderItemResponse(BaseModel):
    id: int
    product_id: int
    variant_id: int | None = None
    product_name: str
    variant_name: str | None = None
    product_code: str
    image_url: str | None = None
    quantity: int
    unit_price: int
    total_price: int


class SellerOrderResponse(BaseModel):
    id: int
    order_id: int
    customer_name: str
    status: str
    ordered_at: datetime
    tracking_number: str | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    history: list[OrderHistoryEntry] = Field(default_factory=list)
    items: list[SellerOrderItemResponse]


class SellerOrderListResponse(BaseModel):
    data: list[SellerOrderResponse]
    meta: dict[str, int]


class StatusUpdateRequest(OrderStatusChange):
    """Status change with bounded tracking and audit note fields."""


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
    history: list[OrderHistoryEntry] | None = None,
) -> SellerOrderResponse:
    rows = session.exec(
        select(OrderItem, Product, ProductVariant)
        .join(Product, Product.id == OrderItem.product_id)
        .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id)
        .where(OrderItem.seller_order_id == seller_order.id)
        .order_by(OrderItem.id)
    ).all()
    items = [
        SellerOrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            product_name=(
                item.product_name_snapshot
                if item.snapshot_initialized
                else item.product_name_snapshot or product.name
            ),
            variant_name=(
                item.variant_name_snapshot
                if item.snapshot_initialized
                else item.variant_name_snapshot or (variant.name if variant else None)
            ),
            product_code=product.code,
            image_url=(
                item.product_image_snapshot
                if item.snapshot_initialized
                else item.product_image_snapshot
                or (variant.image_url if variant else None)
                or product.image_url
            ),
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.quantity * item.unit_price,
        )
        for item, product, variant in rows
        if item.id is not None
    ]
    return SellerOrderResponse(
        id=seller_order.id,
        order_id=seller_order.order_id,
        customer_name=parent_order.recipient_name,
        status=seller_order.status,
        ordered_at=order_timestamp_utc(parent_order.created_at),
        tracking_number=seller_order.tracking_number,
        shipped_at=(
            order_timestamp_utc(seller_order.shipped_at) if seller_order.shipped_at else None
        ),
        delivered_at=(
            order_timestamp_utc(seller_order.delivered_at) if seller_order.delivered_at else None
        ),
        completed_at=(
            order_timestamp_utc(seller_order.completed_at) if seller_order.completed_at else None
        ),
        history=(
            history if history is not None
            else history_by_seller_order(session, [seller_order.id]).get(seller_order.id, [])
        ),
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
    history = history_by_seller_order(session, [seller_order.id for seller_order, _ in rows])
    return SellerOrderListResponse(
        data=[
            _seller_order_response(session, seller_order, parent, history.get(seller_order.id, []))
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
    try:
        seller_status_change(
            session,
            seller.id,
            request.status,
            sub_order_id=sub_order_id,
            tracking_number=request.tracking_number,
            note=request.note,
        )
    except WorkflowError as exc:
        raise HTTPException(exc.status, detail=error_detail(exc.code, exc.message)) from exc
    seller_order = session.get(SellerOrder, sub_order_id)
    parent = session.get(Order, seller_order.order_id)
    return StatusUpdateResponse(data=_seller_order_response(session, seller_order, parent))
