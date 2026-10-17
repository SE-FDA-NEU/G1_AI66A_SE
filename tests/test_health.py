"""Tests for health and root endpoints."""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """Test root endpoint GET / returns 200 and expected metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert data["status"] == "running"
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


def test_health_endpoint(client: TestClient) -> None:
    """Test health endpoint GET /health returns 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data
    assert "environment" in data


def test_browser_root_enters_catalog_without_changing_json_status(client: TestClient) -> None:
    """P0 users can start at /; API clients keep the original status contract."""
    browser = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert browser.status_code == 307
    assert browser.headers["location"] == "/products"
    page = client.get("/", headers={"Accept": "text/html"})
    assert page.status_code == 200
    assert page.url.path == "/products"
    assert "text/html" in page.headers["content-type"]
    metadata = client.get("/", headers={"Accept": "application/json"})
    assert metadata.status_code == 200
    assert metadata.json()["status"] == "running"
