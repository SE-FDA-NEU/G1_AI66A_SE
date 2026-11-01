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
  adminPortal: document.getElementById("admin-portal-link"),
  reviews: document.getElementById("reviews-section"),
  reviewsSummary: document.getElementById("reviews-summary"),
  reviewsError: document.getElementById("reviews-error"),
  reviewsRetry: document.getElementById("reviews-retry"),
  reviewsFeedback: document.getElementById("reviews-feedback"),
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
  reviewEligibilityRetry: document.getElementById("review-eligibility-retry"),
  reviewOrderError: document.getElementById("review-order-item-error"),
  reviewRatingError: document.getElementById("review-rating-error"),
  reviewCommentError: document.getElementById("review-comment-error"),
  reviewMediaError: document.getElementById("review-media-error"),
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
let reviewsRevision = 0;
let eligibilityRevision = 0;
let reviewFormAuth = null;
let reviewSubmitting = false;
const MAX_REVIEW_MEDIA = 5;
const REVIEW_REQUEST_TIMEOUT = 15000;

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
  const isAdmin = Boolean(user && user.role === "admin");

  if (elements.myOrders) elements.myOrders.hidden = !isBuyer;
  if (elements.sellerNewProduct) elements.sellerNewProduct.hidden = !isSeller;
  if (elements.sellerOrders) elements.sellerOrders.hidden = !isSeller;
  if (elements.adminPortal) elements.adminPortal.hidden = !isAdmin;
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
  reviewFormAuth = null;
  elements.reviewComment.value = "";
  elements.reviewMediaUrl.value = "";
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
  if (reviewSubmitting) return;
  const token = localStorage.getItem("access_token");
  const revision = authRevision;
  if (!token) {
    elements.reviewFormStatus.textContent = "Log in with your buyer account to submit a review.";
    return;
  }
  if (!reviewFormAuth || reviewFormAuth.token !== token
      || !isCurrentAuth(token, reviewFormAuth.revision)) {
    reviewFormAuth = null;
    elements.reviewComment.value = "";
    elements.reviewMediaUrl.value = "";
    elements.reviewFormStatus.textContent = "Account changed. Check your completed purchases again.";
    await loadReviewForm({ preserveStatus: true });
    return;
  }
  const mediaUrls = elements.reviewMediaUrl.value.split(/\r?\n/).map(url => url.trim()).filter(Boolean);
  const orderItem = Number(elements.reviewOrderItem.value);
  const rating = Number(elements.reviewRating.value);
  const validations = [
    [elements.reviewOrderItem, elements.reviewOrderError,
      reviewFormAuth.items.has(orderItem) ? "" : "Choose an eligible completed purchase."],
    [elements.reviewRating, elements.reviewRatingError,
      Number.isInteger(rating) && rating >= 1 && rating <= 5 ? "" : "Choose a rating from 1 to 5."],
    [elements.reviewComment, elements.reviewCommentError,
      elements.reviewComment.value.trim().length <= 2000 ? "" : "Keep your comment within 2000 characters."],
    [elements.reviewMediaUrl, elements.reviewMediaError,
      mediaUrls.length > MAX_REVIEW_MEDIA ? "Attach at most 5 image or video URLs."
        : mediaUrls.some(url => !safeReviewMediaUrl(url))
          ? "Use an absolute HTTP(S) media URL of at most 2048 characters on each line." : ""],
  ];
  for (const [field, error, message] of validations) {
    field.setAttribute("aria-invalid", message ? "true" : "false");
    error.textContent = message;
    error.hidden = !message;
  }
  const invalid = validations.find(([, , message]) => message);
  if (invalid) {
    elements.reviewFormStatus.textContent = invalid[2];
    invalid[0].focus?.();
    return;
  }
  const requestBody = {
    order_item_id: orderItem,
    rating,
    comment: elements.reviewComment.value.trim() || null,
    media_urls: mediaUrls,
  };
  reviewSubmitting = true;
  setReviewFormPending(true);
  elements.reviewFormStatus.textContent = "Submitting review…";
  try {
    const response = await reviewRequest(`/api/v1/products/${encodeURIComponent(code)}/reviews`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(requestBody),
    });
    const payload = await response.json().catch(() => null);
    if (!isCurrentAuth(token, revision)) return;
    if (!response.ok && ["ERR_REVIEW_ALREADY_EXISTS", "ERR_REVIEW_NOT_COMPLETED",
      "ERR_REVIEW_NOT_ELIGIBLE"].includes(payload?.error?.code)) {
      elements.reviewFormStatus.textContent = payload.error.message;
      await loadReviewForm({ preserveStatus: true });
      return;
    }
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to submit review.");
    elements.reviewComment.value = "";
    elements.reviewMediaUrl.value = "";
    elements.reviewFormStatus.textContent = "Your verified-purchase review was submitted.";
    await loadReviews();
    await loadReviewForm({ preserveStatus: true });
  } catch (error) {
    if (!isCurrentAuth(token, revision)) return;
    elements.reviewFormStatus.textContent = error instanceof Error ? error.message : "Unable to submit review.";
  } finally {
    reviewSubmitting = false;
    setReviewFormPending(false);
  }
});
elements.retry.addEventListener("click", loadProduct);
elements.reviewsRetry.addEventListener("click", () => loadReviews());
elements.reviewEligibilityRetry.addEventListener("click", () => loadReviewForm());
configureNavigation();
loadProduct();

