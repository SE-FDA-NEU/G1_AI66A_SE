# US21 admin backend workflow (#151)

## Assigned boundary

Task #151, under #113, covers server authorization, category/account administration
and administrative return-dispute adjudication. `AdminUser` and its database-backed
role/status checks, account status APIs and account audit records already existed.
This task reuses them, adds category change history, and closes the transactional
gaps in escalation and adjudication. Platform voucher and product moderation APIs
already exist and retain their current behavior.

The admin voucher API also includes a narrow validation guard: the existing
fixed-amount/no-cap database rule now rejects invalid direct requests with 400
`ERR_INVALID_DISCOUNT` before persistence, instead of a database failure. Pricing
and eligibility policies are unchanged.

Admin screens (#152), story-wide route registration/security work (#153), external
payment-provider integration, new payment policies and new account-deletion policies
are outside this slice. There are no setup or dependency changes.

## Authorization and administrative history

All routes below use the existing `AdminUser` dependency. Authentication resolves
the signed token to the current database user: missing credentials produce 401;
buyers/sellers receive 403 `ERR_ADMIN_REQUIRED`; a restricted/suspended administrator
receives 403 `ERR_ACCOUNT_RESTRICTED`. Token role and database role must agree.
Administrative actor IDs come from that user, never a request field.

Category changes write `category_audit_logs` in the same transaction as the change.
Each record contains the category ID, admin ID, action, UTC time, and before/after
JSON snapshots of `name`, `slug`, `parent_id`, and `is_active`. The category ID is
intentionally not a foreign key: history must survive the existing legacy DELETE.
No-op updates add no history. Legacy deletion also audits reparented children.
No endpoint edits or deletes audit records.

| API | Contract |
|---|---|
| `GET /api/v1/categories` | Existing public list of active categories |
| `GET /api/v1/categories/admin` | Admin list including inactive categories |
| `POST /api/v1/categories` | Validated category creation; audit `CREATE` |
| `PATCH /api/v1/categories/{id}` | Update name/slug/parent/active state; audit `UPDATE` |
| `DELETE /api/v1/categories/{id}` | Existing soft deactivation; audit `DEACTIVATE` |
| `GET/POST /api/v1/admin/categories` | Legacy admin list/create; creation is audited |
| `PUT /api/v1/admin/categories/{id}` | Legacy update with shared hierarchy validation and audit |
| `DELETE /api/v1/admin/categories/{id}` | Existing legacy hard deletion, child reparenting and metadata unlinking; retained `DELETE` audit |
| `GET /api/v1/admin/category-audits?limit=100` | Newest first by time, then ID; limit is 1–100; before/after are objects or null |

Both mutation surfaces use the shared service to reject inactive/missing ancestors
and cycles, including cycles already present in a legacy chain. Their existing
error codes/statuses remain distinct: canonical hierarchy/parent errors use
`ERR_CATEGORY_HIERARCHY`/`ERR_CATEGORY_PARENT`; legacy routes map them to
`ERR_CATEGORY_CYCLE`/`ERR_PARENT_NOT_FOUND`. Existing child-deactivation and slug
uniqueness rules remain. Only an actual slug uniqueness failure is a slug conflict;
failed audit persistence is a database error and rolls back the category change.

`GET /api/v1/admin/users` and `GET /api/v1/admin/users/{id}` retain their current
account views and recent audit records. `PATCH /api/v1/admin/users/{id}/status`
accepts `ACTIVE`, `RESTRICTED` or `SUSPENDED`, plus a reason up to 500 characters.
Unknown fields are rejected. A real transition writes `AccountAuditLog` with the
authenticated admin, old/new status, reason and UTC timestamp. No-op changes add
no event. Existing self-restriction prevention and seller-suspension deactivation
remain. An already issued token cannot bypass the user's updated database status.
Account status, audit and any product deactivation commit together.

## Escalation and adjudication

`POST /api/v1/admin/disputes` preserves the existing query-parameter API:
positive `order_id`, positive `seller_order_id`, a nonblank reason (up to 500
characters) and nonblank evidence (up to 1,000 characters). It returns 201 and the
dispute object. The seller order must belong to the supplied parent and be
`DELIVERED` or `RETURN_REQUESTED`; there can be only one dispute per seller order.

Escalation conditionally changes the seller order to `RETURN_REQUESTED` and escrow
to `PAUSED`, links a matching pending buyer request when available, records
`created_by_user_id`/`created_at`, and derives the parent state. A new status
transition also records the admin actor/role in order history at that same instant.
An existing buyer transition is preserved without adding a duplicate event. A
changed seller order fails the conditional claim with a concurrency error.

`GET /api/v1/admin/disputes` includes the creation actor and decision facts.
`POST /api/v1/admin/disputes/{id}/decision` preserves its JSON request:

```json
{"action": "APPROVE", "decision_notes": "Evidence reviewed", "is_restockable": true}
```

Actions are `APPROVE` or `REJECT`; notes are at most 1,000 characters. Unknown
fields, including client-supplied decision actors or timestamps, are rejected.
Before writing, the service verifies the dispute/order/buyer/seller relationships,
the pending dispute and linked request, and the shared return settlement rules.
It conditionally claims both dispute and linked request, requiring each update to
succeed. A resolved request cannot be overwritten by a later dispute decision.

Settlement uses `services/returns.py`, which also serves seller decisions, and the
payment service merged in #148. Under the [US20 contract](us20-payments.md), an
approved tracked paid return records one `REFUND` event with the authenticated
admin, sets payment to `REFUNDED`, records the refunded amount and voids escrow.
Unpaid/failed returns retain payment state and also void escrow. Approval requiring
payment reconciliation is rejected. Rejection completes the seller order, resumes
escrow and invokes the shared release guard. Only tracked, paid completed orders
can release settlement. Legacy payment snapshots are not proof of collection:
their stored payment status is preserved, with no invented refund event/amount or
settlement time. This task adds no external provider call.

Stock and sales counters change only for an approved, explicitly restockable
return. The common helper restores the exact purchased product or variant,
including inactive inventory, and floors its product sales counter at zero.
Rejection never restocks, even if `is_restockable` was requested.

Dispute/request decision fields, seller/parent state, conditional restocking,
order history, and buyer/seller notifications share one service-owned commit.
Any failure rolls the operation back. A repeat decision is rejected without
restocking or notifying again. Decision time, transition time, new completion
milestones and notification times use the same UTC instant; existing milestones
are preserved.

## Migration and verification

Initialization creates the category audit table and adds nullable
`return_disputes.created_by_user_id` referencing users. Existing disputes retain
an unknown creation actor as null. No action history or actor is fabricated from
current users or unrelated order events. Initialization/migration is repeatable
and preserves the other recorded dispute facts.

The expected-results matrix and reproducible commands are maintained in
[testing.md](testing.md#task-151-admin-authorization-and-dispute-workflow).
CI, a clean-clone run, teammate review and user validation require separate evidence.

The frontend slice is tracked separately in [#152](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/152).
