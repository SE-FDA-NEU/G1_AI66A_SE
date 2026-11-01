# Focused regression cases

Expected results below come from the assigned task/parent story and its documented
API contract, not copied current output. Existing suites retain their earlier
coverage; this table records the new cases for task #127.

## Task #127: order history and shipping milestones

| ID | Preconditions / input / action | Expected result | Technique / test |
|---|---|---|---|
| H127-01 | Owning seller ships a CONFIRMED order through either existing status route | One CONFIRMED -> SHIPPED event, authenticated seller ID/role, trimmed note/tracking, event time equals `shipped_at` | Happy path; `test_shipping_records_actor_note_and_exact_milestone` |
| H127-02 | A shipped order is delivered, then its buyer confirms receipt | DELIVERED and COMPLETED history persists; delivery time equals its event time; earlier shipping/delivery values remain | Lifecycle integration; `test_delivery_keeps_shipping_snapshot_and_buyer_confirmation_is_audited` |
| H127-03 | Buyer, owning seller, unrelated buyer or guest reads history | Buyer sees own order; seller sees only own shop history; unrelated buyer gets 404; guest gets 401 | Authorization decision table; `test_history_is_scoped_to_the_authenticated_shop` |
| H127-04 | Foreign seller updates a sub-order, or owner requests CONFIRMED -> DELIVERED | Existing 403/400; no audit row or shipping milestone | Unhappy partitions; `test_invalid_or_foreign_transitions_create_no_history` |
| H127-05 | Tracking length 99/100/101, blank tracking; note length 999/1000/1001; spoofed actor role | Values at/below limits accepted; invalid/forged values get 422 without writes | Boundary values/input partitions; `test_audit_input_accepts_values_at_and_below_the_limits`, `test_invalid_audit_input_is_rejected_without_writes` |
| H127-06 | Actor role changes after a committed event | Read still reports the original role snapshot | Historical integrity; `test_actor_role_is_a_snapshot_not_a_join_to_the_current_role` |
| H127-07 | Buyer/seller/admin actor passed to the service with fixed clock and fake repository | Exact actor/role/note/time passed to repository; caller retains transaction ownership | Fast unit partition; `test_audit_service_snapshots_authenticated_actor_without_committing` |
| H127-08 | Audit persistence fails while either route ships an order | 500; no persisted new status, milestone or audit row | Failure injection; `test_history_failure_rolls_back_status_and_shipping_milestone` |
| H127-09 | Another shop shipped, current seller has not | Seller receipt has no other shop's tracking/milestones/history | Tenant isolation; `test_seller_receipt_never_uses_another_shops_shipping_milestones` |
| H127-10 | Legacy history exists; run migration twice | One nullable role column; rows/notes preserved; historical role remains unknown | Migration/repeatability; `test_legacy_history_migration_is_repeatable_and_preserves_unknown_role` |
| H127-11 | Two events have the same timestamp | Stable ascending event IDs within the visible shop history | Ordering edge; `test_history_order_is_stable_when_events_share_a_timestamp` |
| H127-12 | History INSERT rejected by SQLite, or commit fails after all writes flush; seller shipping/cancellation and buyer cancellation/confirmation | 500; fresh-session snapshots of orders, inventory, sales counts, history and notifications equal their pre-request values | Transaction failure matrix; `test_database_failure_rolls_back_the_whole_transition` |
| H127-13 | An unrelated buyer/seller reads history or attempts an update; buyer uses seller-only route | Existing 403/404, no private history/tracking returned and no writes | Access matrix; `test_unauthorized_history_reads_reveal_no_order_data`, `test_foreign_status_updates_leave_all_audit_data_unchanged` |
| H127-14 | A seller ships its items, or fetches/updates its receipt while another shop has shipped | GET/PATCH receipts include only the authenticated shop's fulfillment items, history and tracking | Multi-shop integration; `test_seller_receipt_excludes_other_shops_fulfillment_items` |
| H127-15 | Last seller completes with an advancing clock; audit caller provides UTC+07 timestamp | Parent/child/history completion instants match; responses and stored audit time use UTC | Deterministic clock/offset partitions; `test_seller_completion_uses_one_utc_instant_for_parent_child_and_history`, `test_audit_service_converts_offset_timestamp_to_utc` |
| H127-16 | CONFIRMED -> DELIVERED requested through either status route | 400 ERR_INVALID_TRANSITION and all persisted business/audit data unchanged | Invalid transition partition; `test_invalid_transition_leaves_all_audit_data_unchanged` |
| H127-17 | Cancel through the atomic buyer POST/PATCH or either seller PATCH route after integrating #128 | Persisted history/response retains authenticated actor ID/role, optional trimmed note and UTC timestamp; tracked refund remains intact | Workflow integration matrix; `test_atomic_cancellation_workflow_preserves_actor_and_note` |

Risk priority: persisted audit facts, tenant isolation and rollback are checked
first because incorrect identity/history can mislead users about fulfilment and
failed partial writes can leave inconsistent orders. Browser tests are not added:
this task changes backend data, with no new screen or UI interaction.

## Task #135: multi-vendor pricing and shipping

All cases are fast pure-service tests in `tests/test_pricing.py`. Expected money
comes from US16 sections 2 and 4; no database or production data is required.

