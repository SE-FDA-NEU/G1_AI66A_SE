"use strict";
const retry = document.getElementById("retry");
const money = n => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(n);
const paymentMethods = {COD:"Cash on delivery", VIETQR:"VietQR", WALLET:"Wallet", CARD:"Card"};
const paymentStatuses = {UNPAID:"Awaiting payment", PAID:"Paid", REFUND_PENDING:"Refund in progress", REFUNDED:"Refunded", FAILED:"Payment failed"};
function paymentSummary(order) {
  if (!order.payment_method) return {method:"Payment method: Not recorded", status:"Payment not recorded (order placed before payment tracking)."};
  const method = paymentMethods[order.payment_method] || order.payment_method;
  const status = paymentStatuses[order.payment_status] || "Payment status not recorded";
  return {method:`Payment method: ${method}`, status:order.payment_status === "UNPAID" && order.payment_method !== "COD" ? `${status} (demo result not recorded)` : status};
}
async function load() {
  retry.hidden = true; document.getElementById("error").textContent = "";
  const token = localStorage.getItem("access_token");
  if (!token) { location.replace(`/login?return_to=${encodeURIComponent(location.pathname)}`); return; }
  try {
    const id = location.pathname.split("/").pop();
    const response = await fetch(`/api/v1/orders/${encodeURIComponent(id)}`, {headers:{Authorization:`Bearer ${token}`},signal:AbortSignal.timeout(10000)});
    const payload = await response.json();
    if (response.status === 401) { localStorage.removeItem("access_token"); location.reload(); return; }
    if (response.status === 404) throw new Error("We could not find this order in your account. Check the order link, or continue shopping.");
    if (!response.ok) throw new Error(payload.error?.message || "Unable to load confirmation.");
    const order = payload.data;
    document.getElementById("status").textContent = "Order placed. Payment has not been marked successful unless the receipt records a paid result.";
    const payment = paymentSummary(order);
    document.getElementById("payment-method").textContent = payment.method;
    document.getElementById("payment-status").textContent = payment.status;
    const receipt = document.getElementById("receipt"); receipt.replaceChildren();
    const rows = [`Order #${order.id} \u00b7 ${order.status}`, `Total: ${money(order.total_amount)}`, `${order.recipient_name} \u00b7 ${order.delivery_address} \u00b7 ${order.phone_number}`,
      ...order.items.map(i => `${i.product_name} (${i.product_code}) \u00d7 ${i.quantity} \u00b7 ${money(i.unit_price)} each`),
      // Stored amounts from checkout; the page never re-prices an order.
      ...(order.sub_orders || []).filter(so => so.pricing_policy_version && so.pricing_policy_version !== "LEGACY").map(so =>
        `Seller order #${so.id}: items ${money(so.subtotal)}` +
        (so.shop_discount ? `, shop voucher \u2212${money(so.shop_discount)}` : "") +
        (so.platform_discount ? `, platform voucher \u2212${money(so.platform_discount)}` : "") +
        `, shipping ${money(so.shipping_fee)}` +
        (so.shipping_discount ? `, shipping discount \u2212${money(so.shipping_discount)}` : "") +
        ` \u00b7 ${money(so.total_amount)}`),
      ...(order.vouchers || []).map(v => `Voucher ${v.code} (${v.slot.toLowerCase()}): \u2212${money(v.discount_amount)}`)];
    for (const text of rows) { const p = document.createElement("p"); p.textContent = text; receipt.append(p); }
    const trackerAction = document.getElementById("tracker-action");
    const trackOrderButton = document.getElementById("track-order-button");
    if (trackerAction && trackOrderButton) {
      trackOrderButton.href = `/order/${order.id}`;
      trackOrderButton.textContent = `📦 Track Order (#${order.id})`;
      trackerAction.hidden = false;
    }
  } catch(e) { document.getElementById("status").textContent = "Confirmation unavailable."; document.getElementById("error").textContent = e.message; retry.hidden = false; }
}
retry.addEventListener("click", load); load();
