# Sprint log

One section per sprint. Fill it in **during** the sprint, not the night before
the milestone deadline - the commit timestamps on this file are part of the
evidence that the process was real.

---

## Sprint 1 - 2026-09-07 to 2026-09-20

<!-- Sprint 1: weeks 5-6 | Sprint 2: 7-8 | Sprint 3: 9-10 | Sprint 4: 11-12 | Sprint 5: 13-14 -->

### Sprint goal

Define comprehensive user story specifications, acceptance criteria, and traceability matrix for core marketplace features (Product Discovery, Cart, Ordering, Product Management, Order Management).

### Two mandatory chore issues

| Issue | Assignee | Status |
|-------|-----------|----------|
| [Chore] Refine backlog cho Sprint 1 ([#37](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/37)) | @leducminh290506-eng (PO) | Done |
| [Chore] Sprint 1 wrap-up ([#38](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/38)) | @leducminh290506-eng (SM) | Done |

### Committed

| Issue | Story | Points | Owner |
|-------|-------|--------|-------|
| [#13](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/13) | US01 - Browse product catalog | 3 | @QuangMinhQu |
| [#14](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/14) | US02 - View product details | 2 | @leducminh290506-eng |
| [#15](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/15) | US03 - Add and manage products in shopping cart | 5 | @minhnm162 |
| [#16](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/16) | US04 - Place an order from shopping cart | 5 | @Ted Nguyen |
| [#17](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/17) | US05 - View buyer order history | 3 | @QuangMinhQu |
| [#18](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/18) | US06 - Create product listing | 5 | @leducminh290506-eng |
| [#19](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/19) | US07 - Update product info and stock | 3 | @minhnm162 |
| [#20](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/20) | US08 - Seller order management | 5 | @Ted Nguyen |
| [#21](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/21) | US09 - Seller revenue analytics | 5 | @QuangMinhQu |
| [#22](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/22) | US10 - Seller views best-selling products | 3 | @minhnm162 |

**Total committed: 39 points**

### Result

| Issue | Points | Status | If not done, why |
|-------|--------|--------|------------------|
| [#13](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/13) | 3 | Done | |
| [#14](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/14) | 2 | Done | |
| [#15](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/15) | 5 | Done | |
| [#16](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/16) | 5 | Done | |
| [#17](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/17) | 3 | Done | |
| [#18](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/18) | 5 | Done | |
| [#19](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/19) | 3 | Done | |
| [#20](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/20) | 5 | Done | |
| [#21](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/21) | 5 | Done | |
| [#22](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/22) | 3 | Done | |

**Completed: 39 points. Velocity this sprint: 39**

### Sprint Review

- What we demonstrated: Completed user story documentation (US01-US10) with acceptance criteria, domain rules, flowcharts, and updated traceability mapping for US02.
- Feedback received: Ensure traceability matrix status is synchronized with PR completion status when closing issues via PR.
- Backlog changes as a result: Refined acceptance criteria and edge case definitions across user story files.

### Retrospective

| Keep doing | Stop doing | Start doing |
|------------|------------|-------------|
| Thorough user story spec reviews | Delaying traceability status updates | Synchronizing traceability matrix immediately upon PR merge |

**One concrete action for next sprint (with an owner):**
Ensure PR reviews include explicit verification of traceability.md updates before approving (@leducminh290506-eng).

### Attendance

| Member | Planning | Review | Retro |
|--------|----------|--------|-------|
| @Ted Nguyen | Yes | Yes | Yes |
| @QuangMinhQu | Yes | Yes | Yes |
| @minhnm162 | Yes | Yes | Yes |
| @leducminh290506-eng | Yes | Yes | Yes |

---

## Sprint 2 - 2026-09-21 to 2026-10-04

### Sprint goal

Complete the Mini Marketplace system design and deliver a working walking skeleton in which the `/products` page retrieves product data from a real SQLite database.

### Roles

- Product Owner: `@leducminh290506-eng`
- Scrum Master: `@minhnm162`

Sprint 2 uses a different Scrum Master from Sprint 1.

### Two mandatory chore issues

| Issue | Assignee | Status |
|---|---|---|
| [Chore] Refine backlog for Sprint 2 | @leducminh290506-eng (PO) | Done |
| [#54 Sprint 2 wrap-up and sprint log](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/54) | @minhnm162 (SM) | In Progress |

### Committed

| Issue | Task | Points | Owner |
|---|---|---:|---|
| #43 | Define system architecture and ADRs | [EDIT] | [EDIT] |
| #44 | Design relational database schema and ERD | [EDIT] | @minhnm162 |
| #45 | Story: view products from the database | [EDIT] | [EDIT] |
| #46 | Implement database schema and seed dataset | [EDIT] | [EDIT] |
| #47 | Define REST API contract for P0 stories | [EDIT] | [EDIT] |
| #48 | Implement application database connection | [EDIT] | @minhnm162 |
| #49 | Implement GET /products using real database data | [EDIT] | [EDIT] |
| #50 | Complete Sprint 2 system design documentation | [EDIT] | [EDIT] |
| #51 | Create fresh-machine setup guide | [EDIT] | [EDIT] |
| #52 | Verify setup on a non-author machine | [EDIT] | [EDIT] |
| #53 | Update Sprint 2 traceability and implementation evidence | [EDIT] | [EDIT] |
| #54 | Sprint 2 wrap-up and sprint log | [EDIT] | @minhnm162 |
| #56 | Bootstrap runnable application skeleton | [EDIT] | [EDIT] |

**Total committed: [EDIT] points**

### Result

| Issue | Points | Status | If not done, why |
|---|---:|---|---|
| #43 | [EDIT] | Done | |
| #44 | [EDIT] | Done | |
| #45 | [EDIT] | Done | |
| #46 | [EDIT] | Done | |
| #47 | [EDIT] | Done | |
| #48 | [EDIT] | Done | |
| #49 | [EDIT] | Done | |
| #50 | [EDIT] | Done | |
| #51 | [EDIT] | Done | |
| #52 | [EDIT] | Done | |
| #53 | [EDIT] | Done | |
| #54 | [EDIT] | In Progress | Sprint wrap-up is being completed |
| #56 | [EDIT] | Done | |

**Completed: [EDIT] points. Velocity this sprint: [EDIT]**

### Completed issues

- #43 — Define system architecture and ADRs
- #44 — Design relational database schema and ERD
- #45 — Story: view products from the database
- #46 — Implement database schema and seed dataset for walking skeleton
- #47 — Define REST API contract for Mini Marketplace P0 stories
- #48 — Implement application database connection for walking skeleton
- #49 — Implement GET /products using real database data
- #50 — Complete Sprint 2 system design documentation
- #51 — Create fresh-machine setup guide for Mini Marketplace
- #52 — Verify Mini Marketplace setup on a non-author machine
- #53 — Update Sprint 2 traceability and implementation evidence
- #56 — Bootstrap runnable application skeleton

### Merged pull requests

The full Sprint 2 pull-request index is recorded in [Sprint 2 evidence](evidence/sprint2.md).

Known merged Sprint 2 PRs include:

- #58 — Database setup / backend work
- #59 — Database-related implementation
- #60 — `/products` page
- #61 — Walking skeleton cleanup and evidence
- #64 — Independent verification of Issue #45 scenarios
- #65 — Database/schema integration

[EDIT: add any remaining merged Sprint 2 PRs]

### Walking skeleton evidence

The `/products` page calls `GET /api/v1/products`, which reads the SQLite `products` table and returns JSON that the page renders as product cards.

| Item | Evidence |
|---|---|
| Database setup and seed | `python -m src.seed` |
| Seed result | 1 demo seller and 45 products |
| Product API | `GET /api/v1/products` |
| Frontend route | `GET /products` |
| Database | SQLite |
| Independent walking-skeleton verification | PR #64 |

![Products page](images/issue49-catalog.png)

Additional states:

- [Empty catalog](images/issue49-empty-state.png)
- [API error with Retry](images/issue49-error-retry.png)

### Sprint 2 requirements

| Requirement | Result |
|---|---|
| At least 5 Sprint 2 issues are closed | PASS |
| At least 4 Sprint 2 PRs are merged | PASS |
| Every Sprint 2 PR has been reviewed by another team member | [VERIFY] |
| Every team member has at least one merged PR | [VERIFY] |
| Every team member has given at least one review | [VERIFY] |
| Every team member has at least one closed issue | [VERIFY] |
| Sprint 2 SM differs from Sprint 1 SM | PASS |

### Milestone 2 final check

| Requirement | Result |
|---|---|
| `docs/design.md` contains all six required sections | PASS |
| `docs/SETUP.md` exists on `main` | PASS |
| Setup guide was verified on a non-author machine | PASS |
| Walking skeleton uses a real database | PASS |
| Database seed creates at least 10 rows | PASS |
| Project board is available | PASS |
| Sprint 2 committed, completed and velocity values recorded | [PENDING POINTS] |
| Sprint 2 minimum GitHub contribution requirements verified | [VERIFY] |
| Final submission PDF generated from merged documentation | [FINAL SUBMISSION STEP] |

### Sprint Review

- What we demonstrated: a complete walking skeleton from `/products` → FastAPI → SQLite → browser, together with the Sprint 2 architecture, data model, API design, setup guide and implementation evidence.
- Feedback received: database schema, API contract and setup documentation needed to remain consistent with the merged implementation.
- Backlog changes as a result: schema, seed, database connectivity, API contract and fresh-machine setup work were aligned before the Sprint 2 submission.

### Retrospective

| Keep doing | Stop doing | Start doing |
|---|---|---|
| Reviewing PRs before merge | Allowing documentation to become stale after code changes | Updating design and setup evidence immediately after implementation changes |

**One concrete action for next sprint:**  
Keep `docs/design.md`, `docs/SETUP.md`, and `docs/traceability.md` synchronized with every merged implementation PR. Owner: `@minhnm162`.

### Attendance

| Member | Planning | Review | Retro |
|---|---|---|---|
| @leducminh290506-eng | Yes | Yes | Yes |
| @QuangMinhQu | Yes | Yes | Yes |
| @teddywristh | Yes | Yes | Yes |
| @minhnm162 | Yes | Yes | Yes |

---

## Sprint 3 - 2026-10-05 to 2026-10-18

### Sprint goal

Implement and verify all core P0 marketplace user stories (US01 Product Catalog, US02 Product Detail, US03 Shopping Cart, US04 Checkout, US06 Seller Product Creation, US08 Seller Order Management), complete authentication and shared API error envelopes, finalize UI wireframes and usability validation, and deliver Milestone 3.

### Roles

- Product Owner: `@leducminh290506-eng`
- Scrum Master: `@teddywristh`

Sprint 3 Scrum Master (`@teddywristh`) rotates from Sprint 2 Scrum Master (`@minhnm162`), adhering to team policy.

### Two mandatory chore issues

| Issue | Assignee | Status |
|---|---|---|
| [#74 [Chore] Refine backlog for Sprint 3](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) | @leducminh290506-eng (PO) | Done |
| [#86 [Chore] Sprint 3 wrap-up and handoff](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | @teddywristh (SM) | To Do |

### Committed

| Issue | Task / Story | Type | Points / Est | Owner | Reviewer | Dependencies |
|---|---|---|---:|---|---|---|
| [#74](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) | Refine backlog for Sprint 3 | Chore | — | @leducminh290506-eng | @teddywristh | None |
| [#75](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/75) | Implement authentication, navigation and shared API errors | Task | 3h | @leducminh290506-eng | @minhnm162 | #74 |
| [#76](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/76) | Create P0 wireframes and initial UI documentation | Task | 2h | @teddywristh | @leducminh290506-eng | #74 |
| [#77](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/77) | US01 Complete usable product catalog | Story | 3 | @teddywristh | @leducminh290506-eng | #75, #76 |
| [#78](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/78) | US02 Implement product detail and cart entry | Story | 3 | @teddywristh | @MinhQuangQu | #75, #77 |
| [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) | US03 Implement database-backed shopping cart | Story | 8 | @MinhQuangQu | @teddywristh | #75, #78 |
| [#80](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/80) | US04 Implement atomic checkout and order confirmation | Story | 8 | @minhnm162 | @MinhQuangQu | #75, #79 |
| [#81](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/81) | US06 Implement seller product creation with field errors | Story | 5 | @MinhQuangQu | @minhnm162 | #75, #76 |
| [#82](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/82) | US08 Implement seller-scoped order management | Story | 8 | @leducminh290506-eng | @MinhQuangQu | #75, #80 |
| [#83](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/83) | Verify P0 flows and usability with real users | Task | 2h | @minhnm162 | @leducminh290506-eng | #77, #78, #79, #80, #81, #82 |
| [#84](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/84) | Update seed, SETUP and fresh-machine verification | Task | 2h | @minhnm162 | @teddywristh | #75, #80, #82 |
| [#85](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/85) | Finalize UI docs and Milestone 3 evidence | Task | 2h | @MinhQuangQu | @minhnm162 | #76, #83, #84 |
| [#86](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | Sprint 3 wrap-up and handoff | Chore | — | @teddywristh | @leducminh290506-eng | All preceding issues |

**Total committed story points: 35 points** (6 User Stories P0) + 11 hours (5 supporting technical/doc tasks).

### Result

| Issue | Points / Est | Status | If not done, why |
|---|---:|---|---|
| [#74](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) | — | Done | Refinement completed |
| [#75](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/75) | 3h | To Do | |
| [#76](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/76) | 2h | To Do | |
| [#77](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/77) | 3 | To Do | |
| [#78](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/78) | 3 | To Do | |
| [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) | 8 | To Do | |
| [#80](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/80) | 8 | To Do | |
| [#81](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/81) | 5 | To Do | |
| [#82](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/82) | 8 | To Do | |
| [#83](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/83) | 2h | To Do | |
| [#84](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/84) | 2h | To Do | |
| [#85](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/85) | 2h | To Do | |
| [#86](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | — | To Do | |

### Backlog Refinement Decisions (Issue #74)

During Sprint 3 Backlog Refinement, the team finalized the following technical and architectural decisions:

1. **`productCode` Resolution:**
   - Database internal primary key is `Product.id` (INTEGER, autoincrement).
   - Public product identifier is `Product.code` (VARCHAR(20), UNIQUE, e.g. `P-100`).
   - All customer-facing routes (`/products/{productCode}`), API endpoints (`GET /api/v1/products/{productCode}`), and cart operation payloads (`product_code`) resolve entities via `Product.code`. Integer IDs are never exposed in public product URLs.

2. **Stock Rules & Availability:**
   - Catalog query filters: only active products with available inventory (`is_active = TRUE AND stock_quantity > reserved_stock`) appear in the public catalog `/products`.
   - Out-of-stock items: items with zero available stock remain navigable via direct link `/products/{productCode}` but show an "Out of stock" badge and have the "Add to Cart" button disabled.
   - Non-reservation in cart: adding items to `/cart` does not reserve physical stock. Available stock is validated on add/update and revalidated atomically during checkout.
   - Optimistic concurrency control: checkout verifies and decrements stock atomically using `products.version` (`WHERE id = :id AND version = :expected_version AND stock_quantity >= :qty`).
   - Cancellation restock: when a `PENDING` seller order is cancelled, stock is incremented back exactly once.

3. **Standard Error Envelope:**
   - All REST API failure responses adhere strictly to the common error format:
     ```json
     {
       "error": {
         "code": "ERR_CODE",
         "message": "Human-readable explanation"
       }
     }
     ```
   - Standard error codes:
     - `400 Bad Request`: `ERR_INVALID_QUANTITY`, `ERR_INVALID_TRANSITION`, `ERR_EMPTY_CART`.
     - `401 Unauthorized`: `ERR_AUTH_REQUIRED`, `ERR_INVALID_TOKEN`, `ERR_EXPIRED_TOKEN`.
     - `403 Forbidden`: `ERR_SELLER_REQUIRED`, `ERR_RESOURCE_OWNER`.
     - `404 Not Found`: `ERR_PRODUCT_NOT_FOUND`, `ERR_CART_ITEM_NOT_FOUND`, `ERR_ORDER_NOT_FOUND`.
     - `409 Conflict`: `ERR_STOCK_EXCEEDED`, `ERR_PRODUCT_UNAVAILABLE`, `ERR_CONCURRENCY_CONFLICT`.
     - `422 Unprocessable Entity`: `ERR_VALIDATION`.
     - `500 Internal Server Error`: `ERR_DATABASE_FAILURE`, `ERR_INTERNAL`.
   - Security rule: raw exceptions, database stack traces, and internal SQL statements are never leaked in API error responses.

4. **Order & Sub-Order State Machine:**
   - Initial state: `PENDING`.
   - Seller order fulfillment lifecycle: `PENDING` → `PROCESSING` → `SHIPPED` → `COMPLETED`.
   - Cancellation lifecycle: `PENDING` → `CANCELLED` (triggers automatic single-pass stock restoration).
   - Strict transition validation: illegal state transitions (e.g., `SHIPPED` → `PENDING`, `CANCELLED` → `PROCESSING`, `COMPLETED` → `CANCELLED`) are rejected with `400 Bad Request` (`ERR_INVALID_TRANSITION`).
   - Marketplace parent order status (`orders.status`) is computed from child `seller_orders`:
     - `COMPLETED` when all seller orders are `COMPLETED`.
     - `CANCELLED` when all seller orders are `CANCELLED`.
     - `PROCESSING` when at least one seller order has advanced past `PENDING`.

5. **Database Schema Enhancements:**
   - `users.password_hash`: added `password_hash VARCHAR(255) NOT NULL` to table `users` to support secure credentials and JWT login (`POST /api/v1/auth/login`).
   - `orders.request_key`: added `request_key VARCHAR(64) NULL UNIQUE INDEX` to table `orders` to enforce idempotent checkout transactions and prevent duplicate order placement on retry.
   - `order_history`: added audit table `order_history` (`id`, `seller_order_id`, `from_status`, `to_status`, `changed_by_user_id`, `note`, `created_at`) to record every seller order status transition immutably.

### Dependency Graph & Critical Path

```text
[#74 Refine Backlog]
       │
       ├──> [#75 Auth & Shared Errors] ──────────────┐
       │                                             │
       └──> [#76 P0 Wireframes & UI Docs] ──┐        │
                                            │        │
             ┌──────────────────────────────┘        │
             │                                       │
             ▼                                       ▼
     [#77 US01 Catalog]                      [#81 US06 Product Creation]
             │                                       │
             ▼                                       │
     [#78 US02 Product Detail]                       │
             │                                       │
             ▼                                       │
     [#79 US03 Shopping Cart]                        │
             │                                       │
             ▼                                       │
     [#80 US04 Checkout]                             │
             │                                       │
             ▼                                       ▼
     [#82 US08 Seller Orders] ───────────────> [#84 Seed & Setup]
             │                                       │
             └───────────────────┬───────────────────┘
                                 │
                                 ▼
                     [#83 Usability Testing]
                                 │
                                 ▼
                     [#85 Milestone 3 Docs & Evidence]
                                 │
                                 ▼
                     [#86 Sprint 3 Wrap-up]
```

### Sprint Planning Evidence

- **Planning Meeting Date:** 2026-10-08
- **Location:** Online (Team Discord / Google Meet)
- **Attendance:**
  - `@leducminh290506-eng` (Product Owner): Present
  - `@teddywristh` (Scrum Master): Present
  - `@minhnm162` (Developer): Present
  - `@QuangMinhQu` (Developer): Present
- **Velocity & Capacity Assessment:**
  - Sprint 1 velocity: 39 story points.
  - Sprint 2 focus: Architecture, system design, and walking skeleton.
  - Sprint 3 commitment: 35 story points across 4 developers (average ~8.75 points per member), well within historical delivery capacity.
- **Identified Risks & Mitigations:**
  - *Risk 1 (Checkout Concurrency):* High concurrency checkout on the same inventory item may cause overselling. *Mitigation:* Enforce optimistic locking via `products.version` in an atomic database transaction.
  - *Risk 2 (Cross-seller Privacy):* Sellers might query or alter orders of other sellers. *Mitigation:* All seller endpoints extract `seller_id` exclusively from validated JWT claims and verify ownership against `seller_orders.seller_id`.
  - *Risk 3 (Documentation Drift):* Documentation lagging behind rapid implementation. *Mitigation:* SM (@teddywristh) enforces Definition of Done criterion 8 (traceability update required before PR merge).

### Attendance

| Member | Planning | Review | Retro |
|---|---|---|---|
| @leducminh290506-eng | Yes | Pending | Pending |
| @QuangMinhQu | Yes | Pending | Pending |
| @teddywristh | Yes | Pending | Pending |
| @minhnm162 | Yes | Pending | Pending |