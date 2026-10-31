"""Server-side admin authorization, route registry and audit attribution (#153, parent #113).

Every test sends direct HTTP requests with signed tokens, so a hidden UI button is never
treated as access control. The expected results come from the #113/#151 contracts in
docs/us21-admin-workflow.md, not from observed output. Databases are isolated SQLite files.
"""

import importlib
import pkgutil
import re
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from sqlmodel import Session, select

import src.api
from src.api import seller_products
from src.auth import AdminUser, create_access_token, require_admin
from src.main import create_app
from src.models.account_audit_log import AccountAuditLog
from src.models.category import Category
from src.models.category_audit_log import CategoryAuditLog
from src.models.order import Order
from src.models.product import Product
from src.models.product_metadata import ProductMetadata
from src.models.return_request import ReturnRequest
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.models.voucher import Voucher
from tests.cart_db import BUYER_ID, OTHER_BUYER_ID, SELLER_ID
from tests.test_admin_workflow import (
    ADMIN_ID,
    backend,  # noqa: F401  (pytest fixture shared with the #151 suite)
    open_dispute,
    persisted_state,
    submit_buyer_return,
)

TRACEABILITY = Path(__file__).resolve().parents[1] / "docs" / "traceability.md"
API = "/api/v1"
MISSING_ID = 99999

OTHER_SELLER_ID = 5
SECOND_ADMIN_ID = 6
RESTRICTED_ADMIN_ID = 7
SUSPENDED_ADMIN_ID = 8

ADMIN_ACTOR = "admin"
DENIED_ACTORS = {
    "guest": (401, "ERR_AUTH_REQUIRED"),
    "buyer": (403, "ERR_ADMIN_REQUIRED"),
    "other_buyer": (403, "ERR_ADMIN_REQUIRED"),
    "seller": (403, "ERR_ADMIN_REQUIRED"),
    "other_seller": (403, "ERR_ADMIN_REQUIRED"),
    "restricted_admin": (403, "ERR_ACCOUNT_RESTRICTED"),
    "suspended_admin": (403, "ERR_ACCOUNT_RESTRICTED"),
}


@pytest.fixture
def world(backend):  # noqa: F811
    """The #151 database plus every account state and resource the matrix needs."""
    client, engine, ids, tokens = backend
    with Session(engine) as session:
        session.add_all(
            [
                User(id=OTHER_SELLER_ID, name="Other seller", email="s2@test.local", role="seller"),
                User(id=SECOND_ADMIN_ID, name="Admin two", email="a2@test.local", role="admin"),
                User(id=RESTRICTED_ADMIN_ID, name="Rest", email="ra@test.local", role="admin"),
                User(id=SUSPENDED_ADMIN_ID, name="Susp", email="sa@test.local", role="admin"),
            ]
        )
        session.flush()
        # Tokens are issued while every account is still ACTIVE: the guard must read the
        # current database status, not what the token claimed at login.
        issued = {
            "guest": {},
            "buyer": tokens[BUYER_ID],
            "other_buyer": _bearer(session.get(User, OTHER_BUYER_ID)),
            "seller": tokens[SELLER_ID],
            "other_seller": _bearer(session.get(User, OTHER_SELLER_ID)),
            ADMIN_ACTOR: tokens[ADMIN_ID],
            "second_admin": _bearer(session.get(User, SECOND_ADMIN_ID)),
            "restricted_admin": _bearer(session.get(User, RESTRICTED_ADMIN_ID)),
            "suspended_admin": _bearer(session.get(User, SUSPENDED_ADMIN_ID)),
        }
        session.get(User, RESTRICTED_ADMIN_ID).status = "RESTRICTED"
        session.get(User, SUSPENDED_ADMIN_ID).status = "SUSPENDED"
        category = Category(name="Fixture", slug="fixture")
        session.add(category)
        other_order = Order(
            buyer_id=OTHER_BUYER_ID,
            total_amount=50000,
            status="DELIVERED",
            recipient_name="Other",
            delivery_address="Other street",
            phone_number="0912345679",
        )
        session.add(other_order)
        session.flush()
        other_shop = SellerOrder(
            order_id=other_order.id,
            seller_id=OTHER_SELLER_ID,
            status="DELIVERED",
            subtotal=50000,
            total_amount=50000,
        )
        session.add(other_shop)
        session.add_all(
            [
                Voucher(
                    code="PLAT10",
                    scope="PLATFORM",
                    discount_type="PERCENTAGE",
                    discount_value=1000,
                    starts_at=_utc(2030, 1, 1),
                    ends_at=_utc(2031, 1, 1),
                ),
                Voucher(
                    code="SHOPA10",
                    scope="SHOP",
                    seller_id=SELLER_ID,
                    discount_type="PERCENTAGE",
                    discount_value=1000,
                    starts_at=_utc(2030, 1, 1),
                    ends_at=_utc(2031, 1, 1),
                ),
            ]
        )
        session.commit()
        ids = {
            **ids,
            "category": category.id,
            "other_order": other_order.id,
            "other_shop": other_shop.id,
            "platform_voucher": session.exec(select(Voucher).where(Voucher.code == "PLAT10"))
            .one()
            .id,
            "shop_voucher": session.exec(select(Voucher).where(Voucher.code == "SHOPA10")).one().id,
        }
    return client, engine, ids, issued, backend


