# Team Project - Mini Marketplace

A mini marketplace where sellers can list products, buyers can add products to cart and place orders, with order management and basic sales analytics.

**Setup Guide:** [docs/SETUP.md](docs/SETUP.md)

**System Design:** [docs/design.md](docs/design.md) · **UI documentation:** [docs/ui.md](docs/ui.md)

## P0 stories and where each one starts

Set up and start the app with [docs/SETUP.md](docs/SETUP.md) (or the Quickstart below),
load the demo data with `python -m src.seed --demo`, then open
[http://127.0.0.1:8000/](http://127.0.0.1:8000/): the product catalog opens. Every
story starts from a link or button from there; no URL has to be typed.

| Story | Where it starts | Test account |
|---|---|---|
| US01 Browse the product catalog | The catalog that opens at `/` | None |
| US02 View product details | Select a product card in the catalog | None |
| US03 Manage the shopping cart | **Cart** in the top navigation, or **Add to Cart** on a product | `user@example.com` |
| US04 Place an order | **Checkout** at the bottom of the cart | `user@example.com` |
| US06 Create a product listing | **Create product** in the top navigation | `seller@example.com` |
| US08 Manage seller orders | **Seller orders** in the top navigation | `demo.seller@marketplace.local` |

Every test account uses the password `password`; these are development accounts
only. A protected page sends a guest to **Log in** and returns afterwards. The
accounts and their demo data are listed in
[SETUP section 8.1](docs/SETUP.md#81-choose-the-dataset).

## Team & Roles

- **Product Owner (PO):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)
- **Scrum Master (SM - Sprint 1):** [@leducminh290506-eng](https://github.com/leducminh290506-eng)
- **Scrum Master (SM - Sprint 2):** [@minhnm162](https://github.com/minhnm162)
- **Scrum Master (SM - Sprint 3):** [@teddywristh](https://github.com/teddywristh)

| Name | GitHub username | Team Role |
| --- | --- | --- |
| Nguyen Thuy Quynh | [@teddywristh](https://github.com/teddywristh) | SM - Sprint 3 / Member |
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

### 2. Initialize and Migrate the Database

```bash
python -m src.database
```

This creates missing tables and applies supported legacy migrations before data
is inserted. The command is safe to repeat; no separate database server or Alembic
step is required for the project's SQLite setup.

### 3. Seed the Database
 
```bash
python -m src.seed
```

The seed creates the SQLite database, runs automatic migrations, and loads development accounts (seller and buyer) with hashed passwords alongside the 45 sample products. On a new database it prints `Added: 45 products` and `Total products: 45`. Running it again adds none.

For the full P0 demonstration dataset (#84), run:

```bash
python -m src.seed --demo
```

On a fresh database this adds six scenario products to the 45-item catalog (51
stored, 50 purchasable), a populated primary-buyer cart, an empty alternate-buyer
cart, and four sample orders: PENDING, PROCESSING, COMPLETED and CANCELLED.
Re-running `--demo` preserves the installed scenarios and later user changes.
See [demo data and fresh-machine checks](docs/SETUP.md#8-sprint-3-demo-data-and-fresh-machine-check-84).

#### Seeded Development Credentials
| Role | Email | Password |
|---|---|---|
| Seller | `demo.seller@marketplace.local` (or `seller@example.com`) | `password` |
| Buyer | `user@example.com` (or `demo.buyer@marketplace.local`) | `password` |

To reset without dropping tables or losing existing data, stop the server and
choose a new, unused SQLite filename in `DATABASE_URL`, then repeat initialize ->
seed -> start. See SETUP section 8.4 for platform-specific environment syntax.
Existing databases can be migrated in place; no destructive clean flag is needed
for ordinary reruns. Users/products are inserted with ON CONFLICT DO NOTHING and
installed demo scenarios are preserved.

### 4. Run the Tests

```bash
python -m pytest -v
```

### 5. Start Application Server

```bash
python -m src.main
```
Or with auto-reload:
```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000/products](http://127.0.0.1:8000/products): the page shows 20 product cards, starting with "Wireless Mouse" at 180.000 ₫.

The application will be accessible at:
- **Root:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/) opens the catalog in a browser; API clients get the JSON status
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Interactive API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Products API:** [http://127.0.0.1:8000/api/v1/products](http://127.0.0.1:8000/api/v1/products)

The P0 stories and where each one starts are listed at the top of this README.
Every screen, its states and its error messages are documented in
[docs/ui.md](docs/ui.md); screenshots are in [docs/images/ui/](docs/images/ui/) and
the browser record is in the [Milestone 3 evidence](docs/evidence/milestone3.md).

### Checkout and confirmation (US04 / #80)

From a buyer cart choose Checkout, enter recipient name, address and phone, then
confirm. Success opens /checkout/confirmation/{orderId}; only its buyer can retrieve
the data. Checkout is atomic; retrying the same key returns the recorded order.
No shipping fee is added. Startup/seeding applies a non-destructive orders schema
upgrade to existing databases. See [US04 verification](docs/evidence/us04.md).

### Seller product creation (US06 / #81)

Log in as a seller (`seller@example.com` / `password`) and choose **Create product**
in the catalog navigation, or open
[http://127.0.0.1:8000/seller/products/new](http://127.0.0.1:8000/seller/products/new).
Enter name, description, price (whole VND), stock and an absolute http(s) image URL.
The listing is created active and owned by the logged-in seller; the page shows its
product code and a link to it. Stock 0 is allowed: the product page shows Out of
stock and the catalog leaves it out. Buyers and guests cannot create products. The
page-script checks run with `node tests/checkout_ui.mjs`,
`node tests/seller_products_ui.mjs`, `node tests/seller_orders_ui.mjs` and
`node tests/product_detail_ui.mjs` (Node is only needed for these checks). See
[US06 verification](docs/evidence/us06.md).

### Seller order management (US08 / #82)

Log in as a seller and choose **Seller orders** in the top navigation
([http://127.0.0.1:8000/seller/orders](http://127.0.0.1:8000/seller/orders)); a guest
is sent to login first. The page lists only that seller's sub-orders,
newest first, with status and date filters. Each card offers the next allowed step:
**Start processing** or **Cancel** for PENDING, **Mark shipped** for PROCESSING and
**Mark completed** for SHIPPED. Cancelling restores the stock once, and every change
is recorded in `order_history`. With `python -m src.seed --demo`,
`demo.seller@marketplace.local` sees PENDING and COMPLETED orders and
`seller@example.com` sees PROCESSING and CANCELLED ones.
