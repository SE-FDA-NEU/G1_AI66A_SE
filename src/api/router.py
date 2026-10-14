"""Main API router combining all v1 route endpoints."""

from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.products import router as products_router

api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(products_router)
