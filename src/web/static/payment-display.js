"use strict";

globalThis.PaymentDisplay = Object.freeze({
  methodNames: Object.freeze({COD: "Cash on delivery", VIETQR: "VietQR", WALLET: "Wallet", CARD: "Card"}),
  statusNames: Object.freeze({UNPAID: "Awaiting payment", PAID: "Paid", REFUND_PENDING: "Refund in progress", REFUNDED: "Refunded", FAILED: "Payment failed"}),
  summary(order) {
    if (!order.payment_method) {
      return {method: "Payment method: Not recorded", status: "Payment not recorded (order placed before payment tracking)."};
    }
    const method = this.methodNames[order.payment_method] || order.payment_method;
    const status = this.statusNames[order.payment_status] || "Payment status not recorded";
    const demoNote = order.payment_status === "UNPAID" && order.payment_method !== "COD"
      ? " (demo result not recorded)" : "";
    return {method: `Payment method: ${method}`, status: `${status}${demoNote}`};
  },
  renderBadges(order, methodElement, statusElement) {
    if (methodElement) {
      methodElement.hidden = false;
      methodElement.textContent = order.payment_method
        ? `Payment: ${this.methodNames[order.payment_method] || order.payment_method}`
        : "Payment method: Not recorded";
      methodElement.className = "badge";
    }
    if (statusElement) {
      statusElement.hidden = false;
      statusElement.textContent = order.payment_method
        ? `Payment status: ${this.statusNames[order.payment_status] || "Not recorded"}`
        : "Payment not recorded";
      statusElement.className = "badge " + (order.payment_status === "REFUNDED"
        ? "badge-purple" : order.payment_status === "PAID" ? "badge-success" : "");
    }
  },
});
