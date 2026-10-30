"""Seller analytics service (US18).

Provides three analytics views for a seller:
  1. Time-based summary — revenue and order counts grouped by day / week / month.
  2. Best sellers       — products ranked by units sold or by revenue in a period.
  3. Low-stock alerts   — active products whose available stock is at or below a threshold.

All queries are read-only and scoped strictly to the authenticated seller's products.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import case, func
from sqlmodel import Session, select

from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder

# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

Period = Literal["daily", "weekly", "monthly"]

LOW_STOCK_DEFAULT_THRESHOLD = 5


def _period_start(ref: date, period: Period) -> date:
    """Return the inclusive start of the period containing *ref*."""
    if period == "daily":
        return ref
    if period == "weekly":
        # ISO week starts on Monday
        return ref - timedelta(days=ref.weekday())
    # monthly
    return ref.replace(day=1)


def _period_label(bucket_start: date, period: Period) -> str:
    """A human-readable label for one time bucket."""
    if period == "daily":
        return bucket_start.isoformat()
    if period == "weekly":
        week_end = bucket_start + timedelta(days=6)
        return f"{bucket_start.isoformat()}/{week_end.isoformat()}"
    # monthly
    return bucket_start.strftime("%Y-%m")


def _iter_buckets(start: date, end: date, period: Period):
    """Yield the (bucket_start, bucket_end_exclusive) for every period between start and end."""
    current = _period_start(start, period)
    while current <= end:
        if period == "daily":
            yield current, current + timedelta(days=1)
            current += timedelta(days=1)
        elif period == "weekly":
            yield current, current + timedelta(weeks=1)
            current += timedelta(weeks=1)
        else:  # monthly
            if current.month == 12:
                nxt = current.replace(year=current.year + 1, month=1, day=1)
            else:
                nxt = current.replace(month=current.month + 1, day=1)
            yield current, nxt
            current = nxt


# ---------------------------------------------------------------------------
# 1. Time-based summary
# ---------------------------------------------------------------------------


def get_analytics_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    period: Period,
) -> tuple[list[dict], dict]:
    """Return seller-scoped time-bucketed metrics and metadata in a single query."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)

    effective_ts = func.coalesce(SellerOrder.completed_at, SellerOrder.created_at)

    # Single database query aggregating item metrics via SQL GROUP BY
    rows = session.exec(
        select(
            SellerOrder.id,
            SellerOrder.status,
            SellerOrder.escrow_status,
            SellerOrder.total_amount,
            effective_ts.label("effective_dt"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            SellerOrder.status == "COMPLETED",
                            OrderItem.quantity * OrderItem.unit_price,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("items_revenue"),
            func.coalesce(
                func.sum(
                    case(
                        (SellerOrder.status == "COMPLETED", OrderItem.quantity),
                        else_=0,
                    )
                ),
                0,
            ).label("items_sold"),
        )
        .outerjoin(OrderItem, OrderItem.seller_order_id == SellerOrder.id)
        .where(
            SellerOrder.seller_id == seller_id,
            effective_ts >= start_dt,
            effective_ts <= end_dt,
        )
        .group_by(
            SellerOrder.id,
            SellerOrder.status,
            SellerOrder.escrow_status,
            SellerOrder.total_amount,
            SellerOrder.completed_at,
            SellerOrder.created_at,
        )
    ).all()

    buckets: dict[date, dict] = {}
    for bucket_start, bucket_end_exc in _iter_buckets(start_date, end_date, period):
        label = _period_label(bucket_start, period)
        bucket_end = bucket_end_exc - timedelta(days=1)
        buckets[bucket_start] = {
            "period": label,
            "period_start": bucket_start.isoformat(),
            "period_end": bucket_end.isoformat(),
            "revenue": 0,
            "orders": 0,
            "items_sold": 0,
            "gross_order_value": 0,
            "completed_revenue": 0,
            "pending_escrow_revenue": 0,
            "cancellation_rate": 0.0,
            "_cancelled_orders": 0,
            "_total_orders": 0,
        }

    for row in rows:
        order_date = row.effective_dt.date()
        bucket_start = _period_start(order_date, period)
        if bucket_start not in buckets:
            continue
        bucket = buckets[bucket_start]
        amount = int(row.total_amount)
        bucket["gross_order_value"] += amount
        bucket["_total_orders"] += 1

        if row.status == "COMPLETED":
            bucket["revenue"] += int(row.items_revenue)
            bucket["orders"] += 1
            bucket["items_sold"] += int(row.items_sold)
            bucket["completed_revenue"] += amount
        elif row.status == "CANCELLED":
            bucket["_cancelled_orders"] += 1

        if (
            row.status not in {"COMPLETED", "CANCELLED"}
            and row.escrow_status in {"HELD", "PAUSED"}
        ):
            bucket["pending_escrow_revenue"] += amount

    for bucket in buckets.values():
        tot = bucket["_total_orders"]
        can = bucket["_cancelled_orders"]
        bucket["cancellation_rate"] = (
            round(can * 100.0 / tot, 2) if tot > 0 else 0.0
        )

    data = []
    total_revenue = 0
    total_orders = 0
    total_items = 0
    gross_order_value = 0
    completed_revenue = 0
    pending_escrow_revenue = 0
    all_total_orders = 0
    all_cancelled_orders = 0

    for bucket_start in sorted(buckets):
        b = buckets[bucket_start]
        tot = b.pop("_total_orders")
        can = b.pop("_cancelled_orders")
        total_revenue += b["revenue"]
        total_orders += b["orders"]
        total_items += b["items_sold"]
        gross_order_value += b["gross_order_value"]
        completed_revenue += b["completed_revenue"]
        pending_escrow_revenue += b["pending_escrow_revenue"]
        all_total_orders += tot
        all_cancelled_orders += can
        data.append(b)

    meta = {
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "period": period,
        "group_by": period,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_items_sold": total_items,
        "gross_order_value": gross_order_value,
        "completed_revenue": completed_revenue,
        "pending_escrow_revenue": pending_escrow_revenue,
        "cancellation_rate": (
            round(all_cancelled_orders * 100.0 / all_total_orders, 2)
            if all_total_orders > 0
            else 0.0
        ),
    }
    return data, meta


def get_revenue_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    period: Period,
) -> list[dict]:
    """Return a list of time-bucketed revenue/order statistics."""
    data, _ = get_analytics_summary(session, seller_id, start_date, end_date, period)
    return data


