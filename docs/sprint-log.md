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

<!-- Goal, committed work, result, review, retro and attendance: filled in by the Sprint 2 SM (@minhnm162). -->

### Walking skeleton evidence: `/products` from the database (#45, #49)

The `/products` page calls `GET /api/v1/products`, which reads the SQLite
`products` table and returns JSON that the page renders as product cards.
Status as of 2026-10-05. The full index of Sprint 2 pull requests, reviews,
tests and gaps is in [Sprint 2 evidence](evidence/sprint2.md).

| Item | Where | Status |
|---|---|---|
| Database setup, seed data and API | [#58](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/58), [#59](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/59), [#65](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/65) | All merged; #65 on 2026-10-04 |
| `/products` page | [#60](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/60) (Task 4 of #45); cleanup and evidence in [#61](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/61) | Both merged; #61 on 2026-10-04 |
| SQL query used | [Traceability: Task 3](traceability.md#task-3-database-backed-product-api) | `WHERE is_active = TRUE ORDER BY id LIMIT :limit OFFSET :offset` |
| Backend evidence: commands, API output, checks | [Backend evidence for issue #49](traceability.md#backend-evidence-for-issue-49) | Recorded |
| Frontend evidence: checks, environment, steps | [Evidence for issue #49](traceability.md#evidence-for-issue-49) | Recorded |
| Independent check of the 4 scenarios (Task 5 of #45) | [#64](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/64) | Merged on 2026-10-04, approved by @minhnm162 |

![/products showing 20 of the 45 seeded products](images/issue49-catalog.png)

Other states: [empty catalog](images/issue49-empty-state.png),
[API error with Retry](images/issue49-error-retry.png).
