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
SELLER_PRODUCT_NEW_HTML = ROOT / "src" / "web" / "pages" / "seller-product-new.html"
LOGIN_HTML = ROOT / "src" / "web" / "pages" / "login.html"
ORDER_HTML = ROOT / "src" / "web" / "pages" / "order.html"
SELLER_ANALYTICS_HTML = ROOT / "src" / "web" / "pages" / "seller-analytics.html"
SELLER_VOUCHERS_HTML = ROOT / "src" / "web" / "pages" / "seller-vouchers.html"
ADMIN_PORTAL_HTML = ROOT / "src" / "web" / "pages" / "admin-portal.html"


class InputCollector(HTMLParser):
    """Collect all input elements with their attributes and locations."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "input":
            self.inputs.append(dict(attrs))


class RequiredLabelCollector(HTMLParser):
    """Collect labels and the controls they associate with."""

    def __init__(self) -> None:
        super().__init__()
        self.controls: dict[str, bool] = {}
        self.labels: list[tuple[str, set[str]]] = []
        self._active_labels: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"input", "select", "textarea"} and attributes.get("id"):
            control_id = attributes["id"]
            self.controls[control_id] = "required" in attributes
            for label in self._active_labels:
                label["control_ids"].add(control_id)  # type: ignore[union-attr]
        if tag == "label":
            self._active_labels.append(
                {"text": [], "for": attributes.get("for"), "control_ids": set()}
            )

    def handle_data(self, data: str) -> None:
        for label in self._active_labels:
            label["text"].append(data)  # type: ignore[union-attr]

    def handle_endtag(self, tag: str) -> None:
        if tag != "label":
            return
        label = self._active_labels.pop()
        control_ids = set(label["control_ids"])  # type: ignore[arg-type]
        if label["for"]:
            control_ids.add(label["for"])  # type: ignore[arg-type]
        self.labels.append(("".join(label["text"]).strip(), control_ids))  # type: ignore[arg-type]


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
        r"\.button--secondary:hover,\s*button\.button--secondary:hover,"
        r"\s*\.button-secondary:hover\s*\{([^}]+)\}",
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
        r"(input:not\(\[type\]\)[\s\S]*?\{[\s\S]*?"
        r"min-height:\s*var\(--control-height\);[\s\S]*?\})",
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
    """Control aliases .input, .select, .textarea must preserve the native control sizing contract.

    - Desktop contract:
      * Single-line controls (input, select, .input, .select) have min-height:
        var(--control-height).
      * Multiline controls (textarea, .textarea) have min-height: 96px and resize: vertical.
      * textareas must never receive min-height: var(--control-height) to prevent collapsing.
    - Responsive mobile contract:
      * Single-line controls expand to min-height: 44px and font-size: 16px (touch compliance).
      * Multiline controls preserve min-height: 96px and font-size: 16px.
    - In both desktop and mobile, native controls and their corresponding aliases must produce
      identical sizing contracts in the CSS cascade.
    """
    css = BASE_CSS.read_text(encoding="utf-8")

    # 1. Base control box model rule includes all controls and aliases
    common_box_match = re.search(
        r"input:not\(\[type\]\)[\s\S]*?textarea[\s\S]*?select[\s\S]*?\.input[\s\S]*?\.select[\s\S]*?\.textarea[\s\S]*?\{[\s\S]*?display:\s*block;[\s\S]*?width:\s*100%;[\s\S]*?\}",
        css,
    )
    assert common_box_match, (
        "Base control box-model rule must include all native and alias selectors"
    )

    # 2. Desktop single-line sizing rule specifies min-height: var(--control-height)
    # and strictly excludes textarea and .textarea
    single_line_selectors = None
    for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", re.sub(r"@media[\s\S]*?\}\s*\}", "", css)):
        sel_text, body = m.group(1).strip(), m.group(2).strip()
        if "min-height: var(--control-height)" in body:
            single_line_selectors = [s.strip() for s in sel_text.split(",")]
            break
    assert single_line_selectors, "Single-line control sizing rule with --control-height must exist"
    assert ".input" in single_line_selectors
    assert ".select" in single_line_selectors
    assert "textarea" not in single_line_selectors, (
        "textarea must NOT be in single-line control sizing rule"
    )
    assert ".textarea" not in single_line_selectors, (
        ".textarea must NOT be in single-line control sizing rule"
    )

    # 3. Multiline sizing rule specifies min-height: 96px for textarea and .textarea
    ta_match = re.search(
        r"textarea,\s*\.textarea\s*\{[\s\S]*?min-height:\s*96px;[\s\S]*?resize:\s*vertical;[\s\S]*?\}",
        css,
    )
    assert ta_match, "textarea and .textarea must share min-height: 96px and resize: vertical"

    # 4. Mobile media query includes .input/.select at 44px, and textarea/.textarea at 96px
    media_match = re.search(r"@media\s*\(max-width:\s*640px\)\s*\{([\s\S]+?)\}\s*@media", css)
    assert media_match, "Mobile media query (max-width: 640px) must exist"
    mobile_css = media_match.group(1)

    mobile_controls_selectors = None
    mobile_ta_selectors = None
    for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", mobile_css):
        sel_text, body = m.group(1).strip(), m.group(2).strip()
        if "min-height: 44px" in body:
            mobile_controls_selectors = [s.strip() for s in sel_text.split(",")]
        elif "min-height: 96px" in body:
            mobile_ta_selectors = [s.strip() for s in sel_text.split(",")]

    assert mobile_controls_selectors, "Mobile 44px min-height rule must exist"
    assert ".input" in mobile_controls_selectors
    assert ".select" in mobile_controls_selectors
    assert "textarea" not in mobile_controls_selectors
    assert ".textarea" not in mobile_controls_selectors

    assert mobile_ta_selectors, "Mobile textarea 96px min-height rule must exist"
    assert "textarea" in mobile_ta_selectors
    assert ".textarea" in mobile_ta_selectors

    # 5. Verify CSS cascade sizing contract requirements for native vs alias controls
    def evaluate_cascade_sizing(
        tag: str, classes: set[str], input_type: str | None = "text", in_mobile: bool = False
    ) -> dict[str, str]:
        """Determine winning min-height and font-size declarations for a given element."""
        declarations: dict[str, tuple[tuple[int, int, int], int, str]] = {}
        rule_idx = 0

        # Parse rules from desktop or mobile media block
        css_to_parse = mobile_css if in_mobile else re.sub(r"@media[\s\S]*?\}\s*\}", "", css)
        clean = re.sub(r"/\*[\s\S]*?\*/", "", css_to_parse)

        for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", clean):
            raw_selectors, body = m.group(1).strip(), m.group(2).strip()
            if raw_selectors.startswith("@"):
                continue
            rule_idx += 1
            for sel in (s.strip() for s in raw_selectors.split(",")):
                sel_tag_match = re.match(r"^([a-z0-9_-]+)", sel)
                if sel_tag_match and sel_tag_match.group(1) != tag:
                    continue

                if tag == "input":
                    type_match = re.search(r'\[type="([^"]+)"\]', sel)
                    if type_match:
                        if type_match.group(1) != input_type:
                            continue
                    elif ":not([type])" in sel:
                        if input_type is not None:
                            continue

                sel_classes = set(re.findall(r"\.([\w-]+)", sel))
                if sel_classes and not sel_classes.issubset(classes):
                    continue
                if not sel_classes and not sel_tag_match:
                    continue

                class_attr_count = len(sel_classes) + (1 if "[" in sel or ":not" in sel else 0)
                specificity = (0, class_attr_count, 1 if sel_tag_match else 0)
                for decl in body.split(";"):
                    if ":" in decl:
                        prop, val = decl.split(":", 1)
                        prop, val = prop.strip(), val.strip()
                        if prop in ("min-height", "font-size"):
                            cur = declarations.get(prop)
                            is_better = cur is None or specificity > cur[0] or (
                                specificity == cur[0] and rule_idx >= cur[1]
                            )
                            if is_better:
                                declarations[prop] = (specificity, rule_idx, val)

        return {k: v[2] for k, v in declarations.items()}

    # Desktop contract assertions: native controls and aliases must produce identical sizing
    native_input_desktop = evaluate_cascade_sizing(
        "input", set(), input_type="text", in_mobile=False
    )
    untyped_input_desktop = evaluate_cascade_sizing(
        "input", set(), input_type=None, in_mobile=False
    )
    alias_input_desktop = evaluate_cascade_sizing(
        "input", {"input"}, input_type="text", in_mobile=False
    )
    assert native_input_desktop.get("min-height") == "var(--control-height)"
    assert untyped_input_desktop.get("min-height") == "var(--control-height)"
    assert alias_input_desktop.get("min-height") == native_input_desktop.get("min-height")

    native_select_desktop = evaluate_cascade_sizing("select", set(), in_mobile=False)
    alias_select_desktop = evaluate_cascade_sizing("select", {"select"}, in_mobile=False)
    assert native_select_desktop.get("min-height") == "var(--control-height)"
    assert alias_select_desktop.get("min-height") == native_select_desktop.get("min-height")

    native_ta_desktop = evaluate_cascade_sizing("textarea", set(), in_mobile=False)
    alias_ta_desktop = evaluate_cascade_sizing("textarea", {"textarea"}, in_mobile=False)
    standalone_ta_desktop = evaluate_cascade_sizing("div", {"textarea"}, in_mobile=False)
    assert native_ta_desktop.get("min-height") == "96px"
    assert alias_ta_desktop.get("min-height") == "96px"
    assert standalone_ta_desktop.get("min-height") == "96px"

    # Mobile contract assertions: native controls and aliases must produce identical sizing
    native_input_mobile = evaluate_cascade_sizing("input", set(), in_mobile=True)
    alias_input_mobile = evaluate_cascade_sizing("input", {"input"}, in_mobile=True)
    assert native_input_mobile.get("min-height") == "44px"
    assert native_input_mobile.get("font-size") == "16px"
    assert alias_input_mobile.get("min-height") == native_input_mobile.get("min-height")
    assert alias_input_mobile.get("font-size") == native_input_mobile.get("font-size")

    native_select_mobile = evaluate_cascade_sizing("select", set(), in_mobile=True)
    alias_select_mobile = evaluate_cascade_sizing("select", {"select"}, in_mobile=True)
    assert native_select_mobile.get("min-height") == "44px"
    assert native_select_mobile.get("font-size") == "16px"
    assert alias_select_mobile.get("min-height") == native_select_mobile.get("min-height")
    assert alias_select_mobile.get("font-size") == native_select_mobile.get("font-size")

    native_ta_mobile = evaluate_cascade_sizing("textarea", set(), in_mobile=True)
    alias_ta_mobile = evaluate_cascade_sizing("textarea", {"textarea"}, in_mobile=True)
    standalone_ta_mobile = evaluate_cascade_sizing("div", {"textarea"}, in_mobile=True)
    assert native_ta_mobile.get("min-height") == "96px"
    assert native_ta_mobile.get("font-size") == "16px"
    assert alias_ta_mobile.get("min-height") == "96px"
    assert alias_ta_mobile.get("font-size") == "16px"
    assert standalone_ta_mobile.get("min-height") == "96px"
    assert standalone_ta_mobile.get("font-size") == "16px"


def test_semantic_badge_variants_resist_order_stylesheet_cascade_override() -> None:
    """Semantic badge variants must have higher specificity than the page-specific .badge rule.

    When base.css and order.css are both loaded, all supported variants (.badge--success,
    .badge--warning, .badge--danger, and .badge--info) must retain their intended semantic
    foreground and background colors, and must not be overridden by the order stylesheet's
    neutral .badge colors (#475569 / #f1f5f9).
    """
    base_css = BASE_CSS.read_text(encoding="utf-8")
    order_css = ORDER_CSS.read_text(encoding="utf-8")

    # 1. Base stylesheet must declare compound selectors (.badge.badge--*) with
    # specificity (0, 2, 0) for all supported variants
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

    # 3. Simulate the CSS cascade for badge elements across both stylesheets
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

    # Verify ALL 4 supported semantic variants retain their intended colors
    expected_variants = {
        "success": ("var(--color-success-text)", "var(--color-success-bg)"),
        "warning": ("var(--color-warning-text)", "var(--color-warning-bg)"),
        "danger": ("var(--color-danger-text)", "var(--color-danger-bg)"),
        "info": ("var(--color-info-text)", "var(--color-info-bg)"),
    }

    for variant_name, (expected_color, expected_bg) in expected_variants.items():
        # Test compound class: <span class="badge badge--variant">
        decls = calculate_winning_declarations(
            {"badge", f"badge--{variant_name}"}, ["color", "background", "background-color"]
        )
        assert decls["color"][2] == expected_color, (
            f"badge--{variant_name} color overridden: {decls['color']}"
        )
        bg = (decls.get("background") or decls.get("background-color"))[2]
        assert bg == expected_bg, (
            f"badge--{variant_name} background overridden: {bg}"
        )
        # Explicitly verify neutral colors did not win
        assert decls["color"][2] != "#475569", (
            f"badge--{variant_name} color must not be neutral #475569"
        )
        assert bg != "#f1f5f9", f"badge--{variant_name} background must not be neutral #f1f5f9"

        # Test standalone class: <span class="badge--variant">
        standalone_decls = calculate_winning_declarations(
            {f"badge--{variant_name}"}, ["color", "background", "background-color"]
        )
        assert standalone_decls["color"][2] == expected_color
        s_bg = (standalone_decls.get("background") or standalone_decls.get("background-color"))[2]
        assert s_bg == expected_bg

    # Neutral variant retains subtle tokens
    neutral_decls = calculate_winning_declarations(
        {"badge", "badge--neutral"}, ["color", "background", "background-color"]
    )
    assert neutral_decls["color"][2] == "var(--color-text-secondary)"
    neutral_bg = (
        neutral_decls.get("background") or neutral_decls.get("background-color")
    )[2]
    assert neutral_bg == "var(--color-surface-subtle)"

    # Default unstyled badge on order page gets neutral order.css styling
    default_decls = calculate_winning_declarations(
        {"badge"}, ["color", "background-color"]
    )
    assert default_decls["color"][2] == "#475569"
    assert default_decls["background-color"][2] == "#f1f5f9"


def test_all_core_screens_include_base_design_system_stylesheet() -> None:
    """All core marketplace screens must include base.css for shared design tokens."""
    for screen_name in CORE_SCREENS:
        path = ROOT / "src" / "web" / "pages" / screen_name
        assert path.exists(), f"Core screen {screen_name} must exist"
        html = path.read_text(encoding="utf-8")
        assert "/static/base.css" in html, f"{screen_name} must link /static/base.css"


def test_screen_stylesheets_do_not_import_base_css() -> None:
    """Pages load base.css once through HTML links, not render-blocking CSS imports."""
    for path in (ROOT / "src" / "web" / "static").glob("*.css"):
        assert '@import "base.css"' not in path.read_text(encoding="utf-8"), path.name


def test_admin_and_seller_templates_use_button_design_system_classes() -> None:
    """Migrated templates use the .button* convention without mixed legacy classes."""
    for screen_name in ("admin-portal.html", "seller-products.html", "seller-vouchers.html"):
        html = (ROOT / "src" / "web" / "pages" / screen_name).read_text(encoding="utf-8")
        assert not re.search(r'class="[^"]*\bbtn(?:-|[^"]*\bbtn)', html), screen_name


def test_all_core_screens_have_responsive_viewport_meta() -> None:
    """All core marketplace screens must declare a responsive viewport."""
    for screen_name in CORE_SCREENS:
        html = (ROOT / "src" / "web" / "pages" / screen_name).read_text(encoding="utf-8")
        assert '<meta name="viewport"' in html, f"{screen_name} must have viewport meta tag"
        assert "width=device-width" in html, f"{screen_name} must set width=device-width"


def test_table_screens_have_horizontal_scroll_containers() -> None:
    """Complex tables must be wrapped in horizontal scroll containers."""
    for screen_name in (
        "seller-products.html",
        "seller-vouchers.html",
        "admin-portal.html",
        "seller-analytics.html",
    ):
        html = (ROOT / "src" / "web" / "pages" / screen_name).read_text(encoding="utf-8")
        assert "table-container" in html or "table-scroll" in html, (
            f"{screen_name} must wrap table in a scrollable container"
        )


def test_seller_analytics_css_has_responsive_breakpoints() -> None:
    """Seller analytics must provide tablet and mobile breakpoints."""
    css = (ROOT / "src" / "web" / "static" / "seller-analytics.css").read_text(encoding="utf-8")
    assert "@media (max-width: 950px)" in css
    assert "@media (max-width: 540px)" in css


def test_admin_portal_css_has_responsive_breakpoints() -> None:
    """Admin portal must provide responsive breakpoints for small screens."""
    css = (ROOT / "src" / "web" / "static" / "admin-portal.css").read_text(encoding="utf-8")
    assert "@media (max-width: 840px)" in css
    assert "portal-layout" in css


def test_required_form_fields_marked_with_asterisk() -> None:
    """Verify that only required controls receive asterisks across forms (#158)."""
    # 1. Seller Product Creation form
    seller_html = SELLER_PRODUCT_NEW_HTML.read_text(encoding="utf-8")
    assert "Fields marked * are required." in seller_html
    for label in [
        "Product name *",
        "Description *",
        "Price (₫) *",
        "Stock quantity *",
        "Image URL *",
    ]:
        assert f">{label}</label>" in seller_html, f"Missing asterisk in seller label: {label}"

    # 2. Login form
    login_html = LOGIN_HTML.read_text(encoding="utf-8")
    assert "Email *" in login_html
    assert "Password *" in login_html

    # 3. Order return form
    order_html = ORDER_HTML.read_text(encoding="utf-8")
    assert "Delivered shop order *" in order_html
    assert "Reason for return/refund *" in order_html
    assert "Supporting evidence *" in order_html

    # 4. Product detail forms (add to cart, option create, reviews)
    detail_html = PRODUCT_DETAIL_HTML.read_text(encoding="utf-8")
    assert "Quantity *" in detail_html
    assert "SKU *" in detail_html
    assert "Option name *" in detail_html
    assert "Price (VND) *" in detail_html
    assert "Stock *" in detail_html
    assert "Completed purchase *" in detail_html
    assert "Rating *" in detail_html

    # 5. Seller analytics filter form
    analytics_html = SELLER_ANALYTICS_HTML.read_text(encoding="utf-8")
    assert "From (UTC, inclusive) *" in analytics_html
    assert "To (UTC, inclusive) *" in analytics_html

    # 6. Checkout address and delivery forms
    checkout_html = CHECKOUT_HTML.read_text(encoding="utf-8")
    assert "Recipient name *" in checkout_html
    assert "Phone number *" in checkout_html
    assert "Province / city *" in checkout_html
    assert "District *" in checkout_html
    assert "Ward *" in checkout_html
    assert "Detailed address *" in checkout_html
    assert "Delivery address *" in checkout_html
    assert "Payment method *" in checkout_html

    # 7. Admin portal forms
    admin_html = ADMIN_PORTAL_HTML.read_text(encoding="utf-8")
    assert "Category Name *" in admin_html
    assert "Slug (Unique URL identifier) *" in admin_html
    assert "Voucher Code *" in admin_html
    assert "Discount Type *" in admin_html
    assert "Start Date (UTC) *" in admin_html
    assert "End Date (UTC) *" in admin_html
    assert "Account Status *" in admin_html
    assert "Moderation Reason *" in admin_html
    assert "Adjudication Action *" in admin_html
    assert "Decision Notes *" in admin_html


def test_asterisks_only_mark_required_controls_and_explanation_is_consistent() -> None:
    """Every asterisk label must target required control and explain the convention."""
    pages = (
        SELLER_PRODUCT_NEW_HTML,
        LOGIN_HTML,
        ORDER_HTML,
        PRODUCT_DETAIL_HTML,
        SELLER_ANALYTICS_HTML,
        CHECKOUT_HTML,
        ADMIN_PORTAL_HTML,
        SELLER_VOUCHERS_HTML,
    )
    for path in pages:
        html = path.read_text(encoding="utf-8")
        assert "Fields marked * are required." in html, path.name
        parser = RequiredLabelCollector()
        parser.feed(html)
        for text, control_ids in parser.labels:
            if "*" not in text:
                continue
            assert control_ids, f"{path.name}: label has no associated control: {text}"
            assert all(parser.controls.get(control_id) for control_id in control_ids), (
                f"{path.name}: asterisk label must target required controls: {text}"
            )
