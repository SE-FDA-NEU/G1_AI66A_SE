"use strict";

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
  logout: document.getElementById("logout-button"),
};

const transitions = {
  PENDING: [{ status: "PROCESSING", label: "Start processing" }, { status: "CANCELLED", label: "Cancel" }],
  PROCESSING: [{ status: "SHIPPED", label: "Mark shipped" }],
  SHIPPED: [{ status: "COMPLETED", label: "Mark completed" }],
  COMPLETED: [],
  CANCELLED: [],
};

function setState(state, message) {
  elements.message.textContent = message;
  elements.empty.hidden = state !== "empty";
  elements.error.hidden = state !== "error";
  elements.list.hidden = state !== "success";
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
    line.textContent = `${item.product_name} × ${item.quantity} (${item.total_price.toLocaleString("vi-VN")} ₫)`;
    items.append(line);
  });
  card.append(items);
  transitions[order.status].forEach((transition) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = transition.label;
    button.addEventListener("click", () => updateStatus(order.id, transition.status));
    card.append(button);
  });
  return card;
}

async function loadOrders() {
  setState("loading", "Loading orders…");
  const params = new URLSearchParams({ page: "1", limit: "20" });
  if (elements.status.value) params.set("status", elements.status.value);
  if (elements.from.value) params.set("from", elements.from.value);
  if (elements.to.value) params.set("to", elements.to.value);
  try {
    const token = localStorage.getItem("access_token");
    const response = await fetch(`/api/v1/seller/orders?${params}`, {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load orders.");
    if (!Array.isArray(payload.data)) throw new Error("Invalid seller order response.");
    elements.list.replaceChildren(...payload.data.map(createOrderCard));
    setState(payload.data.length ? "success" : "empty", `${payload.data.length} seller orders found.`);
  } catch (error) {
    setState("error", error.message);
  }
}

async function updateStatus(id, status) {
  if (status === "CANCELLED" && !window.confirm("Cancel this order and restore stock?")) return;
  try {
    const token = localStorage.getItem("access_token");
    const response = await fetch(`/api/v1/seller/orders/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ status }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to update order.");
    await loadOrders();
  } catch (error) {
    setState("error", error.message);
  }
}

elements.form.addEventListener("submit", (event) => { event.preventDefault(); loadOrders(); });
elements.retry.addEventListener("click", loadOrders);
elements.logout.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  window.location.href = "/login?return_to=/seller/orders";
});
loadOrders();
