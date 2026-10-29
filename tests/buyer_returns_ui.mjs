// Run the production buyer return controller against isolated DOM/network doubles.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/buyer-returns.js", import.meta.url), "utf8");
class Element {
  constructor(tag = "div") {
    Object.assign(this, {tagName: tag.toUpperCase(), hidden: true, disabled: false,
      value: "", textContent: "", children: [], handlers: {}, attributes: {}});
  }
  set innerHTML(_) { throw new Error("Return data must not become HTML"); }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  async dispatch(name) {
    await Promise.all((this.handlers[name] || []).map(fn => fn({preventDefault() {}})));
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { if (!this.disabled) this.focused = true; }
  append(...nodes) {
    this.children.push(...nodes);
    if (this.tagName === "SELECT" && !this.value && nodes.length) this.value = nodes[0].value;
  }
  replaceChildren(...nodes) { this.children = []; this.value = ""; this.append(...nodes); }
}
const order = {id: 10, sub_orders: [{id: 21, status: "DELIVERED"}, {id: 22, status: "SHIPPED"}],
  items: [{seller_order_id: 21, product_name: "Cotton shirt", quantity: 2}]};
const request = {id: 31, order_id: 10, seller_order_id: 21, status: "PENDING",
  reason: "Damaged parcel", evidence: "Photo reference", created_at: "2026-10-29T10:00:00Z",
  seller_order_status: "RETURN_REQUESTED", payment_status: "PAID", escrow_status: "PAUSED"};
const settle = async () => { for (let n = 0; n < 12; n++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };

function setup({rows = [], role = "buyer", listFailures = 0, post = null, identity = null,
  status = 201, fields = null} = {}) {
  const nodes = new Map(), calls = [], timers = new Map(), windowEvents = {}, navigations = [], submitted = [];
  const storage = new Map([["access_token", "buyer-token"]]);
  let timerId = 0, remainingFailures = listFailures, currentRows = rows, receipt = structuredClone(order);
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element(id.includes("select") ? "select" : "div"));
    return nodes.get(id);
  };
  const response = (payload, code = 200) => ({ok: code >= 200 && code < 300, status: code, json: async () => payload});
  const document = {getElementById: get, createElement: tag => new Element(tag)};
  const fetch = async (url, options = {}) => {
    calls.push({url, options});
    if (url.endsWith("/auth/me")) return identity ? identity.promise : response({id: 2, role});
    if (options.method === "POST") {
      if (post) return post.promise;
      if (status !== 201) return response({error: {message: "Rejected", fields}}, status);
      currentRows = [request];
      return response({data: request}, 201);
    }
    if (url.endsWith("/returns")) {
      if (remainingFailures-- > 0) return response({error: {message: "Unavailable"}}, 503);
      return response({data: currentRows});
    }
    return response({data: receipt});
  };
  const window = {document, fetch, location: {pathname: "/orders/10", replace: url => navigations.push(url)},
    addEventListener: (name, handler) => { windowEvents[name] = handler; }};
  const context = vm.createContext({window, localStorage: {getItem: key => storage.get(key), removeItem: key => storage.delete(key)},
    AbortController, console, setTimeout: fn => { timers.set(++timerId, fn); return timerId; }, clearTimeout: id => timers.delete(id)});
  vm.runInContext(source, context);
  const controller = window.BuyerReturns.create({document, fetch, getToken: () => storage.get("access_token") || storage.get("token"),
    onSubmitted: id => submitted.push(id)});
  const fill = async () => {
    await get("return-request-action").dispatch("click");
    get("return-reason-input").value = "Damaged parcel";
    get("return-evidence-input").value = "Photo reference";
  };
  const text = node => node.textContent + node.children.map(text).join(" ");
  return {controller, get, calls, storage, timers, windowEvents, navigations, submitted, response, fill, text,
    setRows: rows => { currentRows = rows; }, setReceipt: value => { receipt = value; }};
}

