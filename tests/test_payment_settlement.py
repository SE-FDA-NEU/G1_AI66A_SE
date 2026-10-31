"""Payment-state and settlement edge cases (#150, US20 sections 4, 6, 8, 9, 10, 11).

Covers:
- Meta-test: architectural isolation (only src/services/payments.py mutates payment fields)
- Reconciliation identity on multi-vendor orders with vouchers and platform discounts
- Commission flooring and boundary partitions
- Reconciliation with seller analytics across order lifecycles and multi-shop isolation
# 8 - Zero-total orders (100% discount) lifecycle and settlement
# 9 - Safety invariants R1 to R6 (refund idempotency, voided escrow safety, paused hold)
# 10 - Invalid payment transitions rejection
- Duplicate and late conflicting payment callbacks
- Legacy orders isolation (criterion L)
- COD lifecycle and return settlement edge cases
"""

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

import src.services.order_workflow as workflow
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.payment_event import PaymentEvent
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.services.orders import checkout
from src.services.payments import (
    PaymentError,
    calculate_seller_net,
    record_payment_result,
    refund_seller_order,
    try_release,
    void_settlement,
)
from src.services.seller_analytics import get_analytics_summary
from tests import test_atomic_cancellation as cancellation
from tests.cart_db import BUYER_ID, SELLER_ID, add_product
from tests.test_checkout import BODY, headers
from tests.test_checkout_vouchers import VOUCHERS, add_voucher, quote, setup_cart
from tests.test_checkout_vouchers import place as place_with_vouchers
from tests.test_payment_event_order import check_invariants

api = cancellation.api
engine = cancellation.engine

OTHER_SELLER_ID = 4
NOW = datetime.now(UTC)


def place_order(
    engine,
    method="VIETQR",
    *,
    price=100_000,
    quantity=2,
    key="settle-pay",
    seller_id=SELLER_ID,
):
    product_id = add_product(engine, f"PROD-{key}", price=price, stock=10)
    if seller_id != SELLER_ID:
        with Session(engine) as session:
            p = session.get(Product, product_id)
            p.seller_id = seller_id
            session.add(p)
            session.commit()

    with Session(engine) as session:
        session.add(CartItem(buyer_id=BUYER_ID, product_id=product_id, quantity=quantity))
        session.commit()

    from src.schemas.orders import CheckoutRequest

    with Session(engine) as session:
        body = BODY | ({"payment_method": method} if method else {})
        order, _ = checkout(session, BUYER_ID, CheckoutRequest(**body), key)
        return order.id, order.sub_orders[0].id


def record_paid(engine, order_id, key="pay-op-1"):
    with Session(engine) as session:
        record_payment_result(session, order_id, "PAID", "DEMO_OPERATOR", key)
        session.commit()


# ==============================================================================
# 1. Meta-test: Architectural isolation (Section 9)
# ==============================================================================


def test_payment_fields_are_only_written_by_payments_service():
    """Section 9: payment/escrow status and settled_at writes pass through payments.py."""
    violations = []
    excluded_files = {
        "src/services/payments.py",
        "src/database.py",
    }

    for path in Path("src").rglob("*.py"):
        rel_posix = path.as_posix()
        if rel_posix in excluded_files or rel_posix.startswith("src/models/"):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_posix)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr in {"payment_status", "escrow_status", "settled_at"}
                    ):
                        violations.append((rel_posix, node.lineno, target.attr))
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
            ):
                if (
                    len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in {"payment_status", "escrow_status", "settled_at"}
                ):
                    violations.append((rel_posix, node.lineno, node.args[1].value))

    assert violations == [], (
        f"Direct payment/escrow mutations found outside payments.py: {violations}"
    )


# ==============================================================================
# 2. Reconciliation identity on multi-vendor order (Section 4)
# ==============================================================================