| Case | Expected result | Technique / test |
|---|---|---|
| Two-shop worked example | Shop totals 248.000 / 185.000 VND; grand total 433.000; separate shop/platform/shipping funding amounts | `test_contract_example_totals_433000_and_preserves_funding_breakdown` |
| Fixed above/on/below basis; percentage 1/10000 bps, floors and caps | Discount bounded by basis and configured cap, integer floor | `test_item_discount_boundaries` |
| Unequal/equal remainders, zero basis, full discount, amount above float precision | Exact allocation sum; ascending seller-ID ties; no discount for zero-basis shop | `test_largest_remainder_allocation_contract_cases` |
| Random allocation inputs with fixed seed | Every allocation within its basis and less than one VND from its exact quota; sum equals discount | `test_allocation_conserves_money_for_deterministic_random_inputs` |
| Eight shop/platform/shipping combinations | Expected grand totals, applying platform after shop discounts | `test_voucher_stacking_decision_table` |
| Several lines per seller; no cap / cap below or above shipping fee | One 20.000 VND fee per shop; free-shipping cap per shop | `test_group_lines_and_charge_shipping_once_per_seller`, `test_free_shipping_cap_is_applied_per_seller_order` |
| Zero item basis or rounded-zero requested discount | 409-compatible `ERR_VOUCHER_NOT_APPLICABLE`; empty selection gives 400-compatible `ERR_EMPTY_CART` | `test_zero_effect_requested_item_voucher_is_not_applicable`, `test_no_selected_lines_is_an_empty_cart` |
| Malformed numbers/types, cap/rate bounds, voucher for an absent seller | Reject calculation without an output or side effects | `test_invalid_item_discount_rules_fail_before_calculation`, numeric/allocation guard tests |
| Same snapshots in another line order | Equal, immutable result; caller inputs unchanged | `test_pricing_is_repeatable_without_changing_inputs_or_result_snapshots` |
| Random full orders with fixed seed | Each seller formula holds; all aggregate components and grand total reconcile | `test_random_order_totals_reconcile_with_each_seller_breakdown` |
| Three/four sellers with equal platform remainders and reordered lines | Whole-order calculation awards leftover VND to the smallest seller IDs and reconciles totals | `test_full_order_equal_remainders_prefer_lowest_seller_ids` |
| Boolean shop-discount key matching integer seller ID | Reject `True`/`False` instead of treating them as seller IDs | `test_shop_discount_rejects_boolean_seller_keys` |
| One shop's item basis is zero; another has a platform discount; free shipping applies | Zero-basis shop gets no platform allocation but still receives its shipping discount | `test_shipping_discount_applies_to_zero_basis_shop_in_a_mixed_order` |
| 1-bps shop voucher on 1 VND plus another valid shop | Reject the whole calculation with no partial price; quote/checkout adapter behavior is in US16 section 2.4 | `test_one_zero_effect_shop_voucher_rejects_the_whole_multi_shop_calculation` |
| Business rejection versus invalid input | Only business rejections inherit `OrderError`; existing checkout code/message/status contract stays compatible | `test_business_rejections_are_distinct_from_invalid_pricing_input`, `test_order_business_errors_share_the_adapter_contract`, `test_existing_business_error_default_status_stays_compatible` |
| Inject an allocation whose sum differs from the platform discount | Raise internal `RuntimeError` before returning an order price | `test_allocation_conservation_failure_is_an_internal_error` |

Use the README Python 3.12 environment:

```powershell
$env:DEBUG = 'false'
python -m pytest tests/test_pricing.py -q --cov=src.services.pricing --cov-fail-under=100 --cov-report=term-missing
python -m pytest tests/test_checkout.py tests/test_atomic_cancellation.py tests/test_ui_docs_contract.py -q
python -m ruff check src tests/test_pricing.py
git diff --check
```

The pricing command enforces the statement-coverage threshold; results are
recorded in the PR. Voucher permissions, consumption/rollback, persisted receipts
and browser checkout tests remain with #133/#136 integration. No new UI or
real-user test result is claimed here.

## Task #143: seller analytics charts and ranking

Contract and exclusions: [US18 UI boundary](us18-seller-analytics-ui.md).

