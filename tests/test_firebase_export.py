from pathlib import Path

from scripts.export_frontend import PAGE_FILES, PUBLIC_ROOT, export_frontend


def test_export_contains_only_allowlisted_frontend_files():
    files = export_frontend()

    assert set(PAGE_FILES).issubset({path.name for path in files})
    assert Path("404.html") in files
    assert all(path.parts[0] in {"static", "404.html", *PAGE_FILES} for path in files)
    assert not any(path.suffix in {".py", ".db", ".env"} for path in files)
    assert (PUBLIC_ROOT / "static" / "products.js").is_file()
