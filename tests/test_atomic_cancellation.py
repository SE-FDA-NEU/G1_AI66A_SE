"""Cancellation effects observed through new sessions on real SQLite files."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event
from sqlmodel import Session, select
from starlette.testclient import TestClient

import src.services.order_workflow as workflow
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_history import OrderHistory
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.product_variant import ProductVariant
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.orders import CheckoutRequest
from src.services.orders import checkout
from tests.cart_db import add_product, create_cart_engine
from tests.test_checkout import BODY, headers


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "cancellation.db")
    yield value
    value.dispose()


@pytest.fixture
def api(engine):
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def purchase(engine, *, variant=False, shops=1):
    ids = [add_product(engine, f"CANCEL-{i}", stock=10) for i in range(shops)]
    with Session(engine) as session:
        if shops > 1:
            session.add(User(id=4, name="Other shop", email="shop2@test.local", role="seller"))
            session.flush()
            product = session.get(Product, ids[1])
            product.seller_id = 4
            session.add(product)
        for product_id in ids:
            variant_id = None
            if variant:
                item = ProductVariant(
                    product_id=product_id,
                    seller_id=1,
                    sku="CANCEL-V",
                    name="Variant",
                    price=100,
                    stock_quantity=10,
                )
                session.add(item)
                session.flush()
                variant_id = item.id
            session.add(
                CartItem(buyer_id=2, product_id=product_id, variant_id=variant_id, quantity=2)
            )
        session.commit()
        order, _ = checkout(session, 2, CheckoutRequest(**BODY), "purchase")
        return order.id, [child.id for child in order.sub_orders], ids


def snapshot(engine):
    with Session(engine) as session:
        return {
            model.__tablename__: [
                row.model_dump()
                for row in session.exec(
                    select(model).order_by(
                        model.id if model != ProductMetadata else model.product_id
                    )
                ).all()
            ]
            for model in (
                Order,
                SellerOrder,
                Product,
                ProductVariant,
                ProductMetadata,
                OrderHistory,
                Notification,
            )
        }


def assert_cancelled(engine, order_id, children, products):
    with Session(engine) as session:
        parent = session.get(Order, order_id)
        assert (parent.status, parent.payment_status) == ("CANCELLED", "REFUNDED")
        for child_id in children:
            child = session.get(SellerOrder, child_id)
            assert (child.status, child.payment_status, child.escrow_status) == (
                "CANCELLED",
                "REFUNDED",
                "REFUNDED",
            )
        for product_id in products:
            assert session.get(Product, product_id).stock_quantity == 10
            assert session.get(ProductMetadata, product_id).sales_count == 0
        history = session.exec(select(OrderHistory)).all()
        assert len(history) == len(children)
        assert all(row.to_status == "CANCELLED" for row in history)
        notifications = session.exec(
            select(Notification).where(Notification.recipient_user_id == 2)
        ).all()
        assert len(notifications) == len(children)


@pytest.mark.parametrize("route", ["buyer-post", "buyer-patch", "seller-patch", "seller-legacy"])
def test_all_cancellation_routes_restore_once(api, engine, route):
    order_id, children, products = purchase(engine)
    actor = 1 if route.startswith("seller") else 2
    url = (
        f"/api/v1/seller/orders/{children[0]}/status"
        if route == "seller-patch"
        else f"/api/v1/orders/{order_id}/status"
    )

    def request():
        if route == "buyer-post":
            return api.post(f"/api/v1/orders/{order_id}/cancel", headers=headers(engine, actor))
        return api.patch(url, json={"status": "CANCELLED"}, headers=headers(engine, actor))

    first = request()
    assert first.status_code == 200, first.text
    after = snapshot(engine)
    assert request().status_code == 400
    assert snapshot(engine) == after
    assert_cancelled(engine, order_id, children, products)


@pytest.mark.parametrize("stage", ["inventory", "notification", "parent", "commit"])
def test_failure_rolls_back_all_effects_and_allows_retry(engine, monkeypatch, stage):
    order_id, children, products = purchase(engine, shops=2)
    before = snapshot(engine)
    function_name = {
        "inventory": "restore_order_item_stock",
        "notification": "create_notification",
        "parent": "_sync_parent",
    }.get(stage)
    original = getattr(workflow, function_name) if function_name else None

    def fail(*args, **kwargs):
        if original:
            original(*args, **kwargs)
        raise RuntimeError("injected cancellation failure")

    with monkeypatch.context() as patch:
        if function_name:
            patch.setattr(workflow, function_name, fail)
        with Session(engine) as session:
            if stage == "commit":
                event.listen(session, "before_commit", fail)
            with pytest.raises(RuntimeError, match="injected"):
                workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
    assert snapshot(engine) == before
    with Session(engine) as session:
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
    assert_cancelled(engine, order_id, children, products)


@pytest.mark.parametrize("payment", ["PAID", "UNPAID", "FAILED"])
def test_cancellation_only_marks_collected_payments_refunded(engine, payment):
    order_id, children, products = purchase(engine)
    with Session(engine) as session:
        child = session.get(SellerOrder, children[0])
        child.payment_status = payment
        session.add(child)
        session.commit()
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
    with Session(engine) as session:
        parent = session.get(Order, order_id)
        child = session.get(SellerOrder, children[0])
        expected = "REFUNDED" if payment == "PAID" else payment
        assert parent.payment_status == child.payment_status == expected
        assert (
            parent.escrow_status
            == child.escrow_status
            == ("REFUNDED" if payment == "PAID" else "VOIDED")
        )


def test_partial_seller_cancellation_leaves_other_shop_untouched(engine):
    order_id, children, products = purchase(engine, shops=2)
    with Session(engine) as session:
        workflow.seller_status_change(session, 1, "CANCELLED", sub_order_id=children[0])
    with Session(engine) as session:
        assert session.get(Order, order_id).payment_status == "PARTIALLY_REFUNDED"
        assert session.get(SellerOrder, children[1]).payment_status == "PAID"
        assert session.get(SellerOrder, children[1]).status == "PENDING"
        assert session.get(Product, products[1]).stock_quantity == 8
        assert session.get(ProductMetadata, products[1]).sales_count == 2
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
    assert_cancelled(engine, order_id, children, products)


def test_request_cancellation_has_no_inventory_or_refund_effect(engine):
    order_id, children, products = purchase(engine)
    with Session(engine) as session:
        workflow.seller_status_change(session, 1, "CONFIRMED", sub_order_id=children[0])
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLATION_REQUESTED")
    with Session(engine) as session:
        assert session.get(SellerOrder, children[0]).payment_status == "PAID"
        assert session.get(Product, products[0]).stock_quantity == 8
        assert session.get(ProductMetadata, products[0]).sales_count == 2
        workflow.seller_status_change(session, 1, "CANCELLED", sub_order_id=children[0])
    with Session(engine) as session:
        assert session.get(Product, products[0]).stock_quantity == 10
        assert session.get(SellerOrder, children[0]).payment_status == "REFUNDED"


def test_cancel_restores_only_purchased_inactive_variant(engine):
    order_id, children, products = purchase(engine, variant=True)
    with Session(engine) as session:
        product = session.get(Product, products[0])
        product.is_active = False
        variant = session.exec(select(ProductVariant)).one()
        variant.is_active = False
        session.add_all([product, variant])
        session.commit()
        workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
    with Session(engine) as session:
        assert session.exec(select(ProductVariant)).one().stock_quantity == 10
        assert session.get(Product, products[0]).stock_quantity == 10
        assert session.get(Product, products[0]).version == 1


@pytest.mark.parametrize(
    "actors", [("buyer", "seller"), ("seller", "seller"), ("cancel", "confirm")]
)
def test_competing_requests_cannot_duplicate_restore_or_resurrect_order(engine, actors):
    order_id, children, products = purchase(engine)
    barrier = Barrier(2)

    def worker(actor):
        with Session(engine) as session:
            # Both operations begin with the same version of the child.
            child = session.get(SellerOrder, children[0])
            assert child.status == "PENDING"
            barrier.wait(timeout=10)
            try:
                if actor == "buyer":
                    workflow.buyer_cancellation(session, 2, order_id, "CANCELLED")
                else:
                    status = "CONFIRMED" if actor == "confirm" else "CANCELLED"
                    workflow.seller_status_change(session, 1, status, sub_order_id=children[0])
                return 200
            except workflow.WorkflowError as exc:
                return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, actors))
    assert 200 in results
    with Session(engine) as session:
        child = session.get(SellerOrder, children[0])
        restored = child.status == "CANCELLED"
        assert session.get(Product, products[0]).stock_quantity == (10 if restored else 8)
        history = session.exec(select(OrderHistory)).all()
        assert sum(row.to_status == "CANCELLED" for row in history) == int(restored)
        notifications = session.exec(
            select(Notification).where(Notification.recipient_user_id == 2)
        ).all()
        assert len(notifications) == len(history)


def test_foreign_actor_and_shipped_child_cannot_cancel(api, engine):
    order_id, children, products = purchase(engine)
    before = snapshot(engine)
    assert (
        api.post(f"/api/v1/orders/{order_id}/cancel", headers=headers(engine, 3)).status_code == 404
    )
    assert snapshot(engine) == before
    with Session(engine) as session:
        workflow.seller_status_change(session, 1, "PROCESSING", sub_order_id=children[0])
        workflow.seller_status_change(session, 1, "SHIPPED", sub_order_id=children[0])
    before = snapshot(engine)
    assert (
        api.patch(
            f"/api/v1/orders/{order_id}/status",
            json={"status": "CANCELLED"},
            headers=headers(engine),
        ).status_code
        == 400
    )
    assert snapshot(engine) == before
