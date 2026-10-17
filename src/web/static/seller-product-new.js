"use strict";

// US06 seller product form. The API enforces the seller role; this page only guides the user.
const PAGE_PATH = "/seller/products/new";
const LOGIN_URL = `/login?return_to=${encodeURIComponent(PAGE_PATH)}`;
const CREATE_URL = "/api/v1/seller/products";
const REQUEST_TIMEOUT_MS = 10000;
const DRAFT_KEY = "seller-product-draft";
const FIELDS = ["name", "description", "price", "stock_quantity", "image_url"];
const LABELS = {
  name: "Product name",
  description: "Description",
  price: "Price",
  stock_quantity: "Stock quantity",
  image_url: "Image URL",
};
const LIMITS = {
  name: 200,
  description: 3000,
  image_url: 2048,
  price: 1000000000,
  stock_quantity: 1000000,
};
const FIELDS_TITLE = "Please correct the highlighted fields.";
const IMAGE_URL_MESSAGE = "Image URL must be an absolute http:// or https:// address.";
const NAME_LINE_MESSAGE = "Product name must be one line, without tabs or control characters.";
// Same rules as the server: text made only of invisible characters (zero-width spaces,
// Hangul fillers, braille blanks) counts as empty, and a name stays on one line.
const VISIBLE_CHARACTER = /[^\s\p{Cc}\p{Cf}\p{Z}\p{Cn}ᅟᅠ⠀ㅤﾠ]/u;
const LINE_BREAK_OR_CONTROL = /[\p{Cc}\p{Zl}\p{Zp}]/u;
const UNCONFIRMED_MESSAGE =
  "The server did not confirm the listing (network error or timeout). Your values are kept. " +
  "The listing may already exist, so check before submitting again.";
const ACCOUNT_CHANGED_MESSAGE =
  "Your account changed in another tab. Reload this page before creating a product.";

const form = document.getElementById("product-form");
const elements = {
  accountStatus: document.getElementById("account-status"),
  accountRetry: document.getElementById("account-retry"),
  forbidden: document.getElementById("forbidden"),
  summary: document.getElementById("error-summary"),
  summaryTitle: document.getElementById("error-summary-title"),
  summaryList: document.getElementById("error-summary-list"),
  reload: document.getElementById("reload-page"),
  submitStatus: document.getElementById("submit-status"),
  created: document.getElementById("product-created"),
  createdName: document.getElementById("created-name"),
  createdCode: document.getElementById("created-code"),
  createdStock: document.getElementById("created-stock"),
  viewProduct: document.getElementById("view-product"),
  createAnother: document.getElementById("create-another"),
};

// The token that loaded this page; every request uses it, never a newer one.
let contextToken = null;
let contextChanged = false;
let accountId = null;
let ready = false;
let pending = false;

function timeoutSignal() {
  return typeof AbortSignal !== "undefined" && AbortSignal.timeout
    ? AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    : undefined;
}

function authHeaders() {
  return { Accept: "application/json", Authorization: `Bearer ${contextToken}` };
}

function setDisabled(value) {
  for (const control of form.elements) control.disabled = value;
}

/** Stop for good once the stored token is no longer the one this page was loaded with. */
function accountChanged() {
  if (!contextChanged && localStorage.getItem("access_token") === contextToken) return false;
  contextChanged = true;
  ready = false;
  setDisabled(true);
  form.hidden = true;
  elements.created.hidden = true;
  elements.submitStatus.textContent = "";
  clearErrors();
  showSummary(ACCOUNT_CHANGED_MESSAGE, []);
  elements.reload.hidden = false;
  return true;
}

function messagesOf(value) {
  if (Array.isArray(value)) return value.map(String);
  return typeof value === "string" ? [value] : [];
}

function clearErrors() {
  for (const name of FIELDS) {
    form.elements[name].removeAttribute("aria-invalid");
    const node = document.getElementById(`${name}-error`);
    node.textContent = "";
    node.hidden = true;
  }
  elements.summary.hidden = true;
  elements.summaryTitle.textContent = "";
  elements.summaryList.replaceChildren();
  elements.reload.hidden = true;
}

