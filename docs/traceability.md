# Traceability

Every screen traces back to a feature and forward to the issue that built it.

This table is the single source of truth for Milestone 1 section 6 and for the
Milestone 4 report. Keep it current - a PR that adds a route and does not
update this file should not be approved.

| Route | Purpose | Access | Priority | Feature | Story issue | Spec PR (Milestone 1) | Implementation PR (Sprint 2) | Runtime |
|---|---|---|---|---|---|---|---|---|
| `/products` | Browse product catalog | G | P0 | F1 Product Discovery | [#13](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/13), [#45](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/45) | [#24](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/24) | [#57](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/57), [#58](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/58), [#59](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/59), [#60](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/60), [#61](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/61), [#64](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/64), [#65](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/65), [#68](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/68), [#70](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/70) | Partial |
| `/products/:productId` | View product details | G | P0 | F1 Product Discovery | [#14](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/14) | [#35](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/35) | None yet | Not implemented |
| `/cart` | Manage shopping cart | U | P0 | F2 Cart | [#15](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/15), [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) | [#31](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/31) | Branch `feat/79-cart` (Sprint 3) | Implemented on `feat/79-cart`; buyers add products from `/products/:productCode` (#78, [PR #91](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/91)) |
| `/checkout` | Place an order | U | P0 | F3 Ordering | [#16](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/16) | [#23](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/23) | None yet | Not implemented |
| `/orders` | View buyer orders | U | P1 | F3 Ordering | [#17](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/17) | [#27](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/27) | None yet | Not implemented |
| `/orders/:id` | View buyer order details | U | P1 | F3 Ordering | [#17](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/17) | [#27](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/27) | None yet | Not implemented |
| `/seller/products` | Manage seller products | U | P0 | F4 Product Management | None | None | None yet | Not implemented; not in the Milestone 1 requirements (gap G8) |
| `/seller/products/new` | Create product listing | U | P0 | F4 Product Management | [#18](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/18) | [#32](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/32) | None yet | Not implemented |
| `/seller/products/:productId/edit` | Update product information and stock | U | P1 | F4 Product Management | [#19](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/19) | [#34](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/34) | None yet | Not implemented |
| `/seller/orders` | Manage incoming orders | U | P0 | F5 Order Management | [#20](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/20) | [#26](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/26) | None yet | Not implemented |
| `/seller/analytics` | View sales analytics | U | P1 | F6 Analytics | [#21](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/21) | [#33](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/33) | None yet | Not implemented |
| `/seller/analytics/products` | View best-selling product ranking | U | P2 | F6 Analytics | [#22](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/22) | [#39](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/39) | None yet | Not implemented |

**Access codes:** G = guest (not logged in) · U = authenticated user · A = admin

**Spec PR:** the merged Milestone 1 pull request that specified the story. A
merged spec PR means the story is specified, not built.

**Runtime** on `main` at `37e80c3`: Implemented / Partial / Not implemented.
`/products` is Partial because the walking skeleton covers part of US01; see
[P0 story map](#p0-story-map).

## P0 story map

Each P0 story traced from the Milestone 1 requirements through the screen, the
endpoint in the [API design](design.md#33-p0-endpoint-contract) and the tables
in the [data model](design.md#22-table-definitions) to what runs today. The
data model (PR #66, approved by @MinhQuangQu) and the API contract (PR #63,
approved by @minhnm162; restored and aligned with `seller_orders` in PR #69,
approved by @minhnm162) are merged for all six stories. All six tables exist in
the database since PR #68 (#46), but only the catalog reads them.

| Story | Screen | Endpoint | Tables | Runtime on `main` | Tests and evidence |
|---|---|---|---|---|---|
| [US01](us01-browse-product-catalog.md) Browse product catalog ([#13](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/13)) | `/products` | `GET /api/v1/products` | `products`; `users` as the owning seller | Partial. The page and the API read the database. The page shows only the first 20 products, with no page controls or filters (G3), and out-of-stock products are still listed (G2). | `tests/test_products.py`, `tests/test_issue45_scenarios.py`, `tests/test_products_page.py`; items E1 to E6 in the [evidence index](evidence/sprint2.md) |
| [US02](us02-view-product-detail.md) View product details ([#14](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/14)) | `/products/:productId` | `GET /api/v1/products/{productCode}` | `products` | Not implemented | None yet; the screen and the endpoint name the product differently (G4) |
| [US03](us03-cart.md) Cart management ([#15](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/15)) | `/cart` | `GET /api/v1/cart`; `POST /api/v1/cart/items`; `PATCH` and `DELETE /api/v1/cart/items/{productCode}` | `cart_items`, `products`, `users` | Implemented on `feat/79-cart` ([#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79)) for authenticated buyers. Buyers add products with Add to Cart on the product detail page (#78, [PR #91](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/91)) | `tests/test_cart_service.py`, `tests/test_cart_api.py`, `tests/test_cart_page.py`; [evidence for issue #79](#evidence-for-issue-79) |
| [US04](us04-checkout.md) Checkout and order placement ([#16](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/16)) | `/checkout` | `POST /api/v1/orders` | `orders`, `seller_orders`, `order_items`, `cart_items`, `products`, `users` | Not implemented; the tables exist | None yet |
| [US06](us06-create-product.md) Create product listing ([#18](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/18)) | `/seller/products/new` | `POST /api/v1/seller/products` | `products`, `users` | Not implemented | None yet |
| [US08](us08-seller-order-management.md) Seller order management ([#20](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/20)) | `/seller/orders` | `GET /api/v1/seller/orders`; `PATCH /api/v1/seller/orders/{subOrderId}/status` | `seller_orders`, `order_items`, `orders`, `products`, `users` | Not implemented; the tables exist | None yet |

Routes that run on `main` at `37e80c3`: the `/products` page, `GET /api/v1/products`,
`GET /health`, `GET /api/v1/health` and `GET /`. No other P0 endpoint exists yet.

## Task 3: Database-backed product API

`GET /api/v1/products?page={page}&limit={limit}` is implemented by
`src/api/products.py:list_products()`. It queries the `products` table
(`src/models/product.py`) through the SQLModel session injected as `SessionDep`
(`src/database.py`), returns only active products, and orders them by `id` so
pages are stable. `python -m src.database` creates the table and
`python -m src.seed` loads 45 sample products; running the seed again adds none.

Equivalent SQL for one request:

```sql
SELECT COUNT(*) FROM products WHERE is_active = TRUE;

SELECT * FROM products
WHERE is_active = TRUE
ORDER BY id
LIMIT :limit OFFSET :offset;   -- offset = (page - 1) * limit
```

The internal primary key `id` is an integer; the API returns it as a string,
together with the product `code` (for example `P-100`). `thumbnail_url` and
`image_url` both come from the `image_url` column, and `stock_status` is derived
from `stock_quantity`: `out_of_stock` at 0, `low_stock` up to 5, otherwise
`in_stock`.

| Task 3 requirement | Implementation | Status |
|---|---|---|
| Fetch products from the real database | `list_products()` runs SQLModel `select` queries through `SessionDep` | Done |
| Do not hard-code the product list | Every item in `data` is built from a selected `Product` row | Done |
| Support the defined product-list API contract | Returns `data` and `meta` (`current_page`, `limit`, `total`, `total_pages`); `page < 1`, `limit < 1` or `limit > 100` return `422` | Done |
| Apply catalog visibility rules | Both queries filter on `is_active = TRUE` | Done |
| Keep query failures apart from an empty catalog | A database error is logged on the server and returns `500` with a generic message; an empty table returns `200` with `data: []` and `total: 0` | Done |

### Backend evidence for issue #49

Run on 2026-10-04 against commit `489f187` with a new SQLite database file.
Environment: Ubuntu 24.04 on WSL2, Python 3.12.3, FastAPI 0.142.2,
SQLModel 0.0.22, SQLAlchemy 2.0.54, Uvicorn 0.54.0.

```text
$ python -m src.database
Database initialization completed successfully.
$ python -m src.seed
Added: 45 products
Total products: 45
Active products: 45
$ python -m src.seed
Added: 0 products
Total products: 45
Active products: 45
$ python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
$ curl "http://127.0.0.1:8000/api/v1/products?page=1&limit=20"
```

First item and `meta` of that response:

```json
{"id": "1", "code": "P-100", "name": "Wireless Mouse", "description": "Wireless mouse for study and office work", "price": 180000.0, "thumbnail_url": "/images/p-100.jpg", "image_url": "/images/p-100.jpg", "stock_quantity": 12, "stock_status": "in_stock"}
{"current_page": 1, "limit": 20, "total": 45, "total_pages": 3}
```

| Check | Result |
|---|---|
| Pages 1 to 4 with `limit=20` | 20, 20, 5 and 0 items; 45 distinct codes; `total` 45 and `total_pages` 3 on every page |
| `page=0`, `limit=0`, `limit=101` | `422` |
| `P-100` set to `is_active = 0` | Not in `data`; `total` drops to 44 |
| Name and price of `P-101` changed in the database | The next response shows the new values |
| `products` table renamed, so the query fails | `500` with `{"detail": "Unable to load products right now. Please try again later."}`; the server log shows `Product catalog query failed` with the traceback |
| All rows deleted | `200` with `data: []`, `total: 0`, `total_pages: 0` |

The `/products` browser checks from the frontend evidence below were rerun on
this commit and database (20/20 passed). Screenshots:
[catalog](images/issue49-catalog.png),
[empty state](images/issue49-empty-state.png),
[error with Retry](images/issue49-error-retry.png).
Automated coverage is in `tests/test_products.py` and `tests/test_database.py`
(`pytest`: 22 passed).

## Frontend `/products` evidence

The guest-facing `/products` page is served by the same FastAPI app as the API:
`src/web/router.py` returns `src/web/pages/products.html`, and `src/main.py`
mounts `src/web/static/` at `/static`. Browser behavior lives in
`src/web/static/products.js`, which requests `/api/v1/products?page=1&limit=20`
and renders only `response.data`; it does not contain a hard-coded product
array. The page renders product cards, a loading skeleton, an API error with a
Retry action, and the empty-state message `No products available at the moment.`

| Frontend requirement | Implementation | Evidence |
|---|---|---|
| Display products returned by the backend | `loadProducts()` in `src/web/static/products.js` fetches the first page and builds each card with `createProductCard()` | Browser page at `http://127.0.0.1:8000/products` |
| Display at least 10 records when available | The request asks for `page=1&limit=20`, so the page shows up to 20 products | With the 45 seeded products, the page shows 20 of 45 |
| Display an empty state | `loadProducts()` shows the empty state when `data` is empty and `meta.total` is 0 | An empty `products` table shows the empty-state message |
| Handle loading and API failures | `loadProducts()` shows a loading skeleton; HTTP errors, network failures, a 10 s timeout and malformed payloads show an error with a Retry button | An API `500` shows the error state; Retry reloads the products |

### Evidence for issue #49

Captured on 2026-10-04 against commit `883e9a4` (PR #61), using a new SQLite
database file seeded with `python -m src.seed` (45 active products).
Environment: Ubuntu 24.04 on WSL2, Python 3.12.3, FastAPI 0.142.2,
SQLModel 0.0.22, SQLAlchemy 2.0.54, Uvicorn 0.54.0, headless Chromium 149
driven by Playwright.

| Check | Result |
|---|---|
| Clean seeded database | `GET /api/v1/products?page=1&limit=20` returns `meta.total` 45 and 20 items; the page shows the same 20 names and prices, formatted in VND (`180.000 ₫`) |
| Name and price changed in the test database, page reloaded | The first card shows the new name and price |
| Empty test database (`DELETE FROM products`) | API `200` with `data: []` and `total: 0`; the page shows the empty state without errors |
| API error (`products` table renamed in the test database) | API `500`; the page shows the error message and Retry; after the table is restored, Retry shows the 20 products again |
| Layout at 1280 / 800 / 390 px | 4 / 3 / 2 columns, no horizontal scrolling |

![Catalog page showing 20 of the 45 seeded products](images/issue49-catalog.png)

![Empty state for an empty products table](images/issue49-empty-state.png)

![Error state with Retry while the API returns 500](images/issue49-error-retry.png)

To reproduce:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # keep only DATABASE_URL=sqlite:///./marketplace.db
python -m src.seed      # creates the tables, a demo seller and 45 products; a rerun adds none
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/products. Run the edit, empty and error checks on a
disposable copy of the database.

## Frontend `/cart` evidence

The buyer's cart page is served at `/cart` by `src/web/router.py`. Its script,
`src/web/static/cart.js`, sends the token saved by the login page as
`Authorization: Bearer`, renders only the cart returned by `/api/v1/cart`, and
re-renders after each change from the server's answer. The page follows the
wireframe in [`docs/ui.md`](ui.md) section 2.3.

| Acceptance criterion (#79) | Implementation | Automated test |
|---|---|---|
| An added product is stored in the database with its quantity | Add to Cart on `/products/:productCode` (#78) calls `POST /api/v1/cart/items`, which runs `CartService.add_item()` | `test_first_add_stores_one_line`, `test_add_creates_a_line_then_increases_it`, `test_buyer_can_add_product_to_database_backed_cart` |
| Adding the same product again increases the existing line | `add_item()` increases the line found by `buyer_id` and `product_id` in one `UPDATE`, so concurrent additions are all kept | `test_adding_the_same_product_again_increases_the_existing_line`, `test_add_does_not_overwrite_an_increase_made_after_reading_the_line`, `test_concurrent_cart_additions_preserve_all_updates`, `test_concurrent_cart_inserts_handle_conflict_gracefully`, `test_database_allows_one_line_per_buyer_and_product` |
| Quantity 2 changed to 3 is still correct after a reload | `PATCH /api/v1/cart/items/{productCode}`; the page reloads from `GET /api/v1/cart` | `test_quantity_change_survives_a_reload_with_recalculated_total`, `test_quantity_change_survives_a_reload` |
| Removing a line recalculates the total | `DELETE /api/v1/cart/items/{productCode}` returns the remaining cart | `test_removing_a_line_keeps_the_others_and_recalculates_the_total`, `test_delete_removes_the_line_and_recalculates_the_total` |
| A quantity above available stock is refused and the previous one kept | `validate_purchasable_quantity()`; the page puts the previous quantity back and shows the server's message next to the line | `test_update_above_available_stock_keeps_the_previous_quantity`, `test_quantity_above_stock_is_refused_and_the_previous_one_kept`, `test_add_refuses_one_more_than_the_available_stock`, `test_update_refuses_one_more_than_the_available_stock`, `test_a_change_that_fails_after_writing_is_rolled_back`, `test_database_failure_after_writing_leaves_the_cart_unchanged` |
| An empty cart shows the empty state with Continue shopping | `GET` returns `200` with `items: []`; the page shows `Your cart is empty.`, total `0 ₫` and a link to `/products` | `test_buyer_without_lines_gets_an_empty_cart` (service and API), `test_cart_page_offers_empty_error_and_checkout_actions` |

### Evidence for issue #79

Captured on 2026-10-14 against commit `a4aaec4` on `feat/79-cart`, using a new
SQLite database file seeded with `python -m src.seed` and the seeded buyer
`user@example.com`. Environment: Ubuntu 24.04 on WSL2, Python 3.12.3,
FastAPI 0.142.2, SQLModel 0.0.22, SQLAlchemy 2.0.54, Uvicorn 0.54.0, headless
Chromium 149 driven by Playwright. Items were added with
`POST /api/v1/cart/items`, before the Add to Cart button of #78 was merged.

| Check | Result |
|---|---|
| Guest opens `/cart` | Sent to `/login?return_to=%2Fcart`; after logging in, the buyer is back on `/cart` and sees the empty state with total `0 ₫` |
| Add `P-100` twice with quantity 1 | `201`, then `200`; `cart_items` holds one `P-100` line with quantity 2 |
| `+` on `P-100`, then reload | Quantity 3 and total `1.190.000 ₫` (3 × 180.000 + 650.000) on screen and in `cart_items` |
| Type 99 for `P-101` (13 available) | `Cannot add more than 13 items (available stock limit)` next to the line; the field returns to 1; the database and the total are unchanged |
| Type 0 | `Enter a whole number of at least 1.` without a request; `−` is disabled at quantity 1 |
| Stock of `P-101` set to 0 in the database, page reloaded | The line stays with its quantity, shows `This product is out of stock.`, and Checkout is disabled until the line is removed |
| Remove the last line | Empty state; `cart_items` is empty |
| Seller `seller@example.com` opens `/cart` | `A buyer account is required.` without Retry |
| Tampered token in `localStorage` | Token removed, sent to `/login?return_to=%2Fcart` |
| Width 375 px | No horizontal scrolling |

![Cart with two lines after the quantity of P-100 was raised to 3 and the page reloaded](images/issue79-cart-data.png)

![Quantity above available stock refused, previous quantity kept](images/issue79-cart-stock-error.png)

![Line flagged after its stock dropped to 0; Checkout disabled](images/issue79-cart-flagged.png)

![Empty cart with total 0 and Continue shopping](images/issue79-cart-empty.png)

#### Add to Cart from the product detail page (#78)

Captured on 2026-10-16 against the merge commit `d9f956e`, after #78
([PR #91](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/91)) reached `main`, on a new seeded database in the same environment.

| Check | Result |
|---|---|
| Guest opens `Wireless Mouse` from the catalog, sets quantity 2, selects Add to Cart | Sent to `/login?return_to=/products/P-100?quantity=2`; nothing is added yet |
| Buyer logs in | Back on `/products/P-100` with quantity 2 kept; Add to Cart opens `/cart` with one `P-100` line of 2, and `cart_items` holds the same |
| Add `P-100` again with quantity 1 | Still one line, now 3; total `540.000 ₫` |
| Add 8 more from the detail page (10 available, 3 in the cart) | The detail page shows `Cannot add more than 10 items (available stock limit)` and stays open; the cart keeps 3 |
| Product with no available stock | `Out of stock` and Add to Cart disabled |
| Cart link in the detail page navigation | Opens `/cart` |

![Cart after adding Wireless Mouse twice from the product detail page](images/issue79-cart-from-detail.png)

To reproduce, seed a new database as in the `/products` evidence above, start
the app, open http://127.0.0.1:8000/products, choose a product, select Add to
Cart and log in as `user@example.com` with password `password`.

## REST API design

The complete API contract is documented in
[`docs/design.md`](./design.md). It defines the method, path, access
requirement, inputs, success response, and error responses for the P0
product, cart, checkout, seller product, and seller order workflows.

| Design deliverable | Coverage | Status |
|---|---|---|
| REST endpoint contract | 10 documented endpoints under `/api/v1` | Done |
| Error handling contract | Documents `400`, `401`, `403`, `404`, `409`, `422`, and `500` conditions | Done |
| P0 story coverage | US01, US02, US03, US04, US06, and US08 mapped to endpoints | Done |

## P0 UI wireframes and documentation

The initial UI contract is documented in [`docs/ui.md`](./ui.md). It provides
wireframes and implementation-facing traceability for all six P0 screens,
plus login and order confirmation.

| UI requirement | Evidence in `docs/ui.md` | Traceability |
|---|---|---|
| Wireframe for the product catalog | Section 2.1, `/products` | US01 / issue #13 and issue #45 |
| Wireframe for product details | Section 2.2, `/products/:productCode` | US02 / issue #14 |
| Wireframe for cart management | Section 2.3, `/cart` | US03 / issue #15 |
| All four cart states | Section 2.3, “Required cart states” | US03 / loading, data, empty, and error |
| Wireframe for checkout | Section 2.4, `/checkout` | US04 / issue #16 |
| Wireframe for seller product creation | Section 2.5, `/seller/products/new` | US06 / issue #18 |
| Wireframe for seller order management | Section 2.6, `/seller/orders` | US08 / issue #20 |
| Login and confirmation screens | Sections 2.7 and 2.8 | Shared authentication and checkout completion |
| Purpose, endpoint, access, CTA, next step, and UI states | Sections 1 and 2 | Applies to every documented screen |
| Buyer and seller flows | Section 1, “Navigation flows” | US01 → US04 and US06 → US08 |
| Review before implementation | Section 4, “Wireframe review checklist” | Pending product, buyer, seller, accessibility, and engineering review |

## Business rules

Numbered, so issues and tests can cite them.

| # | Rule | Enforced where (on `main` at `37e80c3`) | Tested by |
|---|------|----------------|-----------|
| BR1 | Only available products can be displayed in the product catalog. | `list_products()` in `src/api/products.py` returns only rows with `is_active = TRUE`. Stock is not checked: an out-of-stock product is listed with `stock_status: out_of_stock` (gap G2). | `test_products_database_pagination_and_visibility` in `tests/test_products.py` (an inactive product is left out); the scenarios in `tests/test_issue45_scenarios.py` |
| BR2 | Buyers may add or update cart items only when the requested quantity is a positive integer and does not exceed current available stock. Adding an item to the cart does not reserve stock. | `validate_quantity()` and `validate_purchasable_quantity()` in `src/services/cart.py` (#79): available stock is `stock_quantity - reserved_stock`, and `POST` checks the quantity after adding to an existing line. The cart never writes to `products`. Backed by CHECK `quantity > 0` and `UNIQUE(buyer_id, product_id)` on `cart_items` (#46). | `tests/test_cart_service.py` (`test_reserved_stock_is_not_available_to_the_cart`, `test_add_checks_stock_against_the_quantity_after_adding`, `test_cart_changes_never_touch_product_stock`, invalid quantities); `tests/test_cart_api.py` (`409`, `400` and `422` responses); `test_add_rechecks_stock_when_the_line_filled_up_after_reading`; the stock boundary tests (`test_add_accepts_exactly_the_available_stock`, `test_add_refuses_one_more_than_the_available_stock`, `test_adding_to_a_line_may_reach_exactly_the_available_stock`, `test_update_accepts_exactly_the_available_stock`, `test_quantity_at_the_stock_limit_is_accepted_and_one_more_is_refused`); and `test_concurrent_additions_respect_stock_limit` in `tests/test_product_detail.py` |
| BR3 | A buyer must be authenticated before placing an order. | Design only: Bearer token on checkout ([API design](design.md#32-authentication-and-common-response-rules)). No authentication exists. | None yet |
| BR4 | A buyer can view only their own orders. | Design only: order endpoints and authentication are not built. | None yet |
| BR5 | Sellers may create and manage only products belonging to their own store. Product ownership must be derived from the authenticated seller identity. | Schema only: `products.seller_id` is a foreign key to `users.id` (#46). Taking the seller from the token needs authentication, which does not exist. | None yet (gap G7) |
| BR6 | Sellers can view and manage incoming orders related to their products. | Schema only: `seller_orders.seller_id` and `UNIQUE(order_id, seller_id)` (#46). No seller order endpoint exists. | None yet |
| BR7 | Seller revenue is calculated only from the authenticated seller's order items in COMPLETED orders, using the item price recorded at purchase time. | Design only: `order_items.unit_price`, `seller_orders.status` and `seller_orders.completed_at` ([data model](design.md#25-business-rule-mapping)). Analytics (P1) is not built. | None yet |
| BR8 | Before creating an order, the system must revalidate product availability and stock using the latest stock data. If stock is insufficient, the order must not be created and the buyer must be informed which item caused the problem. | Design only: one checkout transaction with an optimistic check on `products.version` ([transaction rules](design.md#26-transaction-level-rules)). Checkout is not built. | None yet |
| BR9 | Product updates (price, stock quantity, and product information) must validate that price is strictly positive (> 0) and stock quantity is a non-negative integer (>= 0). If an update fails validation, the database transaction is aborted, and all previous valid data remains unchanged. | Schema only: CHECK `price > 0`, `stock_quantity >= 0`, `reserved_stock >= 0` and `reserved_stock <= stock_quantity` on `products` (#46). The update flow (US07, P1) is not built. | None yet; no test writes an invalid value (gap G7) |
| BR10 | Seller best-selling product analytics must rank only the authenticated seller's own products using quantities from completed order items in the selected reporting period. | Design only: completed `seller_orders` and `order_items` quantities ([data model](design.md#25-business-rule-mapping)). Analytics (P2) is not built. | None yet |