async function loadReviews() {
  const requestId = ++reviewsRevision;
  elements.reviews.setAttribute("aria-busy", "true");
  elements.reviewsSummary.textContent = "Loading reviews…";
  elements.reviewsError.hidden = true;
  elements.reviewsRetry.hidden = true;
  elements.reviewsList.hidden = true;
  try {
    const token = localStorage.getItem("access_token");
    const revision = authRevision;
    currentIdentity = null;
    const response = await reviewRequest(`/api/v1/products/${encodeURIComponent(code)}/reviews`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => null);
    if (requestId !== reviewsRevision) return;
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load reviews.");
    const reviews = Array.isArray(payload.data) ? payload.data : [];
    elements.reviewsSummary.textContent = payload.review_count
      ? `${Number(payload.rating).toFixed(1)} ★ from ${payload.review_count} verified purchase${payload.review_count === 1 ? "" : "s"}`
      : "No reviews yet.";
    elements.rating.textContent = elements.reviewsSummary.textContent;
    if (token) {
      try {
        const identityResponse = await reviewRequest("/api/v1/auth/me", {
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
    if (requestId !== reviewsRevision) return;
    if (!isCurrentAuth(token, revision)) currentIdentity = null;
    elements.reviewsList.replaceChildren(...reviews.map(createReviewCard));
    elements.reviewsList.hidden = false;
  } catch (error) {
    if (requestId !== reviewsRevision) return;
    elements.reviewsSummary.textContent = "Reviews could not be loaded.";
    elements.reviewsError.textContent = error instanceof Error ? error.message : "Unable to load reviews.";
    elements.reviewsError.hidden = false;
    elements.reviewsRetry.hidden = false;
  } finally {
    if (requestId === reviewsRevision) {
      elements.reviews.setAttribute("aria-busy", "false");
      await loadSellerVariantControls();
    }
  }
}

async function reviewRequest(url, options = {}) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), REVIEW_REQUEST_TIMEOUT) : null;
  try {
    return await fetch(url, { ...options, ...(controller ? { signal: controller.signal } : {}) });
  } catch (error) {
    throw new Error(error?.name === "AbortError"
      ? "The request timed out. Please try again." : "We could not reach the server. Please try again.");
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

function setReviewFormPending(pending) {
  [elements.reviewSubmit, elements.reviewOrderItem, elements.reviewRating,
    elements.reviewComment, elements.reviewMediaUrl].forEach(field => { field.disabled = pending; });
}

function safeReviewMediaUrl(value) {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url : null;
  } catch { return null; }
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
  summary.textContent = `${variant.name} · ${variant.sku} · ${priceFormatter.format(variant.price)} · Physical: ${variant.stock_quantity} · Reserved: ${variant.reserved_stock} · Available: ${variant.available_stock} · ${variant.is_active ? "Active" : "Inactive"}`;
  const form = document.createElement("form");
  form.className = "variant-edit-form";
  const values = [
    ["SKU *", variant.sku, "text"],
    ["Option name *", variant.name, "text"],
    ["Price (VND) *", variant.price, "number"],
    ["Physical stock *", variant.stock_quantity, "number"],
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
    const values = {
      sku: inputs[0].value.trim(),
      name: inputs[1].value.trim(),
      price: Number(inputs[2].value),
      stock_quantity: Number(inputs[3].value),
      image_url: inputs[4].value.trim() || null,
    };
    const original = {
      sku: variant.sku,
      name: variant.name,
      price: variant.price,
      stock_quantity: variant.stock_quantity,
      image_url: variant.image_url,
    };
    const changes = { expected_version: variant.version };
    Object.keys(values).forEach((field) => {
      if (values[field] !== original[field]) changes[field] = values[field];
    });
    if (Object.keys(changes).length === 1) {
      elements.variantManagerStatus.textContent = "No changes to save.";
      return;
    }
    await submitVariantUpdate(variant.id, changes);
  });
  row.append(summary, form);
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "button";
  toggle.textContent = variant.is_active ? "Deactivate option" : "Reactivate option";
  toggle.addEventListener("click", () =>
    submitVariantUpdate(variant.id, {
      expected_version: variant.version,
      is_active: !variant.is_active,
    }));
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
  const rating = Math.max(1, Math.min(5, Math.trunc(Number(review.rating) || 1)));
  heading.textContent = `${rating}/5 ${"★".repeat(rating)}${"☆".repeat(5 - rating)} · Verified purchase`;
  card.append(heading);
  appendReviewTime(card, review.created_at, "Reviewed");
  if (review.comment) {
    const comment = document.createElement("p");
    comment.textContent = review.comment;
    card.append(comment);
  }
  appendReviewMedia(card, review);
  if (review.seller_reply) {
    const reply = document.createElement("div");
    reply.className = "review-card__reply";
    const replyHeading = document.createElement("h4");
    replyHeading.textContent = "Seller reply";
    const replyText = document.createElement("p");
    replyText.textContent = review.seller_reply;
    reply.append(replyHeading, replyText);
    appendReviewTime(reply, review.seller_replied_at, "Seller replied");
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

function appendReviewTime(container, value, label) {
  if (!value) return;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return;
  const time = document.createElement("time");
  time.dateTime = date.toISOString();
  time.textContent = `${label} ${date.toLocaleString()}`;
  container.append(time);
}

function appendReviewMedia(card, review) {
  const refs = [...new Set([...(Array.isArray(review.media_urls) ? review.media_urls : []),
    ...(review.media_url ? [review.media_url] : [])])].slice(0, MAX_REVIEW_MEDIA);
  const gallery = document.createElement("div");
  gallery.className = "review-media";
  for (const [index, value] of refs.entries()) {
    const url = safeReviewMediaUrl(value);
    if (!url) continue;
    const figure = document.createElement("figure");
    const isImage = /\.(png|jpe?g|gif|webp|avif|svg)$/i.test(url.pathname);
    const isVideo = /\.(mp4|webm|ogv|ogg)$/i.test(url.pathname);
    if (isImage || isVideo) {
      const preview = document.createElement(isImage ? "img" : "video");
      preview.className = isImage ? "review-media__image" : "review-media__video";
      if (isImage) {
        preview.alt = `Review photo ${index + 1}`;
        preview.loading = "lazy";
      } else {
        preview.controls = true;
        preview.preload = "metadata";
        preview.setAttribute("aria-label", `Review video ${index + 1}`);
      }
      const unavailable = document.createElement("p");
      unavailable.textContent = "Preview unavailable. Open the media link below.";
      unavailable.hidden = true;
      preview.addEventListener("error", () => {
        preview.hidden = true;
        unavailable.hidden = false;
      }, { once: true });
      preview.src = url.href;
      figure.append(preview, unavailable);
    }
    const link = document.createElement("a");
    link.className = "review-media__link";
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `Open ${isImage ? "image" : isVideo ? "video" : "media"} ${index + 1} (new tab)`;
    figure.append(link);
    gallery.append(figure);
  }
  if (gallery.children.length) card.append(gallery);
}

async function loadReviewForm({ preserveStatus = false } = {}) {
  const requestId = ++eligibilityRevision;
  const token = localStorage.getItem("access_token");
  const revision = authRevision;
  const isCurrentForm = () => requestId === eligibilityRevision && isCurrentAuth(token, revision);
  reviewFormAuth = null;
  elements.reviewEligibilityRetry.hidden = true;
  elements.reviewFormSection.hidden = false;
  elements.reviewForm.hidden = true;
  elements.reviewLoginPrompt.hidden = Boolean(token);
  if (!preserveStatus) elements.reviewFormStatus.textContent = "";
  elements.reviewLoginLink.href = `/login?return_to=${encodeURIComponent(window.location.pathname)}`;
  if (!token) return;
  if (!preserveStatus) elements.reviewFormStatus.textContent = "Checking completed purchases…";
  try {
    const identityResponse = await reviewRequest("/api/v1/auth/me", {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    if (!isCurrentForm()) return;
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
    if (!isCurrentForm()) return;
    if (identity.role !== "buyer") {
      elements.reviewFormStatus.textContent = "Only buyer accounts can submit product reviews.";
      return;
    }
    const response = await reviewRequest(
      `/api/v1/products/${encodeURIComponent(code)}/reviewable-items`,
      { headers: { Accept: "application/json", Authorization: `Bearer ${token}` } },
    );
    const payload = await response.json().catch(() => null);
    if (!isCurrentForm()) return;
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to check completed purchases.");
    const items = Array.isArray(payload.data) ? payload.data : [];
    reviewFormAuth = { token, revision, items: new Set(items.map(item => Number(item.order_item_id))) };
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
    if (!isCurrentForm()) return;
    const message = error instanceof Error ? error.message : "Unable to check completed purchases.";
    elements.reviewFormStatus.textContent = preserveStatus && elements.reviewFormStatus.textContent
      ? `${elements.reviewFormStatus.textContent} ${message}` : message;
    elements.reviewEligibilityRetry.hidden = false;
  }
}

function appendSellerReplyForm(card, review) {
  const ownerToken = localStorage.getItem("access_token");
  const ownerRevision = authRevision;
  let saving = false;
  const form = document.createElement("form");
  form.className = "seller-reply-form";
  const label = document.createElement("label");
  label.textContent = review.seller_reply ? "Update your reply *" : "Reply to this review *";
  const input = document.createElement("textarea");
  input.id = `seller-reply-${review.id}`;
  label.htmlFor = input.id;
  input.required = true;
  input.maxLength = 2000;
  input.rows = 3;
  input.value = review.seller_reply || "";
  const button = document.createElement("button");
  button.type = "submit";
  button.className = "button";
  button.textContent = review.seller_reply ? "Update reply" : "Reply";
  const status = document.createElement("p");
  status.id = `seller-reply-status-${review.id}`;
  status.setAttribute("role", "status");
  input.setAttribute("aria-describedby", status.id);
  form.append(label, input, button, status);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving) return;
    const token = localStorage.getItem("access_token");
    if (!token) {
      status.textContent = "Log in with your seller account to reply to reviews.";
      return;
    }
    if (token !== ownerToken || !isCurrentAuth(ownerToken, ownerRevision)) {
      status.textContent = "Account changed. Reload reviews before replying.";
      return;
    }
    const reply = input.value.trim();
    if (!reply || reply.length > 2000) {
      status.textContent = "Enter a reply from 1 to 2000 characters.";
      input.setAttribute("aria-invalid", "true");
      input.focus?.();
      return;
    }
    input.setAttribute("aria-invalid", "false");
    saving = true;
    button.disabled = true;
    input.disabled = true;
    status.textContent = "Saving reply…";
    try {
      const replyResponse = await reviewRequest(`/api/v1/seller/reviews/${review.id}/reply`, {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reply }),
      });
      const replyPayload = await replyResponse.json().catch(() => null);
      if (!isCurrentAuth(ownerToken, ownerRevision)) return;
      if (!replyResponse.ok) throw new Error(replyPayload?.error?.message || "Unable to save reply.");
      status.textContent = "Reply saved.";
      elements.reviewsFeedback.textContent = "Seller reply saved.";
      await loadReviews();
    } catch (cause) {
      if (!isCurrentAuth(ownerToken, ownerRevision)) return;
      status.textContent = cause instanceof Error ? cause.message : "Unable to save reply.";
    } finally {
      saving = false;
      button.disabled = false;
      input.disabled = false;
    }
  });
  card.append(form);
}

window.addEventListener?.("storage", (event) => {
  if (event.key !== "access_token" && event.key !== null) return;
  authRevision += 1;
  reviewFormAuth = null;
  currentIdentity = null;
  elements.reviewForm.hidden = true;
  elements.reviewComment.value = "";
  elements.reviewMediaUrl.value = "";
  elements.reviewsList.querySelectorAll(".seller-reply-form").forEach(form => form.remove());
  configureNavigation();
  loadReviews();
  loadReviewForm();
});
