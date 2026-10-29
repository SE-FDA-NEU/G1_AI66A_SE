// Deterministic API fixtures shared by DOM and native-browser UI checks (#143).
export function analyticsPayload(url, mode = "modern") {
  const query = new URL(url, "http://localhost").searchParams;
  const from = query.get("from"), to = query.get("to");
  if (url.includes("best-sellers")) return {data: mode === "empty" ? [] : [
    {product_id: 7, product_code: "SHIRT-7", product_name: "Everyday cotton shirt", units_sold: 9, revenue: 900000},
    {product_id: 8, product_code: "BAG-8", product_name: "Canvas bag", units_sold: 3, revenue: 240000},
  ], meta: {from, to, sort_by: "units", limit: Number(query.get("limit")), count: mode === "empty" ? 0 : 2}};
  const period = query.get("period"), monthly = period === "monthly";
  const periods = [...new Set([from, to].map(date => monthly ? date.slice(0, 7) : date))];
  const empty = mode === "empty", modern = mode !== "legacy";
  const total = empty ? 0 : 1140000;
  return {data: periods.map((date, index) => ({period: date, revenue: index ? 0 : total,
    period_start: from, period_end: to, orders: empty ? 0 : 2, items_sold: empty ? 0 : 12,
    ...(modern ? {gross_order_value: empty ? 0 : index ? 200000 : 1600000,
      completed_revenue: index ? 0 : total, pending_escrow_revenue: empty ? 0 : index ? 200000 : 300000,
      cancellation_rate: empty ? 0 : index ? 0 : 50} : {})})),
  meta: {from, to, period, total_revenue: total, total_orders: empty ? 0 : 2, total_items_sold: empty ? 0 : 12,
    ...(modern ? {gross_order_value: empty ? 0 : 1800000, completed_revenue: total,
      pending_escrow_revenue: empty ? 0 : 500000, cancellation_rate: empty ? 0 : 12.5} : {})}};
}
