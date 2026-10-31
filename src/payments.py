"""Demo operator command for prepaid results (US20 section 7, decision D4).

    python -m src.payments record-result --order 12 --result PAID --event-key demo-12-1

It runs locally against the configured database in its own transaction and has no
HTTP surface, so no buyer or seller can mark an order paid.
"""

import argparse
import sys

from sqlmodel import Session

from src.database import engine, init_db
from src.services.payments import PaymentError, record_payment_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.payments")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record-result", help="Record a demo payment result.")
    record.add_argument("--order", type=int, required=True)
    record.add_argument("--result", choices=("PAID", "FAILED", "RETRY"), required=True)
    record.add_argument("--event-key", required=True)
    args = parser.parse_args(argv)

    init_db()
    with Session(engine) as session:
        try:
            order = record_payment_result(
                session, args.order, args.result, "DEMO_OPERATOR", args.event_key
            )
            session.commit()
        except PaymentError as exc:
            session.rollback()
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            return 1
        session.refresh(order)
        print(
            f"Order {order.id}: payment_status={order.payment_status} "
            f"escrow_status={order.escrow_status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
