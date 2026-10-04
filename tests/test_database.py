"""Tests for database initialization and session management."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

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
