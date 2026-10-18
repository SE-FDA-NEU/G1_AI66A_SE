# Issue #84: seed, SETUP and fresh-machine verification

Owner / current implementation and guide author: @minhnm162 with Codex assistance.
Baseline: origin/main fac5740; PR #96 still open when checked on 2026-10-18.
Status: implementation and automated checks completed locally; independent run NOT PERFORMED.

## Automated evidence

`tests/test_seed_scenarios.py` exercises hashed accounts, empty/data carts, all four
order statuses, purchase prices/totals/seller ownership, completed_at, inventory,
repeat seed with exact row comparison, preservation after user edits/cart deletion,
rollback after injected failure, product-code collision rejection, real CLI calls
on a fresh temporary SQLite file, foreign-key checks, login/cart/catalog/receipt
APIs and buyer isolation. The original default seed and legacy migration tests are
retained. Database and .env files are not added to Git.

Available author environment is Windows/Python 3.11.9 with an existing virtualenv;
repository target is Python 3.12. Automated temporary databases are not an independent
fresh-machine test.

Verified on 2026-10-18:

| Check | Result |
|---|---|
| Full pytest suite, final sequential run | 317 passed, 1 existing Starlette/httpx warning |
| New demo-seed cases | 6 passed (included in the full run) |
| Ruff src/tests and git diff --check | Passed |
| pip check in the existing author environment | No broken requirements found |
| Git tracked .env/database/dump files | None |

Commands: DEBUG=false for the process, then python -m pytest -q
--basetemp=.pytest_cache/issue84-final; python -m ruff check src tests;
python -m pip check; git diff --check. The explicit temporary directory isolates
this run from earlier test files. An earlier overlapping test attempt hit a
Windows SQLite file lock; the final isolated sequential full run above passed.
These results do not claim a clean dependency install or independent machine run.

## Acceptance status

- [x] At least two buyers and two sellers.
- [x] Demo passwords securely hashed; existing hashes preserved.
- [x] In-stock and out-of-stock products with `python -m src.seed --demo`.
- [x] Empty/data carts and seller orders in multiple statuses on a fresh demo DB.
- [x] Re-running does not duplicate or reset installed scenarios.
- [x] Database/.env files excluded from the intended changes.
- [x] Windows and Linux setup instructions.
- [x] Existing database migration and a fresh-file reset/recovery path.
- [x] Demo accounts, product codes, dates and expected counts documented.
- [ ] Tester other than the SETUP author performs fresh-machine verification.

## Independent tester record ? NOT PERFORMED

- Tester name/handle: pending (must differ from guide author).
- Date/time/timezone: pending.
- Device/OS, Python version (3.12+), Git version: pending.
- Tested branch and full commit SHA: pending.
- Clean clone directory / new virtual environment / fresh DB filename: pending.
- Followed Windows or Linux instructions: pending.

| Check | Expected | Actual / evidence | Result |
|---|---|---|---|
| Dependency install + pip check | No broken requirements | Not run | Pending |
| First demo seed | 4 users, 51 products, 1 cart line, 4 orders/suborders/items | Not run | Pending |
| Repeat demo seed | Already installed; counts unchanged | Not run | Pending |
| Catalog/detail | 50 purchasable; P-DEMO-OUT disabled | Not run | Pending |
| Buyer accounts | Primary populated, alternate empty, ownership isolated | Not run | Pending |
| Seller accounts after #96 | Own pending/completed vs processing/cancelled fixtures | Not run | Pending |
| Automated checks | All required tests/lint pass on tested baseline | Not run | Pending |
| Existing DB migration | Old rows preserved; seed repeated safely | Not run | Pending |
| Fresh-file reset/recovery | New demo DB; previous DB still present | Not run | Pending |

Problems, exact steps and resolution: not collected.
Screenshots / seed logs / test logs: not collected.
Tester confirmation and final result: pending.

Do not close #84 or mark this record passed until the named independent tester
has run the current instructions and provided their actual outcome.


## Review follow-up: RC seed and fresh setup

The earlier sequential CLI and foreign-key tests passed on fresh SQLite. No new
required seed environment variables were introduced (DATABASE_URL and DEBUG were
already in .env.example). The review nevertheless identified improvements worth
making: conflict-safe inserts and serialization for concurrent runs, one data
transaction across catalog/demo, explicit migration onboarding, and nested-path
creation. The implementation now covers those cases without deleting existing data.

- Users/products: ON CONFLICT DO NOTHING on email/code; retain changed passwords,
  IDs, ownership and product edits. Same-key full demo reruns preserve scenarios.
- Transaction: schema first; users -> products -> cart/order -> seller order ->
  order items in one data transaction with BEGIN IMMEDIATE. Committing users before
  children is not necessary: inserted/flushed parents are visible within the same
  connection and foreign keys stay enabled. Failures roll back all inserted data.
- First-run schema initialization also serializes SQLite writers, avoiding DDL
  races when concurrent seed processes start on a completely empty database.
- Config: .env.example documents the existing settings, portable URLs and CLI flag;
  DEBUG=false is the template default. No extra seed variable was invented.
- README/SETUP: dependencies -> explicit python -m src.database -> seed -> server.
  Seed still initializes/migrates itself if invoked directly on a fresh database.
- Path handling: pathlib creates missing SQLite parent folders; tests cover nested
  paths with spaces and Unicode. Actual non-Windows runs remain independent work.

Additional regressions: three simultaneous fresh CLI seed processes (both catalog
and demo mode), rollback of catalog/users when a later demo insert fails, retry
after the failure, explicit migration-before-seed, and nested missing directories.
Final review-fix run on 2026-10-18: **322 pytest tests passed** (including 11
seed-scenario cases); Ruff and git diff --check passed. One pre-existing
Starlette/httpx deprecation warning remains. Command: DEBUG=false followed by
python -m pytest -q --basetemp=.pytest_cache/review84-final. Changes remain local
and uncommitted at the time of this record; the independent-machine gate is unchanged.

Remaining evidence: non-author fresh-machine verification on Python 3.12+ and real
macOS/Linux/WSL execution. No tester identity, run or screenshots are fabricated.
