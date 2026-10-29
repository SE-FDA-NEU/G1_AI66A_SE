"use strict";

(() => {
  const REQUEST_TIMEOUT_MS = 15000;
  const DEFAULT_RANGE_DAYS = 30;
  const GROUPS = ["day", "month"];
  const RANKING_LIMITS = ["5", "10", "20"];
  const get = id => document.getElementById(id);
  const token = () => localStorage.getItem("access_token") || localStorage.getItem("token");
  const labels = {
    gross_order_value: "Gross order value",
    completed_revenue: "Completed revenue",
    pending_escrow_revenue: "Pending escrow revenue",
    cancellation_rate: "Cancellation rate",
  };
  const money = new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 0});
  const rate = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
  const format = (value, key) => value == null ? "Not available"
    : key === "cancellation_rate" ? `${rate.format(value)}%` : `${money.format(value)} VND`;
  const status = message => { get("analytics-status").textContent = message; };
  const isoDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
    && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  const nonnegativeInteger = value => Number.isSafeInteger(value) && value >= 0;
  let revision = 0, controller, report, failedFilters, sellerToken;
  let openRanking = window.location.pathname === "/seller/analytics/products";
  if (openRanking) {
    get("analytics-nav-summary").removeAttribute("aria-current");
    get("analytics-nav-ranking").setAttribute("aria-current", "page");
  }

  function clearReport() {
    report = null;
    get("analytics-report").hidden = true;
    get("analytics-chart").replaceChildren();
    get("analytics-values-body").replaceChildren();
    get("analytics-ranking-body").replaceChildren();
    for (const key of Object.keys(labels)) get(`metric-${key}`).textContent = "Not available";
  }

  function stop() {
    revision++;
    controller?.abort();
    clearReport();
  }

  function showError(message, retry = true) {
    clearReport();
    get("analytics-error-message").textContent = message;
    get("analytics-error").hidden = false;
    get("analytics-retry").hidden = !retry;
    status("Analytics could not be displayed.");
  }

  function login() {
    stop();
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    window.location.replace(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
  }

  // The deadline covers response-body parsing too, not just receipt of headers.
  async function request(url, accessToken, signal) {
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("The request timed out. Select Retry analytics.")), REQUEST_TIMEOUT_MS);
    });
    try {
      return await Promise.race([deadline, (async () => {
        const response = await fetch(url, {
          headers: {Accept: "application/json", Authorization: `Bearer ${accessToken}`}, signal,
        });
        if (response.status === 401) {
          if (token() === accessToken && !signal.aborted) login();
          throw new Error("Your session expired. Log in again.");
        }
        if (response.status === 403) throw new Error("Only active seller accounts can view analytics.");
        if (!response.ok) throw new Error("The server could not load analytics. Select Retry analytics.");
        return response.json();
      })()]);
    } catch (error) {
      if (error instanceof TypeError) throw new Error("Check your connection, then select Retry analytics.");
      if (error instanceof SyntaxError) throw new Error("The analytics response was incomplete. Select Retry analytics.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  function readFilters() {
    let firstInvalid;
    const values = Object.fromEntries(["from", "to", "group", "limit"].map(key => {
      const input = get(`analytics-${key}`), error = get(`analytics-${key}-error`);
      input.removeAttribute("aria-invalid"); error.hidden = true; error.textContent = "";
      return [key, input.value];
    }));
    const invalid = (key, message) => {
      const input = get(`analytics-${key}`), error = get(`analytics-${key}-error`);
      input.setAttribute("aria-invalid", "true"); error.textContent = message; error.hidden = false;
      firstInvalid ||= input;
    };
    for (const key of ["from", "to"]) if (!isoDate(values[key])) invalid(key, "Enter a valid date.");
    if (isoDate(values.from) && isoDate(values.to) && values.from > values.to) invalid("to", "To must be on or after From.");
    if (!GROUPS.includes(values.group)) invalid("group", "Choose Day or Month.");
    if (!RANKING_LIMITS.includes(values.limit)) invalid("limit", "Choose Top 5, Top 10 or Top 20.");
    if (firstInvalid) {
      stop(); get("analytics-error").hidden = true; failedFilters = null;
      status("Check the highlighted filters, then select Apply filters."); firstInvalid.focus(); return null;
    }
    return Object.freeze(values);
  }

  function validateReport(summary, ranking, filters) {
    const bad = () => { throw new Error("The analytics response was incomplete. Select Retry analytics."); };
    const period = filters.group === "day" ? "daily" : "monthly";
    if (!summary?.meta || !ranking?.meta || !Array.isArray(summary.data) || !Array.isArray(ranking.data)) bad();
    for (const payload of [summary, ranking]) {
      if (payload.meta.from !== filters.from || payload.meta.to !== filters.to) bad();
    }
    if (summary.meta.period !== period || ranking.meta.sort_by !== "units") bad();
    const metricValid = (value, key) => key === "cancellation_rate"
      ? typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
      : nonnegativeInteger(value);
    for (const row of [summary.meta, ...summary.data]) {
      if (!row || typeof row !== "object") bad();
      for (const key of Object.keys(labels)) if (row[key] != null && !metricValid(row[key], key)) bad();
    }
    if (summary.meta.completed_revenue == null && !nonnegativeInteger(summary.meta.total_revenue)) bad();
    const seen = new Set();
    for (const row of summary.data) {
      if (typeof row.period !== "string" || !(period === "daily" ? isoDate(row.period) : /^\d{4}-(0[1-9]|1[0-2])$/.test(row.period))
        || seen.has(row.period) || (row.completed_revenue == null && !nonnegativeInteger(row.revenue))) bad();
      const start = period === "daily" ? filters.from : filters.from.slice(0, 7);
      const end = period === "daily" ? filters.to : filters.to.slice(0, 7);
      if (row.period < start || row.period > end) bad();
      seen.add(row.period);
    }
    for (const row of ranking.data) {
      if (!row || !Number.isSafeInteger(row.product_id) || row.product_id <= 0
        || typeof row.product_name !== "string" || typeof row.product_code !== "string"
        || !nonnegativeInteger(row.units_sold) || !nonnegativeInteger(row.revenue)) bad();
    }
    return {summary, ranking, filters, legacy: summary.meta.completed_revenue == null};
  }

  function appendRow(body, values) {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell);
    }
    body.append(row);
  }

  function drawChart() {
    if (!report) return;
    const key = get("analytics-chart-metric").value;
    if (!Object.hasOwn(labels, key)) return;
    const {summary, legacy} = report;
    const label = legacy && key === "completed_revenue" ? "Completed-sales revenue (legacy)" : labels[key];
    const points = summary.data.map(row => ({label: row.period,
      value: legacy && key === "completed_revenue" ? row.revenue : row[key]}))
      .sort((a, b) => a.label.localeCompare(b.label));
    const unavailable = points.some(point => point.value == null) || summary.meta[key] == null && !(legacy && key === "completed_revenue");
    const chart = get("analytics-chart"), empty = get("analytics-chart-empty"), body = get("analytics-values-body");
    chart.replaceChildren(); body.replaceChildren();
    get("analytics-chart-description").textContent = `${label}. UTC periods; ${legacy && key === "completed_revenue" ? "filtered by completion date" : "financial metrics filtered by order creation date"}.`;
    get("analytics-value-heading").textContent = label;
    get("analytics-values-caption").textContent = `${label} by ${report.filters.group}, ${report.filters.from} to ${report.filters.to} (inclusive, UTC)`;
    get("analytics-values").hidden = unavailable || !points.length;
    if (!unavailable) for (const point of points) appendRow(body, [point.label, format(point.value, key)]);
    empty.hidden = !unavailable && points.length > 0 && points.some(point => point.value > 0);
    empty.textContent = unavailable ? "This metric is not available in the current report. Select another metric."
      : "No non-zero values in this range. Try a wider range or another metric; exact returned values are available below.";
    chart.hidden = !empty.hidden;
    if (!chart.hidden) window.SellerAnalyticsChart.render(chart, {points, label, unit: key === "cancellation_rate" ? "%" : "VND"});
  }

  function render() {
    const {summary, ranking, filters, legacy} = report;
    const missing = Object.keys(labels).some(key => summary.meta[key] == null);
    get("analytics-applied-range").textContent = `${filters.from} to ${filters.to} (inclusive, UTC) | Group: ${filters.group} | Top ${filters.limit} products`;
    get("analytics-date-basis").textContent = legacy
      ? "Legacy completed-sales revenue and product rankings use completion dates. Available financial metrics use order creation dates."
      : "Financial metrics use order creation dates. Completed-product rankings use completion dates.";
    get("completed-revenue-label").textContent = legacy ? "Completed-sales revenue (legacy)" : labels.completed_revenue;
    get("completed-revenue-description").textContent = legacy
      ? "Completed item value, filtered by completion date."
      : "Completed order value, filtered by order creation date.";
    get("analytics-compatibility").hidden = !missing;
    get("analytics-compatibility").textContent = "Some financial metrics are not available from the current API. Legacy completed-sales revenue uses completion dates and item prices; it is not the new creation-date financial metric. Missing values are not zero.";
    for (const key of Object.keys(labels)) {
      const value = legacy && key === "completed_revenue" ? summary.meta.total_revenue : summary.meta[key];
      get(`metric-${key}`).textContent = format(value, key);
    }
    const rows = [...ranking.data].sort((a, b) => b.units_sold - a.units_sold || a.product_id - b.product_id);
    get("analytics-ranking-empty").hidden = rows.length !== 0;
    get("analytics-ranking-table").hidden = rows.length === 0;
    get("analytics-ranking-caption").textContent = `Top ${filters.limit} products by units sold, ${filters.from} to ${filters.to} (inclusive, UTC)`;
    const body = get("analytics-ranking-body"); body.replaceChildren();
    rows.forEach((row, index) => appendRow(body, [index + 1, `${row.product_name} (${row.product_code})`,
      money.format(row.units_sold), format(row.revenue, "completed_revenue")]));
    drawChart(); get("analytics-report").hidden = false;
    status("Analytics loaded. Change filters and select Apply filters to update the report.");
    if (openRanking) {
      openRanking = false;
      get("best-sellers-title").focus();
      get("best-sellers-title").scrollIntoView({block: "start"});
    }
  }

  async function load(filters) {
    stop(); const current = revision, accessToken = token();
    if (!accessToken) { login(); return; }
    if (sellerToken !== accessToken) { await initialize(); return; }
    const active = controller = new AbortController();
    failedFilters = filters; get("analytics-error").hidden = true; status("Loading analytics...");
    const period = filters.group === "day" ? "daily" : "monthly";
    // Send matching aliases while #142 rolls out, without changing the legacy API.
    const query = new URLSearchParams({from_date: filters.from, to_date: filters.to, group_by: filters.group,
      from: filters.from, to: filters.to, period});
    const best = new URLSearchParams({from: filters.from, to: filters.to, sort_by: "units", limit: filters.limit});
    try {
      const [summary, ranking] = await Promise.all([
        request(`/api/v1/seller/analytics?${query}`, accessToken, active.signal),
        request(`/api/v1/seller/analytics/best-sellers?${best}`, accessToken, active.signal),
      ]);
      if (current !== revision || token() !== accessToken) return;
      report = validateReport(summary, ranking, filters); render(); failedFilters = null;
    } catch (error) {
      if (current !== revision || token() !== accessToken) return;
      active.abort(); showError(error.message || "Check your connection, then select Retry analytics.");
    }
  }

  async function initialize() {
    stop(); sellerToken = null; failedFilters = null; get("analytics-error").hidden = true;
    const current = revision, accessToken = token();
    if (!accessToken) { login(); return; }
    const active = controller = new AbortController(); status("Checking seller access...");
    try {
      const user = await request("/api/v1/auth/me", accessToken, active.signal);
      if (current !== revision || token() !== accessToken) return;
      if (user?.role !== "seller" || user.status && user.status !== "ACTIVE") {
        showError("Only active seller accounts can view analytics.", false); return;
      }
      sellerToken = accessToken;
      const filters = readFilters(); if (filters) await load(filters);
    } catch (error) {
      if (current === revision && token() === accessToken) { active.abort(); showError(error.message); }
    }
  }

  const today = new Date(), start = new Date(today);
  start.setUTCDate(start.getUTCDate() - (DEFAULT_RANGE_DAYS - 1));
  get("analytics-from").value = start.toISOString().slice(0, 10);
  get("analytics-to").value = today.toISOString().slice(0, 10);
  get("analytics-filters").addEventListener("submit", event => {
    event.preventDefault(); const filters = readFilters(); if (filters) void load(filters);
  });
  get("analytics-chart-metric").addEventListener("change", drawChart);
  get("analytics-retry").addEventListener("click", () => {
    if (failedFilters && sellerToken === token()) void load(failedFilters); else void initialize();
  });
  get("analytics-logout").addEventListener("click", login);
  window.addEventListener("storage", event => {
    if (event.key === "access_token" || event.key === "token" || event.key === null) void initialize();
  });
  window.addEventListener("pagehide", stop);
  // Revalidate authentication when a private page returns from the back/forward cache.
  window.addEventListener("pageshow", event => { if (event.persisted) void initialize(); });
  void initialize();
})();