let page = setup();
await page.controller.update(order);
assert.equal(page.get("return-request-action").hidden, false);
assert.equal(page.get("buyer-return-form").hidden, true);
assert.deepEqual(page.get("return-seller-order-select").children.map(row => row.value), ["21"]);
await page.fill();
assert.equal(page.get("buyer-return-form").hidden, false);
assert.equal(page.get("return-request-action").hidden, true);
await page.get("return-request-action").dispatch("click");
assert.equal(page.get("return-reason-input").value, "Damaged parcel", "Reopening an open form cannot erase a draft");

// Drafts remain attached to their seller order when the selector changes.
page = setup(); await page.controller.update({...order, sub_orders: order.sub_orders.map(row => ({...row, status: "DELIVERED"}))});
await page.fill();
page.get("return-seller-order-select").value = "22";
await page.get("return-seller-order-select").dispatch("change");
assert.equal(page.get("return-reason-input").value, "");
page.get("return-reason-input").value = "Wrong size";
page.get("return-seller-order-select").value = "21";
await page.get("return-seller-order-select").dispatch("change");
assert.equal(page.get("return-reason-input").value, "Damaged parcel");

// Boundaries are checked before mutation; trimming and field focus are explicit.
for (const [field, value] of [["reason", "  "], ["reason", "ab"], ["reason", "x".repeat(501)],
  ["evidence", "ab"], ["evidence", "x".repeat(2001)]]) {
  page = setup(); await page.controller.update(order); await page.fill();
  page.get(`return-${field}-input`).value = value;
  await page.get("buyer-return-form").dispatch("submit");
  assert.equal(page.calls.filter(row => row.options.method === "POST").length, 0);
  assert.equal(page.get(`return-${field}-input`).attributes["aria-invalid"], "true");
  assert.equal(page.get(`return-${field}-input`).focused, true);
}
for (const [reason, evidence] of [["abc", "def"], ["x".repeat(500), "x".repeat(2000)]]) {
  page = setup(); await page.controller.update(order); await page.fill();
  page.get("return-reason-input").value = ` ${reason} `;
  page.get("return-evidence-input").value = evidence;
  await page.get("buyer-return-form").dispatch("submit");
  const posted = page.calls.find(row => row.options.method === "POST");
  assert.deepEqual(JSON.parse(posted.options.body), {seller_order_id: 21, reason, evidence});
  assert.equal(page.get("buyer-return-form").hidden, true);
  assert.ok(page.get("return-feedback").textContent.includes("#31 submitted"));
  assert.ok(page.text(page.get("return-requests-list")).includes("Pending review"));
  assert.deepEqual(page.submitted, [10]);
  await page.controller.update({...order, sub_orders: [{id: 21, status: "RETURN_REQUESTED"}]});
  assert.ok(page.get("return-feedback").textContent.includes("#31 submitted"), "Refresh preserves confirmation");
}

// A pending mutation is sent once, controls lock, and cancel cannot hide it.
const slowPost = deferred();
page = setup({post: slowPost}); await page.controller.update(order); await page.fill();
const posting = page.get("buyer-return-form").dispatch("submit");
await settle();
await page.get("buyer-return-form").dispatch("submit");
await page.get("return-cancel").dispatch("click");
assert.equal(page.calls.filter(row => row.options.method === "POST").length, 1);
assert.equal(page.get("btn-submit-return").disabled, true);
assert.equal(page.get("buyer-return-form").hidden, false);
slowPost.resolve(page.response({data: request}, 201)); await posting;
assert.equal(page.get("btn-submit-return").disabled, false);

// Validation failures retain input, end progress and can be cancelled/reopened.
page = setup({status: 422, fields: {evidence: ["Provide evidence."]}});
await page.controller.update(order); await page.fill();
await page.get("buyer-return-form").dispatch("submit");
assert.equal(page.get("return-evidence-input").value, "Photo reference");
assert.equal(page.get("return-evidence-error").textContent, "Provide evidence.");
assert.equal(page.get("return-evidence-input").focused, true);
assert.equal(page.get("btn-submit-return").disabled, false);
assert.ok(!page.get("return-feedback").textContent.includes("Submitting"));
await page.get("return-cancel").dispatch("click");
await page.get("return-request-action").dispatch("click");
assert.equal(page.get("return-reason-input").value, "Damaged parcel");

