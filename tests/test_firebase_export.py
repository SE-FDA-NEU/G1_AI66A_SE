from pathlib import Path

import pytest

from scripts.export_frontend import PAGE_FILES, PUBLIC_ROOT, export_frontend


def test_export_contains_only_allowlisted_frontend_files():
    files = export_frontend()

    assert set(PAGE_FILES).issubset({path.name for path in files})
    assert Path("404.html") in files
    assert all(path.parts[0] in {"static", "404.html", *PAGE_FILES} for path in files)
    assert not any(path.suffix in {".py", ".db", ".env"} for path in files)
    assert (PUBLIC_ROOT / "static" / "products.js").is_file()
    assert not (PUBLIC_ROOT / "static" / "uploads").exists()


def test_export_writes_one_https_api_origin(monkeypatch):
    monkeypatch.setenv("MARKETPLACE_API_ORIGIN", "https://example.trycloudflare.com/")
    export_frontend()
    assert '"https://example.trycloudflare.com"' in (
        PUBLIC_ROOT / "static" / "backend-config.js"
    ).read_text()


@pytest.mark.parametrize("origin", ["http://example.com", "https://example.com/path", "https://u:p@example.com"])
def test_export_rejects_invalid_hosted_origin(monkeypatch, origin):
    monkeypatch.setenv("MARKETPLACE_API_ORIGIN", origin)
    with pytest.raises(ValueError):
        export_frontend()
