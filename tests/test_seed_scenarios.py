"""#84: optional demo seed is complete, repeatable and non-destructive."""

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

import src.seed as seed
from src.auth import verify_password
from src.models.cart_item import CartItem
from src.models.order import Order
from src.models.order_item import OrderItem
from src.models.product import Product
from src.models.seller_order import SellerOrder
from src.models.user import User
from src.schemas.seller_products import ProductCreate
from src.services.seller_products import create_product
from tests.cart_db import enable_foreign_keys


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    event.listen(engine, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(seed, "engine", engine)
    monkeypatch.setattr(seed, "init_db", lambda: None)
    seed.seed_products()
    yield engine
    engine.dispose()


def snapshot(engine):
    with Session(engine) as session:
        return {
            model.__tablename__: [
                row.model_dump() for row in session.exec(select(model).order_by(model.id)).all()
            ]
            for model in [User, Product, CartItem, Order, SellerOrder, OrderItem]
        }


def test_demo_seed_accounts_stock_carts_and_order_consistency(seeded):
    assert seed.seed_demo_scenarios() is True
    with Session(seeded) as session:
        users = {row.email: row for row in session.exec(select(User)).all()}
        assert sum(row.role == "buyer" for row in users.values()) == 2
        assert sum(row.role == "seller" for row in users.values()) == 2
        for row in users.values():
            assert row.password_hash != "password"
            assert verify_password("password", row.password_hash)
        products = {row.code: row for row in session.exec(select(Product)).all()}
        assert len(products) == 53
        assert products["P-DEMO-OUT"].stock_quantity == 0
        lines = session.exec(select(CartItem)).all()
        assert len(lines) == 1 and lines[0].quantity == 2
        assert lines[0].buyer_id == users[seed.DEMO_BUYER_EMAIL].id
        assert not session.exec(
            select(CartItem).where(CartItem.buyer_id == users["demo.buyer@marketplace.local"].id)
        ).all()
        for status, code, quantity in seed.DEMO_ORDERS:
            parent = session.exec(
                select(Order).where(Order.request_key == f"seed84:{status}")
            ).one()
            child = session.exec(select(SellerOrder).where(SellerOrder.order_id == parent.id)).one()
            item = session.exec(
                select(OrderItem).where(OrderItem.seller_order_id == child.id)
            ).one()
            assert parent.status == child.status == status
            assert parent.total_amount == item.unit_price * item.quantity
            assert item.product_id == products[code].id and item.quantity == quantity
            assert child.seller_id == products[code].seller_id
            assert (child.completed_at is not None) == (status == "COMPLETED")
        assert len(session.exec(select(Order)).all()) == 4


def test_repeated_demo_seed_preserves_all_rows_and_user_changes(seeded):
    seed.seed_demo_scenarios()
    before = snapshot(seeded)
    seed.seed_products()
    assert seed.seed_demo_scenarios() is False
    assert snapshot(seeded) == before
    with Session(seeded) as session:
        line = session.exec(select(CartItem)).one()
        session.delete(line)
        product = session.exec(select(Product).where(Product.code == "P-DEMO-CART")).one()
        product.stock_quantity = 8
        product.name = "User edited listing"
        session.add(product)
        order = session.exec(select(Order).where(Order.request_key == seed.DEMO_MARKER)).one()
        order.status = "PROCESSING"
        session.add(order)
        session.commit()
    changed = snapshot(seeded)
    seed.seed_products()
    assert seed.seed_demo_scenarios() is False
    assert snapshot(seeded) == changed


def test_scenario_failure_rolls_back_marker_and_all_demo_rows(seeded):
    before = snapshot(seeded)
    from sqlalchemy import text

    with seeded.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER reject_demo_item BEFORE INSERT ON order_items "
                "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        )
    with pytest.raises(IntegrityError):
        seed.seed_demo_scenarios()
    assert snapshot(seeded) == before


def test_existing_non_demo_code_is_not_overwritten(seeded):
    with Session(seeded) as session:
        owner = session.exec(select(User).where(User.role == "seller")).first()
        session.add(
            seed.make_product(
                "P-DEMO-CART", "Existing listing", "Preserve", 99, 5, seller_id=owner.id
            )
        )
        session.commit()
    before = snapshot(seeded)
    with pytest.raises(RuntimeError, match="codes already exist"):
        seed.seed_demo_scenarios()
    assert snapshot(seeded) == before


def _create_demo_seller_listing(engine) -> int:
    """A real listing created through the Seller API, owned by the demo seller account.

    Its code always matches generate_product_code()'s format (P- + 18 hex chars), which
    also matches cleanup_legacy_catalog's "P-%" scan for retired seed fixtures.
    """
    with Session(engine) as session:
        demo_seller = session.exec(
            select(User).where(User.email == seed.DEMO_SELLER_EMAIL)
        ).one()
        created = create_product(
            session,
            demo_seller.id,
            ProductCreate(
                name="Seller's own listing",
                description="Created by the demo seller through the real API, not seeded.",
                price=199_000,
                stock_quantity=3,
                image_url="https://example.test/own-listing.jpg",
            ),
        )
        return session.exec(select(Product).where(Product.code == created.code)).one().id


def test_reseeding_preserves_an_unreferenced_listing_the_demo_seller_created(seeded):
    """A P-* code the demo seller creates themselves must survive reseeding untouched.

    cleanup_legacy_catalog scans the demo seller's "P-%" products to retire old seed
    fixtures; without excluding generate_product_code()'s format, a real listing with no
    orders/cart/variant/review would be deleted outright as if it were a retired fixture.
    """
    product_id = _create_demo_seller_listing(seeded)
    seed.seed_products()
    with Session(seeded) as session:
        product = session.get(Product, product_id)
        assert product is not None
        assert product.name == "Seller's own listing"
        assert product.is_active is True


def test_reseeding_preserves_a_cart_referenced_listing_the_demo_seller_created(seeded):
    """Same as above, but referenced by a cart: must stay active, not be deactivated."""
    product_id = _create_demo_seller_listing(seeded)
    with Session(seeded) as session:
        buyer = session.exec(select(User).where(User.role == "buyer")).first()
        product = session.get(Product, product_id)
        session.add(
            CartItem(
                buyer_id=buyer.id,
                product_id=product_id,
                quantity=1,
                price_at_add=product.price,
            )
        )
        session.commit()
    seed.seed_products()
    with Session(seeded) as session:
        product = session.get(Product, product_id)
        assert product is not None
        assert product.is_active is True


def test_demo_cli_on_fresh_sqlite_and_rerun(tmp_path):
    import sqlite3
    from contextlib import closing

    from tests.test_database import run_python

    path = tmp_path / "cli-demo.db"
    first_output = run_python(["-m", "src.seed", "--demo"], path)
    assert "Demo scenarios: added" in first_output
    assert "Products after demo seed: 53" in first_output
    assert "already installed (unchanged)" in run_python(["-m", "src.seed", "--demo"], path)
    with closing(sqlite3.connect(path)) as connection:
        for table, expected in [
            ("users", 5),
            ("products", 53),
            ("cart_items", 1),
            ("orders", 4),
            ("seller_orders", 4),
            ("order_items", 4),
        ]:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_demo_accounts_cart_catalog_and_receipt_api(seeded):
    from starlette.testclient import TestClient

    from src.database import get_session
    from src.main import create_app

    seed.seed_demo_scenarios()
    app = create_app()

    def sessions():
        with Session(seeded) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        for email, populated in [
            (seed.DEMO_BUYER_EMAIL, True),
            ("demo.buyer@marketplace.local", False),
        ]:
            login = client.post("/api/v1/auth/login", json={"email": email, "password": "password"})
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            cart = client.get("/api/v1/cart", headers=headers).json()["data"]
            assert bool(cart["items"]) == populated
            if populated:
                assert cart["cart_total"] == 200_000
                with Session(seeded) as session:
                    orders = session.exec(select(Order)).all()
                for order in orders:
                    result = client.get(f"/api/v1/orders/{order.id}", headers=headers)
                    assert result.status_code == 200
                    assert result.json()["data"]["total_amount"] == order.total_amount
            else:
                assert (
                    client.get(f"/api/v1/orders/{orders[0].id}", headers=headers).status_code == 404
                )
        catalog = client.get("/api/v1/products?limit=100").json()
        assert catalog["meta"]["total"] == 52
        assert "P-DEMO-OUT" not in {row["code"] for row in catalog["data"]}
        detail = client.get("/api/v1/products/P-DEMO-OUT")
        assert detail.json()["stock_status"] == "out_of_stock"


@pytest.mark.parametrize("demo", [False, True])
def test_parallel_cli_seeding_on_fresh_database_is_idempotent(tmp_path, demo):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import closing

    from tests.test_database import run_python

    path = tmp_path / "parallel.db"
    args = ["-m", "src.seed"] + (["--demo"] if demo else [])
    with ThreadPoolExecutor(max_workers=3) as pool:
        outputs = list(pool.map(lambda _: run_python(args, path), range(3)))
    assert len(outputs) == 3
    if demo:
        assert sum("Demo scenarios: added" in output for output in outputs) == 1
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == (
            53 if demo else 47
        )
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == (4 if demo else 0)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cli_demo_transaction_rolls_back_catalog_and_users_too(tmp_path, monkeypatch):
    from sqlalchemy import text

    value = create_engine(f"sqlite:///{(tmp_path / 'atomic.db').as_posix()}")
    event.listen(value, "connect", enable_foreign_keys)
    SQLModel.metadata.create_all(value)
    monkeypatch.setattr(seed, "engine", value)
    monkeypatch.setattr(seed, "init_db", lambda: None)
    with value.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER fail_demo BEFORE INSERT ON order_items "
                "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        )
    before = snapshot(value)
    try:
        with pytest.raises(IntegrityError):
            seed._run_seed(catalog=True, demo=True)
        assert snapshot(value) == before
        with value.begin() as connection:
            connection.execute(text("DROP TRIGGER fail_demo"))
        seed._run_seed(catalog=True, demo=True)
        with Session(value) as session:
            assert len(session.exec(select(Product)).all()) == 53
            assert len(session.exec(select(Order)).all()) == 4
    finally:
        value.dispose()


def test_fresh_nested_database_path_with_spaces_and_unicode(tmp_path):
    import sqlite3
    from contextlib import closing

    from tests.test_database import run_python

    path = tmp_path / "nested data" / "donn\u00e9es" / "demo.db"
    assert not path.parent.exists()
    output = run_python(["-m", "src.seed", "--demo"], path)
    assert "Products after demo seed: 53" in output
    assert path.is_file()
    assert "already installed" in run_python(["-m", "src.seed", "--demo"], path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_explicit_migration_then_seed_on_fresh_database(tmp_path):
    from tests.test_database import run_python

    path = tmp_path / "migrated.db"
    assert "initialization completed" in run_python(["-m", "src.database"], path)
    assert "Products after demo seed: 53" in run_python(["-m", "src.seed", "--demo"], path)
    assert "already installed" in run_python(["-m", "src.seed", "--demo"], path)
