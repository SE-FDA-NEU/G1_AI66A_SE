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
  assert.ok(
    btnStyles.primaryHoverColor === "rgb(255, 255, 255)" || btnStyles.primaryHoverColor === "var(--color-on-accent)",
    "Primary button hover color must be white or var(--color-on-accent)"
  );
  assert.equal(btnStyles.primaryHoverBg, "var(--color-accent-hover)", "Primary button hover background must be --color-accent-hover");
  assert.equal(btnStyles.secondaryHoverColor, "var(--color-accent)", "Secondary button hover color must be --color-accent");
  assert.ok(
    btnStyles.dangerHoverColor === "rgb(255, 255, 255)" || btnStyles.dangerHoverColor === "var(--color-on-accent)",
    "Danger button hover color must be white or var(--color-on-accent)"
  );

  // Verify desktop control sizing for .input, .select, and .textarea aliases
  console.log("Checking desktop control aliases (.input, .select, .textarea) sizing...");
  const desktopControlAliases = await send("Runtime.evaluate", {
    expression: `(() => {
      const container = document.createElement("div");
      container.innerHTML = \`
        <input class="input" id="alias-input" value="test" />
        <select class="select" id="alias-select"><option>1</option></select>
        <textarea class="textarea" id="alias-textarea">sample</textarea>
      \`;
      document.body.appendChild(container);
      const inEl = document.getElementById("alias-input");
      const selEl = document.getElementById("alias-select");
      const taEl = document.getElementById("alias-textarea");
      const res = {
        inputMinHeight: window.getComputedStyle(inEl).minHeight,
        selectMinHeight: window.getComputedStyle(selEl).minHeight,
        textareaMinHeight: window.getComputedStyle(taEl).minHeight,
      };
      container.remove();
      return res;
    })()`,
    returnByValue: true,
  });
  const dAliases = desktopControlAliases.result.value;
  console.log("Desktop control alias metrics:", dAliases);
  assert.equal(dAliases.inputMinHeight, "42px", ".input min-height must be 42px on desktop");
  assert.equal(dAliases.selectMinHeight, "42px", ".select min-height must be 42px on desktop");
  assert.equal(dAliases.textareaMinHeight, "96px", ".textarea min-height must preserve 96px on desktop (not collapse to 42px)");

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

  // Verify mobile control aliases (.input, .select, .textarea)
  console.log("Checking mobile control aliases (.input, .select, .textarea) sizing...");
  const mobileControlAliases = await send("Runtime.evaluate", {
    expression: `(() => {
      const container = document.createElement("div");
      container.innerHTML = \`
        <input class="input" id="alias-m-input" value="test" />
        <select class="select" id="alias-m-select"><option>1</option></select>
        <textarea class="textarea" id="alias-m-textarea">sample</textarea>
      \`;
      document.body.appendChild(container);
      const inEl = document.getElementById("alias-m-input");
      const selEl = document.getElementById("alias-m-select");
      const taEl = document.getElementById("alias-m-textarea");
      const res = {
        inputMinHeight: window.getComputedStyle(inEl).minHeight,
        selectMinHeight: window.getComputedStyle(selEl).minHeight,
        textareaMinHeight: window.getComputedStyle(taEl).minHeight,
      };
      container.remove();
      return res;
    })()`,
    returnByValue: true,
  });
  const mAliases = mobileControlAliases.result.value;
  console.log("Mobile control alias metrics:", mAliases);
  assert.equal(mAliases.inputMinHeight, "44px", ".input min-height must be 44px on mobile");
  assert.equal(mAliases.selectMinHeight, "44px", ".select min-height must be 44px on mobile (overriding 42px)");
  assert.equal(mAliases.textareaMinHeight, "96px", ".textarea min-height must preserve 96px on mobile");

  const scMobileCheckout = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(OUTPUT_DIR, "mobile-checkout.png"), Buffer.from(scMobileCheckout.data, "base64"));

  // Verify semantic badge variants on the order tracker page (order.css + base.css cascade)
  console.log("Checking semantic badge variants cascade on order tracking page...");
  await setViewport(1280, 800, false);
  await navigate("/order/1");

  const badgeCascadeStyles = await send("Runtime.evaluate", {
    expression: `(() => {
      const container = document.createElement("div");
      container.innerHTML = \`
        <span class="badge" id="b-test-default">Default</span>
        <span class="badge badge--success" id="b-test-success">Success</span>
        <span class="badge badge--danger" id="b-test-danger">Danger</span>
        <span class="badge badge--warning" id="b-test-warning">Warning</span>
        <span class="badge badge--info" id="b-test-info">Info</span>
      \`;
      document.body.appendChild(container);

      const def = window.getComputedStyle(document.getElementById("b-test-default"));
      const suc = window.getComputedStyle(document.getElementById("b-test-success"));
      const dan = window.getComputedStyle(document.getElementById("b-test-danger"));
      const war = window.getComputedStyle(document.getElementById("b-test-warning"));
      const inf = window.getComputedStyle(document.getElementById("b-test-info"));

      const res = {
        defaultBg: def.backgroundColor,
        defaultColor: def.color,
        successBg: suc.backgroundColor,
        successColor: suc.color,
        dangerBg: dan.backgroundColor,
        dangerColor: dan.color,
        warningBg: war.backgroundColor,
        warningColor: war.color,
        infoBg: inf.backgroundColor,
        infoColor: inf.color,
      };
      container.remove();
      return res;
    })()`,
    returnByValue: true,
  });

  const bStyles = badgeCascadeStyles.result.value;
  console.log("Order page badge cascade computed styles:", bStyles);
  // Default unstyled .badge on order page gets neutral order.css styling
  assert.equal(bStyles.defaultBg, "rgb(241, 245, 249)", "Default badge gets neutral #f1f5f9 background");
  assert.equal(bStyles.defaultColor, "rgb(71, 85, 105)", "Default badge gets neutral #475569 color");

  // Semantic variants must NOT be overridden by the order stylesheet's neutral colors
  assert.notEqual(bStyles.successBg, "rgb(241, 245, 249)", "badge--success background must not be overridden by neutral order.css");
  assert.notEqual(bStyles.successColor, "rgb(71, 85, 105)", "badge--success color must not be overridden by neutral order.css");
  assert.equal(bStyles.successBg, "rgb(236, 253, 245)", "badge--success must have var(--color-success-bg) (#ecfdf5)");
  assert.equal(bStyles.successColor, "rgb(6, 95, 70)", "badge--success must have var(--color-success-text) (#065f46)");

  assert.notEqual(bStyles.dangerBg, "rgb(241, 245, 249)", "badge--danger background must not be overridden by neutral order.css");
  assert.notEqual(bStyles.dangerColor, "rgb(71, 85, 105)", "badge--danger color must not be overridden by neutral order.css");
  assert.equal(bStyles.dangerBg, "rgb(254, 242, 242)", "badge--danger must have var(--color-danger-bg) (#fef2f2)");
  assert.equal(bStyles.dangerColor, "rgb(153, 27, 27)", "badge--danger must have var(--color-danger-text) (#991b1b)");

  assert.equal(bStyles.warningBg, "rgb(255, 251, 235)", "badge--warning must have var(--color-warning-bg) (#fffbeb)");
  assert.equal(bStyles.warningColor, "rgb(146, 64, 14)", "badge--warning must have var(--color-warning-text) (#92400e)");
  assert.equal(bStyles.infoBg, "rgb(240, 249, 255)", "badge--info must have var(--color-info-bg) (#f0f9ff)");
  assert.equal(bStyles.infoColor, "rgb(3, 105, 161)", "badge--info must have var(--color-info-text) (#0369a1)");

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
