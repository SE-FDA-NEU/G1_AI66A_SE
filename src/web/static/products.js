"use strict";

const PRODUCTS_URL = "/api/v1/products";
const CATEGORIES_URL = "/api/v1/categories";
const SELLERS_URL = "/api/v1/sellers";
const PAGE_LIMIT = 20;
const REQUEST_TIMEOUT_MS = 10000;
const PLACEHOLDER_IMAGE = "/static/product-placeholder.svg";

const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

const elements = {
  status: document.getElementById("products-status"),
  loading: document.getElementById("products-loading"),
  grid: document.getElementById("products-grid"),
  empty: document.getElementById("products-empty"),
  emptyMessage: document.getElementById("products-empty-message"),
  resetEmpty: document.getElementById("products-reset-empty"),
  error: document.getElementById("products-error"),
  errorMessage: document.getElementById("products-error-message"),
  retry: document.getElementById("products-retry"),
  search: document.getElementById("products-search"),
  searchInput: document.getElementById("product-search-input"),
  filterCategory: document.getElementById("filter-category"),
  filterSeller: document.getElementById("filter-seller"),
  filterMinPrice: document.getElementById("filter-min-price"),
  filterMaxPrice: document.getElementById("filter-max-price"),
  priceError: document.getElementById("price-error"),
  filterRating: document.getElementById("filter-rating"),
  filterInStock: document.getElementById("filter-in-stock"),
  catalogSort: document.getElementById("catalog-sort"),
  applyFilters: document.getElementById("apply-filters"),
  resetFilters: document.getElementById("reset-filters"),
  pagination: document.getElementById("products-pagination"),
  previous: document.getElementById("products-previous"),
  next: document.getElementById("products-next"),
  page: document.getElementById("products-page"),
  loginLink: document.getElementById("login-link"),
  logoutButton: document.getElementById("logout-button"),
  buyerOrdersLink: document.getElementById("buyer-orders-link"),
  sellerNewProductLink: document.getElementById("seller-new-product-link"),
  sellerOrdersLink: document.getElementById("seller-orders-link"),
  adminPortalLink: document.getElementById("admin-portal-link"),
};

let currentPage = 1;
let currentSearch = "";
let currentCategory = "";
let currentSeller = "";
let currentMinPrice = "";
let currentMaxPrice = "";
let currentRating = "";
let currentInStock = true;
let currentSort = "";

function getUserFromToken() {
  const token = localStorage.getItem("access_token");
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
  const hasToken = Boolean(user);
  if (elements.loginLink) elements.loginLink.hidden = hasToken;
  if (elements.logoutButton) elements.logoutButton.hidden = !hasToken;
  if (!hasToken && elements.loginLink) {
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath && currentPath !== "/login") {
      elements.loginLink.href = `/login?return_to=${encodeURIComponent(currentPath)}`;
    }
  }

  const isSeller = Boolean(user && user.role === "seller");
  const isBuyer = Boolean(user && user.role === "buyer");
  const isAdmin = Boolean(user && user.role === "admin");

  if (elements.buyerOrdersLink) {
    elements.buyerOrdersLink.hidden = !isBuyer;
  }
  if (elements.sellerNewProductLink) {
    elements.sellerNewProductLink.hidden = !isSeller;
  }
  if (elements.sellerOrdersLink) {
    elements.sellerOrdersLink.hidden = !isSeller;
  }
  if (elements.adminPortalLink) {
    elements.adminPortalLink.hidden = !isAdmin;
  }
}

if (elements.logoutButton) {
  elements.logoutButton.addEventListener("click", () => {
    localStorage.removeItem("access_token");
    configureNavigation();
  });
}

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

  if (product.rating && product.rating > 0) {
    const ratingEl = document.createElement("p");
    ratingEl.className = "product-card__rating";
    ratingEl.textContent = `★ ${Number(product.rating).toFixed(1)}`;
    body.append(ratingEl);
  }

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

let activeAbortController = null;
let currentRequestId = 0;

const LOAD_ERROR_MESSAGE = "We could not load the products. Check your connection, then select Retry.";
const TIMEOUT_MESSAGE = "The catalog is taking too long to respond. Select Retry to try again.";

