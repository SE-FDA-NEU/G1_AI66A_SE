// Run with: node tests/catalog_ui.mjs
// Verifies products.js catalog UI logic: combined filters, price validation,
// sort modes, pagination, empty states, error retry, and navigation controls.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/products.js", import.meta.url), "utf8");

class Element {
  constructor(tag = "div") {
    Object.assign(this, {
      tagName: tag.toUpperCase(),
      id: "",
      className: "",
      textContent: "",
      title: "",
      src: "",
      alt: "",
      href: "",
      value: "",
      checked: true,
      disabled: false,
      hidden: false,
      children: [],
      handlers: {},
      parentNode: null,
    });
  }
  addEventListener(name, handler) {
    (this.handlers[name] ??= []).push(handler);
  }
  append(...nodes) {
    for (const node of nodes) {
      node.parentNode = this;
      this.children.push(node);
    }
  }
  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this.append(...nodes);
  }
  dispatch(name, event = {}) {
    const evt = { preventDefault() {}, target: this, ...event };
    for (const handler of this.handlers[name] ?? []) {
      handler(evt);
    }
  }
}

const priceFmt = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });
const settle = async () => {
  for (let i = 0; i < 15; i += 1) await new Promise((resolve) => setImmediate(resolve));
};

function createJwt(role, id = 1) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ sub: String(id), role }));
  return `${header}.${payload}.signature`;
}

function sampleProductsPayload({ total = 2, total_pages = 1, current_page = 1, data = null } = {}) {
  const items = data !== null ? data : [
    {
      id: "1",
      code: "P-LAP-PRO",
      name: "Pro Ultrabook Laptop",
      description: "High performance laptop",
      price: 25000000,
      stock_quantity: 10,
      stock_status: "in_stock",
      thumbnail_url: "/img/p1.jpg",
      rating: 4.8,
      review_count: 12,
      sales_count: 50,
      category_id: 3,
      seller_id: 1,
    },
    {
      id: "2",
      code: "P-ACC-MOUSE",
      name: "Ergonomic Optical Mouse",
      description: "Wireless mouse",
      price: 450000,
      stock_quantity: 3,
      stock_status: "low_stock",
      thumbnail_url: null,
      rating: 4.5,
      review_count: 8,
      sales_count: 120,
      category_id: 4,
      seller_id: 1,
    },
  ];
  return {
    data: items,
    meta: {
      total,
      total_items: total,
      total_pages,
      current_page,
      limit: 20,
    },
  };
}

function setup({
  token = null,
  productsResponse = null,
  failFetch = false,
} = {}) {
  let shouldFail = failFetch;
  const nodes = new Map();
  const get = (id) => {
    if (!nodes.has(id)) {
      const tag = id.includes("search-input") || id.includes("price") ? "input"
        : id.includes("category") || id.includes("seller") || id.includes("rating") || id.includes("sort") ? "select"
        : id.includes("button") || id.includes("apply") || id.includes("reset") || id.includes("previous") || id.includes("next") ? "button"
        : id.includes("grid") || id.includes("loading") ? "ul"
        : id.includes("link") ? "a"
        : "div";
      const el = new Element(tag);
      el.id = id;
      nodes.set(id, el);
    }
    return nodes.get(id);
  };

  const storage = new Map(token ? [["access_token", token]] : []);
  const calls = [];
  let currentProductsData = productsResponse || sampleProductsPayload();

  const context = vm.createContext({
    document: {
      getElementById: get,
      createElement: (tag) => new Element(tag),
    },
    window: {
      location: { pathname: "/products", search: "", href: "/products" },
    },
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, val) => storage.set(key, String(val)),
      removeItem: (key) => storage.delete(key),
    },
    URLSearchParams,
    Intl,
    AbortController,
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
    encodeURIComponent,
    setTimeout,
    clearTimeout,
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), options });
      if (shouldFail && url.includes("/api/v1/products")) {
        return {
          ok: false,
          status: 500,
          json: async () => ({ error: { code: "ERR_DATABASE_FAILURE", message: "Database down" } }),
        };
      }
      if (url.includes("/api/v1/categories")) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { id: 1, name: "Electronics", parent_id: null },
            { id: 2, name: "Computers", parent_id: 1 },
            { id: 3, name: "Laptops", parent_id: 2 },
          ],
        };
      }
      if (url.includes("/api/v1/sellers")) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { id: 1, name: "Seller One" },
            { id: 2, name: "Seller Two" },
          ],
        };
      }
      if (url.includes("/api/v1/products")) {
        return {
          ok: true,
          status: 200,
          json: async () => (typeof currentProductsData === "function" ? currentProductsData(url) : currentProductsData),
        };
      }
      throw new Error(`Unexpected URL in fetch double: ${url}`);
    },
  });

  vm.runInContext(source, context);

  return {
    get,
    calls,
    storage,
    setProductsResponse: (resp) => { currentProductsData = resp; },
    setFailFetch: (fail) => { shouldFail = fail; },
  };
}