| Case | Input/action | Expected result | Coverage |
|---|---|---|---|
| A143-01 | Open either analytics route and follow seller navigation | Production assets served; no private report in HTML; ranking route selects its navigation link and focuses the ranking once, without stealing focus on filter updates | `tests/test_seller_analytics_ui.py`; DOM and native route checks |
| A143-02 | Guest, expired token, buyer or inactive seller | Login return path or seller-access explanation; no financial requests for denied identity | `tests/seller_analytics_ui.mjs`; native buyer case; existing API auth regressions |
| A143-03 | Valid inclusive dates, day/month, top 5/10/20 | Matching canonical/legacy summary parameters; ranking uses units and the same dates; no client seller ID | DOM; native month/top-5 interaction |
| A143-04 | Missing/invalid dates, reversed range, unsupported grouping/limit | No report request; associated error with focused input; stale data hidden | DOM boundary partitions; native date focus |
| A143-05 | Four financial metrics with unequal bucket rates | Distinct VND/percentage units; summary uses the API aggregate, not an average; metric change redraws SVG and exact table locally | DOM and native browser |
| A143-06 | Legacy completed-sales response; missing new financial metrics | Explicit legacy label/time basis; missing metrics say Not available, never zero | DOM and native browser |
| A143-07 | All-zero periods, no completed sales, failed request, failed-body deadline | Useful independent empty states; failures hide data and allow Retry; date edits retained; Retry reuses applied filters | DOM and native browser; timeout in DOM |
| A143-08 | Invalid money values or product name containing HTML | Invalid report rejected; product name rendered as literal text | DOM invalid partitions and injection fixture |
| A143-09 | Superseded request, stale 401, account switch, logout | Old responses cannot replace current data; account changes immediately clear private data; logout clears both token keys | DOM race tests |
| A143-10 | Native controls, chart/table at 390/768/1280px | No page overflow; chart/table can scroll within panels; labelled controls, exact values, validation focus and Retry work | `tests/seller_analytics_browser.mjs` |
| A143-11 | Existing seller analytics ownership, periods, completion dates and historical prices | Existing API results and authorization remain unchanged | `tests/test_us18_seller_analytics.py` |
| A143-12 | Chrome page calls actual FastAPI/SQLite; owned completed/pending/paused/cancelled orders, foreign seller and out-of-range data | Correct day/month report, units ranking and historical prices; current API labels legacy values honestly; financial API gives 700k gross, 500k completed, 150k pending and weighted 20% cancellation, independent of bucket rates | `tests/test_seller_analytics_integration.py`; strict financial mode for #142 candidate |

Run with the README Python 3.12 environment and dependencies:

```powershell
python -m pytest tests/test_us18_seller_analytics.py tests/test_seller_analytics_ui.py tests/test_ui_docs_contract.py tests/test_ui_styling.py -q
python -m pytest tests/test_seller_analytics_integration.py -q
ruff check src tests/test_seller_analytics_ui.py tests/test_seller_analytics_integration.py
node tests/seller_analytics_ui.mjs
node tests/seller_analytics_browser.mjs
git diff --check
```

The native test requires Node 22+ and an installed Chrome/Edge. It detects standard
Windows Chrome/Edge and Linux Chrome/Chromium paths; set `BROWSER_PATH` for another
location. It uses an isolated profile and local fixture server and rewrites the
screenshots under `docs/images/us18/`. CI's Page script checks run the DOM suite;
the native-browser command is an explicit local verification step. Report actual
run results in the PR, not as a permanent claim in this contract.

The FastAPI/SQLite browser suite reuses the optional Playwright tool already
installed by CI, plus installed Chrome/Edge (`BROWSER_PATH` can override its path).
For local setup, install it with `python -m pip install playwright`; no browser
download is needed when Chrome/Edge is installed. The suite is collected by the
existing CI pytest step. It skips only if Playwright is absent. For an isolated
#142 candidate or after that API merges, require the financial response explicitly:

```powershell
$env:ANALYTICS_REQUIRE_FINANCIAL = '1'
python -m pytest tests/test_seller_analytics_integration.py -q
Remove-Item Env:ANALYTICS_REQUIRE_FINANCIAL
```

The strict mode is expected to fail against the legacy API. Keep the post-merge
financial acceptance item pending until it passes on the integrated branch.

## Task #139: buyer return-request UI

Expected results come from #139, parent #109 and the existing return API schema.
The UI cases execute the production controller in `tests/buyer_returns_ui.mjs`;
native layout/integration cases use `tests/buyer_returns_browser.mjs`.

| Case | Expected result | Verification |
|---|---|---|
| Mixed-shop receipt with delivered/shipped shops and pending requests | Only delivered shops without a pending request appear; send the selected shop ID explicitly | DOM and native page checks |
| Reason lengths 2/3/500/501; evidence 2/3/2000/2001; whitespace | Invalid input prevents POST and focuses its field; valid limits are accepted | DOM boundary partitions |
| Switch eligible shop, cancel/reopen or refresh same order | Draft remains attached to its original shop; selection is retained when still eligible | DOM draft checks |
| Repeated submit/cancel while POST is pending | One POST, locked controls, form stays visible until result | DOM pending-write checks |
| Server 422 with field errors | End progress, retain input, unlock before moving focus to the invalid control | DOM regression and native browser |
| Successful POST followed by receipt refresh | Persistent request-number confirmation; one status card; submitted shop no longer selectable | DOM and native browser |
| Return read fails or write outcome is uncertain | Fail closed, retain draft, explicit Retry reads receipt/requests and never repeats POST | DOM timeout/conflict and native committed-503 fixture |
| Multiple requests, rejected/approved results, hostile reason/evidence text | Show all current statuses/notes as text; no injected HTML or unsafe automatic links | DOM and native browser |
| Guest/seller, expired token, another account/order selected during a request | No buyer action, appropriate login recovery, old response/draft cannot appear in the new context | DOM and native account-change cases |
| Native page at 390/768/1280px | No horizontal page overflow; visible labels/focus and usable form controls | Chrome/Edge screenshots |
| Existing return backend and page aliases | Ownership/eligibility/refund rules unchanged; both aliases serve the new assets | `tests/test_return_refund.py`, `tests/test_order_tracker.py` |

