"""Optional Chromium acceptance run: requires Playwright and an installed .venv.

Run `python tests/browser_us13.py`; all demo data lives in a temporary SQLite file.
"""

import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
images = root / "docs/images/us13"
images.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="us13-demo-") as directory:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{directory}/demo.db", "DEBUG": "false"}
    subprocess.run(
        [str(root / ".venv/bin/python"), "-m", "src.database"],
        cwd=root,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [str(root / ".venv/bin/python"), "-m", "src.database"],
        cwd=root,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [str(root / ".venv/bin/python"), "-m", "src.seed", "--demo"],
        cwd=root,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with open("/tmp/us13-server.log", "w") as log:
        server = subprocess.Popen(
            [
                str(root / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "src.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8135",
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen("http://127.0.0.1:8135/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 360, "height": 800})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto("http://127.0.0.1:8135/login?return_to=%2Fcheckout")
                page.locator("#email").fill("user@example.com")
                page.locator("#password").fill("password")
                page.get_by_role("button", name="Log in", exact=True).click()
                page.wait_for_url("**/checkout")
                expect(page.locator("#address-status")).to_contain_text("No saved addresses")

                def create(name, street):
                    page.locator("#add-address").click()
                    for field, value in dict(
                        recipient_name=name,
                        phone_number="0912345678",
                        province="Hà Nội",
                        district="Đống Đa",
                        ward="Láng Thượng",
                        detailed_address=street,
                    ).items():
                        page.locator(f"#address-{field}").fill(value)
                    page.get_by_role("button", name="Save address", exact=True).click()
                    expect(page.locator("#address-form")).to_be_hidden()

                create("Nguyễn Minh", "12 Phố Chùa Láng")
                create("Buyer office", "24 Nguyễn Trãi")
                expect(page.locator("#address-list article")).to_have_count(2)
                page.locator("#address-list article").nth(1).get_by_role(
                    "button", name="Set default"
                ).click()
                expect(page.locator("#address-list article").first).to_contain_text("Buyer office")
                page.reload()
                expect(page.locator("#address-choice")).to_have_value("2")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(images / "mobile-address-book.png"), full_page=True)
                # Client-visible backend validation and focus.
                page.locator("#address-list article").first.get_by_role(
                    "button", name="Edit", exact=True
                ).click()
                page.locator("#address-phone_number").fill("123")
                page.get_by_role("button", name="Save address", exact=True).click()
                expect(page.locator("#address-phone_number")).to_have_attribute(
                    "aria-invalid", "true"
                )
                expect(page.locator("#address-phone_number")).to_be_focused()
                page.screenshot(path=str(images / "mobile-field-error.png"), full_page=True)
                page.locator("#cancel-address").click()
                # Leave a second product unselected, then buy only the original line.
                auth = {
                    "Authorization": "Bearer "
                    + page.evaluate("localStorage.getItem('access_token')")
                }
                base = "http://127.0.0.1:8135"
                added = page.request.post(
                    base + "/api/v1/cart/items",
                    headers=auth,
                    data={"product_code": "P-DEMO-PENDING", "quantity": 1},
                )
                assert added.ok
                extra = next(
                    row
                    for row in added.json()["data"]["items"]
                    if row["product_code"] == "P-DEMO-PENDING"
                )
                deselected = page.request.patch(
                    base + f"/api/v1/cart/items/{extra['cart_item_id']}/select",
                    headers=auth,
                    data={"is_selected": False},
                )
                assert deselected.ok
                page.reload()
                expect(page.locator("#address-choice")).to_have_value("2")
                expect(page.locator("#summary")).not_to_contain_text("Demo pending item")
                # Buy using non-default original address.
                page.locator("#address-choice").select_option("1")
                with page.expect_request("**/api/v1/orders") as placed:
                    page.locator("#confirm").click()
                page.wait_for_url("**/checkout/confirmation/*")
                receipt_url = page.url
                expect(page.locator("#receipt")).to_contain_text("Nguyễn Minh")
                receipt_before = page.locator("#receipt").inner_text()
                remaining = page.request.get(base + "/api/v1/cart", headers=auth).json()["data"][
                    "items"
                ]
                assert len(remaining) == 1 and remaining[0]["product_code"] == "P-DEMO-PENDING"
                assert "Nguyễn Minh" in receipt_before and "12 Phố Chùa Láng" in receipt_before
                assert json.loads(placed.value.post_data) == {"address_id": 1, "address_version": 2}
                page.goto("http://127.0.0.1:8135/checkout")
                expect(page.locator("#address-list article")).to_have_count(2)
                card = page.locator("#address-list article").filter(has_text="Nguyễn Minh")
                card.get_by_role("button", name="Edit", exact=True).click()
                page.locator("#address-recipient_name").fill("Changed recipient")
                page.locator("#address-detailed_address").fill("Changed street")
                page.get_by_role("button", name="Save address", exact=True).click()
                expect(page.locator("#address-form")).to_be_hidden()
                card = page.locator("#address-list article").filter(has_text="Changed recipient")
                card.get_by_role("button", name="Delete", exact=True).click()
                page.locator("#cancel-delete").click()
                expect(card).to_be_visible()
                card.get_by_role("button", name="Delete", exact=True).click()
                page.locator("#confirm-delete").click()
                expect(page.locator("#address-list article")).to_have_count(1)
                page.goto(receipt_url)
                expect(page.locator("#receipt")).to_contain_text("Nguyễn Minh")
                assert page.locator("#receipt").inner_text() == receipt_before
                page.screenshot(path=str(images / "snapshot-after-delete.png"), full_page=True)
                # Lose the response after the server commits, delete the source, then reload/retry.
                add = page.request.post(
                    base + "/api/v1/cart/items",
                    headers=auth,
                    data={"product_code": "P-DEMO-CART", "quantity": 1},
                )
                assert add.ok
                page.goto(base + "/checkout")
                expect(page.locator("#address-choice")).to_have_value("2")
                committed = {}

                def lose_response(route):
                    response = route.fetch()
                    assert response.status == 201
                    committed.update(response.json()["data"])
                    route.abort("failed")

                page.route("**/api/v1/orders", lose_response)
                page.locator("#confirm").click()
                expect(page.locator("#retry")).to_be_visible()
                expect(page.locator("#address-choice")).to_be_disabled()
                assert committed["recipient_name"] == "Buyer office"
                assert page.request.delete(base + "/api/v1/addresses/2", headers=auth).status == 204
                page.unroute("**/api/v1/orders")
                page.reload()
                expect(page.locator("#retry")).to_be_visible()
                page.locator("#retry").click()
                page.wait_for_url(f"**/checkout/confirmation/{committed['id']}")
                expect(page.locator("#receipt")).to_contain_text("Buyer office")
                page.screenshot(path=str(images / "replay-after-source-delete.png"), full_page=True)
                # A second buyer sees no address from A, even with an empty cart.
                page.goto("http://127.0.0.1:8135/login?return_to=%2Fcheckout")
                page.locator("#email").fill("demo.buyer@marketplace.local")
                page.locator("#password").fill("password")
                page.get_by_role("button", name="Log in", exact=True).click()
                page.wait_for_url("**/checkout")
                expect(page.locator("#address-status")).to_contain_text("No saved addresses")
                expect(page.locator("#checkout-form")).to_be_hidden()
                create("Buyer B", "Only B street")
                expect(page.locator("#address-list article")).to_have_count(1)
                expect(page.locator("#address-list")).not_to_contain_text("Buyer office")
                assert not errors, errors
                browser.close()
                print(
                    "Browser checks passed: 360px, CRUD/default/reload, inline error/focus, "
                    "non-default/partial checkout, edit/delete snapshot, "
                    "lost-response reload/retry after source deletion, "
                    "two-account isolation and empty-cart management."
                )
        finally:
            server.terminate()
            server.wait(timeout=10)
