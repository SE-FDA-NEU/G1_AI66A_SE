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
  variantLabel: document.getElementById("variant-label"),
  variant: document.getElementById("product-variant"),
  rating: document.getElementById("product-rating"),
  description: document.getElementById("product-description"),
  stock: document.getElementById("product-stock"),
  form: document.getElementById("add-to-cart-form"),
  quantity: document.getElementById("product-quantity"),
  add: document.getElementById("add-to-cart"),
  cartStatus: document.getElementById("cart-status"),
  cartLink: document.getElementById("cart-link"),
  login: document.getElementById("login-link"),
  logout: document.getElementById("logout-button"),
  myOrders: document.getElementById("my-orders-link"),
  sellerNewProduct: document.getElementById("seller-new-product-link"),
  sellerOrders: document.getElementById("seller-orders-link"),
  reviews: document.getElementById("reviews-section"),
  reviewsSummary: document.getElementById("reviews-summary"),
  reviewsError: document.getElementById("reviews-error"),
  reviewsList: document.getElementById("reviews-list"),
  reviewFormSection: document.getElementById("review-form-section"),
  reviewLoginPrompt: document.getElementById("review-login-prompt"),
  reviewLoginLink: document.getElementById("review-login-link"),
  reviewForm: document.getElementById("review-form"),
  reviewOrderItem: document.getElementById("review-order-item"),
  reviewRating: document.getElementById("review-rating"),
  reviewComment: document.getElementById("review-comment"),
  reviewMediaUrl: document.getElementById("review-media-url"),
  reviewSubmit: document.getElementById("review-submit"),
  reviewFormStatus: document.getElementById("review-form-status"),
  variantManager: document.getElementById("variant-manager"),
  variantManagerStatus: document.getElementById("variant-manager-status"),
  variantCreateForm: document.getElementById("variant-create-form"),
  variantManagerList: document.getElementById("variant-manager-list"),
};
const priceFormatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });
let currentProduct = null;
let selectedVariantId = null;
let currentIdentity = null;
let authRevision = 0;

function isCurrentAuth(token, revision) {
  return authRevision === revision && localStorage.getItem("access_token") === token;
}

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

function getReturnPath(selectedQty) {
  const qty = selectedQty !== undefined ? selectedQty : (parseInt(elements.quantity?.value, 10) || 1);
  const params = new URLSearchParams({ quantity: String(qty) });
  if (selectedVariantId !== null) params.set("variant_id", String(selectedVariantId));
  return `${window.location.pathname}?${params}`;
}

function configureNavigation() {
  const user = getUserFromToken();
  const loggedIn = Boolean(user);
  elements.login.hidden = loggedIn;
  elements.logout.hidden = !loggedIn;
  if (!loggedIn) {
    elements.login.href = `/login?return_to=${encodeURIComponent(getReturnPath())}`;
  }

  const isSeller = Boolean(user && user.role === "seller");
  const isBuyer = Boolean(user && user.role === "buyer");

  if (elements.myOrders) elements.myOrders.hidden = !isBuyer;
  if (elements.sellerNewProduct) elements.sellerNewProduct.hidden = !isSeller;
  if (elements.sellerOrders) elements.sellerOrders.hidden = !isSeller;
}

