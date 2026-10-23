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

        if "orders" in tables:
            columns = {c["name"] for c in inspector.get_columns("orders")}
            for name in ("request_key", "request_hash"):
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE orders ADD COLUMN {name} VARCHAR(64)"))
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_request_key "
                    "ON orders (request_key)"
                )
            )

        if "product_metadata" in tables:
            fks = inspector.get_foreign_keys("product_metadata")
            fk_tables = {fk.get("referred_table") for fk in fks}
            if "products" not in fk_tables or "categories" not in fk_tables:
                if connection.dialect.name == "sqlite":
                    # SQLite does not support ALTER TABLE ADD CONSTRAINT FOREIGN KEY.
                    # Table rebuild migration procedure:
                    # 1. Clean orphan references before enforcing foreign keys
                    connection.execute(
                        text("DELETE FROM product_metadata WHERE product_id NOT IN (SELECT id FROM products)")
                    )
                    connection.execute(
                        text(
                            "UPDATE product_metadata SET category_id = NULL "
                            "WHERE category_id IS NOT NULL AND category_id NOT IN (SELECT id FROM categories)"
                        )
                    )
                    # 2. Create replacement table with new foreign key constraints
                    connection.execute(
                        text(
                            "CREATE TABLE product_metadata__migration ("
                            "product_id INTEGER NOT NULL PRIMARY KEY, "
                            "category_id INTEGER, "
                            "rating FLOAT NOT NULL DEFAULT 0.0, "
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
                            "INSERT INTO product_metadata__migration (product_id, category_id, rating, sales_count, created_at) "
                            "SELECT product_id, category_id, rating, sales_count, created_at FROM product_metadata"
                        )
                    )
                    # 4. Swap tables and recreate index
                    connection.execute(text("DROP TABLE product_metadata"))
                    connection.execute(text("ALTER TABLE product_metadata__migration RENAME TO product_metadata"))
                    connection.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_product_metadata_category_id "
                            "ON product_metadata (category_id)"
                        )
                    )

        # Backfill ProductMetadata for any existing products that lack metadata
        if "products" in tables and "product_metadata" in tables:
            connection.execute(
                text(
                    "INSERT INTO product_metadata (product_id, category_id, rating, sales_count, created_at) "
                    "SELECT p.id, NULL, 0.0, 0, CURRENT_TIMESTAMP "
                    "FROM products p "
                    "WHERE p.id NOT IN (SELECT product_id FROM product_metadata)"
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