```powershell
$env:DEBUG = 'false'
node tests/buyer_returns_ui.mjs
node tests/buyer_returns_browser.mjs
python -m pytest tests/test_return_refund.py tests/test_order_tracker.py tests/test_ui_docs_contract.py tests/test_ui_styling.py -q
python -m ruff check src tests/test_return_refund.py
git diff --check
```

The DOM suite runs in the existing CI page-script step. Native checks require an
installed Chrome/Edge, or `BROWSER_PATH`; they need no npm dependency and use an
isolated browser profile. Actual run results and AI disclosure belong in the PR.

## Task #149: payment choices and order payment display

The #149 boundary is method capture and display only. The server is the single
compatibility default: an omitted method is recorded as `COD`; the browser sends
the required selected value. Existing payment-state defaults and seller fulfilment
transitions are not changed by this task.

| Case | Expected result | Verification |
|---|---|---|
| Omitted method | Stores `COD` for compatibility | `tests/test_checkout.py` |
| Unknown method | `422` field validation and no order writes | `tests/test_checkout.py` |
| Legacy `NULL` method | Confirmation says payment method/status not recorded | `tests/checkout_ui.mjs` |
| Unpaid VIETQR/WALLET/CARD | Shows awaiting/demo result not recorded, never Paid | `tests/checkout_ui.mjs` and shared `payment-display.js` |
| Legacy orders migration | Adds nullable column, preserves data, and is repeatable | `tests/test_database.py` |

Commands used for local verification:

```powershell
$env:DEBUG = 'false'
python -m src.database
python -m src.seed
python -m pytest -q
node tests/checkout_ui.mjs
python -m ruff check src tests/test_checkout.py tests/test_database.py
git diff --check
```

Observed results on 2026-10-30, after running the README database setup, were:

- `python -m src.database`: completed successfully.
- `python -m src.seed`: completed successfully; existing database reported `Added: 0 products`.
- `python -m pytest -q`: **1007 passed, 2 skipped, 5 warnings** in 601.00 seconds.
- `node tests/checkout_ui.mjs`: passed, including timeout/replay, legacy receipt,
  unpaid demo-method and shared payment-display checks.
- All ten CI-listed page-script commands passed, including
  `node tests/checkout_ui.mjs` and `node tests/addresses_ui.mjs`.
- Targeted Ruff on the touched Python modules/tests: all checks passed.
- `git diff --check`: passed.

`ruff check .` still reports eight pre-existing issues in
`tests/generate_ui_evidence.py` and `tests/test_ui_styling.py`; CI treats lint as
warning-only. GitHub CI, teammate review and screenshot capture are not claimed
as complete by these local results. The optional browser screenshot command
`python tests/browser_us13.py` could not run in this environment because the
README dependency set does not install the optional `playwright` package; no
screenshot is claimed from that failed command.

## Task #146: category and variant APIs

Expected results come from task #146, parent story #111 (US19), and `docs/us19-categories-variants-snapshots.md`.

| Case | Expected result | Verification |
|---|---|---|
| Non-admin category mutation | 403 Forbidden for buyer or seller; allowed only for admin | `tests/test_us19_categories_variants.py:test_admin_categories_enforce_hierarchy_permissions_and_soft_deactivation` |
| Category hierarchy cycle / inactive parent | 422 Unprocessable Entity when parent is inactive or self/ancestor cycle is detected | Same test case |
| Category deactivation with active children | 409 Conflict with `ERR_CATEGORY_HAS_CHILDREN` | Same test case |
| Shop-scoped SKU conflict | 409 Conflict with `ERR_VARIANT_SKU_CONFLICT` on duplicate SKU within same seller shop | `tests/test_us19_categories_variants.py:test_variants_are_shop_owned_and_checkout_keeps_purchase_snapshots` |
| Variant update version conflict | 409 Conflict with `ERR_CONCURRENCY_CONFLICT` when `expected_version` does not match database version | `tests/test_us19_categories_variants.py:test_variant_updates_require_displayed_version_and_keep_physical_stock` |
| Variant stock lower than reserved stock | 422 Unprocessable Entity rejecting physical stock reduction below reserved commitments | Same test case |
| Cross-shop variant access | 403 Forbidden with `ERR_RESOURCE_OWNER` when accessing or modifying variants belonging to another seller's product | `tests/test_us19_categories_variants.py:test_other_shop_cannot_manage_variant` |
| Soft-delete variant / category | Sets `is_active=False` and increments version; historical references preserved | US19 regression suite |

Run focused API regression suite:

```powershell
python -m pytest tests/test_us19_categories_variants.py -q
python -m ruff check src tests/test_us19_categories_variants.py
git diff --check
```

## Task #147: immutable order-item snapshots

Assigned criteria: snapshot persistence and preserved history in #111/#147. The
existing implementation is verified by `tests/test_order_item_snapshots.py`, using
independent SQLite files, real authenticated APIs and fresh-session assertions.

