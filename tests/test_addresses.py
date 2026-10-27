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
