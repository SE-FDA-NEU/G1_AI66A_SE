"use strict";
const retry = document.getElementById("retry");
const money = n => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(n);
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
    document.getElementById("status").textContent = "Order placed successfully.";
    const receipt = document.getElementById("receipt"); receipt.replaceChildren();
    const rows = [`Order #${order.id} \u00b7 ${order.status}`, `Total: ${money(order.total_amount)}`, `${order.recipient_name} \u00b7 ${order.delivery_address} \u00b7 ${order.phone_number}`,
      ...order.items.map(i => `${i.product_name} (${i.product_code}) \u00d7 ${i.quantity} \u00b7 ${money(i.unit_price)} each`)];
    for (const text of rows) { const p = document.createElement("p"); p.textContent = text; receipt.append(p); }
  } catch(e) { document.getElementById("status").textContent = "Confirmation unavailable."; document.getElementById("error").textContent = e.message; retry.hidden = false; }
}
retry.addEventListener("click", load); load();