def test_contract_worked_example_reconciliation_identity(api, engine):
    """US20 section 4: total - net - shipping == commission - platform_disc - ship_disc."""
    setup_cart(engine)
    add_voucher(engine, "SHOPA30K", scope="SHOP", seller_id=SELLER_ID, discount_value=30_000)
    add_voucher(
        engine, "PLAT10", discount_type="PERCENTAGE", discount_value=1000, max_discount=50_000
    )
    add_voucher(
        engine, "FREESHIP15", discount_type="FREE_SHIPPING", discount_value=0, max_discount=15_000
    )

    quote_res = quote(api, engine)
    assert quote_res.status_code == 200, quote_res.text
    revision = quote_res.json()["data"]["quote_revision"]

    place_res = place_with_vouchers(
        api, engine, VOUCHERS | {"quote_revision": revision, "payment_method": "VIETQR"}
    )
    assert place_res.status_code == 201, place_res.text
    order_data = place_res.json()["data"]
    order_id = order_data["id"]

    with Session(engine) as session:
        children = session.exec(
            select(SellerOrder)
            .where(SellerOrder.order_id == order_id)
            .order_by(SellerOrder.seller_id)
        ).all()
        assert len(children) == 2

        child_a, child_b = children[0], children[1]
        assert child_a.seller_id == SELLER_ID
        assert child_b.seller_id == OTHER_SELLER_ID

        # Shop A (seller 1): subtotal 300k, shop discount 30k -> basis 270k
        assert child_a.subtotal == 300_000
        assert child_a.shop_discount == 30_000
        assert child_a.platform_discount == 27_000
        assert child_a.shipping_fee == 20_000
        assert child_a.shipping_discount == 15_000
        assert child_a.total_amount == 248_000
        assert child_a.commission_amount == 13_500
        assert child_a.seller_net_amount == 256_500

        # Shop B (seller 4): subtotal 200k, shop discount 0 -> basis 200k
        assert child_b.subtotal == 200_000
        assert child_b.shop_discount == 0
        assert child_b.platform_discount == 20_000
        assert child_b.shipping_fee == 20_000
        assert child_b.shipping_discount == 15_000
        assert child_b.total_amount == 185_000
        assert child_b.commission_amount == 10_000
        assert child_b.seller_net_amount == 190_000

        # Assert Section 4 reconciliation identity
        sum_total_amount = sum(c.total_amount for c in children)  # 433_000
        sum_seller_net = sum(c.seller_net_amount for c in children)  # 446_500
        sum_shipping_fee = sum(c.shipping_fee for c in children)  # 40_000
        sum_commission = sum(c.commission_amount for c in children)  # 23_500
        sum_platform_discount = sum(c.platform_discount for c in children)  # 47_000
        sum_shipping_discount = sum(c.shipping_discount for c in children)  # 30_000

        left_side = sum_total_amount - sum_seller_net - sum_shipping_fee
        right_side = sum_commission - sum_platform_discount - sum_shipping_discount

        assert left_side == right_side == -53_500
        # Platform funded 47k + 30k = 77k; seller net exceeds buyer payment minus commission
        assert sum_seller_net > sum_total_amount - sum_shipping_fee

    check_invariants(engine)


# ==============================================================================
# 3. Commission flooring and boundary partitions
# ==============================================================================


@pytest.mark.parametrize(
    ("basis", "rate_bps", "expected_commission", "expected_net"),
    [
        (0, 500, 0, 0),
        (1, 500, 0, 1),
        (19, 500, 0, 19),
        (20, 500, 1, 19),
        (10_001, 500, 500, 9_501),
        (19_999, 500, 999, 19_000),
        (1_000_000_000, 500, 50_000_000, 950_000_000),
        (500_000, 0, 0, 500_000),
        (500_000, 10_000, 500_000, 0),
    ],
)
def test_commission_floor_and_boundary_partitions(
    basis, rate_bps, expected_commission, expected_net
):
    commission, net = calculate_seller_net(basis, rate_bps)
    assert commission == expected_commission
    assert net == expected_net
    assert commission + net == basis


