// Run: node tests/cart_ui.mjs. Execute the actual page script, not a copied implementation.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/cart.js", import.meta.url), "utf8");
const tick = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };
const price = n => new Intl.NumberFormat("vi-VN", {style: "currency", currency: "VND"}).format(n);

class Element {
  constructor(tag = "div") {
    Object.assign(this, {tagName: tag, id: "", className: "", textContent: "", children: [],
      dataset: {}, handlers: {}, attributes: {}, hidden: false, disabled: false,
      checked: false, indeterminate: false, value: ""});
    this.classList = {add: name => { this.className += ` ${name}`; }};
  }
  set innerHTML(_) { throw new Error("Render server text through textContent"); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  querySelectorAll(selector) {
    const matches = node => selector.split(",").some(part => {
      part = part.trim();
      return part.startsWith(".") ? node.className.split(" ").includes(part.slice(1)) : node.tagName === part;
    });
    const result = [];
    for (const child of this.children) {
      if (matches(child)) result.push(child);
      result.push(...child.querySelectorAll(selector));
    }
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  dispatch(name) { for (const handler of this.handlers[name] ?? []) handler({target: this}); }
}

function item(id, seller, selected, extra = {}) {
  return {cart_item_id: id, product_id: id, product_code: `P-${id}`, seller_id: seller,
    seller_name: `Shop ${seller}`, name: `Item ${id}`, unit_price: 100000, price_at_add: 100000,
    price_changed: false, quantity: 1, line_total: 100000, available_stock: 5,
    availability: "available", is_selected: selected, ...extra};
}
function snapshot(items, extra = {}) {
  return {items, cart_total: items.reduce((sum, line) => sum + line.line_total, 0),
    selected_total: items.filter(line => line.is_selected).reduce((sum, line) => sum + line.line_total, 0),
    ...extra};
}
const ok = data => ({data});

function setup(responses, token = "buyer-a") {
  const roots = new Map();
  const ids = ["cart-status", "cart-loading", "cart-content", "cart-lines", "cart-total",
    "cart-total-label", "checkout-button", "checkout-blocked", "cart-empty", "cart-empty-total",
    "cart-error", "cart-error-message", "cart-retry", "logout-button", "cart-change-error"];
  for (const id of ids) roots.set(id, Object.assign(new Element(), {id}));
  let activeElement = null;
  const get = id => roots.get(id) ?? [...roots.values()].flatMap(root => root.querySelectorAll("input, button"))
    .find(node => node.id === id) ?? null;
  const document = {getElementById: get, createElement: tag => {
    const node = new Element(tag);
    node.focus = () => { activeElement = node; };
    return node;
  }, get activeElement() { return activeElement; }};
  for (const node of roots.values()) node.focus = () => { activeElement = node; };
  const local = new Map(token ? [["access_token", token]] : []);
  const calls = [], navigation = [], windowHandlers = {};
  const context = vm.createContext({document, Intl, AbortController, setTimeout, clearTimeout,
    localStorage: {getItem: key => local.get(key) ?? null, removeItem: key => local.delete(key)},
    window: {location: {assign: url => navigation.push(url), replace: url => navigation.push(url),
      reload: () => navigation.push("reload")}, addEventListener: (name, handler) => {windowHandlers[name] = handler;}},
    fetch: async (url, options) => {
      calls.push({url, ...options});
      const response = await responses.shift();
      assert.ok(response, `Unexpected request ${url}`);
      if (response instanceof Error) throw response;
      const status = response.status ?? 200;
      return {status, ok: status < 400, json: async () => response.payload ?? response};
    },
  });
  vm.runInContext(source, context);
  const change = id => { const node = get(id); assert.ok(node, id); node.focus(); node.checked = !node.checked; node.dispatch("change"); };
  return {get, calls, navigation, change, setToken: value => value === null ? local.clear() : local.set("access_token", value),
    storage: key => windowHandlers.storage({key}), get focused() { return activeElement; },
    text: node => [node.textContent, ...node.children.map(child => pageText(child))].join(" ")};
}
function pageText(node) { return [node.textContent, ...node.children.map(pageText)].join(" "); }

// Grouping, tri-state, exact totals, visible price changes in either direction, unavailable rows.
const items = [item(1, 10, true), item(2, 10, false), item(3, 20, true,
  {unit_price: 80000, line_total: 80000, price_changed: true}),
item(4, 20, false, {availability: "unavailable", available_stock: 0}),
item(5, 20, false, {availability: "insufficient_stock", available_stock: 0}),
item(6, 30, false, {unit_price: 120000, line_total: 120000, price_changed: true})];
let page = setup([ok(snapshot(items))]);
await tick();
assert.equal(page.get("cart-lines").children.length, 3);
assert.equal(page.get("select-shop-10").indeterminate, true);
assert.equal(page.get("select-shop-20").checked, true);
assert.equal(page.get("select-item-4").disabled, true);
assert.equal(page.get("select-item-5").checked, false);
assert.equal(page.get("cart-total").textContent, price(180000));
const text = pageText(page.get("cart-lines"));
assert.ok(text.includes(`Shop subtotal: ${price(200000)} · Selected: ${price(100000)}`));
assert.ok(text.includes(`Price changed: ${price(100000)} when added → ${price(80000)} now.`));
assert.ok(text.includes(`Price changed: ${price(100000)} when added → ${price(120000)} now.`));
assert.ok(text.includes("Unavailable for checkout"));
assert.equal(page.get("checkout-button").disabled, true); // #120 has not advertised capability.
page.get("checkout-button").dispatch("click");
assert.deepEqual(page.navigation, []);

// Item selection uses the cart row ID, persists only after API acknowledgement and restores focus.
const changedItems = [item(91, 10, false, {product_code: "P-DIFFERENT"})];
page = setup([ok(snapshot(changedItems)), ok(snapshot([{...changedItems[0], is_selected: true}]))]);
await tick();
page.change("select-item-91");
await tick();
assert.equal(page.calls[1].url, "/api/v1/cart/items/91/select");
assert.equal(page.calls[1].method, "PATCH");
assert.equal(page.calls[1].headers.Authorization, "Bearer buyer-a");
assert.deepEqual(JSON.parse(page.calls[1].body), {is_selected: true});
assert.equal(page.get("cart-total").textContent, price(100000));
assert.equal(page.get("select-item-91").checked, true);
assert.equal(page.focused.id, "select-item-91");

// Selecting a shop is one atomic request; unrelated shops follow the server snapshot.
page = setup([ok(snapshot([item(1, 10, true), item(2, 10, false), item(3, 20, true)])),
  ok(snapshot([item(1, 10, true), item(2, 10, true), item(3, 20, true)]))]);
await tick();
page.change("select-shop-10");
await tick();
assert.equal(page.calls[1].url, "/api/v1/cart/select-shop/10");
assert.deepEqual(JSON.parse(page.calls[1].body), {is_selected: true});
assert.equal(page.get("select-shop-10").indeterminate, false);
assert.equal(page.get("select-shop-20").checked, true);
assert.equal(page.get("cart-total").textContent, price(300000));

// Conflict and network failures roll back checkbox state and totals, retaining actionable feedback.
for (const failure of [new Error("offline"), {status: 409, payload: {error: {message: "Cart changed. Try again."}}}]) {
  page = setup([ok(snapshot([item(1, 10, true)])), failure,
    ok(snapshot([item(1, 10, false)]))]);
  await tick();
  page.change("select-item-1");
  await tick();
  assert.equal(page.get("select-item-1").checked, true);
  assert.equal(page.get("cart-total").textContent, price(100000));
  assert.equal(page.get("cart-change-error").hidden, false);
  page.change("select-item-1");
  await tick();
  assert.equal(page.get("select-shop-10").checked, false);
  assert.equal(page.get("checkout-button").disabled, true);
  assert.equal(page.get("cart-change-error").hidden, true);
}

// No overlapping mutations or checkout during pending selection.
let complete;
const pending = new Promise(resolve => {complete = resolve;});
page = setup([ok(snapshot([item(1, 10, true)], {supports_partial_checkout: true})), pending]);
await tick();
page.change("select-item-1");
assert.equal(page.get("checkout-button").disabled, true);
page.change("select-shop-10");
page.get("checkout-button").dispatch("click");
assert.equal(page.calls.length, 2);
assert.deepEqual(page.navigation, []);
complete(ok(snapshot([item(1, 10, false)], {supports_partial_checkout: true})));
await tick();
assert.equal(page.get("select-shop-10").checked, false);

// Selection capability may enable checkout, but an empty selection never does.
page = setup([ok(snapshot([item(1, 10, true)], {supports_partial_checkout: true}))]);
await tick();
assert.equal(page.get("checkout-button").disabled, false);
page.get("checkout-button").dispatch("click");
assert.deepEqual(page.navigation, ["/checkout"]);

// A shop with only unavailable items cannot be selected.
page = setup([ok(snapshot([item(1, 10, false, {availability: "unavailable"})]))]);
await tick();
assert.equal(page.get("select-shop-10").disabled, true);
assert.equal(page.get("checkout-button").disabled, true);

// Never submit A's displayed context using B's token, even without a storage event.
for (const action of ["selection", "checkout", "storage"]) {
  page = setup([ok(snapshot([item(1, 10, true)], {supports_partial_checkout: true}))]);
  await tick();
  page.setToken("buyer-b");
  if (action === "selection") page.change("select-item-1");
  if (action === "checkout") page.get("checkout-button").dispatch("click");
  if (action === "storage") page.storage("access_token");
  await tick();
  assert.equal(page.calls.length, 1);
  assert.deepEqual(page.navigation, ["reload"]);
  assert.equal(page.get("cart-content").hidden, true);
}

// Whole-cart responses keep the existing cart working without fabricated shop/selection metadata.
const legacy = {items: [{product_id: 1, product_code: "P-1", name: "Old item", quantity: 1,
  unit_price: 100000, line_total: 100000, availability: "available", available_stock: 5}], cart_total: 100000};
page = setup([ok(legacy)]);
await tick();
assert.equal(page.get("cart-total-label").textContent, "Total:");
assert.equal(page.get("checkout-button").disabled, false);
assert.equal(page.get("select-item-1"), null);
page.get("checkout-button").dispatch("click");
assert.deepEqual(page.navigation, ["/checkout"]);

// Quantity and removal distinguish cart lines while retaining product-code routes.
page = setup([ok(snapshot([item(1, 10, true)])),
  ok(snapshot([item(1, 10, true, {quantity: 2, line_total: 200000})])),
  ok(snapshot([]))]);
await tick();
page.get("increase-1").focus();
page.get("increase-1").dispatch("click");
await tick();
assert.equal(page.calls[1].url, "/api/v1/cart/items/P-1");
assert.deepEqual(JSON.parse(page.calls[1].body), {quantity: 2});
assert.equal(page.get("cart-total").textContent, price(200000));
assert.equal(page.focused.id, "increase-1");
page.get("remove-1").dispatch("click");
await tick();
assert.equal(page.calls[2].method, "DELETE");
assert.equal(page.get("cart-empty").hidden, false);

// Two options of the same product have separate controls and variant-scoped quantity routes.
const black = item(1, 10, true, {variant_id: 11, variant_name: "Black"});
const white = item(2, 10, false, {
  product_id: 1, product_code: "P-1", variant_id: 22, variant_name: "White",
});
page = setup([
  ok(snapshot([black, white])),
  ok(snapshot([black, {...white, quantity: 2, line_total: 200000}])),
]);
await tick();
page.get("increase-2").dispatch("click");
await tick();
assert.equal(page.calls[1].url, "/api/v1/cart/items/P-1?variant_id=22");
assert.equal(page.get("quantity-2").value, "2");
assert.ok(page.text(page.get("cart-lines")).includes("White"));

// Ignore a pending response after switching accounts; never render the old account's data.
let resolveOld;
page = setup([new Promise(resolve => {resolveOld = resolve;})]);
page.setToken("buyer-b");
resolveOld(ok(snapshot([item(1, 10, true)])));
await tick();
assert.deepEqual(page.navigation, ["reload"]);
assert.equal(page.get("cart-content").hidden, true);

// Invalid or incomplete new contracts fail closed; they must not enable whole-cart checkout.
for (const invalid of [snapshot([item(1, 10, true)], {selected_total: 1}),
  {items: [{...legacy.items[0], seller_id: 10}], cart_total: 100000},
  snapshot([item(1, 10, true, {availability: "unavailable"})]),
  snapshot([item(1, 10, true), item(1, 20, true)])]) {
  page = setup([ok(invalid)]);
  await tick();
  assert.equal(page.get("cart-error").hidden, false);
  page.get("checkout-button").dispatch("click");
  assert.deepEqual(page.navigation, []);
}

// Existing loading/empty/error/retry/auth states remain usable.
page = setup([ok({items: [], cart_total: 0})]);
await tick();
assert.equal(page.get("cart-empty").hidden, false);
page = setup([new Error("offline"), ok(legacy)]);
await tick();
assert.equal(page.get("cart-error").hidden, false);
page.get("cart-retry").dispatch("click");
await tick();
assert.equal(page.get("cart-content").hidden, false);
page = setup([], null);
await tick();
assert.equal(page.calls.length, 0);
assert.deepEqual(page.navigation, ["/login?return_to=%2Fcart"]);
page = setup([{status: 403, payload: {error: {message: "Forbidden"}}}]);
await tick();
assert.equal(page.get("cart-retry").hidden, true);
console.log("Cart UI checks passed (US12 #119: grouping, selection, errors, account context, compatibility).");
