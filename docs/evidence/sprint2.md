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
