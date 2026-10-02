from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from src.config import get_settings


settings = get_settings()
DATABASE_URL = settings.DATABASE_URL

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]