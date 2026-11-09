"""#227: real notification badge/read interactions over isolated production APIs."""

import os
from pathlib import Path

import pytest
from sqlmodel import Session

from src.auth import create_access_token
from src.models.user import User
from tests import test_notification_badge as badge_api
from tests import test_purchase_roles_browser as purchase_ui

api, engine, browser = badge_api.api, badge_api.engine, purchase_ui.browser
expect = purchase_ui.expect
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def notification_shop(browser, api, engine):
    with Session(engine) as session:
        tokens = {role: create_access_token(session.get(User, user_id))
                  for role, user_id in {"buyer": 2, "seller": 1, "other_buyer": 3}.items()}
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    shop = purchase_ui.Shop(context.new_page(), api, tokens)
    yield shop
    assert shop.errors == []
    context.close()


@pytest.mark.parametrize("count", [0, 1, 99, 100, 125])
def test_badge_count_boundaries_and_accessible_exact_total(notification_shop, engine, count):
    badge_api.seed_notifications(engine, unread=count, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/products", "buyer")
    link = page.locator('a[href="/notifications"]')
    label = f"Notifications, {count} unread" if count else "Notifications"
    expect(link).to_have_attribute("aria-label", label)
    if count:
        expect(page.locator(".notification-badge")).to_have_text(
            "99+" if count > 99 else str(count))
        expect(page.locator(".notification-badge")).to_be_visible()
    else:
        expect(page.locator(".notification-badge")).to_be_hidden()


def test_guest_has_no_badge_or_count_request(notification_shop):
    shop, page = notification_shop, notification_shop.page
    shop.open("/products", None)
    expect(page.locator(".notification-badge")).to_be_hidden()
    assert not any(path.endswith("/unread-count") for _, path, _ in shop.calls)


def test_single_read_updates_badge_and_another_open_tab(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=2, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/products", "buyer")
    expect(page.locator(".notification-badge")).to_have_text("2")
    second = purchase_ui.Shop(page.context.new_page(), shop.api, shop.tokens)
    second.page.goto(purchase_ui.ORIGIN + "/notifications")
    expect(second.page.locator(".notification-badge")).to_have_text("2")

    second.page.get_by_role("button", name="Mark as read", exact=True).first.click()

    expect(second.page.locator(".notification-badge")).to_have_text("1")
    expect(page.locator(".notification-badge")).to_have_text("1")
    expect(second.page.locator(".notification--unread")).to_have_count(1)
    assert second.errors == []


def test_mark_all_reads_notifications_outside_the_displayed_hundred(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=125, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    expect(page.locator(".notification-badge")).to_have_text("99+")
    expect(page.locator(".notification--unread")).to_have_count(100)
    page.get_by_role("button", name="Mark all as read", exact=True).click()
    expect(page.locator("#notifications-status")).to_have_text("0 unread notifications.")
    expect(page.locator(".notification-badge")).to_be_hidden()
    expect(page.locator("#notifications-mark-all")).to_be_disabled()
    assert all(value is not None for value in badge_api.stored_reads(engine).values())


def test_overlapping_reads_in_two_tabs_refresh_after_each_commit(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=2, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    expect(page.locator("#notifications-status")).to_have_text("2 unread notifications.")
    second = purchase_ui.Shop(page.context.new_page(), shop.api, shop.tokens)
    second.page.goto(purchase_ui.ORIGIN + "/notifications")
    expect(second.page.locator("#notifications-status")).to_have_text("2 unread notifications.")
    held = []
    page.route("**/notifications/*/read", lambda route: held.append(route))
    with page.expect_request("**/notifications/*/read"):
        page.get_by_role("button", name="Mark as read", exact=True).first.click()
    second.page.get_by_role("button", name="Mark as read", exact=True).nth(1).click()
    expect(page.locator("#notifications-status")).to_have_text("1 unread notification.")
    shop.forward(held[0])
    expect(page.locator(".notification-badge")).to_be_hidden()
    expect(second.page.locator(".notification-badge")).to_be_hidden()
    expect(page.locator("#notifications-status")).to_have_text("0 unread notifications.")
    assert second.errors == []


def test_opening_related_page_reads_notification_before_navigation(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=1, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    page.get_by_role("link", name="Open related page", exact=True).click()
    expect(page).to_have_url(purchase_ui.ORIGIN + "/products")
    expect(page.locator(".notification-badge")).to_be_hidden()
    assert all(value is not None for value in badge_api.stored_reads(engine).values())


def test_failed_read_retains_unread_state_and_allows_retry(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=1, read=0)
    shop, page = notification_shop, notification_shop.page
    page.route("**/notifications/*/read", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"error":{"message":"Please retry."}}'))
    shop.open("/notifications", "buyer")
    page.get_by_role("link", name="Open related page", exact=True).click()
    expect(page.locator("#notifications-error")).to_have_text("Please retry.")
    expect(page).to_have_url(purchase_ui.ORIGIN + "/notifications")
    expect(page.locator(".notification-badge")).to_have_text("1")
    assert all(value is None for value in badge_api.stored_reads(engine).values())
    page.unroute("**/notifications/*/read")
    page.get_by_role("button", name="Mark as read", exact=True).click()
    expect(page.locator("#notifications-status")).to_have_text("0 unread notifications.")
    expect(page.locator("#notifications-mark-all")).to_be_disabled()
    expect(page.locator(".notification-badge")).to_be_hidden()


def test_failed_mark_all_can_retry_without_losing_unread_state(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=2, read=0)
    shop, page = notification_shop, notification_shop.page
    page.route("**/notifications/mark-all-read", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"error":{"message":"Please retry."}}'))
    shop.open("/notifications", "buyer")
    page.locator("#notifications-mark-all").click()
    expect(page.locator("#notifications-error")).to_have_text("Please retry.")
    expect(page.locator(".notification-badge")).to_have_text("2")
    expect(page.locator("#notifications-mark-all")).to_be_enabled()
    assert all(value is None for value in badge_api.stored_reads(engine).values())
    page.unroute("**/notifications/mark-all-read")
    page.locator("#notifications-mark-all").click()
    expect(page.locator(".notification-badge")).to_be_hidden()


def test_badge_count_error_recovers_on_focus(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=2, read=0)
    shop, page = notification_shop, notification_shop.page
    page.route("**/notifications/unread-count", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"error":{"message":"Unavailable"}}'))
    shop.open("/products", "buyer")
    expect(page.locator('a[href="/notifications"]')).to_have_attribute(
        "aria-label", "Notifications, unread count unavailable")
    expect(page.locator(".notification-badge")).to_be_hidden()
    page.unroute("**/notifications/unread-count")
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.locator(".notification-badge")).to_have_text("2")


def test_old_mark_all_response_cannot_change_new_account_and_duplicate_is_blocked(
    notification_shop, engine,
):
    badge_api.seed_notifications(engine, unread=2, read=0)
    badge_api.seed_notifications(engine, user_id=3, unread=7, read=0)
    shop, page = notification_shop, notification_shop.page
    held = []

    def hold_committed_response(route):
        response = shop.api.post(badge_api.ALL_PATH, headers=route.request.headers)
        held.append((route, response))

    page.route("**/notifications/mark-all-read", hold_committed_response)
    shop.open("/notifications", "buyer")
    with page.expect_request("**/notifications/mark-all-read"):
        page.locator("#notifications-mark-all").click()
    expect(page.locator("#notifications-mark-all")).to_be_disabled()
    page.locator("#notifications-mark-all").evaluate(
        "button => button.dispatchEvent(new Event('click'))")
    assert len(held) == 1
    shop.switch("other_buyer")
    expect(page.locator(".notification-badge")).to_have_text("7")
    expect(page.locator("#notifications-status")).to_have_text("7 unread notifications.")
    route, response = held[0]
    route.fulfill(status=response.status_code, body=response.content,
                  content_type="application/json")
    expect(page.locator("#notifications-status")).to_have_text("7 unread notifications.")
    expect(page.locator(".notification-badge")).to_have_text("7")
    expect(page.locator("#notifications-mark-all")).to_be_enabled()


def test_mark_all_is_available_when_only_older_hidden_rows_are_unread(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=25, read=100)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    expect(page.locator("#notifications-status")).to_have_text("25 unread notifications.")
    expect(page.locator(".notification--unread")).to_have_count(0)
    expect(page.locator("#notifications-mark-all")).to_be_enabled()
    page.locator("#notifications-mark-all").click()
    expect(page.locator(".notification-badge")).to_be_hidden()
    assert all(value is not None for value in badge_api.stored_reads(engine).values())


def test_account_changes_use_new_recipient_and_logout_hides_badge(notification_shop, engine):
    badge_api.seed_notifications(engine, unread=2, read=0)
    badge_api.seed_notifications(engine, user_id=1, unread=7, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    expect(page.locator(".notification-badge")).to_have_text("2")
    shop.switch("seller")
    expect(page.locator(".notification-badge")).to_have_text("7")
    expect(page.locator("#notifications-status")).to_have_text("7 unread notifications.")
    shop.switch("other_buyer")
    expect(page.locator(".notification-badge")).to_be_hidden()
    expect(page.locator("#notifications-status")).to_have_text("You have no notifications.")
    page.locator("#notifications-logout").click()
    expect(page).to_have_url(purchase_ui.ORIGIN + "/login?return_to=%2Fnotifications")
    expect(page.locator(".notification-badge")).to_be_hidden()


@pytest.mark.parametrize("storage", ["localStorage", "sessionStorage"])
def test_badge_accepts_existing_legacy_and_session_tokens(notification_shop, engine, storage):
    badge_api.seed_notifications(engine, unread=3, read=0)
    shop, page = notification_shop, notification_shop.page
    shop.open("/notifications", "buyer")
    expect(page.locator(".notification-badge")).to_have_text("3")
    key = "token" if storage == "localStorage" else "access_token"
    page.evaluate("""({storage, key, token}) => {
        localStorage.removeItem('access_token');
        window[storage].setItem(key, token);
        window.dispatchEvent(new StorageEvent('storage', {key: 'access_token'}));
    }""", {"storage": storage, "key": key, "token": shop.tokens["buyer"]})
    expect(page.locator("#notifications-status")).to_have_text("3 unread notifications.")
    page.locator("#notifications-mark-all").click()
    expect(page.locator(".notification-badge")).to_be_hidden()
    expect(page.locator("#notifications-status")).to_have_text("0 unread notifications.")


@pytest.mark.parametrize("width", [390, 1280])
def test_large_badge_fits_navigation_on_mobile_and_desktop(notification_shop, engine, width):
    badge_api.seed_notifications(engine, unread=125, read=0)
    shop, page = notification_shop, notification_shop.page
    page.set_viewport_size({"width": width, "height": 900})
    shop.open("/notifications", "buyer")
    expect(page.locator(".notification-badge")).to_have_text("99+")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator('a[href="/notifications"]').bounding_box()["height"] >= 44
    if directory := os.environ.get("NOTIFICATION_BADGE_ARTIFACTS"):
        output = ROOT / directory
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / f"notification-badge-{width}.png"))


def test_every_existing_notification_navigation_loads_badge_controller():
    pages = [page for page in (ROOT / "src/web/pages").glob("*.html")
             if 'href="/notifications"' in page.read_text(encoding="utf-8")]
    assert pages
    for page in pages:
        assert 'src="/static/notification-badge.js"' in page.read_text(encoding="utf-8"), page.name