def test_calculate_seller_net_rejects_negative_or_overflow_rates():
    with pytest.raises(ValueError, match="Basis must be >= 0"):
        calculate_seller_net(-1, 500)

    with pytest.raises(ValueError, match="rate within 0-10000 bps"):
        calculate_seller_net(100_000, -1)

    with pytest.raises(ValueError, match="rate within 0-10000 bps"):
        calculate_seller_net(100_000, 10_001)


# ==============================================================================
# 4. Zero-total orders (100% discount / free item)
# ==============================================================================


def test_zero_total_order_lifecycle_and_settlement(engine):
    """Section 3: total_amount = 0 records PAID with ZERO_TOTAL source; releases on completion."""
    order_id, child_id = place_order(engine, "CARD", price=50_000, quantity=1, key="zero-order")

    with Session(engine) as session:
        order = session.get(Order, order_id)
        child = session.get(SellerOrder, child_id)
        child.subtotal = 0
        child.shop_discount = 0
        child.total_amount = 0
        from src.services.payments import start_payment

        start_payment(session, order, [child], "CARD")
        session.commit()

    with Session(engine) as session:
        order = session.get(Order, order_id)
        child = session.get(SellerOrder, child_id)
        assert child.total_amount == 0
        assert child.payment_status == "PAID"
        assert child.escrow_status == "HELD"
        assert child.commission_amount == 0
        assert child.seller_net_amount == 0
        assert order.payment_status == "PAID"
        assert order.escrow_status == "HELD"

        event = session.exec(
            select(PaymentEvent).where(PaymentEvent.order_id == order_id)
        ).one()
        assert event.source == "ZERO_TOTAL"
        assert event.kind == "PAYMENT_RESULT"
        assert event.amount == 0

    check_invariants(engine)

    # Move order through fulfillment to COMPLETED
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_id)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        order = session.get(Order, order_id)
        assert child.status == "COMPLETED"
        assert child.escrow_status == "RELEASED"
        assert child.settled_at is not None
        assert order.escrow_status == "RELEASED"

    check_invariants(engine)


# ==============================================================================
# 5. Seller Analytics reconciliation across order lifecycle
# ==============================================================================


def test_seller_analytics_reconciliation_across_order_lifecycle(engine):
    """Reconcile seller analytics financial metrics with payment & escrow state transitions."""
    today = datetime.now(UTC).date()
    order_id, child_id = place_order(
        engine, "VIETQR", price=120_000, quantity=1, key="analytics-flow"
    )

    # 1. New order: UNPAID, HELD
    with Session(engine) as session:
        buckets, meta = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert buckets[0]["gross_order_value"] == 120_000
        assert buckets[0]["completed_revenue"] == 0
        assert buckets[0]["pending_escrow_revenue"] == 120_000  # Held in pending escrow
        assert buckets[0]["cancellation_rate"] == 0.0

    # 2. Payment recorded: PAID, HELD
    record_paid(engine, order_id, key="an-paid-1")
    with Session(engine) as session:
        buckets, meta = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert buckets[0]["gross_order_value"] == 120_000
        assert buckets[0]["completed_revenue"] == 0
        assert buckets[0]["pending_escrow_revenue"] == 120_000  # Now PAID and HELD

    # 3. Fulfillment to COMPLETED: PAID, RELEASED
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_id)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.escrow_status == "RELEASED"
        assert child.settled_at is not None

        buckets, meta = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert buckets[0]["gross_order_value"] == 120_000
        assert buckets[0]["pending_escrow_revenue"] == 0  # Released from pending escrow
        assert buckets[0]["completed_revenue"] == 120_000
        assert buckets[0]["orders"] == 1
        assert buckets[0]["items_sold"] == 1

    check_invariants(engine)


