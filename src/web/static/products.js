"use strict";

const PRODUCTS_URL = "/api/v1/products";
const PAGE_LIMIT = 20;
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
  search: document.getElementById("products-search"),
  searchInput: document.getElementById("product-search-input"),
  pagination: document.getElementById("products-pagination"),
  previous: document.getElementById("products-previous"),
  next: document.getElementById("products-next"),
  page: document.getElementById("products-page"),
  loginLink: document.getElementById("login-link"),
  logoutButton: document.getElementById("logout-button"),
};

let currentPage = 1;
let currentSearch = "";

function configureNavigation() {
  const hasToken = Boolean(localStorage.getItem("access_token"));
  elements.loginLink.hidden = hasToken;
  elements.logoutButton.hidden = !hasToken;
  if (!hasToken) {
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath && currentPath !== "/login") {
      elements.loginLink.href = `/login?return_to=${encodeURIComponent(currentPath)}`;
    }
  }
}

elements.logoutButton.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  configureNavigation();
});

/** Show exactly one of the loading / success / empty / error regions. */
function showState(state, message) {
  elements.loading.hidden = state !== "loading";
  elements.grid.hidden = state !== "success";
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.pagination.hidden = state !== "success";
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

  const link = document.createElement("a");
  link.className = "product-card__link";
  link.href = `/products/${encodeURIComponent(product.code)}`;

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

  link.append(image, body);
  card.append(link);
  return card;
}

async function fetchProducts(page, search) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const params = new URLSearchParams({
    page: String(page),
    limit: String(PAGE_LIMIT),
  });
  if (search) {
    params.set("search", search);
  }
  try {
    const response = await fetch(`${PRODUCTS_URL}?${params}`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.error?.message || "Unable to load products.");
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

function updatePagination(meta) {
  elements.pagination.hidden = meta.total_pages <= 1;
  elements.previous.disabled = meta.current_page <= 1;
  elements.next.disabled = meta.current_page >= meta.total_pages;
  elements.page.textContent = `Page ${meta.current_page} of ${meta.total_pages}`;
}

async function loadProducts(page = currentPage) {
  currentPage = page;
  elements.retry.disabled = true;
  showState("loading", "Loading products…");
  try {
    const { data, meta } = await fetchProducts(currentPage, currentSearch);
    if (data.length === 0) {
      showState("empty", "No products available at the moment.");
    } else {
      elements.grid.replaceChildren(...data.map(createProductCard));
      showState("success", `Showing ${data.length} of ${meta.total} products.`);
      updatePagination(meta);
    }
  } catch (error) {
    showState("error", "Something went wrong. Please try again later.");
  } finally {
    elements.retry.disabled = false;
  }
}

elements.retry.addEventListener("click", loadProducts);
elements.search.addEventListener("submit", (event) => {
  event.preventDefault();
  currentSearch = elements.searchInput.value.trim();
  currentPage = 1;
  loadProducts();
});
elements.previous.addEventListener("click", () => loadProducts(currentPage - 1));
elements.next.addEventListener("click", () => loadProducts(currentPage + 1));
loadProducts();
configureNavigation();
