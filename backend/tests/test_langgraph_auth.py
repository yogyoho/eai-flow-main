"""Tests for LangGraph Server auth handler (langgraph_auth.py).

Validates that the LangGraph auth layer enforces the same rules as Gateway:
  cookie → JWT decode → DB lookup → token_version check → owner filter

Following the LangGraph SDK's recommended pattern:
  - Default deny via global handler
  - Resource/action-specific handlers for threads, store, assistants, crons
"""

import asyncio
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-key-for-langgraph-auth-testing-min-32")

from langgraph_sdk import Auth

from app.gateway.auth.config import AuthConfig, set_auth_config
from app.gateway.auth.jwt import create_access_token, decode_token
from app.gateway.auth.models import User
from app.gateway.langgraph_auth import (
    allow_assistants,
    allow_crons,
    authenticate,
    deny_all,
    on_threads_create,
    on_threads_create_run,
    on_threads_delete,
    on_threads_read,
    on_threads_search,
    on_threads_update,
    scope_store,
)

# ── Helpers ───────────────────────────────────────────────────────────────

_JWT_SECRET = "test-secret-key-for-langgraph-auth-testing-min-32"


@pytest.fixture(autouse=True)
def _setup_auth_config():
    set_auth_config(AuthConfig(jwt_secret=_JWT_SECRET))
    yield
    set_auth_config(AuthConfig(jwt_secret=_JWT_SECRET))


def _req(cookies=None, method="GET", headers=None):
    return SimpleNamespace(cookies=cookies or {}, method=method, headers=headers or {})


def _user(user_id=None, token_version=0):
    return User(email="test@example.com", password_hash="fakehash", system_role="user", id=user_id or uuid4(), token_version=token_version)


def _mock_provider(user=None):
    p = AsyncMock()
    p.get_user = AsyncMock(return_value=user)
    return p


# ── @auth.authenticate ───────────────────────────────────────────────────


def test_no_cookie_raises_401():
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req()))
    assert exc.value.status_code == 401
    assert "Not authenticated" in str(exc.value.detail)


def test_invalid_jwt_raises_401():
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req({"access_token": "garbage"})))
    assert exc.value.status_code == 401
    assert "Invalid token" in str(exc.value.detail)


def test_expired_jwt_raises_401():
    token = create_access_token("user-1", expires_delta=timedelta(seconds=-1))
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req({"access_token": token})))
    assert exc.value.status_code == 401


def test_user_not_found_raises_401():
    token = create_access_token("ghost")
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(None)):
        with pytest.raises(Auth.exceptions.HTTPException) as exc:
            asyncio.run(authenticate(_req({"access_token": token})))
        assert exc.value.status_code == 401
        assert "User not found" in str(exc.value.detail)


def test_token_version_mismatch_raises_401():
    user = _user(token_version=2)
    token = create_access_token(str(user.id), token_version=1)
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(user)):
        with pytest.raises(Auth.exceptions.HTTPException) as exc:
            asyncio.run(authenticate(_req({"access_token": token})))
        assert exc.value.status_code == 401
        assert "revoked" in str(exc.value.detail).lower()


def test_valid_token_returns_user_id():
    user = _user(token_version=0)
    token = create_access_token(str(user.id), token_version=0)
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(user)):
        result = asyncio.run(authenticate(_req({"access_token": token})))
    assert result == str(user.id)


def test_valid_token_matching_version():
    user = _user(token_version=5)
    token = create_access_token(str(user.id), token_version=5)
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(user)):
        result = asyncio.run(authenticate(_req({"access_token": token})))
    assert result == str(user.id)


# ── @auth.authenticate edge cases ────────────────────────────────────────


def test_provider_exception_propagates():
    """Provider raises → should not be swallowed silently."""
    token = create_access_token("user-1")
    p = AsyncMock()
    p.get_user = AsyncMock(side_effect=RuntimeError("DB down"))
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=p):
        with pytest.raises(RuntimeError, match="DB down"):
            asyncio.run(authenticate(_req({"access_token": token})))


def test_jwt_missing_ver_defaults_to_zero():
    """JWT without 'ver' claim → decoded as ver=0, matches user with token_version=0."""
    import jwt as pyjwt

    uid = str(uuid4())
    raw = pyjwt.encode({"sub": uid, "exp": 9999999999, "iat": 1000000000}, _JWT_SECRET, algorithm="HS256")
    user = _user(user_id=uid, token_version=0)
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(user)):
        result = asyncio.run(authenticate(_req({"access_token": raw})))
    assert result == uid


