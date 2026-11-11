from fastapi.testclient import TestClient

from src.main import create_app


def test_demo_cors_preflight_allows_hosting_and_rejects_other_origin(monkeypatch):
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://demo.web.app"])
    client = TestClient(create_app())
    headers = {
        "Origin": "https://demo.web.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
    }
    allowed = client.options("/api/v1/orders", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://demo.web.app"
    for name in ("authorization", "content-type", "idempotency-key"):
        assert name in allowed.headers["access-control-allow-headers"].lower()
    headers["Origin"] = "https://untrusted.example"
    rejected = client.options("/api/v1/orders", headers=headers)
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
