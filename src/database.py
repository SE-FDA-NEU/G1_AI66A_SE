"""Database engine, session management, and runtime initialization."""

import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.models.base import Base

logger = logging.getLogger(__name__)

settings = get_settings()

# Engine creation: handle SQLite specific threading configuration
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables registered with Base at runtime.

    This ensures that from a clean checkout, the database is generated dynamically
    without committing runtime database files to Git.
    """
    logger.info("Initializing database schema at runtime using %s", settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")


def check_db_connection() -> bool:
    """Verify active database connectivity with a lightweight ping."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        return False


if __name__ == "__main__":
    init_db()
    print("Database initialization completed successfully.")
