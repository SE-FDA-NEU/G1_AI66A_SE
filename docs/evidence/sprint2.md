# Sprint 2 Evidence

This index collects the Sprint 2 evidence: which issue each pull request
delivered, who approved it, the test results, the walking skeleton checks and
the screenshots. Each item records the commit it ran on, and later commits do
not change that result. The [traceability matrix](../traceability.md) links
each P0 story to the items here.

Status as of 2026-10-05, `main` at `37e80c3`.

## 1. Issues and pull requests

"Approved by" lists the reviews with the state Approved on GitHub. A review
request, an @mention or a merge is not counted as a review.

| Issue | Deliverable | PR | Author | Approved by | Merged (merge commit) |
|---|---|---|---|---|---|
| [#56](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/56) | Runnable application skeleton | [#57](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/57) | @leducminh290506-eng | [@teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/57#pullrequestreview-5375509789) | 2026-10-01 (`d672e79`) |
| [#45](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/45) | Product database and seed data | [#58](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/58) | @minhnm162 | [@teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/58#pullrequestreview-5400611015), [@MinhQuangQu](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/58#pullrequestreview-5401174218) | 2026-10-03 (`377bfb9`) |
| [#45](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/45) | Product list API and query | [#59](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/59) | @teddywristh | [@leducminh290506-eng](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/59#pullrequestreview-5394640192) | 2026-10-02 (`967c9a3`) |
| [#45](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/45) | `/products` page and empty state | [#60](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/60) | @MinhQuangQu | None; merged by the author (gap G6) | 2026-10-03 (`73820f4`) |
| [#49](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/49) | Page connected to the API, with loading, empty and error states | [#61](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/61) | @teddywristh | [@leducminh290506-eng](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/61#pullrequestreview-5404089293) | 2026-10-04 (`f73f220`) |
| [#47](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/47) | REST API contract | [#63](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/63) | @teddywristh | [@minhnm162](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/63#pullrequestreview-5406514009) | 2026-10-04 (`8d8e231`); the merge dropped the contract from `docs/design.md`, and #69 restored it |
| [#45](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/45) | Independent check of the four scenarios (Task 5) | [#64](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/64) | @leducminh290506-eng | [@minhnm162](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/64#pullrequestreview-5404429860) | 2026-10-04 (`840ad96`) |
| [#49](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/49) | Catalog database setup and backend verification | [#65](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/65) | @MinhQuangQu | [@leducminh290506-eng](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/65#pullrequestreview-5404055202) | 2026-10-04 (`bcf1697`) |
| [#44](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/44) | Data model and ERD | [#66](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/66) | @minhnm162 | [@MinhQuangQu](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/66#pullrequestreview-5405795708) | 2026-10-04 (`cc5ff7d`) |
| [#51](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/51) | Fresh-machine setup guide | [#67](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/67) | @MinhQuangQu | [@minhnm162](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/67#pullrequestreview-5407055440) | 2026-10-04 (`00de729`) |
| [#46](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/46) | Six-table schema and seed with a demo seller | [#68](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/68) | @minhnm162 | [@MinhQuangQu](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/68#pullrequestreview-5406983241), [@teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/68#pullrequestreview-5406983251) | 2026-10-04 (`8bb938f`) |
| [#43](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/43) | Architecture, C4 diagram and two ADRs | [#69](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/69) | @MinhQuangQu | [@minhnm162](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/69#pullrequestreview-5406848795) | 2026-10-04 (`325142d`) |
| [#48](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/48) | Database connection and its failure test | [#70](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/70) | @minhnm162 | [@MinhQuangQu](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/70#pullrequestreview-5406989250) | 2026-10-04 (`85c98fe`) |
| [#50](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/50) | Complete system design document | [#71](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/71) | @leducminh290506-eng | [@teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/71#pullrequestreview-5407110299) | 2026-10-04 (`37e80c3`) |
| [#52](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52) | Setup verified on a non-author machine | No PR; the record is [a comment on #52](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982133134) | @leducminh290506-eng | [Confirmed and closed by @teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982150358) | Not applicable |

PR [#62](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/62) (Sprint 2 roles in
the README) is not linked to an issue and is not listed.

## 2. Test results

| Run | Commit | Result | Notes |
|---|---|---|---|
| [CI 37215985306](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/37215985306) | `37e80c3` (`main`) | 46 passed, 1 warning; Ruff passed | Current suite |
| [CI 37179138732](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/37179138732) | `840ad96` | 45 passed, 1 warning | Before #46 and #48 |
| [Backend evidence for #49](../traceability.md#backend-evidence-for-issue-49) | `489f187` (PR #65) | 22 passed | The suite at that commit; not comparable with the counts above |

The 46 tests on `37e80c3`, by file:

| File | Tests | What they cover |
|---|---|---|
| `tests/test_issue45_scenarios.py` | 23 | The four #45 scenarios: data comes from the database, at least 10 products, an empty database, pagination |
| `tests/test_products.py` | 10 | Catalog API: pagination, `is_active` visibility, `422` for invalid pagination, live database changes, seed idempotence, `500` when the query fails |
| `tests/test_products_page.py` | 4 | The `/products` HTML page and its static files are served |
| `tests/test_database.py` | 4 | Connection check, session, `python -m src.database` and `python -m src.seed` on a SQLite file, connection failure handled (#48) |
| `tests/test_config.py` | 3 | Settings and their validation |
| `tests/test_health.py` | 2 | `GET /` and `GET /health` |

No test covers the CHECK and foreign key constraints added in #46 (gap G7).

## 3. Walking skeleton (#45)

| ID | Evidence | Commit | Environment | Result |
|---|---|---|---|---|
| E1 | [Backend checks for #49](../traceability.md#backend-evidence-for-issue-49): init, seed, API output, pages 1 to 4, `422`, inactive product hidden, live changes, `500` on a failed query, empty table | `489f187` | Ubuntu 24.04 on WSL2, Python 3.12.3 | All checks passed |
| E2 | [Browser checks for #49](../traceability.md#evidence-for-issue-49): seeded catalog, live edit, empty state, error with Retry, layout at 1280 / 800 / 390 px, with the three screenshots below | `883e9a4` (PR #61) | Headless Chromium 149 with Playwright | All checks passed |
| E3 | Scenario tests in `tests/test_issue45_scenarios.py` from PR #64 | `840ad96`; still passing on `37e80c3` | CI, Python 3.12 | 23 passed |
| E4 | [Walking skeleton section](../design.md#4-walking-skeleton) of the design: route, table, SQL query, screenshot, `.env.example` | PR #71 | Not applicable | Documented |
| E5 | Author check of the setup guide ([SETUP section 7](../SETUP.md#7-verification)): clean clone, `python -m src.seed` only, six tables, 1 user and 45 products | `85c98fe` | Ubuntu 24.04 on WSL2, Python 3.13.12 | Passed; author check, not independent |
| E6 | Independent setup verification (#52), see section 5 | Guide at `1c5982d` | Windows 11, Python 3.12.7 | Pass |

## 4. Screenshots

| Screenshot | Shows | Commit and environment | Source |
|---|---|---|---|
| [Catalog](../images/issue49-catalog.png) | 20 of the 45 seeded products | `883e9a4`, headless Chromium 149, 2026-10-04 | PR #61 |
| [Empty state](../images/issue49-empty-state.png) | "No products available at the moment." for an empty `products` table | `883e9a4`, same run | PR #61 |
| [Error with Retry](../images/issue49-error-retry.png) | The error message and Retry while the API returns `500` | `883e9a4`, same run | PR #61 |
| [Windows catalog](https://github.com/user-attachments/assets/bf9c33c4-8551-45dd-81fa-d8ff8761e0d8) | `/products` in Edge on Windows 11: "Wireless Mouse", "180.000 ₫", "In Stock" | Guide at `1c5982d`, 2026-10-04 | #52 record |
| [Windows server log](https://github.com/user-attachments/assets/94e4feb3-a95a-4c48-a055-5baca00315ce) | The catalog `SELECT ... WHERE products.is_active IS 1 ORDER BY products.id LIMIT ? OFFSET ?`, `GET /api/v1/products?page=1&limit=20` `200`, and `404` for `/images/p-*.jpg` before the placeholder loads | Guide at `1c5982d`, 2026-10-04 | #52 record |
| [C4 container diagram](../images/mini-marketplace-c4.svg) | Containers of the system | PR #69 | Design |
| [ERD](../images/design_erd.png) | The six tables and their relationships | PR #66 | Design |

## 5. Setup verification (#51, #52)

| Run | Guide commit | Who and where | Result |
|---|---|---|---|
| Independent (#52) | `1c5982d` | @leducminh290506-eng; Windows 11 (x64), Git 2.51.1, Python 3.12.7; 2026-10-04 23:10 to 23:28 GMT+7 | Pass: install, `.env`, `python -m src.database`, `python -m src.seed` (45 products), start, `/products` and endpoints, 45 tests passed. [Record](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982133134), [confirmation](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982150358) |
| Author check | `main` at `85c98fe` | @MinhQuangQu; Ubuntu 24.04 on WSL2, Python 3.13.12; 2026-10-04 | Pass: `python -m src.seed` alone created six tables, 1 user and 45 products; 46 tests passed; every check in SETUP section 5 matched |

Both runs are recorded in [SETUP section 7](../SETUP.md#7-verification). The
independent run checked the guide before it moved to the single seed command
and the six-table schema, so the current guide has been run only by its author
(gap G5).

## 6. Gap ledger

Differences between the requirements, the design and the running code found
while building this index. Owners are proposed; each owner confirms or hands a
gap on.

| ID | Gap | Evidence | Impact | Proposed owner | Status |
|---|---|---|---|---|---|
| G1 | The catalog API differs from the API contract in three details: `id` is a string, not an integer; invalid `page` or `limit` returns `422`, not `400`; errors use FastAPI's `{"detail": ...}`, not `{"error": {"code", "message"}}` | [Design 1.5](../design.md#15-running-catalog-api-compared-with-the-api-contract); `src/api/products.py`; `test_list_products_rejects_invalid_pagination` expects `422` | A client written from the contract handles ids and errors wrongly | @teddywristh (#47) | Open |
| G2 | BR1 and US01 criterion 2 exclude products with no stock, but the catalog filters only on `is_active`, so out-of-stock products are listed with `stock_status: out_of_stock` | `list_products()` in `src/api/products.py`; [US01](../us01-browse-product-catalog.md); design 2.7 replaces `is_published` with `is_active` | Buyers see products they cannot buy, and the empty state never appears for an all-out-of-stock catalog | @leducminh290506-eng (PO) decides the rule | Open; decision needed |
| G3 | US01 criterion 1 expects page controls, but the page always loads `page=1&limit=20`, has no page controls or filters, and its cards do not link to a detail page | `PRODUCTS_URL` in `src/web/static/products.js` | Products after the first 20 cannot be reached from the page | US01 implementation task, scheduled by the PO | Open |
| G4 | US02 names its screen `/products/:productId`, while the endpoint is `GET /api/v1/products/{productCode}` and design 3.1 says public URLs use the product code | [Design 3.1](../design.md#31-product-identifiers); [traceability route table](../traceability.md) | The detail screen and its API could be built against different identifiers | @teddywristh (#47) with the PO | Open |
| G5 | The independent setup run used the guide at `1c5982d`. The current guide (single seed command, six tables, demo seller) has only been run by its author, on Linux | Section 5; [SETUP section 7](../SETUP.md#7-verification) | Windows steps of the current guide are unverified | @MinhQuangQu (#51) with a non-author tester | Open |
| G6 | PR #60 was merged by its author without an approving review | Section 1; PR #60 has no reviews | Breaks the rule that a self-merged PR does not count | @minhnm162 (Sprint 2 SM, #54) | Recorded for the retrospective |
| G7 | No automated test exercises the CHECK constraints or foreign keys added in #46 | Section 2; `tests/` | A model change could drop a constraint without a failing test | @minhnm162 (#46) | Open |
| G8 | `/seller/products` is listed as a P0 route with no story, and it is not in the Milestone 1 requirements | [Traceability route table](../traceability.md); `docs/requirements.md` lists only `/seller/products/new` and `/seller/products/:productId/edit` | Unclear scope for seller product management | @leducminh290506-eng (PO) | Open |
| G9 | `GET /api/v1/cart` returns `404` "when no active cart exists", but the data model has no cart entity: a cart is the buyer's `cart_items` rows | [Design 3.3](../design.md#33-p0-endpoint-contract) and [2.2](../design.md#22-table-definitions) | It is unclear whether an empty cart is `200` with no lines or `404` | @teddywristh (#47) | Open |
| G10 | The seed stores image URLs `/images/p-*.jpg` that the app does not serve, so every catalog load logs `404`s before the placeholder appears | Windows server log screenshot in section 4; `make_product()` in `src/seed.py` | Noisy logs; no real product images | @minhnm162 (#46) | Open; low impact |
| G11 | Design sections 1.2 and 1.4 and the C4 diagram still described #46 as in progress | `docs/design.md` before this PR | The design understated what runs | @MinhQuangQu (#43) | Fixed in this PR |
| G12 | The traceability route table had a placeholder `#<PR_NUMBER>` for US03 and pointed US06 and US07 at PRs #28 and #30, which were closed without merging | `docs/traceability.md` before this PR | Wrong spec links | @MinhQuangQu (#53) | Fixed in this PR: #31, #32 and #34 |
