// Run: node tests/notification_badge_ui.mjs
// Exercise the production badge controller, including responses that ignore abort.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/notification-badge.js", import.meta.url), "utf8");
class Element {
  constructor() { this.children = []; this.hidden = false; this.classList = {add() {}}; }
  append(node) { this.children.push(node); }
  prepend(node) { this.children.unshift(node); }
  after() {}
  setAttribute(name, value) { this[name] = value; }
}
const response = (count, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => ({unread_count: count}),
});
const settle = async () => {
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
};
function setup({token = "buyer-token", fetchCount = () => response(3)} = {}) {
  const link = new Element(), calls = [], handlers = new Map();
  const storage = new Map(token ? [["access_token", token]] : []);
  const on = (name, callback) => handlers.set(name, [...(handlers.get(name) || []), callback]);
  const context = vm.createContext({
    document: {
      querySelectorAll: () => [link], createElement: () => new Element(),
      addEventListener: on, visibilityState: "visible",
    },
    window: {addEventListener: on},
    localStorage: {getItem: key => storage.get(key) ?? null},
    sessionStorage: {getItem: () => null},
    AbortController, setTimeout, clearTimeout,
    fetch: async (url, options) => { calls.push({url, options}); return fetchCount(options); },
  });
  vm.runInContext(source, context);
  return {link, badge: link.children[0].children[0], storage, calls,
    emit: async (name, event = {}) => {
      await Promise.all((handlers.get(name) || []).map(callback => callback(event)));
      await settle();
    }};
}

for (const count of [0, 1, 99, 100, 125]) {
  const page = setup({fetchCount: () => response(count)});
  await settle();
  assert.equal(page.badge.hidden, count === 0);
  assert.equal(page.badge.textContent, count > 99 ? "99+" : String(count || ""));
  assert.equal(page.link["aria-label"], count ? `Notifications, ${count} unread` : "Notifications");
  assert.equal(page.calls[0].options.headers.Authorization, "Bearer buyer-token");
}
let page = setup({token: null});
await settle();
assert.equal(page.calls.length, 0);
assert.equal(page.badge.hidden, true);

for (const invalid of [-1, 0.5, "3", null, Infinity]) {
  page = setup({fetchCount: () => response(invalid)});
  await settle();
  assert.equal(page.badge.hidden, true);
  assert.equal(page.link["aria-label"], "Notifications, unread count unavailable");
}

let status = 503;
page = setup({fetchCount: () => response(2, status)});
await settle();
assert.equal(page.badge.hidden, true);
status = 200;
await page.emit("focus");
assert.equal(page.badge.textContent, "2");
assert.equal(page.badge.hidden, false);

let finishOld;
const oldRequest = new Promise(resolve => { finishOld = resolve; });
page = setup({fetchCount: options => options.headers.Authorization === "Bearer buyer-token"
  ? oldRequest : response(7)});
await settle();
page.storage.set("access_token", "seller-token");
await page.emit("storage", {key: "access_token"});
assert.equal(page.badge.textContent, "7");
finishOld(response(125));
await settle();
assert.equal(page.badge.textContent, "7", "Old account results cannot replace the current badge");
page.storage.delete("access_token");
await page.emit("click");
assert.equal(page.badge.hidden, true, "Same-tab logout clears the badge");

let count = 3;
page = setup({fetchCount: () => response(count)});
await settle();
count = 2;
await page.emit("notifications:changed");
assert.equal(page.badge.textContent, "2");
count = 0;
await page.emit("storage", {key: "notifications:read"});
assert.equal(page.badge.hidden, true);

page = setup({fetchCount: () => response(0, 401)});
await settle();
assert.equal(page.badge.hidden, true);
assert.equal(page.storage.get("access_token"), "buyer-token", "The shared badge does not clear sessions");
console.log("Notification badge checks passed: boundaries, auth, stale responses, logout, retry and read events.");
