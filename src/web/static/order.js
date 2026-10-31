"use strict";

const money = (n) =>
  new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(n);

const formatDate = (isoStr) => {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  return d.toLocaleDateString("vi-VN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatMetricDate = (isoStr) => {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const formatOrderDate = (isoStr) => {
  if (!isoStr || Number.isNaN(new Date(isoStr).getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }).format(new Date(isoStr));
};

const statusNames = {
  PENDING: "Order Placed",
  CONFIRMED: "In Production",
  PROCESSING: "In Production",
  CANCELLATION_REQUESTED: "Cancellation Requested",
  SHIPPED: "Ocean Transit",
  DELIVERED: "Shipping Final Mile",
  COMPLETED: "Delivered",
  CANCELLED: "Order Cancelled",
  RETURN_REQUESTED: "Return Requested",
  RETURNED_REFUNDED: "Returned and Refunded",
};

const elements = {
  title: document.getElementById("order-title"),
  statusBadge: document.getElementById("order-status-badge"),
  liveIndicator: document.getElementById("live-indicator"),
  meta: document.getElementById("order-meta"),
  statusMsg: document.getElementById("status-message"),
  errorMsg: document.getElementById("error-message"),
  milestonesCard: document.getElementById("milestones-card"),
  actionsCard: document.getElementById("actions-card"),
  actionHint: document.getElementById("action-hint"),
  // Buyer action buttons
  cancelBtn: document.getElementById("cancel-btn"),
  reqCancelBtn: document.getElementById("req-cancel-btn"),
  confirmDeliveryBtn: document.getElementById("confirm-delivery-btn"),
  // Seller action buttons
  sellerConfirmBtn: document.getElementById("seller-confirm-btn"),
  sellerShipBtn: document.getElementById("seller-ship-btn"),
  sellerDeliverBtn: document.getElementById("seller-deliver-btn"),
  sellerApproveCancelBtn: document.getElementById("seller-approve-cancel-btn"),
  sellerRejectCancelBtn: document.getElementById("seller-reject-cancel-btn"),
  sellerCancelBtn: document.getElementById("seller-cancel-btn"),
  sellerOrdersLink: document.getElementById("seller-orders-link"),
  adminPortalLink: document.getElementById("admin-portal-link"),
  myOrdersLink: document.getElementById("my-orders-link"),
  detailsCard: document.getElementById("details-card"),
  recipientName: document.getElementById("recipient-name"),
  phoneNumber: document.getElementById("phone-number"),
  deliveryAddress: document.getElementById("delivery-address"),
  itemsCard: document.getElementById("items-card"),
  itemsList: document.getElementById("items-list"),
  orderTotal: document.getElementById("order-total"),
  priceBreakdown: document.getElementById("order-price-breakdown"),
  breakdownUnavailable: document.getElementById("order-breakdown-unavailable"),
  retryBtn: document.getElementById("retry-btn"),
  trackingInfo: document.getElementById("tracking-info"),
  trackingNumberVal: document.getElementById("tracking-number-val"),
  // New Metric Summary & Status Elements
  summaryMetricsBar: document.getElementById("summary-metrics-bar"),
  orderPlacedVal: document.getElementById("order-placed-val"),
  orderTotalVal: document.getElementById("order-total-val"),
  orderShipToVal: document.getElementById("order-ship-to-val"),
  orderIdVal: document.getElementById("order-id-val"),
  statusHeadlineName: document.getElementById("status-headline-name"),
  estDeliveryVal: document.getElementById("est-delivery-val"),
  stepperProgressBar: document.getElementById("stepper-progress-bar"),
  mapBtnVector: document.getElementById("map-btn-vector"),
  mapBtnSat: document.getElementById("map-btn-sat"),
  mapViewport: document.getElementById("delivery-map-viewport"),
  mapTargetLabel: document.getElementById("map-target-label"),
  orderSwitcherWrap: document.getElementById("order-switcher-wrap"),
  orderSelect: document.getElementById("order-select"),
  // Badges & Escrow
  badgePaymentMethod: document.getElementById("badge-payment-method"),
  badgePaymentStatus: document.getElementById("badge-payment-status"),
  badgeEscrowStatus: document.getElementById("badge-escrow-status"),
  escrowNotice: document.getElementById("escrow-paused-notice"),
  // Return / Refund elements
  returnStatusCard: document.getElementById("return-status-card"),
  returnReqId: document.getElementById("return-req-id"),
  returnReqDate: document.getElementById("return-req-date"),
  badgeReturnStatus: document.getElementById("badge-return-status"),
  returnReqReason: document.getElementById("return-req-reason"),
  returnReqEvidence: document.getElementById("return-req-evidence"),
  returnResolutionDetails: document.getElementById("return-resolution-details"),
  returnReqDecisionNotes: document.getElementById("return-req-decision-notes"),
  returnReqRestockStatus: document.getElementById("return-req-restock-status"),
  reviewerPanel: document.getElementById("reviewer-decision-panel"),
  btnApproveReturn: document.getElementById("btn-approve-return"),
  btnRejectReturn: document.getElementById("btn-reject-return"),
  decisionNotesInput: document.getElementById("decision-notes-input"),
  decisionRestockCheckbox: document.getElementById("decision-restock-checkbox"),
  returnRequestsList: document.getElementById("return-requests-list"),
  returnSingleRequestDetails: document.getElementById("return-single-request-details"),
};

let currentOrder = null;
let orderLoadRevision = 0;
const buyerReturns = window.BuyerReturns.create({
  getToken,
  onSubmitted: refreshOrderAfterReturn,
  onPending: pending => {
    elements.confirmDeliveryBtn.disabled = pending;
    elements.orderSelect.disabled = pending;
  },
});

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("token");
}

