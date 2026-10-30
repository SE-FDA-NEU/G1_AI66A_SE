/* Native SVG, with exact values provided separately by the analytics page. */
"use strict";
window.SellerAnalyticsChart = {
  render(container, {points, label, unit}) {
    const ns = "http://www.w3.org/2000/svg";
    const element = (tag, attributes = {}, text = "") => {
      const node = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
      node.textContent = text;
      return node;
    };
    const width = 760, height = 280, left = 90, right = 25, top = 25, bottom = 55;
    const max = points.reduce((value, point) => Math.max(value, point.value), 0) || 1;
    const x = i => left + (points.length === 1 ? .5 : i / (points.length - 1)) * (width - left - right);
    const y = value => height - bottom - value / max * (height - top - bottom);
    const svg = element("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-labelledby": "analytics-svg-title analytics-svg-description"});
    svg.append(element("title", {id: "analytics-svg-title"}, `${label} over time`),
      element("desc", {id: "analytics-svg-description"}, `${points.length} reported periods. Vertical axis: ${unit}. Exact values are in the table below.`));
    for (let tick = 0; tick <= 4; tick++) {
      const value = max * tick / 4, row = y(value);
      svg.append(element("line", {x1: left, y1: row, x2: width - right, y2: row, class: "chart-grid"}),
        element("text", {x: left - 10, y: row + 4, "text-anchor": "end"},
          `${new Intl.NumberFormat("en", {notation: "compact", maximumFractionDigits: 1}).format(value)}${unit === "%" ? "%" : ""}`));
    }
    const tickIndexes = new Set([0, points.length - 1]);
    for (let i = 1; i < 4; i++) tickIndexes.add(Math.round((points.length - 1) * i / 4));
    for (const index of tickIndexes) svg.append(element("text", {x: x(index), y: height - 20,
      "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}, points[index].label));
    svg.append(element("text", {x: left, y: 14}, unit),
      element("polyline", {points: points.map((point, index) => `${x(index)},${y(point.value)}`).join(" "), class: "chart-line"}));
    for (const [index, point] of points.entries()) {
      const circle = element("circle", {cx: x(index), cy: y(point.value), r: 3, class: "chart-point"});
      circle.append(element("title", {}, `${point.label}: ${point.value} ${unit}`));
      svg.append(circle);
    }
    container.replaceChildren(svg);
  },
};