async function fetchProducts(page, search, signal) {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(PAGE_LIMIT),
  });
  if (search) {
    params.set("search", search);
  }
  if (currentCategory) {
    params.set("category_id", currentCategory);
  }
  if (currentSeller) {
    params.set("seller_id", currentSeller);
  }
  if (currentMinPrice) {
    params.set("min_price", currentMinPrice);
  }
  if (currentMaxPrice) {
    params.set("max_price", currentMaxPrice);
  }
  if (currentRating) {
    params.set("min_rating", currentRating);
  }
  if (currentInStock !== undefined && currentInStock !== null) {
    params.set("in_stock", String(currentInStock));
  }
  if (currentSort) {
    params.set("sort", currentSort);
  }

  const response = await fetch(`${PRODUCTS_URL}?${params}`, {
    headers: { Accept: "application/json" },
    signal: signal,
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
}

function updatePagination(meta) {
  currentPage = meta.current_page;
  elements.pagination.hidden = meta.total_pages <= 1;
  elements.previous.disabled = meta.current_page <= 1;
  elements.next.disabled = meta.current_page >= meta.total_pages;
  elements.page.textContent = `Page ${meta.current_page} of ${meta.total_pages}`;
}

function hasActiveFilters() {
  return Boolean(
    currentSearch ||
    currentCategory ||
    currentSeller ||
    currentMinPrice ||
    currentMaxPrice ||
    currentRating ||
    !currentInStock ||
    currentSort
  );
}

async function loadProducts(page = currentPage) {
  currentPage = page;

  if (activeAbortController) {
    activeAbortController.abort();
  }
  const controller = new AbortController();
  activeAbortController = controller;
  const requestId = ++currentRequestId;
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  elements.retry.disabled = true;
  showState("loading", "Loading products…");
  try {
    const { data, meta } = await fetchProducts(currentPage, currentSearch, controller.signal);
    clearTimeout(timeoutId);

    // Guard against outdated responses from overlapping requests
    if (requestId !== currentRequestId) {
      return;
    }

    if (data.length === 0) {
      if (hasActiveFilters()) {
        elements.emptyMessage.textContent = "No products match your search or filter criteria. Try adjusting or clearing your filters.";
        if (elements.resetEmpty) elements.resetEmpty.hidden = false;
      } else {
        elements.emptyMessage.textContent = "No products available at the moment.";
        if (elements.resetEmpty) elements.resetEmpty.hidden = true;
      }
      showState("empty", elements.emptyMessage.textContent);
    } else {
      elements.grid.replaceChildren(...data.map(createProductCard));
      showState("success", `Showing ${data.length} of ${meta.total} products.`);
      updatePagination(meta);
    }
  } catch (error) {
    clearTimeout(timeoutId);
    // A newer query aborted this request and will update the page itself.
    if (requestId !== currentRequestId) {
      return;
    }
    // Only the timeout aborts the current request, so it must end in the error state.
    const message = error.name === "AbortError" ? TIMEOUT_MESSAGE : LOAD_ERROR_MESSAGE;
    elements.errorMessage.textContent = message;
    showState("error", message);
  } finally {
    clearTimeout(timeoutId);
    if (activeAbortController === controller) {
      activeAbortController = null;
    }
    if (requestId === currentRequestId) {
      elements.retry.disabled = false;
    }
  }
}

function isWholePrice(value) {
  return value === "" || /^\d+$/.test(value);
}

function priceBoundsError() {
  const min = elements.filterMinPrice.value.trim();
  const max = elements.filterMaxPrice.value.trim();
  if (!isWholePrice(min) || !isWholePrice(max)) {
    return "Enter prices as whole numbers of 0 ₫ or more.";
  }
  if (min !== "" && max !== "" && Number(min) > Number(max)) {
    return "Minimum price cannot be greater than maximum price.";
  }
  return "";
}

function validatePriceBounds() {
  const message = priceBoundsError();
  elements.priceError.textContent = message;
  elements.priceError.hidden = message === "";
  return message === "";
}

/** Copy the visible controls into the applied query, so results always match what is shown. */
function readFilterControls() {
  currentSearch = elements.searchInput.value.trim();
  currentCategory = elements.filterCategory ? elements.filterCategory.value : "";
  currentSeller = elements.filterSeller ? elements.filterSeller.value : "";
  currentMinPrice = elements.filterMinPrice ? elements.filterMinPrice.value.trim() : "";
  currentMaxPrice = elements.filterMaxPrice ? elements.filterMaxPrice.value.trim() : "";
  currentRating = elements.filterRating ? elements.filterRating.value : "";
  currentInStock = elements.filterInStock ? elements.filterInStock.checked : true;
  currentSort = elements.catalogSort ? elements.catalogSort.value : "";
}

function applyCurrentFilters() {
  if (!validatePriceBounds()) {
    return;
  }
  readFilterControls();

  currentPage = 1;
  loadProducts();
}

function resetAllFilters() {
  elements.searchInput.value = "";
  if (elements.filterCategory) elements.filterCategory.value = "";
  if (elements.filterSeller) elements.filterSeller.value = "";
  if (elements.filterMinPrice) elements.filterMinPrice.value = "";
  if (elements.filterMaxPrice) elements.filterMaxPrice.value = "";
  if (elements.priceError) {
    elements.priceError.textContent = "";
    elements.priceError.hidden = true;
  }
  if (elements.filterRating) elements.filterRating.value = "";
  if (elements.filterInStock) elements.filterInStock.checked = true;
  if (elements.catalogSort) elements.catalogSort.value = "";

  currentSearch = "";
  currentCategory = "";
  currentSeller = "";
  currentMinPrice = "";
  currentMaxPrice = "";
  currentRating = "";
  currentInStock = true;
  currentSort = "";

  currentPage = 1;
  loadProducts();
}

async function loadFilterOptions() {
  if (
    !elements.filterCategory ||
    elements.filterCategory.tagName !== "SELECT" ||
    !elements.filterSeller ||
    elements.filterSeller.tagName !== "SELECT"
  ) {
    return;
  }
  try {
    const [categoriesRes, sellersRes] = await Promise.all([
      fetch(CATEGORIES_URL, { headers: { Accept: "application/json" } }).catch(() => null),
      fetch(SELLERS_URL, { headers: { Accept: "application/json" } }).catch(() => null),
    ]);

    if (categoriesRes && categoriesRes.ok && elements.filterCategory) {
      const categories = await categoriesRes.json();
      if (Array.isArray(categories)) {
        const defaultCatOpt = document.createElement("option");
        defaultCatOpt.value = "";
        defaultCatOpt.textContent = "All categories";
        elements.filterCategory.replaceChildren(defaultCatOpt);
        for (const cat of categories) {
          const opt = document.createElement("option");
          opt.value = String(cat.id);
          const prefix = cat.parent_id ? "— " : "";
          opt.textContent = `${prefix}${cat.name}`;
          elements.filterCategory.append(opt);
        }
      }
    }

    if (sellersRes && sellersRes.ok && elements.filterSeller) {
      const sellers = await sellersRes.json();
      if (Array.isArray(sellers)) {
        const defaultSellerOpt = document.createElement("option");
        defaultSellerOpt.value = "";
        defaultSellerOpt.textContent = "All sellers";
        elements.filterSeller.replaceChildren(defaultSellerOpt);
        for (const seller of sellers) {
          const opt = document.createElement("option");
          opt.value = String(seller.id);
          opt.textContent = seller.name;
          elements.filterSeller.append(opt);
        }
      }
    }
  } catch (err) {
    // Graceful degradation: filter controls remain functional even if remote options fail
  }
}

// Event Bindings
elements.retry.addEventListener("click", () => loadProducts());
elements.search.addEventListener("submit", (event) => {
  event.preventDefault();
  applyCurrentFilters();
});

if (elements.applyFilters) {
  elements.applyFilters.addEventListener("click", applyCurrentFilters);
}
if (elements.resetFilters) {
  elements.resetFilters.addEventListener("click", resetAllFilters);
}
if (elements.resetEmpty) {
  elements.resetEmpty.addEventListener("click", resetAllFilters);
}
if (elements.catalogSort) {
  elements.catalogSort.addEventListener("change", applyCurrentFilters);
}
if (elements.filterCategory) {
  elements.filterCategory.addEventListener("change", applyCurrentFilters);
}
if (elements.filterSeller) {
  elements.filterSeller.addEventListener("change", applyCurrentFilters);
}
if (elements.filterRating) {
  elements.filterRating.addEventListener("change", applyCurrentFilters);
}
if (elements.filterInStock) {
  elements.filterInStock.addEventListener("change", applyCurrentFilters);
}
if (elements.filterMinPrice) {
  elements.filterMinPrice.addEventListener("input", () => validatePriceBounds());
}
if (elements.filterMaxPrice) {
  elements.filterMaxPrice.addEventListener("input", () => validatePriceBounds());
}

elements.previous.addEventListener("click", () => loadProducts(currentPage - 1));
elements.next.addEventListener("click", () => loadProducts(currentPage + 1));

loadFilterOptions();
// Back navigation can restore the previous control values; load what the controls show.
readFilterControls();
if (!validatePriceBounds()) {
  currentMinPrice = "";
  currentMaxPrice = "";
}
loadProducts();
configureNavigation();
