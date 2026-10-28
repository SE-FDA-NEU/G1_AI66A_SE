// Run: node tests/products_ui.mjs. Executes the real catalog script against DOM and network
// doubles: request timeout, superseded responses, filters kept after errors, price input rules,
// page reset on filter change, and controls restored by back navigation.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/products.js", import.meta.url), "utf8");
const settle = async () => { for (let i = 0; i < 10; i++) await new Promise(setImmediate); };

class Element {
  constructor(tag = "div") {
    Object.assign(this, {tagName: tag.toUpperCase(), id: "", className: "", textContent: "",
      value: "", checked: false, hidden: false, disabled: false, children: [], handlers: {}});
  }
  set innerHTML(_) { throw new Error("Render server text through textContent"); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  dispatch(name) { for (const handler of this.handlers[name] ?? []) handler({preventDefault() {}, target: this}); }
}

const product = (id) => ({id: String(id), code: `P-${id}`, name: `Product ${id}`, price: 100000,
  thumbnail_url: null, stock_quantity: 10, stock_status: "in_stock", rating: 0});
const page = (ids, {total = ids.length, current = 1, pages = 1} = {}) =>
  ({data: ids.map(product), meta: {total, total_items: total, current_page: current, limit: 20,
    total_pages: pages}});

/**
 * `respond(url)` returns a payload, an Error to reject with, or a promise of either.
 * A request whose signal aborts rejects with AbortError, as fetch does.
 */
function setup({respond = () => page([1]), controls = {}} = {}) {
  const nodes = new Map();
  const get = (id) => {
    if (!nodes.has(id)) {
      const tag = id.startsWith("filter-") || id === "catalog-sort" ? "select" : "div";
      nodes.set(id, Object.assign(new Element(tag), {id}));
    }
    return nodes.get(id);
  };
  get("filter-in-stock").checked = true;
  for (const [id, values] of Object.entries(controls)) Object.assign(get(id), values);

  const requests = [];
  const timers = [];
  const context = vm.createContext({
    document: {getElementById: get, createElement: (tag) => new Element(tag)},
    window: {location: {pathname: "/products", search: ""}},
    localStorage: {getItem: () => null, removeItem() {}},
    fetch: (url, {signal} = {}) => {
      if (url === "/api/v1/categories" || url === "/api/v1/sellers") {
        return Promise.resolve({ok: true, json: async () => []});
      }
      const query = new URL(url, "http://localhost").searchParams;
      requests.push(query);
      return new Promise((resolve, reject) => {
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        Promise.resolve(respond(url)).then((result) => {
          if (result instanceof Error) reject(result);
          else resolve({ok: true, json: async () => result});
        });
      });
    },
    // Timers are fired by the test, so a timeout needs no real wait.
    setTimeout: (callback) => timers.push(callback) - 1,
    clearTimeout: (id) => { timers[id] = null; },
    AbortController, URLSearchParams, Intl, atob, encodeURIComponent,
  });
  vm.runInContext(source, context);
  return {
    get, requests,
    last: () => requests.at(-1),
    fireTimeouts: () => timers.splice(0).forEach((callback) => callback?.()),
    shown: () => ["products-loading", "products-grid", "products-empty", "products-error"]
      .filter((id) => !get(id).hidden),
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {promise, resolve};
}

// A request that never answers ends in the error state when its timeout fires, then Retry works.
let hang = true;
let ui = setup({respond: () => (hang ? new Promise(() => {}) : page([1]))});
await settle();
assert.deepEqual(ui.shown(), ["products-loading"]);
ui.fireTimeouts();
await settle();
assert.deepEqual(ui.shown(), ["products-error"], "A timed-out request must not stay on loading");
assert.match(ui.get("products-error-message").textContent, /too long/);
assert.equal(ui.get("products-status").textContent, ui.get("products-error-message").textContent);
assert.equal(ui.get("products-retry").disabled, false);
hang = false;
ui.get("products-retry").dispatch("click");
await settle();
assert.equal(ui.requests.length, 2);
assert.deepEqual(ui.shown(), ["products-grid"]);
console.log("Timeout checks passed: error state with Retry, not an endless loading state.");

// An older response that arrives after a newer query never replaces the newer results.
const slow = deferred();
let calls = 0;
ui = setup({respond: () => (++calls === 1 ? slow.promise : page([2]))});
await settle();
ui.get("filter-category").value = "4";
ui.get("filter-category").dispatch("change");
await settle();
slow.resolve(page([1]));
await settle();
assert.deepEqual(ui.shown(), ["products-grid"]);
assert.deepEqual(ui.get("products-grid").children.map((card) => card.children[0].href), ["/products/P-2"]);
assert.equal(ui.last().get("category_id"), "4");
console.log("Superseded request checks passed: the late response is discarded without an error.");

// A failed load keeps the chosen filters on screen, and Retry repeats exactly that query.
let fail = true;
ui = setup({respond: () => (fail ? new TypeError("Failed to fetch") : page([3]))});
await settle();
ui.get("product-search-input").value = "lamp";
ui.get("filter-seller").value = "7";
ui.get("filter-seller").dispatch("change");
await settle();
assert.deepEqual(ui.shown(), ["products-error"]);
assert.match(ui.get("products-error-message").textContent, /could not load/);
assert.equal(ui.get("product-search-input").value, "lamp");
assert.equal(ui.get("filter-seller").value, "7");
fail = false;
ui.get("products-retry").dispatch("click");
await settle();
assert.equal(ui.last().get("search"), "lamp");
assert.equal(ui.last().get("seller_id"), "7", "Changing the seller applies it like the other selects");
assert.deepEqual(ui.shown(), ["products-grid"]);
console.log("Error checks passed: filters stay visible and Retry reuses the same query.");

// Price bounds are whole, non-negative VND; Enter in the form follows the same rule as Apply.
ui = setup();
await settle();
const before = ui.requests.length;
for (const [min, max] of [["-5", ""], ["1500.5", ""], ["", "1e6"], ["900000", "100000"]]) {
  ui.get("filter-min-price").value = min;
  ui.get("filter-max-price").value = max;
  ui.get("apply-filters").dispatch("click");
  ui.get("products-search").dispatch("submit");
  await settle();
  assert.equal(ui.get("price-error").hidden, false, `${min}..${max} must be rejected`);
}
assert.match(ui.get("price-error").textContent, /cannot be greater/);
ui.get("filter-min-price").value = "-1";
ui.get("filter-min-price").dispatch("input");
assert.match(ui.get("price-error").textContent, /whole numbers of 0/);
assert.equal(ui.requests.length, before, "An invalid price range sends no request");
ui.get("filter-min-price").value = "155500";
ui.get("filter-max-price").value = "";
ui.get("products-search").dispatch("submit");
await settle();
assert.equal(ui.get("price-error").hidden, true);
assert.equal(ui.last().get("min_price"), "155500", "Prices off the 1,000 step are still accepted");
console.log("Price checks passed: negative, decimal and reversed bounds blocked; Enter equals Apply.");

// Changing a filter from page 2 starts again at page 1.
ui = setup({respond: (url) => {
  const current = Number(new URL(url, "http://localhost").searchParams.get("page"));
  return page([current], {total: 45, current, pages: 3});
}});
await settle();
ui.get("products-next").dispatch("click");
await settle();
assert.equal(ui.get("products-page").textContent, "Page 2 of 3");
ui.get("filter-rating").value = "4.0";
ui.get("filter-rating").dispatch("change");
await settle();
assert.equal(ui.last().get("page"), "1");
assert.equal(ui.get("products-page").textContent, "Page 1 of 3");
assert.equal(ui.get("products-previous").disabled, true);
console.log("Pagination checks passed: a filter change resets to page 1.");

// Back navigation can restore control values before the script runs; the first load uses them.
ui = setup({controls: {"filter-rating": {value: "4.0"}, "filter-in-stock": {checked: false},
  "catalog-sort": {value: "price_desc"}}});
await settle();
assert.equal(ui.requests.length, 1);
assert.equal(ui.last().get("min_rating"), "4.0");
assert.equal(ui.last().get("in_stock"), "false");
assert.equal(ui.last().get("sort"), "price_desc");

ui = setup({controls: {"filter-min-price": {value: "500"}, "filter-max-price": {value: "100"}}});
await settle();
assert.equal(ui.last().get("min_price"), null, "A restored invalid range is not applied");
assert.equal(ui.get("price-error").hidden, false, "and the error explains why");
console.log("Restored-control checks passed: the first request matches what the form shows.");
