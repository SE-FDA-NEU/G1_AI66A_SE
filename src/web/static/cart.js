"use strict";

const CART_URL = "/api/v1/cart";
const CART_ITEMS_URL = "/api/v1/cart/items";
const REQUEST_TIMEOUT_MS = 10000;
const PLACEHOLDER_IMAGE = "/static/product-placeholder.svg";
const THUMBNAIL_SIZE_PX = 96;

const LOAD_ERROR_MESSAGE = "We could not load your cart. Please try again.";
const CHANGE_ERROR_MESSAGE = "We could not update your cart. Please try again.";
const INVALID_QUANTITY_MESSAGE = "Enter a whole number of at least 1.";

const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

const elements = {
  status: document.getElementById("cart-status"),
  loading: document.getElementById("cart-loading"),
  content: document.getElementById("cart-content"),
  lines: document.getElementById("cart-lines"),
  total: document.getElementById("cart-total"),
  empty: document.getElementById("cart-empty"),
  emptyTotal: document.getElementById("cart-empty-total"),
  error: document.getElementById("cart-error"),
  retry: document.getElementById("cart-retry"),
};

/** An error whose message comes from the API and is written for the buyer. */
class ApiError extends Error {}

/** Show exactly one of the loading / data / empty / error regions. */
function showState(state, message) {
  elements.loading.hidden = state !== "loading";
  elements.content.hidden = state !== "data";
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.status.textContent = message;
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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const message = payload?.error?.message;
      throw message ? new ApiError(message) : new Error(`Cart request failed: ${response.status}`);
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
      : `Only ${item.available_stock} left in stock.`;
  }
  return "";
}

function createLineImage(item) {
  const image = document.createElement("img");
  image.className = "cart-line__image";
  image.alt = "";
  image.width = THUMBNAIL_SIZE_PX;
  image.height = THUMBNAIL_SIZE_PX;
  // Missing or broken images fall back to the placeholder once (no retry loop).
  image.addEventListener("error", () => { image.src = PLACEHOLDER_IMAGE; }, { once: true });
  image.src = item.image_url || PLACEHOLDER_IMAGE;
  return image;
}

function createLineInfo(item) {
  const info = document.createElement("div");
  info.className = "cart-line__info";

  const name = document.createElement("h2");
  name.className = "cart-line__name";
  name.textContent = item.name;

  const price = document.createElement("p");
  price.className = "cart-line__price";
  price.textContent = `${formatPrice(item.unit_price)} each`;
  info.append(name, price);

  const warning = availabilityWarning(item);
  if (warning) {
    const badge = document.createElement("p");
    badge.className = "cart-line__warning";
    badge.textContent = warning;
    info.append(badge);
  }

  const error = document.createElement("p");
  error.className = "cart-line__error";
  error.setAttribute("role", "alert");
  error.hidden = true;
  info.append(error);
  return info;
}

function createQuantityForm(item) {
  const form = document.createElement("form");
  form.className = "cart-line__quantity";
  form.noValidate = true;

  const inputId = `quantity-${item.product_code}`;
  const label = document.createElement("label");
  label.className = "visually-hidden";
  label.htmlFor = inputId;
  label.textContent = `Quantity for ${item.name}`;

  const input = document.createElement("input");
  input.id = inputId;
  input.name = "quantity";
  input.type = "number";
  input.min = "1";
  input.step = "1";
  input.inputMode = "numeric";
  input.value = String(item.quantity);

  const submit = document.createElement("button");
  submit.className = "button";
  submit.type = "submit";
  submit.textContent = "Update";

  form.append(label, input, submit);
  return form;
}

function createRemoveButton(item) {
  const button = document.createElement("button");
  button.className = "cart-line__remove";
  button.type = "button";
  button.textContent = "Remove";
  button.setAttribute("aria-label", `Remove ${item.name} from cart`);
  return button;
}

function createCartLine(item) {
  const line = document.createElement("li");
  line.className = "cart-line";

  const lineTotal = document.createElement("p");
  lineTotal.className = "cart-line__total";
  lineTotal.textContent = formatPrice(item.line_total);

  const form = createQuantityForm(item);
  const remove = createRemoveButton(item);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    updateQuantity(line, item, form.elements.quantity);
  });
  remove.addEventListener("click", () => removeLine(line, item));

  line.append(createLineImage(item), createLineInfo(item), form, lineTotal, remove);
  return line;
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
  showState(
    "data",
    `${itemCountLabel(cart.items.length)} in your cart. Total ${formatPrice(cart.cart_total)}.`,
  );
}

/** Lock every line while one change is pending, so changes never overlap. */
function setLinesBusy(busyLine, busy) {
  for (const control of elements.lines.querySelectorAll("input, button")) {
    control.disabled = busy;
  }
  busyLine.setAttribute("aria-busy", String(busy));
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
  setLinesBusy(line, true);
  try {
    renderCart(await sendChange());
    return true;
  } catch (error) {
    showLineError(line, error instanceof ApiError ? error.message : CHANGE_ERROR_MESSAGE);
    setLinesBusy(line, false);
    return false;
  }
}

async function updateQuantity(line, item, input) {
  const quantity = Number(input.value);
  if (!Number.isInteger(quantity) || quantity < 1) {
    showLineError(line, INVALID_QUANTITY_MESSAGE);
    return;
  }
  if (quantity === item.quantity) {
    showLineError(line, "");
    return;
  }
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

async function loadCart() {
  elements.retry.disabled = true;
  showState("loading", "Loading your cart…");
  try {
    renderCart(await requestCart(CART_URL));
  } catch {
    showState("error", LOAD_ERROR_MESSAGE);
  } finally {
    elements.retry.disabled = false;
  }
}

elements.retry.addEventListener("click", loadCart);
loadCart();
