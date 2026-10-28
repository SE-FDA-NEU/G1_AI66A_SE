// Run with: node tests/verify_ui_rendering.mjs
// Verifies UI input heights (desktop 42px, mobile 44px), button hover colors,
// and saves responsive evidence screenshots for core screens.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

const PORT = 8145;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUTPUT_DIR = join(import.meta.dirname, "../docs/images/responsive");
await mkdir(OUTPUT_DIR, { recursive: true });

const CHROME_PATHS = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];

import { existsSync } from "node:fs";
const chromeExe = CHROME_PATHS.find(existsSync);
if (!chromeExe) {
  console.log("No Chrome/Edge executable found; skipping browser rendering verification.");
  process.exit(0);
}

// 1. Start test server on demo database
const tempDir = join(tmpdir(), `ui-render-test-${Date.now()}`);
await mkdir(tempDir, { recursive: true });
const dbPath = join(tempDir, "test.db");

const env = { ...process.env, DATABASE_URL: `sqlite:///${dbPath}`, DEBUG: "false" };

console.log("Setting up database and server...");
const py = process.platform === "win32" ? "python" : "python3";
const run = (cmd, args) => new Promise((resolve, reject) => {
  const p = spawn(cmd, args, { env, stdio: "ignore" });
  p.on("exit", code => code === 0 ? resolve() : reject(new Error(`${cmd} exited with ${code}`)));
});

await run(py, ["-m", "src.database"]);
await run(py, ["-m", "src.seed", "--demo"]);

const server = spawn(py, ["-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", String(PORT)], {
  env,
  stdio: "ignore",
});

// Wait for server health
for (let i = 0; i < 50; i++) {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    if (res.ok) break;
  } catch {
    await new Promise(r => setTimeout(r, 100));
  }
}

// 2. Launch headless Chrome with remote debugging
const chromeUserData = join(tempDir, "chrome-profile");
const chromePort = 9223;
const chrome = spawn(chromeExe, [
  "--headless=new",
  `--remote-debugging-port=${chromePort}`,
  `--user-data-dir=${chromeUserData}`,
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
], { stdio: "ignore" });