| Case | Input/action | Expected result | Verification |
|---|---|---|---|
| S147-01 | Base product or variant; legacy/quoted checkout; option image, product fallback or neither | Persist exact product/variant name, image and integer unit price with initialized marker; quantities/totals match purchase data | Checkout/image decision table |
| S147-02 | Edit name/price/image, deactivate, or DELETE after purchase | Buyer detail/list and seller detail/list preserve purchase facts; DELETE retains inactive referenced rows | Catalog mutation matrix |
| S147-03 | Purchase without an image, then add one later | Historical NULL remains NULL in storage and every read surface | NULL-image partitions in the same matrix |
| S147-04 | Repeat checkout key after edit/deactivation/DELETE, then rerun migrations | Same stored lines and total, no duplicate snapshots; known values stay unchanged | Idempotency and repeatability checks |
| S147-05 | Add to cart, edit catalog, then checkout | Snapshot uses checkout-time metadata and price rather than old cart-time values | Legacy/quote timing pair |
| S147-06 | Two-shop order; each seller reads; unrelated buyer reads | Seller receives only own historical line; buyer receives both; unrelated buyer gets 404 | Ownership integration |
| S147-07 | Physically DELETE purchased base product or variant in the database | FK rejects removal; rollback preserves order lines and readable history | Referential-integrity partitions |
| S147-08 | Client supplies snapshot names/image or unit price | 422, no order/snapshot written, cart and inventory preserved | Server-owned field partitions |
| S147-09 | Second snapshot INSERT fails after an earlier line reached persistence | 500 database error; orders, snapshots, inventory, cart, sales counters and notifications equal pre-request state | SQLite failure injection, legacy/quote pair |
| S147-10 | Existing known snapshots lack marker column; migrate repeatedly after catalog changes | Preserve known values, explicit NULL image, row references, quantity and unit price; add marker once | Legacy schema with saved image/NULL partitions |
| S147-11 | List, get and patch an existing seller product with no image | 200 responses contain explicit NULL image; deactivation is persisted | Direct regression in `tests/test_seller_products.py` |

Run with README dependencies and Python 3.12:

```powershell
$env:DEBUG = 'false'
python -m pytest tests/test_order_item_snapshots.py -q
python -m pytest tests/test_us19_categories_variants.py tests/test_checkout.py tests/test_checkout_vouchers.py tests/test_seller_products.py tests/test_database.py tests/test_ui_docs_contract.py -q
python -m ruff check src tests/test_order_item_snapshots.py tests/test_seller_products.py
git diff --check
```

The suite is discovered by the existing CI pytest step. No new browser dependency
is needed: this task tests persistence and API contracts and adds no new screen.
Only report CI/review/clean-clone results after they have actually been verified.

## Task #157: phone number formatting and validation

| Case | Expected result | Verification |
|---|---|---|
| 7 and 15 ASCII digits with supported separators | Accepted; outer/repeated spaces normalize without changing digits | Existing address boundary tests and checkout schema validation |
| Fewer/more digits or unsupported punctuation | Rejected with `phone_number` field feedback and no order/address write | Existing invalid-format tests plus browser field-error checks |
| Manual checkout and address-book storage | Both persist the same normalized representation | `tests/test_addresses.py` and `tests/test_checkout.py` normalization regressions |

```powershell
$env:DEBUG = 'false'
python -m pytest tests/test_addresses.py tests/test_checkout.py -q
node tests/addresses_ui.mjs
node tests/checkout_ui.mjs
python -m ruff check src/schemas/delivery.py tests/test_addresses.py tests/test_checkout.py
git diff --check
```

Country-code conversion and provider verification are intentionally outside this
bug fix; the normalization preserves the entered digit sequence.
## Issue #159: recorded order date and total

`tests/test_order_summary_browser.py` executes the production order page in
Chromium/Chrome, routes requests through real FastAPI handlers, and uses fresh
SQLite files. Third-party map resources are blocked; map rendering is outside this
fix. Prices and timestamps below are independent expected purchase facts.

| Case | Expected result |
|---|---|
| Two shops, vouchers, catalog edited after purchase; 390/768/1280 px; reload | Stored 2026-01-02 15:04 UTC displays as 22:04 GMT+7 in the configured browser; subtotal 500,000 minus shop 30,000 minus platform 47,000 plus shipping 40,000 minus shipping discount 30,000 = grand total 433,000 VND; no viewport overflow |
| Real zero-total voucher checkout | Grand total is 0 VND, not the 50,000 VND item subtotal; zero discounts remain 0, not negative zero |
| Switch discounted order -> legacy-pricing order -> first order | Stored totals 433,000 -> 70,000 -> 433,000; old breakdown clears and the unavailable explanation is visible for legacy pricing |
| Detail read fails, then Retry succeeds | Summary stays hidden on the initial failure; Retry displays the actual receipt |
| Another authenticated buyer opens the order URL | API denies access; no summary or item details are shown |

Run with Python 3.12, README dependencies, Playwright, and installed Chrome:

```powershell
python -m pip install playwright
$env:DEBUG = 'false'
python -m pytest tests/test_order_summary_browser.py -q
python -m ruff check tests/test_order_summary_browser.py
node --check src/web/static/order.js
node tests/buyer_returns_ui.mjs
git diff --check
```

The fixture tries Playwright Chromium, then installed Chrome. Set `BROWSER_PATH`
to an installed Chrome/Edge executable when automatic detection is unavailable.
The existing CI pytest step discovers this file. To regenerate the desktop/mobile
screenshots with deterministic fixture data, set
`$env:UPDATE_ORDER_SUMMARY_SCREENSHOTS = '1'` before running the browser suite.
Local verification, CI, human review and clean-clone verification are separate.

## Task #152: admin catalog and voucher screens

