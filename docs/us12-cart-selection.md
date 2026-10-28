# US12: Select Items and Shops for Partial Checkout (#104)

## Scope

This change implements all four acceptance criteria of story #104: persisted
selection and price-at-add, grouped cart UI, selected-only checkout, and regression
coverage. It includes the work described by tasks #118-#121, following the author's
explicit request to complete the whole story. Earlier frontend-only #119 scope
notes are superseded. Other stories (addresses, variants, shipping discounts,
vouchers, order snapshots and shared restyling) are not included.

## Runtime contract

GET and successful cart mutations return `{ "data": cart }`, including all cart
rows. Existing fields and product-code quantity/remove URLs are retained.

| Field | Meaning |
| --- | --- |
| `items[].cart_item_id` | Cart row ID, distinct from product code |
| `items[].seller_id`, `seller_name` | Seller grouping ID and display name |
| `items[].is_selected` | Persisted selection, false for unavailable rows |
| `items[].price_at_add` | Unit price when the row was first added, integer VND |
| `items[].price_changed` | Whether current unit price differs from price-at-add |
| `cart_total` | Sum of all current line totals, including unselected rows |
| `selected_total` | Sum of selected available rows at current prices |
| `supports_partial_checkout` | True: this server supports selected-only checkout |

| Method / URL | Input | Success / errors |
| --- | --- | --- |
| `PATCH /api/v1/cart/items/{item_id}/select` | Strict JSON boolean `is_selected` | Updated cart; 404 for missing/another buyer's row, 409 if selecting unavailable quantity |
| `PATCH /api/v1/cart/select-shop/{seller_id}` | Same boolean | One atomic shop change, skipping unavailable rows; 404 if this buyer has no rows in that shop |
| `POST /api/v1/orders` | Existing delivery fields and `Idempotency-Key` | 201 selected order, 200 idempotent replay; 400 empty/no selection, 409 stock/cart conflict |

All endpoints enforce buyer authentication/ownership. Invalid selection types or
extra body fields return 422. Existing common error codes/envelope remain.
A shop change touches only that buyer's rows, never another buyer's shop selection.
Selection updates match ID, owner, product and quantity, retaining the row-count
conflict check to protect against reused SQLite row IDs.

## Persistence and checkout

- New rows default to selected and capture the current product price. Increasing
  quantity or adding the same product again preserves the initial price baseline
  and the buyer's selection. Removal and re-addition create a new baseline.
- Cart refresh keeps unavailable rows and quantities but persists their deselection.
  Replenishing stock does not silently select them again. Refresh is an idempotent
  reconciliation of availability, not a stock reservation. Both reads that reconcile
  and explicit mutations commit/rollback inside CartService.
- `python -m src.database` applies repeatable migrations for existing databases.
  Existing rows default to selected; legacy `price_at_add` is backfilled from the
  price available at migration, since the original historical price was not stored.
  Later migrations never overwrite that baseline. Imported rows with a null
  baseline initialize it on first cart refresh. New seed cart rows capture it directly.
- Checkout reads only selected rows. Validation, stock/version updates, parent and
  seller orders, order items and selected-row deletion share one transaction.
  Rows are deleted before commit inside that transaction, so they disappear only
  when the order commits. A failure rolls back stock, orders and cart deletion.
  Unselected rows remain unchanged, including unavailable rows.
