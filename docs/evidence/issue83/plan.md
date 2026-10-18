# Issue #83: execution guide

Scope: automated P0 verification and usability test preparation only.
No completed independent reviews or external-user sessions are included. Owner: @minhnm162.
The required evidence index is ../sprint3.md (section 4). This folder contains
repeatable scripts/checklists and blank recording forms, not completed sessions.

## Baseline and setup

Current branch starts from main fac5740. US08 is PR #96 at 96841c4, still open
when checked on 2026-10-18. Its content is treated as finalized by the task owner.
A disposable snapshot of that PR plus src/main.py and tests/test_p0_flows.py from
this branch was used for pre-merge integration verification. No PR code was edited
and no merge/approval was performed. Re-run on the final merged main commit.

After PR #96 merges, with this work committed, merge current main into this branch
and record the actual commit. Do not claim the PR snapshot run was a main run.

```powershell
git fetch origin
git merge origin/main
git rev-parse HEAD
.\.venv\Scripts\Activate.ps1
$env:DEBUG = 'false'
python -m pytest
python -m ruff check src tests
node tests/checkout_ui.mjs
node tests/seller_products_ui.mjs
python -m src.seed
python -m src.main
```

Use separate browser profiles/private windows for buyer and seller; tabs in one
profile share localStorage. Seed supplies buyer user@example.com and
 demo.buyer@marketplace.local, sellers demo.seller@marketplace.local and
seller@example.com. All demo accounts use the documented password `password`.
Use fictional delivery details. Never commit database files or real personal data.

## Prepare test data using the application

