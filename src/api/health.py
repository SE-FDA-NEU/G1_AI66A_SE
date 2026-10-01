"""Health check and smoke verification endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from src import __version__
from src.config import get_settings
from src.database import check_db_connection

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Schema for health status response."""

    status: str
    version: str
    environment: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return application health, version, environment, and database status.

    Used by smoke tests and deployment readiness probes.
    """
    settings = get_settings()
    db_connected = check_db_connection()
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.APP_ENV,
        database="connected" if db_connected else "disconnected",
    )
