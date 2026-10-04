# Team Project - Mini Marketplace

A mini marketplace where sellers can list products, buyers can add products to cart and place orders, with order management and basic sales analytics.

**Setup Guide:** [docs/SETUP.md](docs/SETUP.md)

**System Design:** [docs/design.md](docs/design.md)

## Team & Roles

- **Product Owner (PO):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)
- **Scrum Master (SM - Sprint 1):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)
- **Scrum Master (SM - Sprint 2):** [@minhnm162](https://github.com/minhnm162)

| Name | GitHub username | Team Role |
| --- | --- | --- |
| Nguyen Thuy Quynh | [@teddywristh](https://github.com/teddywristh) | Member |
| Nguyen Quang Minh | [@MinhQuangQu](https://github.com/MinhQuangQu) | Member |
| Nguyen Ho Nhat Minh | [@minhnm162](https://github.com/minhnm162) | SM - Sprint 2 / Member |
| Le Duc Minh | [@leducminh290506-eng](https://github.com/leducminh290506-eng) | PO / SM - Sprint 1 / Member |


## GitHub Project Board

- **Sprint Board Link:** [https://github.com/orgs/SE-FDA-NEU/projects/6/views/1?layout=board](https://github.com/orgs/SE-FDA-NEU/projects/6/views/1?layout=board)

## Definition of Done (DoD)

- Refer to the full team Definition of Done document: [Definition of Done](docs/definition-of-done.md)

---

## Tech Stack & Runtime

- **Language & Runtime:** Python `>= 3.12`
- **Web Framework:** FastAPI `>= 0.115.0`
- **ASGI Server:** Uvicorn `>= 0.30.0`
- **Configuration & Validation:** Pydantic & Pydantic-Settings
- **Database:** SQLite (SQLModel on SQLAlchemy)
- **Web UI:** HTML/CSS/JavaScript served by FastAPI (no Node.js or npm step)
- **Testing:** pytest, pytest-cov, Starlette/HTTPX
- **Linter & Formatter:** Ruff

The full fresh-machine guide, with configuration, troubleshooting and verification, is [docs/SETUP.md](docs/SETUP.md).

---

## Quickstart

Run every command from the repository root.

### 1. Clone & Setup Environment

#### Windows (PowerShell)
```powershell
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

#### macOS / Linux
```bash
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

### 2. Create and Seed the Database

```bash
python -m src.seed
```

The seed creates the SQLite database and its table, then loads the sample data. On a new database it prints `Added: 45 products` and `Total products: 45`. Running it again adds none.

### 3. Run the Tests

```bash
python -m pytest -v
```

### 4. Start Application Server

```bash
python -m src.main
```
Or with auto-reload:
```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000/products](http://127.0.0.1:8000/products): the page shows 20 product cards, starting with "Wireless Mouse" at 180.000 ₫.

The application will be accessible at:
- **Root Status:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Interactive API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Walking Skeleton Products API:** [http://127.0.0.1:8000/api/v1/products](http://127.0.0.1:8000/api/v1/products)
- **Products Page (US01):** [http://127.0.0.1:8000/products](http://127.0.0.1:8000/products)
