// Run with: node tests/notifications_browser.mjs
// Executes the notifications page in Chrome/Edge to verify role-aware navigation.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {existsSync} from "node:fs";
import {readFile, mkdtemp} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

const root = new URL("../", import.meta.url);
const executable = process.env.BROWSER_PATH || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium",
].find(existsSync);
assert.ok(executable, "Set BROWSER_PATH to an installed Chrome/Edge executable");

let role = "buyer";
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, "http://localhost").pathname;
    if (path === "/api/v1/auth/me") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({id: 2, role, status: "ACTIVE"}));
      return;
    }
    if (path === "/api/v1/notifications") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({data: [], unread_count: 0}));
      return;
    }
    const file = path === "/notifications" ? "src/web/pages/notifications.html"
      : path.startsWith("/static/") ? `src/web${path}` : null;
    if (!file) { response.writeHead(404).end(); return; }
    response.setHeader("Content-Type", file.endsWith(".js") ? "text/javascript"
      : file.endsWith(".css") ? "text/css" : "text/html; charset=utf-8");
    response.end(await readFile(new URL(file, root)));
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const profile = await mkdtemp(join(tmpdir(), "notifications221-browser-"));
const browser = spawn(executable, ["--headless=new", "--disable-gpu", "--no-first-run",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`], {windowsHide: true, stdio: ["ignore", "ignore", "pipe"]});
let browserError = "", ws;
browser.stderr.on("data", chunk => { browserError += chunk; });

const token = roleName => {
  const payload = Buffer.from(JSON.stringify({sub: "2", role: roleName})).toString("base64url");
  return `eyJhbGciOiJIUzI1NiJ9.${payload}.signature`;
};

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
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const waitFor = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.fail(expression);
  };
  await send("Page.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem('access_token', '${token("buyer")}');`,
  });
  await send("Page.navigate", {url: `http://127.0.0.1:${server.address().port}/notifications`});
  await waitFor('document.getElementById("notifications-status").textContent.includes("no notifications")');
  assert.equal(await evaluate('document.getElementById("notifications-seller-new-product-link").hidden'), true);
  assert.equal(await evaluate('document.getElementById("notifications-seller-orders-link").hidden'), true);

  role = "seller";
  await evaluate(`localStorage.setItem('access_token', '${token("seller")}'); location.reload();`);
  await waitFor('document.getElementById("notifications-status").textContent.includes("no notifications")');
  assert.equal(await evaluate('document.getElementById("notifications-seller-new-product-link").hidden'), false);
  assert.equal(await evaluate('document.getElementById("notifications-seller-orders-link").hidden'), false);
  console.log("Notifications browser checks passed: Buyer links hidden and Seller links visible.");
} finally {
  ws?.close(); browser.kill(); server.closeAllConnections(); server.close();
}
