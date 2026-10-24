
# System Design - Mini Marketplace

This document is the Sprint 2 system design. Each section has an owner issue;
#50 assembles the complete document.

| Section | Content | Issue |
|---|---|---|
| 1. Architecture | C4 container diagram, containers, request flow, what runs today | #43 |
| 2. Data Model | ERD, tables, constraints, transaction rules | #44 |
| 3. API Design | REST contract for the P0 stories | #47 |
| 4. Walking Skeleton | Route, table, query and screenshot of the running page | #50 |
| 5. Architecture Decision Records | ADR-001 and ADR-002 | #43 |
| 6. What Changed Since Milestone 1 | Changes from feedback, review and implementation | #50 |

---

## 1. Architecture

This section describes the system as it runs in Sprint 2: the walking skeleton
that shows real products from the database on the `/products` page. The other
P0 stories are designed in sections 2 and 3 and have no runtime code yet.

### 1.1 Container diagram

![C4 container diagram of the Mini Marketplace](images/mini-marketplace-c4.svg)

The diagram follows the C4 model at container level: each box is an application
or a data store, and the dashed line is the system boundary. Its source is
[`images/mini-marketplace-c4.mmd`](images/mini-marketplace-c4.mmd); after editing
it, render the SVG again with the Mermaid CLI. Version 11.17.0 was used; later
11.x releases need a newer headless Chrome.

```bash
npx -p @mermaid-js/mermaid-cli@11.17.0 mmdc -i docs/images/mini-marketplace-c4.mmd -o docs/images/mini-marketplace-c4.svg
```

### 1.2 Containers

| Container | Technology | Responsibility | Code |
|---|---|---|---|
| Web UI | HTML, CSS and JavaScript running in the browser | Shows the product catalog and the cart, each with loading, empty and error/Retry states | `src/web/pages/`, `src/web/static/` |
| Web/API application | Python, FastAPI, Uvicorn | Serves the page and the `/static` files, exposes the REST API under `/api/v1`, validates requests and queries the database; business rules live in services such as `CartService` | `src/main.py`, `src/web/router.py`, `src/api/`, `src/schemas/`, `src/services/`, `src/config.py`, `src/database.py` |
| Marketplace database | SQLite file (`marketplace.db`, location set by `DATABASE_URL`) | Stores the six relational tables of section 2 (`users`, `products`, `cart_items`, `orders`, `seller_orders`, `order_items`), with foreign keys and CHECK constraints enabled | `src/models/` |
| Database init and seed CLI | Python console commands using SQLModel | `python -m src.seed` creates missing tables and loads a demo seller and 45 sample products, skipping rows that already exist; `python -m src.database` only creates missing tables | `src/seed.py`, `src/database.py` |

The CLI is not a server: a developer or setup tester runs it on demand. The
settings loader, the database session layer and the routers are components
inside the Web/API application, not separate containers.

The application and the CLI both open the SQLite file directly through
SQLModel/SQLAlchemy. There is no database server and no network protocol between
them and the database.

**Database connection layer.** `src/config.py` reads `DATABASE_URL` from the
environment or `.env`. `src/database.py` builds one engine from it, and each
request receives its own session through `SessionDep`. `init_db()` creates
missing tables at start-up and from the CLI. `/health` runs `SELECT 1` and
reports `"database": "connected"` or `"disconnected"`, and a failed catalog
query returns `500` with a generic message. Issue #48 owns this layer and its
error handling.

### 1.3 Request flow for `/products`

1. The browser requests `GET /products`. The application returns
   `products.html` (`src/web/router.py`), and the page loads
   `/static/products.css` and `/static/products.js` from the same server.
2. `products.js` calls `GET /api/v1/products?page=1&limit=20` on the same
   origin, with a 10 second timeout.
3. `list_products()` (`src/api/products.py`) receives a session through
   `SessionDep` and runs two queries on `products`: a `COUNT(*)` and a paged
   `SELECT` filtered on `is_active = TRUE` and ordered by `id`.
4. The API returns `{data, meta}`. The page builds one card per item (name,
   price in VND, stock badge, image with a placeholder fallback).
5. An empty catalog (`data: []`, `meta.total: 0`) shows the empty state. An HTTP
   error, a network failure, the timeout or a malformed response shows the error
   message with Retry. A failed database query returns `500` with a generic
   message, so it is never shown as an empty catalog.

### 1.4 What runs today and what is design only

