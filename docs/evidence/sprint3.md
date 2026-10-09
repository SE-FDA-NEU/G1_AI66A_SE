# Sprint 3 Evidence

This document records the repository evidence, planning records, and backlog refinement decisions used to verify the Sprint 3 administrative and architectural requirements.

## Sprint 3 Summary

| Item | Value |
|---|---|
| Sprint dates | 2026-10-05 to 2026-10-18 |
| Product Owner | `@leducminh290506-eng` |
| Scrum Master | `@teddywristh` |
| Sprint 2 Scrum Master | `@minhnm162` |
| Scrum Master rotation | PASS (Sprint 1: `@leducminh290506-eng` → Sprint 2: `@minhnm162` → Sprint 3: `@teddywristh`) |
| Planning meeting date | 2026-10-08 |
| Total committed story points | 35 points (6 P0 user stories) + 11 hours (5 supporting technical/doc tasks) |

---

## 1. Backlog Refinement & Issue Registry (Issue #74)

All 13 Sprint 3 issues are registered on GitHub with clear ownership and assigned reviewers:

| Issue | Title | Type | Points / Est | Assignee / Owner | Reviewer |
|---|---|---|---:|---|---|
| [#74](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) | [Chore] Refine backlog for Sprint 3 | Chore | — | `@leducminh290506-eng` (PO) | `@teddywristh` (SM) |
| [#75](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/75) | [Task] Implement authentication, navigation and shared API errors | Task | 3h | `@leducminh290506-eng` | `@minhnm162` |
| [#76](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/76) | [Task] Create P0 wireframes and initial UI documentation | Task | 2h | `@teddywristh` | `@leducminh290506-eng` |
| [#77](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/77) | [Story] US01 Complete usable product catalog | Story | 3 | `@teddywristh` | `@leducminh290506-eng` |
| [#78](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/78) | [Story] US02 Implement product detail and cart entry | Story | 3 | `@teddywristh` | `@MinhQuangQu` |
| [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) | [Story] US03 Implement database-backed shopping cart | Story | 8 | `@MinhQuangQu` | `@teddywristh` |
| [#80](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/80) | [Story] US04 Implement atomic checkout and order confirmation | Story | 8 | `@minhnm162` | `@MinhQuangQu` |
| [#81](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/81) | [Story] US06 Implement seller product creation with field errors | Story | 5 | `@MinhQuangQu` | `@minhnm162` |
| [#82](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/82) | [Story] US08 Implement seller-scoped order management | Story | 8 | `@leducminh290506-eng` | `@MinhQuangQu` |
| [#83](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/83) | [Task] Verify P0 flows and usability with real users | Task | 2h | `@minhnm162` | `@leducminh290506-eng` |
| [#84](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/84) | [Task] Update seed, SETUP and fresh-machine verification | Task | 2h | `@minhnm162` | `@teddywristh` |
| [#85](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/85) | [Task] Finalize UI docs and Milestone 3 evidence | Task | 2h | `@MinhQuangQu` | `@minhnm162` |
| [#86](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | [Chore] Sprint 3 wrap-up and handoff | Chore | — | `@teddywristh` (SM) | `@leducminh290506-eng` (PO) |

---

## 2. Core Design and Schema Decisions Finalized

### 2.1 Public Product Identification (`productCode`)
- **Internal Database Key:** `Product.id` (INTEGER, autoincrement PK).
- **Public URL & API Key:** `Product.code` (VARCHAR(20), UNIQUE).
- **Route Contract:** Public endpoints (`/products/{productCode}`, `GET /api/v1/products/{productCode}`, `PATCH /api/v1/cart/items/{productCode}`) resolve products by unique string `code`. Internal integer IDs are not exposed in public URLs.

### 2.2 Stock Visibility and Validation Rules
- **Catalog Visibility:** Catalog query filters on `is_active = TRUE AND stock_quantity > reserved_stock`. Out-of-stock products are hidden from the catalog grid.
- **Product Detail Behavior:** Direct navigation to an out-of-stock product detail page displays an "Out of stock" badge and disables the Add to Cart button.
- **Cart Stock Semantics:** Adding an item to `/cart` does not reserve physical stock. Available stock is validated on add/update and revalidated atomically during checkout.
- **Atomic Checkout & Optimistic Locking:** Concurrency is controlled via `products.version`. Stock reduction occurs atomically:
  ```sql
  UPDATE products
  SET stock_quantity = stock_quantity - :qty,
      version = version + 1
  WHERE id = :product_id
    AND version = :expected_version
    AND stock_quantity >= :qty;
  ```
- **Cancellation Restock:** Cancelling a `PENDING` seller order restores stock exactly once.

### 2.3 Shared Error Envelope
All API error responses use the standardized schema:
```json
{
  "error": {
    "code": "ERR_CODE",
    "message": "Human-readable explanation"
  }
}
```
HTTP status code mapping:
- `400`: `ERR_INVALID_QUANTITY`, `ERR_INVALID_TRANSITION`, `ERR_EMPTY_CART`
- `401`: `ERR_AUTH_REQUIRED`, `ERR_INVALID_TOKEN`, `ERR_EXPIRED_TOKEN`
- `403`: `ERR_SELLER_REQUIRED`, `ERR_RESOURCE_OWNER`
- `404`: `ERR_PRODUCT_NOT_FOUND`, `ERR_CART_ITEM_NOT_FOUND`, `ERR_ORDER_NOT_FOUND`
- `409`: `ERR_STOCK_EXCEEDED`, `ERR_PRODUCT_UNAVAILABLE`, `ERR_CONCURRENCY_CONFLICT`
- `422`: `ERR_VALIDATION`
- `500`: `ERR_DATABASE_FAILURE`, `ERR_INTERNAL`

Internal database details, tracebacks, and raw SQL queries are excluded from client payloads.

### 2.4 Order & Sub-Order State Machine
- **Seller Order (`seller_orders`):**
  - Initial state: `PENDING`.
  - Allowed transitions: `PENDING` → `PROCESSING` → `SHIPPED` → `COMPLETED`.
  - Cancellation transition: `PENDING` → `CANCELLED` (restores stock once).
  - Illegal transitions: Reject with `400 Bad Request` (`ERR_INVALID_TRANSITION`).
- **Marketplace Order (`orders`):**
  - Aggregated dynamically from constituent `seller_orders`:
    - `COMPLETED` when all child seller orders are `COMPLETED`.
    - `CANCELLED` when all child seller orders are `CANCELLED`.
    - `PROCESSING` when at least one child seller order is `PROCESSING` or `SHIPPED`.
    - `PENDING` when all child seller orders are `PENDING`.

### 2.5 Database Schema Enhancements
1. **`users.password_hash`:**
   - Field: `password_hash: str = Field(max_length=255)`
   - Purpose: Store secure password hashes for authentication (`POST /api/v1/auth/login`).
2. **`orders.request_key`:**
   - Field: `request_key: str | None = Field(default=None, unique=True, index=True, max_length=64)`
   - Purpose: Support idempotent checkout requests, preventing duplicate orders upon network retries.
3. **`order_history` Table:**
   - Schema:
     - `id`: INTEGER PK
     - `seller_order_id`: INTEGER FK → `seller_orders.id`
     - `from_status`: VARCHAR(30)
     - `to_status`: VARCHAR(30)
     - `changed_by_user_id`: INTEGER FK → `users.id`
     - `note`: TEXT (optional)
     - `created_at`: DATETIME

---

## 3. Sprint Planning Evidence

- **Planning Meeting Date:** 2026-10-08
- **Participants:**
  - `@leducminh290506-eng` (Product Owner)
  - `@teddywristh` (Scrum Master)
  - `@minhnm162` (Developer)
  - `@QuangMinhQu` (Developer)
- **Attendance Record:** All 4 members attended.
- **Backlog Refinement Status:** All 13 issues reviewed, acceptance criteria agreed upon, dependencies mapped, and story points committed.