Expected behavior comes from #152, parent #113 and the
[UI contract](us21-admin-ui.md). Tests use production page assets, a real browser,
authenticated FastAPI requests and isolated SQLite; selected failure/held responses
are explicit test doubles. They do not represent human user acceptance.

| ID | Action / partition | Expected result | Verification |
|---|---|---|---|
| U152-01 | Create/edit/delete category; cancel deletion first | Native form checks, confirmed CRUD with persisted category changes; cancellation sends no DELETE | Real API/database lifecycle |
| U152-02 | Open editor; Tab/Shift+Tab; Escape | Named modal, initial/trapped focus, inert background and focus restoration | Browser keyboard interactions |
| U152-03 | Create each voucher type, with/without an optional cap; invalid end date; cancel/confirm creation | No request for invalid/cancelled input; exactly one POST with the full expected JSON payload, integer values/limits, UTC periods and no client-supplied scope/owner; API stores platform scope | Five-case payload decision table and committed voucher rows |
| U152-04 | Cancel/confirm voucher status change | Cancel sends no PATCH; confirmation updates the named code once | Production toggle/API integration |
| U152-05 | Read fails, code duplicates, then transient save failure | Retry works; backend error is shown and focused in the form; input remains; controls unlock; corrected retry succeeds | Read/server/network error paths |
| U152-06 | Hold save; repeat submit; press Escape | One mutation, visible/live progress, locked controls and no pending dismissal | Controlled pending response |
| U152-07 | Cancel/confirm product moderation; search empty; view at 390px | Correct product state; no cancelled PATCH; empty feedback; no horizontal page overflow | Catalog integration and mobile geometry |
| U152-08 | Guest/buyer/seller opens portal | Access denied without requests for admin datasets | Role partitions, existing server authorization coverage |
| U152-09 | Account changes before a prepared write or before an old read finishes | No prepared write; late private rows discarded and portal hidden | Account-context race regressions |
| U152-10 | Older search response arrives after a newer empty result | Newer filter result remains visible | Out-of-order real API responses |
| U152-11 | Whitespace name or invalid slug | Invalid field feedback and no mutation | Client validation partitions |
| U152-12 | Fixed voucher with a carried-over cap; free shipping with a stale disabled value | Fixed voucher POST omits the `max_discount` key entirely; free shipping sends `discount_value: 0`; enabled empty caps send null | Exact JSON assertions before inspecting persisted rows; direct-request backend checks belong to #151 |
| U152-13 | Existing account modal: keyboard trap, Cancel/Escape, failed save, corrected retry | Cancel sends no PATCH/audit; focus restores, error retains input, successful retry records the status and authenticated audit; background unlocks | Real account API/database regression |
| U152-14 | Existing dispute modal: required notes, Escape, failed decision, retry; approve with/without restock and reject | No cancelled POST; focus/error recovery preserved; exact decision JSON, actor/notes, order/escrow state and conditional inventory effects persist | Three real dispute workflow cases after integrating #151 |

Use the README Python environment and the browser dependency installed by CI:

~~~powershell
$env:DEBUG = 'false'
python -m pip install playwright
python -m pytest tests/test_admin_portal_browser.py tests/test_admin_portal.py tests/test_ui_docs_contract.py -q
python -m ruff check src tests/test_admin_portal_browser.py tests/test_admin_portal.py
node --check src/web/static/admin-portal.js
git diff --check
~~~

Chrome/Edge is detected on Windows; set `BROWSER_PATH` if installed elsewhere.
To regenerate the documented screenshots with fake data, set
`ADMIN_UI_ARTIFACTS=docs/images/us21` before running the browser suite. Run results
belong in the PR, without marking unverified CI or human review complete.

## Task #151: admin authorization and dispute workflow

Expected behavior comes from #151, parent #113, and the
[US21 backend contract](us21-admin-workflow.md). New tests use isolated SQLite
files, real authenticated routes, deterministic decision clocks and fresh-session
assertions. Existing admin and return suites retain their earlier coverage.

