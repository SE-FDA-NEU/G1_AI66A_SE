# Setup and Running Guide - Mini Marketplace

This document provides step-by-step instructions to set up, configure, run, and test the **Mini Marketplace** application from a clean checkout.

---

## 1. Selected Stack & Runtime

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

## 2. Repository Structure

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

## 3. Cross-Platform Setup Instructions

### Prerequisites
- Python 3.12+ installed on your system.
- Git.

---

### Windows (PowerShell)

```powershell
# 1. Clone the repository and enter the directory
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment file from template
Copy-Item .env.example .env

# 5. Initialize the database schema (optional, also runs on startup)
python -m src.database

# 6. Run the smoke tests
pytest -v

# 7. Start the application
python -m src.main
# Or run with uvicorn directly:
# uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

---

### Windows (Command Prompt - CMD)

```cmd
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

python -m venv .venv
.venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env

python -m src.database
pytest -v
python -m src.main
```

---

### macOS / Linux (Bash or Zsh)

```bash
# 1. Clone the repository and enter the directory
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
python3 -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment file from template
cp .env.example .env

# 5. Initialize the database schema (optional, also runs on startup)
python3 -m src.database

# 6. Run the smoke tests
pytest -v

# 7. Start the application
python3 -m src.main
# Or run with uvicorn directly:
# uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 4. Verifying the Running Application

Once the server is started:
- **Server Address:** `http://127.0.0.1:8000` (or `http://localhost:8000`)
- **Landing Root:** `GET http://127.0.0.1:8000/`
  ```json
  {
    "app": "Mini Marketplace",
    "version": "0.1.0",
    "status": "running",
    "environment": "development",
    "docs": "/docs",
    "health": "/health"
  }
  ```
- **Health Check:** `GET http://127.0.0.1:8000/health`
  ```json
  {
    "status": "ok",
    "version": "0.1.0",
    "environment": "development",
    "database": "connected"
  }
  ```
- **Interactive API Documentation (Swagger UI):**
  Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your browser.
- **Alternative ReDoc Documentation:**
  Open [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc) in your browser.
- **Product Catalog Skeleton (US01):**
  `GET http://127.0.0.1:8000/api/v1/products?page=1&limit=20`
- **Product Catalog Page:**
  Open [http://127.0.0.1:8000/products](http://127.0.0.1:8000/products) in
  your browser. The same FastAPI/Uvicorn server serves the page; there is no
  separate frontend build or npm step. Run `python -m src.seed` first to load
  the 45 sample products. The page requests `/api/v1/products?page=1&limit=20`,
  shows the first 20 products, and renders loading, error with Retry, and empty
  states.

---

## 5. Database Handling & Lifecycle

- The application uses **SQLite** as default for lightweight development and testing.
- **Dynamic Creation:** Database tables are initialized automatically at runtime during application startup (via FastAPI lifespan) or explicitly using `python -m src.database`.
- **Clean Checkout Guarantee:** The repository **does not** contain any committed database files (`*.sqlite`, `*.db`). `.gitignore` strictly excludes all database binaries and dumps.
- **Testing Isolation:** During automated tests, an in-memory database (`sqlite:///:memory:`) is used, preventing any file modifications or cross-test contamination.

---

## 6. Continuous Integration (CI) Validation

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) automatically validates every push and pull request:
1. **Stack Detection:** Dynamically detects `requirements.txt` / `pyproject.toml`.
2. **Clean Dependency Installation:** Sets up Python 3.12 runner and installs `requirements.txt` and testing utilities.
3. **Static Analysis & Linting:** Executes `ruff check .` to guarantee code style and identify errors.
4. **Smoke and Unit Tests:** Executes `pytest -v --cov --cov-report=term-missing --junitxml=junit.xml` to verify endpoint availability and response contracts.
5. **Credential & Secret Scanning:** Validates that no secret keys, API tokens, `.env` files, or database binaries are accidentally committed.