// Read errors fail closed, with Retry; sellers/guests cannot open the buyer form.
page = setup({listFailures: 1}); await page.controller.update(order);
assert.equal(page.get("return-retry").hidden, false);
assert.equal(page.get("return-request-action").hidden, true);
await page.get("return-retry").dispatch("click"); await settle();
assert.equal(page.get("return-request-action").hidden, false);
page = setup({role: "seller"}); await page.controller.update(order);
assert.equal(page.get("buyer-return-form-card").hidden, true);
page = setup(); page.storage.clear(); await page.controller.update(order);
assert.equal(page.calls.length, 0);

// A timed-out write may already exist: explicit Retry reconciles, never retries POST.
page = setup({post: deferred()}); await page.controller.update(order); await page.fill();
const timedOut = page.get("buyer-return-form").dispatch("submit"); await settle();
for (const timer of [...page.timers.values()]) timer();
await timedOut;
assert.equal(page.get("btn-submit-return").disabled, true);
assert.equal(page.get("return-reason-input").value, "Damaged parcel");
page.setRows([request]); page.setReceipt({...order, sub_orders: [{id: 21, status: "RETURN_REQUESTED"}]});
await page.get("return-retry").dispatch("click"); await settle();
assert.equal(page.calls.filter(row => row.options.method === "POST").length, 1);
assert.equal(page.get("buyer-return-form").hidden, true);
assert.ok(page.get("return-feedback").textContent.includes("#31 is recorded"));

// History is text-only, shows every shop and includes rejection/approval feedback.
page = setup({rows: [request, {...request, id: 32, seller_order_id: 22, status: "REJECTED",
  reason: "<img onerror=alert(1)>", decision_notes: "Please contact the shop.", decided_at: "2026-10-29T11:00:00Z"},
  {...request, id: 33, seller_order_id: 23, status: "APPROVED", payment_status: "REFUNDED"}]});
await page.controller.update(order);
assert.equal(page.get("return-requests-list").children.length, 3);
assert.ok(page.text(page.get("return-requests-list")).includes("<img onerror=alert(1)>"));
assert.ok(page.text(page.get("return-requests-list")).includes("Please contact the shop."));
assert.equal(page.get("return-request-action").hidden, true);

// Account changes and order changes discard late responses and isolate drafts.
const lateIdentity = deferred();
page = setup({identity: lateIdentity});
const reading = page.controller.update(order);
page.storage.set("access_token", "another-account");
page.windowEvents.storage({key: "access_token"});
lateIdentity.resolve(page.response({id: 2, role: "buyer"})); await reading;
assert.equal(page.get("buyer-return-form-card").hidden, true);
const oldPost = deferred();
page = setup({post: oldPost}); await page.controller.update(order); await page.fill();
const oldPosting = page.get("buyer-return-form").dispatch("submit"); await settle();
await page.controller.update({...order, id: 11});
oldPost.resolve(page.response({data: request}, 201)); await oldPosting;
assert.equal(page.get("return-feedback").textContent, "");
assert.equal(page.get("return-reason-input").value, "");
assert.deepEqual(page.submitted, []);

// Expired authentication clears both supported token keys; conflict refreshes eligibility.
page = setup({status: 401}); await page.controller.update(order); await page.fill();
page.storage.set("token", "legacy-token");
await page.get("buyer-return-form").dispatch("submit");
assert.equal(page.storage.size, 0);
assert.deepEqual(page.navigations, ["/login?return_to=%2Forders%2F10"]);
page = setup({status: 409}); await page.controller.update(order); await page.fill();
await page.get("buyer-return-form").dispatch("submit");
assert.equal(page.get("btn-submit-return").disabled, true);
page.setReceipt({...order, sub_orders: [{id: 21, status: "COMPLETED"}]});
await page.get("return-retry").dispatch("click"); await settle();
assert.equal(page.get("return-request-action").hidden, true);
console.log("Buyer returns: eligibility, boundaries, status, drafts, duplicate locks, retry and stale-context checks passed.");