def test_seller_analytics_cancellation_and_return_reconciliation(api, engine):
    """Cancelled or returned orders do not count as completed revenue or escrow in analytics."""
    today = datetime.now(UTC).date()

    # Flow A: Paid then cancelled
    order_id_1, child_id_1 = place_order(
        engine, "WALLET", price=80_000, quantity=1, key="an-cancel"
    )
    record_paid(engine, order_id_1, key="an-cancel-paid")

    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id_1, "CANCELLED")

    with Session(engine) as session:
        buckets, meta = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert buckets[0]["completed_revenue"] == 0
        assert buckets[0]["pending_escrow_revenue"] == 0
        assert buckets[0]["cancellation_rate"] == 100.0

    # Flow B: Delivered then return approved
    order_id_2, child_id_2 = place_order(
        engine, "WALLET", price=60_000, quantity=1, key="an-return"
    )
    record_paid(engine, order_id_2, key="an-return-paid")
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id_2)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id_2)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id_2)

    ret_res = api.post(
        f"/api/v1/orders/{order_id_2}/returns",
        json={"reason": "Damaged product", "evidence": "photo.jpg"},
        headers=headers(engine),
    )
    assert ret_res.status_code == 201
    return_id = ret_res.json()["data"]["id"]

    # While return is requested: escrow is PAUSED
    with Session(engine) as session:
        buckets, _ = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert buckets[0]["pending_escrow_revenue"] == 60_000

    # Approve return
    app_res = api.post(
        f"/api/v1/return-requests/{return_id}/decision",
        json={"action": "APPROVE", "is_restockable": False},
        headers=headers(engine, SELLER_ID),
    )
    assert app_res.status_code == 200

    with Session(engine) as session:
        buckets, _ = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        # Returned-refunded does not count in completed or pending escrow revenue
        assert buckets[0]["completed_revenue"] == 0
        assert buckets[0]["pending_escrow_revenue"] == 0

    check_invariants(engine)


def test_multi_vendor_analytics_tenant_isolation(engine):
    """Multi-shop order: verify absolute tenant isolation in seller analytics."""
    today = datetime.now(UTC).date()
    with Session(engine) as session:
        session.add(
            User(id=OTHER_SELLER_ID, name="Other Shop", email="shop2@test.local", role="seller")
        )
        session.commit()

    prod_1 = add_product(engine, "M-SHOP-1", price=50_000, stock=10)
    prod_2 = add_product(engine, "M-SHOP-2", price=75_000, stock=10)
    with Session(engine) as session:
        session.get(Product, prod_2).seller_id = OTHER_SELLER_ID
        session.add(CartItem(buyer_id=BUYER_ID, product_id=prod_1, quantity=1))
        session.add(CartItem(buyer_id=BUYER_ID, product_id=prod_2, quantity=1))
        session.commit()

    from src.schemas.orders import CheckoutRequest

    with Session(engine) as session:
        body = BODY | {"payment_method": "VIETQR"}
        order, _ = checkout(session, BUYER_ID, CheckoutRequest(**body), "mv-isolation")
        order_id = order.id
        sub_orders = sorted(order.sub_orders, key=lambda so: so.seller_id)
        child_1_id, child_2_id = sub_orders[0].id, sub_orders[1].id

    record_paid(engine, order_id, key="mv-paid-key")

    # Complete Shop 1
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_1_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_1_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_1_id)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_1_id)

    # Cancel Shop 2
    with Session(engine) as session:
        workflow.seller_status_change(
            session, OTHER_SELLER_ID, "CANCELLED", sub_order_id=child_2_id
        )

    with Session(engine) as session:
        # Shop 1 analytics
        b1, _ = get_analytics_summary(session, SELLER_ID, today, today, "daily")
        assert b1[0]["gross_order_value"] == 50_000
        assert b1[0]["completed_revenue"] == 50_000
        assert b1[0]["pending_escrow_revenue"] == 0
        assert b1[0]["cancellation_rate"] == 0.0

        # Shop 2 analytics
        b2, _ = get_analytics_summary(session, OTHER_SELLER_ID, today, today, "daily")
        assert b2[0]["gross_order_value"] == 75_000
        assert b2[0]["completed_revenue"] == 0
        assert b2[0]["pending_escrow_revenue"] == 0
        assert b2[0]["cancellation_rate"] == 100.0

    check_invariants(engine)


