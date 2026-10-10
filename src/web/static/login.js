"use strict";

const form = document.getElementById("login-form");
const error = document.getElementById("login-error");

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
    window.location.assign("/products");
  } catch (reason) {
    error.textContent = reason instanceof Error ? reason.message : "Unable to log in.";
    error.hidden = false;
  }
});
