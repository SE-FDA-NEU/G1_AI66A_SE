// Run with: node tests/product_detail_ui.mjs
// Execute product-detail.js against a small DOM and network test double.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../src/web/static/product-detail.js", import.meta.url), "utf8");

class Element {
  constructor(tag = "div") {
    Object.assign(this, {
      tagName: tag.toUpperCase(), hidden: false, disabled: false, textContent: "",
      value: "", className: "", children: [], handlers: {}, parentNode: null,
    });
  }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  setAttribute(name, value) { this[name] = value; }
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
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  querySelectorAll(classSelector) {
    const className = classSelector.slice(1);
    return this.children.flatMap(child => [
      ...(child.className.split(/\s+/).includes(className) ? [child] : []),
      ...child.querySelectorAll(classSelector),
    ]);
  }
  async dispatch(name) {
    const event = {preventDefault() {}};
    await Promise.all((this.handlers[name] ?? []).map(handler => handler(event)));
  }
}

const success = (payload, status = 200) => ({
  status, ok: status >= 200 && status < 300, json: async () => payload,
});
const review = {
  id: 71, rating: 5, created_at: "2026-10-20T10:00:00Z",
  comment: "Good product", seller_reply: null,
};
const settle = async () => {
  for (let i = 0; i < 12; i += 1) await new Promise(resolve => setImmediate(resolve));
};

function setup({role = "buyer", token = "test-token", eligible = [], eligibilityError = false,
  pendingIdentity = null} = {}) {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const formSection = get("review-form-section");
  formSection.append(get("review-login-prompt"), get("review-form"), get("review-form-status"));
  const reviewList = get("reviews-list");
  const storage = new Map(token ? [["access_token", token]] : []);
  const calls = [];
  let eligibleItems = [...eligible];
  const location = {pathname: "/products/US15-REVIEW", search: "", assign() {}};
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Element(tag)},
    window: {location},
    localStorage: {
      getItem: key => storage.get(key) ?? null,
      removeItem: key => storage.delete(key),
    },
    sessionStorage: {getItem: () => null, removeItem() {}, setItem() {}},
    URLSearchParams,
    Intl,
    Date,
    encodeURIComponent,
    decodeURIComponent,
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      if (url === "/api/v1/products/US15-REVIEW") {
        return success({id: 10, seller_id: 7, name: "Review product", price: 100,
          stock_quantity: 4, review_count: 1, rating: 5});
      }
      if (url === "/api/v1/products/US15-REVIEW/reviews" && options.method !== "POST") {
        return success({data: [review], review_count: 1, rating: 5});
      }
      if (url === "/api/v1/auth/me") {
        return pendingIdentity
          ? pendingIdentity
          : success({id: role === "seller" ? 7 : 3, role});
      }
      if (url === "/api/v1/products/US15-REVIEW/reviewable-items") {
        if (eligibilityError) return success({error: {message: "Eligibility service unavailable."}}, 503);
        const items = eligibleItems;
        eligibleItems = [];
        return success({data: items});
      }
      if (url === "/api/v1/products/US15-REVIEW/reviews" && options.method === "POST") {
        return success({data: {id: 72}});
      }
      if (url.startsWith("/api/v1/seller/reviews/")) return success({data: {}});
      throw new Error(`Unexpected request: ${url}`);
    },
  });
  vm.runInContext(source, context);
  return {get, calls, storage, reviewList};
}

let page = setup({eligible: []});
await settle();
assert.equal(page.get("review-form").hidden, true);
assert.equal(page.get("review-form-status").textContent,
  "There are no completed, unreviewed purchases for this product.");
assert.equal(page.get("review-form-status").parentNode, page.get("review-form-section"),
  "Eligibility feedback is outside the hidden form");

page = setup({eligibilityError: true});
await settle();
assert.equal(page.get("review-form").hidden, true);
assert.equal(page.get("review-form-status").textContent, "Eligibility service unavailable.");

page = setup({eligible: [{order_item_id: 42, quantity: 1}]});
await settle();
assert.equal(page.get("review-form").hidden, false);
page.get("review-order-item").value = "42";
await page.get("review-form").dispatch("submit");
await settle();
assert.ok(page.calls.some(call => call.options.method === "POST"
  && call.url.endsWith("/reviews")), "The buyer review was submitted");
assert.equal(page.get("review-form").hidden, true, "No review controls remain after the last item is reviewed");
assert.equal(page.get("review-form-status").textContent, "Your verified-purchase review was submitted.");

page = setup({role: "seller"});
await settle();
const staleReplyForm = page.reviewList.children[0].querySelectorAll(".seller-reply-form")[0];
assert.ok(staleReplyForm, "The owning seller has reply controls");
await page.get("logout-button").dispatch("click");
assert.equal(page.storage.has("access_token"), false);
assert.equal(page.reviewList.querySelectorAll(".seller-reply-form").length, 0,
  "Logout immediately removes seller reply controls");
const replyCountBeforeSubmit = page.calls.filter(call => call.url.startsWith("/api/v1/seller/reviews/")).length;
await staleReplyForm.dispatch("submit");
assert.equal(page.calls.filter(call => call.url.startsWith("/api/v1/seller/reviews/")).length,
  replyCountBeforeSubmit, "A stale reply handler does not send the logged-out token");

let resolveIdentity;
const delayedIdentity = new Promise(resolve => { resolveIdentity = resolve; });
page = setup({role: "seller", pendingIdentity: delayedIdentity});
await settle();
await page.get("logout-button").dispatch("click");
resolveIdentity(success({id: 7, role: "seller"}));
await settle();
assert.equal(page.reviewList.querySelectorAll(".seller-reply-form").length, 0,
  "A pending identity response cannot restore reply controls after logout");

console.log("Product detail checks passed: eligibility states, final review feedback, logout, and stale identity.");
