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
  focus() { this.focused = true; }
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
  pendingIdentity = null, reviewRows = [review], reviewResults = null,
  postError = null, identityId = null, pendingPost = null,
  postCode = "ERR_VALIDATION", postStatus = 422, eligibilityFailures = 0} = {}) {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const formSection = get("review-form-section");
  get("review-rating").value = "5";
  formSection.append(get("review-login-prompt"), get("review-form"), get("review-form-status"));
  const reviewList = get("reviews-list");
  const storage = new Map(token ? [["access_token", token]] : []);
  const calls = [];
  let eligibleItems = [...eligible];
  let remainingEligibilityFailures = eligibilityFailures;
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
    URL, AbortController, setTimeout, clearTimeout,
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
        if (reviewResults) return reviewResults.length > 1 ? reviewResults.shift() : reviewResults[0];
        return success({data: reviewRows, review_count: reviewRows.length, rating: 5});
      }
      if (url === "/api/v1/auth/me") {
        return pendingIdentity
          ? pendingIdentity
          : success({id: identityId ?? (role === "seller" ? 7 : 3), role});
      }
      if (url === "/api/v1/products/US15-REVIEW/reviewable-items") {
        if (eligibilityError || remainingEligibilityFailures > 0) {
          remainingEligibilityFailures--;
          return success({error: {message: "Eligibility service unavailable."}}, 503);
        }
        const items = eligibleItems;
        eligibleItems = [];
        return success({data: items});
      }
      if (url === "/api/v1/products/US15-REVIEW/reviews" && options.method === "POST") {
        if (pendingPost) return pendingPost;
        if (postError) return success({error: {code: postCode, message: postError}}, postStatus);
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
assert.equal(page.get("review-eligibility-retry").hidden, false);

page = setup({eligibilityFailures: 1, eligible: [{order_item_id: 42, quantity: 1}]});
await settle();
await page.get("review-eligibility-retry").dispatch("click");
await settle();
assert.equal(page.get("review-form").hidden, false);
assert.equal(page.get("review-eligibility-retry").hidden, true);

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

page = setup({token: null, reviewRows: [{...review,
  media_urls: ["https://example.com/photo.jpg", "https://example.com/clip.mp4",
    "javascript:alert(1)"], seller_reply: "Thanks!", seller_replied_at: null,
}]});
await settle();
assert.equal(page.reviewList.querySelectorAll(".review-media__image").length, 1);
assert.equal(page.reviewList.querySelectorAll(".review-media__video").length, 1);
assert.equal(page.reviewList.querySelectorAll(".review-media__link").length, 2,
  "Unsafe media schemes are never rendered");
const sellerReply = page.reviewList.querySelectorAll(".review-card__reply")[0];
assert.equal(sellerReply.children.filter(node => node.tagName === "TIME").length, 0,
  "An absent seller reply timestamp never renders Invalid Date");

page = setup({reviewResults: [success({error: {message: "Reviews unavailable."}}, 503),
  success({data: [], review_count: 0, rating: 0})]});
await settle();
assert.equal(page.get("reviews-error").hidden, false);
assert.equal(page.get("reviews-retry").hidden, false);
await page.get("reviews-retry").dispatch("click");
await settle();
assert.equal(page.get("reviews-error").hidden, true);
assert.equal(page.get("reviews-summary").textContent, "No reviews yet.");

page = setup({eligible: [{order_item_id: 42, quantity: 1}]});
await settle();
page.get("review-order-item").value = "42";
page.get("review-rating").value = "0";
await page.get("review-form").dispatch("submit");
assert.equal(page.calls.filter(call => call.options.method === "POST").length, 0);
assert.ok(page.get("review-rating-error").textContent.includes("1 to 5"));
assert.equal(page.get("review-rating").focused, true);
page.get("review-rating").value = "5";
page.get("review-media-url").value = "https://example.com/photo.jpg\nhttps://example.com/clip.mp4";
await page.get("review-form").dispatch("submit");
const mediaSubmission = page.calls.find(call => call.options.method === "POST");
assert.deepEqual(JSON.parse(mediaSubmission.options.body).media_urls,
  ["https://example.com/photo.jpg", "https://example.com/clip.mp4"]);

page = setup({eligible: [{order_item_id: 42, quantity: 1}], postError: "Please check your review."});
await settle();
page.get("review-order-item").value = "42";
page.get("review-comment").value = "Keep my draft";
await page.get("review-form").dispatch("submit");
assert.equal(page.get("review-comment").value, "Keep my draft");
assert.equal(page.get("review-submit").disabled, false);
assert.equal(page.get("review-form-status").textContent, "Please check your review.");

page = setup({eligible: [{order_item_id: 42, quantity: 1}],
  postError: "This purchase was already reviewed.", postCode: "ERR_REVIEW_ALREADY_EXISTS", postStatus: 409});
await settle();
page.get("review-order-item").value = "42";
page.get("review-comment").value = "Keep rejected draft";
await page.get("review-form").dispatch("submit");
assert.equal(page.get("review-form").hidden, true);
assert.equal(page.get("review-comment").value, "Keep rejected draft");
assert.equal(page.get("review-form-status").textContent, "This purchase was already reviewed.");

page = setup({eligible: [{order_item_id: 42, quantity: 1}]});
await settle();
page.get("review-order-item").value = "42";
page.storage.set("access_token", "another-account");
await page.get("review-form").dispatch("submit");
assert.equal(page.calls.filter(call => call.options.method === "POST").length, 0,
  "A form authorized for the previous account cannot submit with a replacement token");

page = setup({role: "seller", identityId: 99});
await settle();
assert.equal(page.reviewList.querySelectorAll(".seller-reply-form").length, 0);

page = setup({role: "seller"});
await settle();
let replyForm = page.reviewList.querySelectorAll(".seller-reply-form")[0];
const replyInput = replyForm.children.find(node => node.tagName === "TEXTAREA");
replyInput.value = "   ";
await replyForm.dispatch("submit");
assert.equal(page.calls.filter(call => call.url.startsWith("/api/v1/seller/reviews/")).length, 0);
assert.equal(replyInput.focused, true);
replyInput.value = "Thanks";
page.storage.set("access_token", "different-seller");
await replyForm.dispatch("submit");
assert.equal(page.calls.filter(call => call.url.startsWith("/api/v1/seller/reviews/")).length, 0);

let finishReview;
page = setup({eligible: [{order_item_id: 42, quantity: 1}],
  pendingPost: new Promise(resolve => { finishReview = resolve; })});
await settle();
page.get("review-order-item").value = "42";
const submitting = page.get("review-form").dispatch("submit");
await settle();
assert.equal(page.get("review-submit").disabled, true);
await page.get("review-form").dispatch("submit");
assert.equal(page.calls.filter(call => call.options.method === "POST").length, 1);
await page.get("logout-button").dispatch("click");
finishReview(success({data: {id: 72}}, 201));
await submitting;
assert.equal(page.get("review-form").hidden, true);
assert.equal(page.get("review-form-status").textContent, "");

console.log("Product detail checks passed: eligibility, media, retry, validation, drafts, and account isolation.");
