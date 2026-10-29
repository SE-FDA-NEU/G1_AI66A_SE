// node tests/seller_analytics_browser.mjs (Node 22+, installed Chrome/Edge).
// Deterministic API fixtures verify the production page, script, native DOM and layout.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {existsSync} from "node:fs";
import {readFile, mkdir, mkdtemp, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {analyticsPayload} from "./analytics_fixtures.mjs";

const root = new URL("../", import.meta.url);
const executable = process.env.BROWSER_PATH || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium",
].find(existsSync);
assert.ok(executable, "Set BROWSER_PATH to an installed Chrome/Edge executable");
const profile = await mkdtemp(join(tmpdir(), "analytics143-browser-"));
const output = new URL("../docs/images/us18/", import.meta.url);
await mkdir(output, {recursive: true});
let mode = "modern", failed = false, role = "seller";
const requests = [];
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, "http://localhost").pathname;
    if (path.startsWith("/api/")) {
      requests.push(request.url);
      response.setHeader("Content-Type", "application/json");
      if (path.endsWith("auth/me")) { response.end(JSON.stringify({id: 7, role, status: "ACTIVE"})); return; }
      if (failed) { response.writeHead(503).end(JSON.stringify({error: {message: "Unavailable"}})); return; }
      response.end(JSON.stringify(analyticsPayload(request.url, mode))); return;
    }
    const file = path.startsWith("/seller/analytics") ? "src/web/pages/seller-analytics.html"
      : /^\/static\/[\w.-]+$/.test(path) ? `src/web${path}` : null;
    if (!file) { response.writeHead(404).end(); return; }
    response.setHeader("Content-Type", file.endsWith(".js") ? "text/javascript"
      : file.endsWith(".css") ? "text/css" : "text/html; charset=utf-8");
    response.end(await readFile(new URL(file, root)));
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = spawn(executable, ["--headless=new", "--disable-gpu", "--no-first-run",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`], {windowsHide: true, stdio: ["ignore", "ignore", "pipe"]});
let browserError = "", ws;
browser.stderr.on("data", chunk => { browserError += chunk; });
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 100)); }
  }
  assert.ok(port, browserError.slice(-1500));
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(targets.find(target => target.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = event => {
    const message = JSON.parse(event.data), task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id); clearTimeout(task.timer);
    message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id;
    const timer = setTimeout(() => { pending.delete(next); reject(new Error(method)); }, 10000);
    pending.set(next, {resolve, reject, timer}); ws.send(JSON.stringify({id: next, method, params}));
  });
  const evaluate = async expression => {
    const result = await send("Runtime.evaluate", {expression, returnByValue: true});
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result.value;
  };
  const waitFor = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.fail(expression);
  };
  const viewport = (width, height = 1000) => send("Emulation.setDeviceMetricsOverride", {width, height, deviceScaleFactor: 1, mobile: false});
  const screenshot = async (name, width) => {
    const height = await evaluate("document.documentElement.scrollHeight");
    await viewport(width, height + 50); await evaluate("window.scrollTo(0, 0)");
    const shot = await send("Page.captureScreenshot", {format: "png", captureBeyondViewport: true});
    await writeFile(new URL(name, output), Buffer.from(shot.data, "base64")); await viewport(width);
  };
  await send("Page.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", {source: "localStorage.setItem('access_token', 'fixture-seller');"});
  for (const width of [390, 768, 1280]) {
    await viewport(width); await send("Page.navigate", {url: `${base}/seller/analytics`});
    await waitFor('document.getElementById("analytics-status").textContent.startsWith("Analytics loaded")');
    // Fixed screenshot range keeps evidence deterministic while the page defaults to UTC today.
    await evaluate('document.getElementById("analytics-from").value = "2026-10-01"; document.getElementById("analytics-to").value = "2026-10-30"; document.getElementById("analytics-filters").requestSubmit()');
    await waitFor('!document.getElementById("analytics-report").hidden && document.getElementById("analytics-applied-range").textContent.startsWith("2026-10-01")');
    assert.equal(await evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), true, `No page overflow at ${width}`);
    assert.equal(await evaluate('document.getElementById("metric-cancellation_rate").textContent'), "12.5%");
    assert.equal(await evaluate('document.querySelector("#analytics-chart svg").getAttribute("role")'), "img");
    assert.equal(await evaluate('document.querySelector("#analytics-ranking-body tr").children[2].textContent'), "9");
    assert.equal(await evaluate('document.getElementById("analytics-from").labels.length'), 1);
    await screenshot(`analytics-${width}.png`, width);
  }
  await viewport(390);
  const count = requests.length;
  await evaluate('document.getElementById("analytics-from").value = "2026-12-31"; document.getElementById("analytics-to").value = "2026-01-01"; document.getElementById("analytics-filters").requestSubmit()');
  await waitFor('document.activeElement.id === "analytics-to"');
  assert.equal(requests.length, count);
  await screenshot("analytics-validation-390.png", 390);
  await evaluate('document.getElementById("analytics-from").value = "2026-09-01"; document.getElementById("analytics-to").value = "2026-10-30"; document.getElementById("analytics-group").value = "month"; document.getElementById("analytics-limit").value = "5"; document.getElementById("analytics-filters").requestSubmit()');
  await waitFor('document.getElementById("analytics-status").textContent.startsWith("Analytics loaded")');
  assert.ok(requests.some(url => url.includes("group_by=month") && url.includes("period=monthly")));
  await evaluate('document.getElementById("analytics-chart-metric").value = "cancellation_rate"; document.getElementById("analytics-chart-metric").dispatchEvent(new Event("change")); document.getElementById("analytics-values").open = true');
  assert.equal(await evaluate('document.querySelector("#analytics-values-body tr").children[1].textContent'), "50%");
  failed = true; await evaluate('document.getElementById("analytics-filters").requestSubmit()');
  await waitFor('!document.getElementById("analytics-error").hidden');
  assert.equal(await evaluate('document.getElementById("analytics-from").value'), "2026-09-01");
  failed = false; await evaluate('document.getElementById("analytics-retry").click()');
  await waitFor('!document.getElementById("analytics-report").hidden');
  mode = "empty"; await evaluate('document.getElementById("analytics-filters").requestSubmit()');
  await waitFor('!document.getElementById("analytics-ranking-empty").hidden');
  assert.equal(await evaluate('document.getElementById("analytics-chart-empty").hidden'), false);
  await screenshot("analytics-empty-390.png", 390);
  mode = "legacy"; await send("Page.reload");
  await waitFor('!document.getElementById("analytics-report").hidden');
  assert.equal(await evaluate('document.getElementById("metric-gross_order_value").textContent'), "Not available");
  assert.equal(await evaluate('document.getElementById("analytics-compatibility").hidden'), false);
  assert.ok((await evaluate('document.getElementById("analytics-date-basis").textContent')).startsWith("Legacy completed-sales revenue and product rankings use completion dates."));
  await screenshot("analytics-legacy-390.png", 390);
  mode = "modern"; await send("Page.navigate", {url: `${base}/seller/analytics/products`});
  await waitFor('document.activeElement.id === "best-sellers-title"');
  assert.equal(await evaluate('document.querySelector("[aria-current=page]").id'), "analytics-nav-ranking");
  assert.equal(await evaluate('document.getElementById("analytics-report").hidden'), false);
  role = "buyer"; const beforeDenied = requests.length; await send("Page.reload");
  await waitFor('!document.getElementById("analytics-error").hidden');
  assert.equal(requests.length, beforeDenied + 1, "Buyer triggers identity check only");
  assert.equal(await evaluate('document.getElementById("analytics-report").hidden'), true);
  console.log("Native seller analytics checks passed: Chrome/Edge, 390/768/1280px, SVG/table, weighted metric, month/top filters, validation focus, retry, empty, legacy and buyer denial.");
} finally {
  ws?.close(); browser.kill(); server.closeAllConnections(); server.close();
}
