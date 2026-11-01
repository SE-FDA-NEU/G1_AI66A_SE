# ruff: noqa: E501  (the embedded in-page JavaScript keeps readable long lines)
"""Issue #156 (parent #114): responsive, keyboard and contrast audit in a real browser.

Every page is served by the production FastAPI handlers on an isolated SQLite file; only
the transport is intercepted. Data is deliberately awkward (very long names, several
shops, several items) because short demo data hides overflow. Expected limits come from
WCAG 2.2 AA (contrast 4.5:1 / 3:1 large text, focus visible, 24 px target minimum) and
from the plan's rule that no page may scroll horizontally at 320-1440 CSS px.
"""

import os
from urllib.parse import urlsplit

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.testclient import TestClient

import src.models  # noqa: F401
from src.auth import create_access_token, hash_password
from src.database import get_session
from src.main import create_app
from src.models.cart_item import CartItem
from src.models.notification import Notification
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from tests.cart_db import BUYER_ID, SELLER_ID, add_product, enable_foreign_keys

sync_api = pytest.importorskip("playwright.sync_api")
ORIGIN = "http://responsive-audit.test"
ADMIN_ID = 4
VIEWPORTS = [320, 375, 390, 768, 1024, 1440]
LONG_NAME = "Máy xay sinh tố đa năng công suất lớn phiên bản đặc biệt " * 3
LONG_ADDRESS = "Số 1234, ngõ 56/78/90 đường Nguyễn Văn Cừ kéo dài, phường Ngọc Lâm, Long Biên"
TARGET_MIN = 24  # WCAG 2.2 SC 2.5.8 minimum target size in CSS px
# Pages whose interactive content depends on data an audit cannot fabricate honestly are
# still loaded, but only checked for overflow, labels, focus and contrast.
PAGES = [
    ("guest", "/products"),
    ("guest", "/products/AUDIT-1"),
    ("guest", "/login"),
    ("buyer", "/cart"),
    ("buyer", "/checkout"),
    ("buyer", "/orders"),
    ("buyer", "/notifications"),
    ("seller", "/seller/orders"),
    ("seller", "/seller/products"),
    ("seller", "/seller/products/new"),
    ("seller", "/seller/vouchers"),
    ("seller", "/seller/analytics"),
    ("admin", "/admin"),
]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('audit') / 'audit.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(id=SELLER_ID, name="Seller " + "Long " * 8, email="s@t.local", role="seller",
                     password_hash=hash_password("x")),
                User(id=BUYER_ID, name="Buyer", email="b@t.local", role="buyer",
                     password_hash=hash_password("x")),
                User(id=ADMIN_ID, name="Admin", email="a@t.local", role="admin",
                     password_hash=hash_password("x")),
            ]
        )
        session.commit()
    first = add_product(engine, "AUDIT-1", price=1_234_567_000, stock=7)
    for index in range(2, 9):
        add_product(engine, f"AUDIT-{index}", price=90_000 * index, stock=3)
    with Session(engine) as session:
        for product in session.exec(select(Product)):
            product.name = f"{LONG_NAME} {product.code}"
            session.add(product)
        session.add(CartItem(buyer_id=BUYER_ID, product_id=first, quantity=2))
        order = Order(
            buyer_id=BUYER_ID,
            total_amount=2_469_134_000,
            status="PENDING",
            recipient_name="Nguyễn Văn " + "Rất Dài " * 6,
            delivery_address=LONG_ADDRESS,
            phone_number="0912345678",
        )
        session.add(order)
        session.flush()
        shop = SellerOrder(
            order_id=order.id, seller_id=SELLER_ID, status="PENDING",
            subtotal=2_469_134_000, total_amount=2_469_134_000,
        )
        session.add(shop)
        session.flush()
        session.add(
            OrderItem(
                seller_order_id=shop.id, product_id=first, quantity=2, unit_price=1_234_567_000
            )
        )
        for number in range(6):
            session.add(
                Notification(
                    recipient_user_id=BUYER_ID,
                    order_id=order.id,
                    event_key=f"audit:{number}",
                    message=("Đơn hàng cập nhật " + LONG_ADDRESS) * 2,
                    target_path=f"/orders/{order.id}",
                )
            )
        session.commit()
        tokens = {
            "guest": None,
            "buyer": create_access_token(session.get(User, BUYER_ID)),
            "seller": create_access_token(session.get(User, SELLER_ID)),
            "admin": create_access_token(session.get(User, ADMIN_ID)),
        }
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, tokens
    engine.dispose()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        executable = os.environ.get("BROWSER_PATH")
        try:
            value = (
                playwright.chromium.launch(executable_path=executable)
                if executable
                else playwright.chromium.launch()
            )
        except sync_api.Error:
            value = playwright.chromium.launch(channel="chrome")
        yield value
        value.close()


