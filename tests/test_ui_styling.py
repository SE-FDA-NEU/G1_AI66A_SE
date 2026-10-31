"""Tests for UI styling, link button contrast on hover, and form input sizing (US22, #114)."""

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
BASE_CSS = ROOT / "src" / "web" / "static" / "base.css"
CHECKOUT_HTML = ROOT / "src" / "web" / "pages" / "checkout.html"
CART_HTML = ROOT / "src" / "web" / "pages" / "cart.html"
PRODUCT_DETAIL_HTML = ROOT / "src" / "web" / "pages" / "product-detail.html"
ORDER_CSS = ROOT / "src" / "web" / "static" / "order.css"


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

    assert "color: var(--color-on-accent);" in hover_block, (
        "button:hover, .button:hover must explicitly set the accent contrast color"
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

    assert "color: var(--color-on-accent);" in active_block, (
        "button:active, .button:active must explicitly set the accent contrast color"
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
    assert "color: var(--color-on-accent);" in danger_hover.group(1)
    assert "background-color: var(--color-danger-text);" in danger_hover.group(1)


def test_shared_design_tokens_cover_required_categories() -> None:
    """The shared stylesheet exposes stable tokens for #154 components."""
    css = BASE_CSS.read_text(encoding="utf-8")

    required_tokens = {
        "--color-accent",
        "--color-success-bg",
        "--color-warning-bg",
        "--color-danger-bg",
        "--color-info-bg",
        "--font-sans",
        "--font-size-sm",
        "--space-4",
        "--border-width",
        "--shadow-sm",
        "--radius-md",
        "--focus-width",
    }
    assert all(f"{token}:" in css for token in required_tokens)


def test_shared_components_have_semantic_variants() -> None:
    """Buttons, fields, cards, tables, badges, and alerts share base rules."""
    css = BASE_CSS.read_text(encoding="utf-8")

    for selector in (".card", ".input", ".table-wrap", "table.table", ".badge", ".alert"):
        assert selector in css, f"Shared component {selector} must be defined"
    for variant in ("success", "warning", "danger", "info"):
        assert f".badge--{variant}" in css
        assert f".alert--{variant}" in css


def test_untyped_inputs_included_in_desktop_form_styles() -> None:
    """input:not([type]) must be included in desktop form styles so untyped inputs are 42px tall."""
    css = BASE_CSS.read_text(encoding="utf-8")

    # Locate the desktop form controls rule that uses the shared control token.
    match = re.search(
        r"(input:not\(\[type\]\)[\s\S]*?\{[\s\S]*?min-height:\s*var\(--control-height\);[\s\S]*?\})",
        css,
    )
    assert match, (
        "Desktop form input rule must include input:not([type]) and the shared control token"
    )
    block = match.group(1)

    assert 'input[type="text"]' in block
    assert "min-height: var(--control-height);" in block


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

    assert set(found_ids.keys()) == expected_text_input_ids, (
        "Missing expected inputs in checkout.html: "
        f"{expected_text_input_ids - set(found_ids.keys())}"
    )
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


def test_control_aliases_preserve_native_sizing_and_textarea_min_height() -> None:
    """Control aliases .input, .select, .textarea must integrate into native control rules.

    - .textarea must preserve min-height: 96px on desktop and mobile instead of collapsing to 42px.
    - .select and .input must expand to 44px on mobile for touch compliance.
    - No isolated alias rule may override native controls with a duplicate declaration.
    """
    css = BASE_CSS.read_text(encoding="utf-8")

    # 1. Desktop base rule includes .input, .select, .textarea alongside native elements
    base_rule_match = re.search(
        r"input:not\(\[type\]\)[\s\S]*?textarea[\s\S]*?select[\s\S]*?\{[\s\S]*?min-height:\s*var\(--control-height\);[\s\S]*?\}",
        css,
    )
    assert base_rule_match, "Base control rule with --control-height must exist"
    base_selectors = base_rule_match.group(0).split("{")[0]
    assert ".input" in base_selectors
    assert ".select" in base_selectors
    assert ".textarea" in base_selectors

    # 2. textarea and .textarea must share the 96px minimum height
    ta_match = re.search(r"textarea,\s*\.textarea\s*\{[\s\S]*?min-height:\s*96px;[\s\S]*?\}", css)
    assert ta_match, "textarea and .textarea must both specify min-height: 96px"

    # 3. No duplicate isolated class rule resetting .textarea to var(--control-height)
    for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", css):
        sel_text, body = m.group(1).strip(), m.group(2).strip()
        if "min-height" in body:
            selectors = [s.strip() for s in sel_text.split(",")]
            # An isolated alias rule targets .textarea without native textarea
            has_ta_alias = any(s == ".textarea" for s in selectors)
            has_native_ta = any(s == "textarea" for s in selectors)
            if has_ta_alias and not has_native_ta:
                raise AssertionError(
                    f"Found conflicting isolated .textarea rule: {sel_text} {{ {body} }}"
                )

    # 4. Mobile media query includes .input and .select at 44px, and textarea / .textarea at 96px
    media_match = re.search(r"@media\s*\(max-width:\s*640px\)\s*\{([\s\S]+?)\}\s*@media", css)
    assert media_match, "Mobile media query (max-width: 640px) must exist"
    mobile_css = media_match.group(1)

    mobile_controls_match = re.search(
        r"input:not\(\[type\]\)[\s\S]*?select[\s\S]*?\{[\s\S]*?min-height:\s*44px;[\s\S]*?\}",
        mobile_css,
    )
    assert mobile_controls_match, "Mobile 44px min-height rule must exist"
    mobile_sel_block = mobile_controls_match.group(0).split("{")[0]
    assert ".input" in mobile_sel_block
    assert ".select" in mobile_sel_block

    mobile_ta_match = re.search(
        r"textarea,\s*\.textarea\s*\{[\s\S]*?min-height:\s*96px;[\s\S]*?\}",
        mobile_css,
    )
    assert mobile_ta_match, "Mobile textarea and .textarea must preserve min-height: 96px"


def test_semantic_badge_variants_resist_order_stylesheet_cascade_override() -> None:
    """Semantic badge variants must have higher specificity than the page-specific .badge rule.

    When base.css and order.css are both loaded, .badge--success, .badge--warning,
    .badge--danger, and .badge--info must retain their semantic foreground/background
    and not be overridden by the order stylesheet's neutral .badge colors.
    """
    base_css = BASE_CSS.read_text(encoding="utf-8")
    order_css = ORDER_CSS.read_text(encoding="utf-8")

    # 1. Base stylesheet must declare compound selectors (.badge.badge--*) with
    # specificity (0, 2, 0)
    for variant in ("neutral", "success", "warning", "danger", "info"):
        compound_selector = f".badge.badge--{variant}"
        assert compound_selector in base_css, (
            f"{compound_selector} compound selector required in base.css"
        )

    # 2. order.css .badge rule must not use !important to override semantic variants
    order_badge_match = re.search(r"\.badge\s*\{([^}]+)\}", order_css)
    assert order_badge_match, ".badge rule must exist in order.css"
    order_badge_block = order_badge_match.group(1)
    assert "!important" not in order_badge_block

    # 3. Simulate the CSS cascade for an element: <span class="badge badge--success">
    def selector_matches_badge(sel: str, element_classes: set[str]) -> bool:
        sel = sel.strip()
        if "#" in sel:
            return False
        tag_match = re.match(r"^([a-z0-9_-]+)", sel)
        if tag_match and tag_match.group(1) != "span":
            return False
        base_part = re.sub(r":not\([^)]*\)", "", sel)
        required_classes = set(re.findall(r"\.([\w-]+)", base_part))
        if not required_classes or not required_classes.issubset(element_classes):
            return False
        for neg_cls in re.findall(r":not\(\.([\w-]+)\)", sel):
            if neg_cls in element_classes:
                return False
        for neg_attr in re.findall(r':not\(\[class\*="([\w-]+)"\]\)', sel):
            if any(neg_attr in c for c in element_classes):
                return False
        return True

    def calculate_winning_declarations(
        classes: set[str], properties: list[str]
    ) -> dict[str, tuple[tuple[int, int, int], int, str]]:
        winning: dict[str, tuple[tuple[int, int, int], int, str]] = {}
        rule_index = 0

        combined_css = [("base.css", base_css), ("order.css", order_css)]
        for _, sheet_text in combined_css:
            clean = re.sub(r"/\*[\s\S]*?\*/", "", sheet_text)
            clean = re.sub(r"@keyframes[\s\S]*?\}\s*\}", "", clean)
            clean = re.sub(r"@media[\s\S]*?\}\s*\}", "", clean)
            for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", clean):
                raw_selectors = m.group(1).strip()
                body = m.group(2).strip()
                if raw_selectors.startswith("@"):
                    continue
                rule_index += 1
                for sel in (s.strip() for s in raw_selectors.split(",")):
                    if not selector_matches_badge(sel, classes):
                        continue

                    class_count = len(re.findall(r"\.[\w-]+", sel)) + len(
                        re.findall(r"\[[^\]]+\]", sel)
                    )
                    element_count = 1 if re.match(r"^span\b", sel) else 0
                    specificity = (0, class_count, element_count)

                    for decl in body.split(";"):
                        if ":" in decl:
                            prop, val = decl.split(":", 1)
                            prop = prop.strip()
                            val = val.strip()
                            if prop in properties:
                                current = winning.get(prop)
                                if current is None or specificity > current[0] or (
                                    specificity == current[0] and rule_index >= current[1]
                                ):
                                    winning[prop] = (specificity, rule_index, val)
        return winning

    success_decls = calculate_winning_declarations(
        {"badge", "badge--success"}, ["color", "background", "background-color"]
    )
    assert success_decls["color"][2] == "var(--color-success-text)", (
        f"badge--success color overridden: {success_decls['color']}"
    )
    success_bg = (success_decls.get("background") or success_decls.get("background-color"))[2]
    assert success_bg == "var(--color-success-bg)", (
        f"badge--success background overridden: {success_bg}"
    )

    danger_decls = calculate_winning_declarations(
        {"badge", "badge--danger"}, ["color", "background", "background-color"]
    )
    assert danger_decls["color"][2] == "var(--color-danger-text)"
    danger_bg = (danger_decls.get("background") or danger_decls.get("background-color"))[2]
    assert danger_bg == "var(--color-danger-bg)"


    neutral_decls = calculate_winning_declarations(
        {"badge"}, ["color", "background-color"]
    )
    assert neutral_decls["color"][2] == "#475569"
    assert neutral_decls["background-color"][2] == "#f1f5f9"
