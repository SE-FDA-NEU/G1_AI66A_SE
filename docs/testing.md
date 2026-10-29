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
