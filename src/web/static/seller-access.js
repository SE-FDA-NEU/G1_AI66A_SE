"use strict";

// Seller pages are public browser shells, so reject a known non-seller before
// the page-specific script can render seller navigation or start seller calls.
(function redirectNonSeller() {
  const token = localStorage.getItem("access_token");
  if (!token) return;

  try {
    const encodedPayload = token.split(".")[1];
    if (!encodedPayload) return;
    const payload = JSON.parse(atob(encodedPayload.replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.role && payload.role !== "seller") {
      window.location.replace("/products");
    }
  } catch {
    // Page-specific code handles malformed or expired tokens.
  }
})();
