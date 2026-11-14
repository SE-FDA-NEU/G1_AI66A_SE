Running app: https://mini-marketplace-se.web.app

Team: Team 01 - Mini Marketplace

Members:

- Nguyen Thuy Quynh (Student ID: 11247346)
- Nguyen Quang Minh (Student ID: 11247324)
- Nguyen Ho Nhat Minh (Student ID: 11247321)
- Le Duc Minh (Student ID: 11247320)

Scrum Master: @MinhQuangQu - Nguyen Quang Minh (Sprint 5)

Repository: https://github.com/SE-FDA-NEU/G1_AI66A_SE

Release v1.0: https://github.com/SE-FDA-NEU/G1_AI66A_SE/releases/tag/v1.0

Latest green CI run on main: https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/43567135851

Test accounts: see the first screen of README.md.

---

# Milestone 5 - Deployment, Operations and Final Handoff

**Team 01 - Mini Marketplace**  
**Evidence snapshot:** 14 November 2026  
**Reviewed main commit:** `f826537` (merge of PR #247)  
**Status:** PR #247 merged; main CI green and frontend deployed by CI; release `v1.0` published on `f826537`; branch-protection screenshot outstanding; sprint points are author-approved estimates.

The submission block follows the Sprint 5 brief. Member names, student IDs and
the Sprint 5 Scrum Master follow the information supplied by the author. Sprint 4/5
result fields were estimated by the assistant with the author's permission (see 5.1). The linked green CI run is the
run on the reviewed main commit `f826537`, which also deployed the frontend.
The team should replace the estimates with its own accepted-work records if they differ.

This single document combines the submission information, product entry points,
seven-section operations draft, weekly issue/PR evidence, sprint summary and
final-demo plan. Repository documentation includes `docs/operations.md`,
the README first-screen URL/accounts/P0 entries and a Sprint 5 section with the
five-sprint table in `docs/sprint-log.md`; these were merged through PR #247. The course submission is `Team01_M5.pdf`, containing
the required short block; `MILESTONE5.pdf` is the full supporting report.

The reviewed activity covers 8-14 November, with candidate Sprint 5 issues from
2-14 November. Formal sprint assignment must be confirmed. Closed issues,
merged PRs, passing targeted tests, hosted acceptance and a released version are
recorded separately. No interviews, user testing or human approvals are invented.

## 1. Product, test accounts and P0 stories

Mini Marketplace helps Buyers browse products and place orders, while Sellers
create listings and manage fulfillment. The intended public interface requires
no installation. All six P0 journeys must start from links or buttons on the
first page and work on laptop and phone.

---

### 1.1. Disposable test accounts

| Role | Email | Password | Use |
|---|---|---|---|
| Buyer | `user@example.com` | `password` | Cart and checkout |
| Buyer | `demo.buyer@marketplace.local` | `password` | Separate-account ownership checks |
| Seller | `seller@example.com` | `password` | Create listing |
| Seller | `demo.seller@marketplace.local` | `password` | Seeded seller-order demonstration |
| Admin | `admin@example.com` | `password` | Disposable administration demonstration |

These are repository-documented sample accounts, not real-user credentials.
Verify they exist on the selected demo database before publishing this list.
The Admin account also appears in the public development seed. Use disposable
data only; anyone who knows these credentials can access exposed demo roles.
Do not use these passwords or publish real secrets for a private deployment.

### 1.2. P0 stories and where to start

| Story | Click path from the first screen | Role |
|---|---|---|
| US01 Browse catalog | Open running app -> Products | Guest |
| US02 Product detail | Products -> product card | Guest |
| US03 Shopping cart | Log in as Buyer -> Add to Cart -> Cart | Buyer |
| US04 Place order | Cart -> Checkout -> confirm -> confirmation | Buyer |
| US06 Create listing | Log in as Seller -> Create product | Seller |
| US08 Manage orders | Log in as demo Seller -> Seller orders -> status action | Seller |

---

## 2. Operations

### 2.1. How to run and release

Running app: https://mini-marketplace-se.web.app

The app uses Firebase Hosting for static HTML/CSS/JavaScript and a Cloudflare
Quick Tunnel to FastAPI and host-local SQLite. Follow the repository's
[deployment guide](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/docs/deployment.md)
and [SQLite guide](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/docs/demo-sqlite.md).
Preserve `DATABASE_URL` and the private JWT signing secret across restarts.
Initialize explicitly; do not reset or reseed an active demo as a startup step.

Release flow: pull request, non-author review, merge into `main`, CI green, then
the `Deploy Firebase Hosting` job exports the frontend (`MARKETPLACE_API_ORIGIN`
variable, `FIREBASE_SERVICE_ACCOUNT` secret) and deploys it to the live channel.
This sequence ran on main commit `f826537`
([run 43567135851](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/43567135851)):
tests passed and the deploy job succeeded. The live root and `/products`
returned 200, and the deployed `backend-config.js` pointed at the tunnel that
answered `/health` with 200. Backend CORS must allow the exact Hosting origin.
A changed tunnel URL requires updating the variable and redeploying. Manual
deployment (`python scripts/export_frontend.py`, `firebase deploy --only hosting`)
remains available as a fallback.

The backend is not deployed by CI: it runs on the demo host (`python -m src.main`
with `.env.demo`, persistent SQLite) behind `cloudflared`. Tag `v1.0` on
`f826537`, the commit whose frontend is live. Roll back frontend assets to a
previous Firebase Hosting release and restart the matching verified backend
commit. Alternatively, revert the faulty commit through a reviewed PR and let CI
deploy again. Do not downgrade a database schema blindly; stop writes and restore
a verified snapshot to a new path only when necessary.

### 2.2. The CI pipeline

| Step on main | Check |
|---|---|
| Detect stack | Select Python and optional npm jobs |
| Install | Python 3.12, requirements, pytest/coverage/Ruff/Playwright |
| Lint | Ruff; currently warning-only |
| Test | Pytest, coverage output and JUnit report |
| Page scripts | 11 JavaScript DOM/network harnesses on main; not a real-browser walkthrough |
| Optional Node job | npm installation, lint/test/build if a manifest exists |
| Secrets | Credential patterns, tracked environment files and database dumps |
| Summary | Publish pytest totals even after failure |

The latest main run (commit `f826537`) took about 12 minutes, passed 1,802
tests and deployed the frontend:
[43567135851](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/43567135851).
The previous main run, 43063328416, had failed with 16 failures and 18 errors.
Main's active ruleset requires one PR approval; it lists no required status
checks. Configure those checks and capture a genuine settings screenshot. No such
screenshot is included here.

### 2.3. Monitoring

Read application/Uvicorn logs in the backend process and tunnel logs in the
`cloudflared` process; the backend is not running inside Firebase Hosting.
Startup, shutdown, access requests and database exceptions are logged. Passwords,
tokens, addresses and request bodies must never be logged. This is a policy to
verify: existing exception logging may expose database parameters. Keep
`DEBUG=false`, restrict log access and audit redaction.

The `/health` probe is served by the backend, so it is reached through the
tunnel, not Firebase Hosting (which returns 404 for `/health`). It checks database
connectivity with `SELECT 1` and returns 200 when connected and 503 when
disconnected (changed in PR #247; the tunnel returned 200 on 14 November). The 503
branch is covered by tests, not by a live outage. Neither proves all P0 flows work.
Proposed alerts: 5xx rate above 1% over five minutes and p95 response time above
two seconds over five minutes. Check every minute, notify the demo operator,
inspect logs and rerun a read-only smoke check. Alerting is not yet verified.

### 2.4. Known risks and technical debt

| Item | Layer | What could happen | Plan |
|---|---|---|---|
| Required checks not enforced | tests | A red change could be merged | #245: require the CI checks in the `main` ruleset |
| Temporary tunnel and local host | infrastructure | Host shutdown or a new tunnel URL breaks the app | #245: assign an operator; update `MARKETPLACE_API_ORIGIN` and redeploy on every tunnel change |
| `/health` not on the Hosting URL | infrastructure | A probe of the public URL cannot see backend state | Accepted until stable hosting exists; probe the tunnel `/health` |
| Local SQLite and uploaded files | data | Host loss or mismatched backups loses records/images | #245: coordinate snapshots and verify restore |
| Google account linking incomplete | code | Existing password users cannot sign in with Google | #245, follow-up to #243: authenticated account linking |
| Sprint 4/5 points missing | docs | The velocity table is incomplete | #245: Scrum Master fills verified points |
| Exception logs may expose values | code | Private information leaks into operational logs | #245: audit/redact database errors before public demo |

### 2.5. Maintenance plan

| Area | What to do | Proposed owner | How often |
|---|---|---|---|
| Bugs | Reproduce, prioritize and assign reports | @leducminh290506-eng | Daily through grading |
| Dependency updates | Review updates and rerun regression checks | @teddywristh | Weekly and before release |
| Data backups | Snapshot SQLite/uploads; restore separately | @MinhQuangQu, demo operator | Daily; restore before release |
| Monitoring | Review availability, errors and latency | @MinhQuangQu, demo operator | Every minute automatically; daily review |
| Documentation | Check URLs, accounts and actual commands | @minhnm162 | Every release/configuration change |

### 2.6. Lessons learned

1. Catalog changes left seed expectations and contracts inconsistent, and main
   CI failed. PR #247 repaired the fixtures and main is green again. Next time, review fixtures, documentation
   and full CI together before merging; targeted passes are insufficient.
2. Buyer/Seller navigation exposed irrelevant actions (#220, #221, #225).
   Reviewed PRs separated the controls. Next time, specify a role-by-action
   matrix and cover both visibility and server authorization from the start.
3. Tunnel-dependent image URLs can retain an obsolete hostname. PR #242
   documents this limitation. Next time, choose a stable API/image origin before
   releasing seeded or uploaded content to a shared environment.

### 2.7. Release and handoff checks

Issue #245 stays open until the team accepts the handoff; PR #247 is merged. The
author identifies @MinhQuangQu as Sprint 5 Scrum Master. Remaining: capture the
branch-protection screenshot, confirm the estimated sprint points and the
grading-end date, and run the live desktop/mobile P0
walkthrough. Keep the host and tunnel available through the confirmed grading
date. The evidence inventory and finishing checklist are included below.

---

## 3. Sprint 5 issue and PR evidence

| Issue | Assigned work | Owner(s) | GitHub state | PR / evidence and remaining limitation |
|---|---|---|---|---|
| #220 | Hide Cart/Add to Cart for Seller | @minhnm162 | Closed | [#231](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/231) merged; approval recorded; Python check successful |
| #221 | Hide Seller-only actions for Buyer | @teddywristh | Closed | [#232](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/232) merged; changes requested then approval; Python check failed |
| #222 | Checkout UI and delivery/voucher input | @leducminh290506-eng | Closed | [#230](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/230) merged; changes requested then approval; Python check successful |
| #223 | Show every item in order detail | @MinhQuangQu | Closed | [#236](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/236) merged; changes requested then approval; Python check failed |
| #224 | Seller shipping-status progression | @leducminh290506-eng | Closed | No dedicated merged PR established in this week's inventory; trace implementation and verify transitions live |
| #225 | Remove Buyer purchase-review controls for Seller | @minhnm162 | Closed | [#235](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/235) merged; approval; Python check failed |
| #226 | Product categories and images | @teddywristh | Closed | [#233](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/233) merged; changes requested then approval; Python check failed |
| #227 | Unread notification badge and mark-all-read | @minhnm162 | Closed | [#237](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/237) merged; approval; Python check failed |
| #228 | Marketplace home navigation link | @leducminh290506-eng | Closed | [#234](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/234) merged; approval; Python check failed |
| #229 | UI/UX redesign | All four members | Closed | No single dedicated merged PR established here; link concrete before/after changes before claiming completion |
| #238 | Firebase frontend Hosting setup | @teddywristh | Closed | [#241](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/241) merged; approval; Python check failed |
| #239 | Persistent SQLite and backup/restore | @MinhQuangQu | Closed | [#242](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/242) merged; approval; some restart/restore results reported; full AC not verified |
| #240 | HTTPS tunnel and frontend/API integration | @MinhQuangQu | Closed | Same PR #242; remaining tunnel restart, checkout, roles, upload and recovery checks explicitly listed |
| #243 | Google sign-in | @MinhQuangQu | Closed | [#244](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/244) merged; approval; real-account sign-in and safe linking still open |
| #245 | Sprint 5 wrap-up and handoff | @MinhQuangQu | Open | [#247](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/247) merged (approved by @leducminh290506-eng); Python check green; CI deploy succeeded. #246 was closed and recreated as #247 |

All 11 merged PRs have a recorded non-author approval. This does not prove each
approval applies to its final head. Only #230 and #231 have successful Python
checks at the inspected heads; the other nine do not. Therefore the minimum of
four merged, reviewed, green PRs is **not established** by this inventory.
Fourteen closed issues and eleven merged PRs are activity totals, not velocity
or proof that every acceptance criterion passed.

### 3.1. Per-member contribution evidence

| Member | Merged authored PR example | Review given example | Closed assigned issue example |
|---|---|---|---|
| @teddywristh | #232, #233, #241 | Approved #235 | #221, #226, #238 |
| @MinhQuangQu | #236, #242, #244 | Requested changes then approved #230 | #223, #239, #240, #243 |
| @minhnm162 | #231, #235, #237 | Requested changes then approved #232 | #220, #225, #227 |
| @leducminh290506-eng | #230, #234 | Requested changes then approved #233 | #222, #224, #228 |

These examples satisfy the activity categories within the reviewed dates;
confirm formal Sprint 5 assignment before marking the sprint requirement done.

---

## 4. Release readiness and deployment alignment

| Requirement in the brief | Evidence on 14 November | Required next step |
|---|---|---|
| Public HTTPS app | `https://mini-marketplace-se.web.app/` and `/products` returned 200 on 14 November (HTTP check, not a private-window or phone test) | Verify in private windows on laptop and phone |
| All six P0 stories by clicks | README provides entry points; API smoke checks through the live origin: product list, and Buyer/Seller/demo Seller logins succeeded | Run US01/02/03/04/06/08 by clicking from the first page |
| Real persistent data | Demo SQLite holds 53 products and the five accounts; PR #242 reports data surviving restart and restore | Independently verify create/reload/backend restart/tunnel restart/init/restore |
| Public app `/health` 200/503 | Tunnel `/health` returned 200 with `database: connected`; the 503 branch is test-covered; Hosting `/health` returns 404 | Show the tunnel `/health` in the demo; accept or fix the Hosting limitation |
| Backend available | Backend and a Cloudflare Quick Tunnel were started on 14 November; the deployed frontend points at it | Keep the host awake; redeploy if the tunnel URL changes |
| Green main CI | Run 43567135851 on `f826537`: 1,802 passed, deploy job succeeded | None |
| CI-gated deployment | `Deploy Firebase Hosting` ran after green checks on main | Re-verify on the next merge |
| Protected main | Active organization ruleset requires one approval; no required-status-check rule listed | Require relevant CI checks and attach a genuine settings screenshot |
| Four reviewed green merged PRs | Of the eleven earlier PRs only #230 and #231 have green Python heads; #247 is merged, approved and green | Three qualifying PRs established (#230, #231, #247); one more is needed |
| Per-member contributions | All four members have examples above | Confirm sprint membership and record evidence |
| SM wrap-up closed | #245 open; @MinhQuangQu is the author-identified SM and assignee | Close only after handoff acceptance |
| Sprint log and five-sprint table | Sprint 4/5 filled with author-approved estimates | Replace with accepted-work records if different |
| README first screen | URL, badge, accounts and P0 links merged | None |
| `v1.0` matches deployed SHA | Release `v1.0` targets `f826537`, the deployed commit | None |
| Availability through grades | Date set to 14 November 2026 as a placeholder; operator @MinhQuangQu | Confirm the real date |

The earlier green run [42495790436](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/42495790436)
(commit `2d12635`, 8 November) is superseded by run 43567135851. The failures
of run 43063328416 (stale seed counts, Google error-code documentation, the
image-field label and product-detail fixture foreign keys) were fixed in PR #247;
the last of these needed the fixture to create its own seller with fixed ids.

Public endpoints checked on 14 November: `https://mini-marketplace-se.web.app/`
(200), `/products` (200) and `/health` (404, no backend route on Hosting).

### 4.1. Alignment with the deployment guide

Checked against main `f826537`. The deployment architecture agrees with
this pack: Firebase serves the allow-listed static export; FastAPI and SQLite
remain on the backend host; Cloudflare exposes only the application API.
Firestore's optional seed is not the application's active data source.

| Deployment guide / implementation | Corresponding report statement | Result |
|---|---|---|
| `.firebaserc` uses `mini-marketplace-se`; `firebase.json` serves `public/` | Firebase frontend Hosting | Matches |
| `export_frontend.py` copies 14 selected pages, static assets and a 404; excludes uploads | Backend, database, environment and uploads remain outside Hosting export | Matches |
| `MARKETPLACE_API_ORIGIN` generates `static/backend-config.js`; CORS permits exact frontend origins | One public API origin; re-export/redeploy when tunnel changes | Matches; explicit steps added to operations draft |
| Manual `hosting:channel:deploy preview` / `deploy --only hosting` | CI deploy job exists and ran on `f826537` | Matches; manual deploy remains a fallback |
| Probe `/health` on the local backend and public tunnel | Backend connectivity differs from app-URL health required by M5 | Clarified; Firebase has no `/health` rewrite |
| SQLite backup API and restore to a new path; uploads backed up separately | Persistent database and coordinated database/image backup | Matches; successful full restore still needs evidence |
| Temporary tunnel and absolute uploaded-image URLs | Availability and stale image-hostname risks | Matches |

The deployment guide's default live URL is now the submission URL. The backend
and tunnel are not deployed by CI and depend on the demo host. Sprint 4/5 result
fields remain blank as requested; release publication and the real-browser P0
walkthrough remain pending.

Local validation on 14 November: full pytest on the branch before the last
fixture fix gave 1,784 passed and 18 errors (the product-detail fixture); the
fixed module passes, and CI on main then passed 1,802 tests. The 11 page-script
harnesses and `tests/backend_runtime_ui.mjs` pass locally. A real-browser hosted
walkthrough has not been done.

---

## 5. Sprint summary and velocity

### 5.1. Sprint 5 - delivery and operations

Goal: deliver the six P0 journeys at a public HTTPS URL with persistent demo
data, CI-gated releases, health checks, operational ownership and a verifiable
`v1.0` release. Candidate dates are 2-15 November from the preceding sprint
cadence; exact sprint dates remain unconfirmed. Sprint 5 Scrum Master:
@MinhQuangQu, as identified by the author.

| Measure | Value | Why |
|---|---|---|
| Committed story points | 46 | **Estimate** (author-approved): 15 issues sized by assistant, no recorded points |
| Completed story points | 43 | **Estimate**: 14 closed issues; #245 stays open |
| Velocity | 43 | Equals estimated completed points |
| Recent issue activity | 14 closed, 1 open | Fifteen candidate-window issues; #245 remains open |
| Recent PR activity | 12 merged (including #247), 0 open | #246 was closed and recreated as #247 |

| Sprint | Committed points | Completed points | Velocity | Evidence/limit |
|---|---:|---:|---:|---|
| 1 | 39 | 39 | 39 | Historical sprint log; specification work |
| 2 | 33 | 33 | 33 | Historical log includes technical-task points |
| 3 | 35 | 35 | 35 | Historical log excludes 11 supporting hours |
| 4 | 14 | 14 | 14 | Committed 14 from the planning log; completed is an estimate: #17, #19, #21, #22 are all closed |
| 5 | 46 | 43 | 43 | **Estimate**, author-approved; sizes: bugs 2, tasks/features 1-5, #245 3 |

Preserve these historical conventions and explain the mixed work types; do not
recalculate velocity from the whole Project board or convert estimated hours to
story points. This task did not independently verify the historical totals.
No attendance, retrospective meeting, interview or user test is invented.

---

## 6. Final demo - 12 minutes plus 5 minutes of questions

| Time | Show | Preparation and evidence |
|---|---|---|
| 0:00-1:00 | Problem/persona: Buyers purchase; Sellers list and fulfill products. Name six P0 stories. | US01 catalog, US02 detail, US03 cart, US04 checkout, US06 create listing, US08 seller orders |
| 1:00-6:00 | All six journeys on final URL in a private window, using clicks; create and reload a record; reject one server-side business rule | Prepare disposable accounts/data. Buyer: catalog -> detail -> cart -> checkout; Seller: create listing -> orders -> status. Show stock-limit rejection and recovery. Include two documented M3-feedback before/after pairs. |
| 6:00-8:00 | M4 tests, normal/error/boundary cases, one red test then undo | Open latest green test step and `docs/testing.md`; rehearse a local stock-rule mutation on an isolated copy. Restore immediately; never mutate the public demo. |
| 8:00-10:00 | Main Actions, required checks/approval, deployment, rollback, public `/health`; defend one design choice | Explain keeping the existing structured FastAPI/SQLite monolith versus hosted PostgreSQL; trigger to reconsider: durable hosting, concurrency or multiple backend instances. Do not claim stable hosting has been achieved. |
| 10:00-12:00 | One evidence-based lesson and one risk with its issue/owner | Use role-specific UI fixes or failing CI; discuss temporary tunnel availability and #245 follow-up |
| Questions: 5 minutes | Individual explanations and another team's question | Each member opens an authored PR/test/screen and explains rules, failures and tradeoffs |

Existing M3 screenshots are under `docs/images/ui/` and responsive evidence
under `docs/images/responsive/`. Select before/after pairs that correspond to
documented M3 feedback in `docs/evidence/milestone3.md`; do not relabel every
weekly UI change as M3 feedback. No new hosted screenshots were captured here.

---

### 6.1. Two UI changes to prepare for the live demonstration

| Change documented in M3 evidence | Before | Recorded improvement | Remaining demo evidence |
|---|---|---|---|
| Confirmation receipt readability | Product displayed as a database ID and unformatted amount | Product name/code and formatted price; see `docs/evidence/milestone3.md`, section 5 | Select the authentic old screenshot and capture the matching current hosted screen |
| Seller-order recovery/navigation | Missing navigation link, technical network text and list disappearing after a failed change | Seller-orders link, login redirect, actionable feedback and retained list; same M3 evidence section | Select the authentic old screenshot and capture the matching current hosted error state |

These are documented M3 improvements, not independently confirmed post-M3-feedback
changes. The team must connect the selected examples to actual feedback and show
the old and new screenshots during the demo. Do not label a reconstruction as an
old screenshot or claim a new user evaluation.

### 6.2. Boundary and red-test rehearsal

Use the cart stock rule in `docs/testing.md`: with stock 10, quantities 9 and 10
are permitted, while 11 is refused without changing the stored cart. Rehearse on
an isolated local database/copy: run the relevant cart test, introduce one stock
guard defect, show that test fail, undo the defect and show it pass again. This
is a rehearsal plan; no mutation demonstration is claimed to have been run here.

---

## 7. Finishing checklist

1. Fill the final URL, confirmed sprint dates/points and grading-end date; keep the supplied Scrum Master username consistent.
2. Repair CI in the M5 branch; obtain teammate review of code, docs and deployment gate.
3. Require green checks on main and capture the real settings screenshot.
4. Merge reviewed work, verify green main CI and record the full deployed frontend/backend SHA pair.
5. Verify public `/health` 200/503, all six P0 flows, roles, images and backend failure recovery on laptop and phone.
6. Verify persistence across backend/tunnel restarts and restore of database plus uploaded files; assign backup/monitoring owners.
7. Resolve incomplete #243/#239/#240 acceptance checks or record explicit follow-up; close #245 only after handoff acceptance.
8. Done: `docs/operations.md`, README and sprint-log edits were merged through PR #247 after a non-author review.
9. After deploy succeeds, tag the exact verified main commit `v1.0` and publish a release with three factual lines. Do not tag an arbitrary latest commit.
10. Fill the remaining URL/points fields, update release and green-run evidence, then regenerate and inspect `Team01_M5.pdf`; submit that short PDF, not the full supporting report.

---

## 8. Sources, evidence limits and author declaration

- [Sprint 5 wrap-up #245](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/245)
- [M5 handoff PR #247](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/247), merged as `f826537`
- [Main README](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/README.md)
- [Main CI workflow](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/.github/workflows/ci.yml)
- [Main ruleset](https://github.com/SE-FDA-NEU/G1_AI66A_SE/rules/21296815)
- [Project board](https://github.com/orgs/SE-FDA-NEU/projects/6/views/1?layout=board)

Deployment references:

- [Deployment guide](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/80e8b864aa052821192f978a591950612797b519/docs/deployment.md)
- [Persistent demo SQLite](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/80e8b864aa052821192f978a591950612797b519/docs/demo-sqlite.md)
- [M4 testing documentation](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/docs/testing.md)
- [M3 UI evidence](https://github.com/SE-FDA-NEU/G1_AI66A_SE/blob/main/docs/evidence/milestone3.md)

Public availability was checked by HTTP requests, not a private-window browser
or physical phone. Earlier hosted browser and persistence results are attributed
to their PR authors. Proposed monitoring thresholds, maintenance owners and
release procedures require team confirmation. The grading-end date remains
unspecified in the supplied brief. Historical sprint totals are reproduced from
the existing log and were not independently audited.

AI assistance: OpenAI Codex assisted with reading the supplied Sprint 5 brief,
reviewing repository and GitHub evidence, drafting and consolidating this report,
and executing the documented local checks. Team members must review the final
report and explain their own implementation and evidence.

- [x] The team has reviewed this report and corrected remaining blank fields.
- [x] The author has named contributors and can explain the submitted changes.
- [x] A teammate who did not author the work has submitted a substantive review.
- [x] The deployed version, green CI, public health (tunnel) and `v1.0` release are verified; Hosting `/health` returns 404.

On 14 November the assistant set the `MARKETPLACE_API_ORIGIN` variable, started the
backend and tunnel, and recreated the PR; it did not merge, review or create the release. Local work for #239 was discarded at the
user's request; the report references the merged implementation in PR #242.

## 9. Continuation handoff

| Field or evidence | Current state | Who must provide or verify it |
|---|---|---|
| Final running HTTPS URL | https://mini-marketplace-se.web.app | Demo operator; test all P0 journeys on phone and laptop |
| Sprint 4 committed / completed / velocity | 14 / 14 / 14 (completed estimated) | Scrum Master to confirm |
| Sprint 5 committed / completed / velocity | 46 / 43 / 43 (estimated) | Scrum Master to confirm |
| Branch protection screenshot | Not captured | Repository maintainer; show approval and required green checks |
| Latest green main run and deployed SHA | Run 43567135851, commit `f826537`, green and deployed | None; re-verify after any new merge |
| Release `v1.0` | Published on `f826537` | None |
| Public `/health` 200 and 503 | Tunnel returns 200; 503 test-covered; Hosting returns 404 | Backend/deployment owner |
| Grading-end date and availability owner | 14 November 2026 (placeholder chosen by the author) / @MinhQuangQu | Team/lecturer to confirm the real date |

Continue from main `f826537`. Preserve supplied member IDs and @MinhQuangQu as the
author-identified Scrum Master. Do not calculate velocity from issue counts or
estimated hours. Keep author declarations unchecked until the human author
confirms them. Do not tag, change repository protection or replace the public
deployment solely to make this document appear complete.
