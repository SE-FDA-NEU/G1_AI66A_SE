"""Create deterministic demo documents for the Mini Marketplace Firestore project.

The payloads mirror the current marketplace domain, but are intentionally
independent from the SQLite seed. Running this script again updates the same
document IDs instead of creating duplicates.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ID = "mini-marketplace-se"
SERVICE_ACCOUNT_ENV = "FIREBASE_SERVICE_ACCOUNT_JSON"


def demo_documents(now: datetime | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Return the small, safe demo dataset without contacting Firebase."""
    created_at = now or datetime.now(UTC)
    created_at = created_at.astimezone(UTC)
    buyer_id = "user-demo-buyer"
    seller_id = "user-demo-seller"

    return {
        "users": {
            buyer_id: {
                "name": "Demo Buyer",
                "email": "demo.buyer@marketplace.local",
                "role": "buyer",
                "status": "ACTIVE",
                "created_at": created_at,
            },
            seller_id: {
                "name": "Demo Seller",
                "email": "demo.seller@marketplace.local",
                "role": "seller",
                "status": "ACTIVE",
                "created_at": created_at,
            },
        },
        "categories": {
            "category-electronics": {
                "name": "Electronics",
                "slug": "electronics",
                "parent_id": None,
                "is_active": True,
            },
            "category-home": {
                "name": "Home & Living",
                "slug": "home-living",
                "parent_id": None,
                "is_active": True,
            },
        },
        "products": {
            "product-wireless-mouse": {
                "code": "P-100",
                "seller_id": seller_id,
                "category_id": "category-electronics",
                "name": "Wireless Mouse",
                "description": "Quiet wireless mouse for everyday work.",
                "price": 180000,
                "stock_quantity": 45,
                "reserved_stock": 0,
                "image_url": "/static/product-placeholder.svg",
                "is_active": True,
                "version": 1,
            },
            "product-desk-lamp": {
                "code": "P-101",
                "seller_id": seller_id,
                "category_id": "category-home",
                "name": "Adjustable Desk Lamp",
                "description": "LED desk lamp with three brightness levels.",
                "price": 320000,
                "stock_quantity": 18,
                "reserved_stock": 0,
                "image_url": "/static/product-placeholder.svg",
                "is_active": True,
                "version": 1,
            },
        },
        "orders": {
            "order-demo-1001": {
                "buyer_id": buyer_id,
                "status": "COMPLETED",
                "total_amount": 180000,
                "payment_method": "COD",
                "payment_status": "PAID",
                "escrow_status": "RELEASED",
                "recipient_name": "Demo Buyer",
                "delivery_address": "1 Demo Street, Hanoi",
                "phone_number": "0900000000",
                "created_at": created_at - timedelta(days=2),
                "items": [
                    {
                        "product_id": "product-wireless-mouse",
                        "product_code": "P-100",
                        "product_name": "Wireless Mouse",
                        "quantity": 1,
                        "unit_price": 180000,
                    }
                ],
            }
        },
        "notifications": {
            "notification-demo-1001": {
                "recipient_user_id": buyer_id,
                "order_id": "order-demo-1001",
                "event_key": "order-demo-1001-completed",
                "message": "Your order has been completed.",
                "target_path": "/orders/order-demo-1001",
                "created_at": created_at - timedelta(days=1),
                "read_at": None,
            }
        },
    }


def seed_firestore() -> int:
    """Overwrite the deterministic demo documents and return the write count."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as error:
        raise SystemExit(
            "Install Firebase Admin SDK first: "
            "python -m pip install -r requirements-firebase.txt"
        ) from error

    service_account_path = os.environ.get(SERVICE_ACCOUNT_ENV)
    if service_account_path:
        app = firebase_admin.initialize_app(
            credentials.Certificate(str(Path(service_account_path))),
            {"projectId": PROJECT_ID},
        )
    else:
        app = firebase_admin.initialize_app(options={"projectId": PROJECT_ID})

    client = firestore.client(app)
    count = 0
    for collection, documents in demo_documents().items():
        for document_id, payload in documents.items():
            client.collection(collection).document(document_id).set(payload)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(f"Wrote {seed_firestore()} demo Firestore documents to {PROJECT_ID}.")


if __name__ == "__main__":
    main()
