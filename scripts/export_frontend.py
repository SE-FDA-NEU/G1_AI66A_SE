"""Export only the browser frontend into Firebase Hosting's public directory."""

from __future__ import annotations

import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "web"
PUBLIC_ROOT = REPOSITORY_ROOT / "public"

PAGE_FILES = (
    "admin-portal.html",
    "cart.html",
    "checkout.html",
    "confirmation.html",
    "login.html",
    "notifications.html",
    "order.html",
    "product-detail.html",
    "products.html",
    "seller-analytics.html",
    "seller-orders.html",
    "seller-product-new.html",
    "seller-products.html",
    "seller-vouchers.html",
)

NOT_FOUND_PAGE = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Page not found | Mini Marketplace</title>
    <link rel="stylesheet" href="/static/base.css">
  </head>
  <body><main class="page-shell"><h1>Page not found</h1>
    <p>The page you requested does not exist.</p><p><a href="/products">Return to products</a></p>
  </main></body>
</html>
"""


def export_frontend() -> list[Path]:
    """Create a clean, deterministic Hosting directory and return its files."""
    if PUBLIC_ROOT.exists():
        shutil.rmtree(PUBLIC_ROOT)
    PUBLIC_ROOT.mkdir()

    for page_name in PAGE_FILES:
        source = SOURCE_ROOT / "pages" / page_name
        if not source.is_file():
            raise FileNotFoundError(f"Frontend page is missing: {source}")
        shutil.copy2(source, PUBLIC_ROOT / page_name)

    shutil.copytree(SOURCE_ROOT / "static", PUBLIC_ROOT / "static")
    (PUBLIC_ROOT / "404.html").write_text(NOT_FOUND_PAGE, encoding="utf-8")
    return sorted(path.relative_to(PUBLIC_ROOT) for path in PUBLIC_ROOT.rglob("*"))


if __name__ == "__main__":
    files = export_frontend()
    print(f"Exported {len(files)} frontend files to {PUBLIC_ROOT}")