def test_jwt_missing_ver_rejected_when_user_version_nonzero():
    """JWT without 'ver' (defaults 0) vs user with token_version=1 → 401."""
    import jwt as pyjwt

    uid = str(uuid4())
    raw = pyjwt.encode({"sub": uid, "exp": 9999999999, "iat": 1000000000}, _JWT_SECRET, algorithm="HS256")
    user = _user(user_id=uid, token_version=1)
    with patch("app.gateway.langgraph_auth.get_local_provider", return_value=_mock_provider(user)):
        with pytest.raises(Auth.exceptions.HTTPException) as exc:
            asyncio.run(authenticate(_req({"access_token": raw})))
        assert exc.value.status_code == 401


def test_wrong_secret_raises_401():
    """Token signed with different secret → 401."""
    import jwt as pyjwt

    raw = pyjwt.encode({"sub": "user-1", "exp": 9999999999, "ver": 0}, "wrong-secret-that-is-long-enough-32chars!", algorithm="HS256")
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req({"access_token": raw})))
    assert exc.value.status_code == 401


# ── Authorization helpers ──────────────────────────────────────────────────


class _FakeUser:
    """Minimal BaseUser-compatible object without langgraph_api.config dependency."""

    def __init__(self, identity: str):
        self.identity = identity
        self.is_authenticated = True
        self.display_name = identity


def _make_ctx(user_id, resource="threads", action="create"):
    return Auth.types.AuthContext(resource=resource, action=action, user=_FakeUser(user_id), permissions=[])


# ── Default deny ─────────────────────────────────────────────────────────


def test_deny_all_returns_false():
    result = asyncio.run(deny_all(_make_ctx("user-a"), {}))
    assert result is False


# ── Threads: create ──────────────────────────────────────────────────────


def test_threads_create_stamps_user_id():
    value = {}
    result = asyncio.run(on_threads_create(_make_ctx("user-a"), value))
    assert value["metadata"]["user_id"] == "user-a"
    # Create returns None (accept without filter)
    assert result is None


def test_threads_create_preserves_existing_metadata():
    value = {"metadata": {"title": "hello"}}
    result = asyncio.run(on_threads_create(_make_ctx("user-a"), value))
    assert value["metadata"]["user_id"] == "user-a"
    assert value["metadata"]["title"] == "hello"
    assert result is None


def test_threads_create_overrides_conflicting_user_id():
    """If value already has a different user_id in metadata, it gets overwritten."""
    value = {"metadata": {"user_id": "attacker"}}
    asyncio.run(on_threads_create(_make_ctx("real-owner"), value))
    assert value["metadata"]["user_id"] == "real-owner"


# ── Threads: read ────────────────────────────────────────────────────────


def test_threads_read_returns_filter():
    result = asyncio.run(on_threads_read(_make_ctx("user-a", action="read"), {}))
    assert result == {"user_id": "user-a"}


def test_threads_read_different_users_different_filters():
    f_a = asyncio.run(on_threads_read(_make_ctx("user-a", action="read"), {}))
    f_b = asyncio.run(on_threads_read(_make_ctx("user-b", action="read"), {}))
    assert f_a["user_id"] != f_b["user_id"]


# ── Threads: search ──────────────────────────────────────────────────────


def test_threads_search_returns_filter():
    result = asyncio.run(on_threads_search(_make_ctx("user-a", action="search"), {}))
    assert result == {"user_id": "user-a"}


# ── Threads: update ──────────────────────────────────────────────────────


def test_threads_update_stamps_and_filters():
    value = {}
    result = asyncio.run(on_threads_update(_make_ctx("user-a", action="update"), value))
    assert value["metadata"]["user_id"] == "user-a"
    assert result == {"user_id": "user-a"}


# ── Threads: delete ──────────────────────────────────────────────────────


def test_threads_delete_returns_filter():
    result = asyncio.run(on_threads_delete(_make_ctx("user-a", action="delete"), {}))
    assert result == {"user_id": "user-a"}


# ── Threads: create_run ──────────────────────────────────────────────────