function setProductImage(imageUrl, altText) {
  elements.image.alt = altText;
  elements.image.addEventListener("error", () => {
    elements.image.src = PLACEHOLDER_IMAGE;
  }, { once: true });
  elements.image.src = imageUrl || PLACEHOLDER_IMAGE;
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
        showError("This product does not exist or is no longer for sale. Go back to the catalogue to choose another one.", false);
        return;
      }
      throw new Error(payload?.error?.message || "Unable to load product.");
    }
    const product = payload;
    elements.name.textContent = product.name;
    elements.price.textContent = priceFormatter.format(product.price);
    elements.rating.textContent = product.review_count
      ? `${Number(product.rating).toFixed(1)} ★ (${product.review_count} reviews)`
      : "No reviews yet";
    elements.description.textContent = product.description || "No description available.";
    setProductImage(product.image_url || product.thumbnail_url, product.name);
    const variants = Array.isArray(product.variants) ? product.variants : [];
    const hasVariants = Boolean(product.has_variants || variants.length);
    elements.variant.replaceChildren();
    elements.variantLabel.hidden = !hasVariants;
    elements.variant.hidden = !hasVariants;
    variants.forEach((variant) => {
      const option = document.createElement("option");
      option.value = String(variant.id);
      option.textContent = `${variant.name} · ${priceFormatter.format(variant.price)} · ${variant.stock_quantity} available`;
      elements.variant.append(option);
    });
    if (hasVariants && variants.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No active options";
      option.disabled = true;
      option.selected = true;
      elements.variant.append(option);
    }
    elements.variant.disabled = variants.length === 0;
    const requestedVariantId = new URLSearchParams(window.location.search).get("variant_id");
    const selectedVariant = variants.find((variant) => String(variant.id) === requestedVariantId);
    const selected = selectedVariant || variants[0] || (
      hasVariants ? { price: product.price, stock_quantity: 0 } : product
    );
    if (variants.length) elements.variant.value = String(selected.id);
    selectedVariantId = variants.length ? selected.id : null;
    setProductImage(selected.image_url || product.image_url || product.thumbnail_url, product.name);
    elements.price.textContent = priceFormatter.format(selected.price);
    const available = selected.stock_quantity > 0;
    elements.stock.textContent = available ? `In Stock (${selected.stock_quantity} available)` : "Out of stock";
    elements.stock.className = `product-detail__stock ${available ? "product-detail__stock--available" : "product-detail__stock--unavailable"}`;
    elements.add.disabled = !available || (hasVariants && variants.length === 0);
    elements.quantity.max = String(selected.stock_quantity);

    // Restore and revalidate selected quantity against current stock
    const preservedQty = getPreservedQuantity();
    if (available) {
      const validQty = Math.min(Math.max(1, preservedQty), selected.stock_quantity);
      elements.quantity.value = String(validQty);
      if (preservedQty > selected.stock_quantity) {
        elements.cartStatus.textContent = `Quantity adjusted to maximum available stock (${selected.stock_quantity}).`;
      }
    } else {
      elements.quantity.value = "1";
    }
    try {
      sessionStorage.removeItem(`pending_cart_${code}`);
    } catch (_) {}

    elements.detail.hidden = false;
    elements.status.hidden = true;
    currentProduct = product;
    elements.reviews.hidden = false;
    configureNavigation();
    loadReviews();
    loadReviewForm();
  } catch (error) {
    showError("We could not load this product. Check your connection, then select Retry.");
  }
}

elements.quantity.addEventListener("input", () => {
  configureNavigation();
});
elements.quantity.addEventListener("change", () => {
  configureNavigation();
});
elements.variant.addEventListener("change", () => {
  const variant = currentProduct?.variants?.find((item) => String(item.id) === elements.variant.value);
  if (!variant) return;
  selectedVariantId = variant.id;
  elements.price.textContent = priceFormatter.format(variant.price);
  setProductImage(variant.image_url || currentProduct.image_url || currentProduct.thumbnail_url, currentProduct.name);
  const available = variant.stock_quantity > 0;
  elements.stock.textContent = available ? `In Stock (${variant.stock_quantity} available)` : "Out of stock";
  elements.stock.className = `product-detail__stock ${available ? "product-detail__stock--available" : "product-detail__stock--unavailable"}`;
  elements.add.disabled = !available;
  elements.quantity.max = String(variant.stock_quantity);
  elements.quantity.value = available ? String(Math.min(Number(elements.quantity.value) || 1, variant.stock_quantity)) : "1";
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
      body: JSON.stringify({
        product_code: code,
        quantity: quantityValue,
        ...(selectedVariantId !== null ? { variant_id: selectedVariantId } : {}),
      }),
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
  authRevision += 1;
  currentIdentity = null;
  elements.reviewForm.hidden = true;
  elements.reviewLoginPrompt.hidden = false;
  elements.reviewFormStatus.textContent = "";
  elements.reviewsList.querySelectorAll(".seller-reply-form").forEach((form) => form.remove());
  configureNavigation();
  loadReviews();
  loadReviewForm();
});
elements.reviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = localStorage.getItem("access_token");
  if (!token) {
    elements.reviewFormStatus.textContent = "Log in with your buyer account to submit a review.";
    return;
  }
  const requestBody = {
    order_item_id: Number(elements.reviewOrderItem.value),
    rating: Number(elements.reviewRating.value),
    comment: elements.reviewComment.value.trim() || null,
    media_url: elements.reviewMediaUrl.value.trim() || null,
  };
  elements.reviewSubmit.disabled = true;
  elements.reviewFormStatus.textContent = "Submitting review…";
  try {
    const response = await fetch(`/api/v1/products/${encodeURIComponent(code)}/reviews`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(requestBody),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to submit review.");
    elements.reviewComment.value = "";
    elements.reviewMediaUrl.value = "";
    elements.reviewFormStatus.textContent = "Your verified-purchase review was submitted.";
    await loadReviews();
    await loadReviewForm({ preserveStatus: true });
  } catch (error) {
    elements.reviewFormStatus.textContent = error instanceof Error ? error.message : "Unable to submit review.";
  } finally {
    elements.reviewSubmit.disabled = false;
  }
});
elements.retry.addEventListener("click", loadProduct);
configureNavigation();
loadProduct();

