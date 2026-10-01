"""Application entrypoint and FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import __version__
from src.api.health import router as health_router
from src.api.router import api_router
from src.config import get_settings
from src.database import init_db

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mini_marketplace")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application lifespan events: startup and shutdown."""
    logger.info("Starting up %s v%s...", app.title, app.version)
    # Ensure database schema is initialized dynamically at runtime
    init_db()
    yield
    logger.info("Shutting down %s...", app.title)


def create_app() -> FastAPI:
    """Factory function to build and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="Mini Marketplace runnable application skeleton for Sprint 2 walking skeleton.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    origins = (
        settings.CORS_ORIGINS
        if isinstance(settings.CORS_ORIGINS, list)
        else [settings.CORS_ORIGINS]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root route - provides informative landing response
    @app.get("/", tags=["Root"])
    def read_root() -> Dict[str, str]:
        """Root endpoint confirming application is live and accessible."""
        return {
            "app": settings.APP_NAME,
            "version": __version__,
            "status": "running",
            "environment": settings.APP_ENV,
            "docs": "/docs",
            "health": "/health",
        }

    # Top-level health check (for convenience and container orchestrators)
    app.include_router(health_router)

    # Include versioned API router
    app.include_router(api_router)

    return app


app = create_app()


def start() -> None:
    """Start application server using configured host and port."""
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    start()
