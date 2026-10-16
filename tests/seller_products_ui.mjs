// Run with: node tests/seller_products_ui.mjs
// Execute the real US06 page script against a small DOM/network test double.
// Visual layout and keyboard use are checked in a real browser (docs/evidence/us06.md).
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const read = name => readFile(new URL(`../src/web/static/${name}`, import.meta.url), "utf8");
const formSource = await read("seller-product-new.js");
const FIELDS = ["name", "description", "price", "stock_quantity", "image_url"];
const LOGIN = "/login?return_to=%2Fseller%2Fproducts%2Fnew";
const VALID = {
  name: "  Training Mouse ",
  description: " Wireless mouse for study. ",
  price: "180000",
  stock_quantity: "10",
  image_url: " https://example.com/mouse.jpg ",
};
const SELLER = {status: 200, payload: {id: 1, name: "Seller A", email: "a@test.local", role: "seller"}};
const BUYER = {status: 200, payload: {id: 2, name: "Buyer", email: "b@test.local", role: "buyer"}};
const CREATED = {
  status: 201,
  payload: {data: {id: 46, code: "P-6E1059D348A4CB729F", seller_id: 1, name: "Training Mouse",
    description: "Wireless mouse for study.", price: 180000, stock_quantity: 10, reserved_stock: 0,
    image_url: "https://example.com/mouse.jpg", is_active: true, version: 1}},
};

let focused = null;

class Element {
  constructor(id = "", tag = "div") {
    Object.assign(this, {id, tagName: tag.toUpperCase(), hidden: false, disabled: false,
      textContent: "", value: "", href: "", src: "", children: [], handlers: {}});
    this.attributes = new Map();
  }
  // Rendering user or server text as HTML would be a defect, so any use fails the run.
  set innerHTML(_value) { throw new Error("innerHTML must not be used"); }
  get innerHTML() { return ""; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  removeAttribute(name) { this.attributes.delete(name); }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  dispatch(name, event = {}) {
    for (const handler of this.handlers[name] ?? []) handler({preventDefault() {}, target: this, ...event});
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  focus() { focused = this; }
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

const tick = () => new Promise(resolve => setImmediate(resolve));
async function settle() { for (let i = 0; i < 5; i += 1) await tick(); }

function setup({token = "seller-token", responses = [], draft = null} = {}) {
  focused = null;
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element(id));
    return nodes.get(id);
  };
  const form = get("product-form");
  form.hidden = true;
  const controls = FIELDS.map(name => Object.assign(get(`input-${name}`), {name, validity: {badInput: false}}));
  form.elements = [...controls, get("create-button")];
  for (const control of controls) form.elements[control.name] = control;
  form.reset = () => { for (const control of controls) control.value = ""; };
  for (const id of ["forbidden", "error-summary", "account-retry", "reload-page", "product-created"]) {
    get(id).hidden = true;
  }

  const local = new Map(token ? [["access_token", token]] : []);
  const session = new Map(draft ? [["seller-product-draft", JSON.stringify(draft)]] : []);
  const calls = [];
  const navigations = [];
  const windowHandlers = {};
  const location = {
    pathname: "/seller/products/new",
    search: "",
    replace: url => navigations.push(["replace", url]),
    assign: url => navigations.push(["assign", url]),
    reload: () => navigations.push(["reload"]),
  };
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Element("", tag)},
    window: {location, addEventListener(name, handler) { (windowHandlers[name] ??= []).push(handler); }},
    location,
    localStorage: {getItem: key => local.get(key) ?? null},
    sessionStorage: {
      getItem: key => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, String(value)),
      removeItem: key => session.delete(key),
    },
    AbortSignal: {timeout: () => undefined},
    URL,
    console,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      const next = await responses.shift();
      assert.ok(next, `Unexpected request: ${url}`);
      if (next instanceof Error) throw next;
      const status = next.status ?? 200;
      return {
        status,
        ok: status >= 200 && status < 300,
        json: async () => {
          if (next.payload === undefined) throw new SyntaxError("Unexpected end of JSON input");
          return next.payload;
        },
      };
    },
  });
  vm.runInContext(formSource, context);
  const field = name => form.elements[name];
  const fill = values => { for (const [name, value] of Object.entries(values)) field(name).value = value; };
  const submit = () => form.dispatch("submit");
  const posts = () => calls.filter(call => call.options.method === "POST");
  const values = () => Object.fromEntries(FIELDS.map(name => [name, field(name).value]));
  const fieldError = name => get(`${name}-error`);
  const summaryLines = () => get("error-summary-list").children.map(child => child.textContent);
  const setToken = value => (value === null ? local.delete("access_token") : local.set("access_token", value));
  const storageEvent = key => { for (const handler of windowHandlers.storage ?? []) handler({key}); };
  return {get, form, field, fill, submit, calls, posts, values, fieldError, summaryLines, navigations,
    session, setToken, storageEvent};
}

