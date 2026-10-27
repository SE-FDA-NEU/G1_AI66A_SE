"use strict";

const CART_URL = "/api/v1/cart";
const CART_ITEMS_URL = "/api/v1/cart/items";
const CHECKOUT_URL = "/checkout";
const LOGIN_URL = `/login?return_to=${encodeURIComponent("/cart")}`;
const ACCESS_TOKEN_KEY = "access_token";
const REQUEST_TIMEOUT_MS = 10000;
const PLACEHOLDER_IMAGE = "/static/product-placeholder.svg";
const THUMBNAIL_SIZE_PX = 96;

const LOAD_ERROR_MESSAGE = "Unable to load your cart. Please try again.";
const CHANGE_ERROR_MESSAGE = "We could not update your cart. Please try again.";
const INVALID_QUANTITY_MESSAGE = "Enter a whole number of at least 1.";
const BUYER_ONLY_MESSAGE = "The cart is for buyer accounts. Log in with a buyer account to shop.";

const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

const elements = {
  status: document.getElementById("cart-status"),
  loading: document.getElementById("cart-loading"),
  content: document.getElementById("cart-content"),
  lines: document.getElementById("cart-lines"),
  total: document.getElementById("cart-total"),
  totalLabel: document.getElementById("cart-total-label"),
  checkout: document.getElementById("checkout-button"),
  checkoutBlocked: document.getElementById("checkout-blocked"),
  empty: document.getElementById("cart-empty"),
  emptyTotal: document.getElementById("cart-empty-total"),
  error: document.getElementById("cart-error"),
  errorMessage: document.getElementById("cart-error-message"),
  retry: document.getElementById("cart-retry"),
  logout: document.getElementById("logout-button"),
};

const accountToken = localStorage.getItem(ACCESS_TOKEN_KEY);
let accountInvalidated = false;
let changingCart = false;
let currentCart = null;

function hasCurrentAccount() {
  if (accountInvalidated) return false;
  if (localStorage.getItem(ACCESS_TOKEN_KEY) === accountToken) return true;
  accountInvalidated = true;
  setControlsEnabled(false);
  showState("loading", "Your account changed. Reloading your cart…");
  window.location.reload();
  return false;
}

/** An error answered by the API; its message is written for the buyer. */
class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** Show exactly one of the loading / data / empty / error regions. */
function showState(state, message) {
  elements.loading.hidden = state !== "loading";
  elements.content.hidden = state !== "data";
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.status.textContent = message;
}

/** The cart needs a buyer: drop a missing or rejected token and come back here after login. */
function redirectToLogin() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.location.replace(LOGIN_URL);
  // Never settles, so no error state flashes while the browser leaves the page.
  return new Promise(() => {});
}

function isValidCart(cart) {
  const valid = (
    cart !== null &&
    typeof cart === "object" &&
    Array.isArray(cart.items) &&
    Number.isSafeInteger(cart.cart_total) && cart.cart_total >= 0 &&
    cart.items.every(item => item !== null && typeof item === "object")
  );
  if (!valid) return false;
  // Old responses remain whole-cart checkout. Partial metadata must never silently fall back.
  const selectionFields = ["cart_item_id", "seller_id", "seller_name", "is_selected",
    "price_at_add", "price_changed"];
  const hasSelectionData = "selected_total" in cart || "supports_partial_checkout" in cart ||
    cart.items.some(item => selectionFields.some(field => field in item));
  if (!hasSelectionData) return true;
  if (!Number.isSafeInteger(cart.selected_total) || cart.selected_total < 0) return false;
  if ("supports_partial_checkout" in cart && typeof cart.supports_partial_checkout !== "boolean") {
    return false;
  }
  const validItems = cart.items.every(item =>
    Number.isSafeInteger(item.cart_item_id) && item.cart_item_id > 0 &&
    Number.isSafeInteger(item.seller_id) && item.seller_id > 0 &&
    typeof item.seller_name === "string" && item.seller_name.trim() !== "" &&
    typeof item.is_selected === "boolean" &&
    Number.isSafeInteger(item.price_at_add) && item.price_at_add >= 0 &&
    Number.isSafeInteger(item.unit_price) && item.unit_price >= 0 &&
    Number.isSafeInteger(item.quantity) && item.quantity > 0 &&
    Number.isSafeInteger(item.line_total) &&
    item.line_total === item.unit_price * item.quantity &&
    item.price_changed === (item.price_at_add !== item.unit_price) &&
    ["available", "insufficient_stock", "unavailable"].includes(item.availability) &&
    (item.availability === "available" || !item.is_selected),
  );
  return validItems && new Set(cart.items.map(item => item.cart_item_id)).size === cart.items.length &&
    cart.selected_total === selectedSubtotal(cart.items) &&
    cart.cart_total === cart.items.reduce((total, item) => total + item.line_total, 0);
}

