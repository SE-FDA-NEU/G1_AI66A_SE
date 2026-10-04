"""Pytest fixtures and configuration."""

import os
from typing import Generator

import pytest
from sqlmodel import Session
from starlette.testclient import TestClient

# Ensure test environment uses an in-memory SQLite database
# to keep tests clean and fast.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from src.database import engine, init_db
from src.main import create_app
from src.models.user import User


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize database tables and a reusable test seller."""
    init_db()

    with Session(engine) as session:
        seller = session.get(User, 1)

        if seller is None:
            session.add(
                User(
                    id=1,
                    name="Test Seller",
                    email="test.seller@marketplace.local",
                    role="seller",
                )
            )
            session.commit()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client fixture configured with in-memory database."""
    app = create_app()

    with TestClient(app) as test_client:
        yield test_client