| ID | Partition / action | Expected result | Verification |
|---|---|---|---|
| A151-01 | Guest, buyer or seller calls category/audit/account/dispute routes directly | 401/403; no mutations, leaked audit records or actor spoofing | Direct-request authorization matrix |
| A151-02 | Existing token belongs to a restricted/suspended admin or moderated buyer/seller | Server reads current account status and denies prohibited actions | Admin restriction and account moderation cases |
| A151-03 | Create/update/delete via canonical or legacy categories; repeat an unchanged update | Before/after snapshots and authenticated UTC actor history commit with the change; no no-op audit | Both-route audit and legacy child-reparenting cases |
| A151-04 | Duplicate slug, invalid ancestor, blank/unknown fields, inactive ancestor or legacy cycle | Reject without writes; keep existing route-specific error contracts | Validation partitions and cycle fixture |
| A151-05 | Category audit INSERT fails during create, update or delete | 500 database error, not slug conflict; category, associations and audits equal before-state | Trigger failure matrix |
| A151-06 | Moderate buyer/seller; repeat status; fail account audit; try self-restriction or actor injection | Existing restrictions/audit/deactivation remain atomic and server-owned | Account status/audit integration |
| A151-07 | Escalate delivered order or existing pending buyer return | Pause seller/parent escrow, persist admin creator; one actual status event, existing buyer history retained | Escalation and request-linking cases |
| A151-08 | Boundary reason/evidence, duplicate dispute, wrong parent, unavailable state, failed insert/history/commit or lost claim | Reject or roll back all dispute/state/history writes | Escalation boundaries and failure injection |
| A151-09 | Paid/unpaid/failed payments, approve/reject and restock flag | Apply shared settlement rules, derive parent, update linked request and exact actor/time; restock only when approved and requested | Decision table with fixed UTC clock |
| A151-10 | Restock an inactive purchased variant; repeat decision | Restore that variant only; product counter reconciles; repeated decision changes nothing | Variant and replay regressions |
| A151-11 | Unreconciled payment, moved-on order, resolved/mismatched request, mismatched dispute ownership or forged decision fields | Reject before effects; preserve all persisted state | Invalid-adjudication partitions |
| A151-12 | Inventory/history/notification/commit fails, or request/dispute conditional claim loses | Roll back dispute, request, orders, stock/counters, history and notifications together | Trigger/commit/claim failure matrix |
| A151-13 | Another session changes a seller order after it was read | Conditional escalation cannot rewind the changed status | Two-session stale-state regression |
| A151-14 | Initialize an old dispute schema twice, with existing known facts | Nullable unknown creator stays null; create empty category audit table; preserve facts and foreign keys | Legacy migration regression |
| A151-15 | Decide a tracked paid dispute after integrating #148; inject refund-event failure; retry | Shared payment service records one admin-attributed refund and voids escrow; failure rolls back ledger with every other effect | Payment-event assertions and refund-trigger rollback |
| A151-16 | Approve/reject a legacy dispute with no payment method | Preserve the stored payment snapshot without inventing a refund, refunded amount or settlement time | Legacy payment compatibility pair |
| A151-17 | Direct fixed-amount voucher request includes a cap | 400 before persistence, with no partial voucher write | Fixed-cap validation regression |

Run with the README Python 3.12 environment and dependencies:

~~~powershell
$env:DEBUG = 'false'
python -m pytest tests/test_admin_workflow.py tests/test_admin_portal.py tests/test_return_decisions.py tests/test_return_refund.py tests/test_us19_categories_variants.py tests/test_database.py tests/test_ui_docs_contract.py -q
python -m ruff check src tests/test_admin_workflow.py tests/test_admin_portal.py
git diff --check
~~~

No UI or browser interaction is added by this backend task. Test execution results
and AI assistance disclosure belong in the PR; they do not establish human review
or story-wide acceptance.

## Task #153: admin route registry and security tests

Expected behavior comes from #153, parent #113 and the
[US21 contract](us21-admin-workflow.md). Tests send direct HTTP requests with signed
tokens on isolated SQLite files; no UI state is treated as access control.

| ID | Partition / action | Expected result | Verification |
|---|---|---|---|
| A153-01 | Add, remove or unguard an admin route | Registry test fails until `traceability.md` and the test registry are updated; every admin route depends on `require_admin` | Route discovery from routers plus OpenAPI |
| A153-02 | Guest, buyer, other buyer, seller, other seller, restricted and suspended admin call each admin route with a valid request | 401/403 with the documented code and an identical database snapshot | Actor x route matrix |
| A153-03 | Active admin calls each route with a valid request | Documented success status | Same registry |
| A153-04 | Token issued while ACTIVE, account restricted afterwards | Next request is 403 `ERR_ACCOUNT_RESTRICTED`, no write; token role must match the database role | Restriction and forged-role cases |
| A153-05 | Unknown ids; malformed or unknown fields; limit below/above 1-100 | 404 `*_NOT_FOUND` or 422 `ERR_VALIDATION`, no write | Partition tables |
| A153-06 | Actor id supplied in query or body | Audit actor is the authenticated admin; forbidden fields are rejected | Actor spoofing cases |
| A153-07 | Scope, seller or owner supplied for vouchers/products; seller edits foreign or platform voucher; admin route targets shop voucher | Scope and owner come from the server; foreign access is 404 with no write | Scope and ownership cases |
| A153-08 | Seller and admin approve the same restockable paid return; outsiders try the seller route | Same stock, payment, escrow and parent result; outsiders get 403 and no write | Parity and cross-account cases |
| A153-09 | Failed category mutations; two admins act in sequence | No audit row for failures; history names the real actor, newest first | Audit history cases |

Run with the README Python 3.12 environment:

~~~powershell
$env:DEBUG = 'false'
python -m pytest tests/test_admin_security.py tests/test_admin_workflow.py tests/test_admin_portal.py -q
python -m ruff check tests/test_admin_security.py
git diff --check
~~~

Audit for platform vouchers and product moderation does not exist; it is listed as a gap
in the traceability table, not tested as if present. CI, review and a clean-clone run
need separate evidence.

## Task #154: shared CSS design tokens and components

Expected results come from US22/#114 and the shared styling contract in
`docs/design.md`.

