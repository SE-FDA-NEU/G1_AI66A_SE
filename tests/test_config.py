"""Tests for application configuration management."""

import pytest

from src.config import Settings, get_settings


def test_get_settings() -> None:
    """Test get_settings returns Settings instance with defaults."""
    settings = get_settings()
    assert settings.APP_NAME == "Mini Marketplace"
    assert settings.APP_HOST == "127.0.0.1"
    assert settings.APP_PORT == 8000


def test_validate_database_url() -> None:
    """Test validate_database_url rejects empty string."""
    with pytest.raises(ValueError, match="DATABASE_URL must not be empty"):
        Settings(DATABASE_URL="")


def test_parse_cors_origins() -> None:
    """Test parsing CORS origins string and json formats."""
    settings = Settings(CORS_ORIGINS="http://localhost:3000,http://example.com")
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://example.com"]

    settings_json = Settings(CORS_ORIGINS='["http://localhost:8000"]')
    assert settings_json.CORS_ORIGINS == ["http://localhost:8000"]
