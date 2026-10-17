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


## 4. P0 flows and real-user usability ? issue #83

Owner: @minhnm162. Reviewer: @leducminh290506-eng. Status: IN PROGRESS.

### 4.1 Baseline and evidence search

Checked on 2026-10-18: branch test/83-p0-flows-usability starts from main fac5740
(PR #95 merged). US08 PR #96 at 96841c4 was still OPEN; task owner treats that
content as final. No approval/merge is claimed here. Its code was tested in a
disposable snapshot with the new #83 test and browser-entry fix, without editing
the PR or mixing its implementation into this branch.

Searched 57 local/remote refs and 90 unique Markdown blobs, PR descriptions and
repository issue comments, including #83 and #96. No completed three independent
heuristic-review records or external-user session measurements were found in that
search. #83 comments were empty. PR #88 contains wireframes and review guidance,
not completed sessions. US04 and US06 evidence explicitly excludes real-user
usability. GitHub code reviews and implementation screenshots do not substitute for
these required sessions. Evidence may exist outside the connected repository;
none is assumed or fabricated.

### 4.2 Story -> screen -> route -> endpoint -> BR -> test -> evidence matrix

Manual cases are specified in [the execution guide](issue83/plan.md). Existing
feature tests remain the detailed rule coverage; #83 adds cross-story integration.

| Story | Screen / route | Endpoint | BR | Case / automated coverage | Evidence / current status |
|---|---|---|---|---|---|
| US01 #13/#77 | Entry /; catalog /products | GET /, GET /api/v1/products | BR1 | TC01; test_p0_seller_creation_to_buyer_receipt; test_products.py, test_products_page.py | Automated HTTP/database verified; human navigation pending |
| US02 #14/#78 | /products/{productCode} | GET /api/v1/products/{productCode}, POST /api/v1/cart/items | BR1, BR2 | TC02; test_product_detail.py; P0 purchase integration | API/page delivery verified; guest-return browser check pending |
| US03 #15/#79 | /cart | GET /api/v1/cart; POST /items; PATCH/DELETE /items/{productCode} | BR2 | TC03, TC14; test_cart_api.py, test_cart_service.py, test_cart_page.py; P0 integration | Automated rule coverage; manual states/input recovery pending |
| US04 #16/#80 | /checkout; /checkout/confirmation/{orderId} | POST /api/v1/orders; GET /api/v1/orders/{orderId} | BR3, BR4, BR8 | TC04-TC06, TC13; test_checkout.py, checkout_ui.mjs; P0 integration | Multi-seller receipt, replay, ownership, stock/cart verified automatically; human session pending |
| US06 #18/#81 | /seller/products/new | POST /api/v1/seller/products | BR5, BR9 | TC07-TC08; test_seller_products.py, seller_products_ui.mjs; P0 integration | Listing-to-purchase integration verified; human session pending |
| US08 #20/#82 | /seller/orders | GET /api/v1/seller/orders; PATCH /api/v1/seller/orders/{subOrderId}/status | BR6, BR8 (restock) | TC09-TC12; test_p0_receipt_to_seller_fulfilment; PR #96 test_seller_orders.py | #83 integration passed on finalized PR snapshot; rerun on merged main; human session pending |

### 4.3 Automated verification

Commands and test environment: see issue83/plan.md. Python available in this
session is 3.11.9; repository targets 3.12, so confirm target-runtime CI separately.
DEBUG=false is set for command processes only. No .env or development database
is modified by the tests; new integration tests use temporary SQLite files.

- New HTTP/database integration: seller login -> two sellers create listings ->
  browser-entry redirect -> catalog search -> detail -> cart add/update -> buyer
  checkout -> owned receipt -> same-key replay -> committed totals/stock/items.
- PR-snapshot integration: each seller sees only its own suborder; wrong seller
  rejected; invalid transition rejected; complete both children and assert parent
  COMPLETED/completed_at; separately cancel both, assert stock restored once,
  repeated cancellation rejected and parent CANCELLED.
- On pre-US08 main, the two terminal-state cases deliberately skip with a clear
  dependency reason. Skips are not passes; the snapshot run supplements them.
- Browser-entry change: text/html GET / redirects to /products; status/API clients
  keep the existing JSON. See OBS01 in the findings register.

Verified results on 2026-10-18:

| Baseline | Check | Result |
|---|---|---|
| main fac5740 + #83 working changes | Full pytest suite | 313 passed, 2 skipped (US08 not present), 1 existing warning |
| PR #96 at 96841c4 + #83 main.py/test file | Full pytest suite on disposable snapshot | 322 passed, 1 existing warning |
| Same PR snapshot | New #83 integration cases | 3 passed, no skips |
| #83 working branch | Ruff src/tests and git diff --check | Passed |
| #83 working branch | checkout_ui.mjs and seller_products_ui.mjs via Node runtime | Passed |
| Connected UI inventory | Browser/manual session availability | No connected browser; no browser execution claimed |

The current-branch total includes the dedicated browser-entry/JSON-contract regression
in tests/test_health.py, added after the PR-snapshot run. The snapshot result remains
322 passed and does not claim that additional test was run there.

The warning is the existing Starlette/httpx deprecation. Automated checks are not
browser screenshots, human task durations or independent heuristic reviews.

### 4.4 Human verification and evidence index

| Required activity | Record | Status |
|---|---|---|
| Three independent heuristic reviews | [HR01-HR03 forms](issue83/heuristic-reviews.md) | NOT PERFORMED; reviewer names/dates/findings not supplied |
| External user sessions | [Session and metric forms](issue83/user-sessions.md) | NOT PERFORMED; planned participant count needs confirmation |
| Completion, seconds, misclicks, assistance and blockers | Same session records | NOT MEASURED; no invented zeros or success rates |
| Findings severity 0-4 and owners | [Findings/retest register](issue83/findings.md) | Technical OBS01 recorded; human findings not yet collected |
| Severity 3-4 fixes and retests | Same findings register | Must be checked after real sessions; browser retest of OBS01 pending |
| Screenshots/notes | Link actual files here by case/session ID | No #83 human screenshots captured in this session |

### 4.5 Issue acceptance checklist

- [x] Create Story -> Screen -> Route -> Endpoint -> BR -> Test Case -> Evidence matrix.
- [ ] Test buyer flow from / to receipt in a real browser (automated integration done).
- [ ] Test seller creation in a real browser for this baseline (automated integration done).
- [ ] Test seller management in a real browser (PR-snapshot automated integration done).
- [ ] Conduct 3 independent heuristic reviews.
- [ ] Record severity 0-4 and an owner for each observed human finding.
- [ ] Conduct the planned external user-testing sessions.
- [ ] Record real completion/time/misclick/blocking measurements.
- [ ] Fix and retest all observed severity 3-4 findings.
- [x] Store the current evidence index in docs/evidence/sprint3.md.

Do not close #83 until remaining real-browser/reviewer/user evidence is recorded.
