"""Browser-facing routes for the marketplace."""

# The inline HTML/CSS/JavaScript is kept together as the page asset.
# ruff: noqa: E501

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Web"])


PRODUCTS_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Product catalog | Mini Marketplace</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      color: #172033;
      background: #f5f7fb;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 48px 0 64px; }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 32px; }
    h1 { margin: 0; font-size: clamp(2rem, 5vw, 3.5rem); letter-spacing: -0.04em; }
    .subtitle { color: #667085; margin: 10px 0 0; }
    .count { color: #667085; font-size: .95rem; white-space: nowrap; }
    .status { text-align: center; padding: 48px 20px; color: #667085; }
    .error { color: #b42318; background: #fef3f2; border: 1px solid #fecdca; border-radius: 12px; }
    .empty { background: white; border-radius: 16px; box-shadow: 0 8px 30px #10182812; }
    .products { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; }
    .card { background: white; border: 1px solid #eaecf0; border-radius: 16px; overflow: hidden; box-shadow: 0 8px 30px #1018280d; }
    .card-image { height: 150px; display: grid; place-items: center; background: linear-gradient(135deg, #e0e7ff, #fce7f3); color: #475467; font-size: 2.5rem; }
    .card-body { padding: 18px; }
    .card h2 { font-size: 1.05rem; margin: 0 0 8px; }
    .description { color: #667085; font-size: .9rem; min-height: 40px; margin: 0 0 16px; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .price { font-weight: 700; font-size: 1.1rem; }
    .stock { font-size: .78rem; color: #027a48; background: #ecfdf3; border-radius: 999px; padding: 5px 9px; }
    .stock.low { color: #b54708; background: #fffaeb; }
    .stock.out { color: #b42318; background: #fef3f2; }
    button { border: 0; border-radius: 8px; padding: 10px 16px; background: #344054; color: white; cursor: pointer; font-weight: 600; }
    button:hover { background: #1d2939; }
    @media (max-width: 600px) { header { display: block; } .count { display: block; margin-top: 16px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Product catalog</h1>
        <p class="subtitle">Browse products available from our marketplace.</p>
      </div>
      <div id="count" class="count" aria-live="polite"></div>
    </header>
    <section id="status" class="status" aria-live="polite">Loading products...</section>
    <section id="products" class="products" aria-label="Available products"></section>
  </main>
  <script>
    const status = document.getElementById("status");
    const products = document.getElementById("products");
    const count = document.getElementById("count");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }[character]));
    }

    function stockClass(stockStatus) {
      return stockStatus === "out_of_stock" ? "out"
        : stockStatus === "low_stock" ? "low" : "";
    }

    function stockLabel(product) {
      if (product.stock_status === "out_of_stock") return "Out of stock";
      if (product.stock_status === "low_stock") return `Only ${product.stock_quantity} left`;
      return "In stock";
    }

    function renderProducts(items, total) {
      count.textContent = `${total} product${total === 1 ? "" : "s"}`;
      if (!items.length) {
        status.className = "status empty";
        status.innerHTML = "<strong>No products available at the moment.</strong>";
        products.replaceChildren();
        return;
      }
      status.hidden = true;
      products.innerHTML = items.map((product) => `
        <article class="card">
          <div class="card-image" aria-hidden="true">🛍️</div>
          <div class="card-body">
            <h2>${escapeHtml(product.name)}</h2>
            <p class="description">${escapeHtml(product.description || "Quality marketplace product.")}</p>
            <div class="card-footer">
              <span class="price">$${Number(product.price).toFixed(2)}</span>
              <span class="stock ${stockClass(product.stock_status)}">${stockLabel(product)}</span>
            </div>
          </div>
        </article>
      `).join("");
    }

    async function loadProducts() {
      status.hidden = false;
      status.className = "status";
      status.textContent = "Loading products...";
      try {
        const response = await fetch("/api/v1/products?limit=100");
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
        const payload = await response.json();
        renderProducts(payload.data, payload.meta.total);
      } catch (error) {
        console.error("Unable to load products", error);
        status.className = "status error";
        status.innerHTML = 'Something went wrong while loading products. <button type="button" onclick="loadProducts()">Retry</button>';
        products.replaceChildren();
      }
    }

    loadProducts();
  </script>
</body>
</html>"""


@router.get("/products", response_class=HTMLResponse)
def products_page() -> HTMLResponse:
    """Render the guest product catalog shell."""
    return HTMLResponse(content=PRODUCTS_PAGE)
