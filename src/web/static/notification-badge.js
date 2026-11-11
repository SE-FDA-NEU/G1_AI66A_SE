"use strict";

(() => {
  const links = [...document.querySelectorAll('a[href="/notifications"]')];
  if (!links.length) return;
  const badges = links.map(link => {
    link.classList.add("notification-link");
    const icon = document.createElement("span");
    icon.className = "notification-icon";
    icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>';
    const badge = document.createElement("span");
    badge.className = "notification-badge";
    badge.hidden = true;
    badge.setAttribute("aria-hidden", "true");
    icon.append(badge);
    link.prepend(icon);
    return badge;
  });
  const announcement = document.createElement("span");
  announcement.className = "notification-announcement";
  announcement.setAttribute("role", "status");
  announcement.setAttribute("aria-live", "polite");
  links[0].after(announcement);
  let revision = 0;
  let observedToken = null;
  let controller = null;

  function token() {
    return localStorage.getItem("access_token") || localStorage.getItem("token")
      || sessionStorage.getItem("access_token");
  }

  function render(count, unavailable = false) {
    const description = unavailable ? "Notifications, unread count unavailable"
      : count > 0 ? `Notifications, ${count} unread` : "Notifications";
    links.forEach((link, index) => {
      link.setAttribute("aria-label", description);
      link.title = unavailable ? "Open notifications to retry loading unread messages." : description;
      badges[index].hidden = !(count > 0);
      badges[index].textContent = count > 99 ? "99+" : String(count || "");
    });
    announcement.textContent = count > 0 ? `${count} unread notifications.` : "";
  }

  async function refresh() {
    const requestId = ++revision;
    controller?.abort();
    const currentToken = token();
    if (currentToken !== observedToken || !currentToken) render(0);
    observedToken = currentToken;
    if (!currentToken) return;
    const active = new AbortController();
    controller = active;
    const timer = setTimeout(() => active.abort(), 15000);
    const isCurrent = () => requestId === revision && currentToken === token();
    try {
      const response = await fetch("/api/v1/notifications/unread-count", {
        headers: {Accept: "application/json", Authorization: `Bearer ${currentToken}`},
        signal: active.signal,
      });
      const payload = await response.json().catch(() => null);
      if (!isCurrent()) return;
      if (!response.ok || !Number.isSafeInteger(payload?.unread_count) || payload.unread_count < 0) {
        render(0, response.status !== 401);
        return;
      }
      render(payload.unread_count);
    } catch {
      if (isCurrent()) render(0, true);
    } finally {
      clearTimeout(timer);
    }
  }

  window.addEventListener("notifications:changed", refresh);
  window.addEventListener("storage", event => {
    if ([null, "access_token", "token", "notifications:read"].includes(event.key)) refresh();
  });
  window.addEventListener("focus", refresh);
  window.addEventListener("pageshow", event => { if (event.persisted) refresh(); });
  // Same-tab logout does not emit a storage event; button handlers run before this listener.
  window.addEventListener("click", () => { if (token() !== observedToken) refresh(); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  refresh();
})();
