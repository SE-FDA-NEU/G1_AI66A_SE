from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.config import get_settings

settings = get_settings()
DATABASE_URL = settings.DATABASE_URL

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

database_url = make_url(DATABASE_URL)
pool_options = (
    {"poolclass": StaticPool}
    if database_url.get_backend_name() == "sqlite"
    and database_url.database in (None, "", ":memory:")
    else {}
)

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


def init_db() -> None:
    """Register application models and create missing tables."""
    import src.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


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
