// node tests/seller_analytics_ui.mjs: production scripts, isolated DOM/network doubles.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";
import {analyticsPayload} from "./analytics_fixtures.mjs";

const source = await readFile(new URL("../src/web/static/seller-analytics.js", import.meta.url), "utf8");
const chart = await readFile(new URL("../src/web/static/analytics-chart.js", import.meta.url), "utf8");
const html = await readFile(new URL("../src/web/pages/seller-analytics.html", import.meta.url), "utf8");
const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };

class Element {
  constructor(tag = "div") { Object.assign(this, {tagName: tag, value: "", hidden: false,
    textContent: "", children: [], handlers: {}, attributes: {}}); }
  set innerHTML(_) { throw new Error("Untrusted content must remain text"); }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(name, fn) { (this.handlers[name] ??= []).push(fn); }
  dispatch(name, event = {}) { for (const fn of this.handlers[name] ?? []) fn({preventDefault() {}, ...event}); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  focus() { this.focused = true; }
  scrollIntoView() { this.scrolled = true; }
}

function setup({accessToken = "seller", role = "seller", status = "ACTIVE", mode = "modern",
  pathname = "/seller/analytics", intercept} = {}) {
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const get = id => { assert.ok(nodes.has(id), `Missing HTML id ${id}`); return nodes.get(id); };
  get("analytics-group").value = "day"; get("analytics-limit").value = "10";
  get("analytics-chart-metric").value = "completed_revenue";
  const storage = new Map(accessToken ? [["access_token", accessToken]] : []), calls = [], navigations = [];
  const window = new Element();
  window.location = {pathname, replace: url => navigations.push(url)};
  const timers = new Map(); let timerId = 0;
  const context = vm.createContext({window, document: {getElementById: get,
    createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag)},
  localStorage: {getItem: key => storage.get(key) ?? null, removeItem: key => storage.delete(key)},
  URLSearchParams, AbortController, TypeError, SyntaxError, console,
  Date: class extends Date {
    constructor(...args) { super(...(args.length ? args : ["2026-10-30T00:15:00Z"])); }
  },
  setTimeout: fn => { const id = ++timerId; timers.set(id, fn); return id; },
  clearTimeout: id => timers.delete(id),
  fetch: async (url, options) => {
    calls.push({url, options});
    const override = await intercept?.(url, options, calls.length);
    if (override instanceof Error) throw override;
    const payload = url.endsWith("auth/me") ? {id: 7, role, status} : analyticsPayload(url, mode);
    return override || {status: 200, ok: true, json: async () => payload};
  }});
  vm.runInContext(chart, context); vm.runInContext(source, context);
  const submit = values => {
    for (const [key, value] of Object.entries(values)) get(`analytics-${key}`).value = value;
    get("analytics-filters").dispatch("submit");
  };
  return {get, calls, storage, navigations, window, timers, submit};
}

let page = setup({accessToken: null}); await settle();
assert.deepEqual(page.navigations, ["/login?return_to=%2Fseller%2Fanalytics"]);
assert.equal(page.calls.length, 0);
for (const account of [{role: "buyer"}, {status: "SUSPENDED"}]) {
  page = setup(account); await settle(); assert.equal(page.calls.length, 1);
  assert.equal(page.get("analytics-retry").hidden, true); assert.equal(page.get("analytics-report").hidden, true);
}
page = setup({intercept: () => ({status: 401, ok: false})}); await settle();
assert.equal(page.storage.size, 0); assert.equal(page.navigations.length, 1);

