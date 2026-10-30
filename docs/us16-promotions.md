# US16 — Vouchers, discount allocation and shipping (contract)

Story #108, tasks #133 (voucher model and validation), #134 (seller voucher UI),
#135 (pricing and shipping), #136 (checkout voucher UI) and #137 (combo rules).

**Status: partial implementation.** Task #135 implements the pure calculation
service in sections 2 and 4, with the integration boundary in section 2.3. It does
not activate voucher pricing in checkout. The persistence/eligibility, quote API,
checkout UI and transaction wiring remain assigned to their respective tasks.
Those portions below are contracts, not evidence of completed integration.
Task #136 now implements the quote API (5.1), quoted checkout (5.2), the quote revision
(5.3) and the checkout page; see section 5.6 for what it covers and what is left. Error
codes join `docs/design.md` section 3.4 only when first raised in code;
`tests/test_ui_docs_contract.py` requires that table to match `src/` exactly.

## 1. Ownership and interfaces

| Module | Responsibility | Task |
|---|---|---|
| `src/services/pricing.py` | Pure calculation: shop discount, platform allocation, shipping, totals. No database access, no commit | #135 |
| `src/services/vouchers.py` | `validate_for_quote` (read only), `consume_for_order`, `restore_for_cancellation`. Flush only; never commit or roll back | #133; restore wired in by #128 |
| `src/services/orders.py` | Checkout coordinator: replay, quote check, stock, voucher consumption and persistence in the existing transaction | #136 |
| `src/api/seller_vouchers.py` | Seller-scoped voucher management | #134 |
| `src/web/static/checkout.js` | One checkout state: address (US13), vouchers, quote, submit | #136 |

The checkout use case keeps its single commit. Persistence helpers receive the
request `Session`, may `flush`, and leave commit and rollback to `checkout()`, as
US13 does for address resolution. The pure pricing service receives no session.

## 2. Money model

All amounts are integer VND. For each seller order `s` in one checkout:

```text
S_s = sum(quantity_i * unit_price_i)          selected cart lines only (US12)
D_shop_s = shop voucher discount              0 <= D_shop_s <= S_s
B_s = S_s - D_shop_s                          post-shop-discount subtotal
D_platform = platform voucher discount        0 <= D_platform <= sum(B_s)
D_platform_s = allocation of D_platform       0 <= D_platform_s <= B_s
H_s = shipping fee                            section 4
F_s = shipping discount                       0 <= F_s <= H_s
T_s = B_s - D_platform_s + H_s - F_s          seller-order total, never negative

Order.total_amount = sum(T_s)                 grand total
```

**Item discount.** `FIXED_AMOUNT`: `min(value, basis)`. `PERCENTAGE`: the value is in
basis points (1–10000), discount `= basis * value // 10000` (floor), then capped by
`max_discount` when set and by the basis. The basis is `S_s` for a shop voucher and
`sum(B_s)` for a platform voucher.

**Platform allocation** uses integers only, no floats. With `W = sum(B_s)`:
`q_s = D_platform * B_s // W` and `r_s = D_platform * B_s % W`. The
`D_platform - sum(q_s)` leftover đồng go one each to the seller orders with the largest
`r_s`, ties broken by ascending `seller_id`. If `W = 0` no allocation is computed. This
keeps `sum(D_platform_s) = D_platform`, and a seller order with `B_s = 0` never
receives a đồng.