function supportsSelection(cart) {
  return Number.isSafeInteger(cart.selected_total);
}

function selectedSubtotal(items) {
  return items.filter(item => item.availability === "available" && item.is_selected)
    .reduce((total, item) => total + item.line_total, 0);
}

/** Send one cart request; every cart endpoint answers with `{ data: cart }`. */
async function requestCart(url, method = "GET", body = undefined) {
  if (!hasCurrentAccount()) throw new Error("Account changed");
  const token = accountToken;
  if (!token) {
    return redirectToLogin();
  }
  const headers = { Accept: "application/json", Authorization: `Bearer ${token}` };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (!hasCurrentAccount()) throw new Error("Account changed");
    if (response.status === 401) {
      return redirectToLogin();
    }
    const payload = await response.json().catch(() => null);
    if (!hasCurrentAccount()) throw new Error("Account changed");
    if (!response.ok) {
      const message = payload?.error?.message;
      throw message
        ? new ApiError(response.status, message)
        : new Error(`Cart request failed: ${response.status}`);
    }
    if (!isValidCart(payload?.data)) {
      throw new Error("Cart response does not match the expected contract");
    }
    return payload.data;
  } finally {
    clearTimeout(timeoutId);
  }
}

function cartItemUrl(productCode, variantId = null) {
  const path = `${CART_ITEMS_URL}/${encodeURIComponent(productCode)}`;
  return variantId === null || variantId === undefined
    ? path
    : `${path}?variant_id=${encodeURIComponent(variantId)}`;
}

function formatPrice(amount) {
  return priceFormatter.format(amount);
}

function itemCountLabel(count) {
  return count === 1 ? "1 item" : `${count} items`;
}

/** Explain why a line cannot be bought as it stands; the server decides, the page only shows it. */
function availabilityWarning(item) {
  if (item.availability === "unavailable") {
    return "This product is no longer available.";
  }
  if (item.availability === "insufficient_stock") {
    return item.available_stock === 0
      ? "This product is out of stock."
      : `Cannot add more than ${item.available_stock} items (available stock limit)`;
  }
  return "";
}

