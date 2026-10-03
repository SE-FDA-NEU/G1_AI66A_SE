# Traceability

Every screen traces back to a feature and forward to the issue that built it.

This table is the single source of truth for Milestone 1 section 6 and for the
Milestone 4 report. Keep it current - a PR that adds a route and does not
update this file should not be approved.

| Route | Purpose | Access | Priority | Feature | Story issue | PR | Status |
|-------|---------|--------|----------|---------|-------------|-----|--------|
| `/products` | Browse product catalog | G | P0 | F1 Product Discovery | [#13](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/13) | [#24](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/24) | In progress |
| `/products/:productId` | View product details | G | P0 | F1 Product Discovery | [#14](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/14) | [#35](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/35) | Done |
| `/cart` | Manage shopping cart | U | P0 | F2 Cart | #15 | #<PR_NUMBER> | In progress |
| `/checkout` | Place an order | U | P0 | F3 Ordering | #16 | #23 | In progress |
| `/orders` | View buyer orders | U | P1 | F3 Ordering | #17 | #27 | In progress |
| `/orders/:id` | View buyer order details | U | P1 | F3 Ordering | #17 | #27 | In progress |
| `/seller/products` | Manage seller products | U | P0 | F4 Product Management | TBD | TBD | Not started |
| `/seller/products/new` | Create product listing | U | P0 | F4 Product Management | #18 | #28 | In progress |
| `/seller/products/:productId/edit` | Update product information and stock | U | P1 | F4 Product Management | #19 | #30 | In progress |
| `/seller/orders` | Manage incoming orders | U | P0 | F5 Order Management | [#20](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/20) | [#26](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/26) | In progress |
| `/seller/analytics` | View sales analytics | U | P1 | F6 Analytics | #21 | #33 | In progress |
| `/seller/analytics/products` | View best-selling product ranking | U | P2 | F6 Analytics | #22 | #39 | In review |

**Access codes:** G = guest (not logged in) · U = authenticated user · A = admin

**Status:** Not started / In progress / Done

## Task 3: Database-backed product API

Task 3 is implemented for the `/products` catalog backend. The
`GET /api/v1/products` endpoint now uses the injected SQLAlchemy database
session to query the `products` table instead of returning a hard-coded
response. The query filters published, non-deleted products, orders by
creation time, and supports paginated results through `page` and `limit`.
Each response includes product fields, stock status, and pagination metadata.

| Task 3 requirement | Implementation | Status |
|---|---|---|
| Fetch products from the real database | `src/api/products.py:list_products()` uses `get_db()` and SQL queries | Done |
| Do not hard-code the product list | Product rows are selected from `products` with bound query parameters | Done |
| Support the defined product-list API contract | `GET /api/v1/products?page={page}&limit={limit}` returns `data` and `meta` | Done |
| Apply catalog visibility rules | Query includes `is_published = true` and `deleted_at IS NULL` | Done |

## Frontend `/products` evidence

The guest-facing `/products` page is implemented in `src/web.py` and registered
through `src/main.py`. It fetches product data from
`/api/v1/products?limit=100`; it does not contain a hard-coded product array.
The page renders product cards, loading feedback, an API error with a Retry
action, and the empty-state message `No products available at the moment.`

| Frontend requirement | Implementation | Evidence |
|---|---|---|
| Display products returned by the backend | `src/web.py` calls the product API and renders the response into the catalog grid | Browser page at `http://127.0.0.1:8000/products` |
| Display at least 10 records when available | The page renders every record returned by the API request with `limit=100` | Depends on the database containing at least 10 product rows |
| Display an empty state | `renderProducts()` hides the grid and displays the empty-state message when `data` is empty | Implemented in `src/web.py` |
| Handle loading and API failures | `loadProducts()` displays loading text and a Retry button for failed requests | Browser validation confirmed the page displays the retry state when the API is unavailable |

## Business rules

Numbered, so issues and tests can cite them.

| # | Rule | Enforced where | Tested by |
|---|------|----------------|-----------|
| BR1 | Only available products can be displayed in the product catalog. | Product catalog | TBD |
| BR2 | Buyers may add or update cart items only when the requested quantity is a positive integer and does not exceed current available stock. Adding an item to the cart does not reserve stock. | Cart | TBD |
| BR3 | A buyer must be authenticated before placing an order. | Checkout | TBD |
| BR4 | A buyer can view only their own orders. | Orders | TBD |
| BR5 | Sellers may create and manage only products belonging to their own store. Product ownership must be derived from the authenticated seller identity. | Seller product management | TBD |
| BR6 | Sellers can view and manage incoming orders related to their products. | Seller order management | TBD |
| BR7 | Seller revenue is calculated only from the authenticated seller's order items in COMPLETED orders, using the item price recorded at purchase time. | Seller analytics | TBD |
| BR8 | Before creating an order, the system must revalidate product availability and stock using the latest stock data. If stock is insufficient, the order must not be created and the buyer must be informed which item caused the problem. | Checkout/order creation | TBD |
| BR9 | Product updates (price, stock quantity, and product information) must validate that price is strictly positive (> 0) and stock quantity is a non-negative integer (>= 0). If an update fails validation, the database transaction is aborted, and all previous valid data remains unchanged. | Seller product management | TBD |
| BR10 | Seller best-selling product analytics must rank only the authenticated seller's own products using quantities from completed order items in the selected reporting period. | Seller analytics | TBD |
