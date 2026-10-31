# US21 admin catalog and voucher UI (#152)

## Scope and existing implementation

The platform portal already existed from #113/PR #173. Task #152 completes the
catalog moderation, category management and platform voucher screens at `/admin`
and `/admin/portal`. It reuses the existing server APIs and administrator guard;
backend audit and adjudication improvements are tracked separately in
[#151](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/151). This UI branch works
with the APIs already present on main and does not require the #151 branch.

Account/dispute screen business rules, new voucher policies, category deletion
policy changes, payment providers and story-wide route registration (#153) are
outside this UI slice. There are no new runtime dependencies or setup steps.

## Supported interactions

| Screen | Interaction | Existing API |
|---|---|---|
| Catalog | Search/filter products and confirm deactivation/reactivation of the named product | `GET /api/v1/admin/products`, `PATCH /api/v1/admin/products/{id}/status` |
| Categories | Add/edit name, slug and parent; confirm deletion with its reparenting/unlinking effects | `GET/POST /api/v1/admin/categories`, `PUT/DELETE /api/v1/admin/categories/{id}` |
| Platform vouchers | Create percentage, fixed-amount or free-shipping vouchers; confirm activation/deactivation of the named code | `GET/POST /api/v1/admin/vouchers`, `PATCH /api/v1/admin/vouchers/{id}` |

Category DELETE retains the legacy API's hard-delete behavior: direct children
move to the deleted category's parent and product category links are removed.
The confirmation identifies the category and describes those effects. This task
does not silently switch that API to the canonical soft-deactivation policy.

Voucher creation confirms the active code, discount and exact UTC validity period
before submitting. The API derives platform scope; the browser does not accept a
seller scope or owner. The form supports the existing limits and caps without
changing pricing calculations. Percentage values retain the existing basis-point
input convention, labelled with its percentage equivalent.

## Validation, recovery and accessibility

Category names/slugs are trimmed. Required fields, length limits and the existing
lowercase slug syntax are checked before mutation. Voucher numeric fields require
whole values with their existing positive/nonnegative bounds. Percentage values
are 1-10,000 basis points; fixed discounts can be as small as 1 VND. A free-shipping
voucher disables the hidden discount-value input and sends zero, so an invisible
required field cannot prevent submission.
The cap is enabled only for percentage/free-shipping vouchers. Fixed-amount
creation sends no cap, matching the existing database constraint. The clearer
server-side rejection of invalid direct requests is covered separately by #151.

Start/end controls are explicitly UTC. Defaults, parsing, submitted timestamps
and displayed validity periods all use UTC independently of the browser timezone.
End must be strictly after start. The server remains authoritative for validation,
authorization, uniqueness and state changes.

Catalog/category/voucher lists provide loading, data, empty and error states with
Retry. Sequence guards discard an older filter response. Mutation controls are
locked while saving; repeated clicks/submit events cannot start another request.
Success is announced after the mutation response confirms it. Read failures after
a confirmed write retain a Retry state rather than inviting another write.

Native validation focuses invalid fields. API/network errors retain form input
and display actionable text inside the still-open dialog; controls are restored
and the error receives focus. Uncertain failures ask the administrator to inspect
current data before retrying. Status/error regions use live semantics and do not
disappear on a timer. Dialog saving progress has its own status region.

Dialogs have an accessible name, modal semantics and initial focus. Tab stays in
the dialog; Escape/Cancel restore the opener, and dismissal is blocked while a
mutation is pending. Background controls are inert. Focus outlines, text status
labels, stronger button contrast and 44px buttons support keyboard/touch use.
Mobile layouts stack forms/navigation and contain wide tables in their own scroll
regions, avoiding horizontal scrolling of the page.

The initial page checks the current user's role/status. Touched requests also
check account context before sending and after receiving data: an account switch
blocks a prepared mutation and discards late private responses. Server-side
`AdminUser` authorization is still required even when the caller bypasses the UI.

## Verification and screenshots

The single expected-results matrix and commands are in
[testing.md](testing.md#task-152-admin-catalog-and-voucher-screens).
`tests/test_admin_portal_browser.py` runs production HTML/CSS/JavaScript in a real
Chrome/Edge browser. Browser requests are routed through the real FastAPI app and
isolated SQLite fixtures; successful CRUD checks inspect committed database rows.
Only failure/pending-response cases intentionally intercept selected responses.

The suite is collected by the existing CI pytest step, which already installs
Playwright. It uses `BROWSER_PATH`, installed Chrome/Edge, or available Chromium.
It requires a browser executable; a DOM-only check is not browser evidence.

Screenshots below are generated from deterministic fake fixtures, not production
accounts or human user tests:

- [Catalog, desktop](images/us21/catalog-desktop.png)
- [Categories, 390px mobile](images/us21/categories-mobile.png)
- [Voucher error with preserved input and visible focus](images/us21/voucher-error.png)

Local execution is separate from remote CI, human review and user acceptance.
