"use strict";
const form = document.getElementById("checkout-form");
const statusText = document.getElementById("status");
const errorText = document.getElementById("error");
const retry = document.getElementById("retry");
const money = n => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(n);
let storageKey;
let pending;
let busy = false;
function message(text) { errorText.textContent = text; }
async function request(url, options = {}) {
  const token = localStorage.getItem("access_token");
  if (!token) { login(); throw new Error("Please log in."); }
  const response = await fetch(url, {...options, headers: {
    "Content-Type":"application/json", Authorization:`Bearer ${token}`, ...options.headers,
  }, signal:AbortSignal.timeout(10000)});
  const payload = await response.json();
  if (response.status === 401) login();
  if (!response.ok) { const e = new Error(payload.error?.message || "Request failed."); e.status = response.status; throw e; }
  return payload;
}
function login() { location.replace("/login?return_to=%2Fcheckout"); }
function lock(value) { busy = value; for (const field of form.elements) field.disabled = value; }
async function init() {
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
    const summary = document.getElementById("summary"); summary.replaceChildren();
    for (const item of cart.items) {
      const p = document.createElement("p");
      p.textContent = `${item.name} ? ${item.quantity}: ${money(item.line_total)}`; summary.append(p);
    }
    const total = document.createElement("strong"); total.textContent = `Total: ${money(cart.cart_total)}`; summary.append(total);
    const valid = cart.items.length && cart.items.every(i => i.availability === "available");
    form.hidden = !valid;
    statusText.textContent = !cart.items.length ? "Your cart is empty." : valid ? "Enter delivery information." : "Update unavailable items in your cart first.";
  } catch (e) { message(e.message); retry.hidden = false; }
}
let sending = false;
async function submit() {
  if (sending || !pending) return;
  sending = true;
  retry.hidden = true; message(""); lock(true); statusText.textContent = "Placing your order...";
  try {
    const {data} = await request("/api/v1/orders", {method:"POST", headers:{"Idempotency-Key":pending.key}, body:JSON.stringify(pending.body)});
    sessionStorage.removeItem(storageKey);
    location.assign(`/checkout/confirmation/${data.id}`);
  } catch (e) {
    message(e.message);
    if (e.status && e.status < 500 && e.status !== 401) {
      sessionStorage.removeItem(storageKey); pending = null; lock(false);
    } else { retry.hidden = false; }
    statusText.textContent = "Order was not confirmed. Your delivery information is preserved.";
  } finally { sending = false; }
}
form.addEventListener("submit", event => {
  event.preventDefault(); if (busy || !form.reportValidity()) return;
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
retry.addEventListener("click", () => pending ? submit() : init());
init();