// Guests go to login with a return path; nothing is requested with a missing token.
let page = setup({token: null});
await settle();
assert.deepEqual(page.navigations, [["replace", LOGIN]]);
assert.equal(page.calls.length, 0);
assert.equal(page.form.hidden, true);

// An expired or rejected token also goes to login.
page = setup({responses: [{status: 401, payload: {error: {code: "ERR_INVALID_TOKEN", message: "x"}}}]});
await settle();
assert.deepEqual(page.navigations, [["replace", LOGIN]]);

// A buyer sees the forbidden state and the form never becomes usable.
page = setup({responses: [BUYER]});
await settle();
assert.equal(page.get("forbidden").hidden, false);
assert.equal(page.form.hidden, true);
assert.ok(page.form.elements.every(control => control.disabled));
page.fill(VALID);
page.submit();
await settle();
assert.equal(page.posts().length, 0);

// A failed account check offers Try again, which loads the form for a seller.
page = setup({responses: [new Error("offline"), SELLER]});
await settle();
assert.equal(page.get("account-retry").hidden, false);
assert.equal(page.form.hidden, true);
page.get("account-retry").dispatch("click");
await settle();
assert.equal(page.form.hidden, false);
assert.match(page.get("account-status").textContent, /Seller A/);
console.log("Account checks passed: guest, rejected token, buyer, retry.");

// A seller gets an enabled form; the account check uses the page's token.
page = setup({responses: [SELLER]});
await settle();
assert.equal(page.form.hidden, false);
assert.ok(page.form.elements.every(control => !control.disabled));
assert.equal(page.calls[0].url, "/api/v1/auth/me");
assert.equal(page.calls[0].options.headers.Authorization, "Bearer seller-token");

// Invalid input never reaches the server; each field shows its own message.
page.fill({name: "   ", description: "ok", price: "1.5", stock_quantity: "-1", image_url: "ftp://example.com/x.jpg"});
const typed = page.values();
page.submit();
await settle();
assert.equal(page.posts().length, 0);
assert.equal(page.fieldError("name").textContent, "Product name is required.");
assert.equal(page.fieldError("price").textContent, "Price must be a whole number of VND.");
assert.equal(page.fieldError("stock_quantity").textContent, "Stock quantity must be 0 or more.");
assert.equal(page.fieldError("image_url").textContent, "Image URL must be an absolute http:// or https:// address.");
assert.equal(page.fieldError("description").hidden, true);
for (const name of ["name", "price", "stock_quantity", "image_url"]) {
  assert.equal(page.field(name).getAttribute("aria-invalid"), "true");
}
assert.equal(page.field("description").getAttribute("aria-invalid"), null);
assert.equal(focused, page.field("name"), "Focus moves to the first invalid field");
assert.equal(page.get("error-summary").hidden, false);
assert.equal(page.get("error-summary-title").textContent, "Please correct the highlighted fields.");
assert.equal(page.summaryLines().length, 4);
assert.deepEqual(page.values(), typed, "Entered values are preserved");