// ==============================================================================
// 1. Initial Render and Product Card Formatting
// ==============================================================================
{
  const ui = setup();
  await settle();

  // Categories and Sellers options populated
  const catSelect = ui.get("filter-category");
  assert.ok(catSelect.children.length >= 4, "Category options populated");
  assert.equal(catSelect.children[0].textContent, "All categories");

  const sellerSelect = ui.get("filter-seller");
  assert.ok(sellerSelect.children.length >= 3, "Seller options populated");
  assert.equal(sellerSelect.children[0].textContent, "All sellers");

  // Grid has 2 rendered product cards
  const grid = ui.get("products-grid");
  assert.equal(grid.hidden, false, "Product grid is displayed");
  assert.equal(grid.children.length, 2, "Renders 2 product cards");

  // First product card checks
  const card1 = grid.children[0];
  const link = card1.children[0];
  assert.equal(link.href, "/products/P-LAP-PRO");
  const body = link.children[1];
  assert.equal(body.children[0].textContent, "Pro Ultrabook Laptop");
  assert.equal(body.children[1].textContent, priceFmt.format(25000000));
  assert.equal(body.children[2].textContent, "★ 4.8");
  assert.equal(body.children[3].textContent, "In Stock");

  // Second product card (low stock badge)
  const card2 = grid.children[1];
  const body2 = card2.children[0].children[1];
  assert.equal(body2.children[3].textContent, "Only 3 left");

  // Pagination is configured
  assert.equal(ui.get("products-page").textContent, "Page 1 of 1");
  assert.equal(ui.get("products-pagination").hidden, true, "Pagination hidden when total_pages <= 1");
}

// ==============================================================================
// 2. Combined Filters
// ==============================================================================
{
  const ui = setup();
  await settle();

  ui.get("product-search-input").value = "keyboard";
  ui.get("filter-category").value = "2";
  ui.get("filter-seller").value = "1";
  ui.get("filter-min-price").value = "500000";
  ui.get("filter-max-price").value = "2000000";
  ui.get("filter-rating").value = "4.0";
  ui.get("filter-in-stock").checked = false;
  ui.get("catalog-sort").value = "price_asc";

  // Dispatch apply filters
  ui.get("apply-filters").dispatch("click");
  await settle();

  const lastCall = ui.calls[ui.calls.length - 1];
  assert.ok(lastCall.url.includes("/api/v1/products"), "Products endpoint requested");
  assert.ok(lastCall.url.includes("search=keyboard"), "Search query included");
  assert.ok(lastCall.url.includes("category_id=2"), "Category ID included");
  assert.ok(lastCall.url.includes("seller_id=1"), "Seller ID included");
  assert.ok(lastCall.url.includes("min_price=500000"), "Min price included");
  assert.ok(lastCall.url.includes("max_price=2000000"), "Max price included");
  assert.ok(lastCall.url.includes("min_rating=4.0"), "Min rating included");
  assert.ok(lastCall.url.includes("in_stock=false"), "In stock false included");
  assert.ok(lastCall.url.includes("sort=price_asc"), "Sort mode included");
}

