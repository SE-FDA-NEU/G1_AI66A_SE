"use strict";
const form = document.getElementById("checkout-form");
const PHONE_ERROR = "Phone number must contain 7 to 15 digits. Use only +, spaces, (), or - as separators.";
function normalizePhoneNumber(value) { return value.trim().replace(/ {2,}/g, " "); }
function phoneValidationError(value) {
  const normalized = normalizePhoneNumber(value);
  const digits = normalized.match(/[0-9]/g) || [];
  return /^[+0-9 ()-]+$/.test(normalized) && digits.length >= 7 && digits.length <= 15 ? "" : PHONE_ERROR;
}
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
    document.getElementById("address-book").hidden = true;
    document.getElementById("address-list").replaceChildren();
    for (const field of document.getElementById("address-form").elements) if ("value" in field) field.value = "";
    for (const field of form.elements) if ("value" in field) field.value = "";
    document.getElementById("summary").replaceChildren();
    resetVouchers();
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
  requireAccountContext();
  const payload = response.status === 204 ? null : await response.json();
  requireAccountContext();
  if (response.status === 401) login();
  if (!response.ok) { const e = new Error(payload.error?.message || "Request failed."); e.status = response.status; e.code = payload.error?.code; e.fields = payload.error?.fields; throw e; }
  return payload;
}
function login() { location.replace("/login?return_to=%2Fcheckout"); }
function lock(value) {
  busy = value;
  for (const field of form.elements) field.disabled = value;
  for (const control of document.getElementById("address-book").querySelectorAll("input,select,button")) control.disabled = value;
  for (const control of voucherSection.querySelectorAll("input,button")) control.disabled = value;
  syncDeliveryMode();
  updateConfirm();
}
function renderCartSummary(cart) {
  if (!cart || !Array.isArray(cart.items) || !Number.isSafeInteger(cart.selected_total) ||
      cart.selected_total < 0 || !cart.items.every(item => item && typeof item.is_selected === "boolean" &&
        Number.isSafeInteger(item.line_total) && item.line_total >= 0 &&
        ["available", "insufficient_stock", "unavailable"].includes(item.availability))) {
    throw new Error("Cart response does not include valid selection details.");
  }
  const summary = document.getElementById("summary");
  summary.replaceChildren();
  const selected = cart.items.filter(item => item.is_selected === true);
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
  const calculatedTotal = selected.reduce((sum, item) => sum + item.line_total, 0);
  if (calculatedTotal !== cart.selected_total) {
    throw new Error("Cart selected total does not match its selected items.");
  }
  // Discounts and shipping come only from the server quote below.
  total.textContent = `Items subtotal: ${money(calculatedTotal)}`;
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
      for (const [name,value] of Object.entries(pending.body)) if (form.elements[name]) form.elements[name].value = value;
      form.hidden = false; lock(true); retry.hidden = false;
      statusText.textContent = "A checkout is pending. Retry to retrieve or finish that order.";
      return;
    }
    form.hidden = true;
    try {
      const {data:cart} = await request("/api/v1/cart");
      const blocked = renderCartSummary(cart);
      form.hidden = Boolean(blocked);
      statusText.textContent = blocked || "Enter delivery information.";
      if (!blocked) renderShopVouchers(cart);
    } finally {
      if (!contextChanged) await loadAddresses();
    }
    if (!form.hidden && !contextChanged) await refreshQuote();
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
      showFields(form, "checkout", e.fields);
      if (e.code === "ERR_QUOTE_STALE" || e.code?.startsWith("ERR_VOUCHER_")) {
        await refreshQuote();
        showVoucherErrors(e.fields);
        message(e.code === "ERR_QUOTE_STALE" ?
          "Prices or vouchers changed. Review the updated total and confirm again." :
          `${e.message} Remove or replace that voucher, then confirm again.`);
      }
      try {
        if (e.code === "ERR_ADDRESS_CHANGED" || e.code === "ERR_ADDRESS_NOT_FOUND") {
          reviewRequired = true;
          await loadAddresses(false);
          message("Address changed or removed. Review the address book and select a delivery option again.");
        }
        if (document.getElementById("address-book").hidden) await loadAddresses(false);
      } catch (refreshError) {
        if (refreshError.accountChanged) return;
        message(refreshError.message + " Reload addresses to review your delivery information.");
        retry.hidden = false;
      }
    } else { retry.hidden = false; }
    statusText.textContent = "Order was not confirmed. Your delivery information is preserved.";
  } finally { sending = false; }
}
form.addEventListener("submit", event => {
  event.preventDefault(); if (authenticationChanged() || busy || !form.reportValidity()) return;
  if (addressBusy) return;
  if (reviewRequired) { message("Review the address book and select a delivery option again."); return; }
  if (!quoteReady()) { message("Wait for the updated total, or remove the rejected voucher, before confirming."); return; }
  clearFields(form, "checkout");
  let body;
  const chosen = addresses.find(row => String(row.id) === addressChoice.value);
  if (addressChoice.value && !chosen) { message("Reload your address book and select an address."); return; }
  if (chosen) body = {address_id:chosen.id, address_version:chosen.version};
  else {
    body = Object.fromEntries(["recipient_name", "delivery_address", "phone_number"].map(name => [name,name === "phone_number" ? normalizePhoneNumber(form.elements[name].value) : form.elements[name].value.trim()]));
    const errors = {};
    for (const name of ["recipient_name", "delivery_address"]) if (!body[name]) errors[name] = ["Enter this required field."];
    const phoneError = phoneValidationError(body.phone_number);
    if (phoneError) errors.phone_number = [phoneError];
    if (Object.keys(errors).length) { showFields(form, "checkout", errors); message("Please correct the highlighted fields."); return; }
  }
  // The exact quote the buyer reviewed; the server rejects it if anything changed since.
  body = {...body, ...voucherBody(), quote_revision:quote.quote_revision};
  pending = {key:crypto.randomUUID(),body};
  sessionStorage.setItem(storageKey, JSON.stringify(pending)); submit();
});
retry.addEventListener("click", () => {
  if (contextChanged) { location.reload(); return; }
  return pending ? submit() : init();
});