// More client rules: huge, fractional and unparseable numbers, and long text in code points.
const checks = [
  [{price: "0"}, "price", "Price must be greater than 0 ₫."],
  [{price: "1000000001"}, "price", "Price must be at most 1.000.000.000 ₫."],
  [{price: "99999999999999999999"}, "price", "Price must be at most 1.000.000.000 ₫."],
  [{price: "1e3"}, "price", "Price must be a whole number of VND."],
  [{stock_quantity: "2.0"}, "stock_quantity", "Stock quantity must be a whole number."],
  [{stock_quantity: "1000001"}, "stock_quantity", "Stock quantity must be at most 1.000.000."],
  [{stock_quantity: ""}, "stock_quantity", "Stock quantity is required."],
  [{name: "x".repeat(201)}, "name", "Product name must be at most 200 characters."],
  [{description: " \n "}, "description", "Description is required."],
  [{image_url: "https://exa mple.com/a.jpg"}, "image_url", "Image URL must be an absolute http:// or https:// address."],
  [{image_url: "/images/p-100.jpg"}, "image_url", "Image URL must be an absolute http:// or https:// address."],
  [{image_url: "javascript:alert(1)"}, "image_url", "Image URL must be an absolute http:// or https:// address."],
];
for (const [patch, name, message] of checks) {
  page.fill({...VALID, ...patch});
  page.submit();
  await settle();
  assert.equal(page.fieldError(name).textContent, message, JSON.stringify(patch));
}
page.fill(VALID);
page.field("price").value = "";
page.field("price").validity = {badInput: true};
page.submit();
await settle();
assert.equal(page.fieldError("price").textContent, "Price must be a whole number of VND.");
page.field("price").validity = {badInput: false};
page.fill({...VALID, name: "🙂".repeat(201)});
page.submit();
await settle();
assert.equal(page.fieldError("name").textContent, "Product name must be at most 200 characters.");
assert.equal(page.posts().length, 0);
// 200 emoji are 400 UTF-16 units but 200 characters, which the server accepts.
page = setup({responses: [SELLER, CREATED]});
await settle();
page.fill({...VALID, name: "🙂".repeat(200)});
page.submit();
await settle();
assert.equal(JSON.parse(page.posts()[0].options.body).name, "🙂".repeat(200));
console.log("Client validation passed: required, whole numbers, bounds, URL, no POST.");

// A valid form sends trimmed text and JSON numbers with the page's token.
page = setup({responses: [SELLER, CREATED]});
await settle();
page.fill(VALID);
page.submit();
await settle();
assert.equal(page.posts().length, 1);
const [post] = page.posts();
assert.equal(post.url, "/api/v1/seller/products");
assert.equal(post.options.headers.Authorization, "Bearer seller-token");
assert.equal(post.options.headers["Content-Type"], "application/json");
assert.deepEqual(JSON.parse(post.options.body), {
  name: "Training Mouse",
  description: "Wireless mouse for study.",
  price: 180000,
  stock_quantity: 10,
  image_url: "https://example.com/mouse.jpg",
});

// Success shows the code and name, links to the public code, and hides the form.
assert.equal(page.form.hidden, true);
assert.equal(page.get("product-created").hidden, false);
assert.equal(page.get("created-name").textContent, "Training Mouse");
assert.equal(page.get("created-code").textContent, "P-6E1059D348A4CB729F");
assert.equal(page.get("view-product").href, "/products/P-6E1059D348A4CB729F");
assert.match(page.get("created-stock").textContent, /10 in stock/);
assert.equal(focused, page.get("product-created"));
assert.equal(page.get("error-summary").hidden, true);

// Create another product reopens an empty form.
page.get("create-another").dispatch("click");
assert.equal(page.form.hidden, false);
assert.equal(page.get("product-created").hidden, true);
assert.ok(FIELDS.every(name => page.field(name).value === ""));
assert.equal(focused, page.field("name"));

// HTML-looking names stay text, unusual codes are encoded, zero stock is explained.
const htmlName = '<img src=x onerror="alert(1)">';
page = setup({responses: [SELLER, {status: 201, payload: {data: {...CREATED.payload.data,
  name: htmlName, code: "P-A/B?C", stock_quantity: 0}}}]});
await settle();
page.fill({...VALID, name: htmlName, stock_quantity: "0"});
page.submit();
await settle();
assert.equal(JSON.parse(page.posts()[0].options.body).stock_quantity, 0);
assert.equal(page.get("created-name").textContent, htmlName);
assert.equal(page.get("view-product").href, "/products/P-A%2FB%3FC");
assert.match(page.get("created-stock").textContent, /Out of stock/);
console.log("Submission and success passed: payload, code/name, link, text rendering.");

// Server field errors land beside their fields; request-level messages go to the summary.
page = setup({responses: [SELLER, {status: 422, payload: {error: {code: "ERR_VALIDATION",
  message: "Please correct the highlighted fields.",
  fields: {price: ["Price must be greater than 0 ₫."], _form: ["seller_id is set by the server and cannot be sent."]}}}}]});
