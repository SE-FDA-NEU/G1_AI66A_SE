# US13 — Address book and delivery snapshots

Implementation for #105 and tasks #122, #123, #124, #125, based on local
`main` at `526803cdef0d2dd7db70342b9e68c0dcbe676067`. PR #164 was checked through
GitHub and remained open/unmerged during implementation; its order tracking work
is not included. There is no invented PR link or claim of external review/issue closure.

## Buyer API contract

All paths below start with `/api/v1/addresses`. A bearer token for a buyer is required;
a guest receives 401 and a seller receives 403. User identity always comes from auth.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | (root) | none | 200 `{data:[address,...]}`, default first then ascending ID |
| POST | (root) | six fields and optional `is_default` | 201 `{data:address}` |
| PUT | `/{id}` | six fields, `is_default`, current `version` | 200 `{data:address}` |
| PATCH | `/{id}/default` | `{version:1}` | 200 `{data:address}` |
| DELETE | `/{id}` | none | 204, empty body |

The six required fields are `recipient_name`, `phone_number`, `province`, `district`,
`ward`, `detailed_address`. Text is trimmed, must contain visible characters, and has
limits 100 for names/administrative fields, 500 for detailed_address and 20 for phone.
Phone permits only ASCII digits and `+ ()-`, and must contain 7–15 digits. Separators
are preserved. `is_default` is a strict boolean; body IDs and versions are strict
positive integers. Requests forbid extra fields, including server-owned fields.
Responses also contain `id`, `version`, `created_at`, `updated_at`; they exclude user_id.
PUT replaces editable fields; omitting is_default means false, as on create.

The first address becomes default. Later addresses do so only when requested. Clearing
or deleting a default may leave no default. Switching defaults increments the versions
of both the target and any cleared address. Changes commit once, with ownership in
SELECT/UPDATE/DELETE and optimistic versions in updates. Invalid ownership/version
cannot clear an existing default. A partial unique database index enforces at most one
default per buyer. SQLite BUSY/LOCKED and default-index conflicts retry at most five
attempts, reading state again after rollback. Other database errors propagate to the
safe database-failure envelope. Deleted SQLite IDs are never reused.

Unknown and foreign IDs both return 404 `ERR_ADDRESS_NOT_FOUND`. Stale versions return
409 `ERR_ADDRESS_CHANGED`; exhausted contention returns 409 `ERR_CONCURRENCY_CONFLICT`.
Validation returns 422 `ERR_VALIDATION` plus `error.fields`; shape/mixed/extra-field
errors use `_form`. Raw input and union model names are excluded. Database failures
return 500 `ERR_DATABASE_FAILURE` without SQL. Seller-product validation is unchanged.

## Checkout and retry

POST `/api/v1/orders` accepts exactly one body shape:

```json
{"recipient_name":"Buyer","delivery_address":"123 Main Street","phone_number":"0912345678"}
```

```json
{"address_id":12,"address_version":3}
```

The normalized request is hashed using the previous serialization; the legacy field
order and phone formatting remain unchanged. On every checkout attempt, replay is
checked before resolving an address. The saved mode hashes only ID/version. Reusing
an Idempotency-Key for another buyer/body/mode returns `ERR_IDEMPOTENCY_CONFLICT`.

For a new order, the buyer-owned record and its version are checked, then name/phone
and `detailed_address, ward, district, province` are copied into the existing three
Order fields. Address lookup does not commit/rollback independently. The checkout
transaction still owns stock updates, seller orders, order items and deletion of only
the selected cart rows. Failure rolls everything back. Receipts read Order directly:
editing/deleting addresses never changes history. A successful request can be replayed
after its source changes/disappears; an uncommitted request cannot use a deleted source.

## Browser behavior

The address book is on `/checkout`, outside the order form; it remains available for
an empty cart or a failed cart load. Initial selection is the default, otherwise the
smallest ID. An explicit manual option retains the old delivery form. Choosing an
address for one order never changes the default. Address and checkout forms are siblings.

