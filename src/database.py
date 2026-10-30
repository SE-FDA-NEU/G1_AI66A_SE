import json
from collections.abc import Generator
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.config import get_settings

settings = get_settings()
DATABASE_URL = settings.DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

database_url = make_url(DATABASE_URL)
pool_options = (
    {"poolclass": StaticPool}
    if database_url.get_backend_name() == "sqlite"
    and database_url.database in (None, "", ":memory:")
    else {}
)

if database_url.get_backend_name() == "sqlite" and database_url.database not in (
    None,
    "",
    ":memory:",
):
    # SQLAlchemy creates the file, but not its parent directories. pathlib keeps
    # nested relative paths portable across Windows, Linux and WSL.
    if not database_url.database.startswith("file:"):
        Path(database_url.database).resolve().parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
    **pool_options,
)

if database_url.get_backend_name() == "sqlite":

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection,
        connection_record,
    ):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def migrate_db(connection: Connection | None = None) -> None:
    """Apply lightweight schema migrations for existing databases."""
    from sqlalchemy import inspect

    with nullcontext(connection) if connection is not None else engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "users" in tables:
            columns = {c["name"] for c in inspector.get_columns("users")}
            if "password_hash" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"
                    )
                )
            if "status" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'"
                    )
                )

        if "cart_items" in tables:
            columns = {c["name"] for c in inspector.get_columns("cart_items")}
            if "is_selected" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE cart_items ADD COLUMN "
                        "is_selected BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
            if "price_at_add" not in columns:
                connection.execute(text("ALTER TABLE cart_items ADD COLUMN price_at_add INTEGER"))
            if "products" in tables:
                connection.execute(
                    text(
                        "UPDATE cart_items SET price_at_add = "
                        "(SELECT price FROM products WHERE products.id = cart_items.product_id) "
                        "WHERE price_at_add IS NULL"
                    )
                )
            if "variant_id" not in columns:
                if (
                    connection.dialect.name == "sqlite"
                    and {
                        "buyer_id",
                        "product_id",
                        "quantity",
                        "created_at",
                    }
                    <= columns
                ):
                    connection.execute(
                        text(
                            "CREATE TABLE cart_items__variants ("
                            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                            "buyer_id INTEGER NOT NULL, product_id INTEGER NOT NULL, "
                            "variant_id INTEGER, quantity INTEGER NOT NULL, "
                            "is_selected BOOLEAN NOT NULL DEFAULT TRUE, price_at_add INTEGER, "
                            "created_at DATETIME NOT NULL, "
                            "FOREIGN KEY(buyer_id) REFERENCES users(id), "
                            "FOREIGN KEY(product_id) REFERENCES products(id), "
                            "FOREIGN KEY(variant_id) REFERENCES product_variants(id), "
                            "CHECK(quantity > 0))"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO cart_items__variants "
                            "(id, buyer_id, product_id, quantity, is_selected, "
                            "price_at_add, created_at) "
                            "SELECT id, buyer_id, product_id, quantity, is_selected, "
                            "price_at_add, created_at "
                            "FROM cart_items"
                        )
                    )
                    connection.execute(text("DROP TABLE cart_items"))
                    connection.execute(
                        text("ALTER TABLE cart_items__variants RENAME TO cart_items")
                    )
                    connection.execute(
                        text("CREATE INDEX ix_cart_items_buyer_id ON cart_items (buyer_id)")
                    )
                    connection.execute(
                        text("CREATE INDEX ix_cart_items_product_id ON cart_items (product_id)")
                    )
                    connection.execute(
                        text("CREATE INDEX ix_cart_items_variant_id ON cart_items (variant_id)")
                    )
                    connection.execute(
                        text(
                            "CREATE UNIQUE INDEX uq_cart_items_buyer_product_base "
                            "ON cart_items (buyer_id, product_id) WHERE variant_id IS NULL"
                        )
                    )
                    connection.execute(
                        text(
                            "CREATE UNIQUE INDEX uq_cart_items_buyer_product_variant "
                            "ON cart_items (buyer_id, product_id, variant_id) "
                            "WHERE variant_id IS NOT NULL"
                        )
                    )
                else:
                    connection.execute(text("ALTER TABLE cart_items ADD COLUMN variant_id INTEGER"))
                    if connection.dialect.name != "sqlite":
                        for constraint in inspector.get_unique_constraints("cart_items"):
                            if set(constraint.get("column_names") or ()) == {
                                "buyer_id",
                                "product_id",
                            }:
                                name = constraint.get("name")
                                if name:
                                    connection.execute(
                                        text(f'ALTER TABLE cart_items DROP CONSTRAINT "{name}"')
                                    )
                    if {"buyer_id", "product_id"} <= columns:
                        connection.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS "
                                "uq_cart_items_buyer_product_base "
                                "ON cart_items (buyer_id, product_id) WHERE variant_id IS NULL"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS "
                                "uq_cart_items_buyer_product_variant "
                                "ON cart_items (buyer_id, product_id, variant_id) "
                                "WHERE variant_id IS NOT NULL"
                            )
                        )

        if "vouchers" in tables:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vouchers_code "
                    "ON vouchers (code)"
                )
            )

        if "categories" in tables:
            columns = {c["name"] for c in inspector.get_columns("categories")}
            if "is_active" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )

        if "order_items" in tables:
            columns = {c["name"] for c in inspector.get_columns("order_items")}
            if "variant_id" not in columns:
                connection.execute(text("ALTER TABLE order_items ADD COLUMN variant_id INTEGER"))
            for name, declaration in (
                ("product_name_snapshot", "VARCHAR(200)"),
                ("variant_name_snapshot", "VARCHAR(100)"),
                ("product_image_snapshot", "VARCHAR(2048)"),
                ("snapshot_initialized", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ):
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE order_items ADD COLUMN {name} {declaration}")
                    )
            if "products" in tables:
                connection.execute(
                    text(
                        "UPDATE order_items SET product_name_snapshot = "
                        "(SELECT name FROM products WHERE products.id = order_items.product_id) "
                        ", product_image_snapshot = "
                        "(SELECT image_url FROM products "
                        "WHERE products.id = order_items.product_id), "
                        "snapshot_initialized = TRUE "
                        "WHERE snapshot_initialized = FALSE "
                        "AND product_name_snapshot IS NULL"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE order_items SET snapshot_initialized = TRUE "
                        "WHERE snapshot_initialized = FALSE"
                    )
                )

        if "reviews" in tables:
            columns = {c["name"] for c in inspector.get_columns("reviews")}
            if "images_json" not in columns:
                connection.execute(text(
                    "ALTER TABLE reviews ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'"
                ))
                if "media_url" in columns:
                    # Copy known legacy references once; do not rewrite existing media lists.
                    rows = connection.execute(text(
                        "SELECT id, media_url FROM reviews WHERE media_url IS NOT NULL"
                    )).all()
                    for review_id, media_url in rows:
                        connection.execute(
                            text("UPDATE reviews SET images_json = :refs WHERE id = :id"),
                            {"refs": json.dumps([media_url]), "id": review_id},
                        )

        if "order_history" in tables:
            columns = {c["name"] for c in inspector.get_columns("order_history")}
            if "actor_role" not in columns:
                connection.execute(
                    text("ALTER TABLE order_history ADD COLUMN actor_role VARCHAR(20)")
                )

        if "orders" in tables:
            columns = {c["name"] for c in inspector.get_columns("orders")}
            for name in ("request_key", "request_hash"):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {name} VARCHAR(64)"))
            if "payment_status" not in columns:
                connection.execute(
                    text("ALTER TABLE orders ADD COLUMN payment_status VARCHAR(30) DEFAULT 'PAID'")
                )
            if "escrow_status" not in columns:
                connection.execute(
                    text("ALTER TABLE orders ADD COLUMN escrow_status VARCHAR(30) DEFAULT 'HELD'")
                )
            for name in ("tracking_number",):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {name} VARCHAR(100)"))
            if "payment_method" not in columns:
                # NULL marks a legacy order placed before payment tracking (US20 section 10).
                connection.execute(text("ALTER TABLE orders ADD COLUMN payment_method VARCHAR(10)"))
            for name in ("shipped_at", "delivered_at", "completed_at"):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {name} DATETIME"))
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_request_key "
                    "ON orders (request_key)"
                )
            )

        if "seller_orders" in tables:
            columns = {c["name"] for c in inspector.get_columns("seller_orders")}
            if "payment_status" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE seller_orders "
                        "ADD COLUMN payment_status VARCHAR(30) DEFAULT 'PAID'"
                    )
                )
            if "escrow_status" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE seller_orders "
                        "ADD COLUMN escrow_status VARCHAR(30) DEFAULT 'HELD'"
                    )
                )

            for name in ("tracking_number",):
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE seller_orders ADD COLUMN {name} VARCHAR(100)")
                    )
            for name in ("shipped_at", "delivered_at", "completed_at"):
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE seller_orders ADD COLUMN {name} DATETIME")
                    )

            subtotal_missing = "subtotal" not in columns
            for name in (
                "subtotal",
                "shop_discount",
                "platform_discount",
                "shipping_fee",
                "shipping_discount",
                "total_amount",
            ):
                if name not in columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE seller_orders "
                            f"ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
                        )
                    )
            if "pricing_policy_version" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE seller_orders "
                        "ADD COLUMN pricing_policy_version VARCHAR(20) NOT NULL DEFAULT 'LEGACY'"
                    )
                )

            for name in (
                "refunded_amount",
                "commission_rate_bps",
                "commission_amount",
                "seller_net_amount",
            ):
                if name not in columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE seller_orders ADD COLUMN {name} "
                            "INTEGER NOT NULL DEFAULT 0"
                        )
                    )
            if "settled_at" not in columns:
                connection.execute(text("ALTER TABLE seller_orders ADD COLUMN settled_at DATETIME"))

            if subtotal_missing and "order_items" in tables:
                connection.execute(
                    text(
                        "UPDATE seller_orders SET "
                        "subtotal = COALESCE(("
                        "    SELECT SUM(quantity * unit_price) "
                        "    FROM order_items "
                        "    WHERE order_items.seller_order_id = seller_orders.id"
                        "), 0), "
                        "total_amount = COALESCE(("
                        "    SELECT SUM(quantity * unit_price) "
                        "    FROM order_items "
                        "    WHERE order_items.seller_order_id = seller_orders.id"
                        "), 0) "
                        "WHERE subtotal = 0"
                    )
                )
        if {"orders", "seller_orders"} <= tables:
            _migrate_payment_states(connection)
        if "notifications" in tables:
            columns = {c["name"] for c in inspector.get_columns("notifications")}
            if "target_path" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE notifications ADD COLUMN "
                        "target_path VARCHAR(512) NOT NULL DEFAULT '/notifications'"
                    )
                )

        if "product_metadata" in tables:
            columns = {c["name"] for c in inspector.get_columns("product_metadata")}
            if "review_count" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE product_metadata ADD COLUMN "
                        "review_count INTEGER NOT NULL DEFAULT 0"
                    )
                )
            fks = inspector.get_foreign_keys("product_metadata")
            fk_tables = {fk.get("referred_table") for fk in fks}
            if "products" not in fk_tables or "categories" not in fk_tables:
                if connection.dialect.name == "sqlite":
                    # SQLite does not support ALTER TABLE ADD CONSTRAINT FOREIGN KEY.
                    # Table rebuild migration procedure:
                    # 1. Clean orphan references before enforcing foreign keys
                    connection.execute(
                        text(
                            "DELETE FROM product_metadata "
                            "WHERE product_id NOT IN (SELECT id FROM products)"
                        )
                    )
                    connection.execute(
                        text(
                            "UPDATE product_metadata SET category_id = NULL "
                            "WHERE category_id IS NOT NULL "
                            "AND category_id NOT IN (SELECT id FROM categories)"
                        )
                    )
                    # 2. Create replacement table with new foreign key constraints
                    connection.execute(
                        text(
                            "CREATE TABLE product_metadata__migration ("
                            "product_id INTEGER NOT NULL PRIMARY KEY, "
                            "category_id INTEGER, "
                            "rating FLOAT NOT NULL DEFAULT 0.0, "
                            "review_count INTEGER NOT NULL DEFAULT 0, "
                            "sales_count INTEGER NOT NULL DEFAULT 0, "
                            "created_at DATETIME NOT NULL, "
                            "FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE, "
                            "FOREIGN KEY(category_id) REFERENCES categories(id)"
                            ")"
                        )
                    )
                    # 3. Copy existing valid data
                    connection.execute(
                        text(
                            "INSERT INTO product_metadata__migration "
                            "(product_id, category_id, rating, review_count, "
                            "sales_count, created_at) "
                            "SELECT product_id, category_id, rating, review_count, "
                            "sales_count, created_at "
                            "FROM product_metadata"
                        )
                    )
                    # 4. Swap tables and recreate index
                    connection.execute(text("DROP TABLE product_metadata"))
                    connection.execute(
                        text("ALTER TABLE product_metadata__migration RENAME TO product_metadata")
                    )
                    connection.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_product_metadata_category_id "
                            "ON product_metadata (category_id)"
                        )
                    )

        # Backfill ProductMetadata for any existing products that lack metadata
        if "products" in tables and "product_metadata" in tables:
            columns = {c["name"] for c in inspector.get_columns("product_metadata")}
            if "is_moderated_deactivated" in columns:
                connection.execute(
                    text(
                        "INSERT INTO product_metadata "
                        "(product_id, category_id, rating, review_count, "
                        "sales_count, created_at, is_moderated_deactivated) "
                        "SELECT p.id, NULL, 0.0, 0, 0, CURRENT_TIMESTAMP, FALSE "
                        "FROM products p "
                        "WHERE p.id NOT IN (SELECT product_id FROM product_metadata)"
                    )
                )
            else:
                connection.execute(
                    text(
                        "INSERT INTO product_metadata "
                        "(product_id, category_id, rating, review_count, sales_count, created_at) "
                        "SELECT p.id, NULL, 0.0, 0, 0, CURRENT_TIMESTAMP "
                        "FROM products p "
                        "WHERE p.id NOT IN (SELECT product_id FROM product_metadata)"
                    )
                )

        if "product_metadata" in tables:
            columns = {c["name"] for c in inspector.get_columns("product_metadata")}
            if "is_moderated_deactivated" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE product_metadata ADD COLUMN is_moderated_deactivated "
                        "BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )

        if "return_requests" in tables:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_return_requests_seller_order_pending "
                    "ON return_requests(seller_order_id) WHERE status = 'PENDING'"
                )
            )

        if "return_disputes" in tables:
            columns = {c["name"] for c in inspector.get_columns("return_disputes")}
            if "return_request_id" not in columns:
                connection.execute(
                    text("ALTER TABLE return_disputes ADD COLUMN return_request_id INTEGER")
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_return_disputes_seller_order "
                    "ON return_disputes(seller_order_id)"
                )
            )

        if "vouchers" in tables:
            if connection.dialect.name == "sqlite":
                create_sql = connection.execute(
                    text("SELECT sql FROM sqlite_master WHERE type='table' AND name='vouchers'")
                ).scalar() or ""
                needs_rebuild = (
                    "ck_vouchers_scope_seller" not in create_sql
                    or "ck_vouchers_discount_value_bounds" not in create_sql
                    or "ck_vouchers_max_discount" not in create_sql
                )
                if needs_rebuild:
                    connection.execute(
                        text(
                            "CREATE TABLE vouchers__upgrade ("
                            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                            "code VARCHAR(32) NOT NULL, "
                            "scope VARCHAR(20) NOT NULL DEFAULT 'PLATFORM', "
                            "seller_id INTEGER, "
                            "discount_type VARCHAR(20) NOT NULL, "
                            "discount_value INTEGER NOT NULL DEFAULT 0, "
                            "max_discount INTEGER, "
                            "min_order_value INTEGER NOT NULL DEFAULT 0, "
                            "usage_limit INTEGER, "
                            "per_user_limit INTEGER, "
                            "used_count INTEGER NOT NULL DEFAULT 0, "
                            "starts_at DATETIME NOT NULL, "
                            "ends_at DATETIME NOT NULL, "
                            "is_active BOOLEAN NOT NULL DEFAULT 1, "
                            "created_at DATETIME NOT NULL, "
                            "updated_at DATETIME NOT NULL, "
                            "FOREIGN KEY(seller_id) REFERENCES users(id), "
                            "CONSTRAINT ck_vouchers_scope_seller CHECK ("
                            "  (scope = 'SHOP' AND seller_id IS NOT NULL) "
                            "  OR (scope = 'PLATFORM' AND seller_id IS NULL)"
                            "), "
                            "CONSTRAINT ck_vouchers_discount_type CHECK ("
                            "  discount_type IN ('FIXED_AMOUNT', 'PERCENTAGE', 'FREE_SHIPPING')"
                            "), "
                            "CONSTRAINT ck_vouchers_free_shipping_platform CHECK ("
                            "  (discount_type != 'FREE_SHIPPING') OR (scope = 'PLATFORM')"
                            "), "
                            "CONSTRAINT ck_vouchers_discount_value_bounds CHECK ("
                            "  (discount_type = 'FIXED_AMOUNT' AND discount_value > 0) "
                            "  OR (discount_type = 'PERCENTAGE' AND discount_value >= 1 "
                            "AND discount_value <= 10000) "
                            "  OR (discount_type = 'FREE_SHIPPING' AND discount_value = 0)"
                            "), "
                            "CONSTRAINT ck_vouchers_max_discount CHECK ("
                            "  (max_discount IS NULL OR max_discount > 0) "
                            "  AND ((discount_type IN ('PERCENTAGE', 'FREE_SHIPPING')) "
                            "OR max_discount IS NULL)"
                            "), "
                            "CONSTRAINT ck_vouchers_limits CHECK ("
                            "  (usage_limit IS NULL OR usage_limit > 0) "
                            "  AND (per_user_limit IS NULL OR per_user_limit > 0)"
                            "), "
                            "CONSTRAINT ck_vouchers_dates CHECK ("
                            "  starts_at < ends_at"
                            "), "
                            "CONSTRAINT ck_vouchers_used_count CHECK ("
                            "  used_count >= 0 AND "
                            "(usage_limit IS NULL OR used_count <= usage_limit)"
                            "), "
                            "CONSTRAINT ck_vouchers_min_order_value CHECK ("
                            "  min_order_value >= 0"
                            ")"
                            ")"
                        )
                    )
                    v_cols = [c["name"] for c in inspector.get_columns("vouchers")]
                    cols_str = ", ".join(v_cols)
                    connection.execute(
                        text(
                            f"INSERT INTO vouchers__upgrade ({cols_str}) "
                            f"SELECT {cols_str} FROM vouchers"
                        )
                    )
                    connection.execute(text("DROP TABLE vouchers"))
                    connection.execute(text("ALTER TABLE vouchers__upgrade RENAME TO vouchers"))
                    connection.execute(
                        text("CREATE UNIQUE INDEX ix_vouchers_code ON vouchers (code)")
                    )



