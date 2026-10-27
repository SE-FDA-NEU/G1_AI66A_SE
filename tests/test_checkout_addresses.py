"""Saved-address snapshots must survive edits/deletes and idempotent retries."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlmodel import Session, select

from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.user_address import UserAddress
from src.schemas.orders import SavedAddressCheckoutRequest
from src.services.orders import checkout
from tests import test_addresses as address_tests
from tests.cart_db import add_product, stored_lines, stored_stock
from tests.test_addresses import ADDRESS, URL, create
from tests.test_checkout import BODY, counts, fill, headers

api = address_tests.api
engine = address_tests.engine


def saved(row):
    return {"address_id": row["id"], "address_version": row["version"]}


def test_snapshot_edit_delete_replay_and_new_order(api, engine):
    row = create(api, engine)
    add_product(engine, "P-100")
    fill(engine)
    body = saved(row)
    response = api.post("/api/v1/orders", json=body, headers=headers(engine))
    assert response.status_code == 201, response.text
    first = response.json()["data"]
    assert first["recipient_name"] == "Nguyễn Minh"
    assert first["phone_number"] == ADDRESS["phone_number"]
    assert first["delivery_address"] == "12 Phố Chùa Láng, Láng Thượng, Đống Đa, Hà Nội"
    changed = api.put(
        f"{URL}/{row['id']}",
        json={
            **ADDRESS,
            "version": 1,
            "recipient_name": "New name",
            "phone_number": "0987654321",
            "detailed_address": "New street",
            "ward": "New ward",
            "district": "New district",
            "province": "New city",
        },
        headers=headers(engine),
    )
    newer = changed.json()["data"]
    assert api.get(f"/api/v1/orders/{first['id']}", headers=headers(engine)).json()["data"] == first
    replay = api.post("/api/v1/orders", json=body, headers=headers(engine))
    assert replay.status_code == 200 and replay.json()["data"] == first
    fill(engine)
    second = api.post("/api/v1/orders", json=saved(newer), headers=headers(engine, key="second"))
    assert second.status_code == 201
    assert (
        second.json()["data"]["delivery_address"] == "New street, New ward, New district, New city"
    )
    api.delete(f"{URL}/{row['id']}", headers=headers(engine))
    assert api.get(f"/api/v1/orders/{first['id']}", headers=headers(engine)).json()["data"] == first
    replay = api.post("/api/v1/orders", json=body, headers=headers(engine))
    assert replay.status_code == 200 and replay.json()["data"] == first
    for different in [saved(newer), BODY, {**body, "address_id": 999}]:
        response = api.post("/api/v1/orders", json=different, headers=headers(engine))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ERR_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("kind", ["foreign", "missing", "stale", "deleted"])
def test_invalid_address_does_not_write(api, engine, kind):
    row = create(api, engine, buyer=3 if kind == "foreign" else 2)
    body = saved(row)
    if kind == "missing":
        body["address_id"] = 999
    elif kind == "stale":
        body["address_version"] = 99
    elif kind == "deleted":
        api.delete(f"{URL}/{row['id']}", headers=headers(engine))
    add_product(engine, "P-100")
    fill(engine)
    response = api.post("/api/v1/orders", json=body, headers=headers(engine))
    assert response.status_code == (409 if kind == "stale" else 404)
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    assert stored_lines(engine, 2) == [("P-100", 1)]


@pytest.mark.parametrize(
    "body",
    [
        {"address_id": True, "address_version": 1},
        {"address_id": "1", "address_version": 1},
        {"address_id": 1, "address_version": False},
        {"address_id": 0, "address_version": 1},
        {"address_id": 1},
        {"address_id": 1, "address_version": 1, **BODY},
        [],
        "text",
    ],
)
def test_checkout_address_validation(api, engine, body):
    response = api.post("/api/v1/orders", json=body, headers=headers(engine))
    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert fields and not any("Request" in name for name in fields)
    if isinstance(body, dict) and "recipient_name" in body:
        assert "_form" in fields
    assert counts(engine) == [0, 0, 0]


def test_saved_checkout_selected_only_and_stock_rollback(api, engine):
    row = create(api, engine)
    add_product(engine, "P-100")
    add_product(engine, "P-200", stock=0)
    fill(engine)
    fill(engine, code="P-200")
    response = api.post("/api/v1/orders", json=saved(row), headers=headers(engine))
    assert response.status_code == 409 and counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    with Session(engine) as session:
        line = session.exec(select(CartItem).order_by(CartItem.id.desc())).first()
        line.is_selected = False
        session.add(line)
        session.commit()
    response = api.post("/api/v1/orders", json=saved(row), headers=headers(engine))
    assert response.status_code == 201
    assert stored_lines(engine, 2) == [("P-200", 1)]


def test_legacy_hash_stays_compatible(api, engine):
    add_product(engine, "P-100")
    fill(engine)
    result = api.post("/api/v1/orders", json=BODY, headers=headers(engine))
    assert result.status_code == 201
    # Exact serialization used before US13; separators/field ordering/phone must stay unchanged.
    historical = (
        '{"recipient_name":"Buyer","delivery_address":"123 Main Street",'
        '"phone_number":"0912345678"}'
    )
    with Session(engine) as session:
        order = session.exec(select(Order)).one()
        assert order.request_hash == hashlib.sha256(historical.encode()).hexdigest()
    assert api.post("/api/v1/orders", json=BODY, headers=headers(engine)).status_code == 200


def test_saved_checkout_concurrent_same_key(api, engine):
    row = create(api, engine)
    add_product(engine, "P-100", stock=1)
    fill(engine)
    barrier = Barrier(2)

    def worker(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return checkout(session, 2, SavedAddressCheckoutRequest(**saved(row)), "same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert results[0][0] == results[1][0]
    assert sum(result[1] for result in results) == 1
    assert counts(engine) == [1, 1, 1] and stored_stock(engine, "P-100") == (0, 0)


def test_checkout_failure_after_snapshot_rolls_back(api, engine, monkeypatch):
    import src.services.orders as service

    row = create(api, engine)
    add_product(engine, "P-100")
    fill(engine)
    original = service.receipt

    def fail(*_):
        raise RuntimeError("failure after writes")

    monkeypatch.setattr(service, "receipt", fail)
    with Session(engine) as session, pytest.raises(RuntimeError):
        checkout(session, 2, SavedAddressCheckoutRequest(**saved(row)), "fail")
    monkeypatch.setattr(service, "receipt", original)
    assert counts(engine) == [0, 0, 0]
    assert stored_stock(engine, "P-100") == (10, 0)
    with Session(engine) as session:
        assert session.get(UserAddress, row["id"]).version == 1
