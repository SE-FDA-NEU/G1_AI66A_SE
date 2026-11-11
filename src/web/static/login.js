"use strict";

const form = document.getElementById("login-form");
const error = document.getElementById("login-error");
const googleStatus = document.getElementById("google-signin-status");

async function handleGoogleCredential(result) {
  googleStatus.textContent = "Signing in…";
  try {
    const response = await fetch("/api/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ credential: result.credential }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "Google sign-in failed. Try again.");
    localStorage.setItem("access_token", payload.access_token);
    window.location.assign(getReturnDestination(payload.user?.role));
  } catch (reason) {
    googleStatus.textContent = reason instanceof TypeError
      ? "Cannot reach the server. Check your connection and try again."
      : reason instanceof Error ? reason.message : "Google sign-in failed. Try again.";
  }
}

async function setupGoogleSignIn() {
  try {
    const response = await fetch("/api/v1/auth/google/config");
    if (!response.ok) throw new Error();
    const { client_id: clientId } = await response.json();
    if (!clientId) {
      googleStatus.textContent = "Google sign-in is not configured.";
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      google.accounts.id.initialize({ client_id: clientId, callback: handleGoogleCredential });
      const googleButton = document.getElementById("google-signin-button");
      google.accounts.id.renderButton(googleButton, {
        theme: "outline", size: "large", text: "continue_with",
        width: Math.min(400, Math.floor(googleButton.getBoundingClientRect().width)),
      });
      googleStatus.textContent = "";
    };
    script.onerror = () => { googleStatus.textContent = "Google sign-in is unavailable. Reload to try again."; };
    document.head.appendChild(script);
  } catch {
    googleStatus.textContent = "Google sign-in is unavailable. Reload to try again.";
  }
}

setupGoogleSignIn();

function getReturnDestination(role) {
  const params = new URLSearchParams(window.location.search);
  const candidate = params.get("return_to") || params.get("redirect") || params.get("next");
  if (
    candidate &&
    candidate.startsWith("/") &&
    !candidate.startsWith("//") &&
    !candidate.includes("\\")
  ) {
    return candidate;
  }
  if (role === "admin") {
    return "/admin";
  }
  return "/products";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  const body = {
    email: form.elements.email.value,
    password: form.elements.password.value,
  };
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Unable to log in.");
    }
    localStorage.setItem("access_token", payload.access_token);
    window.location.assign(getReturnDestination(payload.user?.role));
  } catch (reason) {
    error.textContent = reason instanceof TypeError
      ? "Cannot reach the server. Check your connection and try again."
      : reason instanceof Error ? reason.message : "Unable to log in. Please try again.";
    error.hidden = false;
  }
});