# ==============================================================================
# 6. Safety invariants R1 to R5 (Section 11)
# ==============================================================================


def test_r1_refund_idempotency_across_repeated_calls(engine):
    """R1: Repeated refund/cancellation calls record exactly one REFUND event."""
    order_id, child_id = place_order(engine, "CARD", price=150_000, quantity=1, key="r1-order")
    record_paid(engine, order_id, key="r1-paid")

    # First cancellation refunds the paid seller order
    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    # Second cancellation attempt via seller route is rejected by workflow
    with Session(engine) as session, pytest.raises(workflow.WorkflowError):
        workflow.seller_status_change(session, SELLER_ID, "CANCELLED", sub_order_id=child_id)

    # Calling refund_seller_order again directly on already refunded order returns False
    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        second = refund_seller_order(session, child, None)
        session.commit()
        assert second is False

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "CANCELLED"
        assert child.payment_status == "REFUNDED"
        assert child.escrow_status == "VOIDED"
        assert child.refunded_amount == 150_000
        events = session.exec(
            select(PaymentEvent).where(
                PaymentEvent.seller_order_id == child_id,
                PaymentEvent.kind == "REFUND",
            )
        ).all()
        assert len(events) == 1
        assert events[0].amount == 150_000

    check_invariants(engine)


def test_r3_voided_escrow_cannot_be_settled_or_released(engine):
    """R3: Cancelled or returned seller order escrow stays VOIDED and cannot release."""
    order_id, child_id = place_order(engine, "VIETQR", price=99_000, quantity=1, key="r3-order")
    record_paid(engine, order_id, key="r3-paid")

    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.escrow_status == "VOIDED"
        # Directly call try_release
        released = try_release(session, child)
        session.commit()
        assert released is False

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.escrow_status == "VOIDED"
        assert child.settled_at is None

    # Call void_settlement on an already RELEASED order raises PaymentError
    order_id_rel, child_id_rel = place_order(engine, "COD", price=50_000, quantity=1, key="r3-rel")
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id_rel)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id_rel)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id_rel)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_id_rel)
        child_rel = session.get(SellerOrder, child_id_rel)
        assert child_rel.escrow_status == "RELEASED"

        with pytest.raises(PaymentError, match="Released escrow cannot be voided"):
            void_settlement(session, child_rel)

    check_invariants(engine)


def test_r4_paused_escrow_during_return_review_blocks_release(api, engine):
    """R4: Return under review (PAUSED) holds escrow and blocks release until rejection."""
    order_id, child_id = place_order(engine, "CARD", price=80_000, quantity=1, key="r4-order")
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)

    # Request return -> escrow becomes PAUSED
    ret_res = api.post(
        f"/api/v1/orders/{order_id}/returns",
        json={"reason": "Defective item", "evidence": "video.mp4"},
        headers=headers(engine),
    )
    assert ret_res.status_code == 201
    return_id = ret_res.json()["data"]["id"]

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.escrow_status == "PAUSED"
        # Try release while paused
        released = try_release(session, child)
        session.commit()
        assert released is False

    # Recording payment while paused does not release escrow
    record_paid(engine, order_id, key="r4-paid")
    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.payment_status == "PAID"
        assert child.escrow_status == "PAUSED"
        released = try_release(session, child)
        session.commit()
        assert released is False

    # Reject return -> resumes escrow to HELD and runs release guard to RELEASED
    dec_res = api.post(
        f"/api/v1/return-requests/{return_id}/decision",
        json={"action": "REJECT"},
        headers=headers(engine, SELLER_ID),
    )
    assert dec_res.status_code == 200

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "COMPLETED"
        assert child.escrow_status == "RELEASED"
        assert child.settled_at is not None

    check_invariants(engine)


