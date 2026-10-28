"""Local header identity and EAI JWT/permission resolution."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from jose import jwt

from app import deps
from app.config import settings

from .conftest import headers

PREFIX = "/api/workflow"


def test_local_identity_is_exposed(client: TestClient) -> None:
    response = client.get(
        f"{PREFIX}/meta/me",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handler"] == "u1001"
    assert body["name"] == "Zhang San"
    assert body["auth_mode"] == "local"
    assert body["permissions"] == []


def test_eai_mode_requires_a_token(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "auth_mode", "eai")
    deps._CACHE.clear()
    response = client.get(f"{PREFIX}/meta/me", headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]
    # Read-only routes must not bypass authentication either.
    assert client.get(f"{PREFIX}/forms", headers=headers()).status_code == 401
    assert client.get(f"{PREFIX}/meta/enums", headers=headers()).status_code == 401


def test_eai_mode_rejects_invalid_token(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "auth_mode", "eai")
    deps._CACHE.clear()
    response = client.get(
        f"{PREFIX}/meta/me",
        headers={**headers(), "Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


def test_eai_mode_resolves_identity_and_permissions(client: TestClient, monkeypatch: Any) -> None:
    calls: list[str] = []

    async def fake_me(token: str) -> dict[str, Any]:
        calls.append(token)
        return {
            "identity": {
                "user_id": "u2001",
                "username": "EAI User",
                "role_code": "manager",
                "dept_id": "d01",
            },
            "permissions": ["workflow.definition.read", "workflow.task.approve"],
            "is_admin": False,
        }

    monkeypatch.setattr(settings, "auth_mode", "eai")
    monkeypatch.setattr(deps, "_fetch_eai_me", fake_me)
    deps._CACHE.clear()

    token = jwt.encode(
        {"sub": "u2001", "role_code": "manager", "tenant_id": "T1"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get(
        f"{PREFIX}/meta/me",
        headers={**headers("u9999", "Spoofed", "employee", "d99"), "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handler"] == "u2001"
    assert body["name"] == "EAI User"
    assert body["roles"] == ["manager"]
    assert body["dept"] == "d01"
    assert body["permissions"] == ["workflow.definition.read", "workflow.task.approve"]
    assert body["tenant_id"] == "T1"
    assert body["auth_mode"] == "eai"
    assert calls == [token]
    assert (
        client.get(
            f"{PREFIX}/forms",
            headers={**headers(), "Authorization": f"Bearer {token}"},
        ).status_code
        == 200
    )

    # The identity is cached for the configured TTL, so a second request must
    # not hit the permission center again.
    second = client.get(
        f"{PREFIX}/meta/me",
        headers={**headers(), "Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 200, second.text
    assert calls == [token]


def test_internal_bff_token_can_impersonate(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "auth_mode", "eai")
    monkeypatch.setattr(settings, "internal_token", "test-internal-token")
    response = client.get(
        f"{PREFIX}/meta/me",
        headers={
            **headers("demo-manager", "Demo Manager", "regional_manager", "d01"),
            "X-Workflow-Internal-Token": "test-internal-token",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handler"] == "demo-manager"
    assert body["roles"] == ["regional_manager"]

    denied = client.get(
        f"{PREFIX}/meta/me",
        headers={**headers(), "X-Workflow-Internal-Token": "wrong"},
    )
    assert denied.status_code == 401


def test_eai_cookie_is_accepted(client: TestClient, monkeypatch: Any) -> None:
    async def fake_me(token: str) -> dict[str, Any]:
        return {
            "identity": {"user_id": "u2002", "username": "Cookie User", "role_code": "employee"},
            "permissions": [],
        }

    monkeypatch.setattr(settings, "auth_mode", "eai")
    monkeypatch.setattr(deps, "_fetch_eai_me", fake_me)
    deps._CACHE.clear()

    token = jwt.encode({"sub": "u2002"}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    response = client.get(
        f"{PREFIX}/meta/me",
        headers=headers(),
        cookies={settings.access_token_cookie: token},
    )
    assert response.status_code == 200, response.text
    assert response.json()["handler"] == "u2002"