function createElement(tag, className, text = "") {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function createLineImage(item) {
  const image = createElement("img", "cart-line__image");
  image.alt = "";
  image.width = THUMBNAIL_SIZE_PX;
  image.height = THUMBNAIL_SIZE_PX;
  // Missing or broken images fall back to the placeholder once (no retry loop).
  image.addEventListener("error", () => { image.src = PLACEHOLDER_IMAGE; }, { once: true });
  image.src = item.image_url || PLACEHOLDER_IMAGE;
  return image;
}

function createLineInfo(item) {
  const info = createElement("div", "cart-line__info");
  info.append(
    createElement("h2", "cart-line__name", item.variant_name ? `${item.name} · ${item.variant_name}` : item.name),
    createElement("p", "cart-line__price", `${formatPrice(item.unit_price)} each`),
    createElement(
      "p",
      "cart-line__meta",
      `${item.product_code} · Available: ${item.available_stock}`,
    ),
  );

  const warning = availabilityWarning(item);
  if (warning) {
    info.append(createElement("p", "cart-line__warning", warning));
  }

  if (item.price_changed) {
    info.append(createElement("p", "cart-line__warning",
      `Price changed: ${formatPrice(item.price_at_add)} when added → ${formatPrice(item.unit_price)} now.`));
  }

  const error = createElement("p", "cart-line__error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  info.append(error);
  return info;
}

function createStepButton(label, ariaLabel) {
  const button = createElement("button", "cart-line__step", label);
  button.type = "button";
  button.setAttribute("aria-label", ariaLabel);
  return button;
}

/** `[-] quantity [+]`; typing a number and leaving the field (or pressing Enter) also saves it. */
function createQuantityControl(line, item) {
  const control = createElement("div", "cart-line__quantity");

  const inputId = `quantity-${item.cart_item_id}`;
  const label = createElement("label", "visually-hidden", `Quantity for ${item.name}`);
  label.htmlFor = inputId;

  const input = document.createElement("input");
  input.id = inputId;
  input.type = "number";
  input.min = "1";
  input.step = "1";
  input.inputMode = "numeric";
  input.value = String(item.quantity);

  const decrease = createStepButton("−", `Decrease quantity of ${item.name}`);
  const increase = createStepButton("+", `Increase quantity of ${item.name}`);
  decrease.id = `decrease-${item.cart_item_id}`;
  increase.id = `increase-${item.cart_item_id}`;
  decrease.dataset.minimum = String(item.quantity <= 1);

  decrease.addEventListener("click", () => updateQuantity(line, item, input, item.quantity - 1));
  increase.addEventListener("click", () => updateQuantity(line, item, input, item.quantity + 1));
  input.addEventListener("change", () => updateQuantity(line, item, input, Number(input.value)));

  control.append(label, decrease, input, increase);
  return control;
}

function createRemoveButton(line, item) {
  const button = createElement("button", "cart-line__remove", "Remove");
  button.type = "button";
  button.id = `remove-${item.cart_item_id}`;
  button.setAttribute("aria-label", `Remove ${item.name} from cart`);
  button.addEventListener("click", () => removeLine(line, item));
  return button;
}

function createCartLine(item, selectable = false) {
  const line = createElement("li", "cart-line");
  if (item.availability !== "available") {
    line.classList.add("cart-line--flagged");
  }
  line.append(
    createLineImage(item),
    createLineInfo(item),
    createQuantityControl(line, item),
    createElement("p", "cart-line__total", formatPrice(item.line_total)),
    createRemoveButton(line, item),
  );
  if (selectable) {
    line.classList.add("cart-line--selectable");
    const selection = createSelection(`select-item-${item.cart_item_id}`, `Select ${item.name}`,
      item.is_selected && item.availability === "available", item.availability !== "available");
    selection.classList.add("cart-line__selection");
    selection.querySelector("input").addEventListener("change", event => {
      changeSelection(line, `${CART_ITEMS_URL}/${item.cart_item_id}/select`, event.target.checked);
    });
    line.append(selection);
  }
  return line;
}

function createSelection(id, labelText, checked, disabled = false) {
  const label = createElement("label", "cart-selection");
  const input = createElement("input", "");
  input.type = "checkbox";
  input.id = id;
  input.checked = checked;
  input.dataset.unavailable = String(disabled);
  label.append(input, createElement("span", "", labelText));
  return label;
}

function createShopGroup(sellerId, items) {
  const group = createElement("li", "cart-shop");
  const available = items.filter(item => item.availability === "available");
  const selected = available.filter(item => item.is_selected).length;
  const selection = createSelection(`select-shop-${sellerId}`, `Select shop: ${items[0].seller_name}`,
    available.length > 0 && selected === available.length, available.length === 0);
  const checkbox = selection.querySelector("input");
  checkbox.indeterminate = selected > 0 && selected < available.length;
  checkbox.addEventListener("change", event => {
    changeSelection(group, `${CART_URL}/select-shop/${sellerId}`, event.target.checked);
  });
  const subtotal = available.reduce((total, item) => total + item.line_total, 0);
  const header = createElement("div", "cart-shop__header");
  const heading = createElement("h2", "cart-shop__name", items[0].seller_name);
  header.append(heading, selection, createElement("p", "cart-shop__subtotal",
    `Shop subtotal: ${formatPrice(subtotal)} · Selected: ${formatPrice(selectedSubtotal(items))}`));
  const error = createElement("p", "cart-line__error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const lines = createElement("ul", "cart-lines");
  lines.append(...available.map(item => createCartLine(item, true)));
  group.append(header, error, lines);
  const unavailable = items.filter(item => item.availability !== "available");
  if (unavailable.length) {
    const section = createElement("section", "cart-shop__unavailable");
    const title = createElement("h3", "", "Unavailable for checkout — not selected");
    const unavailableLines = createElement("ul", "cart-lines");
    unavailableLines.append(...unavailable.map(item => createCartLine(item, true)));
    section.append(title, unavailableLines);
    group.append(section);
  }
  return group;
}

function renderShopGroups(items) {
  const shops = new Map();
  for (const item of items) {
    if (!shops.has(item.seller_id)) shops.set(item.seller_id, []);
    shops.get(item.seller_id).push(item);
  }
  return [...shops].map(([sellerId, lines]) => createShopGroup(sellerId, lines));
}

function checkoutBlockedMessage(cart) {
  if (!supportsSelection(cart)) {
    return cart.items.every(item => item.availability === "available") ? "" :
      "Update or remove the highlighted items before checkout.";
  }
  if (!cart.items.some(item => item.availability === "available" && item.is_selected)) {
    return "Select at least one available item to checkout.";
  }
  return cart.supports_partial_checkout === true ? "" :
    "Checkout for selected items is not available yet. Your selection has been saved.";
}

/** Enable every control of the rendered cart, or lock them all while a change is pending. */
function setControlsEnabled(enabled) {
  for (const control of elements.lines.querySelectorAll("input, button")) {
    control.disabled = !enabled || control.dataset.minimum === "true" ||
      control.dataset.unavailable === "true";
  }
  elements.checkout.disabled = !enabled || !elements.checkoutBlocked.hidden;
}

function renderCart(cart) {
  currentCart = cart;
  if (cart.items.length === 0) {
    elements.lines.replaceChildren();
    elements.emptyTotal.textContent = formatPrice(cart.cart_total);
    const note = document.getElementById("recent-order-note");
    if (note) note.hidden = false;
    showState("empty", "Your cart is empty.");
    return;
  }
  const selection = supportsSelection(cart);
  elements.lines.replaceChildren(...(selection ? renderShopGroups(cart.items) :
    cart.items.map(item => createCartLine(item))));
  const total = selection ? cart.selected_total : cart.cart_total;
  elements.totalLabel.textContent = selection ? "Selected total:" : "Total:";
  elements.total.textContent = formatPrice(total);
  elements.checkoutBlocked.textContent = checkoutBlockedMessage(cart);
  elements.checkoutBlocked.hidden = elements.checkoutBlocked.textContent === "";
  setControlsEnabled(true);
  showState(
    "data",
    `${itemCountLabel(cart.items.length)} in your cart. ${elements.totalLabel.textContent} ${formatPrice(total)}.`,
  );
}

function showLineError(line, message) {
  const error = line.querySelector(".cart-line__error");
  error.textContent = message;
  error.hidden = message === "";
}

function restoreFocus(id) {
  const previous = id ? document.getElementById(id) : null;
  const target = previous && !previous.disabled ? previous :
    [...elements.lines.querySelectorAll("input, button")].find(control => !control.disabled);
  (target || elements.status).focus();
}

/**
 * Send one change for a line. On success the cart is rendered again from the server's answer;
 * on failure the previous cart stays on screen and the reason appears next to the line.
 */
async function changeLine(line, sendChange) {
  if (changingCart || !hasCurrentAccount()) return false;
  changingCart = true;
  document.getElementById("cart-change-error").hidden = true;
  const focusId = document.activeElement?.id;
  showLineError(line, "");
  setControlsEnabled(false);
  line.setAttribute("aria-busy", "true");
  try {
    renderCart(await sendChange());
    restoreFocus(focusId);
    return true;
  } catch (error) {
    if (!hasCurrentAccount()) return false;
    showLineError(line, error instanceof ApiError ? error.message : CHANGE_ERROR_MESSAGE);
    line.removeAttribute("aria-busy");
    setControlsEnabled(true);
    return false;
  } finally {
    changingCart = false;
  }
}

async function changeSelection(scope, url, isSelected) {
  if (changingCart || !hasCurrentAccount()) return;
  const changed = await changeLine(scope, () => requestCart(url, "PATCH", { is_selected: isSelected }));
  if (!changed && hasCurrentAccount()) {
    // Restore the last confirmed snapshot; a failed PATCH must not look saved.
    const message = scope.querySelector(".cart-line__error").textContent || CHANGE_ERROR_MESSAGE;
    const focusId = document.activeElement?.id;
    renderCart(currentCart);
    elements.status.textContent = message;
    const error = document.getElementById("cart-change-error");
    error.textContent = message;
    error.hidden = false;
    restoreFocus(focusId);
  }
}

async function updateQuantity(line, item, input, quantity) {
  if (!Number.isInteger(quantity) || quantity < 1) {
    showLineError(line, INVALID_QUANTITY_MESSAGE);
    input.value = String(item.quantity);
    return;
  }
  if (quantity === item.quantity) {
    return;
  }
  input.value = String(quantity);
  const updated = await changeLine(line, () =>
    requestCart(cartItemUrl(item.product_code, item.variant_id), "PATCH", { quantity }),
  );
  if (!updated) {
    input.value = String(item.quantity);
  }
}

function removeLine(line, item) {
  changeLine(line, () => requestCart(cartItemUrl(item.product_code, item.variant_id), "DELETE"));
}

function showLoadError(error) {
  // A seller is signed in correctly but has no cart, so retrying cannot help.
  const forbidden = error instanceof ApiError && error.status === 403;
  elements.errorMessage.textContent = forbidden ? BUYER_ONLY_MESSAGE : LOAD_ERROR_MESSAGE;
  elements.retry.hidden = forbidden;
  showState("error", elements.errorMessage.textContent);
}

async function loadCart() {
  elements.retry.disabled = true;
  showState("loading", "Loading your cart…");
  try {
    renderCart(await requestCart(CART_URL));
  } catch (error) {
    if (hasCurrentAccount()) showLoadError(error);
  } finally {
    elements.retry.disabled = false;
  }
}

elements.retry.addEventListener("click", loadCart);
elements.checkout.addEventListener("click", () => {
  if (hasCurrentAccount() && !changingCart && currentCart?.items.length &&
      !checkoutBlockedMessage(currentCart)) window.location.assign(CHECKOUT_URL);
});
window.addEventListener("storage", event => {
  if (event.key === ACCESS_TOKEN_KEY || event.key === null) hasCurrentAccount();
});
elements.logout.addEventListener("click", () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.location.assign("/products");
});

function getUserFromToken() {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return { id: Number(payload.sub), role: payload.role };
  } catch {
    return null;
  }
}

function configureNavigation() {
  const user = getUserFromToken();
  const myOrders = document.getElementById("my-orders-link");
  const sellerOrders = document.getElementById("seller-orders-link");
  if (user && user.role === "seller") {
    if (myOrders) myOrders.hidden = true;
    if (sellerOrders) sellerOrders.hidden = false;
  } else {
    if (myOrders) myOrders.hidden = !user;
    if (sellerOrders) sellerOrders.hidden = true;
  }
}

configureNavigation();
loadCart();