def _migrate_payment_states(connection: Connection) -> None:
    """US20 section 10 value mapping; every statement is a no-op on a second run."""
    for table in ("orders", "seller_orders"):
        connection.execute(
            text(f"UPDATE {table} SET escrow_status = 'VOIDED' WHERE escrow_status = 'REFUNDED'")
        )
    # Cancellations on main left escrow HELD; a cancelled or returned order is never settled.
    connection.execute(
        text(
            "UPDATE seller_orders SET escrow_status = 'VOIDED' "
            "WHERE status IN ('CANCELLED', 'RETURNED_REFUNDED') AND escrow_status != 'VOIDED'"
        )
    )
    connection.execute(
        text(
            "UPDATE orders SET payment_status = 'PAID' "
            "WHERE payment_status = 'PARTIALLY_REFUNDED'"
        )
    )
    # Recompute the display summary of section 2.3 from the seller orders.
    connection.execute(
        text(
            "UPDATE orders SET escrow_status = CASE "
            "WHEN EXISTS (SELECT 1 FROM seller_orders s WHERE s.order_id = orders.id "
            "  AND s.escrow_status = 'PAUSED') THEN 'PAUSED' "
            "WHEN NOT EXISTS (SELECT 1 FROM seller_orders s WHERE s.order_id = orders.id "
            "  AND s.escrow_status != 'RELEASED') THEN 'RELEASED' "
            "WHEN NOT EXISTS (SELECT 1 FROM seller_orders s WHERE s.order_id = orders.id "
            "  AND s.escrow_status != 'VOIDED') THEN 'VOIDED' "
            "WHEN EXISTS (SELECT 1 FROM seller_orders s WHERE s.order_id = orders.id "
            "  AND s.escrow_status = 'HELD') THEN 'HELD' "
            "ELSE 'PARTIALLY_SETTLED' END "
            "WHERE EXISTS (SELECT 1 FROM seller_orders s WHERE s.order_id = orders.id)"
        )
    )


def init_db() -> None:
    """Register application models, create missing tables, and run migrations."""
    import src.models  # noqa: F401

    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            # Serialize first-run DDL as well as data seeding across processes.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        SQLModel.metadata.create_all(connection)
        migrate_db(connection)


def check_db_connection() -> bool:
    """Return whether the configured database accepts a simple query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_db() -> Generator[Session, None, None]:
    """Preserve the session dependency used by existing callers."""
    yield from get_session()


SessionDep = Annotated[Session, Depends(get_session)]


if __name__ == "__main__":
    init_db()
    print("Database initialization completed successfully.")
