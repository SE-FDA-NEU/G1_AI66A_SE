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


@router.get("/products/{product_code}", response_class=FileResponse, include_in_schema=False)
def product_detail_page(product_code: str) -> FileResponse:
    """Serve the product detail page; its script loads the requested product."""
    del product_code
    return FileResponse(PAGES_DIR / "product-detail.html")


@router.get("/cart", response_class=FileResponse, include_in_schema=False)
def cart_page() -> FileResponse:
    """Serve the shopping cart page (US03); its script loads the cart from the API."""
    return FileResponse(PAGES_DIR / "cart.html")


@router.get("/login", response_class=FileResponse, include_in_schema=False)
def login_page() -> FileResponse:
    """Serve the login page."""
    return FileResponse(PAGES_DIR / "login.html")
