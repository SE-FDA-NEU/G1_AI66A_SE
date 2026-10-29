/* Buyer return-request UI (#139). The server owns eligibility and all mutations. */
"use strict";

window.BuyerReturns = (() => {
  const TIMEOUT_MS = 15000;
  const limits = {reason: [3, 500], evidence: [3, 2000]};
  const dateLabel = value => {
    // SQLite return timestamps are UTC even when the existing DTO omits the offset.
    const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
  };

  function create({getToken, onSubmitted = () => {}, onPending = () => {},
    document: doc = window.document, fetch: fetcher = window.fetch.bind(window)}) {
    const node = id => doc.getElementById(id);
    const ui = {
      panel: node("buyer-return-form-card"), form: node("buyer-return-form"),
      action: node("return-request-action"), cancel: node("return-cancel"),
      submit: node("btn-submit-return"), status: node("return-load-status"),
      error: node("return-load-error"), retry: node("return-retry"),
      feedback: node("return-feedback"), formError: node("return-form-error"),
      target: node("return-seller-order-select"),
      reason: node("return-reason-input"), evidence: node("return-evidence-input"),
      history: node("return-status-card"), list: node("return-requests-list"),
    };
    let current = null;
    const live = ctx => current === ctx && getToken() === ctx.token;
    const say = (element, message = "") => {
      element.textContent = message;
      element.hidden = !message;
    };
    function fieldError(field, message = "") {
      say(node(`return-${field}-error`), message);
      (field === "target" ? ui.target : ui[field]).setAttribute("aria-invalid", String(!!message));
    }
    function controls(ctx) {
      const disabled = !ctx.ready || ctx.pending;
      for (const element of [ui.target, ui.reason, ui.evidence, ui.submit, ui.cancel]) {
        element.disabled = disabled;
      }
      ui.action.disabled = disabled;
      ui.submit.textContent = ctx.pending ? "Submitting request…" : "Submit Return & Refund Request";
      ui.form.setAttribute("aria-busy", String(ctx.pending));
      onPending(ctx.pending);
    }
    function hide() {
      ui.panel.hidden = true;
      ui.history.hidden = true;
    }
    function reset() {
      current = null;
      hide();
      ui.form.hidden = true;
      ui.reason.value = ui.evidence.value = ui.target.value = "";
      ui.list.replaceChildren();
      for (const field of ["reason", "evidence", "target"]) fieldError(field);
      for (const element of [ui.feedback, ui.error, ui.formError, ui.status]) say(element);
      onPending(false);
    }
    function unauthenticated(ctx) {
      if (!live(ctx)) return;
      localStorage.removeItem("access_token");
      localStorage.removeItem("token");
      reset();
      window.location.replace(`/login?return_to=${encodeURIComponent(window.location.pathname)}`);
    }
    async function api(ctx, path, options = {}) {
      const controller = new AbortController();
      let timer;
      try {
        return await Promise.race([
          (async () => {
            const response = await fetcher(path, {...options, signal: controller.signal,
              headers: {Accept: "application/json", "Content-Type": "application/json",
                Authorization: `Bearer ${ctx.token}`}});
            const payload = await response.json();
            if (!response.ok) {
              throw Object.assign(new Error(payload?.error?.message || "Please try again."),
                {status: response.status, fields: payload?.error?.fields});
            }
            return payload;
          })(),
          new Promise((_, reject) => {
            timer = setTimeout(() => {
              controller.abort();
              reject(new Error("The request timed out. Check your connection and select Retry."));
            }, TIMEOUT_MS);
          }),
        ]);
      } finally { clearTimeout(timer); }
    }
    function eligible(ctx) {
      const pending = new Set(ctx.requests.filter(row => row.status === "PENDING")
        .map(row => row.seller_order_id));
      return (ctx.order.sub_orders || []).filter(row => row.status === "DELIVERED" &&
        !pending.has(row.id) && !ctx.recorded.has(row.id));
    }
    function draft(ctx) {
      if (ctx.target) ctx.drafts.set(ctx.target, {reason: ui.reason.value, evidence: ui.evidence.value});
    }
    function selectTarget(ctx, target) {
      ctx.target = target;
      ui.target.value = String(target);
      const saved = ctx.drafts.get(target) || {reason: "", evidence: ""};
      ui.reason.value = saved.reason;
      ui.evidence.value = saved.evidence;
      for (const field of ["reason", "evidence", "target"]) fieldError(field);
      say(ui.formError);
    }
    function render(ctx) {
      if (!live(ctx)) return;
      ui.panel.hidden = false;
      node("return-single-request-details").hidden = true;
      node("reviewer-decision-panel").hidden = true;
      ui.list.replaceChildren();
      ui.history.hidden = ctx.requests.length === 0;
      const count = node("badge-return-status");
      count.textContent = String(ctx.requests.length);
      count.className = "badge badge-info";
      count.setAttribute("aria-label", `${ctx.requests.length} return requests`);
      for (const row of ctx.requests) {
        const card = doc.createElement("article");
        card.className = "buyer-return-request";
        const heading = doc.createElement("h4");
        const state = {PENDING: "Pending review", APPROVED: "Approved", REJECTED: "Rejected"};
        heading.textContent = `Request #${row.id} · Shop order #${row.seller_order_id} · ${state[row.status] || row.status}`;
        card.append(heading);
        const details = [
          `Reason: ${row.reason}`, `Evidence: ${row.evidence}`,
          `Submitted: ${dateLabel(row.created_at)}`,
          `Order status: ${row.seller_order_status} · Payment: ${row.payment_status} · Escrow: ${row.escrow_status}`,
        ];
        if (row.status === "PENDING") details.push("Escrow release is paused while this request is reviewed.");
        if (row.decision_notes) details.push(`Review notes: ${row.decision_notes}`);
        if (row.decided_at) details.push(`Reviewed: ${dateLabel(row.decided_at)}`);
        for (const text of details) {
          const paragraph = doc.createElement("p");
          paragraph.textContent = text;
          card.append(paragraph);
        }
        ui.list.append(card);
      }
      const choices = eligible(ctx);
      ui.target.replaceChildren();
      for (const row of choices) {
        const option = doc.createElement("option");
        option.value = String(row.id);
        const names = (ctx.order.items || []).filter(item => item.seller_order_id === row.id)
          .map(item => `${item.product_name} × ${item.quantity}`).join(", ");
        option.textContent = `Shop order #${row.id}${names ? ` · ${names}` : ""}`;
        ui.target.append(option);
      }
      if (ctx.target && !choices.some(row => row.id === ctx.target)) {
        ui.form.hidden = true;
        ctx.target = null;
      }
      ui.action.hidden = !ctx.ready || choices.length === 0 || !ui.form.hidden;
      if (ctx.target) ui.target.value = String(ctx.target);
      if (ctx.ready) say(ui.status, choices.length ? "Choose a delivered shop order to request a return or refund."
        : "No shop order is currently eligible. Returns require delivered items with no pending request.");
      controls(ctx);
    }
    async function load(ctx) {
      if (!live(ctx) || ctx.loading || ctx.pending) return;
      ctx.loading = true;
      ctx.ready = false;
      controls(ctx);
      say(ui.error);
      ui.retry.hidden = true;
      say(ui.status, "Loading return requests…");
      const reconciling = ctx.reconcile;
      try {
        const user = await api(ctx, "/api/v1/auth/me");
        if (!live(ctx)) return;
        if (user.role !== "buyer") { reset(); return; }
        if (user.status && user.status !== "ACTIVE") {
          throw Object.assign(new Error("Your account is restricted. Contact support or sign in with an active buyer account."), {status: 403});
        }
        if (ctx.reconcile) {
          const receipt = await api(ctx, `/api/v1/orders/${ctx.order.id}`);
          if (!live(ctx)) return;
          ctx.order = receipt.data;
        }
        const response = await api(ctx, `/api/v1/orders/${ctx.order.id}/returns`);
        if (!live(ctx)) return;
        if (!Array.isArray(response.data)) throw new Error("Return requests could not be loaded. Select Retry.");
        ctx.requests = response.data;
        const recorded = reconciling && ctx.requests.find(row =>
          row.seller_order_id === ctx.lastAttempt && row.status === "PENDING");
        if (recorded) say(ui.feedback, `Request #${recorded.id} is recorded. Review its current status below.`);
        ctx.ready = true;
        ctx.reconcile = false;
        render(ctx);
      } catch (error) {
        if (!live(ctx)) return;
        if (error.status === 401) { unauthenticated(ctx); return; }
        ui.action.hidden = true;
        say(ui.status);
        say(ui.error, error.status === 403 ? error.message
          : "We could not check return eligibility. Select Retry to refresh the order and requests.");
        ui.retry.hidden = false;
        ctx.reconcile = true;
      } finally {
        if (live(ctx)) { ctx.loading = false; controls(ctx); }
      }
    }
    async function update(order) {
      const token = getToken();
      if (!token || !order?.id) { reset(); return; }
      if (!current || current.token !== token || current.order.id !== order.id) {
        reset();
        current = {order, token, requests: [], drafts: new Map(), recorded: new Set(),
          target: null, ready: false, pending: false, loading: false, reconcile: false};
      } else current.order = order;
      ui.panel.hidden = false;
      await load(current);
    }
    ui.action.addEventListener("click", () => {
      const ctx = current;
      if (!ctx || !live(ctx) || !ctx.ready || ctx.pending || !ui.form.hidden) return;
      const choice = eligible(ctx).find(row => row.id === ctx.target) || eligible(ctx)[0];
      if (!choice) return;
      selectTarget(ctx, choice.id);
      ui.form.hidden = false;
      ui.action.hidden = true;
      ui.target.focus();
    });
    ui.target.addEventListener("change", () => {
      const ctx = current;
      if (!ctx || !live(ctx) || ctx.pending) return;
      draft(ctx);
      selectTarget(ctx, Number(ui.target.value));
    });
    ui.cancel.addEventListener("click", () => {
      if (!current || current.pending) return;
      draft(current);
      ui.form.hidden = true;
      ui.action.hidden = !current.ready || eligible(current).length === 0;
      ui.action.focus();
    });
    ui.retry.addEventListener("click", () => { if (current) void load(current); });
    ui.form.addEventListener("submit", async event => {
      event.preventDefault();
      const ctx = current;
      if (!ctx || !live(ctx)) { reset(); return; }
      if (!ctx.ready || ctx.loading || ctx.pending) return;
      say(ui.formError);
      let firstInvalid = null;
      const body = {seller_order_id: Number(ui.target.value)};
      const targetValid = eligible(ctx).some(row => row.id === body.seller_order_id);
      fieldError("target", targetValid ? "" : "Choose an eligible delivered shop order.");
      if (!targetValid) firstInvalid = ui.target;
      for (const [field, [min, max]] of Object.entries(limits)) {
        body[field] = ui[field].value.trim();
        const length = [...body[field]].length;
        const message = length < min || length > max ? `Enter ${min}–${max} characters for ${field}.` : "";
        fieldError(field, message);
        if (message) firstInvalid ||= ui[field];
      }
      if (firstInvalid) { firstInvalid.focus(); return; }
      draft(ctx);
      ctx.lastAttempt = body.seller_order_id;
      ctx.pending = true;
      controls(ctx);
      say(ui.feedback, "Submitting return request…");
      try {
        const response = await api(ctx, `/api/v1/orders/${ctx.order.id}/returns`,
          {method: "POST", body: JSON.stringify(body)});
        if (!live(ctx)) return;
        const saved = response.data;
        if (!saved?.id || saved.order_id !== ctx.order.id || saved.seller_order_id !== body.seller_order_id) {
          throw new Error("The submission result could not be confirmed.");
        }
        ctx.requests = [saved, ...ctx.requests.filter(row => row.id !== saved.id)];
        ctx.recorded.add(body.seller_order_id);
        ctx.drafts.delete(body.seller_order_id);
        ctx.target = null;
        ui.reason.value = ui.evidence.value = "";
        ui.form.hidden = true;
        say(ui.feedback, `Return request #${saved.id} submitted. Escrow release is paused pending review.`);
        render(ctx);
        void Promise.resolve(onSubmitted(ctx.order.id)).catch(() => {});
      } catch (error) {
        if (!live(ctx)) return;
        if (error.status === 401) { unauthenticated(ctx); return; }
        say(ui.feedback, "Return request was not confirmed.");
        say(ui.formError, error.status === 422 ? "Check the reason and evidence, then submit again."
          : "Check existing requests with Retry before sending again. Your draft is retained.");
        if (error.status === 422) {
          let firstField = null;
          for (const field of ["reason", "evidence"]) {
            if (error.fields?.[field]) {
              fieldError(field, [].concat(error.fields[field]).join(" "));
              firstField ||= ui[field];
            }
          }
          ctx.focusAfterSubmit = firstField || ui.reason;
        } else {
          ctx.ready = false;
          ctx.reconcile = true;
          say(ui.error, "The order may have changed, or the request may already be recorded. Select Retry to check.");
          ui.retry.hidden = false;
        }
      } finally {
        if (live(ctx)) {
          ctx.pending = false;
          controls(ctx);
          ctx.focusAfterSubmit?.focus();
          delete ctx.focusAfterSubmit;
        }
      }
    });
    window.addEventListener("storage", event => {
      if (!event.key || ["access_token", "token"].includes(event.key)) reset();
    });
    reset();
    return {update, reset, hide};
  }
  return {create};
})();
