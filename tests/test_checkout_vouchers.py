"""Quote and voucher checkout on an isolated database (#136, US16 section 5).

The amounts are the worked example of docs/us16-promotions.md section 2.1:
seller 1 sells 2 x 150.000 and seller 4 sells 1 x 200.000 ₫.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from src.models.voucher_usage import VoucherUsage
from tests import test_atomic_cancellation as cancellation
from tests.cart_db import BUYER_ID, SELLER_ID, add_product
from tests.test_checkout import BODY, headers

api = cancellation.api
engine = cancellation.engine
OTHER_SELLER_ID = 4
NOW = datetime.now(UTC)
VOUCHERS = {
    "shop_vouchers": [{"seller_id": SELLER_ID, "code": "SHOPA30K"}],
    "platform_voucher": "PLAT10",
    "shipping_voucher": "FREESHIP15",
}


def setup_cart(engine):
    first = add_product(engine, "VOU-A", price=150_000)
    second = add_product(engine, "VOU-B", price=200_000)
    with Session(engine) as session:
        session.add(User(id=OTHER_SELLER_ID, name="Shop B", email="b@test.local", role="seller"))
        session.flush()
        session.get(Product, second).seller_id = OTHER_SELLER_ID
        session.add(CartItem(buyer_id=BUYER_ID, product_id=first, quantity=2))
        session.add(CartItem(buyer_id=BUYER_ID, product_id=second, quantity=1))
        session.commit()


def add_voucher(engine, code, **fields):
    values = {
        "code": code,
        "scope": "PLATFORM",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 10_000,
        "starts_at": NOW - timedelta(days=1),
        "ends_at": NOW + timedelta(days=1),
    } | fields
    with Session(engine) as session:
        session.add(Voucher(**values))
        session.commit()


def seed_example(engine):
    setup_cart(engine)
    add_voucher(engine, "SHOPA30K", scope="SHOP", seller_id=SELLER_ID, discount_value=30_000)
    add_voucher(
        engine, "PLAT10", discount_type="PERCENTAGE", discount_value=1000, max_discount=50_000
    )
    add_voucher(
        engine, "FREESHIP15", discount_type="FREE_SHIPPING", discount_value=0, max_discount=15_000
    )


def quote(api, engine, body=VOUCHERS):
    return api.post("/api/v1/orders/quote", json=body, headers=headers(engine))


def place(api, engine, body, key="voucher-key"):
    return api.post("/api/v1/orders", json=BODY | body, headers=headers(engine, key=key))


def usage_state(engine):
    with Session(engine) as session:
        return (
            sorted((v.code, v.used_count) for v in session.exec(select(Voucher))),
            len(session.exec(select(VoucherUsage)).all()),
            len(session.exec(select(Order)).all()),
            len(session.exec(select(CartItem)).all()),
        )


def test_quote_prices_the_worked_example(api, engine):
    seed_example(engine)

    response = quote(api, engine)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [
        (
            row["seller_id"],
            row["subtotal"],
            row["shop_discount"],
            row["platform_discount"],
            row["shipping_fee"],
            row["shipping_discount"],
            row["total_amount"],
        )
        for row in data["seller_orders"]
    ] == [
        (SELLER_ID, 300_000, 30_000, 27_000, 20_000, 15_000, 248_000),
        (OTHER_SELLER_ID, 200_000, 0, 20_000, 20_000, 15_000, 185_000),
    ]
    assert data["seller_orders"][0]["shop_voucher"]["status"] == "APPLIED"
    assert data["platform_voucher"] == {
        "code": "PLAT10",
        "status": "APPLIED",
        "discount": 47_000,
        "error": None,
    }
    assert data["shipping_voucher"]["discount"] == 30_000
    assert data["grand_total"] == 433_000
    assert len(data["quote_revision"]) == 64


def test_quote_never_consumes_or_writes(api, engine):
    seed_example(engine)
    before = usage_state(engine)

    for _ in range(3):
        assert quote(api, engine).status_code == 200

    assert usage_state(engine) == before


def test_rejected_voucher_is_reported_and_the_rest_is_priced(api, engine):
    seed_example(engine)
    add_voucher(engine, "OLD10", ends_at=NOW - timedelta(hours=1), starts_at=NOW - timedelta(2))

    data = quote(api, engine, VOUCHERS | {"platform_voucher": "OLD10"}).json()["data"]

    assert data["platform_voucher"]["status"] == "REJECTED"
    assert data["platform_voucher"]["error"]["code"] == "ERR_VOUCHER_EXPIRED"
    assert data["platform_discount"] == 0
    assert data["shop_discount"] == 30_000
    assert data["grand_total"] == 500_000 - 30_000 + 40_000 - 30_000


def test_quote_without_vouchers_adds_shipping(api, engine):
    setup_cart(engine)

    data = quote(api, engine, {}).json()["data"]

    assert (data["subtotal"], data["shipping_fee"], data["grand_total"]) == (
        500_000,
        40_000,
        540_000,
    )


def test_checkout_stores_the_quoted_breakdown_and_consumes_vouchers(api, engine):
    seed_example(engine)
    revision = quote(api, engine).json()["data"]["quote_revision"]

    response = place(api, engine, VOUCHERS | {"quote_revision": revision})

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["total_amount"] == 433_000
    assert [(s["total_amount"], s["pricing_policy_version"]) for s in data["sub_orders"]] == [
        (248_000, "US16-V1"),
        (185_000, "US16-V1"),
    ]
    assert sorted((v["code"], v["slot"], v["discount_amount"]) for v in data["vouchers"]) == [
        ("FREESHIP15", "SHIPPING", 30_000),
        ("PLAT10", "PLATFORM", 47_000),
        ("SHOPA30K", "SHOP", 30_000),
    ]
    assert usage_state(engine) == (
        [("FREESHIP15", 1), ("PLAT10", 1), ("SHOPA30K", 1)],
        3,
        1,
        0,
    )

    replay = place(api, engine, VOUCHERS | {"quote_revision": revision})
    assert replay.status_code == 200
    assert replay.json()["data"]["total_amount"] == 433_000
    assert usage_state(engine)[1] == 3


def test_changed_voucher_rule_makes_the_quote_stale(api, engine):
    seed_example(engine)
    revision = quote(api, engine).json()["data"]["quote_revision"]
    with Session(engine) as session:
        voucher = session.exec(select(Voucher).where(Voucher.code == "PLAT10")).one()
        voucher.discount_value = 2000
        session.add(voucher)
        session.commit()
    before = usage_state(engine)

    response = place(api, engine, VOUCHERS | {"quote_revision": revision})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ERR_QUOTE_STALE"
    assert usage_state(engine) == before


def test_changed_price_makes_the_quote_stale(api, engine):
    seed_example(engine)
    revision = quote(api, engine).json()["data"]["quote_revision"]
    with Session(engine) as session:
        product = session.exec(select(Product).where(Product.code == "VOU-B")).one()
        product.price = 210_000
        session.add(product)
        session.commit()

    response = place(api, engine, VOUCHERS | {"quote_revision": revision})

    assert response.json()["error"]["code"] == "ERR_QUOTE_STALE"


def test_voucher_used_up_since_quote_names_its_slot_and_writes_nothing(api, engine):
    seed_example(engine)
    with Session(engine) as session:
        voucher = session.exec(select(Voucher).where(Voucher.code == "PLAT10")).one()
        voucher.usage_limit = 1
        session.add(voucher)
        session.commit()
    revision = quote(api, engine).json()["data"]["quote_revision"]
    with Session(engine) as session:
        voucher = session.exec(select(Voucher).where(Voucher.code == "PLAT10")).one()
        voucher.used_count = 1
        session.add(voucher)
        session.commit()
    before = usage_state(engine)

    response = place(api, engine, VOUCHERS | {"quote_revision": revision})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "ERR_VOUCHER_USAGE_LIMIT"
    assert list(error["fields"]) == ["platform_voucher"]
    assert usage_state(engine) == before


def test_seller_receipt_shows_only_its_own_shop_voucher(api, engine):
    seed_example(engine)
    revision = quote(api, engine).json()["data"]["quote_revision"]
    order_id = place(api, engine, VOUCHERS | {"quote_revision": revision}).json()["data"]["id"]

    seller_b = api.get(f"/api/v1/orders/{order_id}", headers=headers(engine, OTHER_SELLER_ID))

    assert seller_b.status_code == 200, seller_b.text
    data = seller_b.json()["data"]
    assert [s["seller_id"] for s in data["sub_orders"]] == [OTHER_SELLER_ID]
    assert data["vouchers"] == []
    with Session(engine) as session:
        assert len(session.exec(select(SellerOrder)).all()) == 2


def test_one_voucher_per_shop_and_buyer_only(api, engine):
    seed_example(engine)
    twice = {"shop_vouchers": [{"seller_id": 1, "code": "A"}, {"seller_id": 1, "code": "B"}]}

    assert quote(api, engine, twice).status_code == 422
    assert api.post("/api/v1/orders/quote", json={}).status_code == 401
    seller = api.post("/api/v1/orders/quote", json={}, headers=headers(engine, SELLER_ID))
    assert seller.status_code == 403
