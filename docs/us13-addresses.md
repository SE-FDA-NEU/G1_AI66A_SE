# US13 â€” Address book and delivery snapshots

Implementation for #105 and tasks #122, #123, #124, #125, rebased onto `main` at
`1d809f0bcb0b3fecf38568dc249f76196e23fcf4` (includes the US15 reviews and
notifications from PR #166). PR #164 was checked through GitHub and remained
open/unmerged during implementation; its order tracking work is not included. There is no invented PR link or claim of external review/issue closure.

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
Phone permits only ASCII digits and `+ ()-`, and must contain 7â€“15 digits. Separators
are preserved, while outer and repeated ASCII spaces are normalized before storage;
the digit sequence is never changed. `is_default` is a strict boolean; body IDs and versions are strict
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

## UserAddress field specification

The `user_addresses` table stores buyer-owned delivery addresses. `user_id` is
derived from the authenticated buyer and is never accepted from request bodies or
returned in the public response.

| Field | Type | Required | Constraints and default |
|---|---|---:|---|
| `id` | integer | response only | Positive primary key; SQLite autoincrement prevents ID reuse |
| `user_id` | integer | server-managed | Foreign key to `users.id`; every read/write is owner-scoped |
| `recipient_name` | string | create/update | Trimmed visible text; 1â€“100 characters |
| `phone_number` | string | create/update | 7â€“20 characters, 7â€“15 ASCII digits, separators limited to `+`, spaces, `(`, `)` and `-`; outer/repeated spaces normalized |
| `province` | string | create/update | Trimmed visible text; 1â€“100 characters |
| `district` | string | create/update | Trimmed visible text; 1â€“100 characters |
| `ward` | string | create/update | Trimmed visible text; 1â€“100 characters |
| `detailed_address` | string | create/update | Trimmed visible text; 1â€“500 characters |
| `is_default` | boolean | optional | Strict boolean; defaults to `false`; the first address is forced to `true` |
| `version` | integer | response; update/default request | Positive integer starting at `1`; increments on successful mutation |
| `created_at` | datetime | response only | Server-generated UTC timestamp |
| `updated_at` | datetime | response only | Server-generated UTC timestamp, updated on mutation |

`AddressCreate` and `AddressUpdate` reject unknown fields. `AddressUpdate` and
`AddressDefault` require a strict positive `version`. The database partial unique
index `ux_user_addresses_one_default` permits at most one default address per
buyer.

## Address API examples

All examples use `/api/v1/addresses` and require
`Authorization: Bearer <buyer-token>`.

### Create

```http
POST /api/v1/addresses
Authorization: Bearer <buyer-token>
Content-Type: application/json
```

```json
{
  "recipient_name": "Nguyen Minh",
  "phone_number": "0912345678",
  "province": "Ha Noi",
  "district": "Dong Da",
  "ward": "Lang Thuong",
  "detailed_address": "12 Pho Chua Lang",
  "is_default": true
}
```

Response: `201 Created`.

```json
{
  "data": {
    "id": 12,
    "recipient_name": "Nguyen Minh",
    "phone_number": "0912345678",
    "province": "Ha Noi",
    "district": "Dong Da",
    "ward": "Lang Thuong",
    "detailed_address": "12 Pho Chua Lang",
    "is_default": true,
    "version": 1,
    "created_at": "2026-10-28T15:00:00Z",
    "updated_at": "2026-10-28T15:00:00Z"
  }
}
```

When this is the buyer's first address, `is_default` is `true` even if the
request omits it or sends `false`.

### List

```http
GET /api/v1/addresses
Authorization: Bearer <buyer-token>
```

```json
{
  "data": [
    {
      "id": 12,
      "recipient_name": "Nguyen Minh",
      "phone_number": "0912345678",
      "province": "Ha Noi",
      "district": "Dong Da",
      "ward": "Lang Thuong",
      "detailed_address": "12 Pho Chua Lang",
      "is_default": true,
      "version": 1,
      "created_at": "2026-10-28T15:00:00Z",
      "updated_at": "2026-10-28T15:00:00Z"
    }
  ]
}
```

The default address is returned first, followed by other addresses in ascending
`id` order. Addresses belonging to other buyers are not included.

### Full update with optimistic version checking

```http
PUT /api/v1/addresses/12
Authorization: Bearer <buyer-token>
Content-Type: application/json
```

```json
{
  "recipient_name": "Nguyen Minh",
  "phone_number": "0912345678",
  "province": "Ha Noi",
  "district": "Dong Da",
  "ward": "Lang Thuong",
  "detailed_address": "14 Pho Chua Lang",
  "is_default": false,
  "version": 1
}
```

The response is `200 OK` and contains `version: 2`. A stale version returns
`409 Conflict` without changing the address:

```json
{
  "error": {
    "code": "ERR_ADDRESS_CHANGED",
    "message": "Address changed. Review it before continuing."
  }
}
```

### Set default

```http
PATCH /api/v1/addresses/12/default
Authorization: Bearer <buyer-token>
Content-Type: application/json
```

```json
{
  "version": 2
}
```

The response is `200 OK`. The operation atomically clears the previous default,
increments the affected versions, and increments the selected address version.
A stale version returns the same `409 ERR_ADDRESS_CHANGED` response.

### Delete

```http
DELETE /api/v1/addresses/12
Authorization: Bearer <buyer-token>
```

The response is `204 No Content` with an empty body. An unknown or foreign ID
returns `404 Not Found`:

```json
{
  "error": {
    "code": "ERR_ADDRESS_NOT_FOUND",
    "message": "Address not found. Reload your address book."
  }
}
```

Invalid phone values, missing fields, wrong strict types, and extra fields return
`422 ERR_VALIDATION`. For example:

```json
{
  "error": {
    "code": "ERR_VALIDATION",
    "message": "Please correct the highlighted fields.",
    "fields": {
      "phone_number": [
        "Phone number must contain 7 to 15 digits; use only +, spaces, (), or - as separators."
      ]
    }
  }
}
```

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

## Task #123 follow-up — address UI only

The address book and checkout selector already exist from PR #167. This follow-up
changes only their frontend behavior, UI tests and this documentation. Address APIs,
ownership/version rules, database migrations and order snapshots are unchanged.

- Address cards and their Edit/Delete/Set default actions have distinct accessible
  names identifying the recipient and street. Stable action IDs allow focus to
  return after the cards are refreshed.
- Delete confirmation shows the exact recipient, phone and full address as plain
  text. Cancel receives initial focus, sends no DELETE, clears the confirmation
  details and returns focus to the initiating Delete button. A failed deletion
  retains the target and confirmation for review/retry. Opening an address form or
  starting any address-list refresh invalidates that confirmation, including when
  the refresh fails. Updated address details require a fresh Delete confirmation;
  stale Confirm events send no DELETE and do not announce a successful deletion.
- Cancelling an edit returns to its Edit button. Successful edits return to the
  refreshed Edit button; adding, deleting or setting a default returns to the
  checkout address selector. These actions preserve the user's current delivery
  selection where that address still exists.
- The existing live address status announces saves and successful changes. Its
  `tabindex="-1"` also lets failed card actions focus their visible error feedback.
  Field-level validation continues to preserve entered values and focus the first
  invalid input. Pending mutations disable address controls and refuse duplicates.
  Every failed mutation replaces the saving status with error guidance, whether
  the editor is open or closed. Cancelling after a rejected save cannot leave an
  indefinite progress message.

Run `node tests/addresses_ui.mjs` and `node tests/checkout_ui.mjs` to verify these
behaviors alongside saved/manual checkout selection, account isolation and pending
checkout protection. Review regressions also cover Delete → Edit → Save → stale
Confirm, refresh success/failure, fresh confirmation of updated details, and 422/
network errors followed by cancellation. A native Chromium spot check using disposable API fixtures
also confirmed edit/default/delete focus, targeted delete confirmation and no
horizontal overflow at 360/768/1280px. This spot check does not replace the existing
SQLite persistence tests or claim real-user validation.

## Acceptance evidence — 27 October 2026

| Acceptance criterion | Automated evidence | Browser evidence |
|---|---|---|
| Persistent CRUD and account isolation | `test_crud_defaults_and_persistence`, `test_ownership_auth_and_stale_version_do_not_clear_defaults`, `test_write_predicates_are_owner_scoped` | A creates/edits/deletes; B sees only B; B creates with empty cart |
| One default, available at checkout | `test_constraint_no_id_reuse_and_init_upgrade`, `test_concurrent_default_operations_keep_one_default`, `test_concurrent_first_addresses_keep_one_default`, `test_default_failure_rolls_back_clear` | Switch default, reload, automatic preselection, buy using non-default |
| Immutable snapshots and replay | `test_snapshot_edit_delete_replay_and_new_order`, `test_saved_checkout_concurrent_same_key`, `test_legacy_hash_stays_compatible`, `test_saved_checkout_selected_only_and_stock_rollback` | Buy â†’ edit/delete source â†’ unchanged receipt; abort response after commit â†’ delete source â†’ reload/retry returns same order |
| Actionable field errors | `test_address_validation`, `test_malformed_json_and_missing_fields_have_safe_guidance`, `test_checkout_address_validation`; `addresses_ui.mjs` | Invalid phone displays allowed digit/separator guidance, focuses input; no horizontal overflow at 360px |

Screenshots from the real app on a disposable database:

- [Mobile address book](images/us13/mobile-address-book.png)
- [Mobile field error and keyboard focus](images/us13/mobile-field-error.png)
- [Receipt after editing/deleting its source](images/us13/snapshot-after-delete.png)
- [Replay after response loss and source deletion](images/us13/replay-after-source-delete.png)

Final verification on 27 October 2026, after rebasing onto `main` at `1d809f0`:
**490 pytest tests passed** (including 49 US13 tests), Ruff passed, all six Node
scripts passed, and the Chromium acceptance run passed and regenerated the screenshots. The repeatable browser run also verifies initialization twice and retry
after a committed response is lost and its source address is deleted.

The focused address verification was run with the following exact PowerShell
command:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_addresses.py
```

The observed output was:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\G1_AI66A_SE
configfile: pyproject.toml
collected 32 items

tests\test_addresses.py ................................                 [100%]

============================== 32 passed, 1 warning in 9.62s ==================
```

The warning is a Starlette deprecation warning about using `httpx` with
`starlette.testclient`; it did not fail any test.

Run the automated checks with the repository virtual environment:

```bash
DEBUG=false .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
node tests/cart_ui.mjs
node tests/checkout_ui.mjs
node tests/addresses_ui.mjs
node tests/seller_products_ui.mjs
node tests/seller_orders_ui.mjs
node tests/product_detail_ui.mjs
```

Optional real-browser evidence run: with `.venv` activated, install Playwright and
Chromium into it (`python -m pip install playwright`, then
`python -m playwright install chromium`) and run `python tests/browser_us13.py` from the
repository root. The command is the same in PowerShell, Command Prompt and bash. The
script starts every child process with the interpreter that runs it, runs `init_db`
twice, seeds only a temporary SQLite file, writes the server log to `us13-server.log`
in the system temporary directory, starts a local server on port 8135, exercises both
buyers, saves the screenshots above and stops the server.
The normal pytest/CI suite does not require Playwright.

Baseline repairs: checkout UI fixtures now include US12 selection data; the seller UI
catalog fixture handles its categories/sellers requests separately. Pre-existing Ruff
violations (unused imports, import order, long lines) were corrected without changing
product behavior. The shell's inherited `DEBUG=release` is not a boolean, so verification
uses `DEBUG=false`. TestClient requires execution outside this session's restricted
sandbox; the test application uses disposable databases.

External PR review, merge and issue closure remain repository workflow steps. The local
implementation and verification do not claim that another person has reviewed the work.

## Task #122 Implementation & Verification Summary

- **Target Issue:** [#122 [Task] Add address data model and API](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/122) (Parent Story: #105)
- **Data Model:** `UserAddress` mapped to table `user_addresses`:
  - Enforced version check (`ck_address_version: version >= 1`).
  - Partial unique index `ux_user_addresses_one_default` preventing multiple active defaults per buyer account.
  - SQLite autoincrement enabled ensuring deleted address primary keys are never recycled.
- **REST APIs (`/api/v1/addresses`):**
  - Authenticated buyer protection (`BuyerUser`). Returns `401 Unauthorized` for anonymous guests and `403 Forbidden` for sellers.
  - Endpoints: `GET /` (list ordered by default-first then ID), `POST /` (create with automatic first-address default assignment), `PUT /{id}` (full replacement with optimistic version check), `PATCH /{id}/default` (switch default with automatic clearing and version increments), `DELETE /{id}` (owner-scoped atomic deletion).
- **Error Codes & Security:**
  - `ERR_ADDRESS_NOT_FOUND` (404) for foreign or non-existent IDs.
  - `ERR_ADDRESS_CHANGED` (409) for stale version updates.
  - `ERR_CONCURRENCY_CONFLICT` (409) with 5-attempt retry backoff on database lock/collision.
- **Automated Verification:**
  - `tests/test_addresses.py`: 32 test cases passed covering CRUD lifecycle, ownership isolation, phone number / visible text validators, concurrent default switching, and database rollback safety.
