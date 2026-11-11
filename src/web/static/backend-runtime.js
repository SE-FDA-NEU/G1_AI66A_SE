/* Route only application API requests to the configured backend. */
(() => {
  const configured = window.MARKETPLACE_API_ORIGIN || "";
  const origin = configured ? new URL(configured).origin : "";
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    if (typeof input === "string" && input.startsWith("/api/v1/")) {
      input = origin + input;
    }
    return originalFetch(input, options);
  };
  window.marketplaceImageUrl = (value) => {
    if (!value || !origin) return value;
    if (value.startsWith("/api/v1/") || value.startsWith("/static/uploads/products/")) {
      return origin + value;
    }
    return value;
  };
})();
