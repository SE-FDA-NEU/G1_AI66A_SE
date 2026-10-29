"""Seller analytics service (US18).

Provides three analytics views for a seller:
  1. Time-based summary — revenue and order counts grouped by day / week / month.
  2. Best sellers       — products ranked by units sold or by revenue in a period.
  3. Low-stock alerts   — active products whose available stock is at or below a threshold.

All queries are read-only and scoped strictly to the authenticated seller's products.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import func
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


def get_revenue_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    period: Period,
) -> list[dict]:
    """Return a list of time-bucketed revenue/order statistics.

    Each element is::

        {
            "period":        "2024-01-15",           # label (ISO date / range / YYYY-MM)
            "period_start":  "2024-01-15",
            "period_end":    "2024-01-15",
            "revenue":       1_500_000,              # integer VND
            "orders":        3,                      # distinct seller_orders
            "items_sold":    7,                      # sum of quantities
        }

    Only seller_orders with status COMPLETED count toward revenue.
    """
    start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)

    # Fetch all completed seller_orders in range for this seller.
    # Per docs/design.md line 300 & BR7:
    # "The selected analytics period is evaluated using seller_orders.completed_at,
    # not the original marketplace order creation timestamp."
    rows = session.exec(
        select(SellerOrder, Order, OrderItem, Product)
        .join(Order, Order.id == SellerOrder.order_id)
        .join(OrderItem, OrderItem.seller_order_id == SellerOrder.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            SellerOrder.seller_id == seller_id,
            SellerOrder.status == "COMPLETED",
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) >= start_dt,
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) <= end_dt,
        )
    ).all()

    # Group into buckets
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
            "_order_ids": set(),
        }

    for seller_order, _order, item, _product in rows:
        order_dt = seller_order.completed_at or seller_order.created_at
        order_date = order_dt.date()
        bucket_start = _period_start(order_date, period)
        if bucket_start not in buckets:
            continue
        bucket = buckets[bucket_start]
        bucket["revenue"] += item.quantity * item.unit_price
        bucket["items_sold"] += item.quantity
        bucket["_order_ids"].add(seller_order.id)

    result = []
    for bucket_start in sorted(buckets):
        b = buckets[bucket_start]
        b["orders"] = len(b.pop("_order_ids"))
        result.append(b)

    return result


def get_financial_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    group_by: Period,
) -> list[dict]:
    """Return seller-scoped financial metrics on the same timeline as revenue."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end_date, time.max, tzinfo=UTC)
    rows = session.exec(
        select(SellerOrder, Order)
        .join(Order, Order.id == SellerOrder.order_id)
        .where(
            SellerOrder.seller_id == seller_id,
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) >= start_dt,
            func.coalesce(SellerOrder.completed_at, SellerOrder.created_at) <= end_dt,
        )
    ).all()

    buckets: dict[date, dict] = {}
    for bucket_start, bucket_end_exc in _iter_buckets(start_date, end_date, group_by):
        bucket_end = bucket_end_exc - timedelta(days=1)
        buckets[bucket_start] = {
            "period": _period_label(bucket_start, group_by),
            "period_start": bucket_start.isoformat(),
            "period_end": bucket_end.isoformat(),
            "gross_order_value": 0,
            "completed_revenue": 0,
            "pending_escrow_revenue": 0,
            "cancelled_orders": 0,
            "total_orders": 0,
        }

    for seller_order, order in rows:
        order_date = (
            seller_order.completed_at or seller_order.created_at
        ).date()
        bucket = buckets.get(_period_start(order_date, group_by))
        if bucket is None:
            continue
        amount = order.total_amount
        bucket["gross_order_value"] += amount
        bucket["total_orders"] += 1
        if seller_order.status == "COMPLETED":
            bucket["completed_revenue"] += amount
        if (
            seller_order.status not in {"COMPLETED", "CANCELLED"}
            and seller_order.escrow_status in {"HELD", "PAUSED"}
        ):
            bucket["pending_escrow_revenue"] += amount
        if seller_order.status == "CANCELLED":
            bucket["cancelled_orders"] += 1

    for bucket in buckets.values():
        total_orders = bucket["total_orders"]
        bucket["cancellation_rate"] = (
            round(bucket["cancelled_orders"] * 100 / total_orders, 2)
            if total_orders else 0.0
        )
    return [buckets[key] for key in sorted(buckets)]


def get_analytics_summary(
    session: Session,
    seller_id: int,
    start_date: date,
    end_date: date,
    period: Period,
) -> tuple[list[dict], dict]:
    """Merge the time series and aggregate financial metrics for one seller."""
    revenue_rows = get_revenue_summary(
        session, seller_id, start_date, end_date, period
    )
    financial_rows = get_financial_summary(
        session, seller_id, start_date, end_date, period
    )
    financial_by_start = {row["period_start"]: row for row in financial_rows}
    data = []
    for row in revenue_rows:
        financial = financial_by_start.get(row["period_start"], {})
        data.append(
            {
                **row,
                "gross_order_value": financial.get("gross_order_value", 0),
                "completed_revenue": financial.get("completed_revenue", 0),
                "pending_escrow_revenue": financial.get("pending_escrow_revenue", 0),
                "cancellation_rate": financial.get("cancellation_rate", 0.0),
            }
        )
    total_orders = sum(row["total_orders"] for row in financial_rows)
    meta = {
        "group_by": period,
        "gross_order_value": sum(row["gross_order_value"] for row in financial_rows),
        "completed_revenue": sum(row["completed_revenue"] for row in financial_rows),
        "pending_escrow_revenue": sum(
            row["pending_escrow_revenue"] for row in financial_rows
        ),
        "cancellation_rate": (
            round(
                sum(row["cancelled_orders"] for row in financial_rows) * 100 / total_orders,
                2,
            )
            if total_orders
            else 0.0
        ),
    }
    return data, meta


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