await settle();
page.fill(VALID);
page.submit();
await settle();
assert.equal(page.fieldError("price").textContent, "Price must be greater than 0 ₫.");
assert.equal(page.fieldError("price").hidden, false);
assert.equal(page.field("price").getAttribute("aria-invalid"), "true");
assert.equal(page.fieldError("name").hidden, true);
assert.deepEqual(page.summaryLines(), ["Price: Price must be greater than 0 ₫.",
  "seller_id is set by the server and cannot be sent."]);
assert.equal(focused, page.field("price"));
assert.deepEqual(page.values(), VALID, "Values are kept after a 422");
assert.ok(page.form.elements.every(control => !control.disabled), "Controls unlock after a 422");

// A whole-request 422 (no product field) is shown in the summary.
page = setup({responses: [SELLER, {status: 422, payload: {error: {code: "ERR_VALIDATION",
  message: "The request body is not valid JSON.", fields: {_form: ["The request body is not valid JSON."]}}}}]});
await settle();
page.fill(VALID);
page.submit();
await settle();
assert.equal(page.get("error-summary-title").textContent, "The request body is not valid JSON.");
assert.deepEqual(page.summaryLines(), []);
assert.equal(focused, page.get("error-summary"));
assert.ok(FIELDS.every(name => page.fieldError(name).hidden));

// Database failures and conflicts keep the input, are not shown as a field error, and are not retried.
for (const [status, code, message] of [
  [500, "ERR_DATABASE_FAILURE", "Unable to create the product right now. Please try again later."],
  [409, "ERR_CONCURRENCY_CONFLICT", "Could not assign a unique product code. Please submit again."],
  [403, "ERR_SELLER_REQUIRED", "A seller account is required."],
]) {
  page = setup({responses: [SELLER, {status, payload: {error: {code, message}}}]});
  await settle();
  page.fill(VALID);
  page.submit();
  await settle();
  assert.equal(page.get("error-summary-title").textContent, "The listing was not created.");
  assert.deepEqual(page.summaryLines(), [message]);
  assert.ok(FIELDS.every(name => page.fieldError(name).hidden), `${status} is not a field error`);
  assert.deepEqual(page.values(), VALID);
  assert.ok(page.form.elements.every(control => !control.disabled));
  assert.equal(page.posts().length, 1);
}

// A non-JSON error page still gives a readable message.
page = setup({responses: [SELLER, {status: 502}]});
await settle();
page.fill(VALID);
page.submit();
await settle();
assert.deepEqual(page.summaryLines(), ["Please try again."]);

// A network error or timeout is reported as unconfirmed and never resent automatically.
page = setup({responses: [SELLER, new Error("timeout")]});
await settle();
page.fill(VALID);
page.submit();
await settle();
await settle();
assert.equal(page.posts().length, 1);
assert.equal(page.get("error-summary-title").textContent, "The listing was not confirmed.");
assert.match(page.summaryLines()[0], /may already exist/);
assert.deepEqual(page.values(), VALID);
assert.ok(page.form.elements.every(control => !control.disabled));
console.log("Error handling passed: 422 fields, form errors, 403/409/500/502, network.");

// While a request is pending the form is locked and a second submit sends nothing.
let reply = deferred();
page = setup({responses: [SELLER, reply.promise]});
await settle();
page.fill(VALID);
page.submit();
page.submit();
await settle();
assert.equal(page.posts().length, 1);
assert.ok(page.form.elements.every(control => control.disabled));
assert.equal(page.get("submit-status").textContent, "Creating listing...");
reply.resolve(CREATED);
await settle();
assert.equal(page.get("product-created").hidden, false);
assert.equal(page.get("submit-status").textContent, "");

// An expired session keeps the values for the same account across the login.
page = setup({responses: [SELLER, {status: 401, payload: {error: {code: "ERR_INVALID_TOKEN", message: "x"}}}]});
await settle();
page.fill(VALID);
page.submit();
await settle();
assert.deepEqual(page.navigations, [["assign", LOGIN]]);
const draft = JSON.parse(page.session.get("seller-product-draft"));
assert.deepEqual(draft, {account_id: 1, values: VALID});
page = setup({responses: [SELLER], draft});
await settle();
assert.deepEqual(page.values(), VALID);
assert.match(page.get("account-status").textContent, /restored/);
assert.equal(page.session.size, 0);
page = setup({responses: [{...SELLER, payload: {...SELLER.payload, id: 9}}], draft});
await settle();
assert.ok(FIELDS.every(name => page.field(name).value === ""), "Another seller never sees the draft");
assert.equal(page.session.size, 0);
console.log("Pending lock and session-expiry draft passed.");