page = setup(); await settle();
assert.equal(page.get("analytics-report").hidden, false);
assert.equal(page.get("analytics-from").value, "2026-10-01");
assert.equal(page.get("analytics-to").value, "2026-10-30", "The default is 30 inclusive UTC dates");
assert.equal(page.get("metric-gross_order_value").textContent, "1.800.000 VND");
assert.equal(page.get("metric-cancellation_rate").textContent, "12.5%", "Use weighted API summary, never average bucket percentages");
assert.equal(page.get("analytics-chart").children[0].tagName, "svg");
assert.equal(page.get("analytics-ranking-body").children[0].children[2].textContent, "9");
const query = new URL(page.calls[1].url, "http://localhost").searchParams;
assert.equal(query.get("from_date"), query.get("from")); assert.equal(query.get("to_date"), query.get("to"));
assert.equal(query.get("group_by"), "day"); assert.equal(query.get("period"), "daily");
assert.equal(query.has("seller_id"), false);
assert.ok(page.calls.every(call => call.options.headers.Authorization === "Bearer seller"));
page.get("analytics-chart-metric").value = "cancellation_rate"; page.get("analytics-chart-metric").dispatch("change");
assert.equal(page.calls.length, 3, "Chart selection uses the applied report without refetching");
assert.equal(page.get("analytics-values-body").children[0].children[1].textContent, "50%");
page.submit({from: "2026-09-01", to: "2026-10-30", group: "month", limit: "5"}); await settle();
assert.ok(page.calls[3].url.includes("group_by=month")); assert.ok(page.calls[3].url.includes("period=monthly"));
assert.ok(page.calls[4].url.includes("limit=5"));
assert.ok(page.get("analytics-applied-range").textContent.includes("2026-09-01 to 2026-10-30"));
page.submit({limit: "20"}); await settle(); assert.ok(page.calls.at(-1).url.includes("limit=20"));

for (const values of [{from: ""}, {from: "2026-02-30"}, {from: "2026-12-01", to: "2026-01-01"}, {group: "weekly"}, {limit: "0"}]) {
  page = setup(); await settle(); page.submit(values); await settle();
  assert.equal(page.calls.length, 3, "Invalid filters do not request data");
  assert.equal(page.get("analytics-report").hidden, true);
  assert.ok(["from", "to", "group", "limit"].some(key => page.get(`analytics-${key}`).focused));
}
page = setup({mode: "legacy"}); await settle();
assert.equal(page.get("metric-completed_revenue").textContent, "1.140.000 VND");
assert.ok(page.get("completed-revenue-label").textContent.includes("legacy"));
assert.ok(page.get("analytics-date-basis").textContent.startsWith("Legacy completed-sales revenue and product rankings use completion dates."));
for (const key of ["gross_order_value", "pending_escrow_revenue", "cancellation_rate"]) assert.equal(page.get(`metric-${key}`).textContent, "Not available");
page.get("analytics-chart-metric").value = "gross_order_value"; page.get("analytics-chart-metric").dispatch("change");
assert.equal(page.get("analytics-chart").hidden, true); assert.equal(page.get("analytics-values").hidden, true);
page = setup({mode: "empty"}); await settle();
assert.equal(page.get("analytics-ranking-empty").hidden, false); assert.equal(page.get("analytics-chart-empty").hidden, false);
assert.equal(page.get("metric-cancellation_rate").textContent, "0%"); assert.equal(page.get("analytics-error").hidden, true);

let fail = true;
page = setup({intercept: url => !url.endsWith("auth/me") && fail ? {status: 503, ok: false} : undefined});
await settle(); const failedFrom = page.get("analytics-from").value;
assert.equal(page.get("analytics-error").hidden, false);
page.get("analytics-from").value = "2020-01-01"; fail = false;
page.get("analytics-retry").dispatch("click"); await settle();
assert.ok(page.get("analytics-applied-range").textContent.startsWith(failedFrom), "Retry retains the failed applied range");
assert.equal(page.get("analytics-from").value, "2020-01-01", "Unapplied filter edits are preserved");

for (const invalid of [NaN, -1, true, "100", Number.MAX_SAFE_INTEGER + 1]) {
  page = setup({intercept: url => {
    if (url.endsWith("auth/me") || url.includes("best-sellers")) return;
    const payload = analyticsPayload(url); payload.meta.gross_order_value = invalid;
    return {status: 200, ok: true, json: async () => payload};
  }}); await settle(); assert.equal(page.get("analytics-error").hidden, false);
}
page = setup({intercept: url => {
  if (!url.includes("best-sellers")) return;
  const payload = analyticsPayload(url); payload.data[0].product_name = "<img src=x onerror=bad()>";
  return {status: 200, ok: true, json: async () => payload};
}}); await settle();
assert.ok(page.get("analytics-ranking-body").children[0].children[1].textContent.includes("<img"));

