# US20 — Payment methods, payment status and escrow settlement (contract)

Story #112, tasks #148 (payment fields, state validation, escrow and settlement), #149
(payment selector and status display) and #150 (payment and settlement tests).

**Status: contract only.** It is written against `main` at
`17638838a5eb1369a42df694c0d3b59a17c06d49` (after PR #171). Part of the state already
exists there (section 1). Everything else is a proposal that the owners of #148–#150
confirm or amend in their own pull requests. New error codes join `docs/design.md`
section 3.4 only in the PR that first raises them; `tests/test_ui_docs_contract.py`
requires that table to match the codes in `src/`. This contract needs no new API error
code.

## 1. What `main` already has, and what must change

PR #170 (returns and refunds, #109) added `payment_status` and `escrow_status` to both
`orders` and `seller_orders`. This contract keeps those columns, so there is no parallel
set of payment fields, and fixes the behaviours that conflict with the #112 criteria:

| Today on `main` | Conflict with #112 | Contract |
|---|---|---|
| Every new order and seller order defaults to `payment_status = 'PAID'`, `escrow_status = 'HELD'`, whatever the method | AC1: the initial state is stored; a COD order has not been paid at checkout | Checkout writes the initial state explicitly (section 3); the model default becomes `UNPAID` |
| No payment method is stored | AC1 | New `orders.payment_method` |
| `sync_parent_order_state()` can set parent `payment_status = 'PARTIALLY_REFUNDED'` | AC2: only `UNPAID`, `PAID`, `REFUND_PENDING`, `REFUNDED`, `FAILED` are valid | A partial refund is shown by per-seller-order status and amounts; the parent stays `PAID` (section 2.2) |
| Approving a return sets `payment_status = 'REFUNDED'` and `escrow_status = 'REFUNDED'` without checking that a payment was recorded | AC5: the refund state reflects money actually refunded | Refund only what was captured (section 6); the escrow becomes `VOIDED` |
| Rejecting a return sets `escrow_status = 'RELEASED'` unconditionally | AC3, AC4: release needs `COMPLETED` and a recorded payment | Rejection runs the same release guard as completion (section 5) |
| Completing a seller order never changes `escrow_status` | AC4: settlement happens at completion | Every completion path runs the release guard |
| Cancelling a seller order leaves `PAID` and `HELD` | AC5 | Cancellation voids the settlement and refunds a captured payment once |
| US18 analytics reports gross line totals of `COMPLETED` seller orders | AC4 defines seller net income | Gross sales stay; settled income is a separate figure (section 8) |

All writes to `payment_status`, `escrow_status` and the settlement columns go through
`src/services/payments.py` (section 9). Today `src/services/returns.py` assigns them
directly; #148 moves those assignments into payment-service calls.

## 2. States

### 2.1 Payment methods

| Method | Mode this sprint | Initial `payment_status` | How `PAID` is recorded |
|---|---|---|---|
| `COD` | Tracked, no provider | `UNPAID` | For each seller order, when that seller order reaches `DELIVERED`, or `COMPLETED` straight from `SHIPPED`; source `COD_COLLECTED` |
| `VIETQR` | Tracked demo, no provider | `UNPAID` | The demo operator command (section 7) records `PAID` or `FAILED` for the whole order; source `DEMO_OPERATOR` |
| `WALLET` | Tracked demo, no provider | `UNPAID` | Same as `VIETQR` |
| `CARD` | Tracked demo, no provider | `UNPAID` | Same as `VIETQR`. No card data is collected, stored or sent anywhere |

No method talks to a real provider in this sprint, and no public endpoint lets a buyer or
seller mark a payment `PAID`. The UI (#149) says that VIETQR, WALLET and CARD are demo
methods, and never shows a payment as successful before a result is recorded.

### 2.2 Payment status

`payment_status` on a seller order describes that shop's share, its `total_amount`. On
the parent order it is a summary. Both use only the five #112 values.

| From | To | When |
|---|---|---|
| `UNPAID` | `PAID` | A recorded result: COD collection, demo operator result or zero total |
| `UNPAID` | `FAILED` | A recorded failed attempt (prepaid methods only) |
| `FAILED` | `UNPAID` | The operator starts a new attempt; recorded as its own event |
| `PAID` | `REFUND_PENDING` | A refund is created for a cancellation or an approved return |
| `REFUND_PENDING` | `REFUNDED` | The refund succeeds; in tracked mode, in the same transaction |
| `REFUND_PENDING` | `PAID` | The refund fails |
| `REFUNDED` | — | Terminal |

Any other change is rejected by the payment service, whichever caller asks. A
duplicate result (same event key) changes nothing. A `FAILED` result that arrives after
`PAID` is recorded as ignored and never moves the state back.

**Parent summary.** If any seller order is `REFUND_PENDING`, the parent is
`REFUND_PENDING`. If every seller order that was ever paid is `REFUNDED`, the parent is
`REFUNDED`. If some are `REFUNDED` and others `PAID`, the parent stays `PAID`, and the
receipt shows `refunded_amount > 0`. Otherwise the parent takes the shared value:
`UNPAID`, `PAID` or `FAILED`. Seller orders cancelled while still unpaid keep `UNPAID`
and do not affect the summary of the others.

### 2.3 Escrow status

| Value | Meaning |
|---|---|
| `HELD` | Escrow pending: the seller order is active, its net amount is not settled income |
| `PAUSED` | A return request is under review (already set by `submit_return_request`) |
| `RELEASED` | The seller net amount is settled income, exactly once (section 5) |
| `VOIDED` | The seller order was cancelled or its return approved; nothing will be settled |

`VOIDED` replaces the escrow value `REFUNDED` used on `main`, because the escrow of an
unpaid cancelled order was never refunded. The parent `escrow_status` is a display
summary only, never used for settlement or analytics. It keeps the derivation in
`sync_parent_order_state()`, with `VOIDED` in place of `REFUNDED`: any `PAUSED` →
`PAUSED`, all `RELEASED` → `RELEASED`, all `VOIDED` → `VOIDED`, any `HELD` → `HELD`,
otherwise `PARTIALLY_SETTLED`.

## 3. Checkout

Both checkout body shapes (manual delivery and saved address, US13) gain
`payment_method`, one of the four methods; any other value is `422 ERR_VALIDATION` with
`error.fields.payment_method`. Until the checkout UI sends a method (#149), a body
without it is recorded as `COD`. That is the only method that needs nothing up front, and
the current page already places orders without any payment step. After #149 merges, a
new order without a method is rejected after the replay check, so pending older requests
still replay; US16 section 5.4 handles a missing quote the same way. A body without the field
hashes byte-for-byte as it does today (`test_legacy_hash_stays_compatible` stays
unchanged); a body with it includes it in the hash.

Inside the existing checkout transaction, after the seller orders exist:

1. `orders.payment_method` is set; parent and seller orders start `UNPAID`, escrow
   `HELD`.
2. Each seller order stores `commission_rate_bps` and computes `commission_amount` and
   `seller_net_amount` (section 4).
3. A seller order whose `total_amount` is 0 is recorded `PAID` with source
   `ZERO_TOTAL` and amount 0, whatever the method, because there is nothing to collect.
4. Nothing is committed by the payment service; `checkout()` keeps its single commit.

Idempotent replay returns the stored payment fields and creates no new event.

## 4. Settlement amounts

All amounts are integer VND. With the US16 seller-order snapshot (`docs/us16-promotions.md`
section 2): `B_s = subtotal - shop_discount`.

```text
C_s = B_s * commission_rate_bps // 10000       floor
seller_net_amount = B_s - C_s
```

The platform-funded discounts (`platform_discount`, `shipping_discount`) are not
deducted from seller income, and the shipping fee is not seller income. Proposed rate:
**500 bps (5%)**, a named constant in `src/services/payments.py`, snapshotted on each
seller order. A later rate change never re-prices stored orders.

US16 defines the `seller_orders` snapshot columns `subtotal`, `shop_discount`,
`platform_discount`, `shipping_fee`, `shipping_discount` and `total_amount`. Whichever of
#135 and #148 merges first adds them, exactly as US16 section 6 defines them, and the
other reuses them. Until vouchers exist, `B_s = subtotal`.

Worked example, continuing US16 section 2.1, at 500 bps:

| Component | Shop A | Shop B | Order |
|---|---:|---:|---:|
| Buyer pays `total_amount` | 248.000 | 185.000 | 433.000 |
| `B_s` | 270.000 | 200.000 | 470.000 |
| Commission `C_s` | 13.500 | 10.000 | 23.500 |
| **Seller net** | **256.500** | **190.000** | 446.500 |

Seller net can exceed what the buyer paid because the platform funds 47.000 ₫ of
platform discount and 30.000 ₫ of shipping discount. Per order, this reconciliation
holds and #150 asserts it:
`sum(total_amount) − sum(seller_net) − sum(shipping_fee) = sum(commission) −
sum(platform_discount) − sum(shipping_discount)`; here `433.000 − 446.500 − 40.000 =
23.500 − 47.000 − 30.000 = −53.500`.

| Boundary case | Expected |
|---|---|
| `B_s` 180.000, no vouchers | commission 9.000, net 171.000 |
| `B_s` 10.001 | commission 500 (floor of 500.05), net 9.501 |
| `B_s` 0 | commission 0, net 0 |

## 5. Release guard

A seller order moves `HELD → RELEASED` only when **all** of these hold. It then sets
`settled_at`, exactly once:

- `status = 'COMPLETED'`;
- `payment_status = 'PAID'`;
- `escrow_status = 'HELD'` (not `PAUSED`, `RELEASED` or `VOIDED`);
- `orders.payment_method IS NOT NULL` (section 10: legacy orders never release).

The guard is a conditional update whose rowcount decides whether the release happened:

```sql
UPDATE seller_orders SET escrow_status = 'RELEASED', settled_at = :now
WHERE id = :id AND status = 'COMPLETED' AND payment_status = 'PAID'
  AND escrow_status = 'HELD'
  AND EXISTS (SELECT 1 FROM orders o
              WHERE o.id = seller_orders.order_id AND o.payment_method IS NOT NULL)
```

It runs after every event that can make it true: every completion path (buyer
confirmation and both seller status routes), a payment result that arrives after
completion, and a rejected return. Completing an unpaid COD or prepaid order leaves it
`HELD`; a payment recorded before completion leaves it `HELD` until completion.

## 6. Cancellation and refund

| Event | Seller order payment | Escrow |
|---|---|---|
| Cancelled while `UNPAID` or `FAILED` | Unchanged, nothing to refund | `VOIDED` |
| Cancelled while `PAID` | `PAID → REFUND_PENDING → REFUNDED`, `refunded_amount = total_amount` | `VOIDED` |
| Return requested (`DELIVERED → RETURN_REQUESTED`) | Unchanged | `HELD → PAUSED` |
| Return approved, seller order `PAID` | `PAID → REFUND_PENDING → REFUNDED`, `refunded_amount = total_amount` | `VOIDED` |
| Return approved, seller order not `PAID` | Unchanged | `VOIDED` |
| Return rejected (seller order becomes `COMPLETED` on `main`) | Unchanged | `PAUSED → HELD`, then the release guard |
| Prepaid result `PAID` arrives after a seller order was cancelled | That share goes `PAID → REFUND_PENDING → REFUNDED` | Stays `VOIDED` |

A refund is the seller order's full `total_amount`, shipping included. Returns cover a
whole seller order on `main`, and a cancellation happens before shipment. The refund
runs once: a conditional update `WHERE payment_status = 'PAID'` plus the unique event key
`refund:seller-order:{id}`. A retry, or a second route, refunds nothing more. In tracked
mode the refund succeeds in the same transaction; with a real provider it would stay
`REFUND_PENDING` until a callback, which is out of scope. Cancelling or refunding one
shop never refunds another shop's share.

Cancellation reaches `CANCELLED` through the three paths listed in US16 section 7. The
payment calls belong in the same shared cancellation function as the voucher restore
(#128), not in each route.

## 7. Recording results

`payment_events` stores one row per recorded payment or refund result. It is the audit
trail and the deduplication key:

| Column | Rule |
|---|---|
| `id` | Integer primary key |
| `order_id` | FK `orders.id` |
| `seller_order_id` | FK `seller_orders.id`; NULL when the result covers the whole order |
| `event_key` | `VARCHAR(128)`, UNIQUE |
| `kind` | `PAYMENT_RESULT` or `REFUND` |
| `source` | `COD_COLLECTED`, `DEMO_OPERATOR`, `ZERO_TOTAL`, `TRACKED_REFUND` |
| `from_status`, `to_status` | Story enum values; equal when the event was ignored |
| `amount` | Integer `>= 0` |
| `actor_user_id` | FK `users.id`; NULL for the operator command |
| `created_at` | UTC |

Event keys: `cod:seller-order:{id}`, `zero-total:seller-order:{id}`,
`refund:seller-order:{id}`, and the key the operator passes for demo results. The
service inserts the event first with `ON CONFLICT (event_key) DO NOTHING`. When nothing
is inserted, the result is a duplicate, and the call returns the current state without
any other write.

**Demo operator command** (prepaid methods): `python -m src.payments record-result
--order <id> --result PAID|FAILED|RETRY --event-key <key>`. It runs locally against the
configured database, in its own transaction, and prints the new state. It has no HTTP
surface, so a buyer cannot reach it. A `PAID` result marks every `UNPAID`, non-cancelled
seller order `PAID`; cancelled ones go through the late-payment row in section 6. Then the
release guard runs.

## 8. Display and analytics

**Receipt** (`GET /api/v1/orders/{orderId}`, list and tracker page) gains
`payment_method` and the parent `payment_status`, plus `paid_amount` and
`refunded_amount` derived from the seller orders. Each `sub_orders[]` entry adds
`payment_status`, `escrow_status` and `refunded_amount`. The buyer view never shows
commission or seller net. The seller-scoped view (US16 section 5.2) shows only the
seller's own sub-order and adds its `commission_amount`, `seller_net_amount` and
`settled_at`. Labels for #149: `UNPAID` "Awaiting payment" (COD: "Pay on delivery"),
`PAID` "Paid", `REFUND_PENDING` "Refund in progress", `REFUNDED` "Refunded", `FAILED`
"Payment failed". #149 coordinates with bug #159 (order date and grand total missing
from order details), so both read the same persisted values.

**Analytics.** The US18 `revenue` figure (#169: gross line totals of `COMPLETED` seller
orders by `completed_at`) stays, and is labelled completed sales. #148 adds, scoped to
the seller:

| Figure | Definition | Time basis |
|---|---|---|
| `settled_income` | Sum of `seller_net_amount` where `escrow_status = 'RELEASED'` | `settled_at` |
| `escrow_pending` | Sum of `seller_net_amount` where `payment_status = 'PAID'` and `escrow_status IN ('HELD', 'PAUSED')` | State at request time |

Cancelled, returned-refunded, `VOIDED` and unpaid seller orders never count as settled
income. Response keys are added with US18's owner before merge.

## 9. Service interface (#148)

`src/services/payments.py` owns every write described above. Its functions take the
caller's `Session`, flush when they need an ID, and never commit or roll back:

| Function | Called by |
|---|---|
| `calculate_seller_net(b, rate_bps)` | Pure; checkout and tests |
| `start_payment(session, order, seller_orders, method)` | `checkout()` |
| `record_payment_result(session, order_id, result, source, event_key, actor_id)` | Operator command; COD collection |
| `refund_seller_order(session, seller_order, source, actor_id)` | Shared cancellation (#128), return approval |
| `try_release(session, seller_order)` | Completion paths, payment results, return rejection |
| `void_settlement(session, seller_order)` | Cancellation, return approval |
| `sync_parent_payment(session, order)` | Replaces the payment and escrow part of `sync_parent_order_state()` |

The status values are a `Literal` in the schemas and a frozen set in the service, and
the service rejects any other value with `ERR_INVALID_TRANSITION` (an existing code). A
test fails if any module other than `payments.py` assigns `payment_status`,
`escrow_status` or `settled_at`.

## 10. Persistence and migration

- `orders.payment_method` — `VARCHAR(10)`, NULL only for orders placed before US20.
- `seller_orders` adds `refunded_amount`, `commission_rate_bps`, `commission_amount` and
  `seller_net_amount` (integer, `NOT NULL DEFAULT 0`, `>= 0`), plus `settled_at`
  (nullable). The US16 snapshot columns follow section 4.
- `payment_events` is created from SQLModel metadata by `init_db()`.
- `migrate_db()` adds the missing columns. It maps `escrow_status 'REFUNDED'` to
  `'VOIDED'` on both tables, and parent `payment_status 'PARTIALLY_REFUNDED'` to
  `'PAID'`. A rerun changes nothing.

**Legacy orders** (`payment_method IS NULL`) were stored with the `PAID` default before
any payment was recorded, so that value is not evidence. The migration does not rewrite
it and invents no payment events. Instead, the release guard skips legacy orders, they
never count as settled income, and the UI shows "Payment not recorded" for them. The
#170 return flow keeps working on them.

## 11. Acceptance tests (#150 unless noted)

| Story criterion | Required evidence |
|---|---|
| AC1 method and initial state stored and shown | Checkout with each method stores it, with `UNPAID` (or `PAID` with `ZERO_TOTAL`); a legacy body is recorded as `COD`; the receipt and order page show both (#149) |
| AC2 only valid statuses | Every transition in section 2.2 passes and every other one is rejected; `PARTIALLY_REFUNDED` can no longer be written; duplicate event keys change nothing; `FAILED` after `PAID` never regresses |
| AC3 escrow pending until `COMPLETED` | `PAID` and `DELIVERED` stays `HELD`; return review is `PAUSED`; `escrow_pending` counts them, `settled_income` does not |
| AC4 seller net at completion | Section 4 example and boundary cases; release once through each completion path; complete-before-paid releases only when the payment arrives; the reconciliation identity holds |
| AC5 cancellation and refund recorded once | Each row of section 6; two routes or a retry refund once; one shop's refund leaves the other `PAID`; refunded orders never count as settled income or completed sales |
| Migration | Fresh database, a database from `main` at `17638838`, and a rerun; value mapping; legacy orders never release |

## 12. Decisions to confirm

| Decision | Proposal | Confirm in |
|---|---|---|
| Commission rate | 500 bps, snapshotted per seller order | #148, with the PO |
| COD collection | Recorded when the seller order reaches `DELIVERED` (or `COMPLETED` from `SHIPPED`) | #148, #106 owner |
| Demo results for prepaid methods | Local operator command, no HTTP surface | #148, #149 |
| Escrow value for cancelled or returned orders | `VOIDED` instead of `REFUNDED` | #148, #109 owner |
| Parent partial refund | Parent stays `PAID`; amounts and sub-order statuses show the split | #148, #109 owner |
| Refund amount | Full seller-order `total_amount`, shipping included | #148, #140 |
| Shipping an unpaid prepaid order | Proposal: block `SHIPPED` while a prepaid seller order is `UNPAID` | #148, #106 owner |
| Settled income in analytics | New `settled_income` and `escrow_pending`; US18 `revenue` stays gross | #148, US18 owner |