| Case | Expected result | Verification |
|---|---|---|
| Required token categories | Palette and semantic feedback, typography, spacing, borders, shadows, radii and focus tokens are declared in `base.css` | `test_shared_design_tokens_cover_required_categories` |
| Shared component primitives | Buttons/inputs retain existing behavior and cards, tables, badges and alerts expose reusable selectors | `test_shared_components_have_semantic_variants` and existing UI styling tests |
| Control sizing contract | Single-line controls (.input, .select) have 42px desktop / 44px mobile min-height; multiline controls (textarea, .textarea) preserve 96px min-height without collapsing | `test_control_aliases_preserve_native_sizing_and_textarea_min_height` |
| Badge cascade isolation | Semantic variants (.badge--success, --warning, --danger, --info) preserve color/background when order.css is loaded | `test_semantic_badge_variants_resist_order_stylesheet_cascade_override` |
| Accessibility regressions | Link buttons retain contrast on hover/active; controls retain desktop/mobile sizing and visible focus | Existing tests in `tests/test_ui_styling.py` |

```powershell
python -m pytest tests/test_ui_styling.py -q
python -m ruff check tests/test_ui_styling.py
git diff --check
```

This slice adds no new browser behavior or dependency. Visual review at the
existing responsive breakpoints is still separate from these automated checks.

## Issue #159: recorded order date and total

`tests/test_order_summary_browser.py` executes the production order page in
Chromium/Chrome, routes requests through real FastAPI handlers, and uses fresh
SQLite files. Third-party map resources are blocked; map rendering is outside this
fix. Prices and timestamps below are independent expected purchase facts.

| Case | Expected result |
|---|---|
| Two shops, vouchers, catalog edited after purchase; 390/768/1280 px; reload | Stored 2026-01-02 15:04 UTC displays as 22:04 GMT+7; grand total is 433,000 VND with no viewport overflow |
| Real zero-total voucher checkout | Grand total is 0 VND and zero discounts remain 0 |
| Switch discounted order and legacy-pricing order | Stored totals and breakdowns reload correctly; unavailable legacy explanation is visible |
| Detail read fails, then Retry succeeds | Summary stays hidden on failure; Retry displays the receipt |
| Another authenticated buyer opens the order URL | API denies access; no summary or item details are shown |

Run with Python 3.12, README dependencies, Playwright, and installed Chrome:

```powershell
python -m pytest tests/test_order_summary_browser.py -q
python -m ruff check tests/test_order_summary_browser.py
node --check src/web/static/order.js
git diff --check
```

Set `UPDATE_ORDER_SUMMARY_SCREENSHOTS=1` to regenerate deterministic screenshots.

## Task #156: responsive, keyboard and contrast audit

Expected behavior comes from #156, parent #114, the plan's viewport matrix and WCAG 2.2 AA.
`tests/test_responsive_audit_browser.py` loads 13 pages in headless Chromium against the
production FastAPI handlers and an isolated SQLite file, with deliberately awkward data:
very long product, seller, recipient and address text, a 10-digit price, six long
notifications, an order and a cart line.

| ID | Partition / action | Expected result | Verification |
|---|---|---|---|
| R156-01 | Each page at 320, 375, 390, 768, 1024 and 1440 px | No page-level horizontal scroll (`scrollWidth <= innerWidth`) and no uncaught page error | Per-page/viewport matrix (78 cases) |
| R156-02 | Visible text on flat backgrounds | Contrast >= 4.5:1, or 3:1 for text >= 24px (or >= 18.66px bold) | In-page luminance check |
| R156-03 | First six Tab stops | Focused element lies horizontally inside the viewport, overlaps it vertically (it may be taller than the viewport) and shows an outline or box-shadow ring | Keyboard walk plus four off-screen/tall regression cases |
| R156-04 | Visible input, select, textarea | Has a label, `aria-label`, `aria-labelledby` or title | DOM check |
| R156-05 | Buttons, checkboxes, radios | Target (or its label) at least 24 x 24 CSS px | Bounding-box check |

Pages: `/products`, `/products/:code`, `/login`, `/cart`, `/checkout`, `/orders`,
`/notifications`, `/seller/orders`, `/seller/products`, `/seller/products/new`,
`/seller/vouchers`, `/seller/analytics`, `/admin`.

Defects found on `main` and fixed in CSS/markup only: success text (3.77:1), warning/rating
text (3.19:1), muted order text (4.47:1), the order breadcrumb separator (1.47:1), the
notification time (4.37:1), the "Seller Center" badge (2.54:1), and 18 px checkbox/radio
labels below the 24 px target. The stricter focus check then found the scrollable products table on `/seller/products` as a keyboard stop with no ring; it is now a labelled `region` with a visible focus outline. Contrast tokens were darkened (`--color-text-muted` after the #154/#155 merge, where table headers measured 4.34:1, `--color-success`,
`--color-warning`, `--ios-text-muted`); no layout or DOM contract changed.

Run:

~~~powershell
$env:DEBUG = 'false'
pip install playwright   # uses an installed Chrome/Chromium; set BROWSER_PATH to override
python -m pytest tests/test_responsive_audit_browser.py -q
~~~

Limits, stated so a pass is not over-read: contrast is skipped for gradient or image
backgrounds and hover/disabled states; focus checks cover the first six Tab stops only;
modals, error summaries, loading and empty states are not driven here; `/checkout` has no
saved address and `/seller/analytics` has no sales data in this fixture; this is Chromium
only. Manual browser QA with evidence, and a rerun after the shared design tokens
(#154/#155) merge, are still required and are not claimed by this task.
