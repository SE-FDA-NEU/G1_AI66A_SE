"use strict";

const status = document.getElementById("notifications-status");
const error = document.getElementById("notifications-error");
const retry = document.getElementById("notifications-retry");
const list = document.getElementById("notifications-list");
const logout = document.getElementById("notifications-logout");

function tokenOrLogin() {
  const token = localStorage.getItem("access_token");
  if (token) return token;
  window.location.replace(`/login?return_to=${encodeURIComponent("/notifications")}`);
  return null;
}

async function loadNotifications() {
  const token = tokenOrLogin();
  if (!token) return;
  status.hidden = false;
  status.textContent = "Loading notifications…";
  error.hidden = true;
  retry.hidden = true;
  try {
    const response = await fetch("/api/v1/notifications", {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      tokenOrLogin();
      return;
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || "Unable to load notifications.");
    const notifications = Array.isArray(payload.data) ? payload.data : [];
    status.textContent = `${payload.unread_count} unread notification${payload.unread_count === 1 ? "" : "s"}.`;
    list.replaceChildren(...notifications.map(createNotification));
    if (notifications.length === 0) status.textContent = "You have no notifications.";
  } catch (cause) {
    status.hidden = true;
    error.textContent = cause instanceof Error ? cause.message : "Unable to load notifications.";
    error.hidden = false;
    retry.hidden = false;
  }
}

function createNotification(notification) {
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
  if (!notification.read_at) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.textContent = "Mark as read";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const response = await fetch(`/api/v1/notifications/${notification.id}/read`, {
          method: "PATCH",
          headers: { Accept: "application/json", Authorization: `Bearer ${tokenOrLogin()}` },
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) throw new Error(payload?.error?.message || "Unable to update notification.");
        await loadNotifications();
      } catch (cause) {
        error.textContent = cause instanceof Error ? cause.message : "Unable to update notification.";
        error.hidden = false;
        button.disabled = false;
      }
    });
    item.append(button);
  }
  return item;
}

retry.addEventListener("click", loadNotifications);
logout.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  window.location.replace("/login?return_to=%2Fnotifications");
});
loadNotifications();
