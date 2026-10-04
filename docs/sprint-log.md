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