function getCurrentUser() {
  const token = getToken();
  if (!token) return null;
  try {
    let b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const jsonStr = decodeURIComponent(
      Array.prototype.map
        .call(atob(b64), function (c) {
          return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2);
        })
        .join("")
    );
    const payload = JSON.parse(jsonStr);
    return { id: Number(payload.sub), role: payload.role };
  } catch {
    return null;
  }
}

function getOrderId() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  const last = parts[parts.length - 1];
  return last === "orders" || last === "order" ? null : last;
}

async function request(url, options = {}) {
  const token = getToken();
  if (!token) {
    window.location.replace(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
    return null;
  }
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Network error. Please check your connection and retry.");
  }
  if (getToken() !== token) return null;
  if (response.status === 401) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    window.location.replace(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
    return null;
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message || "Failed to complete request.");
  }
  return payload;
}

function updateStepper(order) {
  const status = order.status;
  const steps = [
    { id: "step-ordered", line: null, dateId: "step-ordered-date", date: order.created_at },
    { id: "step-confirmed", line: 0, dateId: "step-confirmed-date", date: null },
    { id: "step-shipped", line: 1, dateId: "step-shipped-date", date: order.shipped_at },
    { id: "step-delivered", line: 2, dateId: "step-delivered-date", date: order.delivered_at },
    { id: "step-completed", line: 3, dateId: "step-completed-date", date: order.completed_at },
  ];

  const statusWeights = {
    PENDING: 1,
    CONFIRMED: 2,
    PROCESSING: 2,
    CANCELLATION_REQUESTED: 2,
    SHIPPED: 3,
    DELIVERED: 4,
    COMPLETED: 5,
    CANCELLED: 0,
  };

  const progressPercent = {
    0: 0,
    1: 0,
    2: 25,
    3: 50,
    4: 75,
    5: 100,
  };

  const currentWeight = statusWeights[status] || 1;

  steps.forEach((step, index) => {
    const el = document.getElementById(step.id);
    if (!el) return;
    el.classList.remove("active", "done");
    const stepNum = index + 1;
    if (status === "CANCELLED") {
      // no steps marked active
    } else if (stepNum < currentWeight) {
      el.classList.add("done");
    } else if (stepNum === currentWeight) {
      el.classList.add("active");
    }

    if (step.date) {
      const dateEl = document.getElementById(step.dateId);
      if (dateEl) dateEl.textContent = formatMetricDate(step.date);
    }
  });

  if (elements.stepperProgressBar) {
    const pct = status === "CANCELLED" ? 0 : (progressPercent[currentWeight] ?? 0);
    elements.stepperProgressBar.style.width = `${pct}%`;
  }

  if (order.tracking_number) {
    elements.trackingInfo.hidden = false;
    elements.trackingNumberVal.textContent = order.tracking_number;
  } else {
    elements.trackingInfo.hidden = true;
  }
}

function updateActions(order) {
  const user = getCurrentUser();
  const isSeller = Boolean(user && user.role === "seller");
  const isAdmin = Boolean(user && user.role === "admin");

  if (elements.sellerOrdersLink) {
    elements.sellerOrdersLink.hidden = !isSeller;
  }
  if (elements.adminPortalLink) {
    elements.adminPortalLink.hidden = !isAdmin;
  }
  if (elements.myOrdersLink) {
    elements.myOrdersLink.hidden = isSeller;
  }

  // Reset all buttons
  elements.cancelBtn.hidden = true;
  elements.reqCancelBtn.hidden = true;
  elements.confirmDeliveryBtn.hidden = true;

  elements.sellerConfirmBtn.hidden = true;
  elements.sellerShipBtn.hidden = true;
  elements.sellerDeliverBtn.hidden = true;
  elements.sellerApproveCancelBtn.hidden = true;
  elements.sellerRejectCancelBtn.hidden = true;
  elements.sellerCancelBtn.hidden = true;
  elements.actionHint.textContent = "";

  const st = order.status;

  if (isSeller) {
    // Seller action controls
    if (st === "PENDING") {
      elements.actionsCard.hidden = false;
      elements.sellerConfirmBtn.hidden = false;
      elements.sellerCancelBtn.hidden = false;
      elements.actionHint.textContent = "New buyer order. Review and confirm to begin order fulfillment.";
    } else if (st === "CONFIRMED" || st === "PROCESSING") {
      elements.actionsCard.hidden = false;
      elements.sellerShipBtn.hidden = false;
      elements.sellerCancelBtn.hidden = false;
      elements.actionHint.textContent = "Order is confirmed. When packaged, enter tracking number to ship.";
    } else if (st === "CANCELLATION_REQUESTED") {
      elements.actionsCard.hidden = false;
      elements.sellerApproveCancelBtn.hidden = false;
      elements.sellerRejectCancelBtn.hidden = false;
      elements.actionHint.textContent = "Buyer requested cancellation. Approve to cancel and restore stock, or reject.";
    } else if (st === "SHIPPED") {
      elements.actionsCard.hidden = false;
      elements.sellerDeliverBtn.hidden = false;
      elements.actionHint.textContent = "Package is in transit. Mark as delivered once carrier confirms delivery.";
    } else {
      elements.actionsCard.hidden = true;
    }
  } else {
    // Buyer action controls: clean, minimal, only show what the buyer is strictly authorized to perform
    if (st === "PENDING") {
      elements.actionsCard.hidden = false;
      elements.cancelBtn.hidden = false;
      elements.actionHint.textContent = "Your order is pending confirmation. You may cancel it if you changed your mind.";
    } else if (st === "CONFIRMED" || st === "PROCESSING") {
      elements.actionsCard.hidden = false;
      elements.reqCancelBtn.hidden = false;
      elements.actionHint.textContent = "Your order is being prepared. You can request a cancellation from the seller.";
    } else if (st === "DELIVERED") {
      elements.actionsCard.hidden = false;
      elements.confirmDeliveryBtn.hidden = false;
      elements.actionHint.textContent = "Your package has been delivered! Please inspect the items and confirm receipt below.";
    } else {
      elements.actionsCard.hidden = true;
    }
  }
}