def test_r5_released_order_cannot_be_re_released_or_refunded(engine):
    """R5: Already RELEASED order never releases again; workflow rejects cancellation."""
    order_id, child_id = place_order(engine, "VIETQR", price=110_000, quantity=1, key="r5-order")
    record_paid(engine, order_id, key="r5-paid")
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_id)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.escrow_status == "RELEASED"
        orig_settled_at = child.settled_at

        # Attempt to release again
        assert try_release(session, child) is False
        session.commit()

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.settled_at == orig_settled_at

        # Attempt to cancel via workflow is rejected
        with pytest.raises(workflow.WorkflowError):
            workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "COMPLETED"
        assert child.payment_status == "PAID"
        assert child.escrow_status == "RELEASED"
        assert child.settled_at == orig_settled_at

    check_invariants(engine)


# ==============================================================================
# 7. Invalid transitions and state validation
# ==============================================================================


def test_invalid_payment_status_transitions_rejected(engine):
    """Section 2.2: Invalid status transitions raise PaymentError with ERR_INVALID_TRANSITION."""
    order_id, child_id = place_order(engine, "WALLET", price=70_000, quantity=1, key="inv-trans")

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.payment_status == "UNPAID"

        from src.services.payments import _set_payment

        # UNPAID -> REFUNDED directly is illegal
        with pytest.raises(PaymentError) as exc_info:
            _set_payment(session, child, "REFUNDED")
        assert exc_info.value.code == "ERR_INVALID_TRANSITION"

        # Unknown status string
        with pytest.raises(PaymentError) as exc_info:
            _set_payment(session, child, "PARTIALLY_REFUNDED")
        assert exc_info.value.code == "ERR_INVALID_TRANSITION"

    check_invariants(engine)


# ==============================================================================
# 8. Duplicate callbacks and conflicting payment results
# ==============================================================================


def test_duplicate_callbacks_and_conflicting_payment_results(engine):
    """Section 2.2 & 7: Duplicate callbacks are idempotent; late FAILED after PAID is ignored."""
    order_id, child_id = place_order(engine, "CARD", price=85_000, quantity=1, key="cb-order")

    # Initial payment
    record_paid(engine, order_id, key="cb-key-1")

    # Duplicate call with EXACT same key
    with Session(engine) as session:
        res = record_payment_result(session, order_id, "PAID", "DEMO_OPERATOR", "cb-key-1")
        session.commit()
        assert res.payment_status == "PAID"

    # Conflicting FAILED callback with NEW key after PAID
    with Session(engine) as session:
        res_fail = record_payment_result(session, order_id, "FAILED", "DEMO_OPERATOR", "cb-key-2")
        session.commit()
        assert res_fail.payment_status == "PAID"  # Did not regress!

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.payment_status == "PAID"
        late_event = session.exec(
            select(PaymentEvent).where(PaymentEvent.event_key == "cb-key-2")
        ).one()
        assert late_event.from_status == late_event.to_status == "PAID"

    check_invariants(engine)


# ==============================================================================
# 9. Legacy orders edge cases (Section 10 & Criterion L)
# ==============================================================================


