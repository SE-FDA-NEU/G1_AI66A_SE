"""Health check and smoke verification endpoints."""

from fastapi import APIRouter, Response, status
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


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health_check(response: Response) -> HealthResponse:
    """Return application health, version, environment, and database status.

    Used by smoke tests and deployment readiness probes.
    """
    settings = get_settings()
    db_connected = check_db_connection()
    if not db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_connected else "unavailable",
        version=__version__,
        environment=settings.APP_ENV,
        database="connected" if db_connected else "disconnected",
    )
