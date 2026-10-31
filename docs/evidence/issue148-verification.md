# #148 verification: CI and clean clone

Recorded on 2026-10-31 for PR #208 (branch `feat/148-payment-core`). Every result below
was observed directly; nothing here claims a review or a decision confirmation.

## CI

| Commit | Workflow | Event | Result |
|---|---|---|---|
| `67a4bc3` | CI | `pull_request` | success |
| `67a4bc3` | CI | `push` | success |

The run for the commit that adds this file is the one shown on the PR.

## Clean clone (Linux, Python 3.13.12)

Commands from the README "Clone & Setup Environment" section, in a new directory,
against commit `f9a4073`:

```bash
git clone --branch feat/148-payment-core https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip && python -m pip install -r requirements.txt
cp .env.example .env
python -m src.database   # Database initialization completed successfully.
python -m src.seed       # Total products: 45
python -m src.seed --demo  # Products after demo seed: 51
uvicorn src.main:app --host 127.0.0.1 --port 8148
```

| Check | Observed |
|---|---|
| `GET /` and `GET /api/v1/health` | 200 and 200 |
| Buyer `user@example.com` adds `P-100` and checks out with `payment_method: "VIETQR"` | Order created: `VIETQR`, `UNPAID`, escrow `HELD`, `paid_amount` 0 |
| `python -m src.payments record-result --order 5 --result PAID --event-key clean-demo-1`, twice | `payment_status=PAID escrow_status=HELD` both times (second run changes nothing) |
| Same command for order 999 | Prints `ERR_ORDER_NOT_FOUND: Order not found.`, exit code 1 |
| Seller `demo.seller@marketplace.local` moves the sub-order through `PROCESSING`, `SHIPPED`, `DELIVERED`, `COMPLETED` | 200 for each step |
| Seller receipt | `PAID`, `COMPLETED`, escrow `RELEASED`, commission 19.000, seller net 361.000 (380.000 at 500 bps), `settled_at` set |
| Buyer receipt | `VIETQR`, `PAID`, `paid_amount` 380.000; seller net hidden (`null`) |
| A late `FAILED` result (`--event-key clean-late-fail`) | `payment_status=PAID escrow_status=RELEASED`; no regression |
| `GET /orders/5` page | 200 |
| `python -m pytest -q --ignore-glob='*browser*'` in the clone | `1181 passed, 1 skipped, 4 warnings in 918.04s` |
| `python -m ruff check src` plus the three payment test files | `All checks passed!` |

The server log had no errors. Browser-driven checks (`*browser*`) were not run.

## Still open

Decisions D1–D5 in `docs/us20-payments.md` section 12 are pending owner confirmation.
This file does not confirm them.
