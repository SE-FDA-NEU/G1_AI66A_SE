// Run with `node tests/product_detail_variants.mjs` to exercise the actual product-detail script.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(
  new URL("../src/web/static/product-detail.js", import.meta.url),
  "utf8",
);
const tick = async () => {
  for (let index = 0; index < 8; index += 1) {
    await new Promise(setImmediate);
  }
};

class Element {
  constructor(id = "") {
    Object.assign(this, {
      id,
      hidden: false,
      disabled: false,
      value: "",
      max: "",
      textContent: "",
      className: "",
      children: [],
      handlers: {},
      style: {},
    });
  }

  addEventListener(name, handler) {
    (this.handlers[name] ??= []).push(handler);
  }

  append(...items) {
    this.children.push(...items);
  }

  replaceChildren(...items) {
    this.children = items;
  }

  querySelectorAll() {
    return [];
  }

  async dispatch(name) {
    const event = { preventDefault() {} };
    for (const handler of this.handlers[name] ?? []) {
      await handler(event);
    }
  }
}

const elements = new Map();
const getElement = (id) => {
  if (!elements.has(id)) elements.set(id, new Element(id));
  return elements.get(id);
};
const local = new Map();
const session = new Map();
const navigation = [];
const product = {
  id: "41",
  code: "P-VARIANTS",
  name: "Color options",
  description: "Test listing",
  price: 30_000,
  stock_quantity: 0,
  has_variants: true,
  seller_id: 8,
  variants: [
    { id: 11, name: "Black", price: 30_000, stock_quantity: 2, image_url: "/black.jpg" },
    { id: 22, name: "White", price: 40_000, stock_quantity: 1, image_url: "/white.jpg" },
  ],
};

const context = vm.createContext({
  document: {
    getElementById: getElement,
    createElement: (tag) => Object.assign(new Element(), { tagName: tag }),
  },
  window: {
    location: {
      pathname: "/products/P-VARIANTS",
      search: "",
      assign: (url) => navigation.push(url),
    },
  },
  localStorage: {
    getItem: (key) => local.get(key) ?? null,
    removeItem: (key) => local.delete(key),
  },
  sessionStorage: {
    getItem: (key) => session.get(key) ?? null,
    setItem: (key, value) => session.set(key, value),
    removeItem: (key) => session.delete(key),
  },
  URLSearchParams,
  Intl,
  atob,
  decodeURIComponent,
  fetch: async (url) => {
    const payload = url.includes("/reviews")
      ? { data: [], rating: 0, review_count: 0 }
      : product;
    return { ok: true, status: 200, json: async () => payload };
  },
});

vm.runInContext(source, context);
await tick();

const variantSelect = getElement("product-variant");
assert.equal(variantSelect.children.length, 2);
assert.equal(variantSelect.value, "11");
variantSelect.value = "22";
await variantSelect.dispatch("change");
assert.equal(
  getElement("product-price").textContent,
  new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(40_000),
);
assert.equal(getElement("product-image").src, "/white.jpg");
assert.equal(getElement("product-stock").textContent, "In Stock (1 available)");
assert.equal(getElement("product-quantity").max, "1");

await getElement("add-to-cart-form").dispatch("submit");
assert.equal(navigation.length, 1);
const returnTo = new URL(navigation[0], "http://localhost").searchParams.get("return_to");
assert.equal(new URL(returnTo, "http://localhost").searchParams.get("variant_id"), "22");
