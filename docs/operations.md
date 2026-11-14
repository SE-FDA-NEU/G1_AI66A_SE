# M5 operations and handoff

Status checked 2026-11-14. Live URL: <https://mini-marketplace-se.web.app>.
Availability depends on the demo host and a temporary tunnel (see risks below).

## 1. How to run and release

Firebase Hosting serves the static frontend at
<https://mini-marketplace-se.web.app>; a Cloudflare Quick Tunnel forwards API
requests to FastAPI and SQLite on the demo host. Follow [deployment.md](deployment.md)
and [demo-sqlite.md](demo-sqlite.md). A release is: pull request, review, merge
into `main`, CI green, then the `Deploy Firebase Hosting` job publishes the
frontend (verified on main run 43567135851, commit `f826537`). When the tunnel
URL changes, update the `MARKETPLACE_API_ORIGIN` Actions variable and redeploy.
Roll back a broken frontend with Firebase Hosting's previous release, or
`git revert` through a reviewed PR and let CI deploy again. Roll back backend
code by restarting a previously verified commit; restore data only from a
verified backup after stopping writes.

## 2. The CI pipeline

`.github/workflows/ci.yml` detects the stack, installs Python 3.12 dependencies,
runs pytest with coverage, runs the JavaScript page-script checks, scans tracked
files for secrets, and on `main` only, after all of those succeed, exports and
deploys the frontend to Firebase Hosting. The Node job runs only if a package
manifest exists. Ruff is warning-only. The latest run on `main`
([43567135851](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/43567135851),
commit `f826537`) is green: 1802 tests passed in about 12 minutes, and the
deploy job succeeded. Branch protection for `main` is a repository setting;
attach a screenshot of it before submission.

## 3. Monitoring

Uvicorn and application logs appear in the backend process terminal; tunnel
logs appear in the `cloudflared` terminal. Passwords, tokens and request bodies
must not be logged; keep `DEBUG=false` and restrict log access. Backend
`/health` runs `SELECT 1` and returns 200 when the database is connected and
503 when it is not. It is served by the backend, so probe `<tunnel>/health`;
the Hosting URL has no `/health` route. Watch two numbers: the 5xx error rate
and response time. Proposed thresholds are 5xx above 1% and p95 above two
seconds over five minutes; no automated alert exists, so the demo operator
checks the logs and `/health` daily.

## 4. Known risks and technical debt

| Item | Layer | What could happen | Plan |
|---|---|---|---|
| Required checks not enforced | tests | A red change could be merged | #245: require the CI checks in the `main` ruleset. |
| Deploy needs a live tunnel URL | infrastructure | A changed tunnel URL breaks the deployed frontend | #245: update `MARKETPLACE_API_ORIGIN` and redeploy on every tunnel change. |
| Quick Tunnel and local host | infrastructure | Website API becomes unavailable or URL changes | #245: agree stable endpoint, monitoring and recovery procedure. |
| `/health` not on the Hosting URL | infrastructure | A probe of the public URL cannot see backend state | #245: probe the tunnel `/health`; accepted until stable hosting exists. |
| SQLite and uploads on one machine | data | Hardware loss or inconsistent backup loses data | #245: test database and upload backup/restore together. |
| Google sign-in account linking | code | Existing password users cannot use Google with the same email | #245: carry forward a safe authenticated linking flow; #243 was closed. |
| Sprint 4/5 points missing | docs | Velocity table is incomplete | #245: Scrum Master fills verified points. |

## 5. Maintenance plan

Owners and frequency are proposed; the team must confirm them.

| Area | What to do | Owner | How often |
|---|---|---|---|
| Bugs | Reproduce and prioritize issue reports | Team, assign per issue | Daily during demo |
| Dependencies | Review updates and run regression tests | Team, assign owner | Weekly |
| Data backups | Back up SQLite and uploads; test restore separately | Demo host operator | Daily during demo |
| Monitoring | Check tunnel, logs, health and user flows | Demo host operator | Daily during demo |
| Documentation | Compare URLs and commands with current deployment | Sprint 5 wrap-up owner | Every release |

## 6. Lessons learned

1. CI on `main` failed after catalog seed changes: tests and fixtures disagree on
   counts. Next, reconcile requirements and fixtures before merging and verify
   the resulting run rather than inferring success from a PR merge.
2. The login page could not reach Google when the local backend stopped. The
   team restarted it and moved the Google button into the login card; next,
   use monitored stable hosting and test failure recovery.
3. Uploaded product image URLs can contain a temporary tunnel hostname. The
   limitation is documented; next, define a stable image URL contract before
   relying on the demo for a release.

## 7. Sprint 5 handoff

[#245](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/245) closes when the team
accepts this handoff. The [sprint log](sprint-log.md) records verified issue and
PR states. Remaining: the `v1.0` release on commit `f826537`, a branch-protection
screenshot, Sprint 4/5 points and the grading-end date.

To regenerate the PDF after editing `MILESTONE5.md`, install Pandoc and
Playwright with its Chromium browser, then run
`python scripts/export_m5_pdf.py --font-dir /path/to/Windows/Fonts`. The folder
must contain `times.ttf` and `timesbd.ttf`. Do not commit the font files.