**Funding.** The seller funds the shop discount; the platform funds the platform and
shipping discounts. US20 (#112, #148) uses this split for settlement, so a
platform-funded discount does not reduce the seller's net amount.

### 2.1 Worked example

Shop A (`seller_id` 2) sells 2 × 150.000 ₫. Its voucher is `FIXED_AMOUNT` 30.000 ₫ with
a minimum of 200.000 ₫. Shop B (`seller_id` 3) sells 1 × 200.000 ₫ with no shop voucher.
The platform voucher is `PERCENTAGE` 1000 bps (10%), with `max_discount` 50.000 ₫ and a
minimum of 300.000 ₫. The shipping voucher is `FREE_SHIPPING` with `max_discount`
15.000 ₫.

| Component | Shop A | Shop B | Order |
|---|---:|---:|---:|
| Subtotal `S_s` | 300.000 | 200.000 | 500.000 |
| Shop discount | 30.000 | 0 | 30.000 |
| `B_s` | 270.000 | 200.000 | 470.000 |
| Platform discount (10% of 470.000 = 47.000) | 27.000 | 20.000 | 47.000 |
| Shipping fee | 20.000 | 20.000 | 40.000 |
| Shipping discount | 15.000 | 15.000 | 30.000 |
| **Total `T_s`** | **248.000** | **185.000** | **433.000** |

### 2.2 Boundary cases for #135 tests

| Case | Input | Expected |
|---|---|---|
| Fixed above basis | `FIXED_AMOUNT` 50.000 on `S_s` 40.000 | 40.000; `B_s` = 0 |
| Percentage cap | 1500 bps, `max_discount` 20.000, basis 300.000 | 20.000 |
| Percentage floor | 333 bps on 10.001 | 333 |
| Rounding leftover | 100 over `B` = 100 / 200 | 33 / 67 |
| Equal remainders | 100 over `B` = 100 / 100 / 100 (sellers 2, 3, 4) | 34 / 33 / 33 |
| Zero-basis shop | 999 over `B` = 0 / 1.000 / 3.000 (sellers 2, 3, 4) | 0 / 250 / 749 |
| Zero total basis | any platform voucher with `sum(B_s)` = 0 | rejected, `ERR_VOUCHER_NOT_APPLICABLE` |

### 2.3 Implemented calculation boundary (#135)

`src/services/pricing.py` owns the integer money calculation. It has no database,
network, clock or transaction access. The caller passes selected cart snapshots,
not client-supplied prices, and voucher rules already authorized/validated by
#133. Dates, minimums, seller ownership and usage limits are not inferred from a
calculation rule. Numeric/type guards reject malformed rules with `ValueError`;
they do not replace voucher eligibility validation.

```python
from src.services.pricing import (
    ItemDiscount, PricingLine, ShippingDiscount, price_order,
)

price = price_order(
    [PricingLine(seller_id=2, quantity=2, unit_price=150_000),
     PricingLine(seller_id=3, quantity=1, unit_price=200_000)],
    shop_discounts={2: ItemDiscount("FIXED_AMOUNT", 30_000)},
    platform_discount=ItemDiscount("PERCENTAGE", 1000, max_discount=50_000),
    shipping_discount=ShippingDiscount(max_discount=15_000),
)
assert price.grand_total == 433_000
```

- `PricingLine(seller_id, quantity, unit_price)` accepts positive integer seller
  IDs/quantities and non-negative integer VND prices. Lines are grouped by seller;
  shipping is charged once per seller order, including an item subtotal of zero.
- `ItemDiscount(discount_type, discount_value, max_discount=None)` is a frozen
  calculation snapshot. It accepts a positive fixed amount, or 1–10000 basis
  points with an optional positive cap. Fixed amounts do not have a separate cap.
  After #133 validation, copy those three fields from the resolved voucher. A shop
  mapping may contain only sellers in the selected lines; one mapping entry is
  the shop's single voucher slot.
- `ShippingDiscount(max_discount=None)` represents an eligible platform
  `FREE_SHIPPING` voucher. Omission means no shipping discount; an instance with
  no cap covers the fee of every seller order. A cap is applied independently to
  each seller order, not once to the checkout.
- `price_order` returns an immutable `OrderPrice`. Its `seller_orders` tuple is
  sorted by seller ID. Each row contains the six monetary snapshots from section
  6 plus seller ID and policy version. The order has aggregate `subtotal`,
  `shop_discount`, `platform_discount`, `shipping_fee`, `shipping_discount` and
  `grand_total`; allocations and totals reconcile exactly.
- `calculate_item_discount` and `allocate_platform_discount` expose the pure
  arithmetic for reuse. Allocation uses largest remainders and seller-ID ties;
  zero-basis shops receive zero and integer precision is retained above `2**53`.
- An empty selection raises `PricingError` with `code=ERR_EMPTY_CART` and
  `status=400`. A requested item voucher producing zero discount (including a
  zero platform basis) raises `ERR_VOUCHER_NOT_APPLICABLE`, status 409. The later
  quote/checkout adapter maps these errors into the existing API envelope. This
  task adds no HTTP endpoint or new response body.

`PricingError` and the existing `CheckoutError` inherit from the shared
`OrderError(Exception)` in `services/order_errors.py`. They retain the same
`code`, `message` and `status` contract, so #136 can catch `OrderError` for expected
business rejections. Invalid calculation inputs still raise `ValueError`; an
allocation that does not conserve the platform discount raises `RuntimeError`,
including under `python -O`. These indicate internal faults at this boundary and
must not be translated into ordinary 400/409 voucher rejections. Request schemas
and voucher eligibility validation run before this service is called.

For #136, read current cart/voucher state, validate eligibility, and call the same
calculator for quote and inside checkout's existing transaction. Consume usages
and persist the returned snapshots only in that transaction. A calculation or
later write failure must roll back the coordinator's work; this service never
commits or restores anything. Historical receipts continue to read stored facts.
Legacy checkout behavior is unchanged until the section 5.4 integration phase.

The test matrix and verification commands have one source:
[Task #135 in testing.md](testing.md#task-135-multi-vendor-pricing-and-shipping).

### 2.4 Zero-effect voucher decision and adapter behavior

A requested item voucher whose discount rounds to zero rejects the entire
`price_order` calculation with `ERR_VOUCHER_NOT_APPLICABLE`, status 409. For
example, a 1-bps shop voucher on 1 VND fails even when another shop has a positive
subtotal. The calculator returns no partial `OrderPrice` and does not silently
drop the requested voucher. This implements eligibility row 9 in section 3.2.

The #133 validator must reject the same zero-effect rule. Under the proposed
#136 quote contract (section 5.1), the adapter reports that voucher as `REJECTED`
and omits its calculation rule before pricing the remaining valid promotions;
the buyer can remove or replace the rejected code. Submitted checkout retains
the requested voucher set and aborts atomically on rejection (section 5.2).
The pure calculator itself never consumes usage or writes an order.

Coordination: explicit owner acknowledgement of this boundary from #133 and
#136 is still pending. The contract and tests record the decision; they do not
claim that cross-task confirmation has occurred.

## 3. Voucher rules

### 3.1 Types and slots

| Scope | Allowed `discount_type` | Slot | Basis for minimum and discount |
|---|---|---|---|
| `SHOP` | `FIXED_AMOUNT`, `PERCENTAGE` | At most one per seller order, owned by that seller | `S_s` |
| `PLATFORM` | `FIXED_AMOUNT`, `PERCENTAGE` | At most one per checkout (platform slot) | `sum(B_s)` |
| `PLATFORM` | `FREE_SHIPPING` | At most one per checkout (shipping slot) | Minimum on `sum(B_s)`; `F_s = min(H_s, max_discount or H_s)` for every seller order |

Stacking order is fixed: shop vouchers, then the platform voucher, then the shipping
voucher. No other combination is applied. Codes are trimmed and upper-cased before
storage and lookup; a code is unique across all vouchers, so one code identifies one
voucher.

### 3.2 Eligibility order and error codes

Each row gives the condition that **rejects** the voucher. The rows are evaluated in
order, and the first matching row decides the result. `now` is the server's UTC time. A
voucher is valid only while `starts_at <= now < ends_at`, so `ends_at` itself is already
expired.

| # | Rejected when | Status | Code |
|---|---|---|---|
| 1 | No voucher has this code | 404 | `ERR_VOUCHER_NOT_FOUND` |
| 2 | Scope or type does not match the slot, or a shop voucher belongs to a different seller than the seller order | 409 | `ERR_VOUCHER_SCOPE_MISMATCH` |
| 3 | `is_active` is false | 409 | `ERR_VOUCHER_INACTIVE` |
| 4 | `now < starts_at` | 409 | `ERR_VOUCHER_NOT_STARTED` |
| 5 | `now >= ends_at` | 409 | `ERR_VOUCHER_EXPIRED` |
| 6 | Basis `< min_order_value` | 409 | `ERR_VOUCHER_MIN_ORDER` |
| 7 | `usage_limit` is set and `used_count >= usage_limit` | 409 | `ERR_VOUCHER_USAGE_LIMIT` |
| 8 | `per_user_limit` is set and the buyer's `APPLIED` usages `>= per_user_limit` | 409 | `ERR_VOUCHER_USER_LIMIT` |
| 9 | Computed discount `= 0` | 409 | `ERR_VOUCHER_NOT_APPLICABLE` |
| — | `quote_revision` differs from the server's recomputed revision (section 5.3) | 409 | `ERR_QUOTE_STALE` |

Boundary tests for rows 4 and 5: `now = starts_at` passes, `now = starts_at - 1 µs`
gives `ERR_VOUCHER_NOT_STARTED`, `now = ends_at - 1 µs` passes and `now = ends_at`
gives `ERR_VOUCHER_EXPIRED`. Tests use an injected clock, not the machine time.

The statuses follow the existing table: an unknown resource is 404, as with
`ERR_PRODUCT_NOT_FOUND`, and a business state that blocks the action is 409, as with
`ERR_STOCK_EXCEEDED`. A malformed body is `422 ERR_VALIDATION` with `error.fields`: a
code outside 3–32 characters of `A–Z`, `0–9` and `-` after normalization, a repeated
`seller_id`, or the same code in two slots. Messages tell the buyer what to change, for
example the amount still needed to reach the minimum.

## 4. Shipping policy

Each seller order in a quoted checkout has a flat `H_s` of **20.000 ₫**. This matches
Scenario 1 and US04 acceptance criterion 1 in `docs/requirements.md` (180.000 ₫ +
20.000 ₫ = 200.000 ₫). The fee is a named constant in `src/services/pricing.py`, and
every seller order stores the policy version `US16-V1`. Changing the fee or the rules
means a new version; persisted orders are never re-priced. Address-based or
carrier-based shipping is out of scope, so the quote does not depend on the delivery
address.

## 5. API contract

### 5.1 Quote — `POST /api/v1/orders/quote`

Buyer only (401 for a guest, 403 for a seller). Prices the buyer's selected cart lines.
It never writes usages, counters, stock or orders. Body (every field optional, extra
fields forbidden):

```json
{
  "shop_vouchers": [{"seller_id": 2, "code": "SHOPA30K"}],
  "platform_voucher": "PLAT10",
  "shipping_voucher": "FREESHIP15"
}
```

Response `200`:

```json
{"data": {
  "currency": "VND",
  "pricing_policy_version": "US16-V1",
  "quote_revision": "<64 hex characters>",
  "seller_orders": [{
    "seller_id": 2, "items": [{"product_id": 7, "quantity": 2, "unit_price": 150000}],
    "subtotal": 300000, "shop_discount": 30000, "platform_discount": 27000,
    "shipping_fee": 20000, "shipping_discount": 15000, "total_amount": 248000,
    "shop_voucher": {"code": "SHOPA30K", "status": "APPLIED", "discount": 30000}
  }],
  "platform_voucher": {"code": "PLAT10", "status": "APPLIED", "discount": 47000},
  "shipping_voucher": {"code": "FREESHIP15", "status": "APPLIED", "discount": 30000},
  "grand_total": 433000
}}
```

Totals for `subtotal`, each discount and `shipping_fee` are also given at order level,
as in the table in section 2.1. A voucher that fails section 3.2 is returned as
`{"code": "OLD10", "status": "REJECTED", "error": {"code": "ERR_VOUCHER_EXPIRED",
"message": "..."}}`. It contributes 0, and the rest of the quote is still priced, so the
buyer sees the reason next to the voucher. Requesting a quote with no selected lines
returns `400 ERR_EMPTY_CART`, as checkout does today.

### 5.2 Checkout — `POST /api/v1/orders`

Both existing body shapes (manual delivery and `address_id` + `address_version`) gain
the optional voucher fields from section 5.1 plus `quote_revision`. The server:

1. Checks idempotency replay first, unchanged from US13. A committed key returns the
   stored order and its stored amounts, even if a voucher has since expired or changed.
2. Resolves the delivery snapshot (US13).
3. Prices again inside the transaction and compares `quote_revision`. A mismatch
   returns `409 ERR_QUOTE_STALE`, and nothing is written.
4. Applies section 3.2 to every requested voucher. Any failure aborts with that
   voucher's status and code. `error.fields` names each failing slot as
   `shop_vouchers.<seller_id>`, `platform_voucher` or `shipping_voucher`; `error.code`
   is the first failure in that slot order.
5. Updates stock, consumes vouchers (section 7), writes the order, seller orders, items
   and usages, deletes the selected cart rows and commits once.

A request without the new fields hashes byte-for-byte as it does today, so
`test_legacy_hash_stays_compatible` keeps passing unchanged. A request with the new
fields includes them in its hash. Reusing a key with different vouchers or a different
revision returns `ERR_IDEMPOTENCY_CONFLICT`.

The receipt (`GET /api/v1/orders/{orderId}`, also used by `GET /api/v1/orders`) adds the
per-seller-order breakdown and the applied codes. It reads them from persisted rows and
never re-runs pricing. `total_amount` keeps its meaning: the grand total. The
confirmation page and the `/orders/{orderId}` tracker page show the same persisted
values. A seller who opens the receipt (the `seller_id` path added in PR #164) sees only
their own seller order's breakdown, never another shop's amounts or the buyer's grand
total. On `main` that path still returns every item of the parent order, so the item
query has to be scoped to the seller before the breakdown is added.

### 5.3 Quote revision

`quote_revision` is SHA-256 over canonical JSON of the price-relevant inputs: buyer ID,
policy version, the selected lines sorted by product ID (product ID, quantity, current
price, active flag), each requested slot and code, the rule fields of each resolved
voucher (scope, seller, type, value, cap, minimum, window, active flag), and the
shipping fee. It **excludes** stock levels and usage counters, because they change with
every other buyer's checkout; they are checked again in the transaction and reported
with their own codes. The revision detects change only: it is not a credential, and the
client never decides a price.

### 5.4 Compatibility phases

| Phase | Behaviour |
|---|---|
| Until #136 merges | A checkout without `quote_revision` is priced as today: total = subtotal, no shipping, no vouchers, policy `LEGACY`. The current checkout page keeps working |
| After #136 | The checkout page always quotes and sends `quote_revision`. The server rejects new orders without it, after the replay check so pending legacy requests still replay. The note "No shipping fee is added at checkout" in `docs/ui.md` changes in the same PR |

### 5.5 Seller voucher management (#134)

`GET`/`POST /api/v1/seller/vouchers` and `PATCH /api/v1/seller/vouchers/{id}`, seller
only. `seller_id` comes from the token, and `scope` is always `SHOP`. The body forbids
`scope`, `seller_id` and `used_count`, so a seller cannot create a platform voucher by
editing the JSON. Another seller's voucher returns 404. Field errors use `error.fields`
(price, dates, limits). `usage_limit` cannot drop below `used_count`, and a code cannot
change once it has been used. Platform vouchers have no management API in this sprint:
the demo seed creates them, and admin management belongs to #151.

### 5.6 Implemented by #136

- `src/services/checkout_pricing.py` reads the selected cart at current prices,
  validates each requested code in slot order (shop, platform, shipping) with
  `validate_voucher`, and prices what stays eligible with `price_order`. The quote and
  checkout call the same function. It never writes; checkout consumes usages.
- `POST /api/v1/orders/quote` returns the section 5.1 body. A rejected code keeps its
  slot with `status: "REJECTED"` and the error; the rest is still priced.
- `quote_revision` covers the selected lines and current prices, the requested codes,
  and the rule fields of every requested voucher, including a rejected one. Usage
  counters are not part of it, so a voucher that runs out after the quote returns
  `ERR_VOUCHER_USAGE_LIMIT` with `error.fields.platform_voucher`, not `ERR_QUOTE_STALE`.
- A checkout body with `quote_revision` is re-priced in the transaction. A different
  revision returns `409 ERR_QUOTE_STALE`; any rejected voucher aborts with its own code
  and `error.fields`. Otherwise each seller order stores the six amounts and `US16-V1`,
  `orders.total_amount` is the grand total, and one usage per voucher is written.
  Everything rolls back together on failure.
- The idempotency hash leaves out unset voucher fields, so a legacy body hashes as
  before and `test_legacy_hash_stays_compatible` is unchanged.
- The receipt adds the stored breakdown to each `sub_orders` entry and a `vouchers`
  list read from `voucher_usages`. A seller sees only their own shop voucher.
- The checkout page has a voucher slot per selected shop plus platform and
  free-shipping slots. Apply and Remove re-quote. Confirm stays disabled until a quote
  without rejected vouchers arrives. An older quote response never replaces a newer one.
  The POST sends the reviewed `quote_revision`. A stale quote or voucher rejection
  re-quotes and asks the buyer to confirm again. The confirmation page shows the
  stored amounts.

**Not done in #136 (phase 2 of section 5.4):** the server still accepts a new order
without `quote_revision` and prices it as `LEGACY`. The checkout page always sends a
revision, but other callers and many existing tests post the legacy body. Rejecting it
is a separate change that updates those callers. The seller receipt also still shows
the parent `total_amount`, which section 5.2 asks to hide; that is unchanged here.

## 6. Persistence (#133)

`vouchers`:

| Column | Rule |
|---|---|
| `id` | Integer primary key |
| `code` | `VARCHAR(32)`, unique, normalized |
| `scope` | `SHOP` or `PLATFORM` |
| `seller_id` | FK `users.id`; NOT NULL exactly when `scope = 'SHOP'` (CHECK) |
| `discount_type` | `FIXED_AMOUNT`, `PERCENTAGE` or `FREE_SHIPPING`; `FREE_SHIPPING` only with `PLATFORM` (CHECK) |
| `discount_value` | VND `> 0` for `FIXED_AMOUNT`; 1–10000 bps for `PERCENTAGE`; 0 for `FREE_SHIPPING` |
| `max_discount` | NULL or `> 0`; only for `PERCENTAGE` and `FREE_SHIPPING` |
| `min_order_value` | `>= 0`, default 0 |
| `usage_limit` | NULL (unlimited) or `> 0` |
| `per_user_limit` | NULL (unlimited) or `> 0` |
| `used_count` | `>= 0` and `<= usage_limit` when the limit is set; equals the number of `APPLIED` usages |
| `starts_at`, `ends_at` | UTC; `starts_at < ends_at` (CHECK) |
| `is_active` | Boolean |
| `created_at`, `updated_at` | UTC |

`voucher_usages`, one row per redemption: `id`, `voucher_id`, `buyer_id`, `order_id`,
`seller_order_id` (set for `SHOP`, NULL for checkout-level vouchers), `code` (snapshot),
`discount_amount` (`>= 0`, the redemption's total), `status` (`APPLIED` or `RESTORED`),
`created_at` and `restored_at`. A UNIQUE `(voucher_id, order_id)` constraint allows
each voucher once per checkout.

`seller_orders` gains `subtotal`, `shop_discount`, `platform_discount`, `shipping_fee`,
`shipping_discount` and `total_amount` (integer, `>= 0`), plus `pricing_policy_version`.
These columns record the platform and shipping allocations, so no separate allocation
table is needed. For each order, the platform usage's `discount_amount` equals the sum
of `platform_discount`, and the shipping usage's equals the sum of `shipping_discount`.

**Migration.** `init_db()` creates the two new tables from SQLModel metadata.
`migrate_db()` adds each missing `seller_orders` column with `ALTER TABLE ... ADD
COLUMN` (`NOT NULL DEFAULT 0`, and `'LEGACY'` for the version). When `subtotal` is first
added, it backfills `subtotal` and `total_amount` from `order_items`; legacy orders had
no discounts or shipping. A rerun changes nothing. Tests cover a fresh database, a
pre-US16 database and a second run, and check that `orders.total_amount` equals the sum
of `seller_orders.total_amount` for every legacy order. The backfill never invents
voucher usage or shipping for old orders.

## 7. Consumption, concurrency and restoration

**Quote never consumes.** A test asserts that `used_count` and `voucher_usages` are
unchanged after any number of quotes.

**Consume inside checkout.** For each applied voucher, run a conditional update:

```sql
UPDATE vouchers SET used_count = used_count + 1
WHERE id = :id AND is_active = 1
  AND (usage_limit IS NULL OR used_count < usage_limit)
```

A rowcount other than 1 raises `ERR_VOUCHER_USAGE_LIMIT`. Then count the buyer's
`APPLIED` usages of that voucher in the same transaction and insert the usage row. The
count runs after the write, which is SQLite's single-writer serialization point. A
competing checkout either waits or gets BUSY, and the existing retry loop re-reads the
state on its next attempt. A per-user failure therefore rolls back the global increment
as well. Python locks or `SELECT ... FOR UPDATE` are not part of the design.

**Checkout failure.** Any failure, including stock or cart changes, rolls back stock,
counters, usages and the order together. No restore step is needed.

**Restoration (#128 wires it into cancellation).** Since PR #164, a seller order
reaches `CANCELLED`, and has its stock restored, through three code paths:

| Entry point | Who | When |
|---|---|---|
| `PATCH /api/v1/seller/orders/{subOrderId}/status` (`src/api/seller_orders.py`) | Owning seller | From `PENDING`, `CONFIRMED` or `PROCESSING`, or approving `CANCELLATION_REQUESTED` |
| `PATCH /api/v1/orders/{orderId}/status`, seller branch (`src/api/orders.py`) | Owning seller | The same transitions, applied to all of that seller's seller orders in the order |
| `PATCH /api/v1/orders/{orderId}/status` or `POST /api/v1/orders/{orderId}/cancel`, buyer branch (`src/api/orders.py`) | Owning buyer | Only while the parent order is `PENDING`; cancels every seller order |

Restoring a voucher belongs in one shared cancellation function that all three paths
call, which is the extraction #128 plans. It must not be copied into each route. Moving
to `CANCELLATION_REQUESTED`, or rejecting a request (back to `CONFIRMED` or
`PROCESSING`), restores nothing.

- A shop usage is restored when its seller order is cancelled.
- A platform or shipping usage is restored only when every seller order of the order
  with a non-zero `platform_discount` (or `shipping_discount`) is cancelled. Cancelling
  one shop does not return the whole platform usage.
- Restoring runs `UPDATE voucher_usages SET status = 'RESTORED', restored_at = :now
  WHERE id = :id AND status = 'APPLIED'` and decrements `used_count` only when that
  update affects 1 row. Retrying or cancelling through two routes restores once.
- A partial cancellation keeps the other seller orders' allocations and totals. It does
  not re-price them or re-check minimums.
- A return or refund after delivery does not restore usage (proposal; confirm in #133
  and #137).
- Restoring an expired voucher returns its usage count but does not extend its window.

## 8. Combo promotions (#137)

**Decision: deferred.** No team-approved combo-promotion rules are in scope for US16.
In particular, this contract intentionally does not define:

- eligibility (qualifying products, quantities, sellers or customer segments);
- a discount formula, cap or rounding rule; or
- stacking order or interaction with shop, platform or shipping vouchers.

Until a later decision records those rules in this section under a new policy version:

- the voucher model and pricing API accept no combo-promotion input;
- checkout does not infer or apply a combo discount; and
- no combo discount is shown, persisted, consumed or restored.

This is a scope boundary, not a default discount rule. #137 is complete when this
deferral is recorded; implementing combo promotions requires a follow-up contract and
tests before any production behavior is added.

## 9. Acceptance tests

| Story criterion | Required evidence | Task |
|---|---|---|
| Eligible voucher shows its discount before submission | Quote for each type and slot; quote leaves counters and usages unchanged; the checkout UI renders the server values | #135, #136 |
| Limit, expiry, inactive and other-shop vouchers are rejected without consuming | One test per code in section 3.2; global and per-user cap races with two independent connections on a file SQLite database | #133 |
| Per-shop discount and proportional platform allocation | Section 2.2 cases; `sum(D_platform_s) = D_platform` for random inputs | #135 |
| Seller-order and grand totals | Section 2.1 example end to end; the persisted totals equal the quote; the receipt reads persisted values | #135, #136 |
| Combo promotions remain out of scope | Section 8 records the deferred decision and confirms there is no combo input or automatic discount | #137 |
| Rollback and restore keep usage consistent | Failure injected after consumption leaves no usage rows and unchanged counters; one restore per cancellation through each entry point in section 7, including approval of a cancellation request; no restore on request or rejection; platform restore only after every allocated seller order is cancelled; replay never consumes twice | #133, #128 |
| Seller receipt scope | A seller reading a two-shop order sees only their own items and breakdown | #136 |
| Compatibility | Legacy hash test unchanged; key reuse with other vouchers conflicts; migration fresh, legacy and rerun | #133, #136 |
| Seller management scope | Seller A cannot read or edit seller B's voucher; `scope` and `seller_id` in the body are rejected | #134 |

## 10. Decisions to confirm

| Decision | Proposal | Confirm in |
|---|---|---|
| Shipping fee | Confirmed by #135 calculator: flat 20.000 ₫ per seller order, policy `US16-V1`; activation belongs to #136 | #135 |
| Free shipping | #135 calculation uses a separate platform-funded slot with a per-seller-order cap; eligibility remains in #133 | #133, #135 |
| Restore after return or refund | No restore | #133, #137 |
| Combo promotions | Deferred | #137 |
| Legacy checkout without a quote | Accepted until #136 merges, then rejected after replay | #136 |
| Platform voucher management | Seed only this sprint; admin UI in #151 | #151 |
