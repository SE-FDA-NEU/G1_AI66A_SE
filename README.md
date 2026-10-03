# Team Project - Mini Marketplace

A mini marketplace where sellers can list products, buyers can add products to cart and place orders, with order management and basic sales analytics.

## Team & Roles

- **Product Owner (PO):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)
- **Scrum Master (SM - Sprint 1):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)

| Name | GitHub username | Team Role |
| --- | --- | --- |
| Nguyen Thuy Quynh | [@teddywristh](https://github.com/teddywristh) | Member |
| Nguyen Quang Minh | [@MinhQuangQu](https://github.com/MinhQuangQu) | Member |
| Nguyen Ho Nhat Minh | [@minhnm162](https://github.com/minhnm162) | Member |
| Le Duc Minh | [@leducminh290506-eng](https://github.com/leducminh290506-eng) | PO / SM / Member |

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
- **Database:** SQLite (SQLAlchemy ORM, generated at runtime)
- **Testing:** pytest, pytest-cov, Starlette/HTTPX
- **Linter & Formatter:** Ruff

For detailed architecture, configuration flags, and testing instructions, see [docs/SETUP.md](docs/SETUP.md).

---

## Quickstart

### 1. Clone & Setup Environment

#### Windows (PowerShell)
```powershell
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

#### macOS / Linux
```bash
git clone https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run Smoke Tests

```bash
pytest -v
```

### 3. Start Application Server

```bash
python -m src.main
```
Or with auto-reload:
```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

The application will be accessible at:
- **Root Status:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Interactive API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Walking Skeleton Products API:** [http://127.0.0.1:8000/api/v1/products](http://127.0.0.1:8000/api/v1/products)
- **Products Page (US01):** [http://127.0.0.1:8000/products](http://127.0.0.1:8000/products)