async function loadReviews() {
  elements.reviewsError.hidden = true;
  try {
    const token = localStorage.getItem("access_token");
    const revision = authRevision;
    if (!token) currentIdentity = null;
    const response = await fetch(`/api/v1/products/${encodeURIComponent(code)}/reviews`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load reviews.");
    const reviews = Array.isArray(payload.data) ? payload.data : [];
    elements.reviewsSummary.textContent = payload.review_count
      ? `${Number(payload.rating).toFixed(1)} ★ from ${payload.review_count} verified purchase${payload.review_count === 1 ? "" : "s"}`
      : "No reviews yet.";
    elements.rating.textContent = elements.reviewsSummary.textContent;
    if (token) {
      try {
        const identityResponse = await fetch("/api/v1/auth/me", {
          headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
        });
        if (identityResponse.ok) {
          const identity = await identityResponse.json();
          if (isCurrentAuth(token, revision)) currentIdentity = identity;
        }
        else if (identityResponse.status === 401 && isCurrentAuth(token, revision)) {
          localStorage.removeItem("access_token");
          authRevision += 1;
          currentIdentity = null;
          configureNavigation();
        }
        else if (isCurrentAuth(token, revision)) {
          elements.reviewsError.textContent = "Seller reply controls could not be checked.";
          elements.reviewsError.hidden = false;
        }
      } catch {
        if (isCurrentAuth(token, revision)) {
          elements.reviewsError.textContent = "Seller reply controls could not be checked.";
          elements.reviewsError.hidden = false;
        }
      }
    }
    if (!isCurrentAuth(token, revision)) currentIdentity = null;
    elements.reviewsList.replaceChildren(...reviews.map(createReviewCard));
  } catch (error) {
    elements.reviewsError.textContent = error instanceof Error ? error.message : "Unable to load reviews.";
    elements.reviewsError.hidden = false;
  } finally {
    await loadSellerVariantControls();
  }
}

async function loadSellerVariantControls() {
  const token = localStorage.getItem("access_token");
  if (
    !token
    || currentIdentity?.role !== "seller"
    || currentIdentity.id !== currentProduct?.seller_id
  ) {
    elements.variantManager.hidden = true;
    elements.variantManagerList.replaceChildren();
    return;
  }
  elements.variantManager.hidden = false;
  elements.variantManagerStatus.textContent = "Loading product options…";
  try {
    const response = await fetch(
      `/api/v1/seller/products/${encodeURIComponent(currentProduct.id)}/variants`,
      { headers: { Accept: "application/json", Authorization: "Bearer " + token } },
    );
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load product options.");
    elements.variantManagerStatus.textContent = "";
    elements.variantManagerList.replaceChildren(...payload.data.map(renderSellerVariant));
  } catch (error) {
    elements.variantManagerStatus.textContent = error instanceof Error
      ? error.message
      : "Unable to load product options.";
  }
}

function renderSellerVariant(variant) {
  const row = document.createElement("article");
  row.className = "review-card";
  const summary = document.createElement("p");
  summary.textContent = `${variant.name} · ${variant.sku} · ${priceFormatter.format(variant.price)} · ${variant.stock_quantity} in stock · ${variant.is_active ? "Active" : "Inactive"}`;
  const form = document.createElement("form");
  form.className = "variant-edit-form";
  const values = [
    ["SKU", variant.sku, "text"],
    ["Option name", variant.name, "text"],
    ["Price (VND)", variant.price, "number"],
    ["Stock", variant.stock_quantity, "number"],
    ["Image URL", variant.image_url || "", "url"],
  ];
  const inputs = [];
  values.forEach(([labelText, value, type]) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = type;
    input.value = String(value);
    input.required = type !== "url";
    if (type === "number") {
      input.min = labelText === "Stock" ? "0" : "1";
      input.step = "1";
    }
    label.textContent = labelText;
    label.append(input);
    inputs.push(input);
    form.append(label);
  });
  const save = document.createElement("button");
  save.type = "submit";
  save.className = "button";
  save.textContent = "Save changes";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitVariantUpdate(variant.id, {
      sku: inputs[0].value,
      name: inputs[1].value,
      price: Number(inputs[2].value),
      stock_quantity: Number(inputs[3].value),
      image_url: inputs[4].value.trim() || null,
    });
  });
  row.append(summary, form);
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "button";
  toggle.textContent = variant.is_active ? "Deactivate option" : "Reactivate option";
  toggle.addEventListener("click", () =>
    submitVariantUpdate(variant.id, { is_active: !variant.is_active }));
  row.append(toggle);
  return row;
}

