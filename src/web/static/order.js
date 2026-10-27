/**
 * Order Tracking & Return/Refund Page Logic
 */

(function () {
  "use strict";

  const token = localStorage.getItem("token");
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const orderId = pathParts[pathParts.length - 1];

  const statusEl = document.getElementById("global-status");
  const messageEl = document.getElementById("global-message");
  const contentEl = document.getElementById("order-content");

  const orderIdLabel = document.getElementById("order-id-label");
  const orderDateLabel = document.getElementById("order-date-label");
  const badgeOrderStatus = document.getElementById("badge-order-status");
  const badgePaymentStatus = document.getElementById("badge-payment-status");
  const badgeEscrowStatus = document.getElementById("badge-escrow-status");

  const recipientNameEl = document.getElementById("info-recipient-name");
  const recipientPhoneEl = document.getElementById("info-recipient-phone");
  const deliveryAddressEl = document.getElementById("info-delivery-address");
  const itemsTableBody = document.getElementById("items-table-body");
  const orderTotalEl = document.getElementById("order-total-amount");

  const escrowNoticeEl = document.getElementById("escrow-paused-notice");
  const returnStatusCard = document.getElementById("return-status-card");
  const returnReqIdEl = document.getElementById("return-req-id");
  const returnReqDateEl = document.getElementById("return-req-date");
  const badgeReturnStatus = document.getElementById("badge-return-status");
  const returnReqReasonEl = document.getElementById("return-req-reason");
  const returnReqEvidenceEl = document.getElementById("return-req-evidence");
  const returnResolutionDetails = document.getElementById("return-resolution-details");
  const returnDecisionNotesEl = document.getElementById("return-req-decision-notes");
  const returnRestockStatusEl = document.getElementById("return-req-restock-status");

  const reviewerPanel = document.getElementById("reviewer-decision-panel");
  const btnApprove = document.getElementById("btn-approve-return");
  const btnReject = document.getElementById("btn-reject-return");
  const decisionNotesInput = document.getElementById("decision-notes-input");
  const decisionRestockCheckbox = document.getElementById("decision-restock-checkbox");

  const buyerReturnFormCard = document.getElementById("buyer-return-form-card");
  const buyerReturnForm = document.getElementById("buyer-return-form");
  const returnReasonInput = document.getElementById("return-reason-input");
  const returnEvidenceInput = document.getElementById("return-evidence-input");

  let currentOrder = null;
  let activeReturnRequest = null;
  let currentUser = null;

  function showMessage(text, isSuccess) {
    if (!text) {
      messageEl.classList.add("hidden");
      messageEl.textContent = "";
      return;
    }
    messageEl.textContent = text;
    messageEl.className = isSuccess ? "notice-box notice-success" : "notice-box notice-error";
    messageEl.classList.remove("hidden");
  }

  function formatCurrency(amount) {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency: "VND",
    }).format(amount);
  }

  function formatDate(isoString) {
    if (!isoString) return "-";
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  function setBadge(el, text, type) {
    el.textContent = text;
    el.className = "badge";
    if (type === "success") el.classList.add("badge-success");
    else if (type === "warning") el.classList.add("badge-warning");
    else if (type === "danger") el.classList.add("badge-danger");
    else if (type === "purple") el.classList.add("badge-purple");
    else el.classList.add("badge-info");
  }

  async function fetchCurrentUser() {
    if (!token) return null;
    try {
      const res = await fetch("/api/v1/auth/me", {
        headers: { Authorization: "Bearer " + token },
      });
      if (res.ok) {
        const body = await res.json();
        return body.data;
      }
    } catch {
      // Ignore auth fetch failure
    }
    return null;
  }

  async function loadOrder() {
    if (!token) {
      statusEl.textContent = "Please log in to view this order.";
      const authLink = document.getElementById("nav-auth-link");
      if (authLink) {
        authLink.href = "/login?return_to=" + encodeURIComponent(window.location.pathname);
      }
      return;
    }

    statusEl.textContent = "Loading order details...";
    currentUser = await fetchCurrentUser();

    try {
      const orderRes = await fetch("/api/v1/orders/" + encodeURIComponent(orderId), {
        headers: { Authorization: "Bearer " + token },
      });

      if (!orderRes.ok) {
        const err = await orderRes.json().catch(() => ({}));
        statusEl.textContent = "";
        showMessage(err.error ? err.error.message : "Unable to load order details.", false);
        return;
      }

      const orderData = await orderRes.json();
      currentOrder = orderData.data;

      // Also fetch return requests
      const returnsRes = await fetch("/api/v1/orders/" + encodeURIComponent(orderId) + "/returns", {
        headers: { Authorization: "Bearer " + token },
      });

      let returnRequests = [];
      if (returnsRes.ok) {
        const returnsData = await returnsRes.json();
        returnRequests = returnsData.data || [];
      }

      renderOrder(currentOrder, returnRequests);
      statusEl.textContent = "";
      contentEl.classList.remove("hidden");
    } catch (err) {
      statusEl.textContent = "";
      showMessage("Unable to connect to the order service. Please check your connection.", false);
    }
  }

  function renderOrder(order, returnRequests) {
    orderIdLabel.textContent = String(order.id);
    orderDateLabel.textContent = formatDate(order.created_at);

    // Status badges
    let statusType = "info";
    if (order.status === "DELIVERED" || order.status === "COMPLETED") statusType = "success";
    else if (order.status === "RETURN_REQUESTED") statusType = "warning";
    else if (order.status === "RETURNED_REFUNDED") statusType = "purple";
    else if (order.status === "CANCELLED") statusType = "danger";
    setBadge(badgeOrderStatus, order.status.replace("_", " "), statusType);

    const paymentType = order.payment_status === "REFUNDED" ? "purple" : "success";
    setBadge(badgePaymentStatus, "PAYMENT: " + (order.payment_status || "PAID"), paymentType);

    let escrowType = "info";
    if (order.escrow_status === "PAUSED") escrowType = "warning";
    else if (order.escrow_status === "RELEASED") escrowType = "success";
    else if (order.escrow_status === "REFUNDED") escrowType = "purple";
    setBadge(badgeEscrowStatus, "ESCROW: " + (order.escrow_status || "HELD"), escrowType);

    recipientNameEl.textContent = order.recipient_name || "-";
    recipientPhoneEl.textContent = order.phone_number ? "Phone: " + order.phone_number : "";
    deliveryAddressEl.textContent = order.delivery_address || "-";

    // Safely render table items using DOM APIs without innerHTML interpolation
    while (itemsTableBody.firstChild) {
      itemsTableBody.removeChild(itemsTableBody.firstChild);
    }

    if (Array.isArray(order.items)) {
      order.items.forEach(function (item) {
        const row = document.createElement("tr");

        const nameCell = document.createElement("td");
        const nameStrong = document.createElement("strong");
        nameStrong.textContent = item.product_name;
        nameCell.appendChild(nameStrong);
        row.appendChild(nameCell);

        const codeCell = document.createElement("td");
        codeCell.textContent = item.product_code;
        row.appendChild(codeCell);

        const priceCell = document.createElement("td");
        priceCell.className = "text-right";
        priceCell.textContent = formatCurrency(item.unit_price);
        row.appendChild(priceCell);

        const qtyCell = document.createElement("td");
        qtyCell.className = "text-right";
        qtyCell.textContent = String(item.quantity);
        row.appendChild(qtyCell);

        const totalCell = document.createElement("td");
        totalCell.className = "text-right";
        totalCell.textContent = formatCurrency(item.line_total);
        row.appendChild(totalCell);

        itemsTableBody.appendChild(row);
      });
    }

    orderTotalEl.textContent = formatCurrency(order.total_amount);

    // Escrow paused notice
    if (order.escrow_status === "PAUSED") {
      escrowNoticeEl.classList.remove("hidden");
    } else {
      escrowNoticeEl.classList.add("hidden");
    }

    // Return request logic
    activeReturnRequest = returnRequests.length > 0 ? returnRequests[0] : null;

    if (activeReturnRequest) {
      renderReturnCard(activeReturnRequest);
      returnStatusCard.classList.remove("hidden");
      buyerReturnFormCard.classList.add("hidden");
    } else {
      returnStatusCard.classList.add("hidden");
      if (order.status === "DELIVERED") {
        buyerReturnFormCard.classList.remove("hidden");
      } else {
        buyerReturnFormCard.classList.add("hidden");
      }
    }
  }

  function renderReturnCard(retReq) {
    returnReqIdEl.textContent = String(retReq.id);
    returnReqDateEl.textContent = formatDate(retReq.created_at);

    let retType = "warning";
    if (retReq.status === "APPROVED") retType = "success";
    else if (retReq.status === "REJECTED") retType = "danger";
    setBadge(badgeReturnStatus, retReq.status, retType);

    returnReqReasonEl.textContent = retReq.reason;
    returnReqEvidenceEl.textContent = retReq.evidence;

    if (retReq.status !== "PENDING") {
      returnResolutionDetails.classList.remove("hidden");
      returnDecisionNotesEl.textContent = retReq.decision_notes || "No notes provided.";
      if (retReq.status === "APPROVED") {
        returnRestockStatusEl.textContent = retReq.is_restockable
          ? "Items confirmed restockable; stock quantity has been restored."
          : "Items not restocked.";
      } else {
        returnRestockStatusEl.textContent = "Return request was rejected. Order returned to completion.";
      }
      reviewerPanel.classList.add("hidden");
    } else {
      returnResolutionDetails.classList.add("hidden");
      // Check if current user is seller or admin
      if (currentUser && (currentUser.role === "admin" || currentUser.role === "seller")) {
        reviewerPanel.classList.remove("hidden");
      } else {
        reviewerPanel.classList.add("hidden");
      }
    }
  }

  // Handle buyer return form submission
  if (buyerReturnForm) {
    buyerReturnForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      showMessage("", false);

      const reason = returnReasonInput.value.trim();
      const evidence = returnEvidenceInput.value.trim();

      if (!reason || !evidence) {
        showMessage("Please enter both a reason and supporting evidence.", false);
        return;
      }

      try {
        const res = await fetch("/api/v1/orders/" + encodeURIComponent(orderId) + "/returns", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + token,
          },
          body: JSON.stringify({ reason: reason, evidence: evidence }),
        });

        const data = await res.json();
        if (res.ok) {
          showMessage("Return request submitted successfully. Escrow release is paused until review.", true);
          loadOrder();
        } else {
          showMessage(data.error ? data.error.message : "Failed to submit return request.", false);
        }
      } catch (err) {
        showMessage("Unable to submit return request. Please check your connection.", false);
      }
    });
  }

  // Handle reviewer decision (Approve)
  if (btnApprove) {
    btnApprove.addEventListener("click", function () {
      submitDecision("APPROVE");
    });
  }

  // Handle reviewer decision (Reject)
  if (btnReject) {
    btnReject.addEventListener("click", function () {
      submitDecision("REJECT");
    });
  }

  async function submitDecision(action) {
    if (!activeReturnRequest) return;
    showMessage("", false);

    const notes = decisionNotesInput.value.trim();
    const isRestockable = decisionRestockCheckbox.checked;

    try {
      const res = await fetch("/api/v1/return-requests/" + encodeURIComponent(activeReturnRequest.id) + "/decision", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify({
          action: action,
          decision_notes: notes || null,
          is_restockable: isRestockable,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        const msg = action === "APPROVE"
          ? "Return request approved. Payment has been refunded and inventory updated."
          : "Return request rejected. Order returned to completion.";
        showMessage(msg, true);
        loadOrder();
      } else {
        showMessage(data.error ? data.error.message : "Failed to submit decision.", false);
      }
    } catch (err) {
      showMessage("Unable to submit decision. Please check your connection.", false);
    }
  }

  document.addEventListener("DOMContentLoaded", loadOrder);
})();
