# US14 — Atomic cancellation core (#128)

This branch is synced with `main` at `846f4b3` (includes merged PR #185 / #126)
and prepares the transactional cancellation core for review. It does not complete issue #128: restoring voucher
usage depends on the order-linked usage/allocation models in #133/#135, which are
not present on this base. Issue #128 must stay open until that integration is implemented and tested.
No voucher restoration stub is presented as working code.

## Entry points and transaction

The existing routes keep their request/response shapes:

- Buyer `POST /api/v1/orders/{id}/cancel`.
- Buyer `PATCH /api/v1/orders/{id}/status`, targeting `CANCELLED` or
  `CANCELLATION_REQUESTED`.
- Seller `PATCH /api/v1/seller/orders/{sub_order_id}/status`.
- Legacy seller `PATCH /api/v1/orders/{id}/status`.

Both seller routes call `seller_status_change()`. Buyer cancellations and requests
call `buyer_cancellation()` in `src/services/order_workflow.py`. The use case owns
one commit, including the transaction already started by authentication. Every
exception rolls it back. SQLite BUSY/LOCKED retries start from a rollback and are
bounded to five attempts; other database errors propagate to the existing handler.

The seller-order update compares the previously read status, payment status and
escrow status. Only the request that updates that row can apply the effects. Seller
confirmation, fulfilment and cancellation all use this conditional update, so a
stale confirmation cannot overwrite a committed cancellation. An invalid repeat
still returns the existing 400 business error; a concurrent stale write returns
409. This is protection against duplicate effects, not an HTTP idempotency-key API.

A successful cancellation performs these steps within that transaction:

1. Verify resource ownership and allowed child states. Buyers can directly cancel
   pending children; confirmed/processing orders require a request and seller approval.
2. Claim the seller-order transition with a conditional SQL update.
3. Restore the purchased quantity to its product or variant with SQL addition,
   including inactive inventory, and increment that inventory row's version.
   A missing inventory row fails the operation. Existing sales-count reversal is
   retained, including its legacy lower bound of zero.
4. For the tracked payment model currently on `main`, mark `PAID` as `REFUNDED`
   and escrow as `REFUNDED`. Preserve `UNPAID`/`FAILED`, with escrow `VOIDED`.
   Unexpected payment states require reconciliation and reject cancellation.
5. Persist history with the authenticated actor and a notification for the affected
   seller order, then derive parent status/payment/escrow from its children.
6. Commit once. Failure in inventory, notification, parent synchronization or commit
   rolls back the transition, refund status, inventory, sales counts and history.

`CANCELLATION_REQUESTED` does not restore inventory or mark payment refunded.
Cancelling one shop leaves other shops' stock, payment and fulfilment unchanged.
The parent retains the existing `PARTIALLY_REFUNDED` convention for mixed children.
No external payment provider is called and no refund amount ledger is introduced.
The pending payment contract in `docs/us20-payments.md` is not treated as an
already implemented payment service.

Parent shipping, delivery and completion timestamps use the latest non-null
timestamp from the seller orders, with UTC normalization for comparison. A shop
with a lower seller-order ID finishing later therefore advances the parent's
completion time correctly. Parent completion time reflects the latest recorded
child completion; it does not imply that every shop is complete while the parent
status is still `PROCESSING`.

If cancellation encounters a payment status other than `PAID`, `UNPAID` or
`FAILED`, it returns HTTP 409 `ERR_INVALID_PAYMENT_STATE` and leaves cancellation
effects unchanged. The payment must be reconciled before cancellation. The API
error table in `docs/design.md` records this contract.

## Integration before readiness

- **#133/#135:** use the persisted redemption/allocation identities to restore only
  eligible shop/platform voucher usage. A global `Voucher.used_count` alone cannot
  identify which order consumed a use, so this branch does not decrement it blindly.
  Add real-database tests for partial and full multi-shop cancellation, duplicate
  cancellation, and rollback after voucher restoration before closing #128.
- **#126 integrated:** the workflow consumes `is_allowed_transition()` from
  `src/services/order_states.py`. Seller APIs cannot create cancellation requests,
  and buyer cancellation validates both the parent and every active child.
  Conditional writes and the single transaction wrap those shared role rules.
- **PR #186 / #127 integration:** the workflow routes history writes through the
  shared audit service in this branch. Actor roles, validated notes and milestone
  timestamps are captured within the existing cancellation transaction; the
  authorized receipt/history contract is retained.
- **#148:** integrate the payment/refund amount ledger when available. Replace the
  current tracked status update and legacy escrow/parent conventions with the
  approved payment service in the same transaction, without calling a live provider
  from inside a database retry loop.

## Verification

`tests/test_atomic_cancellation.py` uses disposable SQLite files and reads results
through new sessions. It covers all four cancellation entry points, duplicate
requests, failures after inventory/notification/parent changes and at commit,
paid/unpaid/failed payments, multi-shop partial cancellation, request versus
approval, inactive variants, unauthorized access, and competing buyer/seller,
seller/seller and cancellation/confirmation requests.
The review regressions also exercise shipping/delivery/completion milestones
through both seller APIs in both ID orders, and confirm that unreconciled payment
states return 409 without committing cancellation effects.

Run from the repository root:

```bash
DEBUG=false .venv/bin/python -m pytest -q -o addopts='' \
  --basetemp=/tmp/issue128-review \
  tests/test_atomic_cancellation.py tests/test_order_states.py \
  tests/test_order_tracker.py tests/test_seller_orders.py tests/test_return_refund.py \
  tests/test_p0_flows.py tests/test_us15_reviews_notifications.py \
  tests/test_checkout.py tests/test_ui_docs_contract.py
.venv/bin/python -m ruff check src/api/orders.py src/api/seller_orders.py \
  src/services/order_workflow.py src/services/inventory.py src/services/returns.py \
  tests/test_atomic_cancellation.py
git diff --check
```

Focused validation after the review fixes: **144 passed** (one existing
Starlette deprecation warning), including the API milestone regressions and the
complete UI/API documentation contract suite. The eight Node page-script suites from CI also
passed. The initial full-suite run was stopped after main changed to #126; the focused
regression suites above passed on the final main integration.
Repository-wide Ruff currently reports eight pre-existing findings in
`tests/generate_ui_evidence.py` and `tests/test_ui_styling.py`; the changed Python
files pass Ruff. No unrelated formatting repair is included in this change.
