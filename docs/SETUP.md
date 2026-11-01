# Setup and Running Guide - Mini Marketplace

This guide takes a fresh machine from `git clone` to the running Mini Marketplace
with its SQLite catalog, authentication, cart, checkout and seller product form.
Section 8 adds the Sprint 3 demo scenarios and current independent-verification form. Run every command from the repository root, the folder that contains
`README.md`. Sections 1 to 7 follow the setup checklist in issue #51.

Section 7 preserves historical Sprint 2 checks on their original commits. Those
checks do not establish independent verification of the current Sprint 3 guide.
Section 8 records current checks separately; a non-author fresh-machine run is pending.

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Git | 2.x (the author used 2.43.0) | `git --version` |
| Python | 3.12 or newer; CI uses 3.12 | `python --version` (Windows) or `python3 --version` (macOS/Linux) |
| pip | Installed with Python; upgraded inside the virtual environment | `python -m pip --version` |
| Web browser | A current Chrome, Edge, Firefox or Safari | |
| Node.js | **Not required.** The page is plain HTML/CSS/JavaScript served by the Python app; there is no npm step. | |

If `python3 --version` (or `python --version` on Windows) shows a version older
than 3.12, create the virtual environment with an explicit interpreter such as
`python3.12` instead.

---

## 2. Installation

Clone the repository, create a virtual environment and install the dependencies
from `requirements.txt`, the same file CI installs.

### Windows (PowerShell)

```powershell
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

### Windows (Command Prompt)

```cmd
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

### macOS / Linux (Bash or Zsh)

```bash
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Expected: `python -m pip check` prints `No broken requirements found.`

Once the virtual environment is active, every platform uses the same
`python -m ...` commands for the rest of this guide.

---

## 3. Configuration

Create `.env` from the committed template:

| Shell | Command |
|---|---|
| PowerShell | `Copy-Item .env.example .env` |
| Command Prompt | `copy .env.example .env` |
| macOS / Linux | `cp .env.example .env` |

The template works as it is for local development; no value has to be changed.
`.env` is ignored by Git. Never put real passwords, tokens or API keys in
`.env.example` or in any other committed file.

| Variable | Template value | What it controls |
|---|---|---|
| `APP_NAME` | `"Mini Marketplace"` | Application name in the API docs and in `GET /` |
| `APP_ENV` | `development` | Environment name reported by `GET /` and `/health` |
| `DEBUG` | `false` | Set true explicitly for development reload and SQL logging |
| `APP_HOST` | `127.0.0.1` | Host used by `python -m src.main` |
| `APP_PORT` | `8000` | Port used by `python -m src.main` |
| `DATABASE_URL` | `sqlite:///./marketplace.db` | Database location; `./` is the folder the command runs from |
| `SECRET_KEY` | A development placeholder | Reserved for future signing; no current feature reads it |
| `CORS_ORIGINS` | JSON list of `localhost` / `127.0.0.1` origins | Origins allowed to call the API from another site; the `/products` page is served from the same origin and does not need it |

Every variable has a default in `src/config.py`, so the app also starts without
`.env`; the file keeps every machine on the same values. A variable already set
in the shell, such as an exported `DATABASE_URL`, takes precedence over `.env`.
Settings are read once at start-up, so restart the app after editing `.env`.

---

## 4. Database

The app uses a SQLite file, so there is no database server to install. The
initialize/migrate step prepares the schema before the seed loads sample data:

```bash
python -m src.database
python -m src.seed
```

The seed first creates the database file and any missing table of the data
model (`users`, `products`, `cart_items`, `orders`, `seller_orders`,
`order_items`), applies lightweight schema migrations (such as adding
`password_hash` if upgrading an existing SQLite database), and provisions
standard development buyer and seller accounts with usable hashed passwords
alongside the 45 sample products. Expected output on a new database:

```text
Added: 45 products
Total products: 45
Active products: 45
```

If you explicitly enable `DEBUG=true`, SQLAlchemy also prints every SQL
statement as `INFO sqlalchemy.engine.Engine ...` lines, including one
`CREATE TABLE` per table on a new database, so the lines above appear among them.

