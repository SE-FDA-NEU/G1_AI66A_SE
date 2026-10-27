// Run with: node tests/seller_orders_ui.mjs
// Execute the real seller order page script (US08) against a small DOM/network test double.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/seller-orders.js", import.meta.url), "utf8");
const LOGIN = "/login?return_to=%2Fseller%2Forders";
const ORDERS = {status: 200, payload: {data: [
  {id: 5, order_id: 5, customer_name: "Nguyen Minh Anh", status: "PENDING", ordered_at: "2026-10-18T10:00:00Z",
    items: [{id: 9, product_id: 46, product_name: "Demo cart item", variant_name: "Black · Large",
      product_code: "P-DEMO-CART", quantity: 2, unit_price: 100000, total_price: 200000}]},
  {id: 3, order_id: 3, customer_name: "Demo Buyer", status: "COMPLETED", ordered_at: "2026-10-10T12:00:00Z",
    items: [{id: 3, product_id: 49, product_name: "Demo completed item", product_code: "P-DEMO-COMPLETE", quantity: 3, unit_price: 250000, total_price: 750000}]},
], meta: {page: 1, limit: 20, total: 2}}};

class Element {
  constructor(tag = "div") {
    Object.assign(this, {tagName: tag.toUpperCase(), hidden: false, disabled: false, textContent: "",
      value: "", className: "", type: "", children: [], handlers: {}});
  }
  set innerHTML(_value) { throw new Error("innerHTML must not be used"); }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  dispatch(name) { for (const handler of this.handlers[name] ?? []) handler({preventDefault() {}}); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
}

const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise(resolve => setImmediate(resolve)); };

function setup({token = "seller-token", responses = [], confirm = true} = {}) {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const storage = new Map(token ? [["access_token", token]] : []);
  const calls = [];
  const navigations = [];
  const location = {replace: url => navigations.push(url), set href(url) { navigations.push(url); }};
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Element(tag)},
    window: {location, confirm: () => confirm},
    localStorage: {getItem: key => storage.get(key) ?? null, removeItem: key => storage.delete(key)},
    URLSearchParams,
    console,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      const next = responses.shift();
      assert.ok(next, `Unexpected request: ${url}`);
      if (next instanceof Error) throw next;
      return {status: next.status, ok: next.status >= 200 && next.status < 300, json: async () => next.payload};
    },
  });
  vm.runInContext(source, context);
  const cards = () => get("orders-list").children;
  const cardText = card => card.children.map(child => child.textContent || child.children.map(c => c.textContent).join(" ")).join(" | ");
  const button = (card, label) => card.children.find(child => child.tagName === "BUTTON" && child.textContent === label);
  return {get, calls, navigations, storage, cards, cardText, button};
}

// A guest, or a seller whose token was rejected, goes to login and returns here.
let page = setup({token: null});
await settle();
assert.deepEqual(page.navigations, [LOGIN]);
assert.equal(page.calls.length, 0);
page = setup({responses: [{status: 401, payload: {error: {code: "ERR_INVALID_TOKEN", message: "x"}}}]});
await settle();
assert.deepEqual(page.navigations, [LOGIN]);
assert.equal(page.storage.size, 0, "The rejected token is removed");

// A buyer sees what to do, not a bare API message.
page = setup({responses: [{status: 403, payload: {error: {code: "ERR_SELLER_REQUIRED", message: "A seller account is required."}}}]});
await settle();
assert.equal(page.get("orders-error").hidden, false);
assert.equal(page.get("orders-status").textContent, "Only seller accounts can manage orders. Log in with a seller account.");

// A network failure explains itself instead of showing the browser's "Failed to fetch".
page = setup({responses: [new TypeError("Failed to fetch")]});
await settle();
assert.equal(page.get("orders-error").hidden, false);
assert.equal(page.get("orders-status").textContent, "We could not reach the server. Check your connection, then select Retry.");
console.log("Access checks passed: guest and expired token to login, buyer and network messages.");

// A seller sees their orders with the next allowed steps only.
page = setup({responses: [ORDERS]});
await settle();
assert.equal(page.calls[0].options.headers.Authorization, "Bearer seller-token");
assert.equal(page.get("orders-status").textContent, "2 seller orders found.");
assert.equal(page.cards().length, 2);
assert.ok(page.cardText(page.cards()[0]).includes(
  "Demo cart item · Black · Large × 2",
), page.cardText(page.cards()[0]));
assert.ok(page.button(page.cards()[0], "Start processing") && page.button(page.cards()[0], "Cancel"));
assert.equal(page.cards()[1].children.filter(child => child.tagName === "BUTTON").length, 0, "COMPLETED offers no step");

// A failed change keeps the list and says which order was not updated.
page = setup({responses: [ORDERS, {status: 409, payload: {error: {code: "ERR_CONCURRENCY_CONFLICT",
  message: "The seller order changed. Please refresh and try again."}}}]});
await settle();
page.button(page.cards()[0], "Start processing").dispatch("click");
await settle();
assert.equal(page.calls[1].options.method, "PATCH");
assert.deepEqual(JSON.parse(page.calls[1].options.body), {status: "PROCESSING"});
assert.equal(page.get("orders-list").hidden, false, "The list stays on screen");
assert.equal(page.cards().length, 2);
assert.equal(page.get("orders-status").textContent,
  "Order #5 was not updated. The seller order changed. Please refresh and try again.");

// A successful change reloads the list from the server.
const processing = structuredClone(ORDERS);
processing.payload.data[0].status = "PROCESSING";
page = setup({responses: [ORDERS, {status: 200, payload: {data: processing.payload.data[0]}}, processing]});
await settle();
page.button(page.cards()[0], "Start processing").dispatch("click");
await settle();
assert.equal(page.calls.length, 3);
assert.ok(page.button(page.cards()[0], "Mark shipped"), "The reloaded card offers the next step");

// Cancelling asks first; declining sends nothing.
page = setup({responses: [ORDERS], confirm: false});
await settle();
page.button(page.cards()[0], "Cancel").dispatch("click");
await settle();
assert.equal(page.calls.length, 1);
console.log("Order checks passed: list, failed change keeps the list, reload after change, cancel confirm.");