// ==============================================================================
// 3. Price Range Validation (Invalid and Valid)
// ==============================================================================
{
  const ui = setup();
  await settle();
  const initialCallsCount = ui.calls.length;

  // Set invalid price bounds: min > max
  ui.get("filter-min-price").value = "500000";
  ui.get("filter-max-price").value = "100000";

  ui.get("apply-filters").dispatch("click");
  await settle();

  // Price error is displayed and network request blocked
  assert.equal(ui.get("price-error").hidden, false, "Price error is shown");
  assert.equal(ui.get("price-error").textContent, "Minimum price cannot be greater than maximum price.");
  assert.equal(ui.calls.length, initialCallsCount, "No network request made with invalid price bounds");

  // Correct price bounds
  ui.get("filter-max-price").value = "900000";
  ui.get("apply-filters").dispatch("click");
  await settle();

  assert.equal(ui.get("price-error").hidden, true, "Price error is hidden when bounds are valid");
  assert.equal(ui.get("price-error").textContent, "");
  assert.ok(ui.calls.length > initialCallsCount, "Network request sent with valid price bounds");
}

// ==============================================================================
// 4. Every Supported Sort Mode
// ==============================================================================
{
  const sortModes = ["newest", "bestselling", "price_asc", "price_desc", "rating_desc"];
  for (const sort of sortModes) {
    const ui = setup();
    await settle();

    ui.get("catalog-sort").value = sort;
    ui.get("catalog-sort").dispatch("change");
    await settle();

    const lastCall = ui.calls[ui.calls.length - 1];
    assert.ok(lastCall.url.includes(`sort=${sort}`), `Requested sort mode ${sort}`);
  }
}

// ==============================================================================
// 5. Pagination Boundaries
// ==============================================================================
{
  const ui = setup({
    productsResponse: (url) => {
      const params = new URL(url, "http://localhost").searchParams;
      const page = Number(params.get("page") || "1");
      return sampleProductsPayload({ total: 45, total_pages: 3, current_page: page });
    },
  });
  await settle();

  // Page 1: previous disabled, next enabled
  assert.equal(ui.get("products-pagination").hidden, false, "Pagination visible when total_pages > 1");
  assert.equal(ui.get("products-previous").disabled, true, "Previous button disabled on page 1");
  assert.equal(ui.get("products-next").disabled, false, "Next button enabled on page 1");
  assert.equal(ui.get("products-page").textContent, "Page 1 of 3");

  // Click Next -> Page 2
  ui.get("products-next").dispatch("click");
  await settle();

  assert.equal(ui.get("products-previous").disabled, false, "Previous button enabled on page 2");
  assert.equal(ui.get("products-next").disabled, false, "Next button enabled on page 2");
  assert.equal(ui.get("products-page").textContent, "Page 2 of 3");

  // Click Next -> Page 3 (last page boundary)
  ui.get("products-next").dispatch("click");
  await settle();

  assert.equal(ui.get("products-previous").disabled, false, "Previous button enabled on page 3");
  assert.equal(ui.get("products-next").disabled, true, "Next button disabled on last page");
  assert.equal(ui.get("products-page").textContent, "Page 3 of 3");

  // Click Previous -> Page 2
  ui.get("products-previous").dispatch("click");
  await settle();
  assert.equal(ui.get("products-page").textContent, "Page 2 of 3");
}