- The selected-line delete checks row ID, buyer, product, variant, quantity and
  selection. A concurrent deselection/quantity change conflicts and rolls back. The
  variant check (#120) matters because SQLite reuses a freed row ID. Another request
  can remove the ordered line and add a different variant of the same product
  between checkout reading the cart and deleting the line. Without that check,
  checkout would order the old variant and delete the new line. Existing
  optimistic stock checks and cross-buyer ID-reuse protection remain.
- Committed idempotent replay returns the same order before reading the remaining
  cart. It cannot accidentally order newly selected leftover rows on retry.

## Interface

Items are grouped by seller ID. Each shop shows its available subtotal and selected
subtotal. Native labeled checkboxes support item/shop selection and mixed shop
state. Non-available rows are separated, unchecked and disabled, while quantity
and remove controls remain usable. Both increases and decreases disclose old and
current unit prices. The checkout summary contains only selected items and also
shows changed prices.

The UI locks while saving, uses only the confirmed server snapshot, restores failed
selection/total changes with a visible error, and restores keyboard focus. No
selection disables checkout. Authentication changes invalidate the displayed
account context. Server text is rendered with `textContent`. Existing four states
and responsive cart layout/shared tokens remain.

### Task #119 follow-up

The grouped selection implementation already exists on `main`. This follow-up
keeps its API contract and shared styling, gives shop/unavailable groups accessible
heading associations, and includes variant names in item selection, quantity and
removal labels. Unavailable selection controls are disabled as they are created.
Selection saves announce progress through the existing live status region.

Native browsers move focus away when a checkbox is disabled. The selection handler
now captures the initiating control before locking it and restores that control
after an unsuccessful save. Both the mixed shop state and confirmed selected total
are restored. DOM-double tests simulate native focus loss rather than retaining
focus on a disabled control.

The legacy-response path remains for compatibility with older deployments; the
current server always sends selection metadata and enables the selected checkout
capability. Incomplete new metadata never falls back to whole-cart checkout.

## Acceptance and regression checks

| #104 criterion | Automated evidence |
| --- | --- |
| Seller grouping, per-shop subtotal/control | `tests/cart_ui.mjs`; `test_selection_and_shop_metadata_survive_reload` |
| Item/shop changes persist and update selected total | Same API test and item/shop/failure cases in `cart_ui.mjs` |
| Unavailable rows deselect; price changes disclosed | `test_unavailable_rows_deselected_and_not_reselected_on_restock`, `test_price_at_add_is_immutable_across_price_and_quantity_changes`; cart/checkout script checks |
| Only selected order rows created/removed | `test_mixed_shop_checkout_preserves_unselected_rows_and_idempotent_replay`, `test_failed_selected_checkout_rolls_back_every_selected_row` |
| Only the selected variant is ordered; other variant rows stay (#120) | `test_selected_variant_is_ordered_and_other_variant_rows_survive`, `test_cart_id_reused_for_another_variant_during_checkout_is_a_conflict` |

`tests/test_us12.py` also covers strict inputs, ownership, empty selection,
concurrent deselection, reused row IDs and repeatable legacy migration. The US04
concurrency/rollback suite remains in `tests/test_checkout.py`. UI tests execute
the real scripts with DOM/network doubles; API tests use real SQLite files and
independent sessions. These are automated checks, not real user-test evidence.

```text
python -m src.database
python -m pytest -q
python -m ruff check .
node tests/cart_ui.mjs
node tests/cart_selection_browser.mjs
node tests/checkout_ui.mjs
node tests/seller_products_ui.mjs
node tests/seller_orders_ui.mjs
```

For a manual browser check, follow [SETUP](SETUP.md), start the server and log in
as a buyer. Add available products from two sellers, open `/cart`, deselect one
item and reload to check persistence. Select a shop and verify its mixed/checked
state and subtotals; open checkout and confirm only selected items appear. Place
the order, then return to the cart: unselected items must remain. For warning
screens, change a product's price or stock as its seller and reload the buyer cart.
Check widths 390/768/1280px and keyboard selection/focus. Automated browser evidence
is available at [390px](images/us12/cart-selection-390.png),
[768px](images/us12/cart-selection-768.png), and
[1280px](images/us12/cart-selection-1280.png). Real-user validation remains pending.

`node tests/cart_selection_browser.mjs` requires Node 22+ and Chrome/Edge (Windows
paths are detected; other installations can set `BROWSER_PATH`). It starts an
isolated local HTTP server serving the real cart HTML/CSS/JavaScript and deterministic
API fixtures, then uses a temporary headless browser profile. It verifies three
shop groups, mixed/disabled selection, variant labels, price warnings, viewport
overflow, item/shop changes, failed-save focus recovery, and selection across reload.
It rewrites the three screenshots. These fixture screenshots demonstrate rendering
and browser interaction, not backend persistence or real-user testing; the SQLite
API tests above verify persistence, ownership and selected-only checkout separately.

## Design rationale and AI assistance

The supplied course material informed small named functions, explicit contracts,
presentation/service separation, four UI states, clear error recovery and
risk-based tests around totals/ownership/rollback. Codex helped draft and verify
the code, tests and documentation; the author remains responsible for human review
and explaining the implementation. No real-user results are fabricated.