| Area | Status in Sprint 2 |
|---|---|
| `/products` page, `GET /api/v1/products`, `/health`, the `products` table, the seed and init commands | Implemented and covered by automated tests in `tests/` |
| Six-table schema of section 2 with foreign keys and CHECK constraints | Designed in #44; implemented in #46 (PR #68) with models in `src/models/` and foreign key enforcement enabled in `src/database.py` |
| Cart (#79) | `/cart` page and the four `/api/v1/cart` endpoints for authenticated buyers, backed by `CartService` and the `cart_items` table; covered by `tests/test_cart_service.py`, `tests/test_cart_api.py` and `tests/test_cart_page.py`. Buyers add products with Add to Cart on the product detail page (#78, PR #91) |
| Product detail (#78) | `/products/{productCode}` page and `GET /api/v1/products/{productCode}` (PR #91); its Add to Cart button calls `POST /api/v1/cart/items` |
| Checkout (#80) | `/checkout`, `/checkout/confirmation/{orderId}`, `POST /api/v1/orders` and `GET /api/v1/orders/{orderId}` (PR #94); covered by `tests/test_checkout.py` and `tests/checkout_ui.mjs` |
| Seller product creation (#81) | `/seller/products/new` and `POST /api/v1/seller/products` (PR #95); covered by `tests/test_seller_products.py` and `tests/seller_products_ui.mjs` |
| Seller order management (#82) | `/seller/orders`, `GET /api/v1/seller/orders` and `PATCH /api/v1/seller/orders/{subOrderId}/status` with the `order_history` audit table (PR #96); covered by `tests/test_seller_orders.py` |
| P0 end-to-end flows (#83) | Browser entry at `/` and `tests/test_p0_flows.py` (PR #97) |
| Buyer and seller authentication | Implemented in `src/auth.py` and `src/api/auth.py`: signed HS256 JWTs, password hashing, `/auth/login`, `/auth/me`, and seller-role dependency |
| Deployment | One local process (`python -m src.main`) and one SQLite file; the page is served by the same process, so there is no separate frontend deployment |

### 1.5 Running catalog API compared with the API contract

`GET /api/v1/products` follows the path, pagination parameters and `{data, meta}`
shape of section 3. Since #75 its errors use the common envelope, and section 3.3
now records `422 ERR_VALIDATION` for an invalid `page` or `limit` (#85). One detail
still differs:

| Detail | Section 3 contract | Running code (`src/api/products.py`) |
|---|---|---|
| Product `id` | Internal integer | Returned as a string, for example `"1"` |

Public URLs and cart calls use `code`, so no screen depends on the type of `id`.

---|---|---|
| Product `id` | Internal integer | Returned as a string, for example `"1"` |
| Invalid `page` or `limit` | `400 Bad Request` | `422 Unprocessable Entity`, from FastAPI query validation |
| Error body | `{"error": {"code", "message"}}` | FastAPI's `{"detail": "..."}` |

The API owner (#47) decides whether the code moves to the contract or the
contract records the current behaviour.

---

## 2. Data Model

The Mini Marketplace uses a relational database model to support the P0 buyer and seller workflows defined in Milestone 1.

The data model contains six main tables:

- `users`
- `products`
- `cart_items`
- `orders`
- `seller_orders`
- `order_items`

The current implementation already contains the `products` table through the `Product` SQLModel. The remaining tables define the relational structure required to support cart management, checkout, seller ownership, and seller order management.

---

### 2.1 Entity Relationship Diagram

![Mini Marketplace ERD](images/design_erd.png)

---

### 2.2 Table Definitions

#### users

**Purpose:** Stores marketplace user accounts. A user may act as a buyer or seller depending on the assigned role.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `name` | VARCHAR(100) | NOT NULL |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE |
| `password_hash` | VARCHAR(255) | NOT NULL |
| `role` | VARCHAR(20) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |

The `role` field identifies whether the user is permitted to perform buyer or seller operations. `password_hash` stores the cryptographic password hash for user authentication and JWT generation (finalized in Sprint 3 Backlog Refinement, Issue #74).

---

#### products

**Purpose:** Stores products listed by sellers together with their current inventory information.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `code` | VARCHAR(20) | NOT NULL, UNIQUE |
| `seller_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `name` | VARCHAR(200) | NOT NULL |
| `description` | TEXT | Optional |
| `price` | INTEGER | NOT NULL, CHECK `price > 0` |
| `stock_quantity` | INTEGER | NOT NULL, DEFAULT 0, CHECK `stock_quantity >= 0` |
| `reserved_stock` | INTEGER | NOT NULL, DEFAULT 0, CHECK `reserved_stock >= 0` |
| `image_url` | TEXT | Optional |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE |
| `version` | INTEGER | NOT NULL, DEFAULT 1, CHECK `version >= 1` |

Additional inventory constraint:

```text
reserved_stock <= stock_quantity
```

The implemented authentication endpoints are `POST /api/v1/auth/login` and
`GET /api/v1/auth/me`. Login accepts an email and password and returns a bearer
token plus the public user profile. The token contains `sub`, `role`, `iat`,
and `exp`; every authenticated request validates its signature, expiry, user
record, and role. Password hashes are never included in responses.
Malformed bearer tokens (including corrupted base64 payloads and `binascii.Error`)
consistently resolve to `401 Unauthorized` (`ERR_INVALID_TOKEN`).

**Navigation Contract:**
Authentication preserves the originally requested protected route:
- The UI checks for `return_to`, `redirect`, or `next` query parameters upon login.
- Valid destinations must be relative paths beginning with a single `/` (rejecting protocol-relative `//` or scheme-based open redirects).
- When no valid return route is provided, navigation defaults to `/products`.

**Seeding & Migrations:**
Development environments are provisioned via `python -m src.seed`, creating both
seller (`demo.seller@marketplace.local`, `seller@example.com`) and buyer
(`user@example.com`, `demo.buyer@marketplace.local`) accounts hashed with scrypt
(default password `password`). Automatic migration (`migrate_db()`) adds `password_hash`
to legacy SQLite databases seamlessly.

Each product belongs to one seller through `seller_id`.

The current implementation already uses these fields in the `Product` SQLModel. The existing `seller_id` field is finalized by this design as a foreign key to `users.id`.

`thumbnail_url` is not stored as a separate database column. The product API can derive the public thumbnail URL from the stored `image_url` value.

---

#### cart_items

**Purpose:** Stores products that a buyer has currently added to their shopping cart.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `buyer_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `product_id` | INTEGER | NOT NULL, Foreign Key → `products.id` |
| `quantity` | INTEGER | NOT NULL, CHECK `quantity > 0` |
| `created_at` | DATETIME | NOT NULL |

Additional constraint:

```text
UNIQUE(buyer_id, product_id)
```

This constraint prevents the same product from appearing as multiple separate cart lines for the same buyer.

When a buyer adds the same product again, the existing cart item's quantity should be updated rather than creating another cart line.

The cart does not permanently reserve stock. Product availability must be checked again during checkout.

---

#### orders

**Purpose:** Stores the main marketplace order created by a buyer during checkout.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `buyer_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `request_key` | VARCHAR(64) | NULL, UNIQUE, index (idempotency key) |
| `total_amount` | INTEGER | NOT NULL, CHECK `total_amount >= 0` |
| `status` | VARCHAR(30) | NOT NULL |
| `recipient_name` | VARCHAR(100) | NOT NULL |
| `delivery_address` | TEXT | NOT NULL |
| `phone_number` | VARCHAR(20) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |

Each order belongs to one buyer. `request_key` is the optional idempotency key provided by the client to prevent duplicate orders upon network retries (finalized in Sprint 3 Backlog Refinement, Issue #74).

A marketplace order may contain products from multiple sellers. Therefore, seller-specific fulfillment is represented separately through the `seller_orders` table.

---

#### seller_orders

**Purpose:** Represents the seller-specific part of a marketplace order so that each seller can view and manage only the products belonging to them.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `order_id` | INTEGER | NOT NULL, Foreign Key → `orders.id` |
| `seller_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `status` | VARCHAR(30) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |
| `completed_at` | DATETIME | NULL; set when status becomes `COMPLETED` |

Additional constraint:

```text
UNIQUE(order_id, seller_id)
```

This ensures that one seller has only one seller-specific order inside a given marketplace order.

The `status` field allows each seller to manage their own fulfillment process independently from other sellers participating in the same buyer order.

The `completed_at` field records when the seller-specific order reaches the `COMPLETED` state. It remains `NULL` while the seller order has not been completed.

For seller analytics, `seller_orders.status` is the canonical fulfillment status. Revenue and best-selling calculations include only seller orders where:

```text
seller_orders.status = COMPLETED
```

The selected analytics period is evaluated using `seller_orders.completed_at`, not the original marketplace order creation timestamp.

---

#### order_items

**Purpose:** Stores individual purchased products belonging to a seller order.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `seller_order_id` | INTEGER | NOT NULL, Foreign Key → `seller_orders.id` |
| `product_id` | INTEGER | NOT NULL, Foreign Key → `products.id` |
| `quantity` | INTEGER | NOT NULL, CHECK `quantity > 0` |
| `unit_price` | INTEGER | NOT NULL, CHECK `unit_price > 0` |

The `unit_price` field stores the product price at the time of purchase.

This value must be stored separately from the current `products.price` because a seller may change the product price after an order has already been created.

Example:

```text
Product price when ordered: 180,000
Current product price later: 200,000
Stored order_items.unit_price: 180,000
```

Historical orders and seller revenue therefore remain correct even when current product prices change.

---

#### order_history

**Purpose:** Stores immutable status change events for seller orders, tracking the transition history, the user who triggered the update, and any cancellation notes.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `seller_order_id` | INTEGER | NOT NULL, Foreign Key → `seller_orders.id` |
| `from_status` | VARCHAR(30) | NOT NULL |
| `to_status` | VARCHAR(30) | NOT NULL |
| `changed_by_user_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `note` | TEXT | Optional |
| `created_at` | DATETIME | NOT NULL |

This table satisfies the Sprint 3 audit requirement for US08 (Issue #74 / Issue #82): when an order status advances or when a `PENDING` seller order is cancelled and inventory is restocked, an immutable history record is appended.

---

### 2.3 Relationships and Cardinality

| Relationship | Cardinality | Description |
|---|---|---|
| `users` → `products` | 1 to 0..* | One seller may own zero or many products; each product belongs to one seller |
| `users` → `cart_items` | 1 to 0..* | One buyer may have zero or many cart items |
| `products` → `cart_items` | 1 to 0..* | One product may appear in zero or many buyers' carts |
| `users` → `orders` | 1 to 0..* | One buyer may create zero or many orders |
| `orders` → `seller_orders` | 1 to 1..* | One marketplace order contains one or more seller-specific orders |
| `users` → `seller_orders` | 1 to 0..* | One seller may receive zero or many seller orders |
| `seller_orders` → `order_items` | 1 to 1..* | One seller order contains one or more purchased items |
| `products` → `order_items` | 1 to 0..* | One product may appear in zero or many historical order items |
| `seller_orders` → `order_history` | 1 to 0..* | One seller order has zero or many historical state transition records |
| `users` → `order_history` | 1 to 0..* | One user may trigger zero or many order transition events |

---

### 2.4 Relationship Summary

The main relationships can be summarized as follows:

```text
users
 ├──< products
 ├──< cart_items
 ├──< orders
 └──< seller_orders

products
 ├──< cart_items
 └──< order_items

orders
 └──< seller_orders

seller_orders
 └──< order_items
```

A buyer creates one marketplace `order`.

If the order contains products from multiple sellers, the order is divided into multiple `seller_orders`.

Example:

```text
Order #100
│
├── Seller Order A
│   ├── Wireless Mouse
│   └── Mechanical Keyboard
│
└── Seller Order B
    └── Laptop Stand
```

This structure allows each seller to view and manage only their own portion of the marketplace order.

---

### 2.5 Business Rule Mapping

Important relational constraints are mapped to the Milestone 1 business rules below.

| Database Constraint / Design Decision | Milestone 1 Rule | Purpose |
|---|---|---|
| `products.price > 0` | BR9 | Prevents zero or negative product prices |
| `products.stock_quantity >= 0` | BR9 | Prevents negative inventory |
| `products.reserved_stock >= 0` | BR9 | Prevents invalid reserved stock |
| `products.reserved_stock <= products.stock_quantity` | BR9 | Ensures reserved stock does not exceed available stock |
| `products.seller_id → users.id` | BR5 | Associates each product with its owning seller |
| `cart_items.quantity > 0` | BR2 | Ensures buyers can only place positive quantities in a cart |
| `UNIQUE(buyer_id, product_id)` | BR2 | Prevents duplicate cart lines for the same buyer and product |
| `orders.buyer_id → users.id` | BR3 / BR4 | Associates an order with the buyer who created it |
| `seller_orders.seller_id → users.id` | BR6 | Supports seller-specific order ownership |
| `UNIQUE(order_id, seller_id)` | BR6 | Creates one seller-specific order per seller inside a marketplace order |
| `order_items.unit_price` | BR7 | Preserves purchase-time prices for historical revenue calculations |
| `order_items.quantity > 0` | BR7 / BR10 | Ensures purchased quantities used in revenue and analytics are valid |
| `seller_orders.status = COMPLETED` | BR7 / BR10 | Ensures revenue and best-selling analytics include only completed seller sales |
| `seller_orders.completed_at` | BR7 / BR10 | Provides the completion timestamp used to filter analytics by selected period |

Some Milestone 1 business rules require application-level or transaction-level validation in addition to database constraints.

---

### 2.6 Transaction-Level Rules

Some business rules cannot be enforced using only static relational constraints.

In particular, stock must be revalidated immediately before an order is created.

The checkout operation should perform the following steps inside one database transaction:

```text
1. Read the buyer's current cart.
2. Re-read the current product inventory.
3. Verify that every requested quantity is still available.
4. Reject checkout if any product is unavailable.
5. Create the marketplace order.
6. Create the required seller orders.
7. Create order items using purchase-time prices.
8. Update product inventory.
9. Commit the transaction.
```

If any step fails, the transaction must roll back so that no partial order or inconsistent stock update remains.

A database transaction alone is not sufficient to prevent overselling when multiple checkout requests update the same product concurrently.

The design uses optimistic concurrency control through `products.version`.

For each product during checkout:

```text
1. Read the latest stock_quantity and version.
2. Verify that the requested quantity is available.
3. Update the product only if its version is still unchanged.
4. Decrease stock and increment version atomically.
5. If no row is updated, another transaction changed the product first;
   reject the checkout and revalidate instead of creating the order.
```

Conceptually:

```sql
UPDATE products
SET stock_quantity = stock_quantity - :quantity,
    version = version + 1
WHERE id = :product_id
  AND version = :expected_version
  AND stock_quantity >= :quantity;
```

If the update affects zero rows, checkout must fail or revalidate.

The inventory update and creation of `orders`, `seller_orders`, and `order_items` remain inside the same transaction. If any step fails, the complete transaction is rolled back.

This strategy supports BR8 by ensuring that the latest inventory is revalidated and updated atomically before order creation.

---

### 2.7 Implementation Consistency Notes

The current `Product` implementation uses an integer primary key.

The implemented product model contains the following database fields:

```text
id
code
seller_id
name
description
price
stock_quantity
reserved_stock
image_url
is_active
version
```

The public product API may expose derived response fields that are not separate database columns.

For example:

```text
thumbnail_url
stock_status
```

`thumbnail_url` can be derived from `image_url`.

`stock_status` can be calculated from `stock_quantity`.

Therefore, these derived API fields do not need to be stored separately in the relational schema.

The current implementation filters the public product catalog using:

```text
is_active = true
```

#### Product visibility terminology

`is_active` is the canonical persistence field used by the current Product model and by this relational design.

Milestone 1 BR1 also describes purchasable products as active.

If earlier API documentation uses `is_published`, it refers to the same catalog-visibility concept. The project should standardize on `is_active` rather than storing both `is_active` and `is_published`.

Therefore, the relational schema contains only:

```text
is_active
```

The ERD and table definitions in this document therefore retain the existing `is_active` field.

The current `seller_id` field exists in the Product model but is not yet implemented as a foreign key. This database design finalizes the intended relationship as:

```text
products.seller_id → users.id
```

The implementation should be updated later to reflect this relationship when the complete user and seller models are introduced.

---

### 2.8 Data Model Summary

The relational model contains six core transactional tables and one audit log table (finalized for Sprint 3):

| Table | Main Responsibility |
|---|---|
| `users` | Stores buyer and seller accounts and password hashes |
| `products` | Stores seller-owned marketplace products and inventory |
| `cart_items` | Stores products currently selected by buyers |
| `orders` | Stores buyer marketplace orders and request idempotency keys |
| `seller_orders` | Separates each marketplace order by seller |
| `order_items` | Stores purchased products, quantities, and purchase-time prices |
| `order_history` | Stores immutable seller order status transitions and audit notes |

Together, these tables support the core P0 workflows required by the Mini Marketplace:

```text
Browse products
      ↓
Add products to cart
      ↓
Checkout
      ↓
Create buyer order
      ↓
Split order by seller
      ↓
Store purchased items
      ↓
Seller manages own order
```

The ERD in `docs/images/design_erd.png` must remain consistent with all table definitions, primary keys, foreign keys, and cardinalities documented in this section.

---

## 3. API Design

This section defines the API contract for the P0 user stories in Milestone 1.
Sections 3.3 and 3.4 were updated in #85 to the behaviour that runs at Milestone 3;
`tests/test_ui_docs_contract.py` checks that section 3.4 lists exactly the error
codes the code raises.
All endpoints use the `/api/v1` prefix and return JSON. Unless stated
otherwise, timestamps are ISO 8601 UTC strings.

### 3.1 Product identifiers

Product identifiers have two distinct forms:

- `id` is the internal database primary key. It is an integer and is not used
  in public product URLs.
- `code` is the public product identifier. It is a unique string up to 20
  characters, using the existing catalog format such as `P-100`.

Product detail and cart endpoints use `productCode`/`product_code` and must
resolve the product by `Product.code`. They must not require a UUID. Other
resource identifiers follow the identifier type defined by their own database
model; this contract does not assume that every identifier is a UUID.

### 3.2 Authentication and common response rules

- **Guest (G):** no access token is required.
- **User (U):** requires a valid authenticated buyer or seller access token.
- **Seller (S):** requires a valid authenticated seller token. The seller
  identity is taken from the token, never from a request body.
- Authenticated endpoints use `Authorization: Bearer <access-token>`.
- Successful collection responses use `{ "data": [...], "meta": {...} }`.
- Successful mutation responses return the created or updated resource in
  `{ "data": {...} }`.
- Errors use the common shape:

```json
{
  "error": {
    "code": "ERR_CODE",
    "message": "Human-readable explanation"
  }
}
```

### 3.3 P0 endpoint contract

| Method and path | Access | Input parameters/body | Successful response | Error responses | Relevant P0 story |
|---|---|---|---|---|---|
| `GET /api/v1/products` | G | Query: `page` (positive integer, default `1`), `limit` (1-100, default `20`), optional catalog filters | `200 OK`: paginated product summaries with internal integer `id`, public `code`, `name`, `price`, `image_url`/`thumbnail_url`, `stock_quantity`, and `stock_status` | `422 Unprocessable Entity` (`ERR_VALIDATION`) for invalid pagination values; `500` (`ERR_DATABASE_FAILURE`) when the catalog cannot be read | US01 Browse product catalog |
| `GET /api/v1/products/{productCode}` | G | Path: `productCode` public product code, for example `P-100` | `200 OK`: one product with `id` (internal integer), `code`, full description, image, price, and current stock status | `404 Not Found` when the product code does not exist or the product is inactive; `422 Unprocessable Entity` when the code is empty or exceeds 20 characters | US02 View product details |
| `GET /api/v1/cart` | U (buyer) | No body; cart is identified by the authenticated buyer | `200 OK`: the cart in the shape described under "Cart response and rules" below. A buyer with no cart lines gets `200 OK` with `items: []` and `cart_total: 0`, not `404` | `401 Unauthorized` when the token is missing/invalid; `403 Forbidden` (`ERR_BUYER_REQUIRED`) for a seller token | US03 Cart management |
| `POST /api/v1/cart/items` | U (buyer) | JSON: `{ "product_code": "P-100", "quantity": 1 }` | `201 Created` for a new line, or `200 OK` when an existing line is increased; returns the updated cart in the same shape as `GET` | `400 Bad Request` (`ERR_INVALID_QUANTITY`) for zero or negative quantity; `422 Unprocessable Entity` (`ERR_VALIDATION`) when `quantity` is not a JSON integer, such as `true`, `1.5` or `"2"`; `401 Unauthorized`; `404 Not Found` (`ERR_PRODUCT_NOT_FOUND`) for an unknown product code; `409 Conflict` when the product is inactive (`ERR_PRODUCT_UNAVAILABLE`), when the quantity after adding exceeds available stock (`ERR_STOCK_EXCEEDED`), or when concurrent requests on the same line still collide after five attempts (`ERR_CONCURRENCY_CONFLICT`) | US03 Cart management |
| `PATCH /api/v1/cart/items/{productCode}` | U (buyer) | Path: public `productCode`; JSON: `{ "quantity": 2 }` | `200 OK`: updated cart with recalculated line and cart totals | `400 Bad Request` (`ERR_INVALID_QUANTITY`) for zero or negative quantity, because a line is removed with `DELETE`; `422 Unprocessable Entity` (`ERR_VALIDATION`) when `quantity` is not a JSON integer; `401 Unauthorized`; `404 Not Found` (`ERR_CART_ITEM_NOT_FOUND`) when the buyer's cart has no line for the product code; `409 Conflict` when the product is inactive (`ERR_PRODUCT_UNAVAILABLE`) or the new quantity exceeds available stock (`ERR_STOCK_EXCEEDED`) | US03 Cart management |
| `DELETE /api/v1/cart/items/{productCode}` | U (buyer) | Path: public `productCode`; no body | `200 OK`: updated cart after removing the line | `401 Unauthorized`; `404 Not Found` (`ERR_CART_ITEM_NOT_FOUND`) when the buyer's cart has no line for the product code | US03 Cart management |
| `POST /api/v1/orders` | U (buyer) | Header `Idempotency-Key` (1-64 characters); JSON: `{ "recipient_name": "...", "delivery_address": "...", "phone_number": "..." }`; items are read from the authenticated buyer's cart | `201 Created`: order ID, items (`product_id`, `product_code`, `product_name`, `quantity`, purchase-time `unit_price`, `line_total`), total, status, and delivery information; `200 OK` with the same order when the same key and body are replayed | `400 Bad Request` for an empty cart (`ERR_EMPTY_CART`) or a key with surrounding spaces (`ERR_INVALID_KEY`); `422` (`ERR_VALIDATION`) for invalid delivery fields or a missing key; `401 Unauthorized`; `403` (`ERR_BUYER_REQUIRED`); `409 Conflict` when a product is unavailable (`ERR_PRODUCT_UNAVAILABLE`), stock changed (`ERR_STOCK_EXCEEDED`), the cart changed (`ERR_CONCURRENCY_CONFLICT`) or the key was used with another body (`ERR_IDEMPOTENCY_CONFLICT`); `500` (`ERR_DATABASE_FAILURE`) | US04 Checkout and order placement |
| `GET /api/v1/orders/{orderId}` | U (buyer) | Path: integer `orderId` | `200 OK`: the same order shape as checkout, so the confirmation page names each product | `401 Unauthorized`; `403` (`ERR_BUYER_REQUIRED`); `404 Not Found` (`ERR_ORDER_NOT_FOUND`) for a missing order or another buyer's order; `422` for a non-integer id | US04 Order confirmation |
| `POST /api/v1/seller/products` | S | JSON product body: `name`, `description`, `price` (integer VND), `stock_quantity`, and `image_url` (absolute http(s) URL); seller, code and status come from the server (#81) | `201 Created`: `{ "data": ... }` with the new listing, its generated `code`, seller ownership and `is_active` status | `422 Unprocessable Entity` (`ERR_VALIDATION`) with messages per field in `error.fields` for empty, invalid or out-of-range values; `401 Unauthorized`; `403 Forbidden` for a non-seller account; `409 Conflict` when no unique product code could be assigned; `500` on database failure | US06 Create product listing |
| `GET /api/v1/seller/orders` | S | Query: `status`, `from`, `to`, `page`, and `limit` (default `20`) | `200 OK`: paginated seller orders (`seller_orders` rows) owned by the authenticated seller only, each with its `id` (the `subOrderId`), parent `order_id`, status, and its order items (product, quantity, unit price) | `400 Bad Request` for an unknown status (`ERR_INVALID_STATUS`), a date that is not ISO (`ERR_INVALID_DATE`) or `from` after `to` (`ERR_INVALID_DATE_RANGE`); `422` (`ERR_VALIDATION`) for invalid `page`/`limit`; `401 Unauthorized`; `403 Forbidden` (`ERR_SELLER_REQUIRED`) for a non-seller account. Success `meta` is `{page, limit, total}` | US08 Seller order management |
| `PATCH /api/v1/seller/orders/{subOrderId}/status` | S | Path: `subOrderId`, the `seller_orders.id` of a seller order owned by the authenticated seller; JSON: `{ "status": "PROCESSING" }` | `200 OK`: `{ "data": ... }` with the updated sub-order and its items; the change is recorded in `order_history`, and cancelling restores stock once | `400 Bad Request` with `ERR_INVALID_TRANSITION` for an invalid status transition; `422` (`ERR_VALIDATION`) for an unknown status value; `401 Unauthorized`; `403 Forbidden` (`ERR_SELLER_REQUIRED`, or `ERR_RESOURCE_OWNER` if the seller order belongs to another seller); `404 Not Found` (`ERR_ORDER_NOT_FOUND`) when the seller order does not exist; `409` (`ERR_CONCURRENCY_CONFLICT`) when it changed meanwhile | US08 Seller order management |
| `POST /api/v1/auth/login` | G | JSON: `{ "email": "...", "password": "..." }` | `200 OK`: `access_token`, `token_type: bearer` and the user (`id`, `name`, `email`, `role`) | `401 Unauthorized` (`ERR_INVALID_CREDENTIALS`); `422` (`ERR_VALIDATION`) for a malformed email | All protected stories |
| `GET /api/v1/auth/me` | U | No body | `200 OK`: the user of the token | `401 Unauthorized` (`ERR_AUTH_REQUIRED`, `ERR_INVALID_TOKEN`) | Checkout and seller pages |

`subOrderId` is `seller_orders.id` from section 2. Fulfilment status is stored per seller order, so a seller changes the status of their whole part of a marketplace order, not of a single order item.

#### Cart response and rules (US03)

Every cart endpoint, read or mutation, returns the whole cart in one shape
(`CartResponse` in `src/schemas/cart.py`), so the `/cart` page always renders
the server's answer instead of keeping its own copy of the rules:

```json
{
  "data": {
    "items": [
      {
        "product_id": 1,
        "product_code": "P-100",
        "name": "Wireless Mouse",
        "image_url": "/images/p-100.jpg",
        "unit_price": 180000,
        "quantity": 2,
        "line_total": 360000,
        "available_stock": 10,
        "availability": "available"
      }
    ],
    "cart_total": 360000
  }
}
```

`availability` is `available`, `insufficient_stock` (the quantity is above
`available_stock`) or `unavailable` (the product is inactive).

`CartService` (`src/services/cart.py`) enforces these rules. It receives the
session and the authenticated `buyer_id` from the router and never reads the
token itself:

- `available_stock = stock_quantity - reserved_stock`.
- `POST` checks the quantity the line will have after adding, not only the
  amount sent. `PATCH` replaces the quantity.
- Every query is filtered by `buyer_id`. A line that belongs to another buyer
  answers `404 ERR_CART_ITEM_NOT_FOUND`, the same as a missing line.
- Prices and totals are read from `products` on every request and are integer
  VND: `line_total = unit_price x quantity` and `cart_total` is the sum of all
  line totals.
- The cart never changes `stock_quantity` or `reserved_stock`. Checkout checks
  stock again (BR8).
- When stock drops or a product is withdrawn after it was added, `GET` keeps
  the line and its quantity and flags it through `availability`. Nothing is
  removed or reduced without the buyer. Flagged lines still count in
  `cart_total`.
- A refused change leaves the cart exactly as it was. Each mutation commits or
  rolls back inside the service; the router does not commit again.
- The database allows one line per buyer and product:
  `UNIQUE(buyer_id, product_id)` on `cart_items` refuses a duplicate even when
  the service is bypassed. `products.code` is unique, so this is also one line
  per buyer and product code; `cart_items` does not repeat the code.
- Adding to an existing line is one `UPDATE` that sets
  `quantity = quantity + n` only while the result fits available stock, so two
  requests adding to the same line at the same time both count. A change that loses a race
  (the same line inserted twice, the line changed after it was read, or SQLite
  busy) runs again on fresh data, at most five times; after that the request
  answers `409 ERR_CONCURRENCY_CONFLICT`. Other database errors are not
  retried and answer `500 ERR_DATABASE_FAILURE`.
- Only buyers have a cart. A seller token gets `403 ERR_BUYER_REQUIRED` from
  every cart endpoint. The `/cart` page sends a guest, or a buyer whose token
  is rejected with `401`, to `/login?return_to=%2Fcart`.

### 3.4 Error handling

Every error response has the body `{"error": {"code", "message"}}`; the
seller product route adds `error.fields` (section "US06 seller product creation
implementation"). This table lists every code the code raises, checked by
`tests/test_ui_docs_contract.py`. The messages a user sees for each case are in
[docs/ui.md section 3](ui.md#3-error-messages).

| Status | Code | Raised when | Where |
|---|---|---|---|
| `400 Bad Request` | `ERR_INVALID_QUANTITY` | A cart quantity is 0 or negative | Cart |
| `400 Bad Request` | `ERR_EMPTY_CART` | Checkout with no cart lines | Orders |
| `400 Bad Request` | `ERR_INVALID_KEY` | The `Idempotency-Key` has surrounding spaces | Orders |
| `400 Bad Request` | `ERR_SELF_PURCHASE` | A seller attempts to add or checkout their own product | Cart, orders |
| `400 Bad Request` | `ERR_INVALID_TRANSITION` | A seller order status change that the state machine does not allow (section 3.6) | Seller orders |
| `400 Bad Request` | `ERR_INVALID_STATUS` | The seller order `status` filter is not a known status | Seller orders |
| `400 Bad Request` | `ERR_INVALID_DATE` | A `from` or `to` filter is not an ISO date | Seller orders |
| `400 Bad Request` | `ERR_INVALID_DATE_RANGE` | `from` is after `to` | Seller orders |
| `401 Unauthorized` | `ERR_AUTH_REQUIRED` | No bearer token | All protected routes |
| `401 Unauthorized` | `ERR_INVALID_TOKEN` | A malformed, expired or no longer valid token (there is no separate expired-token code) | All protected routes |
| `401 Unauthorized` | `ERR_INVALID_CREDENTIALS` | Wrong email or password | Login |
| `403 Forbidden` | `ERR_SELLER_REQUIRED` | A buyer calls a seller route | Seller products, seller orders |
| `403 Forbidden` | `ERR_BUYER_REQUIRED` | A seller calls a buyer route | Cart, orders |
| `403 Forbidden` | `ERR_RESOURCE_OWNER` | A seller changes another seller's sub-order | Seller orders |
| `404 Not Found` | `ERR_PRODUCT_NOT_FOUND` | Unknown or inactive product code | Products, cart |
| `404 Not Found` | `ERR_CART_ITEM_NOT_FOUND` | The buyer's cart has no line for the code | Cart |
| `404 Not Found` | `ERR_ORDER_NOT_FOUND` | Unknown order, another buyer's order, or unknown seller order | Orders, seller orders |
| `409 Conflict` | `ERR_STOCK_EXCEEDED` | Not enough available stock, in the cart or at checkout | Cart, orders |
| `409 Conflict` | `ERR_PRODUCT_UNAVAILABLE` | The product was withdrawn | Cart, orders |
| `409 Conflict` | `ERR_CONCURRENCY_CONFLICT` | Requests kept colliding (cart line, checkout, product code, seller order) | Cart, orders, seller products, seller orders |
| `409 Conflict` | `ERR_IDEMPOTENCY_CONFLICT` | The checkout key was used with another buyer or body | Orders |
| `422 Unprocessable Entity` | `ERR_VALIDATION` | A field has the wrong format or type, or is missing | All routes |
| `500 Internal Server Error` | `ERR_DATABASE_FAILURE` | A database failure; the response never contains SQL | All routes |
| Any | `ERR_BAD_REQUEST`, `ERR_FORBIDDEN`, `ERR_NOT_FOUND`, `ERR_CONFLICT`, `ERR_INTERNAL_SERVER`, `ERR_REQUEST_FAILED` | Fallback codes in `src/main.py` for an `HTTPException` raised without an envelope; no route raises one today | Shared handler |

The Sprint 3 planning list (`docs/evidence/sprint3.md` section 2.3) also named
`ERR_EXPIRED_TOKEN` and `ERR_INTERNAL`; neither was implemented: an expired token
answers `ERR_INVALID_TOKEN`, and an unexpected database error answers
`ERR_DATABASE_FAILURE`. A request to an unknown `/api/v1` path still answers
Starlette's `{"detail": "Not Found"}` (gap UI-G1 in docs/ui.md).

### 3.5 P0 coverage

The contract covers every P0 story listed in the Milestone 1 requirements:

| Story | Covered endpoints |
|---|---|
| US01 Browse product catalog | `GET /api/v1/products` |
| US02 View product details | `GET /api/v1/products/{productCode}` using public codes such as `P-100` |
| US03 Cart management | `GET`, `POST`, `PATCH`, and `DELETE /api/v1/cart...` |
| US04 Checkout and order placement | `POST /api/v1/orders` |
| US06 Create product listing | `POST /api/v1/seller/products` |
| US08 Seller order management | `GET /api/v1/seller/orders` and `PATCH /api/v1/seller/orders/{subOrderId}/status` |

### 3.6 Order State Machine & Transition Rules

To support US04 (Checkout) and US08 (Seller Order Management), the order lifecycle is governed by a strict state machine:

#### Seller Order Transitions (`seller_orders.status`)

```text
       ┌───────────┐
       │  PENDING  │ ──(cancel)──> [ CANCELLED ] (restores stock once)
       └─────┬─────┘
             │ (seller packages order)
             ▼
      ┌──────────────┐
      │  PROCESSING  │
      └──────┬───────┘
             │ (seller hands to carrier)
             ▼
       ┌───────────┐
       │  SHIPPED  │
       └─────┬─────┘
             │ (buyer receives order)
             ▼
      ┌─────────────┐
      │  COMPLETED  │ (triggers revenue recognition)
      └─────────────┘
```

1. **Initial State:** Upon checkout completion (`POST /api/v1/orders`), every generated `seller_orders` record is created with `status = 'PENDING'`.
2. **Valid Forward Transitions:**
   - `PENDING` → `PROCESSING`
   - `PROCESSING` → `SHIPPED`
   - `SHIPPED` → `COMPLETED` (sets `completed_at = CURRENT_TIMESTAMP`)
3. **Cancellation Rule:**
   - A `PENDING` seller order may transition to `CANCELLED`.
   - When transitioning to `CANCELLED`, all purchased quantities in the sub-order's `order_items` are atomically added back to `products.stock_quantity`.
   - A sub-order that is already `PROCESSING`, `SHIPPED`, or `COMPLETED` cannot be cancelled directly without dispute escalation.
4. **Transition Enforcement:**
   - Attempting an illegal or backwards transition (e.g., `SHIPPED` → `PENDING` or `COMPLETED` → `CANCELLED`) returns `400 Bad Request` with `error.code = 'ERR_INVALID_TRANSITION'`.
   - Every status transition creates an immutable record in `order_history`.
5. **Marketplace Parent Order Aggregation (`orders.status`):**
   - The overall buyer order status reflects the collective state of all child `seller_orders`:
     - `COMPLETED`: When all associated seller orders have reached `COMPLETED`.
     - `CANCELLED`: When all associated seller orders have reached `CANCELLED`.
     - `PROCESSING`: When at least one seller order has progressed past `PENDING` while not all are finished.
     - `PENDING`: When all seller orders remain in `PENDING`.

---

## 4. Walking Skeleton

The Sprint 2 walking skeleton demonstrates an end-to-end slice through all architectural tiers:
**Web UI (browser) → FastAPI application → SQLModel/SQLAlchemy session → SQLite database**.
It proves that the stack can be configured, initialized, seeded, queried, and rendered on any development machine.

### 4.1 Selected Route

The walking skeleton implements the guest-facing product discovery flow (US01):

- **Browser Route:** `GET /products`
  - Served by `src/web/router.py` returning `src/web/pages/products.html`.
  - Dependent assets served statically from `/static`: `products.css`, `products.js`, and `product-placeholder.svg`.
  - The client script (`src/web/static/products.js`) executes in the browser and calls the backend API on the same origin (`/api/v1/products?page=1&limit=20`) using `fetch()` with an explicit 10-second timeout.
- **REST API Route:** `GET /api/v1/products`
  - Defined in `src/api/products.py:list_products()` under the `/api/v1` router prefix.
  - Receives query parameters `page` (default: 1) and `limit` (default: 20, max: 100).
  - Validated by FastAPI/Pydantic (`page >= 1`, `1 <= limit <= 100`), returning `422 Unprocessable Entity` on invalid pagination parameters.
  - Returns a standard envelope containing `data` (list of product summaries) and `meta` (pagination metadata: `current_page`, `limit`, `total`, `total_pages`).
- **Health Verification Routes:** `GET /health` and `GET /api/v1/health`
  - Defined in `src/api/health.py`.
  - Executes `SELECT 1` against the database through `check_db_connection()` to confirm database accessibility.

### 4.2 Database Table Used

The primary persistence entity used by the walking skeleton is the `products` table (`src/models/product.py`), associated with the `users` table (`src/models/user.py`):

- **Table:** `products`
- **Model:** `src.models.product.Product` inheriting from `SQLModel` with `table=True`
- **Schema Columns:**
  - `id`: Integer primary key (`autoincrement=True`).
  - `code`: Unique varchar(20) identifier (e.g., `"P-100"`).
  - `seller_id`: Integer foreign key referencing `users.id` (identifies the owning seller account).
  - `name`: Varchar(200) product title.
  - `description`: Optional text description.
  - `price`: Decimal/float monetary price in VND (constrained by `price > 0`).
  - `stock_quantity`: Integer current stock (constrained by `stock_quantity >= 0`).
  - `reserved_stock`: Integer reserved stock during pending checkout (default `0`, constrained by `reserved_stock >= 0`).
  - `image_url`: Optional text URL or static asset path for product imagery.
  - `is_active`: Boolean catalog visibility flag (default `True`).
  - `version`: Integer optimistic locking counter (default `1`, constrained by `version >= 1`).

### 4.3 Database / SQL Query Used to Retrieve Data

The endpoint `list_products()` in `src/api/products.py` queries the database via an injected SQLModel session (`SessionDep`). It issues two distinct SQL queries:

1. **Total Count Query (Active Products):**
   ```sql
   SELECT COUNT(*) FROM products
   WHERE is_active = TRUE;
   ```
   Computes the total number of catalog-visible records to calculate pagination metadata (`total`, `total_pages = ceil(total / limit)`).

2. **Paged Data Retrieval Query:**
   ```sql
   SELECT id, code, seller_id, name, description, price, stock_quantity, reserved_stock, image_url, is_active, version
   FROM products
   WHERE is_active = TRUE
   ORDER BY id ASC
   LIMIT :limit OFFSET :offset;
   ```
   Where `:offset = (page - 1) * limit`.

**Key Query Characteristics:**
- **Deterministic ordering:** Ordering by `id ASC` ensures pagination stability across successive requests without record duplication or skipping.
- **Business rule enforcement (BR1):** `WHERE is_active = TRUE` guarantees that hidden or inactive items are excluded from both the data slice and the total count.
- **Error boundary isolation:** Database query execution is wrapped in a `try...except SQLAlchemyError` block. If an unexpected database failure occurs, the error is logged server-side with stack trace details, and the API returns `500 Internal Server Error` with a generic message (`"Unable to load products right now. Please try again later."`). It **never** disguises a database error as an empty catalog (`200 OK` with `data: []`).

### 4.4 Confirmation of Database Creation and Seeding

The database setup and seeding process is verified through automated commands and test suites:

- **Database Initialization:**
  - Executed via `python -m src.database` or automatically on application startup via `init_db()` (`src/database.py`).
  - Uses `SQLModel.metadata.create_all(engine)` to create all tables (`users`, `products`, `cart_items`, `orders`, `seller_orders`, `order_items`) if they do not already exist in the SQLite database file (`marketplace.db`).
  - Enables SQLite foreign key constraint enforcement across all sessions via a SQLAlchemy connect listener (`PRAGMA foreign_keys = ON`).

- **Database Seeding:**
  - Executed via `python -m src.seed`.
  - Ensures a default seller user (`id=1`, `email="seller@marketplace.local"`, `role="seller"`) exists.
  - Seeds 45 realistic sample products across multiple categories (electronics, accessories, stationery) with valid prices, positive stock quantities, and `is_active = True`.
  - **Idempotency:** When executed on a fresh database, it reports:
    ```text
    Database tables created or verified.
    Default seller user ready (ID: 1).
    Added: 45 products
    Total products: 45
    Active products: 45
    ```
    When executed again against the same database, it detects existing product codes and inserts zero duplicates:
    ```text
    Database tables created or verified.
    Default seller user ready (ID: 1).
    Added: 0 products
    Total products: 45
    Active products: 45
    ```

- **Verification Evidence:**
  - Verified by automated tests in `tests/test_database.py` and `tests/test_products.py` (46 passing tests).
  - Four independent scenarios verified in `tests/test_issue45_scenarios.py`:
    1. Scenario 1: Display products loaded dynamically from the database.
    2. Scenario 2: At least 10 products available and displayed on default page view (seed provides 45; default page displays 20).
    3. Scenario 3: No hardcoded product arrays in frontend or API code.
    4. Scenario 4: Clean distinction between empty database (`200 OK` with `data: []`) and database error (`500 Internal Server Error`).

### 4.5 Screenshot of the Running Page

The walking skeleton UI running at `http://127.0.0.1:8000/products` displays the seeded products dynamically:

![Catalog page showing 20 of the 45 seeded products](images/issue49-catalog.png)

Additional UI states handled by the frontend implementation:
- **Empty State:** When no active products exist in the database, the page displays a clean user-friendly empty banner:
  ![Empty state for an empty products table](images/issue49-empty-state.png)
- **Error State with Retry:** When the backend API is unreachable or returns a 500 error, the page displays an error notification with a functional Retry action:
  ![Error state with Retry while the API returns 500](images/issue49-error-retry.png)

### 4.6 Environment Configuration (`.env.example`)

The application configuration is managed using `pydantic-settings` (`src/config.py`), reading configuration keys from environment variables or a local `.env` file.

The template `.env.example` provides the following defaults:

```ini
# Application Environment Configuration
# Copy this file to .env and adjust variables as needed:
# cp .env.example .env (Linux/macOS)
# Copy-Item .env.example .env (Windows PowerShell)

APP_NAME="Mini Marketplace"
APP_ENV=development
DEBUG=true
APP_HOST=127.0.0.1
APP_PORT=8000

# Database Configuration (SQLite default for local development and testing)
# In Sprint 2, SQLite database file will be created dynamically at runtime.
DATABASE_URL=sqlite:///./marketplace.db

# Security & CORS settings
# Secret key used for cryptographic signing (minimum 32 characters in production)
SECRET_KEY=dev-secret-key-do-not-use-in-production-environment
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:8000","http://127.0.0.1:8000"]
```

**Configuration Fields Explanation:**

| Variable | Default Value | Description |
|---|---|---|
| `APP_NAME` | `"Mini Marketplace"` | Human-readable application title. |
| `APP_ENV` | `development` | Operating environment (`development`, `testing`, `production`). |
| `DEBUG` | `true` | Enables FastAPI auto-reload and verbose error reporting. |
| `APP_HOST` | `127.0.0.1` | Network interface address to bind Uvicorn server. |
| `APP_PORT` | `8000` | Port number on which the HTTP server listens. |
| `DATABASE_URL` | `sqlite:///./marketplace.db` | SQLAlchemy connection string. Defaults to a local SQLite database file in the project root. Can be overridden (e.g. `sqlite:///:memory:` for in-memory testing). |
| `SECRET_KEY` | `dev-secret-key-...` | Secret string for token generation and cryptographic signing (must be overridden in production). |
| `JWT_EXPIRATION_MINUTES` | `60` | Lifetime of issued bearer access tokens. |
| `CORS_ORIGINS` | JSON list of origins | Allowed origin headers for Cross-Origin Resource Sharing. |

**Setup Procedure for Fresh Machines:**

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Initialize database and seed sample data
python -m src.seed

# 3. Start development server
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

---

## 5. Architecture Decision Records

### ADR-001: Serve the Sprint 2 web UI and REST API from one FastAPI application

| Field | Decision |
|---|---|
| Status | Accepted, 2026-10-04, after team review in PR #69 |
| Context / problem | Sprint 2 needs a walking skeleton that another team can clone and run on a fresh machine: page → API → database. The team already had a FastAPI application with the product API, and the catalog page needs only one screen of browser JavaScript. |
| Considered options | 1. One FastAPI application serves the HTML/CSS/JS page and the REST API on the same origin. 2. A separate frontend application (for example a React build) deployed next to the API. 3. Replace the stack with a server-side rendering framework. |
| Chosen option | Option 1. FastAPI serves `/products` and `/static`, and the browser calls the API on the same origin. |
| Reasons | A single install and a single start command, which keeps the setup guide short. It reuses the code that already works, needs no Node.js toolchain and no CORS setup for the page, and the web (`src/web`) and API (`src/api`) code still live in separate modules. |
| Consequences | The page and the API are released and deployed together. Frontend routing and state stay simple (vanilla JavaScript, no build step). The module boundary between `src/web` and `src/api` has to be kept by review, not by deployment. |
| Evidence | `create_app()` in `src/main.py` includes the web router and mounts `/static`; `src/web/static/products.js` calls the same-origin API; the page and its states are verified in PR #60 and PR #61 (`docs/traceability.md`, screenshots in `docs/images/issue49-*.png`). |
| Reconsider when | Several screens need shared client-side routing or state and the vanilla JavaScript becomes hard to maintain; the frontend needs its own release cycle; or the team adopts a frontend framework that needs a build step. |

### ADR-002: Use SQLite for the Sprint 2 walking skeleton, accessed through SQLModel

| Field | Decision |
|---|---|
| Status | Accepted, 2026-10-04, after team review in PR #69 |
| Context / problem | Milestone 2 needs a real, persistent database that is created and seeded the same way on every machine, including a fresh machine of another team. The walking skeleton stores one table, `products`; section 2 designs six tables with foreign keys and CHECK constraints, which #46 implements. |
| Considered options | 1. SQLite file. 2. PostgreSQL server. 3. MySQL server. Each is reached through SQLModel/SQLAlchemy and configured with `DATABASE_URL`. |
| Chosen option | Option 1. A SQLite file accessed through SQLModel on SQLAlchemy, with the location set by `DATABASE_URL` (default `sqlite:///./marketplace.db`). |
| Reasons | It is a real database that keeps data between runs. It ships with Python, so setup needs no database server, user or password, which suits local development, demos and the fresh-machine check. Tests use the same engine code with an in-memory database. |
| Consequences | SQLite allows only one writer at a time, so concurrent checkouts and running several application servers have not been tested and may need a server database. SQLite enforces CHECK constraints but not foreign keys: they are off unless each connection runs `PRAGMA foreign_keys = ON`, so the section 2 schema needs that pragma on every connection, which `src/database.py` sets in a SQLAlchemy `connect` event since #46. `init_db()` uses `create_all`, which creates missing tables but never alters existing ones: a `marketplace.db` created before a schema change keeps its old tables. A new column then fails with `no such column`, while a new constraint or foreign key is silently missing, so after a schema change the file has to be deleted and seeded again. |
| Evidence | `Product(SQLModel, table=True)` in `src/models/product.py`; `init_db()` in `src/database.py`; the seed adds 45 products and then none (`tests/test_database.py` runs both commands against a temporary SQLite file); CI run [37206917594](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/37206917594) on `8d8e231`: 45 tests passed. SQLite 3.45.1 checks on a test schema that declares the foreign key (an in-memory `users` table and `products.seller_id REFERENCES users(id)`), not on the `main` table of that time, which had none before #46: an orphan `seller_id` was accepted until `PRAGMA foreign_keys = ON` was set and rejected after, and `price = 0` was rejected by a CHECK constraint. A file whose `products` table lacked `seller_id` failed with `no such column: products.seller_id`. A file created by `main` and then opened by the #46 schema code (PR #68) kept its old `products` table and accepted `price = 0` with a NULL `seller_id`. |
| Reconsider when | Tests or demos show write contention errors or miss a non-functional requirement; the system needs more than one application server or a shared central database; a schema change must keep existing data, which needs a migration tool such as Alembic; or a new transaction or deployment requirement cannot be met with a single file. |
| If we change | Changing `DATABASE_URL` alone is not enough: add the database driver, a migration and data transfer step, and retest transactions, the schema, the seed and the test suite. |

---

## 6. What Changed Since Milestone 1

Between the delivery of Milestone 1 and the completion of Sprint 2 (Milestone 2), the team incorporated feedback from the Milestone 1 evaluation, the Sprint 1 Review, and discoveries made during initial implementation. The key architectural and process changes are documented below.

### 6.1 Synchronizing Traceability Matrix Directly with Pull Request Lifecycle

- **Context & Feedback:** During the Sprint 1 Review and Retrospective (`docs/sprint-log.md`), the team identified a recurring divergence: user story specifications, route implementations, and verification evidence in `docs/traceability.md` were lagging behind merged code, leaving the status of routes ambiguous.
- **Change Made:**
  - Established `docs/traceability.md` as the single source of truth for requirements traceability.
  - Instituted an explicit team workflow rule: any Pull Request that introduces, modifies, or completes an API route, web screen, or business rule must update `docs/traceability.md` synchronously before review approval and merge.
  - Added explicit verification evidence blocks in `docs/traceability.md` capturing test runs, CLI reproduction steps, and UI screenshots for every completed milestone task (e.g. Task 3 database API and Task 4 `/products` frontend evidence).
- **Impact:** Eliminates stale documentation, ensures continuous alignment between the project backlog and codebase, and provides traceable audit evidence for milestones.

### 6.2 Transition from In-Memory/Static Mocks to Database-Backed SQLModel Pipeline

- **Context & Feedback:** Milestone 1 defined user stories and initial prototypes with conceptual data representations, but lacked persistent data access, query semantics, or automated database lifecycle controls. Milestone 1 feedback emphasized establishing a functional walking skeleton with real database persistence.
- **Change Made:**
  - Built a centralized database session and engine lifecycle in `src/database.py` utilizing SQLModel and SQLAlchemy with SQLite (`sqlite:///./marketplace.db`).
  - Added automatic table schema generation (`init_db()`) and an idempotent seeding CLI (`src/seed.py`) with 45 structured sample products and a default seller user.
  - Replaced prototype static responses in `GET /api/v1/products` with real SQL queries executing `SELECT COUNT(*)` and paged `SELECT ... LIMIT :limit OFFSET :offset`.
  - Enforced catalog visibility rules at query time (`WHERE is_active = TRUE`) and implemented strict error boundary isolation, ensuring database exceptions return `500 Internal Server Error` and are never misreported as empty catalog results (`200 OK` with `data: []`).
- **Impact:** Delivers a fully working, reproducible walking skeleton that runs identically on local machines, CI environments, and fresh setups without requiring external database servers.

### 6.3 Relational Schema Evolution and Multi-Seller Order Decomposition

- **Context & Feedback:** In early Milestone 1 analysis, orders were conceptualized as simple buyer transactions. During detailed Sprint 2 system design (#44, #46), this model proved inadequate for a multi-vendor marketplace where a single buyer cart may contain products from different sellers, each needing independent fulfillment tracking and isolated order views.
- **Change Made:**
  - Redesigned the relational schema from simple flat orders into a normalized 6-table domain model: `users`, `products`, `cart_items`, `orders`, `seller_orders`, and `order_items`.
  - Introduced the `seller_orders` intermediate entity (`orders` 1 → N `seller_orders` 1 → N `order_items`), establishing a composite relationship where each seller manages only their sub-order partition (`UNIQUE(order_id, seller_id)`).
  - Enforced purchase-time price immutability: `order_items.unit_price` preserves the price at the moment of checkout, guaranteeing that seller revenue calculations (BR7) and best-selling metrics (BR10) remain historically accurate regardless of subsequent product price modifications.
  - Implemented optimistic concurrency control via `products.version` and relational integrity via SQLite foreign key pragma (`PRAGMA foreign_keys = ON`) and column CHECK constraints (`price > 0`, `stock_quantity >= 0`).
- **Impact:** Ensures clean architectural separation of concerns between buyers and sellers, satisfies marketplace business rules (BR5, BR6, BR7, BR9, BR10), and prevents race conditions and overselling during checkout transactions.


### 6.4 Milestone 3 API, schema and architecture changes

Sprint 3 turned the section 3 contract into running code. These changes differ
from the Milestone 1/2 design; each is in the code on `main` and covered by tests.

| Change | Before (design) | After (running) | Why | Where |
|---|---|---|---|---|
| Schema: `users.password_hash` and signed JWTs | No authentication | Scrypt password hashes; HS256 bearer tokens with the role checked against the database on every request | Protected buyer and seller routes (BR3, BR5) | #75, PR #89; `src/auth.py`, `migrate_db()` |
| API: public product code | `/products/:productId` | `/products/{productCode}` and `product_code` in cart calls; the integer id stays internal | Stable public URLs (section 3.1) | #74/#78, PR #91 |
| API/business rule: catalog stock filter | Out-of-stock products listed with a badge | Catalog returns only `stock_quantity > reserved_stock`; detail still shows "Out of stock" | BR1 refinement in Sprint 3 planning | #77, PR #90 |
| API and schema: idempotent checkout | `POST /api/v1/orders` without retry protection | Required `Idempotency-Key` header; new `orders.request_key` (unique) and `orders.request_hash` columns, added to old databases by `migrate_db()`; a replay returns the first order | A timeout retry must not create a second order | #80, PR #94 |
| API: validation status | `400` for invalid input | `422 ERR_VALIDATION` for schema-invalid input; `400` only for business rules such as `ERR_EMPTY_CART` | One status for FastAPI validation everywhere | #80, #81 |
| API: seller product body | Multipart or JSON with an uploaded `image` | JSON with an absolute `image_url`; errors grouped per field in `error.fields` | No file storage in the P0 scope; field-level errors for the form | #81, PR #95 |
| Schema: `order_history` | Not in the six-table design | Audit row for every seller order status change (`from_status`, `to_status`, `changed_by_user_id`, `note`) | Traceable fulfilment and cancellations (BR6) | #82, PR #96 |
| Architecture: browser entry | `GET /` returns JSON only | Browsers (`Accept: text/html`) get `307` to `/products`; other clients keep the JSON | Usability: the root URL opens the shop | #83, PR #97 |
| Seed: demo dataset | 45 catalog products | `python -m src.seed --demo` adds 2 buyers, 2 sellers, carts and orders in four statuses; repeat runs change nothing | Demonstrate every P0 state | #84, PR #98 |
| API: receipt names products | Receipt items carried only `product_id`, so the confirmation page showed "Product #46" and "100000 VND" | Each item also returns `product_code` and `product_name` (the current name; the price stays the purchase-time snapshot); the page shows "Demo cart item (P-DEMO-CART) × 2 · 100.000 ₫ each" | Found while drawing and checking the confirmation screen for Milestone 3 | #85; `src/services/orders.py` `receipt()`, `OrderLine` |

## US04 atomic checkout implementation (#80)

The orders API uses src/schemas/orders.py and src/services/orders.py. The service
owns the request session transaction; authentication may already have started it.
The API never commits separately or calls auto-committing cart mutations.

| Route | Access | Contract |
|---|---|---|
| POST /api/v1/orders | Buyer | Required Idempotency-Key header (1-64 chars, no surrounding whitespace); delivery JSON only; 201 created, 200 committed replay |
| GET /api/v1/orders/{orderId} | Owning buyer | 200 data; 404 ERR_ORDER_NOT_FOUND for both missing and other-buyer orders |
| /checkout | Browser shell | Cart summary, delivery input and request submission |
| /checkout/confirmation/{orderId} | Browser shell | Protected receipt API; canonical URL follows issue #80 |

Orders and seller orders start PENDING. Total is the integer-VND sum of current
product prices times cart quantities; no shipping fee. Unit prices are persisted
on order items. Items, quantities and buyer identity never come from request JSON.

Schema: nullable unique indexed orders.request_key VARCHAR(64), plus nullable
orders.request_hash VARCHAR(64), SHA-256 of normalized delivery JSON. migrate_db()
adds missing columns/index without deleting existing orders; repeating it is safe.
Fresh databases use SQLModel metadata. Replay checks key, buyer and hash before
checking the cart (which is empty after success). Same key with another buyer or
changed payload returns 409 ERR_IDEMPOTENCY_CONFLICT without exposing order data.
Stored order items are authoritative on replay; a newly refilled cart is untouched.

One transaction creates the order, seller orders and purchase-price items, decrements
stock, deletes purchased cart lines and commits. Any failure rolls back everything.
Stock UPDATE requires active status, matching products.version and
stock_quantity - reserved_stock >= quantity; it decreases physical stock and
increments version. Zero updated rows abort checkout. Cart deletion checks line ID, buyer ID, product ID
and quantity; changed/deleted lines abort. Newly added lines are not deleted.
Products are processed in product-ID order.

SQLite BUSY/LOCKED and verified committed key collisions retry after rollback,
at most five attempts. Other integrity/database failures remain database errors.
Errors retain {error: {code, message}}. Empty cart: 400 ERR_EMPTY_CART; unavailable
item: 409 ERR_PRODUCT_UNAVAILABLE; stock/version race: 409 ERR_STOCK_EXCEEDED;
cart/race exhaustion: 409 ERR_CONCURRENCY_CONFLICT; invalid fields/missing key:
422 ERR_VALIDATION; auth: 401/403; database failure: 500 ERR_DATABASE_FAILURE.
The earlier contract's 400 for schema-invalid delivery input is superseded by 422,
consistent with existing FastAPI validation. Checkout errors list field names only,
not raw inputs. See docs/evidence/us04.md for verification and manual checks.


### Review corrections for #80

The purchased-line DELETE checks buyer_id and product_id in addition to ID and
quantity, so SQLite ID reuse cannot identify another buyer/product as the original
line. A zero row count still aborts and rolls back checkout.

Checkout captures the token used to initialize its account context. Every request
uses that captured token and checks current authentication before sending and after
reading a response. A changed token blocks initial submit/retry, clears stale UI,
and offers Reload checkout. The old account's pending request stays under its own
storage key; a full reload must fetch the current account before confirmation.


## US06 seller product creation implementation (#81)

The seller products API uses `src/schemas/seller_products.py`,
`src/services/seller_products.py` and `src/api/seller_products.py`. The service owns
the request session transaction (authentication may already have read the user with
it): it adds the product, flushes, builds the response, and commits once. The router
never commits. No schema migration is needed: every stored field already exists.

| Route | Access | Contract |
|---|---|---|
| POST /api/v1/seller/products | Seller | JSON `name`, `description`, `price`, `stock_quantity`, `image_url`; `201` with `{data: listing}` |
| /seller/products/new | Browser shell | Form, field errors, success region with code, name and product link |

`ProductCreate` is separate from the `Product` table model, forbids extra fields and
trims strings. Name 1-200 characters on one line, description 1-3000; both need at
least one visible character (zero-width and other invisible characters do not count).
Price a strict integer
`1..1000000000` VND, stock a strict integer `0..1000000`, image URL an absolute
http(s) URL of at most 2048 characters. The upper numeric bounds are technical
guardrails that keep price x stock within JavaScript's safe integers; they are not
business rules from the issue. The server sets `seller_id` from the token (BR5),
`reserved_stock = 0`, `version = 1`, `is_active = true`, and a code `P-` + 18 random
upper-case hex characters. Stock 0 does not make a listing inactive.

Price and stock rules are enforced twice: by `ProductCreate` and by the CHECK
constraints on `products` (BR9). A failed request writes nothing.

Product code uniqueness comes from the UNIQUE constraint on `products.code`. After an
`IntegrityError` the service rolls back and checks whether the code now exists; only
then does it retry with a new code, at most three attempts, ending in
`409 ERR_CONCURRENCY_CONFLICT`. Any other integrity or database error is rolled back
and answers `500 ERR_DATABASE_FAILURE` without SQL details.

Validation errors for this route (POST to the exact path only) keep the common
`{error: {code, message}}` envelope and add `error.fields`, a map from field name to
messages. Errors that are not about one field (malformed JSON, a body that is not an
object, server-owned or unknown fields) are listed under `_form`. Messages never echo
the submitted input. All other routes keep their existing validation responses.
See [docs/us06-create-product.md](us06-create-product.md#11-runtime-contract-81) and
[docs/evidence/us06.md](evidence/us06.md).


## Browser entry for P0 verification (#83)

GET / with Accept containing text/html returns 307 to /products so a browser can
begin the buyer journey at the root URL. Other clients retain the original JSON
status response. No authentication is required at entry; protected APIs continue
to enforce roles. This addresses technical observation OBS01 from #83. The
integration test follows the root contract then verifies catalog through receipt;
existing root metadata tests continue to check the non-browser response.