// ==============================================================================
// 6. Empty Results (With and Without Active Filters) & Reset
// ==============================================================================
{
  // 6A. Empty results with active filters
  const ui = setup({
    productsResponse: sampleProductsPayload({ total: 0, total_pages: 0, current_page: 1, data: [] }),
  });
  await settle();

  // Apply a filter
  ui.get("product-search-input").value = "nonexistent-item";
  ui.get("apply-filters").dispatch("click");
  await settle();

  assert.equal(ui.get("products-grid").hidden, true, "Grid hidden on empty results");
  assert.equal(ui.get("products-empty").hidden, false, "Empty state container visible");
  assert.equal(
    ui.get("products-empty-message").textContent,
    "No products match your search or filter criteria. Try adjusting or clearing your filters."
  );
  assert.equal(ui.get("products-reset-empty").hidden, false, "Reset filters button displayed in empty state");

  // Click reset empty button
  ui.get("products-reset-empty").dispatch("click");
  await settle();

  assert.equal(ui.get("product-search-input").value, "", "Search input cleared on reset");
  assert.equal(ui.get("filter-category").value, "", "Category reset");

  // 6B. Unfiltered empty catalog
  const ui2 = setup({
    productsResponse: sampleProductsPayload({ total: 0, total_pages: 0, current_page: 1, data: [] }),
  });
  await settle();

  assert.equal(ui2.get("products-empty").hidden, false);
  assert.equal(ui2.get("products-empty-message").textContent, "No products available at the moment.");
  assert.equal(ui2.get("products-reset-empty").hidden, true, "Reset button hidden when no filters active");
}

// ==============================================================================
// 7. Error Handling and Retry
// ==============================================================================
{
  const ui = setup({ failFetch: true });
  await settle();

  assert.equal(ui.get("products-error").hidden, false, "Error container shown on fetch failure");
  assert.equal(ui.get("products-grid").hidden, true, "Grid hidden on error");
  assert.equal(ui.get("products-retry").disabled, false, "Retry button enabled");

  // Change to succeeding responses and click retry
  const callCountBeforeRetry = ui.calls.length;
  ui.setFailFetch(false);
  ui.setProductsResponse(sampleProductsPayload());
  ui.get("products-retry").dispatch("click");
  await settle();

  assert.ok(ui.calls.length > callCountBeforeRetry, "Retry triggered new fetch");
  assert.equal(ui.get("products-error").hidden, true, "Error container hidden after successful retry");
  assert.equal(ui.get("products-grid").hidden, false, "Grid displayed after retry");
}

// ==============================================================================
// 8. Navigation Authentication and Role-based Links
// ==============================================================================
{
  // Guest
  const guestUi = setup({ token: null });
  await settle();
  assert.equal(guestUi.get("login-link").hidden, false, "Login link visible for guest");
  assert.equal(guestUi.get("logout-button").hidden, true, "Logout button hidden for guest");
  assert.equal(guestUi.get("buyer-orders-link").hidden, true, "Buyer orders hidden for guest");
  assert.equal(guestUi.get("seller-orders-link").hidden, true, "Seller orders hidden for guest");

  // Buyer
  const buyerUi = setup({ token: createJwt("buyer", 42) });
  await settle();
  assert.equal(buyerUi.get("login-link").hidden, true, "Login link hidden for buyer");
  assert.equal(buyerUi.get("logout-button").hidden, false, "Logout button visible for buyer");
  assert.equal(buyerUi.get("buyer-orders-link").hidden, false, "Buyer orders visible for buyer");
  assert.equal(buyerUi.get("seller-orders-link").hidden, true, "Seller orders hidden for buyer");

  // Seller
  const sellerUi = setup({ token: createJwt("seller", 99) });
  await settle();
  assert.equal(sellerUi.get("login-link").hidden, true, "Login link hidden for seller");
  assert.equal(sellerUi.get("logout-button").hidden, false, "Logout button visible for seller");
  assert.equal(sellerUi.get("buyer-orders-link").hidden, true, "Buyer orders hidden for seller");
  assert.equal(sellerUi.get("seller-orders-link").hidden, false, "Seller orders visible for seller");
  assert.equal(sellerUi.get("seller-new-product-link").hidden, false, "Create product visible for seller");
}

console.log("Catalog UI checks passed (combined filters, price validation, sort modes, pagination, empty states, error retry, navigation).");