- **Development Accounts & Usable Credentials:**
  | Account | Email | Password | Role | Purpose |
  |---|---|---|---|---|
  | Primary Seller | `demo.seller@marketplace.local` | `password` | `seller` | Owns all 45 seeded catalog products |
  | Alternate Seller | `seller@example.com` | `password` | `seller` | Convenient standard email for seller testing |
  | Primary Buyer | `user@example.com` | `password` | `buyer` | Standard buyer account for checkout and auth testing |
  | Alternate Buyer | `demo.buyer@marketplace.local` | `password` | `buyer` | Local domain buyer account |

- **Automatic Migration & Recreate Process:**
  - `python -m src.seed` and `python -m src.database` automatically run `migrate_db()` to add missing columns (such as `password_hash`) to legacy SQLite databases without crashing or requiring manual SQL.
  - To perform a 100% clean recreate-and-seed from scratch:
    - **PowerShell:** `Remove-Item marketplace.db -ErrorAction SilentlyContinue; python -m src.seed`
    - **Command Prompt:** `if exist marketplace.db del marketplace.db & python -m src.seed`
    - **macOS / Linux:** `rm -f marketplace.db && python -m src.seed`
- Running `python -m src.seed` again adds nothing (`Added: 0 products`, total still 45) and ensures password hashes on existing seed users are populated.
- A database that already holds other products reports a different total. Use a new database file for a fresh-machine check.
- Optional: `python -m src.database` creates the missing tables and runs migrations without sample data and prints `Database initialization completed successfully.`
- The database file `marketplace.db` is created in the repository root and is ignored by Git. Never commit it.
- The app also creates missing tables and runs migrations when it starts, but it never loads sample data.

---

## 5. Running the Application

```bash
python -m src.main
```

The console shows, among other lines:

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Leave this terminal open while you use the app; stop it with `Ctrl+C`.

**Success URL: http://127.0.0.1:8000/products**

| Check | Exact expected result |
|---|---|
| http://127.0.0.1:8000/products | Heading "Products" and 20 product cards. The first card shows "Wireless Mouse", "180.000 ₫" and "In Stock". Images show a grey placeholder because the seeded image URLs are not served. |
| http://127.0.0.1:8000/api/v1/products?page=1&limit=20 | JSON with 20 items in `data`, the first with `"code": "P-100"`, and `"meta": {"current_page": 1, "limit": 20, "total": 45, "total_pages": 3}` |
| http://127.0.0.1:8000/health | `{"status":"ok","version":"0.1.0","environment":"development","database":"connected"}` |
| http://127.0.0.1:8000/ | A browser is sent to `/products`; `curl http://127.0.0.1:8000/` (no HTML `Accept` header) gets JSON with `"status": "running"` |
| http://127.0.0.1:8000/docs | Swagger UI listing the API |

`/health` only proves that the database connection works. The products page and
the API prove that the seeded data is there. The other P0 screens and the account
for each are listed at the top of the README ("P0 stories and where each one starts"); their states and
messages are documented in [ui.md](ui.md).

To run the automated tests, use a second terminal with the virtual environment
activated (or stop the server first):

```bash
python -m pytest -v
```

Expected: every test passes. The Milestone 4 P0 cases alone run with
`python -m pytest tests/test_m4_p0.py -v` (about 1 minute); see [testing.md](testing.md). Tests use in-memory or disposable file databases;
subprocess seed checks override DATABASE_URL and do not touch marketplace.db.

`uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload` also starts the
app; it takes the host and port from the command line and ignores `APP_HOST`
and `APP_PORT`.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| PowerShell refuses `.\.venv\Scripts\Activate.ps1` with "running scripts is disabled on this system" | Skip activation and call the environment's Python directly: replace `python` with `.\.venv\Scripts\python.exe` in every later command, for example `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m src.main`. |
| `ModuleNotFoundError: No module named 'sqlmodel'` (or `fastapi`, or `src`) | The command ran outside the virtual environment or outside the repository root. `python -m pip --version` must show a path inside `.venv`. Activate the environment again (or use the direct path above), `cd` to the repository root and rerun `python -m pip install -r requirements.txt`. |
| `[Errno 98] Address already in use` when explicitly using `DEBUG=true`, or `[Errno 98] error while attempting to bind on address ('127.0.0.1', 8000): address already in use` with `DEBUG=false`; on Windows the message starts with `[WinError 10048]` | Another server already uses port 8000. Stop it with `Ctrl+C` in its terminal, or set `APP_PORT=8001` in `.env`, restart `python -m src.main` and open http://127.0.0.1:8001/products. |
| `/products` shows "No products available at the moment." or the API reports `"total": 0` | The server reads a database that was never seeded. Check that no `DATABASE_URL` is set in the shell (`echo $DATABASE_URL`, `echo %DATABASE_URL%` or `$env:DATABASE_URL`), run `python -m src.seed` from the repository root, then reload the page. |
| Existing database fails after a schema change | Run `python -m src.database` to apply supported legacy column migrations. If the schema was manually altered beyond supported migrations, retain the file and choose a new unused DATABASE_URL as described in section 8.4. |