async function submitVariantUpdate(variantId, body) {
  const token = localStorage.getItem("access_token");
  if (!token || !currentProduct) return;
  elements.variantManagerStatus.textContent = "Saving product option…";
  try {
    const response = await fetch(
      `/api/v1/seller/products/${encodeURIComponent(currentProduct.id)}/variants/${encodeURIComponent(variantId)}`,
      {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify(body),
      },
    );
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to save product option.");
    elements.variantManagerStatus.textContent = "Product option saved.";
    await loadSellerVariantControls();
    await loadProduct();
  } catch (error) {
    elements.variantManagerStatus.textContent = error instanceof Error
      ? error.message
      : "Unable to save product option.";
  }
}

elements.variantCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = localStorage.getItem("access_token");
  if (!token || !currentProduct) return;
  const body = {
    sku: document.getElementById("variant-sku").value.trim(),
    name: document.getElementById("variant-name").value.trim(),
    price: Number(document.getElementById("variant-price").value),
    stock_quantity: Number(document.getElementById("variant-stock").value),
    image_url: document.getElementById("variant-image").value.trim() || null,
  };
  elements.variantManagerStatus.textContent = "Adding product option…";
  try {
    const response = await fetch(
      `/api/v1/seller/products/${encodeURIComponent(currentProduct.id)}/variants`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify(body),
      },
    );
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to add product option.");
    elements.variantCreateForm.reset();
    elements.variantManagerStatus.textContent = "Product option added.";
    await loadSellerVariantControls();
    await loadProduct();
  } catch (error) {
    elements.variantManagerStatus.textContent = error instanceof Error
      ? error.message
      : "Unable to add product option.";
  }
});

function createReviewCard(review) {
  const card = document.createElement("article");
  card.className = "review-card";
  const heading = document.createElement("h3");
  heading.textContent = `${"★".repeat(review.rating)}${"☆".repeat(5 - review.rating)} · Verified purchase`;
  const date = document.createElement("time");
  date.dateTime = review.created_at;
  date.textContent = new Date(review.created_at).toLocaleDateString();
  card.append(heading, date);
  if (review.comment) {
    const comment = document.createElement("p");
    comment.textContent = review.comment;
    card.append(comment);
  }
  if (review.media_url) {
    const media = document.createElement("a");
    media.href = review.media_url;
    media.target = "_blank";
    media.rel = "noopener noreferrer";
    media.textContent = "View review media";
    card.append(media);
  }
  if (review.seller_reply) {
    const reply = document.createElement("div");
    reply.className = "review-card__reply";
    const replyHeading = document.createElement("h4");
    replyHeading.textContent = "Seller reply";
    const replyText = document.createElement("p");
    replyText.textContent = review.seller_reply;
    const replyDate = document.createElement("time");
    replyDate.dateTime = review.seller_replied_at;
    replyDate.textContent = new Date(review.seller_replied_at).toLocaleDateString();
    reply.append(replyHeading, replyText, replyDate);
    card.append(reply);
  }
  if (
    currentIdentity?.role === "seller"
    && currentIdentity.id === currentProduct?.seller_id
  ) {
    appendSellerReplyForm(card, review);
  }
  return card;
}

