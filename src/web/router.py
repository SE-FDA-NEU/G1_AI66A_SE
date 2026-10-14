"""Web routes serving the browser UI pages."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

WEB_DIR = Path(__file__).resolve().parent
PAGES_DIR = WEB_DIR / "pages"
STATIC_DIR = WEB_DIR / "static"

router = APIRouter(tags=["Web"])


@router.get("/products", response_class=FileResponse, include_in_schema=False)
def products_page() -> FileResponse:
    """Serve the product catalog page (US01); its script loads data from the API."""
    return FileResponse(PAGES_DIR / "products.html")


@router.get("/login", response_class=FileResponse, include_in_schema=False)
def login_page() -> FileResponse:
    """Serve the login page."""
    return FileResponse(PAGES_DIR / "login.html")