let pollTimer = null;

function renderPriceBreakdown(order) {
  if (!elements.priceBreakdown || !elements.breakdownUnavailable) return;
  const columns = [
    {field: "subtotal", id: "order-subtotal", sign: 1},
    {field: "shop_discount", id: "order-shop-discount", sign: -1},
    {field: "platform_discount", id: "order-platform-discount", sign: -1},
    {field: "shipping_fee", id: "order-shipping-fee", sign: 1},
    {field: "shipping_discount", id: "order-shipping-discount", sign: -1},
  ];
  const children = order.sub_orders || [];
  // Legacy defaults and seller-scoped partial receipts cannot explain a full order total.
  const complete = children.length > 0 && children.every(child =>
    child.pricing_policy_version && child.pricing_policy_version !== "LEGACY" &&
    [...columns.map(column => column.field), "total_amount"].every(field =>
      Number.isSafeInteger(child[field]) && child[field] >= 0)
  );
  const totals = columns.map(column =>
    children.reduce((sum, child) => sum + child[column.field], 0));
  const reconciles = complete &&
    children.reduce((sum, child) => sum + child.total_amount, 0) === order.total_amount &&
    totals.reduce((sum, amount, index) => sum + amount * columns[index].sign, 0) === order.total_amount;
  elements.priceBreakdown.hidden = !reconciles;
  elements.breakdownUnavailable.hidden = reconciles;
  columns.forEach((column, index) => {
    const amount = totals[index];
    document.getElementById(column.id).textContent = reconciles ?
      money(amount === 0 ? 0 : amount * column.sign) : "";
  });
}

function startPolling(orderId) {
  if (pollTimer) clearInterval(pollTimer);
  if (!orderId) return;
  const revision = orderLoadRevision;
  const token = getToken();

  pollTimer = setInterval(async () => {
    try {
      const payload = await request(`/api/v1/orders/${encodeURIComponent(orderId)}`);
      if (revision !== orderLoadRevision || getToken() !== token || currentOrder?.id !== orderId) return;
      if (payload && payload.data) {
        const updated = payload.data;
        if (
          !currentOrder ||
          currentOrder.status !== updated.status ||
          JSON.stringify(currentOrder.sub_orders) !== JSON.stringify(updated.sub_orders) ||
          currentOrder.tracking_number !== updated.tracking_number ||
          currentOrder.payment_method !== updated.payment_method ||
          currentOrder.payment_status !== updated.payment_status
        ) {
          renderOrder(updated);
        }
        if (["COMPLETED", "CANCELLED"].includes(updated.status)) {
          clearInterval(pollTimer);
          if (elements.liveIndicator) elements.liveIndicator.hidden = true;
        }
      }
    } catch (_) {}
  }, 4000);
}