const delayed = deferred(); let pendingOnce = true;
page = setup({intercept: url => {
  if (!url.endsWith("auth/me") && !url.includes("best-sellers") && pendingOnce) { pendingOnce = false; return delayed.promise; }
}}); await settle();
page.submit({from: "2026-09-01", to: "2026-09-30"}); await settle();
delayed.resolve({status: 401, ok: false}); await settle();
assert.equal(page.navigations.length, 0, "Stale 401 must not log out the current report");
assert.equal(page.get("analytics-report").hidden, false);
assert.ok(page.get("analytics-applied-range").textContent.startsWith("2026-09-01"));
page.storage.set("access_token", "other-account"); page.window.dispatch("storage", {key: "access_token"});
assert.equal(page.get("analytics-report").hidden, true, "Account switches hide private data synchronously"); await settle();
assert.equal(page.calls.at(-1).options.headers.Authorization, "Bearer other-account");
page.get("analytics-logout").dispatch("click");
assert.equal(page.get("analytics-ranking-body").children.length, 0); assert.equal(page.storage.size, 0);

const oldAccount = deferred();
page = setup({intercept: (url, options) => !url.endsWith("auth/me") && !url.includes("best-sellers")
  && options.headers.Authorization === "Bearer seller" ? oldAccount.promise : undefined}); await settle();
page.storage.set("access_token", "new-seller"); page.window.dispatch("storage", {key: "access_token"}); await settle();
oldAccount.resolve({status: 401, ok: false}); await settle();
assert.equal(page.navigations.length, 0, "Old-account rejection cannot log out the new seller");
assert.equal(page.storage.get("access_token"), "new-seller");
assert.equal(page.get("analytics-report").hidden, false);

for (const error of [new TypeError("Failed to fetch"), new SyntaxError("Invalid JSON")]) {
  page = setup({intercept: url => url.endsWith("auth/me") ? undefined : {
    status: 200, ok: true, json: async () => { throw error; },
  }}); await settle();
  assert.equal(page.get("analytics-error").hidden, false);
  assert.ok(page.get("analytics-error-message").textContent.includes("Retry analytics"));
}
page = setup({intercept: url => {
  if (url.endsWith("auth/me") || url.includes("best-sellers")) return;
  const payload = analyticsPayload(url); payload.meta.from = "1900-01-01";
  return {status: 200, ok: true, json: async () => payload};
}}); await settle(); assert.equal(page.get("analytics-error").hidden, false, "Reject data for the wrong applied range");
page = setup({intercept: url => url.endsWith("auth/me") ? undefined
  : {status: 200, ok: true, json: () => new Promise(() => {})}}); await settle();
for (const timer of [...page.timers.values()]) timer(); await settle();
assert.equal(page.get("analytics-error").hidden, false); assert.ok(page.get("analytics-error-message").textContent.includes("timed out"));
assert.equal(page.get("analytics-report").hidden, true);
page = setup({pathname: "/seller/analytics/products"}); await settle();
assert.equal(page.get("analytics-nav-ranking").attributes["aria-current"], "page");
assert.equal(page.get("analytics-nav-summary").attributes["aria-current"], undefined);
assert.equal(page.get("best-sellers-title").focused, true, "The ranking route opens the ranking after data arrives");
assert.equal(page.get("best-sellers-title").scrolled, true);
page.get("best-sellers-title").focused = false;
page.submit({limit: "5"}); await settle();
assert.equal(page.get("best-sellers-title").focused, false, "Applying filters must not steal focus again");
page = setup({accessToken: null, pathname: "/seller/analytics/products"}); await settle();
assert.deepEqual(page.navigations, ["/login?return_to=%2Fseller%2Fanalytics%2Fproducts"]);
console.log("Seller analytics DOM checks passed: access, filters, modern/legacy metrics, SVG/table, ranking, empty/error/retry, timeout, safe text and account/request races.");
