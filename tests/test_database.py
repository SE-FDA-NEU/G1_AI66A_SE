"""Tests for database initialization and session management."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

import src.database as database
from src.database import check_db_connection, get_db
from src.seed import build_products

PROJECT_ROOT = Path(__file__).resolve().parents[1]

API_TOTAL_SCRIPT = (
    "from fastapi.testclient import TestClient\n"
    "from src.main import app\n"
    "print(TestClient(app).get('/api/v1/products').json()['meta']['total'])\n"
)


def run_python(args: list[str], db_path: Path) -> str:
    """Run a project command against a SQLite file, as a developer would from a shell."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "DEBUG": "false"}
    result = subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_check_db_connection() -> None:
    """Test check_db_connection returns True for active database."""
    assert check_db_connection() is True


def test_get_db() -> None:
    """Test get_db generator yields active database session."""
    db_gen = get_db()
    session = next(db_gen)
    assert session is not None
    db_gen.close()


def test_init_and_seed_commands_on_sqlite_file(tmp_path: Path) -> None:
    """`python -m src.database` and `python -m src.seed` work on a real database file."""
    db_path = tmp_path / "catalog.db"

    run_python(["-m", "src.database"], db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone() == (0,)

    expected = len(build_products())
    assert f"Added: {expected} products" in run_python(["-m", "src.seed"], db_path)
    assert "Added: 0 products" in run_python(["-m", "src.seed"], db_path)
    assert run_python(["-c", API_TOTAL_SCRIPT], db_path).strip() == str(expected)

def test_check_db_connection_handles_database_error(monkeypatch) -> None:
    """Database connection failures should be handled without crashing."""

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("simulated database connection failure")

    monkeypatch.setattr(database, "engine", BrokenEngine())

    assert database.check_db_connection() is False


def test_legacy_database_migration_adds_password_hash(tmp_path: Path) -> None:
    """Databases created before password_hash was added are safely migrated on init/seed."""
    db_path = tmp_path / "legacy.db"

    # Simulate an existing database created before the PR (missing password_hash column)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                role VARCHAR(20) NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users (name, email, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("Legacy Seller", "demo.seller@marketplace.local", "seller", "2026-10-01 00:00:00"),
        )
        connection.commit()

        col_names = [col[1] for col in connection.execute("PRAGMA table_info(users)").fetchall()]
        assert "password_hash" not in col_names

    output = run_python(["-m", "src.seed"], db_path)
    assert "Added: 45 products" in output

    with closing(sqlite3.connect(db_path)) as connection:
        col_names = [col[1] for col in connection.execute("PRAGMA table_info(users)").fetchall()]
        assert "password_hash" in col_names
        seller = connection.execute(
            "SELECT email, password_hash, role FROM users "
            "WHERE email = 'demo.seller@marketplace.local'"
        ).fetchone()
        assert seller is not None
        assert seller[0] == "demo.seller@marketplace.local"
        assert seller[1].startswith("scrypt$")
        assert seller[2] == "seller"


def test_legacy_database_migration_adds_product_metadata_foreign_keys(tmp_path: Path) -> None:
    """
    Databases with pre-existing product_metadata lacking foreign keys are safely migrated and
    foreign keys enforced.
    """
    db_path = tmp_path / "legacy_metadata.db"

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                role VARCHAR(20) NOT NULL,
                password_hash VARCHAR(255) NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(100) NOT NULL UNIQUE,
                parent_id INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(20) NOT NULL UNIQUE,
                seller_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                description VARCHAR(500) NOT NULL,
                price INTEGER NOT NULL,
                stock_quantity INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0,
                image_url VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        # Create pre-existing product_metadata without foreign key constraints (like
        # before PR #102 fix)
        connection.execute(
            """
            CREATE TABLE product_metadata (
                product_id INTEGER NOT NULL PRIMARY KEY,
                category_id INTEGER,
                rating FLOAT NOT NULL DEFAULT 0.0,
                sales_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL
            )
            """
        )
        # Insert a user, category, and product
        connection.execute(
            'INSERT INTO users (id, name, email, role, created_at) '
            "VALUES (1, 'Seller', 's@test.local', 'seller', '2026-10-01')"
        )
        connection.execute(
            "INSERT INTO categories (id, name, slug) VALUES (1, 'Peripherals', 'peripherals')"
        )
        connection.execute(
            'INSERT INTO products (id, code, seller_id, '
            'name, description, price, stock_quantity, image_url) '
            "VALUES (1, 'P-LEGACY-1', 1, 'Legacy Mouse', 'Desc', 100000, 10, 'http://test/mouse.jpg')"
        )
        connection.execute(
            'INSERT INTO products (id, code, seller_id, '
            'name, description, price, stock_quantity, image_url) '
            "VALUES (2, 'P-LEGACY-2', 1, 'Legacy Keyboard', 'Desc', 200000, 5, 'http://test/keyb.jpg')"
        )
        # Metadata for product 1
        connection.execute(
            'INSERT INTO product_metadata (product_id, '
            'category_id, rating, sales_count, created_at) '
            "VALUES (1, 1, 4.2, 35, '2026-10-01 10:00:00')"
        )
        # Orphan metadata row (product_id 999 does not exist)
        connection.execute(
            'INSERT INTO product_metadata (product_id, '
            'category_id, rating, sales_count, created_at) '
            "VALUES (999, 1, 3.0, 10, '2026-10-01 10:00:00')"
        )
        connection.commit()

        # Before migration, no foreign keys on product_metadata
        fks_before = connection.execute("PRAGMA foreign_key_list(product_metadata)").fetchall()
        assert len(fks_before) == 0

    # Run database migration
    run_python(["-m", "src.database"], db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        fks_after = connection.execute("PRAGMA foreign_key_list(product_metadata)").fetchall()
        # Should have foreign keys referencing products and categories
        referred_tables = {fk[2] for fk in fks_after}
        assert "products" in referred_tables
        assert "categories" in referred_tables

        # Check orphan row was purged
        orphan = connection.execute(
            "SELECT * FROM product_metadata WHERE product_id = 999"
        ).fetchone()
        assert orphan is None

        # Check existing valid data was preserved
        valid = connection.execute(
            'SELECT product_id, category_id, rating, '
            'sales_count FROM product_metadata WHERE product_id = 1'
        ).fetchone()
        assert valid == (1, 1, 4.2, 35)

        # Check existing product 2 without metadata was backfilled with defaults
        p2_meta = connection.execute(
            'SELECT product_id, category_id, rating, '
            'sales_count FROM product_metadata WHERE product_id = 2'
        ).fetchone()
        assert p2_meta is not None
        assert p2_meta[0] == 2
        assert p2_meta[2] == 0.0
        assert p2_meta[3] == 0

        metadata_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'product_metadata'"
        ).fetchone()[0]
        assert "ck_product_metadata_rating_range" in metadata_sql
        assert "ck_product_metadata_review_count_nonnegative" in metadata_sql
        assert "ck_product_metadata_sales_count_nonnegative" in metadata_sql

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                'UPDATE product_metadata SET sales_count = -1 WHERE product_id = 1'
            )
            connection.commit()

        # Foreign key constraint must now be enforced by SQLite
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                'INSERT INTO product_metadata (product_id, '
                'category_id, rating, sales_count, created_at) '
                "VALUES (8888, 1, 0.0, 0, '2026-10-23 00:00:00')"
            )
            connection.commit()