def test_threads_create_run_stamps_and_filters():
    value = {}
    result = asyncio.run(on_threads_create_run(_make_ctx("user-a", action="create_run"), value))
    assert value["metadata"]["user_id"] == "user-a"
    assert result == {"user_id": "user-a"}


# ── Store ────────────────────────────────────────────────────────────────


def test_store_scopes_namespace():
    value = {"namespace": ["shared"]}
    asyncio.run(scope_store(_make_ctx("user-a", resource="store", action="put"), value))
    assert value["namespace"] == ("user-a", "shared")


def test_store_empty_namespace():
    value = {"namespace": []}
    asyncio.run(scope_store(_make_ctx("user-a", resource="store", action="get"), value))
    assert value["namespace"] == ("user-a",)


def test_store_no_namespace_key():
    value = {}
    asyncio.run(scope_store(_make_ctx("user-a", resource="store", action="search"), value))
    assert value["namespace"] == ("user-a",)


def test_store_already_scoped():
    value = {"namespace": ["user-a", "data"]}
    asyncio.run(scope_store(_make_ctx("user-a", resource="store", action="put"), value))
    assert value["namespace"] == ("user-a", "data")


# ── Assistants / Crons ───────────────────────────────────────────────────


def test_assistants_accepts_all():
    result = asyncio.run(allow_assistants(_make_ctx("user-a", resource="assistants", action="create"), {}))
    assert result is None


def test_crons_accepts_all():
    result = asyncio.run(allow_crons(_make_ctx("user-a", resource="crons", action="create"), {}))
    assert result is None


# ── Gateway parity ───────────────────────────────────────────────────────


def test_shared_jwt_secret():
    token = create_access_token("user-1", token_version=3)
    payload = decode_token(token)
    from app.gateway.auth.errors import TokenError

    assert not isinstance(payload, TokenError)
    assert payload.sub == "user-1"
    assert payload.ver == 3


def test_langgraph_json_has_auth_path():
    import json

    config = json.loads((Path(__file__).parent.parent / "langgraph.json").read_text())
    assert "auth" in config
    assert "langgraph_auth" in config["auth"]["path"]


def test_auth_handler_has_all_layers():
    """Verify authenticate + default deny + resource-specific handlers."""
    from app.gateway.langgraph_auth import auth

    assert auth._authenticate_handler is not None
    # Default deny global handler
    assert len(auth._global_handlers) == 1
    # Resource/action-specific handlers: threads(6) + assistants(1) + crons(1) + store(1) = 9
    assert len(auth._handlers) == 9


# ── CSRF in LangGraph auth ──────────────────────────────────────────────


def test_csrf_get_no_check():
    """GET requests skip CSRF — should proceed to JWT validation."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req(method="GET")))
    # Rejected by missing cookie, NOT by CSRF
    assert exc.value.status_code == 401
    assert "Not authenticated" in str(exc.value.detail)


def test_csrf_post_missing_token():
    """POST without CSRF token → 403."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req(method="POST", cookies={"access_token": "some-jwt"})))
    assert exc.value.status_code == 403
    assert "CSRF token missing" in str(exc.value.detail)


def test_csrf_post_mismatched_token():
    """POST with mismatched CSRF tokens → 403."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(
            authenticate(
                _req(
                    method="POST",
                    cookies={"access_token": "some-jwt", "csrf_token": "real-token"},
                    headers={"x-csrf-token": "wrong-token"},
                )
            )
        )
    assert exc.value.status_code == 403
    assert "mismatch" in str(exc.value.detail)


def test_csrf_post_matching_token_proceeds_to_jwt():
    """POST with matching CSRF tokens passes CSRF check, then fails on JWT."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(
            authenticate(
                _req(
                    method="POST",
                    cookies={"access_token": "garbage", "csrf_token": "same-token"},
                    headers={"x-csrf-token": "same-token"},
                )
            )
        )
    # Past CSRF, rejected by JWT decode
    assert exc.value.status_code == 401
    assert "Invalid token" in str(exc.value.detail)


def test_csrf_put_requires_token():
    """PUT also requires CSRF."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req(method="PUT", cookies={"access_token": "jwt"})))
    assert exc.value.status_code == 403


def test_csrf_delete_requires_token():
    """DELETE also requires CSRF."""
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        asyncio.run(authenticate(_req(method="DELETE", cookies={"access_token": "jwt"})))
    assert exc.value.status_code == 403
