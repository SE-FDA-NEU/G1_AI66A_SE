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
  checkout: document.getElementById("checkout-button"),
  checkoutBlocked: document.getElementById("checkout-blocked"),
  empty: document.getElementById("cart-empty"),
  emptyTotal: document.getElementById("cart-empty-total"),
  error: document.getElementById("cart-error"),
  errorMessage: document.getElementById("cart-error-message"),
  retry: document.getElementById("cart-retry"),
  logout: document.getElementById("logout-button"),
};

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
  return (
    cart !== null &&
    typeof cart === "object" &&
    Array.isArray(cart.items) &&
    Number.isInteger(cart.cart_total)
  );
}

/** Send one cart request; every cart endpoint answers with `{ data: cart }`. */
async function requestCart(url, method = "GET", body = undefined) {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
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
    if (response.status === 401) {
      return redirectToLogin();
    }
    const payload = await response.json().catch(() => null);
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

function cartItemUrl(productCode) {
  return `${CART_ITEMS_URL}/${encodeURIComponent(productCode)}`;
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
    createElement("h2", "cart-line__name", item.name),
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

  const inputId = `quantity-${item.product_code}`;
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
  button.setAttribute("aria-label", `Remove ${item.name} from cart`);
  button.addEventListener("click", () => removeLine(line, item));
  return button;
}

function createCartLine(item) {
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
  return line;
}

/** Enable every control of the rendered cart, or lock them all while a change is pending. */
function setControlsEnabled(enabled) {
  for (const control of elements.lines.querySelectorAll("input, button")) {
    control.disabled = !enabled || control.dataset.minimum === "true";
  }
  elements.checkout.disabled = !enabled || !elements.checkoutBlocked.hidden;
}

function renderCart(cart) {
  if (cart.items.length === 0) {
    elements.lines.replaceChildren();
    elements.emptyTotal.textContent = formatPrice(cart.cart_total);
    showState("empty", "Your cart is empty.");
    return;
  }
  elements.lines.replaceChildren(...cart.items.map(createCartLine));
  elements.total.textContent = formatPrice(cart.cart_total);
  elements.checkoutBlocked.hidden = cart.items.every((item) => item.availability === "available");
  setControlsEnabled(true);
  showState(
    "data",
    `${itemCountLabel(cart.items.length)} in your cart. Total ${formatPrice(cart.cart_total)}.`,
  );
}

function showLineError(line, message) {
  const error = line.querySelector(".cart-line__error");
  error.textContent = message;
  error.hidden = message === "";
}

/**
 * Send one change for a line. On success the cart is rendered again from the server's answer;
 * on failure the previous cart stays on screen and the reason appears next to the line.
 */
async function changeLine(line, sendChange) {
  showLineError(line, "");
  setControlsEnabled(false);
  line.setAttribute("aria-busy", "true");
  try {
    renderCart(await sendChange());
    return true;
  } catch (error) {
    showLineError(line, error instanceof ApiError ? error.message : CHANGE_ERROR_MESSAGE);
    line.removeAttribute("aria-busy");
    setControlsEnabled(true);
    return false;
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
    requestCart(cartItemUrl(item.product_code), "PATCH", { quantity }),
  );
  if (!updated) {
    input.value = String(item.quantity);
  }
}

function removeLine(line, item) {
  changeLine(line, () => requestCart(cartItemUrl(item.product_code), "DELETE"));
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
    showLoadError(error);
  } finally {
    elements.retry.disabled = false;
  }
}

elements.retry.addEventListener("click", loadCart);
elements.checkout.addEventListener("click", () => window.location.assign(CHECKOUT_URL));
elements.logout.addEventListener("click", () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.location.assign("/products");
});
loadCart();