function renderOrder(order) {
  currentOrder = order;

  if (elements.title) elements.title.textContent = "ORDER TRACKING PAGE";
  if (elements.statusBadge) {
    elements.statusBadge.textContent = order.status.replace("_", " ");
    elements.statusBadge.className = `badge ${order.status.toLowerCase()}`;
  }

  if (elements.liveIndicator) {
    elements.liveIndicator.hidden = ["COMPLETED", "CANCELLED"].includes(order.status);
  }

  // Display purchase facts from the receipt, independently of today's product prices.
  if (elements.summaryMetricsBar) elements.summaryMetricsBar.hidden = false;
  if (elements.orderPlacedVal) {
    const placed = formatOrderDate(order.created_at);
    elements.orderPlacedVal.textContent = placed;
    if (placed === "Date unavailable") elements.orderPlacedVal.removeAttribute("datetime");
    else elements.orderPlacedVal.setAttribute("datetime", order.created_at);
  }
  if (elements.orderTotalVal) elements.orderTotalVal.textContent = money(order.total_amount);
  if (elements.orderShipToVal) elements.orderShipToVal.textContent = order.recipient_name || "—";
  if (elements.orderIdVal) elements.orderIdVal.textContent = `#${order.id}`;

  // Populate Status Headline
  if (elements.statusHeadlineName) {
    elements.statusHeadlineName.textContent = statusNames[order.status] || order.status;
    if (order.status === "CANCELLED") {
      elements.statusHeadlineName.style.color = "#dc2626";
    } else {
      elements.statusHeadlineName.style.color = "#16a34a";
    }
  }

  // Populate Estimated Delivery
  if (elements.estDeliveryVal) {
    if (order.status === "COMPLETED" && order.completed_at) {
      elements.estDeliveryVal.textContent = `Completed on ${formatMetricDate(order.completed_at)}`;
    } else if (order.status === "DELIVERED" && order.delivered_at) {
      elements.estDeliveryVal.textContent = `Delivered on ${formatMetricDate(order.delivered_at)}`;
    } else if (order.status === "SHIPPED") {
      elements.estDeliveryVal.textContent = "Arriving in 1 - 3 business days";
    } else if (order.status === "CANCELLED") {
      elements.estDeliveryVal.textContent = "Order cancelled";
    } else {
      elements.estDeliveryVal.textContent = "Estimated in 2 - 4 business days";
    }
  }

  // Recipient details
  elements.recipientName.textContent = order.recipient_name;
  elements.phoneNumber.textContent = order.phone_number;
  elements.deliveryAddress.textContent = order.delivery_address;
  elements.orderTotal.textContent = money(order.total_amount);
  renderPriceBreakdown(order);

  // Map destination pin label
  if (elements.mapTargetLabel && order.delivery_address) {
    const parts = order.delivery_address.split(",").map((s) => s.trim()).filter(Boolean);
    elements.mapTargetLabel.textContent = parts[parts.length - 1] || "Destination";
  }

  // Table of items (DOM APIs + textContent to prevent stored XSS)
  const table = document.createElement("table");
  table.className = "items-table";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = [
    { title: "Product", align: "left" },
    { title: "Code", align: "left" },
    { title: "Unit Price", align: "left" },
    { title: "Quantity", align: "left" },
    { title: "Total", align: "right" },
  ];
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.title;
    if (col.align === "right") {
      th.style.textAlign = "right";
    }
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  (order.items || []).forEach((item) => {
    const tr = document.createElement("tr");

    const tdName = document.createElement("td");
    if (item.image_url) {
      const image = document.createElement("img");
      image.className = "order-item-image";
      image.src = item.image_url;
      image.alt = item.product_name;
      image.loading = "lazy";
      tdName.appendChild(image);
    }
    const strongName = document.createElement("strong");
    const nameStrong = strongName;
    nameStrong.textContent = item.product_name;
    strongName.textContent = item.product_name;
    if (item.variant_name) strongName.textContent += ` · ${item.variant_name}`;
    tdName.appendChild(strongName);
    if (item.seller_order_id) {
      const subTag = document.createElement("span");
      subTag.style.cssText = "display: block; font-size: 11px; color: var(--ios-text-muted); margin-top: 2px;";
      subTag.textContent = item.seller_order_status
        ? `Sub-Order #${item.seller_order_id} (${item.seller_order_status.replace("_", " ")})`
        : `Sub-Order #${item.seller_order_id}`;
      tdName.appendChild(subTag);
    }
    tr.appendChild(tdName);

    const tdCode = document.createElement("td");
    const codeCell = tdCode;
    const codeEl = document.createElement("code");
    codeEl.textContent = item.product_code;
    codeCell.textContent = item.product_code;
    codeCell.appendChild(codeEl);
    tr.appendChild(tdCode);

    const tdPrice = document.createElement("td");
    tdPrice.textContent = money(item.unit_price);
    tr.appendChild(tdPrice);

    const tdQty = document.createElement("td");
    tdQty.textContent = item.quantity;
    tr.appendChild(tdQty);

    const tdTotal = document.createElement("td");
    tdTotal.className = "money";
    tdTotal.textContent = money(item.line_total);
    tr.appendChild(tdTotal);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  elements.itemsList.replaceChildren(table);

  PaymentDisplay.renderBadges(order, elements.badgePaymentMethod, elements.badgePaymentStatus);
  if (elements.badgeEscrowStatus) {
    elements.badgeEscrowStatus.hidden = false;
    elements.badgeEscrowStatus.textContent = "Escrow: " + (order.escrow_status || "HELD");
    elements.badgeEscrowStatus.className = "badge " + (
      order.escrow_status === "PAUSED" ? "badge-warning" :
      ["REFUNDED", "VOIDED"].includes(order.escrow_status) ? "badge-purple" : "badge-info"
    );
  }
  if (elements.escrowNotice) {
    elements.escrowNotice.hidden = order.escrow_status !== "PAUSED";
  }

  loadReturnRequests(order);
  updateStepper(order);
  updateActions(order);
  elements.milestonesCard.hidden = false;
  elements.detailsCard.hidden = false;
  elements.itemsCard.hidden = false;

  // Real Leaflet Interactive Map
  initRealMap(order.delivery_address, order.recipient_name);
}

let mapInstance = null;
let vectorTileLayer = null;
let satTileLayer = null;
let markerInstance = null;

function initRealMap(address, recipientName) {
  if (typeof L === "undefined") {
    // If Leaflet is still loading or offline, fallback to vector graphics preview
    return;
  }
  const container = document.getElementById("leaflet-map");
  if (!container) return;

  if (!mapInstance) {
    mapInstance = L.map("leaflet-map", {
      center: [21.0285, 105.8542],
      zoom: 14,
      zoomControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(mapInstance);

    vectorTileLayer = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
      }
    );

    satTileLayer = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        maxZoom: 18,
      }
    );

    vectorTileLayer.addTo(mapInstance);

    if (elements.mapViewport) {
      elements.mapViewport.classList.add("leaflet-loaded");
    }

    if (elements.mapBtnVector && elements.mapBtnSat) {
      elements.mapBtnVector.addEventListener("click", () => {
        elements.mapBtnVector.classList.add("active");
        elements.mapBtnSat.classList.remove("active");
        if (mapInstance && mapInstance.hasLayer(satTileLayer)) {
          mapInstance.removeLayer(satTileLayer);
          vectorTileLayer.addTo(mapInstance);
        }
      });
      elements.mapBtnSat.addEventListener("click", () => {
        elements.mapBtnSat.classList.add("active");
        elements.mapBtnVector.classList.remove("active");
        if (mapInstance && mapInstance.hasLayer(vectorTileLayer)) {
          mapInstance.removeLayer(vectorTileLayer);
          satTileLayer.addTo(mapInstance);
        }
      });
    }

    const expandBtn = document.getElementById("map-expand-btn");
    if (expandBtn) {
      expandBtn.addEventListener("click", () => {
        const grid = document.querySelector(".shipping-and-map-grid");
        if (grid) {
          grid.classList.toggle("map-expanded");
          setTimeout(() => mapInstance && mapInstance.invalidateSize(), 300);
        }
      });
    }
  }

  if (address) {
    geocodeAndPin(address, recipientName);
  }
}

