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
| [#54 Sprint 2 wrap-up and sprint log](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/54) | @minhnm162 (SM) | Done |

### Committed

| Issue | Task | Points | Owner |
|---|---|---:|---|
| #43 | Define system architecture and ADRs | 3 | @MinhQuangQu |
| #44 | Design relational database schema and ERD | 3 | @minhnm162 |
| #45 | Story: view products from the database | 5 | @MinhQuangQu |
| #46 | Implement database schema and seed dataset | 3 | @minhnm162 |
| #47 | Define REST API contract for P0 stories | 3 | @teddywristh |
| #48 | Implement application database connection | 2 | @minhnm162 |
| #49 | Implement GET /products using real database data | 3 | @teddywristh |
| #50 | Complete Sprint 2 system design documentation | 2 | @leducminh290506-eng |
| #51 | Create fresh-machine setup guide | 2 | @MinhQuangQu |
| #52 | Verify setup on a non-author machine | 2 | @leducminh290506-eng |
| #53 | Update Sprint 2 traceability and implementation evidence | 2 | @teddywristh |
| #54 | Sprint 2 wrap-up and sprint log | 2 | @minhnm162 |
| #56 | Bootstrap runnable application skeleton | 3 | @minhnm162 |

**Total committed: 33 points** (1 User story walking skeleton 5 pts + 12 technical/doc tasks 28 pts)

### Result

| Issue | Points | Status | If not done, why |
|---|---:|---|---|
| #43 | 3 | Done | System architecture, C4 diagram and ADR-001/002 completed |
| #44 | 3 | Done | Relational database schema and ERD completed |
| #45 | 5 | Done | Product catalog reading from database delivered |
| #46 | 3 | Done | Database schema and seed dataset loaded |
| #47 | 3 | Done | REST API contract defined |
| #48 | 2 | Done | Database engine and connection error tests implemented |
| #49 | 3 | Done | GET /products served with database data and error/empty states |
| #50 | 2 | Done | System design documentation consolidated |
| #51 | 2 | Done | Setup guide written and verified |
| #52 | 2 | Done | Independent setup run completed on Windows 11 |
| #53 | 2 | Done | Traceability matrix and evidence indexed |
| #54 | 2 | Done | Sprint 2 wrap-up completed |
| #56 | 3 | Done | Runnable application skeleton bootstrapped |

**Completed: 33 points. Velocity this sprint: 33**

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

- #58 — Database setup / backend work (@MinhQuangQu)
- #59 — Database API query implementation (@MinhQuangQu)
- #60 — `/products` page and empty state (@MinhQuangQu)
- #61 — Page connected to API with loading/empty/error states (@teddywristh)
- #63 — REST API contract (@teddywristh)
- #64 — Independent verification of Issue #45 scenarios (@leducminh290506-eng)
- #65 — Catalog database setup and backend verification (@MinhQuangQu)
- #66 — Data model and ERD (@minhnm162)
- #67 — Fresh-machine setup guide (@MinhQuangQu)
- #68 — Six-table schema and seed with a demo seller (@minhnm162)
- #69 — Architecture, C4 diagram and two ADRs (@MinhQuangQu)
- #70 — Database connection and failure test (@minhnm162)
- #71 — Complete system design document (@leducminh290506-eng)
- #72 — Update Sprint 2 traceability and implementation evidence (@teddywristh)
- #73 — Sprint 2 wrap-up and sprint log (@minhnm162)

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
| At least 5 Sprint 2 issues are closed | PASS (13 closed) |
| At least 4 Sprint 2 PRs are merged | PASS (15 merged) |
| Every Sprint 2 PR has been reviewed by another team member | PASS |
| Every team member has at least one merged PR | PASS |
| Every team member has given at least one review | PASS |
| Every team member has at least one closed issue | PASS |
| Sprint 2 SM differs from Sprint 1 SM | PASS |

### Milestone 2 final check

| Requirement | Result |
|---|---|
| `docs/design.md` contains all six required sections | PASS |
| `docs/SETUP.md` exists on `main` | PASS |
| Setup guide was verified on a non-author machine | PASS |
| Walking skeleton uses a real database | PASS |
| Database seed creates at least 10 rows | PASS (45 seeded) |
| Project board is available | PASS |
| Sprint 2 committed, completed and velocity values recorded | PASS (33 points) |
| Sprint 2 minimum GitHub contribution requirements verified | PASS |
| Final submission PDF generated from merged documentation | PASS (Team01_M2.pdf) |

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
| [#86 [Chore] Sprint 3 wrap-up and handoff](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | @teddywristh (SM) | Done |

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
| [#74](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) | — | Done | Refinement completed; 13 Sprint 3 issues registered |
| [#75](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/75) | 3h | Done | JWT auth, role dependency, shared API errors, login/logout navigation, and 52 passing tests implemented |
| [#76](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/76) | 2h | Done | P0 wireframes and initial UI documentation delivered |
| [#77](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/77) | 3 | Done | US01 product catalog with search, pagination, and stock filter delivered |
| [#78](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/78) | 3 | Done | US02 product detail with productCode, out-of-stock badge, and cart entry delivered |
| [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) | 8 | Done | US03 database-backed shopping cart with buyer isolation, 4 states, stock limits delivered |
| [#80](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/80) | 8 | Done | US04 atomic checkout, idempotent replay, and order confirmation delivered |
| [#81](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/81) | 5 | Done | US06 seller product creation with field-level errors and owner token delivered |
| [#82](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/82) | 8 | Done | US08 seller order management with sub-order listing, status transitions, and restock delivered |
| [#83](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/83) | 2h | Done | Automated cross-story P0 integration flows and browser entry redirection verified |
| [#84](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/84) | 2h | Done | Repeatable demo seed scenarios, SETUP guide, and safe reset path implemented |
| [#85](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/85) | 2h | Done | Final UI documentation and Milestone 3 evidence verified with contract tests |
| [#86](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) | — | Done | Sprint 3 wrap-up, sprint log completion, and Milestone 3 submission handoff delivered |

**Completed story points: 35 points** (6 User Stories P0) + 11 hours (5 supporting technical/doc tasks). **Velocity this sprint: 35 story points** (100% completion rate).

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

### Completed issues

- [#74](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/74) — Refine backlog for Sprint 3
- [#75](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/75) — Implement authentication, navigation and shared API errors
- [#76](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/76) — Create P0 wireframes and initial UI documentation
- [#77](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/77) — US01 Complete usable product catalog
- [#78](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/78) — US02 Implement product detail and cart entry
- [#79](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/79) — US03 Implement database-backed shopping cart
- [#80](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/80) — US04 Implement atomic checkout and order confirmation
- [#81](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/81) — US06 Implement seller product creation with field errors
- [#82](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/82) — US08 Implement seller-scoped order management
- [#83](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/83) — Verify P0 flows and usability with real users
- [#84](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/84) — Update seed, SETUP and fresh-machine verification
- [#85](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/85) — Finalize UI docs and Milestone 3 evidence
- [#86](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/86) — Sprint 3 wrap-up and handoff

### Merged pull requests

| PR | Issue | Title | Author | Reviewer | Status |
|---|---|---|---|---|---|
| [#87](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/87) | #74 | chore: refine backlog for Sprint 3 | @leducminh290506-eng | @teddywristh | Merged |
| [#88](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/88) | #76 | [#76] Create P0 wireframes and initial UI documentation | @teddywristh | @leducminh290506-eng | Merged |
| [#89](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/89) | #75 | feat: implement JWT authentication and shared API errors | @leducminh290506-eng | @minhnm162 | Merged |
| [#90](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/90) | #77 | [#77] Complete usable product catalog | @teddywristh | @leducminh290506-eng | Merged |
| [#91](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/91) | #78 | [#78] Implement product detail and cart entry | @teddywristh | @MinhQuangQu | Merged |
| [#92](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/92) | #79 | feat: add cart schemas and CartService | @MinhQuangQu | @teddywristh | Merged |
| [#93](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/93) | — | Chore: Update README role member for sprint 3 | @teddywristh | @minhnm162 | Merged |
| [#94](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/94) | #80 | feat(#80): implement atomic checkout and buyer order API | @minhnm162 | @MinhQuangQu | Merged |
| [#95](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/95) | #81 | feat: add seller product creation API with field-level errors | @MinhQuangQu | @minhnm162 | Merged |
| [#96](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/96) | #82 | feat: add seller-scoped order listing and fulfilment status transitions | @leducminh290506-eng | @MinhQuangQu | Merged |
| [#97](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/97) | #83 | test(#83): cover purchase receipt and seller fulfilment flows | @minhnm162 | @leducminh290506-eng | Merged |
| [#98](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/98) | #84 | feat(#84): add repeatable P0 demo seed scenarios | @minhnm162 | @teddywristh | Merged |
| [#99](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/99) | #85 | docs: finalize the P0 UI documentation against the running screens | @MinhQuangQu | @minhnm162 | Merged |

### Project board evidence

Project board layout at Sprint Planning (2026-10-08):
![Sprint 3 Planning Board](images/sprint3-planning-board.png)

Project board layout at Sprint Review (2026-10-18):
![Sprint 3 Review Board](images/sprint3-review-board.png)

### Sprint 3 requirements

| Requirement | Result |
|---|---|
| At least 5 Sprint 3 issues are closed | PASS (13 closed) |
| At least 4 Sprint 3 PRs are merged | PASS (13 merged) |
| Every Sprint 3 PR has been reviewed by another team member | PASS |
| Every team member has at least one merged PR | PASS (@leducminh290506-eng: #87, #89, #96; @teddywristh: #88, #90, #91, #93; @MinhQuangQu: #92, #95, #99; @minhnm162: #94, #97, #98) |
| Every team member has given at least one review | PASS (@leducminh290506-eng: #88, #90, #97; @teddywristh: #87, #92, #98; @MinhQuangQu: #91, #94, #96; @minhnm162: #89, #95, #99) |
| Every team member has at least one closed issue | PASS (@leducminh290506-eng: #74, #75, #82; @teddywristh: #76, #77, #78, #86; @MinhQuangQu: #79, #81, #85; @minhnm162: #80, #83, #84) |
| Sprint 3 SM differs from Sprint 2 SM | PASS (Sprint 2: @minhnm162 → Sprint 3: @teddywristh) |

### Milestone 3 final check

| Requirement | Result |
|---|---|
| All 6 P0 user stories implemented, verified, and merged on `main` | PASS (US01, US02, US03, US04, US06, US08) |
| `docs/ui.md` contains wireframes, error tables, and contract rules | PASS |
| `/cart` contains all four required visual states | PASS (Loading, Empty, Data, Error with Retry) |
| Shared error envelope and 20 error cases documented and verified | PASS (tested by `tests/test_ui_docs_contract.py`) |
| Seed scenarios and database migrations non-destructive | PASS (`python -m src.seed --demo`) |
| Planning and Review board screenshots captured | PASS |
| Sprint 3 committed, completed and velocity values recorded | PASS (35 story points + 11 hours) |
| Sprint 3 minimum GitHub contribution requirements verified | PASS |
| Final submission PDF generated from merged documentation | PASS (`Team01_M3.pdf`) |

### Sprint Review

- **What we demonstrated:**
  - All six P0 user stories functioning seamlessly end-to-end:
    - **US01 Product Catalog:** Keyword search, pagination (20/page), out-of-stock exclusion, loading/empty/error states.
    - **US02 Product Detail:** Resolution by public `productCode`, stock badge, and authenticated cart entry with login redirect and parameter preservation.
    - **US03 Shopping Cart:** Database-backed cart items isolated per buyer, live quantity increments, available stock enforcement, and four visual states.
    - **US04 Checkout & Order Confirmation:** Atomic multi-seller order placement, `orders.request_key` idempotency protection against duplicate network requests, buyer-isolated receipts, and total recalculation without hidden shipping fees.
    - **US06 Seller Product Creation:** Form validation with field-level error messages, price/stock bounds checks, automatic unique `productCode` assignment, and catalog linking.
    - **US08 Seller Order Management:** Seller-scoped sub-order dashboard, status filtering, order lifecycle transitions (`PENDING` → `PROCESSING` → `SHIPPED` → `COMPLETED`), single-pass cancellation restock, and immutable audit logs in `order_history`.
  - Full automated suite: 359 backend tests, 2 frontend Node scripts, and 24 contract tests passing without regression.
- **Feedback received:**
  - Clarify on the cart page that checkout does not assess shipping fees to prevent buyer confusion.
  - Ensure cancellation restock executes strictly once and protects against duplicate cancellation attempts.
- **Backlog changes as a result:**
  - Standardized UI error messages across all pages according to `docs/ui.md`.
  - Documented known non-blocking visual gaps (UI-G1 to UI-G7) as backlog candidates for Sprint 4 polish.

### Retrospective

| Keep doing | Stop doing | Start doing |
|---|---|---|
| Enforcing contract tests between documentation and runtime (`tests/test_ui_docs_contract.py`) | Deferring end-to-end integration flows to the end of the sprint | Defining shared demo seed fixtures upfront at sprint kickoff |
| Rotating Scrum Master each sprint on schedule | Making manual schema tweaks without migration automation | Pairing on complex database concurrency tests (e.g. optimistic locking and idempotency replay) |

**One concrete action for next sprint (with an owner):**  
Establish automated end-to-end regression test suites for P1 stories (US05 buyer order history, US07 update product, US09 revenue analytics) right after initial API merges. Owner: `@minhnm162`.

### Attendance

| Member | Planning | Review | Retro |
|---|---|---|---|
| @leducminh290506-eng | Yes | Yes | Yes |
| @QuangMinhQu | Yes | Yes | Yes |
| @teddywristh | Yes | Yes | Yes |
| @minhnm162 | Yes | Yes | Yes |