@pytest.fixture
def secured(world):
    """`world` with one pending dispute, so the decision route has a real target."""
    created = open_dispute(world[4])
    assert created.status_code == 201, created.text
    world[2]["dispute"] = created.json()["id"]
    return world


def _utc(year, month, day):
    from datetime import UTC, datetime

    return datetime(year, month, day, tzinfo=UTC)


def _bearer(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def state(secured):
    """Persisted rows plus vouchers, which the #151 snapshot does not include."""
    _, engine, _, _, base = secured
    with Session(engine) as session:
        vouchers = [row.model_dump() for row in session.exec(select(Voucher).order_by(Voucher.id))]
    return {**persisted_state(base), "vouchers": vouchers}


# --- Route registry ---------------------------------------------------------------------
# Each entry is a valid request: if the guard were dropped, the request would succeed and
# change state. `success` is the status an active administrator must receive.
# fmt: off
ADMIN_ROUTES = [
    # (method, path template, request(ids) -> kwargs, success status)
    ("GET", "/admin/category-audits", lambda i: {}, 200),
    ("GET", "/admin/categories", lambda i: {}, 200),
    ("POST", "/admin/categories", lambda i: {"json": {"name": "New", "slug": "new"}}, 201),
    ("PUT", "/admin/categories/{category_id}", lambda i: {"json": {"name": "Renamed"}}, 200),
    ("DELETE", "/admin/categories/{category_id}", lambda i: {}, 204),
    ("GET", "/admin/users", lambda i: {}, 200),
    ("GET", "/admin/users/{user_id}", lambda i: {}, 200),
    ("PATCH", "/admin/users/{user_id}/status",
     lambda i: {"json": {"status": "SUSPENDED", "reason": "Fraud"}}, 200),
    ("GET", "/admin/vouchers", lambda i: {}, 200),
    ("POST", "/admin/vouchers",
     lambda i: {"json": {"code": "NEWPLAT", "discount_type": "FREE_SHIPPING",
                         "starts_at": "2030-01-01T00:00:00Z", "ends_at": "2031-01-01T00:00:00Z"}},
     201),
    ("PATCH", "/admin/vouchers/{voucher_id}", lambda i: {"json": {"is_active": False}}, 200),
    ("GET", "/admin/products", lambda i: {}, 200),
    ("PATCH", "/admin/products/{product_id}/status",
     lambda i: {"json": {"is_active": False, "moderation_notes": "Policy"}}, 200),
    ("GET", "/admin/disputes", lambda i: {}, 200),
    ("POST", "/admin/disputes", lambda i: {"params": {
        "order_id": i["other_order"], "seller_order_id": i["other_shop"],
        "reason": "Late", "evidence": "photo.jpg"}}, 201),
    ("POST", "/admin/disputes/{dispute_id}/decision",
     lambda i: {"json": {"action": "REJECT", "decision_notes": "Evidence reviewed"}}, 200),
    ("GET", "/categories/admin", lambda i: {}, 200),
    ("POST", "/categories", lambda i: {"json": {"name": "Canon", "slug": "canon"}}, 201),
    ("PATCH", "/categories/{category_id}", lambda i: {"json": {"name": "Canon2"}}, 200),
    ("DELETE", "/categories/{category_id}", lambda i: {}, 200),
]
# fmt: on
PATH_IDS = {
    "category_id": "category",
    "user_id": "other_buyer",
    "voucher_id": "platform_voucher",
    "product_id": "product",
    "dispute_id": "dispute",
}


def _path(template, ids):
    values = {**ids, "other_buyer": OTHER_BUYER_ID}
    return API + template.format(**{key: values[ref] for key, ref in PATH_IDS.items()})


def _call(secured, actor, method, template, build):
    client, _, ids, tokens, _ = secured
    return client.request(
        method, _path(template, ids), headers=tokens.get(actor, {}), **build(ids)
    )


def _api_routers():
    """Every APIRouter instance defined in `src.api`, not only the one named `router`.

    The application mounts them lazily, so they are read from the modules; secondary
    routers such as `seller_products.inventory_router` are included. `api_router` is the
    mount point that aggregates the others, so it is skipped to avoid double counting.
    """
    seen = set()
    for module_info in pkgutil.iter_modules(src.api.__path__):
        module = importlib.import_module(f"src.api.{module_info.name}")
        for name, value in vars(module).items():
            if isinstance(value, APIRouter) and name != "api_router" and id(value) not in seen:
                seen.add(id(value))
                yield value


def _discovered_admin_routes():
    """(method, path under /api/v1, guarded) for every admin-looking or admin-guarded route."""
    routes = set()
    for router in _api_routers():
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            guarded = any(dep.call is require_admin for dep in _walk(route.dependant))
            if route.path.startswith("/admin") or guarded:
                routes.update((m, route.path, guarded) for m in route.methods - {"HEAD"})
    return routes


def _unregistered_routes():
    discovered = {(method, path) for method, path, _ in _discovered_admin_routes()}
    return discovered - {(method, template) for method, template, _, _ in ADMIN_ROUTES}


def _walk(dependant):
    for dep in dependant.dependencies:
        yield dep
        yield from _walk(dep)


def test_every_admin_route_requires_the_admin_guard():
    discovered = _discovered_admin_routes()

    unguarded = sorted((m, p) for m, p, guarded in discovered if not guarded)

    assert unguarded == []


def test_registry_lists_exactly_the_implemented_admin_routes():
    discovered = {(method, path) for method, path, _ in _discovered_admin_routes()}
    registered = {(method, template) for method, template, _, _ in ADMIN_ROUTES}

    assert _unregistered_routes() == set(), "new admin route has no security test"
    assert registered - discovered == set(), "registry lists a route that does not exist"


def test_discovered_routes_are_served_by_the_application():
    served = create_app().openapi()["paths"]

    missing = sorted(path for _, path, _ in _discovered_admin_routes() if API + path not in served)

    assert missing == []


def test_unregistered_admin_route_on_a_secondary_router_fails_verification(monkeypatch):
    probe = APIRouter(prefix="/seller/inventory")

    @probe.get("/probe-admin")
    def probe_admin(_admin: AdminUser):
        return {}

    monkeypatch.setattr(seller_products, "probe_router", probe, raising=False)

    assert ("GET", "/seller/inventory/probe-admin") in _unregistered_routes()


def test_traceability_documents_every_registered_admin_route():
    text = TRACEABILITY.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `(GET|POST|PUT|PATCH|DELETE) (/api/v1/[^`]+)`", text, re.MULTILINE)

    documented = {
        (method, path.removeprefix(API))
        for method, path in rows
        if path.removeprefix(API).startswith(("/admin", "/categories"))
    }
    registered = {(method, template) for method, template, _, _ in ADMIN_ROUTES}

    assert registered - documented == set()
    assert documented - registered == set(), "traceability row for a route that does not exist"


# --- Authorization matrix ---------------------------------------------------------------
ROUTE_IDS = [f"{method} {template}" for method, template, _, _ in ADMIN_ROUTES]


@pytest.mark.parametrize("actor", DENIED_ACTORS)
@pytest.mark.parametrize(("method", "template", "build", "_ok"), ADMIN_ROUTES, ids=ROUTE_IDS)
def test_direct_requests_without_an_active_admin_are_denied_without_writes(
    secured, actor, method, template, build, _ok
):
    before = state(secured)

    response = _call(secured, actor, method, template, build)

    expected_status, expected_code = DENIED_ACTORS[actor]
    assert response.status_code == expected_status, response.text
    assert response.json()["error"]["code"] == expected_code
    assert state(secured) == before


@pytest.mark.parametrize(("method", "template", "build", "success"), ADMIN_ROUTES, ids=ROUTE_IDS)
def test_active_admin_reaches_every_admin_route(secured, method, template, build, success):
    response = _call(secured, ADMIN_ACTOR, method, template, build)

    assert response.status_code == success, response.text


def test_forged_admin_role_claim_is_rejected_when_the_database_disagrees(secured):
    client, _, _, _, _ = secured
    forged = User(id=BUYER_ID, name="Buyer", email="buyer@test.local", role="admin")
    before = state(secured)

    response = client.post(
        f"{API}/admin/categories",
        headers=_bearer(forged),
        json={"name": "Forged", "slug": "forged"},
    )

    assert response.status_code == 401
    assert state(secured) == before


def test_token_issued_before_restriction_stops_working_immediately(secured):
    client, engine, _, tokens, _ = secured
    path = f"{API}/admin/users/{SECOND_ADMIN_ID}/status"
    assert client.get(f"{API}/admin/users", headers=tokens["second_admin"]).status_code == 200

    restricted = client.patch(
        path, headers=tokens[ADMIN_ACTOR], json={"status": "RESTRICTED", "reason": "Review"}
    )
    before = state(secured)
    blocked = client.post(
        f"{API}/admin/categories",
        headers=tokens["second_admin"],
        json={"name": "Late", "slug": "late"},
    )

    assert restricted.status_code == 200, restricted.text
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ERR_ACCOUNT_RESTRICTED"
    assert state(secured) == before
    with Session(engine) as session:
        assert session.exec(select(Category).where(Category.slug == "late")).first() is None


# --- Not found and malformed input (authorized admin) -----------------------------------
NOT_FOUND = [
    ("PUT", "/admin/categories/99999", {"json": {"name": "X"}}),
    ("DELETE", "/admin/categories/99999", {}),
    ("GET", "/admin/users/99999", {}),
    ("PATCH", "/admin/users/99999/status", {"json": {"status": "ACTIVE", "reason": "x"}}),
    ("PATCH", "/admin/vouchers/99999", {"json": {"is_active": False}}),
    ("PATCH", "/admin/products/99999/status", {"json": {"is_active": False}}),
    ("POST", "/admin/disputes/99999/decision", {"json": {"action": "REJECT"}}),
    ("PATCH", "/categories/99999", {"json": {"name": "X"}}),
    ("DELETE", "/categories/99999", {}),
]
MALFORMED = [
    ("POST", "/admin/categories", {"json": {"slug": "no-name"}}),
    ("POST", "/admin/categories", {"json": {"name": "A", "slug": "a", "admin_id": 1}}),
    ("POST", "/categories", {"json": {"name": "A", "slug": "a", "admin_id": 1}}),
    ("PATCH", "/admin/users/2/status", {"json": {"status": "BANNED", "reason": "x"}}),
    ("PATCH", "/admin/users/2/status", {"json": {"status": "SUSPENDED", "reason": "x" * 501}}),
    ("POST", "/admin/vouchers", {"json": {"code": "AB", "discount_type": "PERCENTAGE"}}),
    ("POST", "/admin/vouchers", {"json": {"code": "OKCODE", "discount_type": "MAGIC",
                                          "starts_at": "2030-01-01T00:00:00Z",
                                          "ends_at": "2031-01-01T00:00:00Z"}}),
    ("PATCH", "/admin/products/1/status", {"json": {"moderation_notes": "missing flag"}}),
    ("POST", "/admin/disputes/1/decision", {"json": {"action": "MAYBE"}}),
    ("POST", "/admin/disputes/1/decision",
     {"json": {"action": "APPROVE", "decided_by_user_id": 1}}),
    ("GET", "/admin/category-audits?limit=0", {}),
    ("GET", "/admin/category-audits?limit=101", {}),
    ("POST", "/admin/disputes", {"params": {"order_id": 1}}),
]


@pytest.mark.parametrize(("method", "path", "kwargs"), NOT_FOUND)
def test_admin_reports_missing_resources_without_writing(secured, method, path, kwargs):
    client, _, _, tokens, _ = secured
    before = state(secured)

    response = client.request(method, API + path, headers=tokens[ADMIN_ACTOR], **kwargs)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"].endswith("_NOT_FOUND")
    assert state(secured) == before


@pytest.mark.parametrize(("method", "path", "kwargs"), MALFORMED)
def test_admin_rejects_malformed_input_without_writing(secured, method, path, kwargs):
    client, _, _, tokens, _ = secured
    before = state(secured)

    response = client.request(method, API + path, headers=tokens[ADMIN_ACTOR], **kwargs)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "ERR_VALIDATION"
    assert state(secured) == before


# --- Identity, ownership and scope cannot be chosen by the client ------------------------
def test_audit_actor_is_the_authenticated_admin_even_if_the_query_names_another(secured):
    client, engine, _, tokens, _ = secured

    created = client.post(
        f"{API}/admin/categories",
        headers=tokens["second_admin"],
        params={"admin_id": ADMIN_ID, "actor_id": ADMIN_ID},
        json={"name": "Spoof", "slug": "spoof"},
    )
    status_change = client.patch(
        f"{API}/admin/users/{OTHER_BUYER_ID}/status",
        headers=tokens["second_admin"],
        params={"admin_id": ADMIN_ID},
        json={"status": "RESTRICTED", "reason": "Chargebacks"},
    )

    assert created.status_code == 201, created.text
    assert status_change.status_code == 200, status_change.text
    with Session(engine) as session:
        category_audit = session.exec(
            select(CategoryAuditLog).where(CategoryAuditLog.category_id == created.json()["id"])
        ).one()
        account_audit = session.exec(select(AccountAuditLog)).one()
    assert category_audit.admin_id == SECOND_ADMIN_ID
    assert (account_audit.admin_id, account_audit.user_id) == (SECOND_ADMIN_ID, OTHER_BUYER_ID)
    assert (account_audit.old_status, account_audit.new_status) == ("ACTIVE", "RESTRICTED")
    assert account_audit.reason == "Chargebacks"
    assert account_audit.created_at is not None


def test_platform_voucher_scope_and_owner_cannot_be_set_by_the_request(secured):
    client, engine, _, tokens, _ = secured

    response = client.post(
        f"{API}/admin/vouchers",
        headers=tokens[ADMIN_ACTOR],
        json={
            "code": "SCOPED",
            "scope": "SHOP",
            "seller_id": SELLER_ID,
            "discount_type": "FREE_SHIPPING",
            "starts_at": "2030-01-01T00:00:00Z",
            "ends_at": "2031-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 201, response.text
    with Session(engine) as session:
        voucher = session.exec(select(Voucher).where(Voucher.code == "SCOPED")).one()
        assert (voucher.scope, voucher.seller_id) == ("PLATFORM", None)


def test_product_moderation_cannot_reassign_the_owning_seller(secured):
    client, engine, ids, tokens, _ = secured

    response = client.patch(
        f"{API}/admin/products/{ids['product']}/status",
        headers=tokens[ADMIN_ACTOR],
        json={"is_active": False, "seller_id": OTHER_SELLER_ID},
    )

    assert response.status_code == 200, response.text
    with Session(engine) as session:
        product = session.get(Product, ids["product"])
        assert (product.seller_id, product.is_active) == (SELLER_ID, False)
        meta = session.exec(
            select(ProductMetadata).where(ProductMetadata.product_id == ids["product"])
        ).one()
        assert meta.is_moderated_deactivated is True


SELLER_VOUCHER = {
    "code": "MYSHOP",
    "discount_type": "PERCENTAGE",
    "discount_value": 500,
    "starts_at": "2030-01-01T00:00:00Z",
    "ends_at": "2031-01-01T00:00:00Z",
}


def test_seller_voucher_is_always_shop_scoped_to_the_caller(secured):
    client, engine, _, tokens, _ = secured

    response = client.post(
        f"{API}/seller/vouchers",
        headers=tokens["other_seller"],
        json={**SELLER_VOUCHER, "scope": "PLATFORM", "seller_id": SELLER_ID},
    )

    assert response.status_code == 201, response.text
    with Session(engine) as session:
        stored = session.exec(select(Voucher).where(Voucher.code == "MYSHOP")).one()
        assert (stored.scope, stored.seller_id) == ("SHOP", OTHER_SELLER_ID)


@pytest.mark.parametrize(
    ("actor", "target"),
    [
        ("other_seller", "shop_voucher"),  # another seller's shop voucher
        ("seller", "platform_voucher"),  # a shop seller cannot edit the platform voucher
    ],
)
def test_seller_cannot_modify_vouchers_it_does_not_own(secured, actor, target):
    client, _, ids, tokens, _ = secured
    before = state(secured)

    response = client.patch(
        f"{API}/seller/vouchers/{ids[target]}", headers=tokens[actor], json={"is_active": False}
    )

    assert response.status_code == 404, response.text
    assert state(secured) == before


def test_admin_voucher_route_cannot_touch_a_shop_voucher(secured):
    client, _, ids, tokens, _ = secured
    before = state(secured)

    response = client.patch(
        f"{API}/admin/vouchers/{ids['shop_voucher']}",
        headers=tokens[ADMIN_ACTOR],
        json={"is_active": False},
    )

    assert response.status_code == 404, response.text
    assert state(secured) == before


# --- Audit history ----------------------------------------------------------------------
def test_failed_category_mutations_leave_no_audit_record(secured):
    client, engine, ids, tokens, _ = secured
    with Session(engine) as session:
        audits_before = len(session.exec(select(CategoryAuditLog)).all())
    attempts = [
        ("POST", "/admin/categories", {"name": "Dup", "slug": "fixture"}, 409),
        (
            "POST",
            "/admin/categories",
            {"name": "Orphan", "slug": "orphan", "parent_id": MISSING_ID},
            400,
        ),
        ("PUT", f"/admin/categories/{ids['category']}", {"parent_id": ids["category"]}, 400),
    ]

    for method, path, body, expected in attempts:
        response = client.request(method, API + path, headers=tokens[ADMIN_ACTOR], json=body)
        assert response.status_code == expected, response.text

    with Session(engine) as session:
        assert len(session.exec(select(CategoryAuditLog)).all()) == audits_before


def test_audit_history_names_each_admin_in_order_and_hides_nothing_from_admins(secured):
    client, _, ids, tokens, _ = secured
    client.put(
        f"{API}/admin/categories/{ids['category']}",
        headers=tokens["second_admin"],
        json={"name": "Renamed"},
    )
    client.delete(f"{API}/admin/categories/{ids['category']}", headers=tokens[ADMIN_ACTOR])

    history = client.get(f"{API}/admin/category-audits", headers=tokens[ADMIN_ACTOR]).json()

    mine = [row for row in history if row["category_id"] == ids["category"]]
    assert [(row["action"], row["admin_id"]) for row in mine] == [
        ("DELETE", ADMIN_ID),
        ("UPDATE", SECOND_ADMIN_ID),
    ]
    assert mine[1]["before"]["name"] == "Fixture"
    assert mine[1]["after"]["name"] == "Renamed"
    assert mine[0]["after"] is None


# --- Admin and seller return decisions share one settlement rule (#140) -----------------
@pytest.mark.parametrize("decider", ["seller", "admin"])
def test_approved_restockable_return_has_the_same_effect_for_seller_and_admin(world, decider):
    client, engine, ids, tokens, base = world
    request_id = submit_buyer_return(base)
    approve = {"action": "APPROVE", "decision_notes": "OK", "is_restockable": True}
    if decider == "seller":
        response = client.post(
            f"{API}/return-requests/{request_id}/decision", headers=tokens["seller"], json=approve
        )
    else:
        dispute_id = open_dispute(base).json()["id"]
        response = client.post(
            f"{API}/admin/disputes/{dispute_id}/decision", headers=tokens[ADMIN_ACTOR], json=approve
        )

    assert response.status_code == 200, response.text
    with Session(engine) as session:
        shop = session.get(SellerOrder, ids["shop"])
        parent = session.get(Order, ids["order"])
        # The fixture holds 8 units; the buyer returned the 2 purchased and the shop restocked.
        assert session.get(Product, ids["product"]).stock_quantity == 10
        assert (shop.status, shop.payment_status, shop.escrow_status) == (
            "RETURNED_REFUNDED",
            "REFUNDED",
            "VOIDED",
        )
        assert shop.refunded_amount == 200000
        assert (parent.status, parent.escrow_status) == ("RETURNED_REFUNDED", "VOIDED")
        assert session.get(ReturnRequest, request_id).status == "APPROVED"


@pytest.mark.parametrize("actor", ["buyer", "other_buyer", "other_seller"])
def test_accounts_outside_the_order_cannot_decide_its_return(world, actor):
    client, engine, ids, tokens, base = world
    request_id = submit_buyer_return(base)
    before = state(world)

    response = client.post(
        f"{API}/return-requests/{request_id}/decision",
        headers=tokens[actor],
        json={"action": "APPROVE", "decision_notes": "x", "is_restockable": True},
    )

    assert response.status_code == 403, response.text
    assert state(world) == before
    with Session(engine) as session:
        assert session.get(ReturnRequest, request_id).status == "PENDING"
        assert session.get(SellerOrder, ids["shop"]).status == "RETURN_REQUESTED"
