"use strict";

const PLACEHOLDER_IMAGE = "/static/product-placeholder.svg";
const code = decodeURIComponent(window.location.pathname.split("/").pop() || "");
const elements = {
  status: document.getElementById("detail-status"),
  detail: document.getElementById("product-detail"),
  error: document.getElementById("detail-error"),
  errorMessage: document.getElementById("detail-error-message"),
  retry: document.getElementById("detail-retry"),
  image: document.getElementById("product-image"),
  name: document.getElementById("product-name"),
  price: document.getElementById("product-price"),
  description: document.getElementById("product-description"),
  stock: document.getElementById("product-stock"),
  form: document.getElementById("add-to-cart-form"),
  quantity: document.getElementById("product-quantity"),
  add: document.getElementById("add-to-cart"),
  cartStatus: document.getElementById("cart-status"),
  login: document.getElementById("login-link"),
  logout: document.getElementById("logout-button"),
};
const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

function configureNavigation() {
  const loggedIn = Boolean(localStorage.getItem("access_token"));
  elements.login.hidden = loggedIn;
  elements.logout.hidden = !loggedIn;
  if (!loggedIn) {
    elements.login.href = `/login?return_to=${encodeURIComponent(window.location.pathname)}`;
  }
}

function showError(message, retry = true) {
  elements.status.hidden = true;
  elements.detail.hidden = true;
  elements.error.hidden = false;
  elements.errorMessage.textContent = message;
  elements.retry.hidden = !retry;
}

async function loadProduct() {
  elements.status.hidden = false;
  elements.status.textContent = "Loading product…";
  elements.error.hidden = true;
  try {
    const response = await fetch(`/api/v1/products/${encodeURIComponent(code)}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 404) {
        showError("Product not found.", false);
        return;
      }
      throw new Error(payload?.error?.message || "Unable to load product.");
    }
    const product = payload;
    elements.name.textContent = product.name;
    elements.price.textContent = priceFormatter.format(product.price);
    elements.description.textContent = product.description || "No description available.";
    elements.image.alt = product.name;
    elements.image.src = product.image_url || product.thumbnail_url || PLACEHOLDER_IMAGE;
    elements.image.addEventListener("error", () => { elements.image.src = PLACEHOLDER_IMAGE; }, { once: true });
    const available = product.stock_quantity > 0;
    elements.stock.textContent = available ? `In Stock (${product.stock_quantity} available)` : "Out of stock";
    elements.stock.className = `product-detail__stock ${available ? "product-detail__stock--available" : "product-detail__stock--unavailable"}`;
    elements.add.disabled = !available;
    elements.quantity.max = String(product.stock_quantity);
    elements.detail.hidden = false;
    elements.status.hidden = true;
  } catch (error) {
    showError("Something went wrong. Please try again later.");
  }
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = localStorage.getItem("access_token");
  if (!token) {
    window.location.assign(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
    return;
  }
  elements.add.disabled = true;
  elements.cartStatus.textContent = "";
  try {
    const response = await fetch("/api/v1/cart/items", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ product_code: code, quantity: Number(elements.quantity.value) }),
    });
    const payload = await response.json().catch(() => null);
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      window.location.assign(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to add product to cart.");
    elements.cartStatus.textContent = "Product added to cart.";
  } catch (error) {
    elements.cartStatus.textContent = error instanceof Error ? error.message : "Unable to add product to cart.";
  } finally {
    elements.add.disabled = elements.quantity.max === "0";
  }
});

elements.logout.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  configureNavigation();
});
elements.retry.addEventListener("click", loadProduct);
configureNavigation();
loadProduct();
