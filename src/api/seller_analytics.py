"""Seller analytics API endpoints (US18).

Provides three read-only views:
  GET /api/v1/seller/analytics              — time-based revenue & order summary
  GET /api/v1/seller/analytics/best-sellers — products ranked by units sold / revenue
  GET /api/v1/seller/analytics/low-stock    — active products with available stock ≤ threshold
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.auth import SellerUser
from src.database import SessionDep
from src.errors import error_detail
from src.services.seller_analytics import (
    LOW_STOCK_DEFAULT_THRESHOLD,
    get_best_sellers,
    get_financial_summary,
    get_low_stock_products,
    get_revenue_summary,
)

router = APIRouter(prefix="/seller/analytics", tags=["Seller analytics"])

_DEFAULT_DAYS = 30
_MAX_LIMIT = 100
_MIN_THRESHOLD = 0
_MAX_THRESHOLD = 10_000


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=error_detail(code, message))


def _parse_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _bad_request(
            "ERR_INVALID_DATE",
            f"{field_name} must be an ISO date (YYYY-MM-DD).",
        ) from exc


def _resolve_date_range(
    from_date: str | None,
    to_date: str | None,
    default_days: int = _DEFAULT_DAYS,
) -> tuple[date, date]:
    """Return (start, end) inclusive dates; default is the last *default_days* days."""
    today = datetime.now(UTC).date()
    start = _parse_date(from_date, "from") or (today - timedelta(days=default_days - 1))
    end = _parse_date(to_date, "to") or today
    if start > end:
        raise _bad_request("ERR_INVALID_DATE_RANGE", "from must not be after to.")
    return start, end


def _resolve_group_by(value: str | None) -> str | None:
    if value is None:
        return None
    aliases = {"day": "daily", "month": "monthly"}
    normalized = aliases.get(value, value)
    if normalized not in ("daily", "monthly"):
        raise _bad_request(
            "ERR_INVALID_GROUPING",
            "group_by must be one of: day, month, daily, monthly.",
        )
    return normalized


# ---------------------------------------------------------------------------
# Response schemas (inline — no extra file needed for this feature)
# ---------------------------------------------------------------------------


class RevenuePeriod(BaseModel):
    period: str
    period_start: str
    period_end: str
    revenue: int
    orders: int
    items_sold: int
    gross_order_value: int
    completed_revenue: int
    pending_escrow_revenue: int
    cancellation_rate: float


class RevenueAnalyticsResponse(BaseModel):
    data: list[RevenuePeriod]
    meta: dict


class BestSellerItem(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    units_sold: int
    revenue: int


class BestSellersResponse(BaseModel):
    data: list[BestSellerItem]
    meta: dict


class LowStockItem(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    stock_quantity: int
    reserved_stock: int
    available_stock: int


class LowStockResponse(BaseModel):
    data: list[LowStockItem]
    meta: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=RevenueAnalyticsResponse)
def get_analytics(
    session: SessionDep,
    seller: SellerUser,
    from_date: str | None = Query(default=None, alias="from", description="YYYY-MM-DD"),
    to_date: str | None = Query(default=None, alias="to", description="YYYY-MM-DD"),
    period: str = Query(default="daily", description="daily | weekly | monthly"),
    group_by: str | None = Query(default=None, description="day | month"),
    from_date_param: str | None = Query(default=None, alias="from_date"),
    to_date_param: str | None = Query(default=None, alias="to_date"),
) -> RevenueAnalyticsResponse:
    """Return time-bucketed revenue and order counts for the authenticated seller.

    - **from** / **to**: inclusive date range (default: last 30 days).
    - **period**: grouping granularity — `daily`, `weekly`, or `monthly`.
    - Only **COMPLETED** seller orders are included in revenue figures.
    """
    group_by = _resolve_group_by(group_by)
    if period not in ("daily", "weekly", "monthly"):
        raise _bad_request(
            "ERR_INVALID_PERIOD",
            "period must be one of: daily, weekly, monthly.",
        )
    start, end = _resolve_date_range(
        from_date or from_date_param,
        to_date or to_date_param,
    )
    effective_period = group_by or period
    rows = get_revenue_summary(
        session,
        seller.id,
        start,
        end,
        effective_period,  # type: ignore[arg-type]
    )
    financial_group = group_by or ("monthly" if period == "monthly" else "daily")
    financial_rows = get_financial_summary(
        session,
        seller.id,
        start,
        end,
        financial_group,  # type: ignore[arg-type]
    )
    financial_by_start = {row["period_start"]: row for row in financial_rows}
    data = []
    for row in rows:
        financial = financial_by_start.get(row["period_start"], {})
        data.append(
            RevenuePeriod(
                **row,
                gross_order_value=financial.get("gross_order_value", 0),
                completed_revenue=financial.get("completed_revenue", 0),
                pending_escrow_revenue=financial.get("pending_escrow_revenue", 0),
                cancellation_rate=financial.get("cancellation_rate", 0),
            )
        )
    total_revenue = sum(r.revenue for r in data)
    total_orders = sum(r.orders for r in data)
    total_items = sum(r.items_sold for r in data)
    return RevenueAnalyticsResponse(
        data=data,
        meta={
            "from": start.isoformat(),
            "to": end.isoformat(),
            "period": period,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_items_sold": total_items,
            "group_by": financial_group,
            "gross_order_value": sum(r.gross_order_value for r in data),
            "completed_revenue": sum(r.completed_revenue for r in data),
            "pending_escrow_revenue": sum(r.pending_escrow_revenue for r in data),
            "cancellation_rate": (
                round(
                    sum(row["cancelled_orders"] for row in financial_rows)
                    * 100
                    / sum(row["total_orders"] for row in financial_rows),
                    2,
                )
                if sum(row["total_orders"] for row in financial_rows)
                else 0
            ),
        },
    )


@router.get("/best-sellers", response_model=BestSellersResponse)
def get_best_sellers_endpoint(
    session: SessionDep,
    seller: SellerUser,
    from_date: str | None = Query(default=None, alias="from", description="YYYY-MM-DD"),
    to_date: str | None = Query(default=None, alias="to", description="YYYY-MM-DD"),
    sort_by: str = Query(default="units", description="units | revenue"),
    limit: int = Query(default=10, ge=1, le=_MAX_LIMIT),
) -> BestSellersResponse:
    """Return the seller's top products ranked by units sold or revenue.

    - **sort_by**: `units` (default) or `revenue`.
    - **limit**: number of results, 1–100 (default 10).
    - Only **COMPLETED** seller orders contribute.
    """
    if sort_by not in ("units", "revenue"):
        raise _bad_request(
            "ERR_INVALID_SORT",
            "sort_by must be one of: units, revenue.",
        )
    start, end = _resolve_date_range(from_date, to_date)
    rows = get_best_sellers(session, seller.id, start, end, sort_by, limit)  # type: ignore[arg-type]
    data = [BestSellerItem(**r) for r in rows]
    return BestSellersResponse(
        data=data,
        meta={
            "from": start.isoformat(),
            "to": end.isoformat(),
            "sort_by": sort_by,
            "limit": limit,
            "count": len(data),
        },
    )


@router.get("/low-stock", response_model=LowStockResponse)
def get_low_stock_endpoint(
    session: SessionDep,
    seller: SellerUser,
    threshold: int = Query(
        default=LOW_STOCK_DEFAULT_THRESHOLD,
        ge=_MIN_THRESHOLD,
        le=_MAX_THRESHOLD,
        description="Products with available_stock ≤ threshold are returned (default 5).",
    ),
) -> LowStockResponse:
    """Return active products whose available stock is at or below *threshold*.

    Available stock = `stock_quantity − reserved_stock`.
    Results are ordered by available stock ascending (most critical first).
    """
    rows = get_low_stock_products(session, seller.id, threshold)
    data = [LowStockItem(**r) for r in rows]
    return LowStockResponse(
        data=data,
        meta={
            "threshold": threshold,
            "count": len(data),
        },
    )
