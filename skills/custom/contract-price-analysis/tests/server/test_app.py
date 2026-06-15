"""Tests for the FastAPI app scaffold (health endpoint, CORS)."""

from fastapi.testclient import TestClient

from scripts.server.app import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/cpa/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_available():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/cpa/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "Contract Price Analysis API"


def test_cors_header_present():
    app = create_app()
    client = TestClient(app)
    resp = client.options(
        "/api/cpa/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS middleware should acknowledge the preflight.
    assert resp.status_code in (200, 204)
