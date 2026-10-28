// Run: node tests/cart_selection_browser.mjs
// Render the actual cart page and scripts against deterministic API fixtures.
// Backend persistence/ownership is covered separately by tests/test_us12.py.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { existsSync } from "node:fs";
import { readFile, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const root = new URL("../", import.meta.url);
const browserPath = process.env.BROWSER_PATH || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
assert.ok(browserPath, "Set BROWSER_PATH to a Chromium browser executable");
const profile = await mkdtemp(join(tmpdir(), "cart119-browser-"));
const output = new URL("../docs/images/us12/", import.meta.url);
await mkdir(output, { recursive: true });
const makeItem = (id, seller, extra = {}) => ({
  cart_item_id: id, product_id: id, product_code: `CART119-${id}`,
  seller_id: seller, seller_name: `Shop ${seller}`, name: `Product ${id}`,
  quantity: 1, unit_price: 100000, price_at_add: 100000, price_changed: false,
  line_total: 100000, available_stock: 5, availability: "available", is_selected: true,
  ...extra,
});
let items = [makeItem(1, 10, {name: "Cotton shirt", variant_name: "Black / M", variant_id: 11}),
  makeItem(2, 10, {name: "Cotton shirt", variant_name: "White / M", variant_id: 12, is_selected: false}),
  makeItem(3, 20, {name: "Wireless mouse", price_at_add: 120000, price_changed: true}),
  makeItem(4, 20, {name: "Desk lamp", price_at_add: 80000, price_changed: true}),
  makeItem(5, 30, {name: "Notebook", availability: "unavailable", is_selected: false})];
const snapshot = () => ({ data: { items, supports_partial_checkout: true,
  cart_total: items.reduce((sum, item) => sum + item.line_total, 0),
  selected_total: items.filter(item => item.is_selected).reduce((sum, item) => sum + item.line_total, 0),
}});
let failNextSelection = false;
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, "http://localhost").pathname;
    if (path.startsWith("/api/v1/cart")) {
      response.setHeader("Content-Type", "application/json");
      if (request.method === "PATCH") {
        let body = "";
        for await (const chunk of request) body += chunk;
        if (failNextSelection) {
          failNextSelection = false;
          response.writeHead(409).end(JSON.stringify({error: {
            code: "ERR_CONCURRENCY_CONFLICT", message: "Cart changed. Please try again.",
          }}));
          return;
        }
        const selected = JSON.parse(body).is_selected;
        const shop = path.match(/select-shop\/(\d+)$/);
        const item = path.match(/items\/(\d+)\/select$/);
        assert.ok(shop || item, "Only selection mutations expected");
        items = items.map(row => ((shop && row.seller_id === Number(shop[1])) ||
          (item && row.cart_item_id === Number(item[1]))) && row.availability === "available"
          ? {...row, is_selected: selected} : row);
      }
      response.end(JSON.stringify(snapshot()));
      return;
    }
    const allowed = /^\/static\/[\w.-]+$/.test(path);
    const file = path === "/cart" ? "src/web/pages/cart.html" : allowed ? `src/web${path}` : null;
    if (!file) { response.writeHead(404).end(); return; }
    response.setHeader("Content-Type", file.endsWith(".css") ? "text/css" :
      file.endsWith(".js") ? "text/javascript" : file.endsWith(".svg") ? "image/svg+xml" : "text/html");
    response.end(await readFile(new URL(file, root)));
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const url = `http://127.0.0.1:${server.address().port}/cart`;
const browser = spawn(browserPath, ["--headless=new", "--disable-gpu", "--no-first-run",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`], {windowsHide: true, stdio: "ignore"});
let ws;
try {
  let debugPort;
  for (let i = 0; i < 100; i++) {
    try { debugPort = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 100)); }
  }
  assert.ok(debugPort, "Browser must start");
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
  ws = new WebSocket(targets.find(target => target.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    const task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id);
    clearTimeout(task.timeout);
    if (message.error) task.reject(new Error(message.error.message)); else task.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)); }, 10000);
    pending.set(id, {resolve, reject, timeout});
    ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send("Runtime.evaluate", {expression, returnByValue: true});
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const waitFor = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.fail(`Condition not reached: ${expression}`);
  };
  await send("Page.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: 'localStorage.setItem("access_token", "fixture-buyer");',
  });
  for (const width of [390, 768, 1280]) {
    await send("Emulation.setDeviceMetricsOverride", {width, height: 1000, deviceScaleFactor: 1, mobile: false});
    await send("Page.navigate", {url});
    await waitFor('document.getElementById("cart-content")?.hidden === false');
    assert.equal(await evaluate('document.querySelectorAll(".cart-shop").length'), 3);
    assert.equal(await evaluate('document.getElementById("select-shop-10").indeterminate'), true);
    assert.equal(await evaluate('document.getElementById("select-shop-30").disabled'), true);
    assert.equal(await evaluate('document.querySelectorAll(".cart-shop__unavailable .cart-line").length'), 1);
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true, `Overflow at ${width}px`);
    const warnings = await evaluate('document.getElementById("cart-lines").textContent');
    assert.ok(warnings.includes("when added") && warnings.includes("now."));
    assert.equal(await evaluate('document.querySelector("label:has(#select-item-1)").textContent'), "Select Cotton shirt · Black / M");
    const screenshot = await send("Page.captureScreenshot", {format: "png", captureBeyondViewport: true});
    await writeFile(new URL(`cart-selection-${width}.png`, output), Buffer.from(screenshot.data, "base64"));
  }
  const change = id => evaluate(`document.getElementById(${JSON.stringify(id)}).focus(); document.getElementById(${JSON.stringify(id)}).click()`);
  await evaluate('document.getElementById("select-item-2").focus()');
  await send("Input.dispatchKeyEvent", {type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32});
  await send("Input.dispatchKeyEvent", {type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32});
  await waitFor('!document.getElementById("select-item-2").disabled');
  assert.equal(items[1].is_selected, true);
  assert.equal(await evaluate('document.getElementById("select-shop-10").indeterminate'), false);
  assert.equal(await evaluate('document.activeElement.id'), "select-item-2");
  assert.equal(await evaluate('document.getElementById("cart-total").textContent'),
    new Intl.NumberFormat("vi-VN", {style: "currency", currency: "VND"}).format(400000));
  failNextSelection = true;
  await change("select-shop-10");
  await waitFor('document.getElementById("cart-change-error").hidden === false');
  assert.equal(await evaluate('document.activeElement.id'), "select-shop-10");
  assert.equal(await evaluate('document.getElementById("select-shop-10").checked'), true);
  await change("select-shop-10");
  await waitFor('!document.getElementById("select-shop-10").disabled');
  assert.ok(items.filter(item => item.seller_id === 10).every(item => !item.is_selected));
  assert.equal(await evaluate('document.getElementById("cart-total").textContent'),
    new Intl.NumberFormat("vi-VN", {style: "currency", currency: "VND"}).format(200000));
  await change("select-shop-20");
  await waitFor('!document.getElementById("select-shop-20").disabled');
  assert.equal(await evaluate('document.getElementById("checkout-button").disabled'), true);
  await send("Page.reload");
  await waitFor('document.getElementById("cart-content")?.hidden === false');
  assert.equal(await evaluate('document.getElementById("select-shop-10").checked'), false);
  assert.equal(await evaluate('document.getElementById("checkout-button").disabled'), true);
  console.log("PASS: grouped selection, variants, price warnings, unavailable rows, focus recovery, reload and no overflow at 390/768/1280px.");
  console.log("Screenshots use deterministic API fixtures; backend persistence has separate API tests.");
} finally {
  ws?.close();
  browser.kill();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
