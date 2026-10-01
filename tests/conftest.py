"""Pytest fixtures and configuration."""

import os
from typing import Generator

import pytest
from starlette.testclient import TestClient

# Ensure test environment uses an in-memory SQLite database to keep tests clean and fast
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from src.database import init_db
from src.main import create_app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize database tables for the test session."""
    init_db()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client fixture configured with in-memory database."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
