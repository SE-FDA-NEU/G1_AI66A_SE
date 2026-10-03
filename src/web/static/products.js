"use strict";

const PRODUCTS_URL = "/api/v1/products?page=1&limit=20";
const REQUEST_TIMEOUT_MS = 10000;
const PLACEHOLDER_IMAGE = "/static/product-placeholder.svg";

const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

const elements = {
  status: document.getElementById("products-status"),
  loading: document.getElementById("products-loading"),
  grid: document.getElementById("products-grid"),
  empty: document.getElementById("products-empty"),
  error: document.getElementById("products-error"),
  retry: document.getElementById("products-retry"),
};

/** Show exactly one of the loading / success / empty / error regions. */
function showState(state, message) {
  elements.loading.hidden = state !== "loading";
  elements.grid.hidden = state !== "success";
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.status.textContent = message;
}

/**
 * A broken response must surface as an error, never as an empty catalog:
 * `data` has to be an array, and an empty first page is only valid when `meta.total` is 0.
 */
function isValidPayload(payload) {
  return (
    payload !== null &&
    typeof payload === "object" &&
    Array.isArray(payload.data) &&
    payload.meta !== null &&
    typeof payload.meta === "object" &&
    Number.isInteger(payload.meta.total) &&
    (payload.data.length > 0 || payload.meta.total === 0)
  );
}

function stockLabel(product) {
  switch (product.stock_status) {
    case "in_stock":
      return "In Stock";
    case "low_stock":
      return `Only ${product.stock_quantity} left`;
    case "out_of_stock":
      return "Out of Stock";
    default:
      return "";
  }
}

function createProductCard(product) {
  const card = document.createElement("li");
  card.className = "product-card";

  const image = document.createElement("img");
  image.className = "product-card__image";
  image.alt = product.name;
  image.loading = "lazy";
  image.width = 300;
  image.height = 300;
  // Missing or broken thumbnails fall back to the placeholder once (no retry loop).
  image.addEventListener("error", () => { image.src = PLACEHOLDER_IMAGE; }, { once: true });
  image.src = product.thumbnail_url || PLACEHOLDER_IMAGE;

  const body = document.createElement("div");
  body.className = "product-card__body";

  const name = document.createElement("h2");
  name.className = "product-card__name";
  name.textContent = product.name;
  name.title = product.name;

  const price = document.createElement("p");
  price.className = "product-card__price";
  price.textContent = priceFormatter.format(product.price);

  body.append(name, price);

  const stock = stockLabel(product);
  if (stock) {
    const badge = document.createElement("p");
    badge.className = `product-card__stock product-card__stock--${product.stock_status}`;
    badge.textContent = stock;
    body.append(badge);
  }

  card.append(image, body);
  return card;
}

async function fetchProducts() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(PRODUCTS_URL, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Products request failed with HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!isValidPayload(payload)) {
      throw new Error("Products response does not match the expected contract");
    }
    return payload;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function loadProducts() {
  elements.retry.disabled = true;
  showState("loading", "Loading products…");
  try {
    const { data, meta } = await fetchProducts();
    if (data.length === 0) {
      showState("empty", "No products available at the moment.");
    } else {
      elements.grid.replaceChildren(...data.map(createProductCard));
      showState("success", `Showing ${data.length} of ${meta.total} products.`);
    }
  } catch (error) {
    console.error(error);
    showState("error", "Something went wrong. Please try again later.");
  } finally {
    elements.retry.disabled = false;
  }
}

elements.retry.addEventListener("click", loadProducts);
loadProducts();
