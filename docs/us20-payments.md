# US20 — Payment methods, payment status and escrow settlement (contract)

Story #112, tasks #148 (payment fields, state validation, escrow and settlement), #149
(payment selector and status display) and #150 (payment and settlement tests).

**Status: contract only.** It is written against `main` at
`17638838a5eb1369a42df694c0d3b59a17c06d49` (after PR #171). Part of the state already
exists there (section 1). Everything else is a proposal that the owners of #148–#150
confirm or amend in their own pull requests.

Two kinds of rule appear below. **Binding** rules follow directly from the #112
acceptance criteria and from code already on `main`: the five payment statuses, release
only after `COMPLETED` with a recorded payment, no deduction of platform-funded
discounts, one refund per seller order, and the invariants in section 6.3.
**Pending** rules carry a decision ID (D1–D6) from section 12. They are proposals until
the owner named there confirms them in the linked issue, and the behaviour they cover is
not implemented before that confirmation. New error codes join `docs/design.md`
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
| Approving a return sets `payment_status = 'REFUNDED'` and `escrow_status = 'REFUNDED'` without checking that a payment was recorded | AC5: the refund state reflects money actually refunded | Refund only what was captured (section 6); the escrow becomes `VOIDED`. **#140:** an unpaid seller order keeps its payment status and gets `VOIDED`; any state other than `PAID`, `UNPAID` or `FAILED` is `409 ERR_INVALID_PAYMENT_STATE`. A paid one still uses escrow `REFUNDED`, like cancellation, until #148 renames it. The seller decision and the admin dispute decision (`POST /api/v1/admin/disputes/{id}/decision`) share `settle_return()` in `src/services/returns.py`, so both apply these rules |
| Rejecting a return sets `escrow_status = 'RELEASED'` unconditionally | AC3, AC4: release needs `COMPLETED` and a recorded payment | Rejection runs the same release guard as completion (section 5). **#140:** rejection releases only a `PAID` seller order, otherwise escrow returns to `HELD`, and sets `completed_at` |
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
| `COD` | Tracked, no provider | `UNPAID` | For each seller order, when that seller order reaches `DELIVERED`, or `COMPLETED` straight from `SHIPPED`; source `COD_COLLECTED` (D2) |
| `VIETQR` | Tracked demo, no provider | `UNPAID` | The demo operator command (section 7) records `PAID` or `FAILED` for the whole order; source `DEMO_OPERATOR` (D4) |
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

`VOIDED` (decision D5) replaces the escrow value `REFUNDED` used on `main`, because the escrow of an
unpaid cancelled order was never refunded. The parent `escrow_status` is a display
summary only, never used for settlement or analytics. It keeps the derivation in
`sync_parent_order_state()`, with `VOIDED` in place of `REFUNDED`: any `PAUSED` →
`PAUSED`, all `RELEASED` → `RELEASED`, all `VOIDED` → `VOIDED`, any `HELD` → `HELD`,
otherwise `PARTIALLY_SETTLED`. **#140:** until #148 renames `REFUNDED`, a mix of only
`REFUNDED` and `VOIDED` seller orders also summarizes as `VOIDED`, since neither holds escrow.

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
deducted from seller income, and the shipping fee is not seller income. The formula and
the per-seller-order snapshot are binding. The rate value is decision D1: proposed
**500 bps (5%)**, held in one named constant in `src/services/payments.py`. Tests take
the rate from the seller order's snapshot rather than repeating 500, so confirming
another rate changes only that constant. A later rate change never re-prices stored
orders.

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
completion, and a rejected return. Completing an unpaid prepaid order leaves it `HELD`
until its payment arrives; for COD, the completion itself records the payment (section
2.1). A payment recorded before completion leaves the order `HELD` until completion.

## 6. Cancellation and refund

| Event | Seller order payment | Escrow |
|---|---|---|
| Cancelled while `UNPAID` or `FAILED` | Unchanged, nothing to refund | `VOIDED` |
| Cancelled while `PAID` | `PAID → REFUND_PENDING → REFUNDED`, `refunded_amount = total_amount` | `VOIDED` |
| Return requested (`DELIVERED → RETURN_REQUESTED`) | Unchanged | `HELD → PAUSED` |
| Return approved, seller order `PAID` | `PAID → REFUND_PENDING → REFUNDED`, `refunded_amount = total_amount` | `VOIDED` |
| Return approved, seller order not `PAID` | Unchanged | `VOIDED` |
| Return rejected (seller order becomes `COMPLETED` on `main`) | Unchanged | `PAUSED → HELD`, then the release guard |
| Prepaid result `PAID` arrives after a seller order became `CANCELLED` or `RETURNED_REFUNDED` | That share goes `PAID → REFUND_PENDING → REFUNDED` | Stays `VOIDED` |

The refund amount is decision D3: proposed as the seller order's full `total_amount`,
shipping included. Returns cover a whole seller order on `main`, and a cancellation
happens before shipment, so no shipping cost has been incurred. Whatever amount D3
settles on, the refund runs once: a conditional update `WHERE payment_status = 'PAID'`
plus the unique event key `refund:seller-order:{id}`. A retry, or a second route,
refunds nothing more. In tracked mode the refund succeeds in the same transaction; with
a real provider it would stay `REFUND_PENDING` until a callback, which is out of scope.
Cancelling or refunding one shop never refunds another shop's share.

Cancellation reaches `CANCELLED` through the three paths listed in US16 section 7. The
payment calls belong in the same shared cancellation function as the voucher restore
(#128), not in each route.

### 6.1 Events arriving in any order

Payment results, workflow transitions and return decisions arrive from different
actors, in any order, and sometimes twice. Four rules keep the three levels (event log,
seller order, parent summary) consistent:

1. **One transaction per event.** The workflow change and its payment effects commit
   together. For example, the cancelling transaction sets `CANCELLED`, voids the escrow
   and records the refund, so no committed state is `CANCELLED` with `HELD`.
2. **Conditional writes.** Every payment and escrow change is an `UPDATE ... WHERE`
   on the value the handler expects. A rowcount of 0 means another transaction got
   there first. The handler then re-reads the seller order, applies the row of the
   matrix below for the state it actually finds, or does nothing. SQLite serializes
   writers, and the existing busy retry re-runs the whole handler.
3. **Parent recomputed, never incremented.** At the end of every handler,
   `sync_parent_payment()` rebuilds the parent `payment_status` and `escrow_status` from
   all of its seller orders, in the same transaction.
4. **Terminal values stay.** `payment_status` `REFUNDED` and `escrow_status`
   `RELEASED` or `VOIDED` never change again. Seller-order status `COMPLETED`,
   `CANCELLED` or `RETURNED_REFUNDED` cannot move to a state that would release or
   refund again; returns start only from `DELIVERED` on `main`.

Matrix: state found → event → result. "Ignored" means the event row is written with
`from_status = to_status` and nothing else changes; "no-op" means a duplicate key, so
nothing is written.

| Seller order found | Payment `PAID` result | `FAILED` result | Cancellation | Completion | Return approved | Return rejected |
|---|---|---|---|---|---|---|
| Not yet shipped, `UNPAID`, `HELD` | `PAID`, stays `HELD` | `FAILED` | `CANCELLED`, `VOIDED`, no refund | — | — | — |
| Not yet shipped, `PAID`, `HELD` | No-op or ignored | Ignored | `CANCELLED`, `VOIDED`, refund once | — | — | — |
| `SHIPPED` or `DELIVERED`, `UNPAID`, `HELD` | `PAID`, stays `HELD` | `FAILED` | Not allowed by the workflow | `COMPLETED`, stays `HELD` | — | — |
| `DELIVERED`, `PAID`, `HELD` | No-op or ignored | Ignored | Not allowed | `COMPLETED`, `RELEASED` | — | — |
| `COMPLETED`, `UNPAID`, `HELD` | `PAID`, then `RELEASED` | `FAILED`, stays `HELD` | Not allowed | — | — | — |
| `RETURN_REQUESTED`, any payment, `PAUSED` | `PAID` if it was `UNPAID`, stays `PAUSED` | Ignored if `PAID` | Not allowed | — | `RETURNED_REFUNDED`, `VOIDED`, refund once if `PAID` | `COMPLETED`, `HELD`, then the release guard |
| `COMPLETED`, `PAID`, `RELEASED` | No-op or ignored | Ignored | Not allowed | — | — | — |
| `CANCELLED` or `RETURNED_REFUNDED`, not `REFUNDED`, `VOIDED` | `PAID`, then refund once | Ignored | — | — | — | — |
| `CANCELLED` or `RETURNED_REFUNDED`, `REFUNDED`, `VOIDED` | Ignored | Ignored | — | — | — | — |

"—" means the workflow (US14 transitions and the #170 return rules) never delivers that
event in that state, and the payment service rejects it with `ERR_INVALID_TRANSITION`
if a caller tries. The `UNPAID` rows after shipment apply to prepaid methods. For COD,
reaching `DELIVERED`, or `COMPLETED` straight from `SHIPPED`, is itself the `PAID`
result (section 2.1). It is recorded in the same transaction as the transition, so a
COD seller order moves to the `PAID` rows at that moment. Completing a COD order
therefore releases at once.

### 6.2 Same end state in either order

For each pair below, applying the two events in either order gives the same final
state. #150 runs every pair in both orders, and also concurrently on two independent
SQLite connections.

| Events | Final seller order |
|---|---|
| `PAID` result and cancellation | `CANCELLED`, `REFUNDED`, `VOIDED`, one `REFUND` event |
| `PAID` result and completion | `COMPLETED`, `PAID`, `RELEASED`, one release |
| `PAID` result and return approval | `RETURNED_REFUNDED`, `REFUNDED`, `VOIDED`, one `REFUND` event |
| `PAID` result and return rejection | `COMPLETED`, `PAID`, `RELEASED`, one release |
| Two cancellations through different routes | `CANCELLED`, one `REFUND` event if it was paid |
| `PAID` result twice, same key | Identical to one result |

### 6.3 Invariants

These hold after every committed transaction. #150 checks them after each step of every
test, not only at the end. I3–I6 apply to non-legacy orders; legacy rows keep values
stored before US20 (section 10).

| ID | Invariant |
|---|---|
| I1 | `escrow_status = 'RELEASED'` ⇒ `status = 'COMPLETED'`, `payment_status = 'PAID'`, `settled_at IS NOT NULL` and the order has a `payment_method` |
| I2 | `status IN ('CANCELLED', 'RETURNED_REFUNDED')` ⇒ `escrow_status = 'VOIDED'`, so a cancelled or returned seller order is never settled |
| I3 | A seller order has at most one `REFUND` event (unique key), and `refunded_amount` equals that event's amount, or 0 without one |
| I4 | `payment_status = 'REFUNDED'` ⇔ a `REFUND` event exists for that seller order |
| I5 | `refunded_amount <= total_amount` |
| I6 | The parent `payment_status` and `escrow_status` equal the summary of their seller orders (sections 2.2 and 2.3) |
| I7 | A seller order counts in `settled_income` ⇔ `escrow_status = 'RELEASED'` |
| I8 | `payment_method IS NULL` ⇔ the order is legacy (section 10); a legacy order has no payment events and is never `RELEASED` |

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
commission or seller net. Legacy orders follow section 10. The seller-scoped view
(US16 section 5.2) shows only the
seller's own sub-order and adds its `commission_amount`, `seller_net_amount` and
`settled_at`. Labels for #149: `UNPAID` "Awaiting payment" (COD: "Pay on delivery"),
`PAID` "Paid", `REFUND_PENDING` "Refund in progress", `REFUNDED` "Refunded", `FAILED`
"Payment failed". #149 coordinates with bug #159 (order date and grand total missing
from order details), so both read the same persisted values.

**Analytics.** The US18 `revenue` figure (#169: gross line totals of `COMPLETED` seller
orders by `completed_at`) stays, and is labelled completed sales. #148 adds (decision D6), scoped to
the seller:

| Figure | Definition | Time basis |
|---|---|---|
| `settled_income` | Sum of `seller_net_amount` where `escrow_status = 'RELEASED'` | `settled_at` |
| `escrow_pending` | Sum of `seller_net_amount` where `payment_status = 'PAID'` and `escrow_status IN ('HELD', 'PAUSED')` | State at request time |

Cancelled, returned-refunded, `VOIDED`, unpaid and legacy seller orders never count as
settled income (I2, I7, section 10). Response keys are added with US18's owner before
merge.

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
  `'VOIDED'` on both tables, sets `escrow_status = 'VOIDED'` on seller orders that are
  already `CANCELLED` or `RETURNED_REFUNDED` (cancellations on `main` left them
  `HELD`), recomputes the parent escrow summary, and maps parent `payment_status
  'PARTIALLY_REFUNDED'` to `'PAID'`. Afterwards I2 holds for every row, legacy
  included. A rerun changes nothing.

**Legacy orders.** An order is legacy exactly when `payment_method IS NULL` (I8).
Checkout always writes a method, a body without one included, so no new order can be
legacy. Legacy rows were stored with the `PAID` default before anything was recorded,
so that value is not evidence of payment. The migration leaves the stored value as it
is and invents no events. Every reader treats a legacy order as follows:

| Area | Legacy behaviour |
|---|---|
| Receipt API | `payment_method` is `null`, and `payment_status` (parent and each `sub_orders[]` entry) is returned as `null`, not the stored default. `escrow_status` is returned as stored. `paid_amount` and `refunded_amount` are `null` |
| Order page and confirmation (#149) | "Payment not recorded (order placed before payment tracking)" instead of a payment badge; no amount paid or refunded is shown |
| Seller receipt | `commission_amount`, `seller_net_amount` and `settled_at` are `null` |
| Settlement | The release guard never matches (section 5), so the escrow stays `HELD` and becomes `VOIDED` on cancellation or approved return (I2) |
| Payment results | The payment service rejects any result or operator command for a legacy order with `ERR_INVALID_TRANSITION`, so no event is ever written for it (I8) |
| Cancellation or return approval | Status changes as today, escrow becomes `VOIDED`, `payment_status` is left as stored, and no `REFUND` event or `refunded_amount` is written |
| US18 completed sales (`revenue`) | Unchanged: a legacy `COMPLETED` seller order still counts as gross completed sales, as it does on `main` today |
| `settled_income` and `escrow_pending` | Never included |
| Seed data | Demo orders that should show settled income are created with a method and recorded results, not as legacy rows |

## 11. Acceptance tests (#150 unless noted)

| Story criterion | Required evidence |
|---|---|
| AC1 method and initial state stored and shown | Checkout with each method stores it, with `UNPAID` (or `PAID` with `ZERO_TOTAL`); a body without a method is recorded as `COD`; the receipt and order page show both (#149) |
| AC2 only valid statuses | Every transition in section 2.2 passes and every other one is rejected; `PARTIALLY_REFUNDED` can no longer be written; duplicate event keys change nothing; `FAILED` after `PAID` never regresses |
| AC3 escrow pending until `COMPLETED` | `PAID` and `DELIVERED` stays `HELD`; return review is `PAUSED`; `escrow_pending` counts them, `settled_income` does not |
| AC4 seller net at completion | Section 4 example and boundary cases; release once through each completion path; complete-before-paid releases only when the payment arrives; the reconciliation identity holds |
| AC5 cancellation and refund recorded once | Each row of section 6 and the R criteria below |
| Event order | Every row of the section 6.1 matrix; every pair in section 6.2 in both orders and concurrently |
| Legacy orders | The L criterion below, against a database from `main` at `17638838` |
| Migration | Fresh database, a database from `main` at `17638838`, and a rerun; value mapping; I1–I8 hold afterwards |

Refund and settlement safety. These criteria are binding and do not depend on any
pending decision:

- **R1.** Given a seller order whose refund is recorded, when the cancellation or return
  approval is retried, or arrives again through another route, then no second `REFUND`
  event is written and `refunded_amount` is unchanged.
- **R2.** Given two refund attempts for one seller order on two independent SQLite
  connections, when they run concurrently, then exactly one `REFUND` event is
  committed and the other attempt changes nothing.
- **R3.** Given a seller order that is `CANCELLED` or `RETURNED_REFUNDED`, when a
  completion, payment result or release attempt follows, then its escrow stays `VOIDED`
  and `settled_income` does not change.
- **R4.** Given a seller order whose return is under review (`PAUSED`), when a payment
  result arrives or a release is attempted, then nothing is released until the return
  is rejected.
- **R5.** Given a seller order that is already `RELEASED`, when any further event
  arrives, then it is not released again and `settled_income` does not change.
- **R6.** After every step of every test above, invariants I1–I8 hold.
- **L.** Given a legacy order: the receipt returns `null` payment fields; completing it
  never releases; the operator command is rejected; cancelling or approving a return
  writes no refund; it counts in US18 completed sales but never in `settled_income` or
  `escrow_pending`.

## 12. Decision register

The rows below are **pending**: proposals, not agreements. An owner confirms a decision
with a comment in the issue listed. The PR that implements the behaviour links that
comment and changes the row to *Confirmed*. Until then, the "Blocked until confirmed"
work is not merged. Everything marked binding in this document is outside this table.

| ID | Decision | Proposal | Reason | Confirm in (owner) | Status | Blocked until confirmed |
|---|---|---|---|---|---|---|
| D1 | Commission rate | 500 bps, snapshotted per seller order | AC4 needs a rate; the formula itself is binding | #112 (PO `leducminh290506-eng`), #148 | Pending | Merging the settlement part of #148 |
| D2 | When COD counts as paid | When the seller order reaches `DELIVERED`, or `COMPLETED` straight from `SHIPPED` | Returns start from `DELIVERED`; recording it later would leave a returned COD order with nothing to refund, although the buyer paid on delivery | #106 and #109 (`teddywristh`), #148 | Pending | The COD collection hook in #148 and the COD rows of #150 |
| D3 | Refund amount | Full seller-order `total_amount`, shipping included | Returns cover a whole seller order on `main`; cancellation happens before shipment | #109 (`teddywristh`), #140, #148 | Pending | The amount in `refund_seller_order` |
| D4 | How prepaid demo results are recorded | Local operator command with no HTTP surface | #149 must not show success without a documented result; no public way to mark an order paid | #149 (`teddywristh`), #148 | Pending | The operator command and the #149 demo labels |
| D5 | Escrow value after cancellation or approved return | `VOIDED` instead of `REFUNDED` | An unpaid cancelled order's escrow was never refunded. Removing `PARTIALLY_REFUNDED` is binding (AC2) and not part of this row | #109 (`teddywristh`) | Pending | The escrow value mapping in the migration and the matching change in `returns.py` |
| D6 | Settled income in analytics | Add `settled_income` and `escrow_pending`; US18 `revenue` stays gross | AC3 and AC4 need settled income kept apart from completed sales | #110 (`leducminh290506-eng`) | Pending | The analytics response keys |

**Not part of this contract:** blocking `SHIPPED` while a prepaid seller order is
`UNPAID`. It was proposed in the first revision of this PR. It is a workflow rule for
#106, and the section 6.1 matrix gives the correct result whether or not it exists.
Raise it in #106 if the team wants it.
