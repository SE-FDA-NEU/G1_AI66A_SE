"""#225: Seller reads/replies to reviews without the Buyer purchase-review UI."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, select

from src.auth import create_access_token
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.review import Review
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests import test_purchase_roles_browser as purchase_ui
from tests.cart_db import BUYER_ID, SELLER_ID, add_product

api, browser, engine = purchase_ui.api, purchase_ui.browser, purchase_ui.engine
expect = purchase_ui.expect
PRODUCT_CODE = "REVIEW-225"
DETAIL_PATH = f"/products/{PRODUCT_CODE}"
REVIEWS_PATH = f"/api/v1/products/{PRODUCT_CODE}/reviews"


@pytest.fixture
def review_shop(browser, api, engine):
    product_id = add_product(engine, PRODUCT_CODE)
    with Session(engine) as session:
        session.get(Product, product_id).image_url = None
        session.add_all([
            User(id=4, name="Other seller", email="other-seller225@test.local", role="seller"),
            User(id=5, name="Admin", email="admin225@test.local", role="admin"),
        ])
        order = Order(buyer_id=BUYER_ID, total_amount=200_000, status="COMPLETED",
                      recipient_name="Buyer", delivery_address="Test address",
                      phone_number="0123456789")
        session.add(order)
        session.flush()
        seller_order = SellerOrder(order_id=order.id, seller_id=SELLER_ID,
                                   status="COMPLETED",
                                   completed_at=datetime(2026, 11, 1, tzinfo=UTC))
        session.add(seller_order)
        session.flush()
        items = [OrderItem(seller_order_id=seller_order.id, product_id=product_id,
                           quantity=1, unit_price=100_000) for _ in range(2)]
        session.add_all(items)
        session.commit()
        item_ids = [item.id for item in items]
        tokens = {role: create_access_token(session.get(User, user_id))
                  for role, user_id in {"buyer": BUYER_ID, "seller": SELLER_ID,
                                        "other_seller": 4, "admin": 5}.items()}
    response = api.post(REVIEWS_PATH, headers={"Authorization": f"Bearer {tokens['buyer']}"},
                        json={"order_item_id": item_ids[0], "rating": 5,
                              "comment": "Verified customer feedback"})
    assert response.status_code == 201
    context = browser.new_context(viewport={"width": 1280, "height": 1000})
    shop = purchase_ui.Shop(context.new_page(), api, tokens)
    shop.review_id = response.json()["data"]["id"]
    shop.item_id = item_ids[1]
    yield shop
    assert shop.errors == []
    context.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_seller_sees_only_customer_reviews_and_can_reply(review_shop, engine, width):
    shop, page = review_shop, review_shop.page
    page.set_viewport_size({"width": width, "height": 1000})
    shop.open(DETAIL_PATH, "seller")
    expect(page.get_by_role("heading", name="Customer reviews")).to_be_visible()
    expect(page.locator(".seller-reply-form")).to_be_visible()
    expect(page.locator("#review-form-section")).to_be_hidden()
    assert not any(path.endswith("/reviewable-items") for _, path, _ in shop.calls)
    page.locator(".seller-reply-form textarea").fill("Thanks for your review!")
    page.get_by_role("button", name="Reply", exact=True).click()
    expect(page.locator("#reviews-feedback")).to_have_text("Seller reply saved.")
    expect(page.locator(".review-card__reply")).to_contain_text("Thanks for your review!")
    expect(page.locator("#review-form-section")).to_be_hidden()
    with Session(engine) as session:
        review = session.get(Review, shop.review_id)
        assert review.seller_reply == "Thanks for your review!"
        assert review.seller_replied_at is not None
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if directory := os.environ.get("REVIEW_ROLE_ARTIFACTS"):
        output = Path(__file__).resolve().parents[1] / directory
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / f"seller-reviews-{width}.png"), full_page=True)


@pytest.mark.parametrize("actor", ["other_seller", "admin"])
def test_non_buyer_has_no_purchase_review_or_foreign_reply(review_shop, engine, actor):
    shop, page = review_shop, review_shop.page
    shop.open(DETAIL_PATH, actor)
    expect(page.locator("#reviews-list")).to_contain_text("Verified customer feedback")
    expect(page.locator("#reviews-section")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#review-form-section")).to_be_hidden()
    expect(page.locator(".seller-reply-form")).to_have_count(0)
    headers = {"Authorization": f"Bearer {shop.tokens[actor]}"}
    assert shop.api.get(REVIEWS_PATH.replace("/reviews", "/reviewable-items"),
                        headers=headers).status_code == 403
    assert shop.api.post(REVIEWS_PATH, headers=headers,
                         json={"order_item_id": shop.item_id, "rating": 5}).status_code == 403
    with Session(engine) as session:
        assert [review.id for review in session.exec(select(Review))] == [shop.review_id]


def test_eligible_buyer_can_still_submit_a_purchase_review(review_shop, engine):
    shop, page = review_shop, review_shop.page
    shop.open(DETAIL_PATH, "buyer")
    expect(page.locator("#review-form")).to_be_visible()
    page.locator("#review-comment").fill("Buyer review remains available")
    page.get_by_role("button", name="Submit review").click()
    expect(page.locator("#review-form-status")).to_have_text(
        "Your verified-purchase review was submitted.")
    expect(page.locator("#review-form")).to_be_hidden()
    expect(page.locator("#review-form-section")).to_be_visible()
    with Session(engine) as session:
        saved = session.exec(select(Review).where(Review.order_item_id == shop.item_id)).one()
        assert saved.buyer_id == BUYER_ID
        assert saved.comment == "Buyer review remains available"


def test_account_changes_and_logout_update_the_entire_review_section(review_shop):
    shop, page = review_shop, review_shop.page
    shop.open(DETAIL_PATH, "buyer")
    expect(page.locator("#review-form")).to_be_visible()
    page.locator("#review-comment").fill("Private buyer draft")
    shop.switch("seller")
    expect(page.locator("#review-form-section")).to_be_hidden()
    expect(page.locator(".seller-reply-form")).to_be_visible()
    shop.switch("buyer")
    expect(page.locator("#review-form")).to_be_visible()
    expect(page.locator("#review-comment")).to_have_value("")
    expect(page.locator(".seller-reply-form")).to_have_count(0)
    page.locator("#logout-button").click()
    expect(page.locator("#review-login-prompt")).to_be_visible()
    expect(page.locator("#review-form")).to_be_hidden()


def test_old_buyer_eligibility_cannot_restore_the_form_for_seller(review_shop):
    shop, page = review_shop, review_shop.page
    held = []
    page.route("**/reviewable-items", lambda route: held.append(route))
    with page.expect_request("**/reviewable-items"):
        shop.open(DETAIL_PATH, "buyer")
    expect(page.locator("#review-form-section")).to_be_visible()
    assert held
    shop.switch("seller")
    expect(page.locator(".seller-reply-form")).to_be_visible()
    for route in held:
        shop.forward(route)
    expect(page.locator("#review-form-section")).to_be_hidden()
    expect(page.locator("#review-form")).to_be_hidden()


def test_seller_section_stays_hidden_during_identity_loading(review_shop):
    shop, page = review_shop, review_shop.page
    held = []

    def delay_form_identity(route):
        if not held:
            held.append(route)
        else:
            shop.forward(route)

    page.route("**/api/v1/auth/me", delay_form_identity)
    shop.open(DETAIL_PATH, "seller")
    expect(page.locator(".seller-reply-form")).to_be_visible()
    expect(page.locator("#review-form-section")).to_be_hidden()
    shop.forward(held[0])
    expect(page.locator("#review-form-status")).to_have_text("")
    expect(page.locator("#review-form-section")).to_be_hidden()


def test_expired_session_restores_guest_review_login_prompt(review_shop):
    shop, page = review_shop, review_shop.page
    held = []

    def delay_form_identity(route):
        # Let the list detect expiry before the purchase form's request completes.
        if not held:
            held.append(route)
        else:
            shop.forward(route)

    page.route("**/api/v1/auth/me", delay_form_identity)
    shop.tokens["expired"] = create_access_token(
        User(id=SELLER_ID, name="Seller", email="seller@test.local", role="seller"),
        expires_in=-1,
    )
    shop.open(DETAIL_PATH, "expired")
    expect(page.locator("#review-login-prompt")).to_be_visible()
    shop.forward(held[0])
    expect(page.locator("#review-login-prompt")).to_be_visible()
    expect(page.locator("#review-form")).to_be_hidden()


@pytest.mark.parametrize("actor", ["buyer", "seller"])
def test_identity_failure_keeps_role_ui_and_allows_buyer_retry(review_shop, actor):
    shop, page = review_shop, review_shop.page
    page.route("**/api/v1/auth/me", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"error":{"message":"Unavailable"}}'))
    shop.open(DETAIL_PATH, actor)
    expect(page.locator("#reviews-error")).to_be_visible()
    if actor == "seller":
        expect(page.locator("#review-form-section")).to_be_hidden()
    else:
        expect(page.locator("#review-form-status")).to_have_text(
            "Unable to verify the current account.")
        expect(page.locator("#review-eligibility-retry")).to_be_visible()
        page.unroute("**/api/v1/auth/me")
        page.locator("#review-eligibility-retry").click()
        expect(page.locator("#review-form")).to_be_visible()


def test_restored_page_rechecks_role_before_showing_buyer_review_form(review_shop):
    shop, page = review_shop, review_shop.page
    shop.open(DETAIL_PATH, "buyer")
    expect(page.locator("#review-form")).to_be_visible()
    page.locator("#review-comment").fill("Private cached draft")
    page.evaluate("""token => {
        localStorage.setItem('access_token', token);
        window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
    }""", shop.tokens["seller"])
    expect(page.locator("#review-form-section")).to_be_hidden()
    expect(page.locator("#review-comment")).to_have_value("")
    expect(page.locator(".seller-reply-form")).to_be_visible()
