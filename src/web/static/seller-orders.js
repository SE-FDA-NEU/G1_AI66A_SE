"use strict";

const LOGIN_URL = `/login?return_to=${encodeURIComponent("/seller/orders")}`;
const NETWORK_MESSAGE = "We could not reach the server. Check your connection, then select Retry.";
const SELLER_ONLY_MESSAGE = "Only seller accounts can manage orders. Log in with a seller account.";

const elements = {
  form: document.getElementById("filters"),
  status: document.getElementById("status"),
  from: document.getElementById("from"),
  to: document.getElementById("to"),
  message: document.getElementById("orders-status"),
  empty: document.getElementById("orders-empty"),
  error: document.getElementById("orders-error"),
  retry: document.getElementById("orders-retry"),
  list: document.getElementById("orders-list"),
  pagination: document.getElementById("orders-pagination"),
  previous: document.getElementById("orders-previous"),
  next: document.getElementById("orders-next"),
  page: document.getElementById("orders-page"),
  logout: document.getElementById("logout-button"),
};

const transitions = {
  PENDING: [
    { status: "CONFIRMED", label: "Confirm order" },
    { status: "PROCESSING", label: "Start processing" },
    { status: "CANCELLED", label: "Cancel" },
  ],
  CONFIRMED: [
    { status: "SHIPPED", label: "Mark shipped" },
    { status: "CANCELLED", label: "Cancel" },
  ],
  PROCESSING: [
    { status: "SHIPPED", label: "Mark shipped" },
    { status: "CANCELLED", label: "Cancel" },
  ],
  CANCELLATION_REQUESTED: [
    { status: "CANCELLED", label: "Approve cancellation" },
    { status: "CONFIRMED", label: "Reject cancellation" },
  ],
  SHIPPED: [
    { status: "DELIVERED", label: "Mark delivered" },
    { status: "COMPLETED", label: "Mark completed" },
  ],
  DELIVERED: [{ status: "COMPLETED", label: "Mark completed" }],
  RETURN_REQUESTED: [],
  RETURNED_REFUNDED: [],
  COMPLETED: [],
  CANCELLED: [],
};

let currentPage = 1;

/** A missing or rejected token goes to login and comes back here afterwards. */
function goToLogin() {
  localStorage.removeItem("access_token");
  window.location.replace(LOGIN_URL);
}

/** Send one request with the stored token; resolves to null when the page leaves for login. */
async function request(url, options = {}) {
  const token = localStorage.getItem("access_token");
  if (!token) {
    goToLogin();
    return null;
  }
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { Accept: "application/json", Authorization: `Bearer ${token}`, ...options.headers },
    });
  } catch {
    throw new Error(NETWORK_MESSAGE);
  }
  if (response.status === 401) {
    goToLogin();
    return null;
  }
  const payload = await response.json().catch(() => null);
  if (response.status === 403 && payload?.error?.code === "ERR_SELLER_REQUIRED") {
    throw new Error(SELLER_ONLY_MESSAGE);
  }
  if (!response.ok) throw new Error(payload?.error?.message || "The server could not complete the request. Select Retry.");
  return payload;
}

function setState(state, message) {
  elements.message.textContent = message;
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.list.hidden = state !== "success";
  elements.pagination.hidden = state !== "success";
}

function createOrderCard(order) {
  const card = document.createElement("article");
  card.className = "order-card";
  const header = document.createElement("div");
  header.className = "order-card__header";
  const title = document.createElement("h2");
  title.textContent = `Order #${order.id} (parent #${order.order_id})`;
  const status = document.createElement("span");
  status.className = "status";
  status.textContent = order.status;
  header.append(title, status);
  card.append(header);
  const customer = document.createElement("p");
  customer.textContent = `Customer: ${order.customer_name}`;
  card.append(customer);
  const items = document.createElement("ul");
  items.className = "order-card__items";
  order.items.forEach((item) => {
    const line = document.createElement("li");
    const purchasedName = item.variant_name
      ? `${item.product_name} · ${item.variant_name}`
      : item.product_name;
    line.textContent = `${purchasedName} × ${item.quantity} (${item.total_price.toLocaleString("vi-VN")} ₫)`;
    items.append(line);
  });
  card.append(items);
  if (order.tracking_number) {
    const tracking = document.createElement("p");
    tracking.className = "order-card__tracking";
    tracking.textContent = `Tracking: ${order.tracking_number}`;
    card.append(tracking);
  }
  const trackLink = document.createElement("a");
  trackLink.href = `/order/${order.order_id}`;
  trackLink.textContent = order.status === "RETURN_REQUESTED"
    ? `⚠️ Review Return & Refund (Order #${order.order_id})`
    : `Track Order (parent #${order.order_id})`;
  trackLink.className = "order-card__tracker-link";
  if (order.status === "RETURN_REQUESTED") {
    trackLink.style.color = "#ea580c";
    trackLink.style.fontWeight = "bold";
  }
  card.append(trackLink);
  transitions[order.status]?.forEach((transition) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = transition.label;
    button.addEventListener("click", () => updateStatus(order.id, transition.status));
    card.append(button);
  });
  return card;
}

function updatePagination(meta) {
  const totalPages = Math.ceil(meta.total / meta.limit);
  currentPage = meta.page;
  elements.pagination.hidden = totalPages <= 1;
  elements.previous.disabled = currentPage <= 1;
  elements.next.disabled = currentPage >= totalPages;
  elements.page.textContent = `Page ${currentPage} of ${totalPages}`;
}

async function loadOrders(page = currentPage) {
  currentPage = page;
  setState("loading", "Loading orders…");
  const params = new URLSearchParams({ page: String(currentPage), limit: "20" });
  if (elements.status.value) params.set("status", elements.status.value);
  if (elements.from.value) params.set("from", elements.from.value);
  if (elements.to.value) params.set("to", elements.to.value);
  try {
    const payload = await request(`/api/v1/seller/orders?${params}`);
    if (payload === null) return;
    if (!Array.isArray(payload.data)) throw new Error("The server sent an unexpected answer. Select Retry.");
    elements.list.replaceChildren(...payload.data.map(createOrderCard));
    setState(payload.data.length ? "success" : "empty", `${payload.data.length} seller orders found.`);
    if (payload.data.length) updatePagination(payload.meta);
  } catch (error) {
    setState("error", error.message);
  }
}

async function updateStatus(id, status) {
  if (status === "CANCELLED" && !window.confirm("Cancel this order and restore stock?")) return;
  const body = { status };
  if (status === "SHIPPED" && typeof window.prompt === "function") {
    const tracking = window.prompt("Enter tracking number (optional):");
    if (tracking && tracking.trim()) body.tracking_number = tracking.trim();
  }
  let payload;
  try {
    payload = await request(`/api/v1/seller/orders/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    // Keep the list on screen; only this order failed to change.
    elements.message.textContent = `Order #${id} was not updated. ${error.message}`;
    return;
  }
  if (payload !== null) await loadOrders();
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  currentPage = 1;
  loadOrders();
});
elements.retry.addEventListener("click", loadOrders);
elements.previous.addEventListener("click", () => loadOrders(currentPage - 1));
elements.next.addEventListener("click", () => loadOrders(currentPage + 1));
elements.logout.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  window.location.href = "/login?return_to=/seller/orders";
});
loadOrders();
