"""US13 API, owner isolation, validation and real SQLite transaction tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.testclient import TestClient

from src.database import get_session
from src.main import create_app
from src.models.user_address import UserAddress
from src.schemas.addresses import AddressCreate
from src.services.addresses import AddressError, mutate_address
from tests.cart_db import create_cart_engine
from tests.test_checkout import headers

ADDRESS = dict(
    recipient_name=" Nguyễn Minh ",
    phone_number="+84 (912) 345-678",
    province="Hà Nội",
    district="Đống Đa",
    ward="Láng Thượng",
    detailed_address="12 Phố Chùa Láng",
    is_default=False,
)
URL = "/api/v1/addresses"


@pytest.fixture
def engine(tmp_path):
    value = create_cart_engine(tmp_path / "addresses.db")
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


def create(api, engine, buyer=2, **patch):
    result = api.post(URL, json={**ADDRESS, **patch}, headers=headers(engine, buyer))
    assert result.status_code == 201, result.text
    return result.json()["data"]


def test_crud_defaults_and_persistence(api, engine):
    a = create(api, engine)
    b = create(api, engine)
    c = create(api, engine)
    assert a["is_default"] and not b["is_default"] and not c["is_default"]
    result = api.patch(
        f"{URL}/{b['id']}/default", json={"version": b["version"]}, headers=headers(engine)
    )
    assert result.status_code == 200
    rows = api.get(URL, headers=headers(engine)).json()["data"]
    assert rows[0]["id"] == b["id"]
    assert sum(row["is_default"] for row in rows) == 1
    # Clearing a default is allowed; no other address is silently promoted.
    changed = api.put(
        f"{URL}/{b['id']}",
        headers=headers(engine),
        json={
            **ADDRESS,
            "version": result.json()["data"]["version"],
            "recipient_name": " New recipient ",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["recipient_name"] == "New recipient"
    assert not any(r["is_default"] for r in api.get(URL, headers=headers(engine)).json()["data"])
    deleted = api.delete(f"{URL}/{b['id']}", headers=headers(engine))
    assert deleted.status_code == 204 and deleted.content == b""
    with Session(engine) as session:
        assert session.get(UserAddress, b["id"]) is None
        assert session.get(UserAddress, a["id"]).recipient_name == "Nguyễn Minh"
    assert create(api, engine)["id"] > c["id"]


def test_ownership_auth_and_stale_version_do_not_clear_defaults(api, engine):
    a = create(api, engine)
    b = create(api, engine, buyer=3)
    assert api.get(URL).status_code == 401
    assert api.get(URL, headers=headers(engine, 1)).status_code == 403
    assert [r["id"] for r in api.get(URL, headers=headers(engine)).json()["data"]] == [a["id"]]
    for method, suffix, body in [
        ("put", "", {**ADDRESS, "version": 1}),
        ("patch", "/default", {"version": 1}),
        ("delete", "", None),
    ]:
        for address_id in (b["id"], 999):
            options = {"headers": headers(engine)}
            if body is not None:
                options["json"] = body
            response = getattr(api, method)(f"{URL}/{address_id}{suffix}", **options)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "ERR_ADDRESS_NOT_FOUND"
    for method, suffix, body in [
        ("put", "", {**ADDRESS, "version": 99, "is_default": True}),
        ("patch", "/default", {"version": 99}),
    ]:
        response = getattr(api, method)(
            f"{URL}/{a['id']}{suffix}", json=body, headers=headers(engine)
        )
        assert response.status_code == 409
    assert api.get(URL, headers=headers(engine)).json()["data"][0]["is_default"]
    assert api.get(URL, headers=headers(engine, 3)).json()["data"][0]["is_default"]


@pytest.mark.parametrize(
    "patch",
    [
        {"recipient_name": " "},
        {"province": "\u200b"},
        {"ward": ""},
        {"district": "x" * 101},
        {"detailed_address": "x" * 501},
        {"phone_number": "123456"},
        {"phone_number": "1234567890123456"},
        {"phone_number": "0912abc3456"},
        {"phone_number": "１２３４５６７"},
        {"is_default": 1},
        {"is_default": "true"},
        {"user_id": 3},
        {"id": 1},
        {"version": 1},
    ],
)
def test_address_validation(api, engine, patch):
    response = api.post(URL, json={**ADDRESS, **patch}, headers=headers(engine))
    assert response.status_code == 422
    assert response.json()["error"]["fields"]
    assert api.get(URL, headers=headers(engine)).json()["data"] == []


@pytest.mark.parametrize("payload", [[], "text", None, {"phone_number": "0912345678"}])
def test_invalid_address_shapes(api, engine, payload):
    response = api.post(URL, json=payload, headers=headers(engine))
    assert response.status_code == 422 and response.json()["error"]["fields"]


@pytest.mark.parametrize("version", [True, "1", 0, -1, 1.0])
def test_strict_address_versions(api, engine, version):
    a = create(api, engine)
    assert (
        api.patch(
            f"{URL}/{a['id']}/default", json={"version": version}, headers=headers(engine)
        ).status_code
        == 422
    )


def test_constraint_no_id_reuse_and_init_upgrade(api, engine, monkeypatch):
    import src.database as database

    a = create(api, engine)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO user_addresses "
                "(user_id,recipient_name,phone_number,province,district,ward,"
                "detailed_address,is_default,version,created_at,updated_at) "
                "SELECT user_id,recipient_name,phone_number,province,district,ward,"
                "detailed_address,is_default,version,created_at,updated_at FROM user_addresses"
            )
        )
    api.delete(f"{URL}/{a['id']}", headers=headers(engine))
    assert create(api, engine)["id"] > a["id"]
    # Simulate pre-US13 DB, retaining user rows, then run the real initializer twice.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE user_addresses"))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()
    assert any(
        i["name"] == "ux_user_addresses_one_default"
        for i in inspect(engine).get_indexes("user_addresses")
    )
    assert inspect(engine).get_foreign_keys("user_addresses")[0]["referred_table"] == "users"
    assert create(api, engine)["recipient_name"] == "Nguyễn Minh"


def test_default_failure_rolls_back_clear(api, engine):
    a, b = create(api, engine), create(api, engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER reject_default BEFORE UPDATE ON user_addresses "
                "WHEN NEW.is_default=1 BEGIN SELECT RAISE(ABORT, 'unrelated failure'); END"
            )
        )
    response = api.patch(f"{URL}/{b['id']}/default", json={"version": 1}, headers=headers(engine))
    assert response.status_code == 500
    rows = api.get(URL, headers=headers(engine)).json()["data"]
    assert rows[0]["id"] == a["id"] and rows[0]["version"] == 1


def test_concurrent_default_operations_keep_one_default(api, engine):
    create(api, engine)
    b, c = create(api, engine), create(api, engine)
    barrier = Barrier(2)

    def worker(row):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                return mutate_address(session, 2, "default", address_id=row["id"], version=1)
            except AddressError as exc:
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [b, c]))
    assert any(not isinstance(r, AddressError) for r in results)
    with Session(engine) as session:
        assert len(session.exec(select(UserAddress).where(UserAddress.is_default)).all()) == 1


def test_concurrent_first_addresses_keep_one_default(engine):
    barrier = Barrier(2)

    def worker(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return mutate_address(session, 2, "create", AddressCreate(**ADDRESS))

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(worker, range(2)))
    assert len({row.id for row in rows}) == 2
    with Session(engine) as session:
        assert len(session.exec(select(UserAddress).where(UserAddress.is_default)).all()) == 1


def test_write_predicates_are_owner_scoped(api, engine):
    row = create(api, engine)
    statements = []

    def record(_conn, _cursor, statement, *_):
        if statement.startswith(("UPDATE user_addresses", "DELETE FROM user_addresses")):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        api.put(f"{URL}/{row['id']}", json={**ADDRESS, "version": 1}, headers=headers(engine))
        api.delete(f"{URL}/{row['id']}", headers=headers(engine))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements and all("user_addresses.user_id =" in s.split("WHERE")[1] for s in statements)


def test_busy_retries_are_bounded_and_other_database_errors_propagate(engine, monkeypatch):
    import sqlite3

    from sqlalchemy.exc import OperationalError

    import src.services.addresses as service

    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    calls = []
    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY

    def fail(*_args, **_kwargs):
        calls.append(1)
        raise OperationalError("statement", {}, busy)

    with Session(engine) as session:
        monkeypatch.setattr(session, "exec", fail)
        with pytest.raises(AddressError) as result:
            mutate_address(session, 2, "create", AddressCreate(**ADDRESS))
        assert result.value.code == "ERR_CONCURRENCY_CONFLICT"
        assert len(calls) == 5
        calls.clear()
        busy.sqlite_errorcode = sqlite3.SQLITE_ERROR
        with pytest.raises(OperationalError):
            mutate_address(session, 2, "create", AddressCreate(**ADDRESS))
        assert len(calls) == 1


def test_malformed_json_and_missing_fields_have_safe_guidance(api, engine):
    response = api.post(URL, content='{"phone_number":', headers=headers(engine))
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"_form"}
    for name in (
        "recipient_name",
        "phone_number",
        "province",
        "district",
        "ward",
        "detailed_address",
    ):
        body = {key: value for key, value in ADDRESS.items() if key != name}
        response = api.post(URL, json=body, headers=headers(engine))
        assert response.status_code == 422
        assert name in response.json()["error"]["fields"]
        assert "input" not in response.json()["error"]["fields"]


# ==============================================================================
# Address Ownership, CRUD, Default-Behavior, and Validation Tests (Task #105)
# ==============================================================================


def test_address_crud_operations_and_whitespace_trimming(api, engine):
    """Full CRUD lifecycle: creates with trimmed fields, reads, updates, and deletes cleanly."""
    untrimmed = {
        "recipient_name": "  Lê Thị Thu Trang  ",
        "phone_number": " +84 (987) 654-321 ",
        "province": "  Hà Nội  ",
        "district": "  Cầu Giấy  ",
        "ward": "  Dịch Vọng Hậu  ",
        "detailed_address": "  Số 15 Duy Tân  ",
        "is_default": False,
    }
    res_create = api.post(URL, json=untrimmed, headers=headers(engine))
    assert res_create.status_code == 201
    created = res_create.json()["data"]

    # Verify whitespace trimming across all fields
    assert created["recipient_name"] == "Lê Thị Thu Trang"
    assert created["phone_number"] == "+84 (987) 654-321"
    assert created["province"] == "Hà Nội"
    assert created["district"] == "Cầu Giấy"
    assert created["ward"] == "Dịch Vọng Hậu"
    assert created["detailed_address"] == "Số 15 Duy Tân"
    assert created["is_default"] is True  # First address is promoted to default
    assert created["version"] == 1
    assert "user_id" not in created
    assert created["id"] > 0
    addr_id = created["id"]

    # Read: GET /api/v1/addresses
    res_list = api.get(URL, headers=headers(engine))
    assert res_list.status_code == 200
    addresses = res_list.json()["data"]
    assert len(addresses) == 1
    assert addresses[0]["id"] == addr_id

    # Update: PUT /api/v1/addresses/{id}
    update_payload = {
        "recipient_name": "  Trần Văn Nam  ",
        "phone_number": " 0912-345-678 ",
        "province": "  Đà Nẵng  ",
        "district": "  Hải Châu  ",
        "ward": "  Thạch Thang  ",
        "detailed_address": "  Số 42 Bạch Đằng  ",
        "is_default": True,
        "version": 1,
    }
    res_update = api.put(f"{URL}/{addr_id}", json=update_payload, headers=headers(engine))
    assert res_update.status_code == 200
    updated = res_update.json()["data"]
    assert updated["recipient_name"] == "Trần Văn Nam"
    assert updated["phone_number"] == "0912-345-678"
    assert updated["province"] == "Đà Nẵng"
    assert updated["district"] == "Hải Châu"
    assert updated["ward"] == "Thạch Thang"
    assert updated["detailed_address"] == "Số 42 Bạch Đằng"
    assert updated["version"] == 2

    # Update with stale version returns 409 ERR_ADDRESS_CHANGED
    stale_res = api.put(
        f"{URL}/{addr_id}",
        json={**update_payload, "version": 1},
        headers=headers(engine),
    )
    assert stale_res.status_code == 409
    assert stale_res.json()["error"]["code"] == "ERR_ADDRESS_CHANGED"

    # Delete: DELETE /api/v1/addresses/{id}
    res_del = api.delete(f"{URL}/{addr_id}", headers=headers(engine))
    assert res_del.status_code == 204
    assert res_del.content == b""

    # Verify deletion in DB and via API
    assert api.get(URL, headers=headers(engine)).json()["data"] == []
    with Session(engine) as session:
        assert session.get(UserAddress, addr_id) is None

    # Subsequent actions on deleted ID return 404
    assert api.delete(f"{URL}/{addr_id}", headers=headers(engine)).status_code == 404
    assert (
        api.put(
            f"{URL}/{addr_id}",
            json={**update_payload, "version": 2},
            headers=headers(engine),
        ).status_code
        == 404
    )
    assert (
        api.patch(
            f"{URL}/{addr_id}/default", json={"version": 2}, headers=headers(engine)
        ).status_code
        == 404
    )


def test_default_address_lifecycle_switching_and_clearing_without_silent_promotion(api, engine):
    """Addresses handle default assignment, switching, and clearing without silent promotions."""
    # 1. First address automatically becomes default
    addr1 = create(api, engine, is_default=False)
    assert addr1["is_default"] is True
    assert addr1["version"] == 1

    # 2. Second address with is_default=False stays non-default
    addr2 = create(api, engine, is_default=False)
    assert addr2["is_default"] is False

    # 3. Third address with is_default=True becomes default and clears addr1
    addr3 = create(api, engine, is_default=True)
    assert addr3["is_default"] is True

    # Check listing order: default (addr3) first, then addr1, addr2 ascending
    res_list = api.get(URL, headers=headers(engine)).json()["data"]
    assert [a["id"] for a in res_list] == [addr3["id"], addr1["id"], addr2["id"]]
    assert res_list[0]["is_default"] is True
    assert res_list[1]["is_default"] is False
    assert res_list[2]["is_default"] is False

    # addr1 version should have incremented when its default was cleared
    with Session(engine) as session:
        assert session.get(UserAddress, addr1["id"]).version == 2
        addr2_current = session.get(UserAddress, addr2["id"])

    # 4. Switch default to addr2 via PATCH /api/v1/addresses/{id}/default
    res_patch = api.patch(
        f"{URL}/{addr2['id']}/default",
        json={"version": addr2_current.version},
        headers=headers(engine),
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["data"]["is_default"] is True

    # Verify addr2 is now default first in list, and addr3 is cleared
    res_list2 = api.get(URL, headers=headers(engine)).json()["data"]
    assert res_list2[0]["id"] == addr2["id"]
    assert sum(a["is_default"] for a in res_list2) == 1

    # 5. Clear default on addr2 via PUT with is_default=False
    addr2_v2 = res_patch.json()["data"]["version"]
    res_put = api.put(
        f"{URL}/{addr2['id']}",
        json={**ADDRESS, "version": addr2_v2, "is_default": False},
        headers=headers(engine),
    )
    assert res_put.status_code == 200
    assert res_put.json()["data"]["is_default"] is False

    # All addresses are now non-default; no silent promotion happens
    res_list3 = api.get(URL, headers=headers(engine)).json()["data"]
    assert not any(a["is_default"] for a in res_list3)
    # Order defaults to ascending by ID when no default exists
    assert [a["id"] for a in res_list3] == sorted([addr1["id"], addr2["id"], addr3["id"]])

    # 6. Deleting an address when one is default leaves no default
    api.patch(
        f"{URL}/{addr1['id']}/default",
        json={"version": 2},
        headers=headers(engine),
    )
    assert api.get(URL, headers=headers(engine)).json()["data"][0]["id"] == addr1["id"]

    api.delete(f"{URL}/{addr1['id']}", headers=headers(engine))
    res_list4 = api.get(URL, headers=headers(engine)).json()["data"]
    assert len(res_list4) == 2
    assert not any(a["is_default"] for a in res_list4)


@pytest.mark.parametrize(
    "invalid_phone",
    [
        "12345",  # 5 digits (< 7)
        "123456",  # 6 digits (< 7)
        "+84 (12) 34",  # 6 digits with separators (< 7)
        "1234567890123456",  # 16 digits (> 15)
        "+84 (912345678901234)",  # 16 digits (> 15)
        "0912abc3456",  # letters
        "0912#34567",  # disallowed symbol '#'
        "0912*34567",  # disallowed symbol '*'
        "0912.345.678",  # dot is not allowed separator
        "+ ()-",  # separators only without digits
        "   ",  # whitespace only
        "+84 (091) 234-567-8901",  # 23 chars (> 20 max length)
    ],
)
def test_address_phone_validation_invalid_formats(api, engine, invalid_phone):
    """Invalid phone numbers fail validation with actionable field errors."""
    response = api.post(
        URL, json={**ADDRESS, "phone_number": invalid_phone}, headers=headers(engine)
    )
    assert response.status_code == 422
    assert "phone_number" in response.json()["error"]["fields"]
    msg = response.json()["error"]["fields"]["phone_number"][0]
    assert "7 to 15 digits" in msg


@pytest.mark.parametrize(
    "valid_phone",
    [
        "1234567",  # exactly 7 digits
        "123456789012345",  # exactly 15 digits
        "+84 912 345 678",  # spaces and plus
        "+84 (912) 345-678",  # mixed valid separators
        "(024) 3765-4321",  # parentheses and hyphen
        "0912-345-678",  # hyphens
    ],
)
def test_address_phone_validation_valid_formats(api, engine, valid_phone):
    """Valid phone numbers (7 to 15 digits) succeed and preserve separators."""
    addr = create(api, engine, phone_number=valid_phone)
    assert addr["phone_number"] == valid_phone.strip()


def test_address_phone_normalizes_outer_and_repeated_spaces_without_changing_digits(api, engine):
    addr = create(api, engine, phone_number="  +84  912  345  678  ")

    assert addr["phone_number"] == "+84 912 345 678"


@pytest.mark.parametrize(
    "field_name",
    [
        "recipient_name",
        "phone_number",
        "province",
        "district",
        "ward",
        "detailed_address",
    ],
)
@pytest.mark.parametrize(
    "empty_val",
    [
        "",
        "   ",
        "\t\n  ",
        "\u200b",  # zero-width space
    ],
)
def test_address_missing_and_whitespace_fields_validation(api, engine, field_name, empty_val):
    """Empty or non-visible whitespace strings fail validation for every required field."""
    response = api.post(URL, json={**ADDRESS, field_name: empty_val}, headers=headers(engine))
    assert response.status_code == 422
    assert field_name in response.json()["error"]["fields"]


def test_address_field_length_limits(api, engine):
    """Field character length upper boundaries are enforced strictly."""
    # recipient_name: max 100
    valid_name = api.post(
        URL, json={**ADDRESS, "recipient_name": "N" * 100}, headers=headers(engine)
    )
    assert valid_name.status_code == 201

    invalid_name = api.post(
        URL, json={**ADDRESS, "recipient_name": "N" * 101}, headers=headers(engine)
    )
    assert invalid_name.status_code == 422

    # province, district, ward: max 100
    assert (
        api.post(
            URL, json={**ADDRESS, "province": "P" * 101}, headers=headers(engine)
        ).status_code
        == 422
    )
    assert (
        api.post(
            URL, json={**ADDRESS, "district": "D" * 101}, headers=headers(engine)
        ).status_code
        == 422
    )
    assert (
        api.post(
            URL, json={**ADDRESS, "ward": "W" * 101}, headers=headers(engine)
        ).status_code
        == 422
    )

    # detailed_address: max 500
    valid_addr = api.post(
        URL, json={**ADDRESS, "detailed_address": "A" * 500}, headers=headers(engine)
    )
    assert valid_addr.status_code == 201

    invalid_addr = api.post(
        URL, json={**ADDRESS, "detailed_address": "A" * 501}, headers=headers(engine)
    )
    assert invalid_addr.status_code == 422


def test_cross_user_access_attempts_and_role_authorization(api, engine):
    """Unauthenticated users, sellers, and other buyers cannot access or mutate addresses."""
    # 1. Unauthenticated guest attempts
    assert api.get(URL).status_code == 401
    assert api.post(URL, json=ADDRESS).status_code == 401
    assert api.put(f"{URL}/1", json={**ADDRESS, "version": 1}).status_code == 401
    assert api.patch(f"{URL}/1/default", json={"version": 1}).status_code == 401
    assert api.delete(f"{URL}/1").status_code == 401

    # 2. Seller account attempts (user 1 is seller in cart_db)
    seller_hdr = headers(engine, buyer=1)
    assert api.get(URL, headers=seller_hdr).status_code == 403
    assert api.post(URL, json=ADDRESS, headers=seller_hdr).status_code == 403
    assert (
        api.put(f"{URL}/1", json={**ADDRESS, "version": 1}, headers=seller_hdr).status_code == 403
    )
    assert (
        api.patch(f"{URL}/1/default", json={"version": 1}, headers=seller_hdr).status_code == 403
    )
    assert api.delete(f"{URL}/1", headers=seller_hdr).status_code == 403

    # 3. Cross-buyer isolation (Buyer 2 vs Buyer 3)
    b2_addr = create(api, engine, buyer=2, recipient_name="Buyer Two Address")
    b3_addr = create(api, engine, buyer=3, recipient_name="Buyer Three Address")

    # Buyer 2 only sees their address
    b2_list = api.get(URL, headers=headers(engine, buyer=2)).json()["data"]
    assert len(b2_list) == 1
    assert b2_list[0]["id"] == b2_addr["id"]

    # Buyer 3 only sees their address
    b3_list = api.get(URL, headers=headers(engine, buyer=3)).json()["data"]
    assert len(b3_list) == 1
    assert b3_list[0]["id"] == b3_addr["id"]

    # Buyer 2 attempting to PUT Buyer 3's address -> 404 ERR_ADDRESS_NOT_FOUND
    res_cross_put = api.put(
        f"{URL}/{b3_addr['id']}",
        json={**ADDRESS, "version": b3_addr["version"], "recipient_name": "Hacked Name"},
        headers=headers(engine, buyer=2),
    )
    assert res_cross_put.status_code == 404
    assert res_cross_put.json()["error"]["code"] == "ERR_ADDRESS_NOT_FOUND"

    # Buyer 2 attempting to PATCH default on Buyer 3's address -> 404
    res_cross_patch = api.patch(
        f"{URL}/{b3_addr['id']}/default",
        json={"version": b3_addr["version"]},
        headers=headers(engine, buyer=2),
    )
    assert res_cross_patch.status_code == 404
    assert res_cross_patch.json()["error"]["code"] == "ERR_ADDRESS_NOT_FOUND"

    # Buyer 2 attempting to DELETE Buyer 3's address -> 404
    res_cross_del = api.delete(f"{URL}/{b3_addr['id']}", headers=headers(engine, buyer=2))
    assert res_cross_del.status_code == 404
    assert res_cross_del.json()["error"]["code"] == "ERR_ADDRESS_NOT_FOUND"

    # Verify Buyer 3's address was untouched in DB
    with Session(engine) as session:
        b3_check = session.get(UserAddress, b3_addr["id"])
        assert b3_check is not None
        assert b3_check.recipient_name == "Buyer Three Address"
        assert b3_check.is_default is True
        assert b3_check.version == 1


def test_address_body_forbids_client_spoofed_user_id_or_server_fields(api, engine):
    """Payloads attempting to pass user_id, id, version, or created_at are rejected with 422."""
    for forbidden_field in [
        {"user_id": 999},
        {"id": 42},
        {"version": 1},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"updated_at": "2026-01-01T00:00:00Z"},
        {"extra_field": "disallowed"},
    ]:
        res = api.post(URL, json={**ADDRESS, **forbidden_field}, headers=headers(engine))
        assert res.status_code == 422
        assert "_form" in res.json()["error"]["fields"]