try {
  // Wait for Chrome remote debugging endpoint
  let pageTarget = null;
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${chromePort}/json/list`);
      if (res.ok) {
        const list = await res.json();
        pageTarget = list.find(t => t.type === "page") || list[0];
        if (pageTarget) break;
      }
    } catch {
      await new Promise(r => setTimeout(r, 100));
    }
  }

  assert.ok(pageTarget, "Chrome remote debugging page target must be available");

  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  let msgId = 1;
  const pending = new Map();
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const { resolve, reject } = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) reject(new Error(data.error.message));
      else resolve(data.result);
    }
  };

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = msgId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable");
  await send("Runtime.enable");

  // Obtain login token for buyer
  const authRes = await fetch(`${BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "user@example.com", password: "password" }),
  });
  const { access_token } = await authRes.json();
  assert.ok(access_token, "Must obtain test buyer access token");

  // Helper to set viewport
  async function setViewport(width, height, isMobile) {
    await send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: isMobile ? 2 : 1,
      mobile: isMobile,
    });
  }

  // Helper to navigate and wait
  async function navigate(path) {
    await send("Page.navigate", { url: `${BASE_URL}${path}` });
    await new Promise(r => setTimeout(r, 1500));
  }

  // Set auth token in localStorage on the domain
  await navigate("/login");
  await send("Runtime.evaluate", {
    expression: `localStorage.setItem("access_token", "${access_token}")`,
  });

  console.log("Checking desktop input sizing and button contrast...");
  // Check Desktop at 1280x800
  await setViewport(1280, 800, false);
  await navigate("/checkout");

  // Verify input sizing on checkout inputs (both explicitly typed and untyped fallback)
  const desktopInputMetrics = await send("Runtime.evaluate", {
    expression: `(() => {
      // Toggle address form open
      const addBtn = document.getElementById("add-address");
      if (addBtn) addBtn.click();
      const rec = document.getElementById("address-recipient_name");
      const phone = document.getElementById("address-phone_number");
      const csRec = window.getComputedStyle(rec);
      const csPhone = window.getComputedStyle(phone);
      return {
        recipientHeight: rec.getBoundingClientRect().height,
        phoneHeight: phone.getBoundingClientRect().height,
        recipientMinHeight: csRec.minHeight,
        phoneMinHeight: csPhone.minHeight,
        recipientBorderRadius: csRec.borderRadius,
        phoneBorderRadius: csPhone.borderRadius,
      };
    })()`,
    returnByValue: true,
  });

  const dMetrics = desktopInputMetrics.result.value;
  console.log("Desktop input metrics:", dMetrics);
  assert.ok(dMetrics.recipientHeight >= 42, `Recipient height must be >= 42px on desktop, got ${dMetrics.recipientHeight}`);
  assert.ok(dMetrics.phoneHeight >= 42, `Phone height must be >= 42px on desktop, got ${dMetrics.phoneHeight}`);
  assert.equal(dMetrics.recipientMinHeight, "42px");
  assert.equal(dMetrics.phoneMinHeight, "42px");
  assert.equal(dMetrics.recipientBorderRadius, dMetrics.phoneBorderRadius, "Corners should match phone input");

  // Verify button hover contrast in CSS rules
  const cssButtonCheck = await send("Runtime.evaluate", {
    expression: `(() => {
      let primaryHoverColor = null;
      let primaryHoverBg = null;
      let secondaryHoverColor = null;
      let dangerHoverColor = null;
      let dangerHoverBg = null;
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            const sel = rule.selectorText;
            if (!sel) continue;
            if (sel === "button:hover, .button:hover") {
              primaryHoverColor = rule.style.color;
              primaryHoverBg = rule.style.backgroundColor;
            } else if (sel.includes(".button--secondary:hover")) {
              secondaryHoverColor = rule.style.color;
            } else if (sel.includes(".button--danger:hover")) {
              dangerHoverColor = rule.style.color;
              dangerHoverBg = rule.style.backgroundColor;
            }
          }
        } catch {}
      }
      return { primaryHoverColor, primaryHoverBg, secondaryHoverColor, dangerHoverColor, dangerHoverBg };
    })()`,
    returnByValue: true,
  });

  const btnStyles = cssButtonCheck.result.value;
  console.log("Button hover styles:", btnStyles);
  assert.equal(btnStyles.primaryHoverColor, "rgb(255, 255, 255)", "Primary button hover color must be #ffffff (white)");
  assert.equal(btnStyles.primaryHoverBg, "var(--color-accent-hover)", "Primary button hover background must be --color-accent-hover");
  assert.equal(btnStyles.secondaryHoverColor, "var(--color-accent)", "Secondary button hover color must be --color-accent");
  assert.equal(btnStyles.dangerHoverColor, "rgb(255, 255, 255)", "Danger button hover color must be #ffffff");

  // Screenshot desktop checkout
  const scDesktopCheckout = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(OUTPUT_DIR, "desktop-checkout.png"), Buffer.from(scDesktopCheckout.data, "base64"));

  // Check Mobile at 390x844
  console.log("Checking mobile input sizing at 390px...");
  await setViewport(390, 844, true);
  await navigate("/checkout");

  const mobileInputMetrics = await send("Runtime.evaluate", {
    expression: `(() => {
      const addBtn = document.getElementById("add-address");
      if (addBtn) addBtn.click();
      const rec = document.getElementById("address-recipient_name");
      const csRec = window.getComputedStyle(rec);
      return {
        recipientHeight: rec.getBoundingClientRect().height,
        minHeight: csRec.minHeight,
        fontSize: csRec.fontSize,
      };
    })()`,
    returnByValue: true,
  });

  const mMetrics = mobileInputMetrics.result.value;
  console.log("Mobile input metrics:", mMetrics);
  assert.ok(mMetrics.recipientHeight >= 44, `Mobile input height must be >= 44px, got ${mMetrics.recipientHeight}`);
  assert.equal(mMetrics.minHeight, "44px", "Mobile input min-height must be 44px");
  assert.equal(mMetrics.fontSize, "16px", "Mobile input font size must be 16px to prevent iOS auto-zoom");

  const scMobileCheckout = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(OUTPUT_DIR, "mobile-checkout.png"), Buffer.from(scMobileCheckout.data, "base64"));

  // Capture core screens: catalog, product-detail, cart, login (desktop & mobile)
  const screens = [
    { name: "catalog", path: "/products" },
    { name: "cart", path: "/cart" },
    { name: "login", path: "/login" },
  ];

  for (const screen of screens) {
    // Desktop
    await setViewport(1280, 800, false);
    await navigate(screen.path);
    const dSc = await send("Page.captureScreenshot", { format: "png" });
    await writeFile(join(OUTPUT_DIR, `desktop-${screen.name}.png`), Buffer.from(dSc.data, "base64"));

    // Mobile
    await setViewport(390, 844, true);
    await navigate(screen.path);
    const mSc = await send("Page.captureScreenshot", { format: "png" });
    await writeFile(join(OUTPUT_DIR, `mobile-${screen.name}.png`), Buffer.from(mSc.data, "base64"));
  }

  console.log("All headless browser checks and responsive evidence screenshots passed!");

  ws.close();
} finally {
  const killTree = (pid) => {
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/F", "/T", "/PID", String(pid)], { stdio: "ignore" });
      }
    } catch {}
  };
  if (chrome.pid) killTree(chrome.pid);
  if (server.pid) killTree(server.pid);
  chrome.kill();
  server.kill();
  await new Promise(r => setTimeout(r, 500));
  try {
    await rm(tempDir, { recursive: true, force: true });
  } catch {}
}