async function geocodeAndPin(address, recipientName) {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(address)}`,
      { headers: { "Accept-Language": "vi,en" } }
    );
    const data = await res.json();
    if (data && data.length > 0) {
      const lat = parseFloat(data[0].lat);
      const lon = parseFloat(data[0].lon);
      updateMapMarker(lat, lon, address, recipientName);
      return;
    }
  } catch (_) {}

  // Fallback to Vietnam major cities or default coordinates
  const lower = (address || "").toLowerCase();
  let defaultCoords = [21.0285, 105.8542]; // Hanoi
  if (lower.includes("hồ chí minh") || lower.includes("hcm") || lower.includes("sài gòn")) {
    defaultCoords = [10.7769, 106.7009];
  } else if (lower.includes("đà nẵng") || lower.includes("da nang")) {
    defaultCoords = [16.0544, 108.2022];
  }
  updateMapMarker(defaultCoords[0], defaultCoords[1], address, recipientName);
}

function updateMapMarker(lat, lon, address, recipientName) {
  if (!mapInstance || typeof L === "undefined") return;
  mapInstance.setView([lat, lon], 14);
  setTimeout(() => mapInstance && mapInstance.invalidateSize(), 200);

  const applePinIcon = L.divIcon({
    className: "apple-map-marker-pin",
    html: `
      <div style="position:relative; display:flex; align-items:center; justify-content:center;">
        <div style="position:absolute; width:18px; height:8px; background:rgba(239,68,68,0.35); border-radius:50%; bottom:-4px; filter:blur(1px);"></div>
        <svg viewBox="0 0 24 24" fill="#ef4444" style="width:34px; height:34px; filter:drop-shadow(0 3px 6px rgba(0,0,0,0.35));">
          <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
        </svg>
      </div>
    `,
    iconSize: [34, 34],
    iconAnchor: [17, 34],
    popupAnchor: [0, -34],
  });

  if (markerInstance) {
    markerInstance.setLatLng([lat, lon]);
  } else {
    markerInstance = L.marker([lat, lon], { icon: applePinIcon }).addTo(mapInstance);
  }

  const popupContent = document.createElement("div");
  const strongEl = document.createElement("strong");
  strongEl.textContent = recipientName || "Delivery Location";
  popupContent.appendChild(strongEl);
  popupContent.appendChild(document.createElement("br"));
  if (address) {
    popupContent.appendChild(document.createTextNode(address));
  }
  markerInstance.bindPopup(popupContent).openPopup();
}

window.addEventListener("load", () => {
  if (currentOrder && currentOrder.delivery_address) {
    initRealMap(currentOrder.delivery_address, currentOrder.recipient_name);
  }
});

async function loadOrder(specifiedId) {
  const id = specifiedId || getOrderId();
  const revision = ++orderLoadRevision;
  const token = getToken();
  if (!id || String(currentOrder?.id) !== String(id)) buyerReturns.reset();
  else buyerReturns.hide();
  const user = getCurrentUser();
  elements.errorMsg.hidden = true;
  elements.statusMsg.hidden = false;
  elements.statusMsg.textContent = "Loading order details...";
  elements.retryBtn.hidden = true;

  try {
    let payload = null;
    let availableOrders = [];

    if (user && user.role === "buyer") {
      try {
        const listPayload = await request("/api/v1/orders");
        if (Array.isArray(listPayload)) {
          availableOrders = listPayload.map((o) => o.data);
        }
      } catch (_) {}
    } else if (user && user.role === "seller") {
      try {
        const soPayload = await request("/api/v1/seller/orders?limit=50");
        if (soPayload && Array.isArray(soPayload.data)) {
          availableOrders = soPayload.data.map((so) => ({
            id: so.order_id,
            total_amount: so.items.reduce((s, it) => s + it.total_price, 0),
            status: so.status,
          }));
        }
      } catch (_) {}
    }

    if (revision !== orderLoadRevision || getToken() !== token) return;
    if (id) {
      payload = await request(`/api/v1/orders/${encodeURIComponent(id)}`);
    } else {
      if (availableOrders.length > 0) {
        const targetId = availableOrders[0].id;
        payload = await request(`/api/v1/orders/${encodeURIComponent(targetId)}`);
        history.replaceState(null, "", `/order/${targetId}`);
      } else {
        if (user && user.role === "seller") {
          window.location.replace("/seller/orders");
          return;
        }
        elements.statusMsg.hidden = true;
        elements.errorMsg.hidden = false;
        elements.errorMsg.textContent = "You do not have any orders yet. Start shopping to place an order!";
        return;
      }
    }

    if (revision !== orderLoadRevision || getToken() !== token || !payload?.data) return;
    elements.statusMsg.hidden = true;
    renderOrder(payload.data);
    updateOrderSwitcher(availableOrders, payload.data.id);
    startPolling(payload.data.id);
  } catch (err) {
    if (revision !== orderLoadRevision || getToken() !== token) return;
    elements.statusMsg.hidden = true;
    elements.errorMsg.hidden = false;
    elements.errorMsg.textContent = err.message;
    elements.retryBtn.hidden = false;
  }
}

async function refreshOrderAfterReturn(orderId) {
  const revision = orderLoadRevision;
  const token = getToken();
  try {
    const payload = await request(`/api/v1/orders/${encodeURIComponent(orderId)}`);
    if (revision !== orderLoadRevision || getToken() !== token || currentOrder?.id !== orderId) return;
    if (payload?.data) {
      renderOrder(payload.data);
      startPolling(orderId);
    }
  } catch (_) {
    if (revision !== orderLoadRevision || getToken() !== token) return;
    elements.errorMsg.textContent = "Your return request was submitted, but order details could not refresh. Select Retry.";
    elements.errorMsg.hidden = false;
    elements.retryBtn.hidden = false;
  }
}

window.addEventListener("popstate", () => loadOrder());
window.addEventListener("storage", event => {
  if (event.key && !["access_token", "token"].includes(event.key)) return;
  buyerReturns.reset();
  currentOrder = null;
  for (const element of [elements.milestonesCard, elements.detailsCard, elements.itemsCard,
    elements.actionsCard, elements.summaryMetricsBar, elements.orderSwitcherWrap]) element.hidden = true;
  void loadOrder();
});

function updateOrderSwitcher(orders, currentId) {
  if (!elements.orderSwitcherWrap || !elements.orderSelect) return;
  if (!orders || orders.length <= 1) {
    elements.orderSwitcherWrap.hidden = true;
    return;
  }
  elements.orderSelect.replaceChildren();
  const seen = new Set();
  orders.forEach((o) => {
    if (seen.has(o.id)) return;
    seen.add(o.id);
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = `Order #${o.id} — ${money(o.total_amount)} (${o.status.replace("_", " ")})`;
    if (String(o.id) === String(currentId)) {
      opt.selected = true;
    }
    elements.orderSelect.appendChild(opt);
  });
  elements.orderSwitcherWrap.hidden = false;
  elements.orderSelect.onchange = (e) => {
    const nextId = e.target.value;
    history.pushState(null, "", `/order/${nextId}`);
    loadOrder(nextId);
  };
}

