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

Run `python -m pytest tests/test_pricing.py tests/test_checkout.py tests/test_ui_docs_contract.py -q`
with `DEBUG=false` and the README Python 3.12 environment. Voucher permissions,
consumption/rollback, persisted receipts and browser checkout tests remain with
#133/#136 integration. No new UI or real-user test result is claimed here.