---

## 7. Verification

The guide counts as verified only after a team member who did not write it
follows it on their own machine (issue #52). Record that run here.

| Field | Value |
|---|---|
| Tested by | @leducminh290506-eng (#52) |
| Non-author machine | Windows 11 Home or Pro (x64), personal computer, new clone in `D:\G1_AI66A_SE` |
| Versions | Git 2.51.1.windows.1, Python 3.12.7, pip 26.2.1, Microsoft Edge (Chrome is also named in the record) |
| Guide commit | `1c5982d`, the guide before the review changes (see the note below) |
| Test date | 2026-10-04, GMT+7 |
| Test duration | 23:10 to 23:28, about 18 minutes |
| Steps completed | Clone; create and activate `.venv`; install `requirements.txt`; create `.env`; `python -m src.database`; `python -m src.seed` (45 products); `python -m src.main`; check the endpoints and `/products`; `python -m pytest -v` (45 passed) |
| Result | Pass |
| Problems and fixes | `pip check` outside the virtual environment reported conflicts; after activating `.venv` (`.\.venv\Scripts\Activate`) and installing `requirements.txt` it printed `No broken requirements found`. The server log shows `404` for `/images/p-*.jpg`; the page falls back to the placeholder image as designed. |
| Evidence | [Record on #52](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982133134) with a catalog screenshot and a server log screenshot; [confirmed and closed by @teddywristh](https://github.com/SE-FDA-NEU/G1_AI66A_SE/issues/52#issuecomment-5982150358) |

The independent run used the guide at `1c5982d`. Since then the guide makes
`python -m src.seed` the only database command, and #46 added the six-table
schema and the demo seller. The author checked those changes on Linux (below),
but no non-author has run the current guide yet: gap G5 in the
[Sprint 2 evidence](evidence/sprint2.md#6-gap-ledger).

Author check, not the independent verification: on 2026-10-04 the author ran
the macOS/Linux commands of sections 2 to 5 on a clean clone of `main` at
`85c98fe` (after #46 and #48; this guide changes documentation only) with a new
virtual environment, on Ubuntu 24.04 under WSL2 with Git 2.43.0, Python 3.13.12
and pip 26.2.1, in about 25 seconds with a warm pip cache. `pip check` was
clean. On a new database, `python -m src.seed` alone created the six tables,
the demo seller and 45 products, then added 0 on the second run. `pytest`
reported 46 passed and every check in section 5 matched. Both port-in-use
messages in section 6 appeared, and with `APP_PORT=8001` the app served
`/products` on port 8001. A database seeded by the code before #46 kept working
after the update, with no error and without the new constraints, which is why
section 4 asks to delete it.

---

## Appendix A. Stack and Versions

| Component | Selected Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | `>= 3.12` (Target: `3.12.x`) | Core execution runtime |
| **Web Framework** | FastAPI | `>= 0.115.0` | High-performance async REST API with automatic OpenAPI documentation |
| **ASGI Server** | Uvicorn | `>= 0.30.0` | Lightning-fast ASGI web server |
| **Validation & Settings** | Pydantic / Pydantic-Settings | `>= 2.8.0` / `>= 2.4.0` | Type-safe request validation and environment configuration |
| **Database ORM** | SQLModel on SQLAlchemy | `>= 0.0.22, < 0.0.23` / `>= 2.0.30` | Table models, sessions and queries |
| **Database Engine** | SQLite | Built-in | Zero-configuration file database (dynamic runtime generation) |
| **Web UI** | HTML / CSS / JavaScript | - | Eight pages (catalog, detail, cart, checkout, confirmation, login, seller product form, seller orders) served by FastAPI; no build step |
| **Testing** | pytest, pytest-cov, HTTPX | `>= 8.0.0` / `>= 5.0.0` / `>= 0.27.0` | Automated unit, integration, and smoke testing with coverage |
| **Code Quality** | Ruff | `>= 0.5.0` | High-speed linting and code formatting |
| **Page script checks** | Node.js (optional) | `>= 20` | Runs `tests/checkout_ui.mjs`, `tests/seller_products_ui.mjs` and `tests/seller_orders_ui.mjs`; not needed to run the app |

---

## Appendix B. Repository Structure

```
.
├── .github/
│   ├── pull_request_template.md   # PR form used by every pull request
│   └── workflows/
│       ├── ci.yml                 # Lint, pytest, page script checks, secret scan
│       └── ...                    # Board, label and Scrum checks
├── docs/
│   ├── SETUP.md                   # This setup and run guide
│   ├── requirements.md            # Product requirements & user stories (US01-US10)
│   ├── design.md                  # Architecture, data model, API contract and error codes
│   ├── ui.md                      # Screens, states, error cases and known UI gaps
│   ├── traceability.md            # Route, story, business rule and test traceability
│   ├── us01-...md to us10-...md   # One specification per user story
│   ├── sprint-log.md              # Sprint log
│   ├── evidence/                  # Sprint and story evidence (milestone3.md, us04.md, us06.md, ...)
│   └── images/                    # Evidence screenshots; ui/ holds the Milestone 3 UI screenshots and screen flow
├── src/
│   ├── __init__.py                # Package version metadata
│   ├── config.py                  # Pydantic environment configuration loader
│   ├── database.py                # Engine, sessions and lightweight migrations
│   ├── seed.py                    # Accounts, catalog and the optional --demo scenarios
│   ├── auth.py                    # Password hashing, JWTs and role dependencies
│   ├── errors.py                  # Common {"error": {code, message}} envelope
│   ├── main.py                    # Application factory, error handlers and `/`
│   ├── models/                    # users, products, cart_items, orders, seller_orders, order_items, order_history
│   ├── schemas/                   # Request/response models: cart, orders, seller_products
│   ├── services/                  # Business rules: cart, orders (checkout), seller_products
│   ├── api/                       # /api/v1 routers: auth, products, cart, orders, seller_products, seller_orders, health
│   └── web/
│       ├── router.py              # Serves the HTML pages
│       ├── pages/                 # products, product-detail, cart, checkout, confirmation, login, seller-product-new, seller-orders
│       └── static/                # Page scripts, styles and the placeholder image (/static)
├── tests/
│   ├── conftest.py                # Shared fixtures (in-memory SQLite)
│   ├── cart_db.py                 # Disposable SQLite file database for service/API tests
│   ├── test_*.py                  # pytest suites per feature, P0 flows and the docs contract
│   └── *_ui.mjs                   # Page script checks run with Node
├── .env.example                   # Committed environment variable template (no secrets)
├── .gitignore                     # Excludes .env, *.db, *.sqlite*, caches, virtual environments
├── pyproject.toml                 # Build metadata, pytest and ruff settings
├── requirements.txt               # Dependencies installed by this guide and by CI
├── requirements.lock              # Pinned versions; not used by this guide or by CI
└── README.md                      # Project overview and quick start guide
```

---

## Appendix C. Continuous Integration (CI) Validation

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) automatically validates every push and pull request:
1. **Stack Detection:** Dynamically detects `requirements.txt` / `pyproject.toml`.
2. **Clean Dependency Installation:** Sets up Python 3.12 runner and installs `requirements.txt` and testing utilities.
3. **Static Analysis & Linting:** Executes `ruff check .` to guarantee code style and identify errors.
4. **Smoke and Unit Tests:** Executes `pytest -v --cov --cov-report=term-missing --junitxml=junit.xml` to verify endpoint availability and response contracts.
5. **Page Script Checks:** Sets up Node 22 and runs `node tests/checkout_ui.mjs`, `node tests/seller_products_ui.mjs` and `node tests/seller_orders_ui.mjs`.
6. **Credential & Secret Scanning:** Validates that no secret keys, API tokens, `.env` files, or database binaries are accidentally committed.


## US04 orders migration (#80)

Startup (python -m src.main) and seeding (python -m src.seed) automatically add
nullable orders.request_key and orders.request_hash plus the unique key index.
Existing orders are preserved; repeated startup is safe. No reset is required.
See [checkout verification](evidence/us04.md) for the buyer checkout/receipt flow.


## 8. Sprint 3 demo data and fresh-machine check (#84)

### 8.1 Choose the dataset

`python -m src.seed` keeps the original 45-product catalog command and automated
walking-skeleton contract. Use `python -m src.seed --demo` for the full P0 demo.
The CLI applies schema initialization/migrations first, then inserts accounts,
catalog and all requested demo scenarios in a single data transaction. On a clean database: 4 users, 51 products (50 visible in catalog),
1 cart line, 4 orders, 4 seller orders, 4 order items. Active out-of-stock products
are intentionally hidden from the catalog but accessible by their detail URL.

| New database demo account | Password | Initial scenario |
|---|---|---|
| user@example.com | password | Cart: P-DEMO-CART x2, total 200000 VND; owns four sample orders |
| demo.buyer@marketplace.local | password | Empty cart, no sample orders; buyer isolation check |
| demo.seller@marketplace.local | password | 45 catalog products plus demo cart/pending/completed products |
| seller@example.com | password | Demo processing/cancelled/out-of-stock products |

Passwords are stored as scrypt hashes. Existing nonempty hashes, products and user
changes are not overwritten. These initial cart/count expectations apply only to
a clean database, not to a database someone has already used.

| Product code | Seller | Physical stock | Related fixture |
|---|---|---|---|
| P-DEMO-CART | Primary seller | 12 | Primary buyer cart quantity 2; no stock reservation |
| P-DEMO-PENDING | Primary seller | 9 | PENDING order, quantity 1, unit price 150000 |
| P-DEMO-PROCESS | Alternate seller | 8 | PROCESSING order, quantity 2, unit price 200000 |
| P-DEMO-COMPLETE | Primary seller | 7 | COMPLETED order, quantity 3, unit price 250000 |
| P-DEMO-CANCEL | Alternate seller | 10 | CANCELLED order, quantity 1, unit price 300000; already restored |
| P-DEMO-OUT | Alternate seller | 0 | Direct detail shows Out of stock; Add to Cart disabled |

Demo orders have one seller order each and purchase-time price snapshots; their
parent/child statuses agree. Dates are fixed at 2026-10-10 12:00 UTC (19:00 GMT+7),
including completed_at for the completed fixture. Filter seller orders on that
UTC date to find them. These are synthetic fixtures, not actual recorded user
sessions or status-transition histories. PR #96 supplies seller management and its
history model; `/seller/orders` is unavailable until that PR is integrated.

`orders.request_key = seed84:PENDING` is the installation marker. Other fixture
keys are seed84:PROCESSING, seed84:COMPLETED and seed84:CANCELLED. They are reserved
fixture identifiers, not keys for a live checkout replay. An existing marker makes
`--demo` leave all scenarios unchanged, including an emptied cart or processed
order. Do not remove individual marker/product rows to reset the demo. Conflicting
pre-existing demo product codes or account roles are rejected without partial
scenario insertion. A failure before commit leaves no scenario marker or partial
scenario rows. Failure in the demo stage also rolls back catalog/account changes
made by the same CLI invocation. Schema initialization is a separate prior stage.
Users/products use SQLite ON CONFLICT DO NOTHING keyed by email/code, preserving
existing passwords, IDs, quantities and edits. BEGIN IMMEDIATE serializes seed
writers before checking natural keys and marker; schema creation also serializes
first-run DDL, so concurrent seed processes do not race missing-table creation.

### 8.2 Fresh Windows PowerShell run

Use a new clone directory and Python 3.12 or later. Record the tested branch/commit.
Before merge, replace the branch below with chore/84-seed-setup-verification;
after merge use main. Do not reuse the author's virtual environment or database.

```powershell
git clone --branch main https://github.com/SE-FDA-NEU/G1_AI66A_SE.git G1_AI66A_SE-fresh84
cd G1_AI66A_SE-fresh84
git rev-parse HEAD
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
Copy-Item .env.example .env
$env:DEBUG = 'false'
$env:DATABASE_URL = 'sqlite:///./marketplace-fresh84.db'
python -m src.database
python -m src.seed --demo
python -m src.seed --demo
python -m pytest
python -m ruff check src tests
python -m src.main
```

First run core output: Added: 45 products; Total products: 45; Active products: 45;
then Demo scenarios: added and Products after demo seed: 51. Second run core output:
Added: 0 products; Total products: 51; then Demo scenarios: already installed
(unchanged), final products 51. Stop the server with Ctrl+C when finished.
DATABASE_URL/DEBUG process variables override .env and must remain set when starting
that server. If you use another terminal, set the same variables there.

### 8.3 Fresh macOS/Linux run

```bash
git clone --branch main https://github.com/SE-FDA-NEU/G1_AI66A_SE.git G1_AI66A_SE-fresh84
cd G1_AI66A_SE-fresh84
git rev-parse HEAD
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
cp .env.example .env
export DEBUG=false
export DATABASE_URL=sqlite:///./marketplace-fresh84.db
python -m src.database
python -m src.seed --demo
python -m src.seed --demo
python -m pytest
python -m ruff check src tests
python -m src.main
```

### 8.4 Non-destructive migration and reset

Startup/seed/init creates missing tables and migrates users.password_hash and
orders.request_key/request_hash with the unique index. Existing rows are retained;
this does not repair arbitrary manually modified schemas. PR #96 registers
order_history, which init_db creates once that model is present.

To keep existing data, run `python -m src.database`, then optionally
`python -m src.seed --demo`. Legacy accounts get a hash only when missing; modified
passwords are preserved. Do not count this upgrade as a clean-machine installation.

For a safe fresh demo without deleting your current database, stop the server and
set DATABASE_URL to a new unused filename, e.g. marketplace-demo-reset84.db, using
the platform's environment syntax above. Run seed --demo and start the server in
the same environment. This creates a clean dataset while retaining the previous
file. Change back to the earlier DATABASE_URL and restart to recover that dataset.
Choose another unused filename for each reset; reusing an existing one is not a reset.
All *.db/*.sqlite/*.sqlite3/*.sql/*.dump and .env files are ignored; commit none.

### 8.5 Independent verification checklist and record

A tester other than the current SETUP author must perform the fresh run and
complete [the #84 evidence record](evidence/setup84.md). The old #52 check in
section 7 does not satisfy this requirement for the current commit.

Check /health, /products and /api/v1/products?limit=100 (total 50 on a fresh demo).
Check /products/P-DEMO-OUT for out-of-stock detail. Log in each buyer and compare
cart states; the primary total is 200000 VND. Use the primary buyer to load a seeded
receipt (derive its actual ID from database/API; never assume ID=1). Log in each
seller and, after PR #96 merges, verify only their own demo orders and the fixed-date
filter. Existing fixtures include completed/cancelled states; do not attempt to
cancel a processing order. Save seed output from both runs, test output and browser
screenshots. Record any missing US08 route honestly instead of marking it passed.


### 8.6 Review follow-up: environment and portability

No new environment variables are required by the seed. DATABASE_URL, DEBUG and
application/auth configuration are all listed in .env.example with development
defaults; --demo is a command-line flag. The template now defaults DEBUG=false so
onboarding does not depend on reload mode or SQL logging. Existing .env files are
not modified automatically. Clear or correct an inherited invalid DEBUG value if
Pydantic rejects it; process environment variables override .env.

The project's scripts run with `python -m src.database` and `python -m src.seed`
on all platforms. Use forward-slash SQLite URLs, e.g.
`sqlite:///./data/demo database.db`, from the repository root. Runtime directory
creation uses pathlib; SQLAlchemy creates the SQLite file. Relative folders may
contain spaces and Unicode. Windows activation vs Bash `source` is intentionally
shown separately; do not paste a Windows drive path into WSL. macOS/Linux/WSL
execution must still be recorded by a tester on those systems; a Windows test
against a portable path is not proof of every OS. This repo does not use db:seed,
PostgreSQL roles/categories or a separate SQL migration tool.