function showSummary(title, lines) {
  elements.summaryTitle.textContent = title;
  elements.summaryList.replaceChildren(
    ...lines.map((line) => {
      const item = document.createElement("li");
      item.textContent = line;
      return item;
    }),
  );
  elements.summary.hidden = false;
}

/** Show each message beside its field; anything else (`_form`) goes to the summary only. */
function showErrors(fields, title) {
  const lines = [];
  let firstInvalid = null;
  for (const name of FIELDS) {
    const messages = messagesOf(fields[name]);
    if (!messages.length) continue;
    const node = document.getElementById(`${name}-error`);
    node.textContent = messages.join(" ");
    node.hidden = false;
    form.elements[name].setAttribute("aria-invalid", "true");
    lines.push(...messages);
    firstInvalid = firstInvalid || form.elements[name];
  }
  for (const [name, value] of Object.entries(fields)) {
    if (!FIELDS.includes(name)) lines.push(...messagesOf(value).filter((line) => line !== title));
  }
  showSummary(title || FIELDS_TITLE, lines);
  (firstInvalid || elements.summary).focus();
}

function readText(name, errors) {
  const value = form.elements[name].value.trim();
  if (!value) {
    errors[name] = [`${LABELS[name]} is required.`];
  } else if ([...value].length > LIMITS[name]) {
    errors[name] = [`${LABELS[name]} must be at most ${LIMITS[name]} characters.`];
  } else if (name !== "image_url" && !VISIBLE_CHARACTER.test(value)) {
    errors[name] = [`${LABELS[name]} is required.`];
  } else if (name === "name" && LINE_BREAK_OR_CONTROL.test(value)) {
    errors[name] = [NAME_LINE_MESSAGE];
  }
  return value;
}

/** Whole numbers only: parseInt would quietly turn "1.5" into 1. */
function readWhole(name, errors, min, messages) {
  const input = form.elements[name];
  const raw = input.value.trim();
  if (!raw) {
    errors[name] = [input.validity && input.validity.badInput ? messages.type : `${LABELS[name]} is required.`];
    return null;
  }
  if (!/^-?\d+$/.test(raw)) {
    errors[name] = [messages.type];
    return null;
  }
  const value = Number(raw);
  if (value < min) {
    errors[name] = [messages.min];
    return null;
  }
  if (!Number.isSafeInteger(value) || value > LIMITS[name]) {
    errors[name] = [messages.max];
    return null;
  }
  return value;
}

function isHttpUrl(value) {
  if (/\s/.test(value) || !/^https?:\/\/[^/]/i.test(value)) return false;
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && Boolean(url.hostname);
  } catch {
    return false;
  }
}

function readForm() {
  const errors = {};
  const body = {
    name: readText("name", errors),
    description: readText("description", errors),
    price: readWhole("price", errors, 1, {
      type: "Price must be a whole number of VND.",
      min: "Price must be greater than 0 ₫.",
      max: "Price must be at most 1.000.000.000 ₫.",
    }),
    stock_quantity: readWhole("stock_quantity", errors, 0, {
      type: "Stock quantity must be a whole number.",
      min: "Stock quantity must be 0 or more.",
      max: "Stock quantity must be at most 1.000.000.",
    }),
    image_url: readText("image_url", errors),
  };
  if (!errors.image_url && !isHttpUrl(body.image_url)) errors.image_url = [IMAGE_URL_MESSAGE];
  return { body, errors };
}

/** Keep the typed values across a login, for the same account only. */
function saveDraft() {
  const values = {};
  for (const name of FIELDS) values[name] = form.elements[name].value;
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ account_id: accountId, values }));
  } catch {
    // Storage can be unavailable; the user then types the values again.
  }
}

function restoreDraft() {
  let draft = null;
  try {
    draft = JSON.parse(sessionStorage.getItem(DRAFT_KEY));
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    return false;
  }
  if (!draft || draft.account_id !== accountId || typeof draft.values !== "object") return false;
  for (const name of FIELDS) {
    if (typeof draft.values[name] === "string") form.elements[name].value = draft.values[name];
  }
  return true;
}

