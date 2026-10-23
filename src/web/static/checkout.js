"use strict";
const form = document.getElementById("checkout-form");
const statusText = document.getElementById("status");
const errorText = document.getElementById("error");
const retry = document.getElementById("retry");
const money = n => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(n);
let storageKey;
let pending;
let busy = false;
let contextToken;
let contextChanged = false;
function authenticationChanged() {
  if (contextChanged || localStorage.getItem("access_token") !== contextToken) {
    contextChanged = true;
    lock(true);
    form.hidden = true;
    for (const field of form.elements) if ("value" in field) field.value = "";
    document.getElementById("summary").replaceChildren();
    statusText.textContent = "Your account has changed. Reload checkout before confirming.";
    message("");
    retry.textContent = "Reload checkout";
    retry.hidden = false;
    return true;
  }
  return false;
}
function requireAccountContext() {
  if (authenticationChanged()) {
    const error = new Error("Account context changed.");
    error.accountChanged = true;
    throw error;
  }
}
function message(text) { errorText.textContent = text; }
async function request(url, options = {}) {
  requireAccountContext();
  const token = contextToken;
  if (!token) { login(); throw new Error("Please log in."); }
  const response = await fetch(url, {...options, headers: {
    "Content-Type":"application/json", Authorization:`Bearer ${token}`, ...options.headers,
  }, signal:AbortSignal.timeout(10000)});
  const payload = await response.json();
  requireAccountContext();
  if (response.status === 401) login();
  if (!response.ok) { const e = new Error(payload.error?.message || "Request failed."); e.status = response.status; throw e; }
  return payload;
}
function login() { location.replace("/login?return_to=%2Fcheckout"); }
function lock(value) { busy = value; for (const field of form.elements) field.disabled = value; }
function renderCartSummary(cart) {
  const summary = document.getElementById("summary");
  summary.replaceChildren();
  const selected = cart.items.filter(item => item.is_selected !== false);
  for (const item of selected) {
    const line = document.createElement("p");
    line.textContent = `${item.name} × ${item.quantity}: ${money(item.line_total)}`;
    summary.append(line);
    if (item.price_changed) {
      const warning = document.createElement("p");
      warning.textContent = `Price changed: ${money(item.price_at_add)} when added → ${money(item.unit_price)} now.`;
      summary.append(warning);
    }
  }
  const total = document.createElement("strong");
  total.textContent = `Total: ${money(cart.selected_total ?? cart.cart_total)}`;
  summary.append(total);
  if (!cart.items.length) return "Your cart is empty.";
  if (!selected.length) return "Select at least one item in your cart.";
  if (selected.some(item => item.availability !== "available")) {
    return "Update unavailable items in your cart first.";
  }
  return "";
}
async function init() {
  if (contextChanged) { location.reload(); return; }
  contextToken = localStorage.getItem("access_token");
  retry.hidden = true;
  try {
    const user = await request("/api/v1/auth/me");
    // Scope saved delivery details and request keys to the authenticated account.
    storageKey = `checkout:${user.id}`;
    try { pending = JSON.parse(sessionStorage.getItem(storageKey)); } catch { pending = null; }
    if (pending) {
      for (const [name,value] of Object.entries(pending.body)) form.elements[name].value = value;
      form.hidden = false; lock(true); retry.hidden = false;
      statusText.textContent = "A checkout is pending. Retry to retrieve or finish that order.";
      return;
    }
    const {data:cart} = await request("/api/v1/cart");
    const blocked = renderCartSummary(cart);
    form.hidden = Boolean(blocked);
    statusText.textContent = blocked || "Enter delivery information.";
  } catch (e) { if (e.accountChanged) return; message(e.message); retry.hidden = false; }
}
let sending = false;
async function submit() {
  if (sending || !pending || authenticationChanged()) return;
  sending = true;
  retry.hidden = true; message(""); lock(true); statusText.textContent = "Placing your order...";
  try {
    const {data} = await request("/api/v1/orders", {method:"POST", headers:{"Idempotency-Key":pending.key}, body:JSON.stringify(pending.body)});
    sessionStorage.removeItem(storageKey);
    location.assign(`/checkout/confirmation/${data.id}`);
  } catch (e) {
    if (e.accountChanged) return;
    message(e.message);
    if (e.status && e.status < 500 && e.status !== 401) {
      sessionStorage.removeItem(storageKey); pending = null; lock(false);
    } else { retry.hidden = false; }
    statusText.textContent = "Order was not confirmed. Your delivery information is preserved.";
  } finally { sending = false; }
}
form.addEventListener("submit", event => {
  event.preventDefault(); if (authenticationChanged() || busy || !form.reportValidity()) return;
  const body = Object.fromEntries(new FormData(form));
  for (const name in body) body[name] = body[name].trim();
  for (const name of ["recipient_name", "delivery_address"]) {
    if (!body[name]) { message(`Please enter ${name.replaceAll("_", " ")}.`); form.elements[name].focus(); return; }
  }
  if (!/^[+0-9 ()-]+$/.test(body.phone_number) || (body.phone_number.match(/\d/g) || []).length < 7 || (body.phone_number.match(/\d/g) || []).length > 15) {
    message("Phone number must contain 7 to 15 digits."); return;
  }
  pending = {key:crypto.randomUUID(),body};
  sessionStorage.setItem(storageKey, JSON.stringify(pending)); submit();
});
retry.addEventListener("click", () => {
  if (contextChanged) { location.reload(); return; }
  return pending ? submit() : init();
});
init();
