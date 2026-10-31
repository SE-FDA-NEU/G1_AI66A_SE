"""Tests for UI styling, link button contrast on hover, and form input sizing (US22, #114, #155)."""

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
BASE_CSS = ROOT / "src" / "web" / "static" / "base.css"
CHECKOUT_HTML = ROOT / "src" / "web" / "pages" / "checkout.html"
CART_HTML = ROOT / "src" / "web" / "pages" / "cart.html"
PRODUCT_DETAIL_HTML = ROOT / "src" / "web" / "pages" / "product-detail.html"

CORE_SCREENS = [
    "products.html",
    "product-detail.html",
    "cart.html",
    "checkout.html",
    "order.html",
    "seller-products.html",
    "seller-product-new.html",
    "seller-orders.html",
    "seller-analytics.html",
    "seller-vouchers.html",
    "admin-portal.html",
]


class InputCollector(HTMLParser):
    """Collect all input elements with their attributes and locations."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "input":
            self.inputs.append(dict(attrs))


def test_base_css_served_as_stylesheet(client: TestClient) -> None:
    """The base stylesheet is served directly with proper content-type."""
    response = client.get("/static/base.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_link_button_labels_preserve_contrasting_text_on_hover() -> None:
    """Primary link buttons must preserve white text color on hover (#114).

    When an <a> element has the .button class, a:hover sets text color to
    --color-accent-hover while .button:hover sets background to the same color.
    Without an explicit color: #ffffff on .button:hover, both text and background
    become #1d4ed8, rendering the button label invisible.
    """
    css = BASE_CSS.read_text(encoding="utf-8")

    # Locate the button:hover, .button:hover block
    hover_match = re.search(
        r"button:hover,\s*\.button:hover\s*\{([^}]+)\}",
        css,
    )
    assert hover_match, "button:hover, .button:hover rule must exist in base.css"
    hover_block = hover_match.group(1)

    assert "color: #ffffff;" in hover_block, (
        "button:hover, .button:hover must set color: #ffffff to preserve contrast on <a> elements"
    )
    assert "background-color: var(--color-accent-hover);" in hover_block, (
        "button:hover, .button:hover must set background-color: var(--color-accent-hover)"
    )


def test_button_active_preserves_contrasting_text() -> None:
    """Button active state must also preserve contrasting text color."""
    css = BASE_CSS.read_text(encoding="utf-8")

    active_match = re.search(
        r"button:active,\s*\.button:active\s*\{([^}]+)\}",
        css,
    )
    assert active_match, "button:active, .button:active rule must exist in base.css"
    active_block = active_match.group(1)

    assert "color: #ffffff;" in active_block, (
        "button:active, .button:active must explicitly set color: #ffffff"
    )


def test_button_variant_hover_colors_retained() -> None:
    """Secondary and danger button variants retain contrasting text colors on hover."""
    css = BASE_CSS.read_text(encoding="utf-8")

    # Secondary hover
    sec_hover = re.search(
        r"\.button--secondary:hover,\s*button\.button--secondary:hover,\s*\.button-secondary:hover\s*\{([^}]+)\}",
        css,
    )
    assert sec_hover, "Secondary button hover rule must exist"
    assert "color: var(--color-accent);" in sec_hover.group(1)
    assert "background-color: var(--color-surface-hover);" in sec_hover.group(1)

    # Danger hover
    danger_hover = re.search(
        r"\.button--danger:hover,\s*button\.button--danger:hover\s*\{([^}]+)\}",
        css,
    )
    assert danger_hover, "Danger button hover rule must exist"
    assert "color: #ffffff;" in danger_hover.group(1)
    assert "background-color: #b91c1c;" in danger_hover.group(1)


def test_untyped_inputs_included_in_desktop_form_styles() -> None:
    """input:not([type]) must be included in desktop form styles so untyped inputs are 42px tall."""
    css = BASE_CSS.read_text(encoding="utf-8")

    # Locate the desktop form controls rule that includes min-height: 42px
    pattern = r"(input:not\(\[type\]\)[\s\S]*?\{[\s\S]*?min-height:\s*42px;[\s\S]*?\})"
    match = re.search(pattern, css)
    assert match, "Desktop form input rule must include input:not([type]) and min-height: 42px"
    block = match.group(1)

    assert 'input[type="text"]' in block
    assert "min-height: 42px;" in block


def test_untyped_inputs_included_in_mobile_sizing_styles() -> None:
    """input:not([type]) must be included in mobile media queries for min-height 44px."""
    css = BASE_CSS.read_text(encoding="utf-8")

    media_match = re.search(r"@media\s*\(max-width:\s*640px\)\s*\{([\s\S]+?)\}\s*@media", css)
    if not media_match:
        media_match = re.search(r"@media\s*\(max-width:\s*640px\)\s*\{([\s\S]+?)\}\s*\Z", css)
    assert media_match, "Mobile @media (max-width: 640px) rule must exist in base.css"
    mobile_css = media_match.group(1)

    assert "input:not([type])" in mobile_css, (
        "input:not([type]) must be included in mobile @media rule"
    )
    assert "min-height: 44px;" in mobile_css
    assert "font-size: 16px;" in mobile_css


def test_checkout_form_inputs_have_explicit_text_type() -> None:
    """Checkout address and delivery text inputs must have type="text" explicitly set."""
    html = CHECKOUT_HTML.read_text(encoding="utf-8")
    parser = InputCollector()
    parser.feed(html)

    expected_text_input_ids = {
        "address-recipient_name",
        "address-province",
        "address-district",
        "address-ward",
        "address-detailed_address",
        "checkout-recipient_name",
    }

    found_ids = {}
    for inp in parser.inputs:
        inp_id = inp.get("id")
        if inp_id in expected_text_input_ids:
            found_ids[inp_id] = inp.get("type")

    missing = expected_text_input_ids - set(found_ids.keys())
    assert set(found_ids.keys()) == expected_text_input_ids, f"Missing inputs: {missing}"
    for inp_id, inp_type in found_ids.items():
        assert inp_type == "text", f"Input #{inp_id} must have type='text', found: {inp_type}"


def test_product_detail_variant_inputs_have_explicit_text_type() -> None:
    """Product detail variant text inputs must have type="text" explicitly set."""
    html = PRODUCT_DETAIL_HTML.read_text(encoding="utf-8")
    parser = InputCollector()
    parser.feed(html)

    variant_text_ids = {"variant-sku", "variant-name"}
    found_ids = {}
    for inp in parser.inputs:
        inp_id = inp.get("id")
        if inp_id in variant_text_ids:
            found_ids[inp_id] = inp.get("type")

    assert set(found_ids.keys()) == variant_text_ids
    for inp_id, inp_type in found_ids.items():
        assert inp_type == "text", f"Input #{inp_id} must have type='text', found: {inp_type}"


def test_link_buttons_in_core_templates_use_button_class() -> None:
    """Verify that Continue shopping and Back to catalogue use .button class on anchor tags."""
    cart_html = CART_HTML.read_text(encoding="utf-8")
    assert '<a class="button" href="/products">Continue shopping</a>' in cart_html

    detail_html = PRODUCT_DETAIL_HTML.read_text(encoding="utf-8")
    assert '<a class="button button--link" href="/products">Back to catalogue</a>' in detail_html


def test_all_core_screens_include_base_design_system_stylesheet() -> None:
    """All core marketplace screens must include base.css for shared design tokens (US22, #155)."""
    for screen_name in CORE_SCREENS:
        path = ROOT / "src" / "web" / "pages" / screen_name
        assert path.exists(), f"Core screen {screen_name} must exist"
        html = path.read_text(encoding="utf-8")
        assert "/static/base.css" in html, f"{screen_name} must link /static/base.css"


def test_all_core_screens_have_responsive_viewport_meta() -> None:
    """All core marketplace screens must declare viewport meta tag for mobile responsiveness."""
    for screen_name in CORE_SCREENS:
        path = ROOT / "src" / "web" / "pages" / screen_name
        html = path.read_text(encoding="utf-8")
        assert '<meta name="viewport"' in html, f"{screen_name} must have viewport meta tag"
        assert "width=device-width" in html, f"{screen_name} must set width=device-width"


def test_table_screens_have_horizontal_scroll_containers() -> None:
    """Screens with complex tables must wrap tables in horizontal scroll containers."""
    table_screens = [
        "seller-products.html",
        "seller-vouchers.html",
        "admin-portal.html",
        "seller-analytics.html",
    ]
    for screen_name in table_screens:
        path = ROOT / "src" / "web" / "pages" / screen_name
        html = path.read_text(encoding="utf-8")
        assert "table-container" in html or "table-scroll" in html, (
            f"{screen_name} must wrap table in a scrollable container for responsiveness"
        )


def test_seller_analytics_css_has_responsive_breakpoints() -> None:
    """seller-analytics.css must provide grid collapse breakpoints for tablet and mobile."""
    css = (ROOT / "src" / "web" / "static" / "seller-analytics.css").read_text(encoding="utf-8")
    assert "@media (max-width: 950px)" in css
    assert "@media (max-width: 540px)" in css


def test_admin_portal_css_has_responsive_breakpoints() -> None:
    """admin-portal.css must provide responsive breakpoints for small screens."""
    css = (ROOT / "src" / "web" / "static" / "admin-portal.css").read_text(encoding="utf-8")
    assert "@media (max-width: 840px)" in css
    assert "portal-layout" in css
