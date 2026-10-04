# Setup and Running Guide - Mini Marketplace

This guide takes a fresh machine from `git clone` to the running walking
skeleton: the `/products` page showing products read from a real SQLite
database. Run every command from the repository root, the folder that contains
`README.md`. Sections 1 to 7 follow the setup checklist in issue #51.

The macOS/Linux commands were run by the author on a clean clone (see section 7).
The Windows commands have not been run by the author; the independent check in
section 7 records what was tested.

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
| `DEBUG` | `true` | `python -m src.main` reloads on code changes, and SQLAlchemy logs every SQL statement |
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

The app uses a SQLite file, so there is no database server to install. Create
the table, then load the sample data:

```bash
python -m src.database
python -m src.seed
```

Expected output on a new database:

```text
Database initialization completed successfully.
Added: 45 products
Total products: 45
Active products: 45
```

With `DEBUG=true` (the template value), SQLAlchemy also prints every SQL
statement as `INFO sqlalchemy.engine.Engine ...` lines, so the lines above
appear among them.

- **Expected rows after seeding: 45 products**, codes `P-100` to `P-144`, all active.
- Running `python -m src.seed` again adds nothing (`Added: 0 products`, total still 45). Products whose code already exists are skipped, and edited rows are not reset.
- A database that already holds other products reports a different total. Use a new database file for a fresh-machine check.
- `python -m src.database` only creates missing tables. It does not migrate an existing table to a newer schema.
- The database file `marketplace.db` is created in the repository root and is ignored by Git. Never commit it.
- The app also creates missing tables when it starts, but it never loads sample data.

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
| http://127.0.0.1:8000/ | JSON with `"status": "running"` |
| http://127.0.0.1:8000/docs | Swagger UI listing the API |

`/health` only proves that the database connection works. The products page and
the API prove that the seeded data is there.

To run the automated tests, use a second terminal with the virtual environment
activated (or stop the server first):

```bash
python -m pytest -v
```

Expected: every test passes (45 passed at commit `840ad96`). The tests use an
in-memory database and do not touch `marketplace.db`.

`uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload` also starts the
app; it takes the host and port from the command line and ignores `APP_HOST`
and `APP_PORT`.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| PowerShell refuses `.\.venv\Scripts\Activate.ps1` with "running scripts is disabled on this system" | Skip activation and call the environment's Python directly: replace `python` with `.\.venv\Scripts\python.exe` in every later command, for example `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m src.main`. |
| `ModuleNotFoundError: No module named 'sqlmodel'` (or `fastapi`, or `src`) | The command ran outside the virtual environment or outside the repository root. `python -m pip --version` must show a path inside `.venv`. Activate the environment again (or use the direct path above), `cd` to the repository root and rerun `python -m pip install -r requirements.txt`. |
| `[Errno 98] error while attempting to bind on address ('127.0.0.1', 8000): address already in use` (on Windows the message starts with `[WinError 10048]`) | Another server already uses port 8000. Stop it with `Ctrl+C` in its terminal, or set `APP_PORT=8001` in `.env`, restart `python -m src.main` and open http://127.0.0.1:8001/products. |
| `/products` shows "No products available at the moment." or the API reports `"total": 0` | The server reads a database that was never seeded. Check that no `DATABASE_URL` is set in the shell (`echo $DATABASE_URL`, `echo %DATABASE_URL%` or `$env:DATABASE_URL`), run `python -m src.seed` from the repository root, then reload the page. |

---

## 7. Verification

