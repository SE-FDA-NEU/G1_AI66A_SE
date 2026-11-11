# M5 operations and handoff

Status checked 2026-11-12 (Asia/Shanghai). This is a working draft, not evidence
of a completed release or the availability required through the grading date.

## 1. How to run and release

The [Firebase Hosting preview](https://mini-marketplace-se--demo-st26hys4.web.app)
serves static assets; a Cloudflare Quick Tunnel forwards API requests to FastAPI
and SQLite on the demo host. Follow [deployment.md](deployment.md) and
[demo-sqlite.md](demo-sqlite.md). The current preview was manually deployed; a
merge into `main` does not trigger deployment. Before release, the team must
implement and verify a CI-gated deploy and decide on stable hosting. Roll back a
broken frontend using Firebase Hosting's previous release, and roll back backend
code by redeploying a previously verified commit; restore data only from a
verified backup after stopping writes. Preview expiration and the machine being
offline interrupt the site.

## 2. The CI pipeline

`.github/workflows/ci.yml` detects the stack, installs Python dependencies,
runs pytest/coverage and browser-script checks, and scans tracked files for
secrets. The Node job is conditional on a package manifest. Ruff is currently
warning-only. The [latest checked main run](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/43056597333)
failed in Python tests, taking about 8 minutes 13 seconds; the
[last green main run found](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/42495790436)
was on 2026-11-08. It is not the latest commit. Verify required PR review and
green checks in repository settings; branch-protection access returned 404 and
no screenshot has been obtained.

## 3. Monitoring

Uvicorn and application logs appear in the backend process terminal; tunnel
logs appear in the `cloudflared` terminal. Access logs may include client IPs and
paths, and debug SQL may expose values: keep `DEBUG=false`, restrict log access
and verify redaction before claiming sensitive data is excluded. Backend
`/health` checks the database connection with `SELECT 1`; the current deployed
backend reports `database: disconnected` in a 200 response. This branch changes
that backend contract to 503, but has not been deployed. Hosting `/health`
currently returns 404. The team must configure monitoring for error rate and
response time and assign alert thresholds and owners; no alerts are verified.

## 4. Known risks and technical debt

| Item | Layer | What could happen | Plan |
|---|---|---|---|
| Latest main CI fails | tests | Broken changes can reach manual preview | #245: triage failed seed counts, snapshots and required labels; obtain a green run. |
| Manual deployment | infrastructure | URL does not match a CI-approved main commit | #245: configure and verify deploy-after-green before release. |
| Quick Tunnel and local host | infrastructure | Website API becomes unavailable or URL changes | #245: agree stable endpoint, monitoring and recovery procedure. |
| Hosted `/health` missing | infrastructure | External readiness check cannot validate service | #245: route a same-origin probe to the backend and verify 200/503 publicly. |
| SQLite and uploads on one machine | data | Hardware loss or inconsistent backup loses data | #245: test database and upload backup/restore together. |
| Google sign-in account linking | code | Existing password users cannot use Google with the same email | #243: agree and implement a safe authenticated linking flow. |
| M5 evidence incomplete | docs | Submission can misrepresent release readiness | #245: obtain board evidence, CI, tag and team confirmation. |

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

[#245](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/245) remains open. The
[sprint log](sprint-log.md) records verified issue/PR states and unknowns;
the Project board screenshot and end-of-sprint numbers are pending a screenshot,
sprint assignments and team confirmation. Do not tag `v1.0` or submit the draft until the team has
reviewed the remaining checks and the URL actually meets the milestone.

To regenerate the draft PDF after editing `Team01_M5.md`, install Pandoc and
Playwright with its Chromium browser, then run
`python scripts/export_m5_pdf.py --font-dir /path/to/Windows/Fonts`. The folder
must contain `times.ttf` and `timesbd.ttf`; the script embeds those fonts in the
PDF. Do not commit the font files. Verify the generated PDF before submission.
