from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.user import User
from src.models.voucher import Voucher
from tests.cart_db import BUYER_ID, SELLER_ID, create_cart_engine


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "seller_vouchers.db")
    yield value
    value.dispose()


@pytest.fixture
def api(engine):
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client


def headers(engine, user_id=SELLER_ID):
    with Session(engine) as session:
        token = create_access_token(session.get(User, user_id))
    return {"Authorization": f"Bearer {token}"}


def valid_payload(**changes):
    now = datetime.now(UTC)
    return {
        "code": "SHOP10",
        "discount_type": "PERCENTAGE",
        "discount_value": 1000,
        "max_discount": 50_000,
        "min_order_value": 200_000,
        "usage_limit": 100,
        "per_user_limit": 2,
        "starts_at": (now - timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=30)).isoformat(),
        "is_active": True,
        **changes,
    }


def test_seller_can_create_list_and_toggle_owned_voucher(api, engine):
    created = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(),
    )
    assert created.status_code == 201
    voucher = created.json()
    assert voucher["scope"] == "SHOP"
    assert voucher["seller_id"] == SELLER_ID

    listed = api.get("/api/v1/seller/vouchers", headers=headers(engine))
    assert [item["code"] for item in listed.json()] == ["SHOP10"]

    updated = api.patch(
        f"/api/v1/seller/vouchers/{voucher['id']}",
        headers=headers(engine),
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_seller_voucher_validation_and_ownership(api, engine):
    invalid = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(code="bad code", discount_value=0),
    )
    assert invalid.status_code == 422

    invalid_dates = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(
            code="BADDATE",
            ends_at=(datetime.now(UTC) - timedelta(days=2)).isoformat(),
        ),
    )
    assert invalid_dates.status_code == 400
    assert invalid_dates.json()["error"]["code"] == "ERR_INVALID_DATES"

    buyer = api.get("/api/v1/seller/vouchers", headers=headers(engine, BUYER_ID))
    assert buyer.status_code == 403


def test_duplicate_voucher_code_returns_conflict_even_when_database_rejects_it(api, engine):
    first = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(),
    )
    assert first.status_code == 201

    duplicate = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(code="shop10"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ERR_VOUCHER_EXISTS"


def test_patch_validates_discount_dates_usage_and_nullable_fields(api, engine):
    created = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(),
    ).json()
    voucher_id = created["id"]

    incompatible = api.patch(
        f"/api/v1/seller/vouchers/{voucher_id}",
        headers=headers(engine),
        json={"discount_type": "FREE_SHIPPING", "discount_value": 100},
    )
    assert incompatible.status_code == 400
    assert incompatible.json()["error"]["code"] == "ERR_INVALID_DISCOUNT"

    invalid_dates = api.patch(
        f"/api/v1/seller/vouchers/{voucher_id}",
        headers=headers(engine),
        json={"starts_at": valid_payload()["ends_at"]},
    )
    assert invalid_dates.status_code == 400
    assert invalid_dates.json()["error"]["code"] == "ERR_INVALID_DATES"

    with Session(engine) as session:
        voucher = session.get(Voucher, voucher_id)
        voucher.used_count = 3
        session.add(voucher)
        session.commit()

    invalid_limit = api.patch(
        f"/api/v1/seller/vouchers/{voucher_id}",
        headers=headers(engine),
        json={"usage_limit": 2},
    )
    assert invalid_limit.status_code == 400
    assert invalid_limit.json()["error"]["code"] == "ERR_INVALID_USAGE_LIMIT"

    cleared = api.patch(
        f"/api/v1/seller/vouchers/{voucher_id}",
        headers=headers(engine),
        json={"max_discount": None, "usage_limit": None, "per_user_limit": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["max_discount"] is None
    assert cleared.json()["usage_limit"] is None
    assert cleared.json()["per_user_limit"] is None


def test_seller_cannot_manage_another_shop_voucher(api, engine):
    created = api.post(
        "/api/v1/seller/vouchers",
        headers=headers(engine),
        json=valid_payload(),
    )
    voucher_id = created.json()["id"]
    with Session(engine) as session:
        other = User(id=4, name="Other Seller", email="other-seller@test.local", role="seller")
        session.add(other)
        session.commit()

    response = api.patch(
        f"/api/v1/seller/vouchers/{voucher_id}",
        headers=headers(engine, 4),
        json={"is_active": False},
    )
    assert response.status_code == 404
    with Session(engine) as session:
        assert session.exec(select(Voucher).where(Voucher.id == voucher_id)).one().is_active
