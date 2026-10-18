"""The UI and API documentation must match the running code (Milestone 3, #85).

docs/ui.md has the four sections Milestone 3 asks for, in order; its section 3 lists the
messages a user can meet, and docs/design.md section 3.4 lists every API error code. These
tests fail when a section is missing, a story status is not one of the allowed values, or
a documented message, error code, business rule, test name or route no longer exists, so
the documents cannot drift silently from the screens.
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
# A message may join a page sentence and a server sentence, so each part is checked alone.
MESSAGE_PARTS = re.compile(r"\{[^}]*\}|(?<=\.) ")
REQUIRED_SECTIONS = [
    "## 1. P0 stories and status",
    "## 2. Wireframes",
    "## 3. Error messages",
    "## 4. What changed since M2",
]
P0_STORIES = {"US01", "US02", "US03", "US04", "US06", "US08"}
STATUSES = ("works", "partly works", "not started")


def section(path: Path, heading: str) -> str:
    """The text of one Markdown section, up to the next heading of the same level."""
    text = path.read_text(encoding="utf-8")
    level = heading.split(" ")[0]
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1 :]
    following = re.search(rf"^{level} ", rest, flags=re.MULTILINE)
    return rest[: following.start()] if following else rest


def table_rows(text: str, first_cell: str = "") -> list[list[str]]:
    """Body rows of the Markdown tables in `text` whose first cell starts with `first_cell`."""
    rows = []
    for line in text.splitlines():
        if not line.startswith(f"| {first_cell}") or set(line) <= {"|", "-", " "}:
            continue
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


STORY_ROWS = table_rows(section(UI_DOC, "## 1. P0 stories and status"), "US0")
MESSAGE_ROWS = table_rows(section(UI_DOC, "## 3. Error messages"), "`")


def test_ui_has_the_four_required_sections_in_order():
    headings = re.findall(r"^## .+$", UI_DOC.read_text(encoding="utf-8"), flags=re.MULTILINE)

    assert headings == REQUIRED_SECTIONS


def test_every_p0_story_has_an_allowed_status():
    statuses = {row[0].split()[0]: row[3] for row in STORY_ROWS if len(row) == 5}

    assert P0_STORIES <= set(statuses)
    for story, status in statuses.items():
        assert status.startswith(STATUSES), f"{story}: {status!r} is not an allowed status"


def test_every_story_route_is_served(client):
    routes = [
        route
        for row in STORY_ROWS
        if len(row) == 5
        for route in re.findall(r"`(/[^`]*)`", row[2])
    ]

    assert len(routes) == 7
    for path in routes:
        url = re.sub(r"\{\w*Id\}", "1", path.replace("{productCode}", "P-100"))
        response = client.get(url, headers={"Accept": "text/html"}, follow_redirects=False)
        assert response.status_code == 200, f"{path} is not served"


def test_every_wireframe_says_why_the_user_comes_and_what_it_calls():
    wireframes = section(UI_DOC, "## 2. Wireframes")
    screens = re.split(r"^### ", wireframes, flags=re.MULTILINE)[1:]
    drawn = [screen for screen in screens if "```text" in screen]

    assert len(drawn) >= 8
    for screen in drawn:
        name = screen.splitlines()[0]
        assert re.search(r"\*The user[^*]* comes here to ", screen), f"{name}: missing purpose"
        assert "Calls: `" in screen, f"{name}: missing API endpoints"
    cart = next(screen for screen in drawn if screen.startswith("2.3 Cart"))
    for state in ("Empty", "Loading", "Error", "Data"):
        assert f"+- {state} " in cart, f"the cart wireframe is missing the {state} state"


def test_ui_lists_at_least_four_error_messages():
    assert len(MESSAGE_ROWS) >= 4
    assert all(len(row) == 5 for row in MESSAGE_ROWS), "every message row needs five columns"


@pytest.mark.parametrize("row", MESSAGE_ROWS, ids=[row[2][:40] for row in MESSAGE_ROWS])
def test_documented_message_matches_the_code(row):
    http, rule, message, _where, check = row
    source = source_text()

    shown = re.fullmatch(r"`(.+)`", message)
    assert shown, f"{message}: the message must be quoted exactly in backticks"
    for part in MESSAGE_PARTS.split(shown.group(1)):
        if len(part.strip()) >= 4:
            assert part in source, f"{part!r} is not shown by any page or API"

    codes = ERROR_CODE.findall(http)
    assert codes, f"{message}: name the API error code"
    for code in codes:
        assert code in source_error_codes(), f"{code} is not raised by the API"

    rules_table = section(TRACEABILITY_DOC, "## Business rules")
    business_rules = {row[0] for row in table_rows(rules_table, "BR")}
    for rule_id in re.findall(r"BR\d+", rule):
        assert rule_id in business_rules, f"{rule_id} is not a documented rule"

    named = re.fullmatch(r"`(test_\w+)`", check)
    assert named, f"{message}: name one automated test"
    assert named.group(1) in existing_test_names(), f"{named.group(1)} does not exist"


def test_changes_since_m2_are_recorded_in_design():
    changes = table_rows(section(UI_DOC, "## 4. What changed since M2"))[1:]
    design = DESIGN_DOC.read_text(encoding="utf-8")

    assert changes, "name at least one change"
    assert "API: receipt names products" in design
    assert "`product_name`" in section(DESIGN_DOC, "### 3.3 P0 endpoint contract")


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


def test_pages_never_show_a_generic_error():
    """Milestone 3: a message says what happened and what to do next, never just "error"."""
    banned = ("Something went wrong", "Error 422", "Traceback", "Internal Server Error")
    for pattern in ("src/web/**/*.js", "src/web/**/*.html"):
        for path in ROOT.glob(pattern):
            text = path.read_text(encoding="utf-8")
            for phrase in banned:
                assert phrase not in text, f"{path.name} shows {phrase!r}"


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
    """The seller order page turns this 403 into a message that says to log in as a seller."""
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


def test_readme_first_screen_lists_where_each_p0_story_starts():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first_screen = readme[: readme.index("## Team & Roles")]

    assert "## P0 stories and where each one starts" in first_screen
    for story in sorted(P0_STORIES):
        assert f"| {story} " in first_screen, f"{story} is not on the README first screen"
    for account in ("user@example.com", "seller@example.com", "demo.seller@marketplace.local"):
        assert account in first_screen