// An account switch before submit blocks the POST and requires a reload.
page = setup({responses: [SELLER]});
await settle();
page.fill(VALID);
page.setToken("seller-B-token");
page.submit();
await settle();
assert.equal(page.posts().length, 0);
assert.equal(page.form.hidden, true);
assert.match(page.get("error-summary-title").textContent, /account changed/i);
assert.equal(page.get("reload-page").hidden, false);
page.get("reload-page").dispatch("click");
assert.deepEqual(page.navigations, [["reload"]]);

// An account switch while the POST is pending: the result is not shown under the new account.
reply = deferred();
page = setup({responses: [SELLER, reply.promise]});
await settle();
page.fill(VALID);
page.submit();
await settle();
page.setToken("buyer-token");
reply.resolve(CREATED);
await settle();
assert.equal(page.get("product-created").hidden, true);
assert.equal(page.form.hidden, true);
assert.match(page.get("error-summary-title").textContent, /account changed/i);
assert.ok(page.form.elements.every(control => control.disabled));

// An account switch during the account check never shows the form.
reply = deferred();
page = setup({responses: [reply.promise]});
await tick();
page.setToken("other-token");
reply.resolve(SELLER);
await settle();
assert.equal(page.form.hidden, true);
assert.match(page.get("error-summary-title").textContent, /account changed/i);

// Logging out in another tab locks the form at once.
page = setup({responses: [SELLER]});
await settle();
page.setToken(null);
page.storageEvent("access_token");
assert.equal(page.form.hidden, true);
assert.equal(page.get("reload-page").hidden, false);
console.log("Account-switch checks passed: before submit, during POST, during check, other tab.");

// Task 3: a new listing in the real catalog and detail scripts, with an image URL that fails.
const PLACEHOLDER = "/static/product-placeholder.svg";
const BROKEN = "https://images.invalid/missing.jpg";
const listing = {id: "46", code: "P-6E1059D348A4CB729F", name: htmlName, description: "<b>desc</b>",
  price: 180000, thumbnail_url: BROKEN, image_url: BROKEN, stock_quantity: 10, stock_status: "in_stock"};

async function runPage(script, pathname, responses) {
  focused = null;
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element(id));
    return nodes.get(id);
  };
  const location = {pathname, search: "", assign() {}, replace() {}};
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Element("", tag)},
    window: {location, addEventListener() {}},
    location,
    localStorage: {getItem: () => null, removeItem() {}},
    sessionStorage: {getItem: () => null, setItem() {}, removeItem() {}},
    fetch: async url => {
      const next = responses.shift();
      assert.ok(next, `Unexpected request: ${url}`);
      return {status: 200, ok: true, json: async () => next};
    },
    AbortController, URLSearchParams, Intl, setTimeout, clearTimeout, console,
  });
  vm.runInContext(await read(script), context);
  await settle();
  return get;
}

let get = await runPage("products.js", "/products",
  [{data: [listing], meta: {current_page: 1, limit: 20, total: 1, total_pages: 1}}]);
const [card] = get("products-grid").children;
const [link] = card.children;
const [image, body] = link.children;
assert.equal(get("products-grid").hidden, false);
assert.equal(link.href, "/products/P-6E1059D348A4CB729F");
assert.equal(body.children[0].textContent, htmlName);
assert.equal(image.src, BROKEN);
image.dispatch("error");
assert.equal(image.src, PLACEHOLDER, "A broken catalog image falls back to the placeholder");

get = await runPage("product-detail.js", "/products/P-6E1059D348A4CB729F",
  [{...listing, stock_quantity: 0, stock_status: "out_of_stock"}]);
assert.equal(get("product-detail").hidden, false);
assert.equal(get("product-name").textContent, htmlName);
assert.equal(get("product-description").textContent, "<b>desc</b>");
assert.equal(get("product-stock").textContent, "Out of stock");
assert.equal(get("add-to-cart").disabled, true);
assert.equal(get("product-image").src, BROKEN);
get("product-image").dispatch("error");
assert.equal(get("product-image").src, PLACEHOLDER, "A broken detail image falls back to the placeholder");
console.log("Discovery checks passed: catalog card link, detail out of stock, image fallback.");