CRUD uses textContent for user data. Required fields show `*` and instructions; inline
errors use aria-invalid/aria-describedby and focus the first invalid input after
unlocking it. Deletion offers Cancel before any DELETE. Failed mutations preserve
cards/input. Layout and keyboard focus were checked in Chromium at 360px width.

Before POST, checkout saves the exact body/key in sessionStorage scoped by user ID.
Pending requests freeze selection and address actions. Both old manual pending bodies
and saved ID/version bodies restore without loading the address book first. Uncertain
network/server failures keep the pending request for retry. A definite 4xx rejection
clears it; stale/missing addresses refresh the book and require explicit selection
review. Auth context is checked before requests and after responses; account changes
hide/clear old address data and block submit/retry/CRUD. Cross-tab token changes also
invalidate the view.

## Acceptance evidence — 25 October 2026

| Acceptance criterion | Automated evidence | Browser evidence |
|---|---|---|
| Persistent CRUD and account isolation | `test_crud_defaults_and_persistence`, `test_ownership_auth_and_stale_version_do_not_clear_defaults`, `test_write_predicates_are_owner_scoped` | A creates/edits/deletes; B sees only B; B creates with empty cart |
| One default, available at checkout | `test_constraint_no_id_reuse_and_init_upgrade`, `test_concurrent_default_operations_keep_one_default`, `test_concurrent_first_addresses_keep_one_default`, `test_default_failure_rolls_back_clear` | Switch default, reload, automatic preselection, buy using non-default |
| Immutable snapshots and replay | `test_snapshot_edit_delete_replay_and_new_order`, `test_saved_checkout_concurrent_same_key`, `test_legacy_hash_stays_compatible`, `test_saved_checkout_selected_only_and_stock_rollback` | Buy → edit/delete source → unchanged receipt; abort response after commit → delete source → reload/retry returns same order |
| Actionable field errors | `test_address_validation`, `test_malformed_json_and_missing_fields_have_safe_guidance`, `test_checkout_address_validation`; `addresses_ui.mjs` | Invalid phone displays allowed digit/separator guidance, focuses input; no horizontal overflow at 360px |

Screenshots from the real app on a disposable database:

- [Mobile address book](images/us13/mobile-address-book.png)
- [Mobile field error and keyboard focus](images/us13/mobile-field-error.png)
- [Receipt after editing/deleting its source](images/us13/snapshot-after-delete.png)
- [Replay after response loss and source deletion](images/us13/replay-after-source-delete.png)

Final verification on 25 October 2026: **476 pytest tests passed** (including 49
US13 tests), Ruff passed, all five Node scripts passed, and the Chromium acceptance
run passed. The repeatable browser run also verifies initialization twice and retry
after a committed response is lost and its source address is deleted.

Run the automated checks with the repository virtual environment:

```bash
DEBUG=false .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
node tests/cart_ui.mjs
node tests/checkout_ui.mjs
node tests/addresses_ui.mjs
node tests/seller_products_ui.mjs
node tests/seller_orders_ui.mjs
```

Optional real-browser evidence run: install Playwright in the Python environment used
for this command and Chromium (`python -m playwright install chromium`), then run
`python tests/browser_us13.py`. It uses application dependencies from `.venv`, runs
`init_db` twice, seeds only a temporary SQLite file, starts a local server on port
8135, exercises both buyers, saves the screenshots above and stops the server.
The normal pytest/CI suite does not require Playwright.

Baseline repairs: checkout UI fixtures now include US12 selection data; the seller UI
catalog fixture handles its categories/sellers requests separately. Pre-existing Ruff
violations (unused imports, import order, long lines) were corrected without changing
product behavior. The shell's inherited `DEBUG=release` is not a boolean, so verification
uses `DEBUG=false`. TestClient requires execution outside this session's restricted
sandbox; the test application uses disposable databases.

External PR review, merge and issue closure remain repository workflow steps. The local
implementation and verification do not claim that another person has reviewed the work.
