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


def test_immutable_address_snapshot_after_editing_and_deleting_address(api, engine):
    """Orders retain their immutable delivery snapshot after address updates and deletion."""
    add_product(engine, "P-100", stock=20)
    fill(engine)

    # 1. Create Address 1
    addr1_payload = {
        "recipient_name": "Phạm Quốc Anh",
        "phone_number": "+84 (912) 888-999",
        "province": "TP Hồ Chí Minh",
        "district": "Quận 1",
        "ward": "Phường Bến Nghé",
        "detailed_address": "12 Lê Duẩn",
    }
    res = api.post(URL, json=addr1_payload, headers=headers(engine))
    assert res.status_code == 201
    addr1 = res.json()["data"]
    assert addr1["is_default"] is True
    assert addr1["version"] == 1

    # 2. Place Order 1 with saved Address 1
    order1_body = saved(addr1)
    order1_res = api.post(
        "/api/v1/orders", json=order1_body, headers=headers(engine, key="key-order-1")
    )
    assert order1_res.status_code == 201
    order1 = order1_res.json()["data"]
    expected_addr1_full = "12 Lê Duẩn, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh"
    assert order1["recipient_name"] == "Phạm Quốc Anh"
    assert order1["phone_number"] == "+84 (912) 888-999"
    assert order1["delivery_address"] == expected_addr1_full

    with Session(engine) as session:
        db_order1 = session.get(Order, order1["id"])
        assert db_order1.recipient_name == "Phạm Quốc Anh"
        assert db_order1.phone_number == "+84 (912) 888-999"
        assert db_order1.delivery_address == expected_addr1_full

    # 3. Update Address 1 (version 2) with new recipient and location
    addr2_payload = {
        "recipient_name": "Ngô Thị Bích",
        "phone_number": "0987-654-321",
        "province": "Đà Nẵng",
        "district": "Sơn Trà",
        "ward": "An Hải Bắc",
        "detailed_address": "88 Võ Văn Kiệt",
        "version": addr1["version"],
    }
    update_res = api.put(f"{URL}/{addr1['id']}", json=addr2_payload, headers=headers(engine))
    assert update_res.status_code == 200
    addr1_v2 = update_res.json()["data"]
    assert addr1_v2["version"] == 2
    assert addr1_v2["recipient_name"] == "Ngô Thị Bích"

    # 4. Verify Order 1 snapshot remains unchanged in DB and via API
    fetch_order1 = api.get(f"/api/v1/orders/{order1['id']}", headers=headers(engine)).json()["data"]
    assert fetch_order1["recipient_name"] == "Phạm Quốc Anh"
    assert fetch_order1["phone_number"] == "+84 (912) 888-999"
    assert fetch_order1["delivery_address"] == expected_addr1_full

    with Session(engine) as session:
        db_order1_after = session.get(Order, order1["id"])
        assert db_order1_after.recipient_name == "Phạm Quốc Anh"
        assert db_order1_after.phone_number == "+84 (912) 888-999"
        assert db_order1_after.delivery_address == expected_addr1_full

    # 5. Place Order 2 with updated Address 1 (version 2)
    fill(engine)
    order2_body = saved(addr1_v2)
    order2_res = api.post(
        "/api/v1/orders", json=order2_body, headers=headers(engine, key="key-order-2")
    )
    assert order2_res.status_code == 201
    order2 = order2_res.json()["data"]
    expected_addr2_full = "88 Võ Văn Kiệt, An Hải Bắc, Sơn Trà, Đà Nẵng"
    assert order2["recipient_name"] == "Ngô Thị Bích"
    assert order2["phone_number"] == "0987-654-321"
    assert order2["delivery_address"] == expected_addr2_full

    # 6. Delete Address 1
    del_res = api.delete(f"{URL}/{addr1['id']}", headers=headers(engine))
    assert del_res.status_code == 204

    # 7. Verify both Order 1 and Order 2 retain snapshots via API and DB
    order1_after_del = api.get(
        f"/api/v1/orders/{order1['id']}", headers=headers(engine)
    ).json()["data"]
    assert order1_after_del["recipient_name"] == "Phạm Quốc Anh"
    assert order1_after_del["phone_number"] == "+84 (912) 888-999"
    assert order1_after_del["delivery_address"] == expected_addr1_full

    order2_after_del = api.get(
        f"/api/v1/orders/{order2['id']}", headers=headers(engine)
    ).json()["data"]
    assert order2_after_del["recipient_name"] == "Ngô Thị Bích"
    assert order2_after_del["phone_number"] == "0987-654-321"
    assert order2_after_del["delivery_address"] == expected_addr2_full

    with Session(engine) as session:
        db_order1_final = session.get(Order, order1["id"])
        assert db_order1_final.recipient_name == "Phạm Quốc Anh"
        assert db_order1_final.delivery_address == expected_addr1_full

        db_order2_final = session.get(Order, order2["id"])
        assert db_order2_final.recipient_name == "Ngô Thị Bích"
        assert db_order2_final.delivery_address == expected_addr2_full

    # 8. Idempotent replays of Order 1 and Order 2 return 200 with original data
    replay1 = api.post(
        "/api/v1/orders", json=order1_body, headers=headers(engine, key="key-order-1")
    )
    assert replay1.status_code == 200
    assert replay1.json()["data"]["id"] == order1["id"]
    assert replay1.json()["data"]["recipient_name"] == "Phạm Quốc Anh"
    assert replay1.json()["data"]["delivery_address"] == expected_addr1_full

    replay2 = api.post(
        "/api/v1/orders", json=order2_body, headers=headers(engine, key="key-order-2")
    )
    assert replay2.status_code == 200
    assert replay2.json()["data"]["id"] == order2["id"]
    assert replay2.json()["data"]["recipient_name"] == "Ngô Thị Bích"
    assert replay2.json()["data"]["delivery_address"] == expected_addr2_full

    # 9. New checkout attempt with the deleted address returns 404
    fill(engine)
    res_new_with_deleted = api.post(
        "/api/v1/orders", json=saved(addr1_v2), headers=headers(engine, key="key-order-3")
    )
    assert res_new_with_deleted.status_code == 404
    assert res_new_with_deleted.json()["error"]["code"] == "ERR_ADDRESS_NOT_FOUND"