function showForbidden() {
  elements.accountStatus.textContent = "This account cannot create product listings.";
  elements.forbidden.hidden = false;
  form.hidden = true;
}

async function init() {
  if (contextChanged) return;
  ready = false;
  setDisabled(true);
  contextToken = localStorage.getItem("access_token");
  elements.accountRetry.hidden = true;
  elements.accountStatus.textContent = "Checking your account…";
  if (!contextToken) {
    location.replace(LOGIN_URL);
    return;
  }
  try {
    const response = await fetch("/api/v1/auth/me", {
      headers: authHeaders(),
      signal: timeoutSignal(),
    });
    const user = await response.json().catch(() => null);
    if (accountChanged()) return;
    if (response.status === 401) {
      location.replace(LOGIN_URL);
      return;
    }
    if (!response.ok || !user) throw new Error("Account check failed.");
    if (user.role !== "seller") {
      showForbidden();
      return;
    }
    accountId = user.id;
    const restored = restoreDraft();
    elements.accountStatus.textContent = restored
      ? `Signed in as ${user.name}. Your entries were restored; review them and create the listing.`
      : `Signed in as ${user.name}.`;
    form.hidden = false;
    setDisabled(false);
    ready = true;
  } catch {
    if (accountChanged()) return;
    elements.accountStatus.textContent = "We could not check your account. Please try again.";
    elements.accountRetry.hidden = false;
  }
}

function showCreated(product) {
  form.hidden = true;
  elements.createdName.textContent = product.name;
  elements.createdCode.textContent = product.code;
  elements.viewProduct.href = `/products/${encodeURIComponent(product.code)}`;
  elements.createdStock.textContent =
    product.stock_quantity > 0
      ? `${product.stock_quantity} in stock. Buyers can find it in the catalog.`
      : "Stock is 0: the product page shows Out of stock, and the listing stays out of the catalog until it has stock.";
  elements.created.hidden = false;
  elements.created.focus();
}

function handleResponse(response, payload) {
  const error = payload && payload.error;
  if (response.status === 201 && payload && payload.data && typeof payload.data.code === "string") {
    showCreated(payload.data);
    return;
  }
  if (response.status === 401) {
    saveDraft();
    location.assign(LOGIN_URL);
    return;
  }
  if (response.status === 422 && error && error.fields && typeof error.fields === "object") {
    showErrors(error.fields, error.message || FIELDS_TITLE);
    return;
  }
  if (response.ok) {
    showErrors({ _form: [UNCONFIRMED_MESSAGE] }, "The listing was not confirmed.");
    return;
  }
  const message = (error && error.message) || "Please try again.";
  showErrors({ _form: [message] }, "The listing was not created.");
}

async function submitProduct() {
  if (pending || !ready || accountChanged()) return;
  clearErrors();
  const { body, errors } = readForm();
  if (Object.keys(errors).length) {
    showErrors(errors, FIELDS_TITLE);
    return;
  }
  pending = true;
  setDisabled(true);
  elements.submitStatus.textContent = "Creating listing...";
  try {
    // A lost response may follow a committed insert, so a failed POST is never resent here.
    const response = await fetch(CREATE_URL, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: timeoutSignal(),
    });
    const payload = await response.json().catch(() => null);
    if (accountChanged()) return;
    handleResponse(response, payload);
  } catch {
    if (accountChanged()) return;
    showErrors({ _form: [UNCONFIRMED_MESSAGE] }, "The listing was not confirmed.");
  } finally {
    pending = false;
    if (!contextChanged) {
      elements.submitStatus.textContent = "";
      setDisabled(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitProduct();
});
elements.createAnother.addEventListener("click", () => {
  if (accountChanged()) return;
  form.reset();
  clearErrors();
  elements.created.hidden = true;
  form.hidden = false;
  form.elements.name.focus();
});
elements.accountRetry.addEventListener("click", init);
elements.reload.addEventListener("click", () => location.reload());
window.addEventListener("storage", (event) => {
  if (event.key === "access_token" || event.key === null) accountChanged();
});
init();