async function loadReviewForm({ preserveStatus = false } = {}) {
  const token = localStorage.getItem("access_token");
  const revision = authRevision;
  elements.reviewFormSection.hidden = false;
  elements.reviewForm.hidden = true;
  elements.reviewLoginPrompt.hidden = Boolean(token);
  if (!preserveStatus) elements.reviewFormStatus.textContent = "";
  elements.reviewLoginLink.href = `/login?return_to=${encodeURIComponent(window.location.pathname)}`;
  if (!token) return;
  try {
    const identityResponse = await fetch("/api/v1/auth/me", {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    if (!isCurrentAuth(token, revision)) return;
    if (identityResponse.status === 401) {
      localStorage.removeItem("access_token");
      authRevision += 1;
      elements.reviewLoginPrompt.hidden = false;
      configureNavigation();
      return;
    }
    if (!identityResponse.ok) {
      throw new Error("Unable to verify the current account.");
    }
    const identity = await identityResponse.json();
    if (!isCurrentAuth(token, revision)) return;
    if (identity.role !== "buyer") {
      elements.reviewFormStatus.textContent = "Only buyer accounts can submit product reviews.";
      return;
    }
    const response = await fetch(
      `/api/v1/products/${encodeURIComponent(code)}/reviewable-items`,
      { headers: { Accept: "application/json", Authorization: `Bearer ${token}` } },
    );
    const payload = await response.json().catch(() => null);
    if (!isCurrentAuth(token, revision)) return;
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to check completed purchases.");
    const items = Array.isArray(payload.data) ? payload.data : [];
    elements.reviewOrderItem.replaceChildren(...items.map((item) => {
      const option = document.createElement("option");
      option.value = String(item.order_item_id);
      option.textContent = `Order item #${item.order_item_id} · quantity ${item.quantity}`;
      return option;
    }));
    elements.reviewForm.hidden = items.length === 0;
    if (items.length === 0) {
      if (!preserveStatus || !elements.reviewFormStatus.textContent) {
        elements.reviewFormStatus.textContent = "There are no completed, unreviewed purchases for this product.";
      }
    } else if (!preserveStatus) {
      elements.reviewFormStatus.textContent = "";
    }
  } catch (error) {
    if (!isCurrentAuth(token, revision)) return;
    elements.reviewFormStatus.textContent = error instanceof Error ? error.message : "Unable to check completed purchases.";
  }
}

function appendSellerReplyForm(card, review) {
  const form = document.createElement("form");
  form.className = "seller-reply-form";
  const label = document.createElement("label");
  label.textContent = review.seller_reply ? "Update your reply" : "Reply to this review";
  const input = document.createElement("textarea");
  input.required = true;
  input.maxLength = 2000;
  input.rows = 3;
  input.value = review.seller_reply || "";
  const button = document.createElement("button");
  button.type = "submit";
  button.className = "button";
  button.textContent = review.seller_reply ? "Update reply" : "Reply";
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  form.append(label, input, button, status);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = localStorage.getItem("access_token");
    if (!token) {
      status.textContent = "Log in with your seller account to reply to reviews.";
      return;
    }
    button.disabled = true;
    try {
      const replyResponse = await fetch(`/api/v1/seller/reviews/${review.id}/reply`, {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reply: input.value.trim() }),
      });
      const replyPayload = await replyResponse.json().catch(() => null);
      if (!replyResponse.ok) throw new Error(replyPayload?.error?.message || "Unable to save reply.");
      status.textContent = "Reply saved.";
      await loadReviews();
    } catch (cause) {
      status.textContent = cause instanceof Error ? cause.message : "Unable to save reply.";
    } finally {
      button.disabled = false;
    }
  });
  card.append(form);
}