async function handleAction(newStatus, confirmPrompt, extraData = {}) {
  if (confirmPrompt && !window.confirm(confirmPrompt)) {
    return;
  }
  const id = (currentOrder && currentOrder.id) || getOrderId();
  elements.statusMsg.hidden = false;
  elements.statusMsg.textContent = "Updating order...";
  elements.errorMsg.hidden = true;

  try {
    const payload = await request(`/api/v1/orders/${encodeURIComponent(id)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus, ...extraData }),
    });
    if (!payload) return;
    elements.statusMsg.textContent = "Status updated successfully.";
    renderOrder(payload.data);
    startPolling(payload.data.id);
    setTimeout(() => {
      elements.statusMsg.hidden = true;
    }, 4000);
  } catch (err) {
    elements.statusMsg.hidden = true;
    elements.errorMsg.hidden = false;
    elements.errorMsg.textContent = err.message;
  }
}

// Buyer triggers
elements.cancelBtn.addEventListener("click", () =>
  handleAction("CANCELLED", "Are you sure you want to cancel this order?")
);

elements.reqCancelBtn.addEventListener("click", () =>
  handleAction("CANCELLATION_REQUESTED", "Request cancellation from the seller?")
);

elements.confirmDeliveryBtn.addEventListener("click", () =>
  handleAction("COMPLETED", "Confirm that you have received your order in good condition?")
);

// Seller triggers
elements.sellerConfirmBtn.addEventListener("click", () =>
  handleAction("CONFIRMED", "Confirm this order for fulfillment?")
);

elements.sellerShipBtn.addEventListener("click", () => {
  const tracking = window.prompt("Enter carrier tracking number:", "TRK-" + Math.floor(100000 + Math.random() * 900000));
  if (!tracking) return;
  handleAction("SHIPPED", null, { tracking_number: tracking.trim() });
});

elements.sellerDeliverBtn.addEventListener("click", () =>
  handleAction("DELIVERED", "Mark this order as delivered to buyer?")
);

elements.sellerApproveCancelBtn.addEventListener("click", () =>
  handleAction("CANCELLED", "Approve buyer cancellation? Restores item inventory to stock.")
);

elements.sellerRejectCancelBtn.addEventListener("click", () =>
  handleAction("CONFIRMED", "Reject buyer cancellation and keep order in fulfillment?")
);

elements.sellerCancelBtn.addEventListener("click", () =>
  handleAction("CANCELLED", "Cancel this order? Restores item inventory to stock.")
);

elements.retryBtn.addEventListener("click", () => loadOrder());

loadOrder();

let activeReturnRequest = null;

async function loadReturnRequests(order) {
  if (!order || !order.id) return;
  const user = getCurrentUser();
  if (user?.role === "buyer") {
    await buyerReturns.update(order);
    return;
  }
  buyerReturns.reset();
  try {
    const token = getToken();
    const res = await request(`/api/v1/orders/${encodeURIComponent(order.id)}/returns`);
    if (token !== getToken() || currentOrder?.id !== order.id) return;
    const returnRequests = (res && res.data) ? res.data : [];
    activeReturnRequest = returnRequests.length > 0 ? returnRequests[0] : null;

    // Display Return Requests Status per seller order
    if (elements.returnStatusCard) {
      if (returnRequests.length > 0) {
        elements.returnStatusCard.hidden = false;

        // Populate single request elements for backwards compatibility
        const primaryReq = activeReturnRequest;
        if (elements.returnReqId) elements.returnReqId.textContent = String(primaryReq.id);
        if (elements.returnReqDate) elements.returnReqDate.textContent = formatDate(primaryReq.created_at);
        if (elements.badgeReturnStatus) {
          elements.badgeReturnStatus.textContent = primaryReq.status;
          elements.badgeReturnStatus.className = "badge " + (
            primaryReq.status === "APPROVED" ? "badge-success" :
            primaryReq.status === "REJECTED" ? "badge-danger" : "badge-warning"
          );
        }
        if (elements.returnReqReason) elements.returnReqReason.textContent = primaryReq.reason;
        if (elements.returnReqEvidence) elements.returnReqEvidence.textContent = primaryReq.evidence;

        const returnResolutionDetails = document.getElementById("return-resolution-details");
        if (primaryReq.status !== "PENDING") {
          if (returnResolutionDetails) {
            returnResolutionDetails.hidden = false;
            if (elements.returnReqDecisionNotes) {
              elements.returnReqDecisionNotes.textContent = primaryReq.decision_notes || "No notes provided.";
            }
            if (elements.returnReqRestockStatus) {
              elements.returnReqRestockStatus.textContent = primaryReq.status === "APPROVED"
                ? (primaryReq.is_restockable ? "Items confirmed restockable; inventory restored." : "Items not restocked.")
                : "Return request was rejected. Order returned to completion.";
            }
          }
          if (elements.reviewerPanel) elements.reviewerPanel.hidden = true;
        } else {
          if (returnResolutionDetails) returnResolutionDetails.hidden = true;
          if (elements.reviewerPanel) {
            elements.reviewerPanel.hidden = !(user && (user.role === "admin" || user.role === "seller"));
          }
        }

        // If multiple return requests, render per-seller-order list
        if (elements.returnRequestsList && returnRequests.length > 1) {
          if (elements.returnSingleRequestDetails) elements.returnSingleRequestDetails.hidden = true;
          elements.returnRequestsList.replaceChildren();

          returnRequests.forEach((req) => {
            const card = document.createElement("div");
            card.className = "return-request-item";
            card.style.cssText = "padding: 14px; border: 1px solid var(--ios-border); border-radius: 12px; margin-bottom: 12px; background: rgba(0,0,0,0.015);";

            const headerRow = document.createElement("div");
            headerRow.style.cssText = "display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;";

            const subOrderTitle = document.createElement("strong");
            const items = (order.items || []).filter((it) => it.seller_order_id === req.seller_order_id);
            const summary = items.map((it) => it.product_name).join(", ");
            subOrderTitle.textContent = `Sub-Order #${req.seller_order_id} ${summary ? "(" + summary + ")" : ""}`;

            const badge = document.createElement("span");
            badge.className = "badge " + (
              req.status === "APPROVED" ? "badge-success" :
              req.status === "REJECTED" ? "badge-danger" : "badge-warning"
            );
            badge.textContent = req.status;

            headerRow.append(subOrderTitle, badge);
            card.appendChild(headerRow);

            const metaP = document.createElement("p");
            metaP.style.cssText = "font-size: 13px; color: var(--ios-text-muted); margin-bottom: 8px;";
            metaP.textContent = `Request #${req.id} · Submitted on ${formatDate(req.created_at)}`;
            card.appendChild(metaP);

            const reasonP = document.createElement("p");
            reasonP.style.cssText = "font-size: 14px; margin-bottom: 6px;";
            const reasonLabel = document.createElement("strong");
            reasonLabel.textContent = "Reason: ";
            reasonP.append(reasonLabel, document.createTextNode(req.reason));
            card.appendChild(reasonP);

            const evidenceP = document.createElement("p");
            evidenceP.style.cssText = "font-size: 14px; margin-bottom: 8px; white-space: pre-wrap;";
            const evidenceLabel = document.createElement("strong");
            evidenceLabel.textContent = "Evidence: ";
            evidenceP.append(evidenceLabel, document.createTextNode(req.evidence));
            card.appendChild(evidenceP);

            if (req.status !== "PENDING") {
              const resDiv = document.createElement("div");
              resDiv.style.cssText = "padding-top: 8px; border-top: 1px solid var(--ios-border); font-size: 13px;";
              const notesP = document.createElement("p");
              notesP.textContent = `Notes: ${req.decision_notes || "No notes provided."}`;
              const restockP = document.createElement("p");
              restockP.style.cssText = "font-weight: 600; color: var(--ios-green); margin-top: 4px;";
              restockP.textContent = req.status === "APPROVED"
                ? (req.is_restockable ? "Inventory restored." : "Inventory not restocked.")
                : "Request rejected.";
              resDiv.append(notesP, restockP);
              card.appendChild(resDiv);
            } else if (user && (user.role === "admin" || user.role === "seller")) {
              const actionRow = document.createElement("div");
              actionRow.style.cssText = "margin-top: 10px; display: flex; gap: 8px;";

              const btnApprove = document.createElement("button");
              btnApprove.type = "button";
              btnApprove.className = "ios-btn ios-btn-primary";
              btnApprove.style.cssText = "background: #16a34a; font-size: 13px; padding: 6px 12px;";
              btnApprove.textContent = "Approve";
              btnApprove.addEventListener("click", () => handleReturnDecision("APPROVE", req.id));

              const btnReject = document.createElement("button");
              btnReject.type = "button";
              btnReject.className = "ios-btn ios-btn-danger";
              btnReject.style.cssText = "font-size: 13px; padding: 6px 12px;";
              btnReject.textContent = "Reject";
              btnReject.addEventListener("click", () => handleReturnDecision("REJECT", req.id));

              actionRow.append(btnApprove, btnReject);
              card.appendChild(actionRow);
            }

            elements.returnRequestsList.appendChild(card);
          });
        } else {
          if (elements.returnSingleRequestDetails) elements.returnSingleRequestDetails.hidden = false;
          if (elements.returnRequestsList) elements.returnRequestsList.replaceChildren();
        }
      } else {
        elements.returnStatusCard.hidden = true;
      }
    }
  } catch (_) {}
}

