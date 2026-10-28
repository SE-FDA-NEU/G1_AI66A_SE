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

Risk priority: persisted audit facts, tenant isolation and rollback are checked
first because incorrect identity/history can mislead users about fulfilment and
failed partial writes can leave inconsistent orders. Browser tests are not added:
this task changes backend data, with no new screen or UI interaction.