const addressBook = document.getElementById("address-book");
const addressForm = document.getElementById("address-form");
const addressChoice = document.getElementById("address-choice");
const addressStatus = document.getElementById("address-status");
const addressError = document.getElementById("address-error");
const addressFields = ["recipient_name", "phone_number", "province", "district", "ward", "detailed_address"];
let addresses = [], editingAddress = null, deletingAddress = null, addressBusy = false, reviewRequired = false;
function clearFields(target, prefix) {
  for (const field of target.elements) {
    if (!field.name) continue;
    field.removeAttribute("aria-invalid");
    const error = document.getElementById(`${prefix}-${field.name}-error`);
    if (error) error.textContent = "";
  }
}
function showFields(target, prefix, fields = {}) {
  clearFields(target, prefix);
  let first;
  for (const [name, messages] of Object.entries(fields || {})) {
    const field = target.elements[name];
    if (!field) continue;
    field.setAttribute("aria-invalid", "true");
    document.getElementById(`${prefix}-${name}-error`).textContent = messages.join(" ");
    first ||= field;
  }
  if (first) first.focus();
  else if (fields && Object.keys(fields).length) (prefix === "address" ? addressError : errorText).focus();
}
function syncDeliveryMode() {
  const manual = !addressChoice?.value && !pending?.body?.address_id;
  document.getElementById("manual-delivery").hidden = !manual;
  for (const name of ["recipient_name", "delivery_address", "phone_number"]) {
    form.elements[name].disabled = busy || !manual;
    form.elements[name].required = manual;
  }
}
addressChoice.addEventListener("change", () => {
  if (authenticationChanged() || busy || addressBusy) return;
  reviewRequired = false;
  message("");
  syncDeliveryMode();
});
function renderAddresses(preselect) {
  const old = addressChoice.value;
  const list = document.getElementById("address-list");
  list.replaceChildren(); addressChoice.replaceChildren();
  const manual = document.createElement("option");
  manual.value = ""; manual.textContent = "Enter delivery information manually"; addressChoice.append(manual);
  for (const row of addresses) {
    const text = `${row.recipient_name} · ${row.phone_number} · ${row.detailed_address}, ${row.ward}, ${row.district}, ${row.province}${row.is_default ? " · Default" : ""}`;
    const option = document.createElement("option"); option.value = String(row.id); option.textContent = text; addressChoice.append(option);
    const card = document.createElement("article");
    card.setAttribute("aria-label", `Delivery address for ${row.recipient_name} at ${row.detailed_address}`);
    const description = document.createElement("p"); description.textContent = text; card.append(description);
    for (const [label, action] of [["Edit", () => openAddress(row)], ["Delete", () => {
      deletingAddress = row;
      document.getElementById("delete-address-summary").textContent = text;
      document.getElementById("address-delete").hidden = false;
      document.getElementById("cancel-delete").focus();
    }], ...(!row.is_default ? [["Set default", () => runAddress(async () => {
      await request(`/api/v1/addresses/${row.id}/default`, {method:"PATCH", body:JSON.stringify({version:row.version})});
      await loadAddresses(false);
    }, "Default address updated.", "address-choice")]] : [])]) {
      const button = document.createElement("button"); button.type = "button"; button.textContent = label;
      button.id = `address-${row.id}-${label.toLowerCase().replaceAll(" ", "-")}`;
      button.setAttribute("aria-label", `${label} address for ${row.recipient_name} at ${row.detailed_address}`);
      button.addEventListener("click", () => {if (!authenticationChanged() && !busy && !addressBusy) action();}); card.append(button);
    }
    list.append(card);
  }
  const selected = preselect ? (addresses.find(row => row.is_default) || [...addresses].sort((a,b)=>a.id-b.id)[0]) : addresses.find(row => String(row.id) === old);
  addressChoice.value = selected ? String(selected.id) : "";
  addressStatus.textContent = addresses.length ? "Select a saved address or enter delivery information manually." : "No saved addresses. Add an address or enter delivery information manually.";
  syncDeliveryMode();
}
function clearDeleteConfirmation() {
  deletingAddress = null;
  document.getElementById("address-delete").hidden = true;
  document.getElementById("delete-address-summary").textContent = "";
}
async function loadAddresses(preselect = true) {
  // A refreshed list requires confirmation of its current address details.
  clearDeleteConfirmation();
  addressBook.hidden = false;
  lock(true);
  addressStatus.textContent = "Loading addresses...";
  try {
    const {data} = await request("/api/v1/addresses");
    addresses = data; renderAddresses(preselect);
  } catch (e) {
    if (e.accountChanged) return;
    addressStatus.textContent = "Could not load addresses. Reload addresses to try again, or enter delivery information manually.";
    throw e;
  } finally {
    if (!contextChanged) lock(Boolean(pending) || addressBusy);
  }
}
function openAddress(row = null) {
  clearDeleteConfirmation();
  editingAddress = row;
  addressForm.hidden = false;
  addressError.textContent = ""; clearFields(addressForm, "address");
  document.getElementById("address-form-heading").textContent = row ? "Edit address" : "Add address";
  for (const name of addressFields) addressForm.elements[name].value = row?.[name] || "";
  addressForm.elements.is_default.checked = row?.is_default || false;
  addressForm.elements.recipient_name.focus();
}
function focusAddressControl(id) {
  const target = document.getElementById(id) || addressChoice;
  if (!target.disabled) target.focus();
}
async function runAddress(action, successMessage = "", focusId = "") {
  if (authenticationChanged() || busy || addressBusy) return;
  addressBusy = true; addressError.textContent = "";
  if (successMessage) addressStatus.textContent = "Saving address changes...";
  let succeeded = false;
  for (const control of addressBook.querySelectorAll("input,select,button")) control.disabled = true;
  try { await action(); succeeded = true; }
  catch (e) {
    if (e.accountChanged) return;
    lock(false);
    addressError.textContent = e.message + (e.code === "ERR_VALIDATION" ?
      " Your input is preserved. Correct the highlighted fields and save again." :
      " Your input is preserved. Reload addresses to review changes before retrying.");
    addressStatus.textContent = addressError.textContent;
    if (addressForm.hidden) addressStatus.focus();
    else showFields(addressForm, "address", e.fields);
  } finally {
    addressBusy = false;
    if (!contextChanged) lock(Boolean(pending));
  }
  if (succeeded && !contextChanged) {
    if (successMessage) addressStatus.textContent = successMessage;
    if (focusId) focusAddressControl(focusId);
  }
}
document.getElementById("add-address").addEventListener("click", () => {
  if (!authenticationChanged() && !busy && !addressBusy) openAddress();
});
document.getElementById("cancel-address").addEventListener("click", () => {
  addressForm.hidden = true;
  focusAddressControl(editingAddress ? `address-${editingAddress.id}-edit` : "add-address");
});
document.getElementById("reload-addresses").addEventListener("click", () => runAddress(() => loadAddresses(false)));
addressForm.addEventListener("submit", event => {
  event.preventDefault();
  if (!addressForm.reportValidity()) return;
  clearFields(addressForm, "address");
  const phone_number = normalizePhoneNumber(addressForm.elements.phone_number.value);
  const phoneError = phoneValidationError(phone_number);
  if (phoneError) {
    showFields(addressForm, "address", {phone_number: [phoneError]});
    addressStatus.textContent = "Please correct the highlighted fields.";
    return;
  }
  const focusId = editingAddress ? `address-${editingAddress.id}-edit` : "address-choice";
  const successMessage = editingAddress ? "Address updated." : "Address added.";
  return runAddress(async () => {
    const body = Object.fromEntries(addressFields.map(name => [name, name === "phone_number" ? phone_number : addressForm.elements[name].value.trim()]));
    body.is_default = addressForm.elements.is_default.checked;
    if (editingAddress) body.version = editingAddress.version;
    await request(editingAddress ? `/api/v1/addresses/${editingAddress.id}` : "/api/v1/addresses", {method:editingAddress ? "PUT" : "POST", body:JSON.stringify(body)});
    addressForm.hidden = true;
    await loadAddresses(false);
  }, successMessage, focusId);
});
document.getElementById("cancel-delete").addEventListener("click", () => {
  const focusId = deletingAddress ? `address-${deletingAddress.id}-delete` : "add-address";
  clearDeleteConfirmation();
  focusAddressControl(focusId);
});
document.getElementById("confirm-delete").addEventListener("click", () => {
  // Ignore a queued/stale click after editing, cancellation or refresh invalidated it.
  if (!deletingAddress) return;
  return runAddress(async () => {
    await request(`/api/v1/addresses/${deletingAddress.id}`, {method:"DELETE"});
    clearDeleteConfirmation();
    await loadAddresses(false);
  }, "Address deleted.", "address-choice");
});
const voucherSection = document.getElementById("vouchers");
const quoteStatus = document.getElementById("quote-status");
const refreshQuoteButton = document.getElementById("refresh-quote");
const breakdown = document.getElementById("price-breakdown");
const shopNames = new Map();
let selection = {shop:{}, platform:"", shipping:""};
let quote = null, quoteSeq = 0;
function voucherInputId(field) {
  return field.startsWith("shop_vouchers.") ? `voucher-shop-${field.split(".")[1]}` :
    `voucher-${field.replace("_voucher", "")}`;
}
function voucherBody() {
  const body = {};
  const shops = Object.entries(selection.shop).map(([id, code]) => ({seller_id:Number(id), code}));
  if (shops.length) body.shop_vouchers = shops;
  if (selection.platform) body.platform_voucher = selection.platform;
  if (selection.shipping) body.shipping_voucher = selection.shipping;
  return body;
}
function quoteVouchers(data) {
  return [
    ...data.seller_orders.map(row => [`shop_vouchers.${row.seller_id}`, row.shop_voucher]),
    ["platform_voucher", data.platform_voucher], ["shipping_voucher", data.shipping_voucher],
  ].filter(([, result]) => result);
}
function quoteReady() {
  return Boolean(quote) && quoteVouchers(quote).every(([, result]) => result.status === "APPLIED");
}
function updateConfirm() {
  const confirm = document.getElementById("confirm");
  if (confirm) confirm.disabled = busy || !quoteReady();
}
function resetVouchers() {
  quoteSeq++; quote = null;
  selection = {shop:{}, platform:"", shipping:""};
  voucherSection.hidden = true;
  document.getElementById("shop-vouchers").replaceChildren();
  breakdown.replaceChildren();
  quoteStatus.textContent = "";
}
function voucherSlot(field, labelText) {
  const id = voucherInputId(field);
  const slot = document.createElement("div");
  slot.className = "voucher-slot";
  const label = document.createElement("label");
  label.htmlFor = id; label.textContent = labelText;
  const input = document.createElement("input");
  input.id = id; input.type = "text"; input.maxLength = 32; input.autocomplete = "off";
  input.setAttribute("aria-describedby", `${id}-error`);
  label.append(input);
  const error = document.createElement("span");
  error.className = "field-error"; error.id = `${id}-error`;
  slot.append(label);
  for (const [text, action] of [["Apply", "apply"], ["Remove", "remove"]]) {
    const button = document.createElement("button");
    button.type = "button"; button.id = `${id}-${action}`; button.textContent = text;
    button.setAttribute("aria-label", `${text} ${labelText.toLowerCase()}`);
    button.addEventListener("click", () => changeVoucher(field, action === "apply" ? input.value : ""));
    slot.append(button);
  }
  slot.append(error);
  return slot;
}
function renderShopVouchers(cart) {
  shopNames.clear();
  for (const item of cart.items) if (item.is_selected) shopNames.set(item.seller_id, item.seller_name);
  const rows = [...shopNames].map(([id, name]) => voucherSlot(`shop_vouchers.${id}`, `Voucher for ${name}`));
  document.getElementById("shop-vouchers").replaceChildren(...rows);
  voucherSection.hidden = false;
}
function changeVoucher(field, rawCode) {
  if (authenticationChanged() || busy || pending) return;
  const code = rawCode.trim();
  if (field.startsWith("shop_vouchers.")) {
    const id = field.split(".")[1];
    if (code) selection.shop[id] = code; else delete selection.shop[id];
  } else selection[field.replace("_voucher", "")] = code;
  if (!code) document.getElementById(voucherInputId(field)).value = "";
  message("");
  return refreshQuote();
}
function showVoucherErrors(fields = {}) {
  for (const [field, messages] of Object.entries(fields || {})) {
    if (!field.endsWith("_voucher") && !field.startsWith("shop_vouchers.")) continue;
    const id = voucherInputId(field);
    document.getElementById(`${id}-error`).textContent = [].concat(messages).join(" ");
    document.getElementById(id).setAttribute("aria-invalid", "true");
  }
}
function breakdownLine(text) {
  const line = document.createElement("p");
  line.textContent = text;
  return line;
}
function renderQuote(data) {
  for (const field of ["platform_voucher", "shipping_voucher", ...[...shopNames.keys()].map(id => `shop_vouchers.${id}`)]) {
    const id = voucherInputId(field);
    document.getElementById(`${id}-error`).textContent = "";
    document.getElementById(id).removeAttribute("aria-invalid");
  }
  const rejected = {};
  for (const [field, result] of quoteVouchers(data)) {
    if (result.status === "REJECTED") rejected[field] = [result.error.message];
  }
  showVoucherErrors(rejected);
  const lines = [];
  for (const row of data.seller_orders) {
    const shop = shopNames.get(row.seller_id) || `Shop ${row.seller_id}`;
    lines.push(breakdownLine(`${shop}: items ${money(row.subtotal)}` +
      (row.shop_discount ? `, shop voucher −${money(row.shop_discount)}` : "") +
      (row.platform_discount ? `, platform voucher −${money(row.platform_discount)}` : "") +
      `, shipping ${money(row.shipping_fee)}` +
      (row.shipping_discount ? `, shipping discount −${money(row.shipping_discount)}` : "") +
      `. Shop total ${money(row.total_amount)}.`));
  }
  lines.push(breakdownLine(`Items subtotal: ${money(data.subtotal)}`));
  if (data.shop_discount) lines.push(breakdownLine(`Shop discounts: −${money(data.shop_discount)}`));
  if (data.platform_discount) lines.push(breakdownLine(`Platform discount: −${money(data.platform_discount)}`));
  lines.push(breakdownLine(`Shipping fee: ${money(data.shipping_fee)}`));
  if (data.shipping_discount) lines.push(breakdownLine(`Shipping discount: −${money(data.shipping_discount)}`));
  const total = document.createElement("strong");
  total.textContent = `Total to pay: ${money(data.grand_total)}`;
  lines.push(total);
  breakdown.replaceChildren(...lines);
  quoteStatus.textContent = Object.keys(rejected).length ?
    "A voucher cannot be used. Remove or replace it to continue." : "Total updated.";
}
async function refreshQuote() {
  const seq = ++quoteSeq;
  quote = null; updateConfirm();
  refreshQuoteButton.hidden = true;
  quoteStatus.textContent = "Updating your total...";
  try {
    const {data} = await request("/api/v1/orders/quote", {method:"POST", body:JSON.stringify(voucherBody())});
    // A slower, older response must not replace the total for a newer selection.
    if (seq !== quoteSeq) return;
    quote = data;
    renderQuote(data);
  } catch (e) {
    if (e.accountChanged || seq !== quoteSeq) return;
    breakdown.replaceChildren();
    quoteStatus.textContent = `Could not calculate your total. ${e.message}`;
    refreshQuoteButton.hidden = false;
  } finally {
    if (seq === quoteSeq) updateConfirm();
  }
}
for (const slot of ["platform", "shipping"]) {
  const input = document.getElementById(`voucher-${slot}`);
  document.getElementById(`voucher-${slot}-apply`).addEventListener("click", () => changeVoucher(`${slot}_voucher`, input.value));
  document.getElementById(`voucher-${slot}-remove`).addEventListener("click", () => changeVoucher(`${slot}_voucher`, ""));
}
refreshQuoteButton.addEventListener("click", () => { if (!authenticationChanged() && !busy) refreshQuote(); });
globalThis.addEventListener?.("storage", event => {
  if (event.key === "access_token") authenticationChanged();
});
init();
