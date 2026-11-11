"use strict";

const status = document.getElementById("notifications-status");
const error = document.getElementById("notifications-error");
const retry = document.getElementById("notifications-retry");
const list = document.getElementById("notifications-list");
const logout = document.getElementById("notifications-logout");
const markAll = document.getElementById("notifications-mark-all");
const sellerNavigation = [...document.querySelectorAll("[data-seller-nav]")];
let revision = 0;
let unreadCount = 0;
let mutation = null;
const NOTIFICATION_REQUEST_TIMEOUT = 15000;

async function notificationRequest(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NOTIFICATION_REQUEST_TIMEOUT);
  try {
    return await fetch(url, {...options, signal: controller.signal});
  } catch (cause) {
    throw new Error(cause?.name === "AbortError" ? "The request timed out. Please try again."
      : "We could not reach the server. Please try again.");
  } finally {
    clearTimeout(timer);
  }
}

function getStoredToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("token")
    || sessionStorage.getItem("access_token");
}

function isCurrent(token, requestId) {
  return token === getStoredToken() && requestId === revision;
}

function updateMarkAll() {
  markAll.disabled = Boolean(mutation) || unreadCount === 0;
}

async function configureNavigation(token, requestId) {
  sellerNavigation.forEach(link => { link.hidden = true; });
  try {
    const response = await notificationRequest("/api/v1/auth/me", {
      headers: {Accept: "application/json", Authorization: `Bearer ${token}`},
    });
    const user = response.ok ? await response.json() : null;
    if (isCurrent(token, requestId)) {
      sellerNavigation.forEach(link => { link.hidden = user?.role !== "seller"; });
    }
  } catch {
    // Keep seller controls hidden when identity cannot be verified.
  }
}

function tokenOrLogin() {
  const token = getStoredToken();
  if (token) return token;
  window.location.replace(`/login?return_to=${encodeURIComponent("/notifications")}`);
  return null;
}

function signalReadChange() {
  window.dispatchEvent(new Event("notifications:changed"));
  // Other tabs refresh their own count; no notification data or token is shared.
  try {
    localStorage.setItem("notifications:read", `${Date.now()}:${Math.random()}`);
  } catch {
    // A full browser store must not turn a committed read into a failed UI action.
  }
}

async function loadNotifications() {
  const requestId = ++revision;
  const token = tokenOrLogin();
  list.replaceChildren();
  unreadCount = 0;
  if (mutation?.token !== token) mutation = null;
  updateMarkAll();
  if (!token) return;
  status.hidden = false;
  status.textContent = "Loading notifications…";
  error.hidden = true;
  retry.hidden = true;
  await configureNavigation(token, requestId);
  if (!isCurrent(token, requestId)) return;
  try {
    const response = await notificationRequest("/api/v1/notifications", {
      headers: {Accept: "application/json", Authorization: `Bearer ${token}`},
    });
    const payload = await response.json().catch(() => null);
    if (!isCurrent(token, requestId)) return;
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("token");
      sessionStorage.removeItem("access_token");
      window.dispatchEvent(new Event("notifications:changed"));
      tokenOrLogin();
      return;
    }
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load notifications.");
    const notifications = Array.isArray(payload.data) ? payload.data : [];
    unreadCount = payload.unread_count;
    status.textContent = `${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}.`;
    list.replaceChildren(...notifications.map(item => createNotification(item, token, requestId)));
    updateMarkAll();
    if (notifications.length === 0) status.textContent = "You have no notifications.";
  } catch (cause) {
    if (!isCurrent(token, requestId)) return;
    status.hidden = true;
    showError(cause, "Unable to load notifications.");
    retry.hidden = false;
  }
}

function showError(cause, fallback) {
  error.textContent = cause instanceof Error ? cause.message : fallback;
  error.hidden = false;
}

async function readNotifications(path, method, token, requestId) {
  const response = await notificationRequest(path, {
    method, headers: {Accept: "application/json", Authorization: `Bearer ${token}`},
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error?.message || "Unable to update notification.");
  if (token !== getStoredToken()) return false;
  signalReadChange();
  // Another tab may have refreshed this list while this account's read was pending.
  if (requestId !== revision) {
    await loadNotifications();
    return false;
  }
  return true;
}

async function markRead(path, method, token, requestId, destination = null) {
  if (mutation || !isCurrent(token, requestId)) return;
  const operation = {token, requestId};
  mutation = operation;
  updateMarkAll();
  error.hidden = true;
  try {
    if (!await readNotifications(path, method, token, requestId)) return;
    if (destination) window.location.assign(destination);
    else await loadNotifications();
  } catch (cause) {
    if (isCurrent(token, requestId)) showError(cause, "Unable to update notifications.");
  } finally {
    if (mutation === operation) {
      mutation = null;
      updateMarkAll();
    }
  }
}

function createNotification(notification, token, requestId) {
  const item = document.createElement("li");
  item.className = `notification${notification.read_at ? "" : " notification--unread"}`;
  const message = document.createElement("p");
  message.textContent = notification.message;
  const date = document.createElement("time");
  date.dateTime = notification.created_at;
  date.textContent = new Date(notification.created_at).toLocaleString();
  const order = document.createElement("a");
  order.href = notification.target_path;
  order.textContent = "Open related page";
  item.append(message, date, order);
  if (notification.read_at) return item;
  const path = `/api/v1/notifications/${notification.id}/read`;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button";
  button.textContent = "Mark as read";
  button.addEventListener("click", async () => {
    button.disabled = true;
    await markRead(path, "PATCH", token, requestId);
    button.disabled = false;
  });
  order.addEventListener("click", event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    markRead(path, "PATCH", token, requestId, order.href);
  });
  item.append(button);
  return item;
}

markAll.addEventListener("click", () => {
  const token = tokenOrLogin();
  if (token) markRead("/api/v1/notifications/mark-all-read", "POST", token, revision);
});
retry.addEventListener("click", loadNotifications);
logout.addEventListener("click", () => {
  revision += 1;
  list.replaceChildren();
  localStorage.removeItem("access_token");
  localStorage.removeItem("token");
  sessionStorage.removeItem("access_token");
  window.dispatchEvent(new Event("notifications:changed"));
  window.location.replace("/login?return_to=%2Fnotifications");
});
window.addEventListener("storage", event => {
  if ([null, "access_token", "token", "notifications:read"].includes(event.key)) loadNotifications();
});
window.addEventListener("pageshow", event => { if (event.persisted) loadNotifications(); });
loadNotifications();
