from datetime import UTC, datetime

from scripts.seed_firestore import demo_documents


def test_demo_documents_are_deterministic_and_related():
    documents = demo_documents(datetime(2026, 1, 1, tzinfo=UTC))

    assert set(documents) == {"users", "categories", "products", "orders", "notifications"}
    assert documents["products"]["product-wireless-mouse"]["seller_id"] == "user-demo-seller"
    assert documents["orders"]["order-demo-1001"]["buyer_id"] == "user-demo-buyer"
    assert documents["notifications"]["notification-demo-1001"]["order_id"] == "order-demo-1001"