def test_legacy_order_edge_cases_and_isolation(api, engine):
    """Section 10: legacy orders (payment_method IS NULL) never release or refund."""
    order_id, child_id = place_order(engine, "COD", price=65_000, quantity=1, key="leg-order")

    # Make legacy
    with Session(engine) as session:
        session.exec(text(f"UPDATE orders SET payment_method = NULL WHERE id = {order_id}"))
        session.commit()

    # Buyer receipt: null payment fields
    buyer_res = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine))
    assert buyer_res.status_code == 200
    buyer_data = buyer_res.json()["data"]
    assert buyer_data["payment_method"] is None
    assert buyer_data["payment_status"] is None
    assert buyer_data["paid_amount"] is None
    assert buyer_data["refunded_amount"] is None

    # Seller receipt: null settlement fields
    seller_res = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine, SELLER_ID))
    assert seller_res.status_code == 200
    seller_data = seller_res.json()["data"]["sub_orders"][0]
    assert seller_data["commission_amount"] is None
    assert seller_data["seller_net_amount"] is None
    assert seller_data["settled_at"] is None

    # Operator command rejected on legacy order
    with Session(engine) as session, pytest.raises(PaymentError) as exc_info:
        record_payment_result(session, order_id, "PAID", "DEMO_OPERATOR", "leg-op")
    assert exc_info.value.code == "ERR_INVALID_TRANSITION"

    # Fulfilling legacy order to COMPLETED never releases escrow
    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "COMPLETED", sub_order_id=child_id)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "COMPLETED"
        assert child.escrow_status == "HELD"  # Never released!
        assert child.settled_at is None
        events = session.exec(select(PaymentEvent).where(PaymentEvent.order_id == order_id)).all()
        assert events == []  # Invariant I8: legacy orders have no payment events

    check_invariants(engine)


# ==============================================================================
# 10. COD lifecycle and return settlement edge cases
# ==============================================================================


def test_cod_cancellation_before_delivery_leaves_unpaid_voided(engine):
    """COD cancelled before delivery stays UNPAID, escrow VOIDED, refunded_amount = 0."""
    order_id, child_id = place_order(engine, "COD", price=45_000, quantity=1, key="cod-cancel")
    with Session(engine) as session:
        workflow.buyer_cancellation(session, BUYER_ID, order_id, "CANCELLED")

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "CANCELLED"
        assert child.payment_status == "UNPAID"
        assert child.escrow_status == "VOIDED"
        assert child.refunded_amount == 0
        events = session.exec(select(PaymentEvent).where(PaymentEvent.order_id == order_id)).all()
        assert events == []

    check_invariants(engine)


def test_cod_delivered_then_return_approved_refunds_collected_cash(api, engine):
    """COD collected upon delivery: approved return refunds payment and sets escrow to VOIDED."""
    order_id, child_id = place_order(engine, "COD", price=130_000, quantity=1, key="cod-ret")

    with Session(engine) as session:
        workflow.seller_status_change(session, SELLER_ID, "PROCESSING", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "SHIPPED", sub_order_id=child_id)
        workflow.seller_status_change(session, SELLER_ID, "DELIVERED", sub_order_id=child_id)

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.payment_status == "PAID"  # Collected upon delivery!
        assert child.escrow_status == "HELD"

    # Request return
    ret_res = api.post(
        f"/api/v1/orders/{order_id}/returns",
        json={"reason": "Wrong size", "evidence": "item.png"},
        headers=headers(engine),
    )
    assert ret_res.status_code == 201
    return_id = ret_res.json()["data"]["id"]

    # Approve return
    app_res = api.post(
        f"/api/v1/return-requests/{return_id}/decision",
        json={"action": "APPROVE", "is_restockable": True},
        headers=headers(engine, SELLER_ID),
    )
    assert app_res.status_code == 200

    with Session(engine) as session:
        child = session.get(SellerOrder, child_id)
        assert child.status == "RETURNED_REFUNDED"
        assert child.payment_status == "REFUNDED"
        assert child.escrow_status == "VOIDED"
        assert child.refunded_amount == 130_000
        refund_events = session.exec(
            select(PaymentEvent).where(
                PaymentEvent.seller_order_id == child_id,
                PaymentEvent.kind == "REFUND",
            )
        ).all()
        assert len(refund_events) == 1
        assert refund_events[0].amount == 130_000

    check_invariants(engine)