async function handleReturnDecision(action, reqId) {
  const targetReqId = reqId || (activeReturnRequest && activeReturnRequest.id);
  if (!targetReqId) return;
  const notes = (elements.decisionNotesInput && elements.decisionNotesInput.value || "").trim();
  const restock = elements.decisionRestockCheckbox ? elements.decisionRestockCheckbox.checked : false;

  elements.statusMsg.hidden = false;
  elements.statusMsg.textContent = "Submitting decision...";
  elements.errorMsg.hidden = true;

  try {
    const res = await request(`/api/v1/return-requests/${encodeURIComponent(targetReqId)}/decision`, {
      method: "POST",
      body: JSON.stringify({
        action,
        decision_notes: notes || null,
        is_restockable: action === "APPROVE" ? restock : false,
      }),
    });
    if (res && res.data) {
      elements.statusMsg.textContent = action === "APPROVE"
        ? "Return request approved. Payment refunded and inventory updated."
        : "Return request rejected. Order returned to completion.";
      loadOrder();
      setTimeout(() => { elements.statusMsg.hidden = true; }, 4000);
    }
  } catch (err) {
    elements.statusMsg.hidden = true;
    elements.errorMsg.hidden = false;
    elements.errorMsg.textContent = err.message;
  }
}

if (elements.btnApproveReturn) {
  elements.btnApproveReturn.addEventListener("click", () => handleReturnDecision("APPROVE"));
}
if (elements.btnRejectReturn) {
  elements.btnRejectReturn.addEventListener("click", () => handleReturnDecision("REJECT"));
}