CHECKS_JS = """
() => {
  const problems = [];
  const visible = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
      && el.closest('[hidden], [aria-hidden="true"]') === null;
  };
  const describe = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
    + (el.className && typeof el.className === 'string'
       ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const root = document.documentElement;
  if (root.scrollWidth > innerWidth) {
    const wide = [...document.querySelectorAll('body *')].filter(
      el => visible(el) && el.getBoundingClientRect().right > innerWidth + 1
        && !el.closest('[data-scroll-region], .table-scroll, .table-wrap'))
      .slice(0, 4).map(describe);
    problems.push('overflow: page ' + root.scrollWidth + ' > ' + innerWidth + ' by ' + wide.join(', '));
  }
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (!visible(el) || ['hidden', 'submit', 'button'].includes(el.type)) continue;
    const named = (el.labels && el.labels.length) || el.getAttribute('aria-label')
      || el.getAttribute('aria-labelledby') || el.title;
    if (!named) problems.push('unlabeled control: ' + describe(el));
  }
  for (const el of document.querySelectorAll('button, input[type=checkbox], input[type=radio]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < %(min)d || r.height < %(min)d) {
      const label = el.labels && el.labels[0] ? el.labels[0].getBoundingClientRect() : r;
      if (Math.max(r.width, label.width) < %(min)d || Math.max(r.height, label.height) < %(min)d)
        problems.push('small target ' + Math.round(r.width) + 'x' + Math.round(r.height)
                      + ': ' + describe(el));
    }
  }
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(',').map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const backdrop = el => { let layers = [];
    for (let n = el; n; n = n.parentElement) { const s = getComputedStyle(n);
      if (s.backgroundImage !== 'none') return null;
      const c = parse(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a === 1) break; } }
    let base = {r: 255, g: 255, b: 255};
    for (const c of layers.reverse()) base = {r: c.r * c.a + base.r * (1 - c.a),
      g: c.g * c.a + base.g * (1 - c.a), b: c.b * c.a + base.b * (1 - c.a)};
    return base; };
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el) || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    if (el.disabled) continue;
    const s = getComputedStyle(el), fg = parse(s.color), bg = backdrop(el);
    if (!fg || !bg) continue;
    const mixed = {r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a),
                   b: fg.b * fg.a + bg.b * (1 - fg.a)};
    const [hi, lo] = [lum(mixed), lum(bg)].sort((a, b) => b - a);
    const ratio = (hi + 0.05) / (lo + 0.05);
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    const key = describe(el) + ratio.toFixed(2);
    if (ratio < need && !seen.has(key)) {
      seen.add(key);
      problems.push('contrast ' + ratio.toFixed(2) + ' < ' + need + ': ' + describe(el)
                    + ' "' + el.textContent.trim().slice(0, 30) + '"');
    }
  }
  return problems;
}
""" % {"min": TARGET_MIN}

FOCUS_JS = """
() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el);
  const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
  const shadow = s.boxShadow !== 'none';
  const r = el.getBoundingClientRect();
  return {tag: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''), visibleRing: outline || shadow,
          onScreen: r.width > 0 && r.height > 0};
}
"""


def open_page(browser, client, tokens, role, path, width):
    context = browser.new_context(viewport={"width": width, "height": 900}, locale="vi-VN")
    if tokens[role]:
        context.add_init_script(f"localStorage.setItem('access_token', '{tokens[role]}')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_default_timeout(8000)

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != urlsplit(ORIGIN).netloc:
            route.abort()
            return
        response = client.request(
            route.request.method,
            url.path + (f"?{url.query}" if url.query else ""),
            headers={
                k: v for k, v in route.request.headers.items()
                if k.lower() in {"authorization", "content-type"}
            },
            content=route.request.post_data,
        )
        route.fulfill(
            status=response.status_code,
            body=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    page.route("**/*", handle)
    page.goto(ORIGIN + path)
    page.wait_for_load_state("networkidle")
    return context, page, errors


@pytest.mark.parametrize("width", VIEWPORTS)
@pytest.mark.parametrize(("role", "path"), PAGES, ids=[p for _, p in PAGES])
def test_page_is_usable_at_every_viewport(browser, world, role, path, width):
    client, tokens = world
    context, page, errors = open_page(browser, client, tokens, role, path, width)
    try:
        problems = page.evaluate(CHECKS_JS)
        for _ in range(6):  # keyboard: each Tab stop must be on screen and show a focus ring
            page.keyboard.press("Tab")
            focus = page.evaluate(FOCUS_JS)
            if focus is None:
                break
            if not focus["onScreen"] or not focus["visibleRing"]:
                problems.append(f"focus not visible on {focus['tag']}")
    finally:
        context.close()

    assert errors == []
    assert problems == [], f"{path} @ {width}px:\n" + "\n".join(problems)
