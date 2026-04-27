"""Tests for model validation functionality."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.extensions.settings.routers import router


def test_validate_models_empty_list():
    """Test validation with empty model list."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post("/api/extensions/models/validate", json={"models": []})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_validate_models_single_valid():
    """Test validation with a single valid model."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/api/extensions/models/validate",
        json={"models": ["gpt-4"]},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["name"] == "gpt-4"
    assert "status" in results[0]


def test_validate_models_multiple():
    """Test validation with multiple models."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/api/extensions/models/validate",
        json={"models": ["gpt-4", "gpt-3.5-turbo", "nonexistent-model"]},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert results[0]["name"] == "gpt-4"
    assert results[1]["name"] == "gpt-3.5-turbo"
    assert results[2]["name"] == "nonexistent-model"
    # All results should have status field
    for result in results:
        assert "status" in result
        assert "details" in result