def get_financial_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    group_by: Period,
) -> list[dict]:
    """Return seller-scoped financial metrics on the same timeline as revenue."""
    data, _ = get_analytics_summary(session, seller_id, start_date, end_date, group_by)
    return data


# ---------------------------------------------------------------------------
# 2. Best sellers
# ---------------------------------------------------------------------------

SortBy = Literal["units", "revenue"]


def get_best_sellers(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    sort_by: SortBy = "units",
    limit: int = 10,
) -> list[dict]:
    """Return the top-*limit* products ranked by units sold or revenue.

    Only COMPLETED seller_orders contribute. Each element is::

        {
            "product_id":    42,
            "product_code":  "P-...",
            "product_name":  "Laptop XYZ",
            "units_sold":    150,
            "revenue":       450_000_000,
        }
    """
    start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)

    rows = session.exec(
        select(
            Product.id,
            Product.code,
            Product.name,
            func.sum(OrderItem.quantity).label("units_sold"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Order, Order.id == SellerOrder.order_id)
        .where(
            SellerOrder.seller_id == seller_id,
            SellerOrder.status == "COMPLETED",
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) >= start_dt,
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) <= end_dt,
        )
        .group_by(Product.id, Product.code, Product.name)
    ).all()

    items = [
        {
            "product_id": row[0],
            "product_code": row[1],
            "product_name": row[2],
            "units_sold": int(row[3] or 0),
            "revenue": int(row[4] or 0),
        }
        for row in rows
    ]

    sort_key = "revenue" if sort_by == "revenue" else "units_sold"
    items.sort(key=lambda x: x[sort_key], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# 3. Low-stock alerts
# ---------------------------------------------------------------------------


def get_low_stock_products(
    session: Session,
    seller_id: int,
    threshold: int = LOW_STOCK_DEFAULT_THRESHOLD,
) -> list[dict]:
    """Return active products whose *available* stock (stock_quantity − reserved_stock)
    is at or below *threshold*, ordered by available stock ascending.

    Each element is::

        {
            "product_id":       42,
            "product_code":     "P-...",
            "product_name":     "Widget",
            "stock_quantity":   3,
            "reserved_stock":   1,
            "available_stock":  2,
        }
    """
    products = session.exec(
        select(Product)
        .where(
            Product.seller_id == seller_id,
            Product.is_active.is_(True),
        )
        .order_by(
            (Product.stock_quantity - Product.reserved_stock).asc(),
            Product.id.asc(),
        )
    ).all()

    result = []
    for p in products:
        available = p.stock_quantity - p.reserved_stock
        if available <= threshold:
            result.append(
                {
                    "product_id": p.id,
                    "product_code": p.code,
                    "product_name": p.name,
                    "stock_quantity": p.stock_quantity,
                    "reserved_stock": p.reserved_stock,
                    "available_stock": available,
                }
            )
    return result