1. Seller A creates `US83 Mouse` at 100000 VND, stock 10 and an absolute image URL
   (e.g. https://example.com/mouse.jpg; image fallback is allowed).
2. Seller B creates `US83 Keyboard` at 300000 VND, stock 10.
3. Create a listing with stock 0 for the unavailable-product check; save its code.
4. Buyer A adds two mice and one keyboard and checks out: expected total 500000 VND,
   one parent order and two seller orders, physical stock 8 and 9.
5. Create separate new orders for the completion and cancellation scenarios; do not
   try cancelling an already-processing order. Record their actual IDs.
6. Empty the participant's cart through the UI before each new session and provide
   sufficient remaining stock. Re-running seed does not restore consumed stock.
7. For pagination, prepare >20 seller orders in a disposable test database or record
   the check as not run. Do not fabricate page-2 evidence from a one-order dataset.

## Functional cases (TC IDs match the matrix in sprint3.md)

| ID | Actions | Expected result / evidence |
|---|---|---|
| TC01 | Open / in browser, search US83, go Next/Previous | Browser enters catalog; matching active listings; stable pages. Screenshot URL and results. |
| TC02 | Open detail as guest, choose quantity, Add to Cart, log in | Return to detail with selection; confirm Add to Cart; correct buyer cart. |
| TC03 | Add two lines, edit quantity, remove one; enter above available stock | Totals match; removal persists; invalid change rejected with previous cart retained. Capture before/after. |
| TC04 | Submit empty/invalid delivery then valid checkout | Invalid fields explained; valid order receipt/total; purchased lines removed. Record order ID. |
| TC05 | Reload receipt; try as Buyer B; retry same key/payload through API | No second order; B gets 404; POST replay returns existing ID. Save redacted responses. |
| TC06 | After adding product, reduce available stock in another disposable session then submit | Failure names item, preserves cart/input, no partial order or stock reduction. Record DB before/after or automated test evidence. |
| TC07 | Seller submits valid listing and zero-stock listing | Server-owned seller/code; discoverable active stock listing; zero-stock detail not purchasable. |
| TC08 | Missing name/description, negative price/stock, invalid image URL; try buyer account | Field errors without inserted product; buyer forbidden; form values preserved. |
| TC09 | Each seller lists orders, filters date/status, navigates pages when enough records | Only own seller items; filters/date boundary work; all prepared orders reachable. |
| TC10 | PENDING -> PROCESSING -> SHIPPED -> COMPLETED | Child statuses saved, completed_at set; parent reaches COMPLETED when all children complete. |
| TC11 | Cancel separate PENDING order then attempt cancel again | Stock restored once, version increments, one history event; repeated transition rejected. |
| TC12 | Use wrong seller, invalid transition, guest/buyer API requests | Ownership/role denied; invalid transitions rejected; data/history unchanged. |
| TC13 | Switch account in another tab before checkout Confirm or pending Retry | Stale context blocked; reload required; no other-buyer order. |
| TC14 | Slow/offline API, empty carts/orders, keyboard and narrow screen | Visible loading/empty/error/retry states; controls usable. Record observations rather than assuming pass. |

HTTP tests do not execute the browser UI. Node tests use test doubles, not real users.
Use DevTools Network throttling for loading/offline checks, then return Online.
If you must type a route because navigation is missing, record this as assistance
or a finding rather than silently counting the navigation task as independent.

## Three independent heuristic reviews

Ask three separate people to inspect the UI independently before discussing findings.
Suggested team reviewers: @leducminh290506-eng, @MinhQuangQu, @teddywristh; these are
suggestions, not completed reviews. Each fills templates/heuristic-review.md and links the completed record from
heuristic-reviews.md.
Inspect feedback/status, real-world wording, consistency, navigation/recovery,
error prevention/messages, keyboard/focus and mobile readability. Record a zero-finding
review explicitly; do not leave an empty table and call it reviewed.

## External user sessions

Confirm the participant count with the team's planned sessions; the issue does not
state a number. If no plan exists, propose three people outside the development
team, 15-20 minutes each, with buyer and seller tasks represented. This is a proposal,
not a fabricated team decision or an issue requirement. Use anonymous IDs U01 etc.
Ask permission to take notes/screenshots, use demo accounts and fictional addresses.
Give the goals below, not a sequence of button instructions. Ask the participant
to describe what they expect. Avoid help until stuck; record every intervention.

- UT01 Buyer: Find the test mouse, buy two and one test keyboard, and report the
  order ID and total. Starts at /; includes catalog, detail, cart and receipt.
- UT02 Cart/error recovery: Change quantity, remove an unwanted item, recover from
  an invalid delivery field and complete checkout.
- UT03 Seller creation: Publish the supplied product details; show where a buyer
  can find the product. Then explain how to correct an invalid price.
- UT04 Seller fulfilment: Find a prepared new order, start processing it and move
  it through shipping/completion; cancel a different pending order.

Start timing after the goal is read and the starting page is ready. End when the
observable goal is achieved or the participant stops. Count a misclick as a wrong
control/action requiring correction; record hesitation separately. Completion is
independent / assisted / failed, not a single ambiguous yes/no. Record seconds,
misclick count, blocker/finding IDs, device/browser, commit and evidence filename.
A blank metric means not measured, never zero. Capture the participant's own feedback.

## Severity and exit criteria

0: not a usability problem; 1: cosmetic; 2: recoverable minor friction;
3: major difficulty/blocker needing assistance; 4: prevents core task or causes
serious incorrect results. Assign severity from observed impact; reviewers may
initially disagree and should preserve their original judgments before triage.
Each finding needs an owner, steps, expected/actual, evidence and retest result.
Severity 3-4 findings must be fixed and retested on the new commit. Do not mark
#83 done while required sessions or these retests are missing. Upload real evidence
and link it into ../sprint3.md; preserve anonymous notes and raw measurements.


## Deliverable boundaries after PR review

This PR's scope is the automated integration checks, browser-entry correction,
traceability matrix, execution protocol and blank forms in templates/. The evidence
indexes list only submitted completed records; currently neither human index has
any. Do not describe this as completed usability testing or close #83. The interface
screenshots already attached to PR #97 illustrate the application, not participant
identities, session timing or independent heuristic-review results.
