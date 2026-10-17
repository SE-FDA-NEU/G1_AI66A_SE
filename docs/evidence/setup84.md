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
