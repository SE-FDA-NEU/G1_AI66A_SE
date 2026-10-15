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
  cartLink: document.getElementById("cart-link"),
  login: document.getElementById("login-link"),
  logout: document.getElementById("logout-button"),
};
const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

function getReturnPath(selectedQty) {
  const qty = selectedQty !== undefined ? selectedQty : (parseInt(elements.quantity?.value, 10) || 1);
  return `${window.location.pathname}?quantity=${encodeURIComponent(qty)}`;
}

function configureNavigation() {
  const loggedIn = Boolean(localStorage.getItem("access_token"));
  elements.login.hidden = loggedIn;
  elements.logout.hidden = !loggedIn;
  if (!loggedIn) {
    elements.login.href = `/login?return_to=${encodeURIComponent(getReturnPath())}`;
  }
}

function getPreservedQuantity() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("quantity");
  if (fromQuery && !isNaN(Number(fromQuery))) {
    const parsed = parseInt(fromQuery, 10);
    if (parsed > 0) return parsed;
  }
  try {
    const saved = sessionStorage.getItem(`pending_cart_${code}`);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed && typeof parsed.quantity === "number" && parsed.quantity > 0) {
        return parsed.quantity;
      }
    }
  } catch (_) {}
  return 1;
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

    // Restore and revalidate selected quantity against current stock
    const preservedQty = getPreservedQuantity();
    if (available) {
      const validQty = Math.min(Math.max(1, preservedQty), product.stock_quantity);
      elements.quantity.value = String(validQty);
      if (preservedQty > product.stock_quantity) {
        elements.cartStatus.textContent = `Quantity adjusted to maximum available stock (${product.stock_quantity}).`;
      }
    } else {
      elements.quantity.value = "1";
    }
    try {
      sessionStorage.removeItem(`pending_cart_${code}`);
    } catch (_) {}

    elements.detail.hidden = false;
    elements.status.hidden = true;
    configureNavigation();
  } catch (error) {
    showError("Something went wrong. Please try again later.");
  }
}

elements.quantity.addEventListener("input", () => {
  configureNavigation();
});
elements.quantity.addEventListener("change", () => {
  configureNavigation();
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = localStorage.getItem("access_token");
  const quantityValue = parseInt(elements.quantity.value, 10) || 1;

  if (!token) {
    const returnDestination = getReturnPath(quantityValue);
    try {
      sessionStorage.setItem(`pending_cart_${code}`, JSON.stringify({ product_code: code, quantity: quantityValue }));
    } catch (_) {}
    window.location.assign(`/login?return_to=${encodeURIComponent(returnDestination)}`);
    return;
  }
  elements.add.disabled = true;
  elements.cartStatus.textContent = "";
  try {
    const response = await fetch("/api/v1/cart/items", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ product_code: code, quantity: quantityValue }),
    });
    const payload = await response.json().catch(() => null);
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      const returnDestination = getReturnPath(quantityValue);
      try {
        sessionStorage.setItem(`pending_cart_${code}`, JSON.stringify({ product_code: code, quantity: quantityValue }));
      } catch (_) {}
      window.location.assign(`/login?return_to=${encodeURIComponent(returnDestination)}`);
      return;
    }
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to add product to cart.");
    elements.cartStatus.innerHTML = 'Product added to cart. <a id="view-cart-link" class="button button--link" href="/cart">Proceed to Cart →</a>';
    window.location.assign("/cart");
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
