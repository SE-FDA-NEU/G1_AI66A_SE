# US17: buyer return-request UI (#139)

Parent story: #109. The return model, buyer/seller authorization, endpoints and
refund/restock workflow already exist. Task #139 completes the buyer interface on
`/orders/{id}` and its existing `/order/{id}` alias, including mixed-seller orders.
It does not change the backend rules, payment/refund implementation, seller/admin
decision controls, inventory restoration or database migrations.

## Contract and eligibility

- The existing order receipt supplies `sub_orders` and item snapshots. Only a
  seller order with status `DELIVERED` and no `PENDING` return request is offered.
  The parent order need not be `DELIVERED`: another shop may still be shipping.
  Confirming receipt ends eligibility under the current backend workflow.
- The buyer controller checks `/api/v1/auth/me` and loads
  `GET /api/v1/orders/{id}/returns` before enabling its action. The server remains
  authoritative for identity, ownership, eligibility and duplicate protection.
  A failed read disables submission and offers **Retry return status** rather
  than assuming there are no existing requests.
- **Request return or refund** opens a labelled form. Its selector names the
  eligible shop order and product snapshots. Submission always includes an
  explicit integer `seller_order_id`, even in a single-shop order.
- `POST /api/v1/orders/{id}/returns` receives `{seller_order_id, reason, evidence}`.
  Trimmed reason must contain 3–500 characters and evidence 3–2000 characters,
  matching `CreateReturnRequest`. Evidence is explanatory text, serial numbers or
  URL references. This UI does not upload files or render evidence as HTML/media.
- Client validation associates errors with controls through `aria-describedby`
  and `aria-invalid`, then focuses the first invalid field. A server 422 shows a
  form error and any supported `error.fields` messages. Controls are unlocked
  before focusing a server-invalid field; generic 422 responses still give
  actionable guidance. Failed submissions retain drafts, scoped to each shop.

## Loading, feedback and request history

`buyer-returns.js` owns the buyer form and history presentation. The existing
`order.js` delegates the buyer slice to it while retaining seller/admin decisions.
The controller exposes `update`, `hide` and `reset`; its parent refresh callback
updates the receipt without replacing the persistent return confirmation.

- Reads show a loading status. A successful empty read shows why no shop is
  eligible, or offers the return action. Error states have a separate Retry
  control; they never leave a permanent saving/loading message.
- A pending POST locks form controls, Confirm Receipt and the order switcher.
  Repeated clicks cannot send another POST. On HTTP 201, the returned request is
  shown immediately and its shop is removed from the eligible choices. The live
  confirmation names the request and states that escrow release is paused.
- Every request has its own card: request/shop identifiers, current status,
  reason, evidence, submitted time, server payment/escrow/order status, and review
  notes/time when present. `PENDING`, `APPROVED` and `REJECTED` use text, not color
  alone. Naive timestamps from the current SQLite DTO are interpreted as UTC,
  consistent with the server's UTC writer, then displayed in the viewer's locale.
- Return API calls have a 15-second bound. A timeout/network failure, conflict or
  uncertain POST outcome disables another submission. Explicit Retry reads the
  receipt and existing requests first; it never automatically repeats the POST.
  If a pending request is recorded, its actual status replaces the uncertain
  message. Pending-request uniqueness and atomic transitions stay on the server.
- Switching order/account clears the old form/history and invalidates late
  responses. Same-order refreshes retain drafts and selection. A 401 clears both
  supported token keys and redirects to login with a return URL. A previously
  authorized in-flight write may finish on the server; clearing UI state does not
  claim to cancel or roll back that write.

## Verification and screenshots

The single test matrix and commands are in
[testing.md](testing.md#task-139-buyer-return-request-ui). Native browser checks
serve production HTML/CSS/JavaScript with deterministic API fixtures. They verify
layout and interactions; persistence, permissions and refund effects are checked
separately by the existing Python return tests. They are not independent human
review, five-user validation, CI results or a clean-clone run.

The mobile tracker header and status badges wrap so they do not push the return
page sideways. New form styles retain the page's design, visible keyboard focus,
readable text and controls of at least 44px in height.

Screenshots: [phone form](images/us17/return-form-390.png),
[tablet](images/us17/return-form-768.png),
[desktop](images/us17/return-form-1280.png),
[validation](images/us17/return-validation-390.png),
[submitted request](images/us17/return-submitted-390.png).

### Live-backend reproduction

For an end-to-end check, choose a new SQLite file through `DATABASE_URL`, then
initialize/seed/start as documented in README. With the seeded buyer, buy `P-100`;
with its seller, confirm, ship and deliver that shop order. Return to the buyer's
order page and submit a reason and evidence. The UI must show one saved `PENDING`
request, seller-order status `RETURN_REQUESTED` and escrow `PAUSED`, also available
from `GET /api/v1/orders/{id}/returns`.

The [live-backend phone screenshot](images/us17/return-live-390.png) records this
flow using an isolated demo database and real API responses, separately from the
fixture-driven browser suite. It is not a clean-clone or independent human run.
