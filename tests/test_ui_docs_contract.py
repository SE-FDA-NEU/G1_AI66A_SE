"""The UI and API documentation must match the running code (Milestone 3, #85).

docs/ui.md section 3.2 lists the error cases a user can meet and docs/design.md section
3.4 lists every API error code. These tests fail when a documented message, error code,
business rule, test name or route no longer exists, so the documents cannot drift
silently from the screens.
"""

import re
from pathlib import Path

import pytest
from sqlmodel import Session
from starlette.testclient import TestClient

from src.auth import create_access_token
from src.database import get_session
from src.main import create_app
from src.models.user import User
from tests.cart_db import BUYER_ID, create_cart_engine

ROOT = Path(__file__).resolve().parent.parent
UI_DOC = ROOT / "docs" / "ui.md"
DESIGN_DOC = ROOT / "docs" / "design.md"
TRACEABILITY_DOC = ROOT / "docs" / "traceability.md"
ERROR_CODE = re.compile(r"\bERR_[A-Z_]+\b")
PLACEHOLDER = re.compile(r"\{[^}]*\}")


def section(path: Path, heading: str) -> str:
    """The text of one Markdown section, up to the next heading of the same level."""
    text = path.read_text(encoding="utf-8")
    level = heading.split(" ")[0]
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1 :]
    following = re.search(rf"^{level} ", rest, flags=re.MULTILINE)
    return rest[: following.start()] if following else rest


def table_rows(text: str, first_cell: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith(f"| {first_cell}"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def source_text() -> str:
    patterns = ("src/**/*.py", "src/web/**/*.js", "src/web/**/*.html")
    files = [path for pattern in patterns for path in ROOT.glob(pattern)]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def source_error_codes() -> set[str]:
    codes = set()
    for path in ROOT.glob("src/**/*.py"):
        codes |= set(re.findall(r"[\"'](ERR_[A-Z_]+)[\"']", path.read_text(encoding="utf-8")))
    return codes


def existing_test_names() -> set[str]:
    names = set()
    for path in ROOT.glob("tests/*.py"):
        names |= set(re.findall(r"^def (test_\w+)\(", path.read_text(encoding="utf-8"), re.M))
    return names


ERROR_CASES = table_rows(
    section(UI_DOC, "### 3.2 Error cases: API code, business rule and UI message"), "UI-E"
)


def test_ui_documents_at_least_four_error_cases():
    assert len(ERROR_CASES) >= 4
    assert all(len(row) == 8 for row in ERROR_CASES), "every error case needs eight columns"


@pytest.mark.parametrize("row", ERROR_CASES, ids=[row[0] for row in ERROR_CASES])
def test_documented_error_case_matches_the_code(row):
    case, _screen, _trigger, http, rule, message, _recovery, check = row
    source = source_text()

    shown = re.fullmatch(r"`(.+)`", message)
    assert shown, f"{case}: the UI message must be quoted exactly in backticks"
    for fragment in PLACEHOLDER.split(shown.group(1)):
        if len(fragment.strip()) >= 4:
            assert fragment in source, f"{case}: {fragment!r} is not shown by any page or API"

    for code in ERROR_CODE.findall(http):
        assert code in source_error_codes(), f"{case}: {code} is not raised by the API"

    business_rules = {
        row[0] for row in table_rows(section(TRACEABILITY_DOC, "## Business rules"), "BR")
    }
    for rule_id in re.findall(r"BR\d+", rule):
        assert rule_id in business_rules, f"{case}: {rule_id} is not a documented rule"

    named = re.fullmatch(r"`(test_\w+)`", check)
    assert named, f"{case}: name one automated test"
    assert named.group(1) in existing_test_names(), f"{case}: {named.group(1)} does not exist"


def test_design_error_table_lists_exactly_the_codes_the_api_uses():
    table = [
        line
        for line in section(DESIGN_DOC, "### 3.4 Error handling").splitlines()
        if line.startswith("| ")
    ]
    documented = set(ERROR_CODE.findall("\n".join(table)))

    assert documented == source_error_codes(), (
        f"missing from design.md: {sorted(source_error_codes() - documented)}; "
        f"not in the code: {sorted(documented - source_error_codes())}"
    )


def test_every_screen_in_the_inventory_is_served(client):
    inventory = section(UI_DOC, "## 1. Screen inventory and navigation")
    documented = re.findall(r"^\| [^|]+ \| `(/[^`]*)` \|", inventory, flags=re.MULTILINE)

    assert len(documented) == 9
    for path in documented:
        url = re.sub(r"\{\w*Id\}", "1", re.sub(r"\{productCode\}", "P-100", path))
        response = client.get(url, headers={"Accept": "text/html"}, follow_redirects=False)
        assert response.status_code in (200, 307), f"{path} is not served"


@pytest.fixture
def api(tmp_path):
    """A client on a disposable database, with the bearer header of its buyer."""
    engine = create_cart_engine(tmp_path / "ui_contract.db")
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with Session(engine) as session:
        buyer = {"Authorization": f"Bearer {create_access_token(session.get(User, BUYER_ID))}"}
    with TestClient(app) as client:
        yield client, buyer
    engine.dispose()


def test_buyers_and_guests_cannot_use_seller_orders(api):
    """UI-E18: the seller order page shows this API message to a buyer."""
    client, buyer = api

    listing = client.get("/api/v1/seller/orders", headers=buyer)
    change = client.patch(
        "/api/v1/seller/orders/1/status", json={"status": "PROCESSING"}, headers=buyer
    )
    guest = client.get("/api/v1/seller/orders")

    for response in (listing, change):
        assert response.status_code == 403
        assert response.json() == {
            "error": {"code": "ERR_SELLER_REQUIRED", "message": "A seller account is required."}
        }
    assert guest.status_code == 401
    assert guest.json()["error"]["code"] == "ERR_AUTH_REQUIRED"


def test_pages_never_show_a_generic_error():
    """Milestone 3: a message says what happened and what to do next, never just "error"."""
    banned = ("Something went wrong", "Error 422", "Traceback", "Internal Server Error")
    for pattern in ("src/web/**/*.js", "src/web/**/*.html"):
        for path in ROOT.glob(pattern):
            text = path.read_text(encoding="utf-8")
            for phrase in banned:
                assert phrase not in text, f"{path.name} shows {phrase!r}"
