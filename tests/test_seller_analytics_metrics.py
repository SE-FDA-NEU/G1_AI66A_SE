"""Low-stock alerts and analytics metric boundaries on an isolated database (#144).

Expected values are worked out by hand from the rows each test inserts.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.services.seller_analytics import (
    get_best_sellers,
    get_low_stock_products,
    get_revenue_summary,
)
from tests.cart_db import BUYER_ID, SELLER_ID, add_product, create_cart_engine

OTHER_SELLER_ID = 4
DAY = date(2026, 1, 31)


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "analytics.db")
    with Session(value) as session:
        session.add(
            User(id=OTHER_SELLER_ID, name="Other", email="other-shop@test.local", role="seller")
        )
        session.commit()
    yield value
    value.dispose()


def add_variant(engine, product_id, sku, stock, *, reserved=0, active=True, seller=SELLER_ID):
    with Session(engine) as session:
        variant = ProductVariant(
            product_id=product_id,
            seller_id=seller,
            sku=sku,
            name=f"Variant {sku}",
            price=100_000,
            stock_quantity=stock,
            reserved_stock=reserved,
            is_active=active,
        )
        session.add(variant)
        session.commit()
        return variant.id


def add_sale(engine, lines, *, status="COMPLETED", completed_at=None, seller=SELLER_ID):
    """One seller order with (product_id, quantity, unit_price) lines."""
    created = completed_at or datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session:
        order = Order(
            buyer_id=BUYER_ID,
            total_amount=sum(qty * price for _, qty, price in lines),
            status=status,
            recipient_name="Buyer",
            delivery_address="1 Street",
            phone_number="0123456789",
            created_at=created,
        )
        session.add(order)
        session.flush()
        seller_order = SellerOrder(
            order_id=order.id,
            seller_id=seller,
            status=status,
            created_at=created,
            completed_at=completed_at if status == "COMPLETED" else None,
        )
        session.add(seller_order)
        session.flush()
        for product_id, qty, price in lines:
            session.add(
                OrderItem(
                    seller_order_id=seller_order.id,
                    product_id=product_id,
                    quantity=qty,
                    unit_price=price,
                )
            )
        session.commit()


def low_stock(engine, threshold=5, seller=SELLER_ID):
    with Session(engine) as session:
        return get_low_stock_products(session, seller, threshold)


# --- Low-stock alerts ----------------------------------------------------------------


@pytest.mark.parametrize(("stock", "alerted"), [(0, True), (5, True), (6, False)])
def test_product_stock_at_threshold_boundary(engine, stock, alerted):
    add_product(engine, "LOW-P", stock=stock)

    rows = low_stock(engine)

    assert [row["available_stock"] for row in rows] == ([stock] if alerted else [])


@pytest.mark.parametrize(("stock", "alerted"), [(0, True), (5, True), (6, False)])
def test_variant_stock_at_threshold_boundary(engine, stock, alerted):
    product_id = add_product(engine, "LOW-V", stock=50)
    variant_id = add_variant(engine, product_id, "LOW-V-1", stock)

    rows = low_stock(engine)

    expected = [(product_id, variant_id, "LOW-V-1", stock)] if alerted else []
    assert [
        (row["product_id"], row["variant_id"], row["variant_sku"], row["stock_quantity"])
        for row in rows
    ] == expected


def test_product_with_variants_is_reported_per_variant_only(engine):
    product_id = add_product(engine, "LOW-PARENT", stock=0)
    low = add_variant(engine, product_id, "LOW-A", 2)
    add_variant(engine, product_id, "LOW-B", 9)
    add_variant(engine, product_id, "LOW-OFF", 0, active=False)

    rows = low_stock(engine)

    assert [row["variant_id"] for row in rows] == [low]


def test_reserved_stock_counts_against_availability(engine):
    add_product(engine, "LOW-RESERVED", stock=8, reserved=4)

    [row] = low_stock(engine)

    assert (row["stock_quantity"], row["reserved_stock"], row["available_stock"]) == (8, 4, 4)


def test_low_stock_is_scoped_to_the_seller_and_active_catalog(engine):
    mine = add_product(engine, "LOW-MINE", stock=1)
    add_product(engine, "LOW-INACTIVE", stock=1, active=False)
    theirs = add_product(engine, "LOW-THEIRS", stock=1)
    with Session(engine) as session:
        product = session.get(Product, theirs)
        product.seller_id = OTHER_SELLER_ID
        session.add(product)
        session.commit()

    assert [row["product_id"] for row in low_stock(engine)] == [mine]
    assert [row["product_id"] for row in low_stock(engine, seller=OTHER_SELLER_ID)] == [theirs]


def test_low_stock_is_ordered_most_critical_first(engine):
    three = add_product(engine, "LOW-3", stock=3)
    zero = add_product(engine, "LOW-0", stock=0)
    variant_parent = add_product(engine, "LOW-VP", stock=50)
    one = add_variant(engine, variant_parent, "LOW-1", 1)

    rows = low_stock(engine)

    assert [(row["product_id"], row["variant_id"]) for row in rows] == [
        (zero, None),
        (variant_parent, one),
        (three, None),
    ]


# --- Revenue summary and best sellers -------------------------------------------------


def summary(engine, start, end, period="daily", seller=SELLER_ID):
    with Session(engine) as session:
        return get_revenue_summary(session, seller, start, end, period)


def test_date_range_includes_whole_first_and_last_day(engine):
    product_id = add_product(engine, "DATE-P")
    start_of_day = datetime(2026, 1, 31, 0, 0, 0, tzinfo=UTC)
    end_of_day = datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC)
    add_sale(engine, [(product_id, 1, 1_000)], completed_at=start_of_day)
    add_sale(engine, [(product_id, 1, 2_000)], completed_at=end_of_day)
    add_sale(engine, [(product_id, 1, 4_000)], completed_at=start_of_day - timedelta(seconds=1))
    add_sale(engine, [(product_id, 1, 8_000)], completed_at=end_of_day + timedelta(seconds=1))

    [bucket] = summary(engine, DAY, DAY)

    assert (bucket["revenue"], bucket["orders"], bucket["items_sold"]) == (3_000, 2, 2)


def test_monthly_buckets_split_at_month_boundary(engine):
    product_id = add_product(engine, "MONTH-P")
    add_sale(
        engine, [(product_id, 1, 1_000)], completed_at=datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    )
    add_sale(engine, [(product_id, 1, 2_000)], completed_at=datetime(2026, 2, 1, tzinfo=UTC))

    buckets = summary(engine, date(2026, 1, 1), date(2026, 2, 28), "monthly")

    assert [(b["period"], b["revenue"]) for b in buckets] == [
        ("2026-01", 1_000),
        ("2026-02", 2_000),
    ]


def test_only_completed_seller_orders_count_as_revenue(engine):
    product_id = add_product(engine, "STATUS-P")
    when = datetime(2026, 1, 31, 12, tzinfo=UTC)
    add_sale(engine, [(product_id, 1, 1_000)], completed_at=when)
    for status in ("PENDING", "DELIVERED", "RETURN_REQUESTED", "CANCELLED", "RETURNED_REFUNDED"):
        add_sale(engine, [(product_id, 1, 50_000)], status=status, completed_at=when)

    [bucket] = summary(engine, DAY, DAY)

    assert (bucket["revenue"], bucket["orders"]) == (1_000, 1)


def test_multi_item_order_counts_once(engine):
    first = add_product(engine, "MULTI-A")
    second = add_product(engine, "MULTI-B")
    add_sale(
        engine,
        [(first, 2, 1_000), (second, 3, 500)],
        completed_at=datetime(2026, 1, 31, 9, tzinfo=UTC),
    )

    [bucket] = summary(engine, DAY, DAY)

    assert (bucket["revenue"], bucket["orders"], bucket["items_sold"]) == (3_500, 1, 5)


def test_revenue_and_best_sellers_are_scoped_to_the_seller(engine):
    mine = add_product(engine, "SCOPE-MINE")
    theirs = add_product(engine, "SCOPE-THEIRS")
    when = datetime(2026, 1, 31, 9, tzinfo=UTC)
    add_sale(engine, [(mine, 1, 1_000)], completed_at=when)
    add_sale(engine, [(theirs, 9, 9_000)], completed_at=when, seller=OTHER_SELLER_ID)

    [bucket] = summary(engine, DAY, DAY)
    with Session(engine) as session:
        ranked = get_best_sellers(session, SELLER_ID, DAY, DAY)

    assert bucket["revenue"] == 1_000
    assert [row["product_id"] for row in ranked] == [mine]


def test_best_sellers_rank_by_units_with_stable_ties(engine):
    first = add_product(engine, "RANK-A")
    second = add_product(engine, "RANK-B")
    third = add_product(engine, "RANK-C")
    when = datetime(2026, 1, 31, 9, tzinfo=UTC)
    add_sale(engine, [(third, 2, 1_000), (second, 5, 100)], completed_at=when)
    add_sale(engine, [(first, 2, 9_000)], completed_at=when)
    add_sale(engine, [(first, 9, 9_000)], status="CANCELLED", completed_at=when)

    with Session(engine) as session:
        by_units = get_best_sellers(session, SELLER_ID, DAY, DAY)
        by_revenue = get_best_sellers(session, SELLER_ID, DAY, DAY, sort_by="revenue")

    assert [(row["product_id"], row["units_sold"]) for row in by_units] == [
        (second, 5),
        (first, 2),
        (third, 2),
    ]
    assert [row["product_id"] for row in by_revenue] == [first, third, second]
