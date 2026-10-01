"""Tests for database initialization and session management."""

from src.database import check_db_connection, get_db


def test_check_db_connection() -> None:
    """Test check_db_connection returns True for active database."""
    assert check_db_connection() is True


def test_get_db() -> None:
    """Test get_db generator yields active database session."""
    db_gen = get_db()
    session = next(db_gen)
    assert session is not None
    db_gen.close()