The guide counts as verified only after a team member who did not write it
follows it on their own machine (issue #52). Record that run here.

| Field | Value |
|---|---|
| Tested by | _Pending (#52)_ |
| Non-author machine | _Pending: OS and version, machine type, new clone folder_ |
| Versions | _Pending: `git --version`, `python --version`, `python -m pip --version`, browser_ |
| Guide commit | _Pending: SHA of the guide that was followed_ |
| Test date | _Pending: date and time zone_ |
| Test duration | _Pending: start and end time of the whole setup, not the pytest time_ |
| Steps completed | _Pending: installation, `.env`, database, seed, start, success URL_ |
| Result | _Pending: Pass / Fail / Retest required_ |
| Problems and fixes | _Pending_ |
| Evidence | _Pending: screenshot or log links_ |

Author check, not the independent verification: on 2026-10-04 the author ran
the macOS/Linux commands on a clean clone of `main` at `840ad96` (this guide
changes documentation only), on Ubuntu 24.04 under WSL2 with Git 2.43.0,
Python 3.12.3 and pip 26.2.1. `pip check` was clean, the seed added 45 products
and then 0, `pytest` reported 45 passed, and every check in section 5 matched.

---

## Appendix A. Stack and Versions

| Component | Selected Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | `>= 3.12` (Target: `3.12.x`) | Core execution runtime |
| **Web Framework** | FastAPI | `>= 0.115.0` | High-performance async REST API with automatic OpenAPI documentation |
| **ASGI Server** | Uvicorn | `>= 0.30.0` | Lightning-fast ASGI web server |
| **Validation & Settings** | Pydantic / Pydantic-Settings | `>= 2.8.0` | Type-safe request validation and environment configuration |
| **Database ORM** | SQLAlchemy | `>= 2.0.30` | Declarative model mapping & database connection pool |
| **Database Engine** | SQLite | Built-in | Zero-configuration file database (dynamic runtime generation) |
| **Testing** | pytest, pytest-cov, Starlette/HTTPX | `>= 8.0.0` | Automated unit, integration, and smoke testing with coverage |
| **Code Quality** | Ruff | `>= 0.5.0` | High-speed linting and code formatting |

---

## Appendix B. Repository Structure

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Continuous Integration pipeline (linting, tests, secret scan)
│       └── ...
├── docs/
│   ├── SETUP.md                   # This setup and run guide
│   ├── requirements.md           # Product requirements & user stories (US01-US10)
│   ├── traceability.md           # Traceability matrix
│   └── ...
├── src/
│   ├── __init__.py                # Package version metadata
│   ├── config.py                  # Pydantic environment configuration loader
│   ├── database.py                # Database engine, session, & runtime schema creation
│   ├── main.py                    # Application entrypoint & ASGI app factory
│   ├── models/
│   │   ├── __init__.py            # Model registry
│   │   └── base.py                # SQLAlchemy DeclarativeBase and common mixins
│   └── api/
│       ├── __init__.py
│       ├── router.py              # Main API router (/api/v1)
│       ├── health.py              # Health check endpoint (/health & /api/v1/health)
│       └── products.py            # Initial product catalog skeleton (US01)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures and test client configuration
│   └── test_smoke.py              # Smoke tests covering startup, health, routes, OpenAPI
├── .env.example                   # Committed environment variable template (no secrets)
├── .gitignore                     # Excludes .env, *.db, *.sqlite*, caches, virtual environments
├── pyproject.toml                 # Modern Python build metadata, pytest, and ruff settings
├── requirements.txt               # Manifest of required dependencies
├── requirements.lock              # Pinned lockfile for deterministic builds
└── README.md                      # Project overview and quick start guide
```

---

## Appendix C. Continuous Integration (CI) Validation

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) automatically validates every push and pull request:
1. **Stack Detection:** Dynamically detects `requirements.txt` / `pyproject.toml`.
2. **Clean Dependency Installation:** Sets up Python 3.12 runner and installs `requirements.txt` and testing utilities.
3. **Static Analysis & Linting:** Executes `ruff check .` to guarantee code style and identify errors.
4. **Smoke and Unit Tests:** Executes `pytest -v --cov --cov-report=term-missing --junitxml=junit.xml` to verify endpoint availability and response contracts.
5. **Credential & Secret Scanning:** Validates that no secret keys, API tokens, `.env` files, or database binaries are accidentally committed.
