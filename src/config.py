"""Application configuration management supporting both pydantic-settings and pydantic fallback."""

import json
import os
from functools import lru_cache
from typing import List, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Automatically load .env if present
load_dotenv()

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        """Configuration settings loaded from environment variables or .env file."""

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            case_sensitive=False,
        )

        APP_NAME: str = Field(default="Mini Marketplace", description="Name of the application")
        APP_ENV: str = Field(
            default="development", description="Environment: development, test, production"
        )
        DEBUG: bool = Field(default=True, description="Debug mode flag")
        APP_HOST: str = Field(default="127.0.0.1", description="Host address for binding")
        APP_PORT: int = Field(default=8000, description="Port number for listening")
        DATABASE_URL: str = Field(
            default="sqlite:///./marketplace.db",
            description="Database connection URL (defaults to runtime SQLite database)",
        )
        SECRET_KEY: str = Field(
            default="dev-secret-key-do-not-use-in-production-environment",
            description="Application secret key",
        )
        JWT_EXPIRATION_MINUTES: int = Field(default=60, ge=1)
        CORS_ORIGINS: Union[List[str], str] = Field(
            default=["*"],
            description="Allowed CORS origins list or string",
        )

        @field_validator("DATABASE_URL")
        @classmethod
        def validate_database_url(cls, v: str) -> str:
            """Validate database URL is not empty."""
            if not v or not v.strip():
                raise ValueError(
                    "DATABASE_URL must not be empty. Please specify a valid database URL."
                )
            return v.strip()

        @field_validator("CORS_ORIGINS", mode="before")
        @classmethod
        def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
            """Parse CORS origins if provided as a JSON string or comma-separated string."""
            if isinstance(v, str):
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    try:
                        return json.loads(v)
                    except json.JSONDecodeError:
                        pass
                return [origin.strip() for origin in v.split(",") if origin.strip()]
            return v

except ImportError:
    # Graceful fallback to pure Pydantic v2 BaseModel reading from os.environ
    class Settings(BaseModel):  # type: ignore[no-redef]
        """Configuration settings fallback using standard environment variables."""

        APP_NAME: str = Field(
            default_factory=lambda: os.getenv("APP_NAME", "Mini Marketplace"),
            description="Name of the application",
        )
        APP_ENV: str = Field(
            default_factory=lambda: os.getenv("APP_ENV", "development"),
            description="Environment",
        )
        DEBUG: bool = Field(
            default_factory=lambda: os.getenv("DEBUG", "true").lower() in ("true", "1", "yes"),
            description="Debug mode flag",
        )
        APP_HOST: str = Field(
            default_factory=lambda: os.getenv("APP_HOST", "127.0.0.1"),
            description="Host address",
        )
        APP_PORT: int = Field(
            default_factory=lambda: int(os.getenv("APP_PORT", "8000")),
            description="Port number",
        )
        DATABASE_URL: str = Field(
            default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./marketplace.db"),
            description="Database URL",
        )
        SECRET_KEY: str = Field(
            default_factory=lambda: os.getenv(
                "SECRET_KEY", "dev-secret-key-do-not-use-in-production-environment"
            ),
            description="Secret key",
        )
        JWT_EXPIRATION_MINUTES: int = Field(
            default_factory=lambda: int(os.getenv("JWT_EXPIRATION_MINUTES", "60")),
            ge=1,
        )
        CORS_ORIGINS: Union[List[str], str] = Field(
            default_factory=lambda: os.getenv("CORS_ORIGINS", "*"),
            description="Allowed CORS origins",
        )

        @field_validator("DATABASE_URL")
        @classmethod
        def validate_database_url(cls, v: str) -> str:
            """Validate database URL is not empty."""
            if not v or not v.strip():
                raise ValueError(
                    "DATABASE_URL must not be empty. Please specify a valid database URL."
                )
            return v.strip()

        @field_validator("CORS_ORIGINS", mode="before")
        @classmethod
        def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
            """Parse CORS origins if provided as a JSON string or comma-separated string."""
            if isinstance(v, str):
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    try:
                        return json.loads(v)
                    except json.JSONDecodeError:
                        pass
                return [origin.strip() for origin in v.split(",") if origin.strip()]
            return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
