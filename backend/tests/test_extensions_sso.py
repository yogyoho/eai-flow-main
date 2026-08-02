"""Tests for the EAI SSO (OIDC third facade)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response


@pytest.fixture(autouse=True)
def _ensure_gateway_auth_config():
    """确保 Gateway AuthConfig 单例就绪（token 签发用）。"""
    from app.gateway.auth.config import AuthConfig, set_auth_config

    set_auth_config(AuthConfig(jwt_secret="test-secret"))
    yield


def _make_request(host: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = host
    req.url.scheme = "http"
    return req


class TestStateCookie:
    def test_set_eai_state_cookie_writes_path_root(self):
        from app.extensions.auth import sso
        from app.gateway.auth.oidc_state import OIDCStatePayload

        resp = Response()
        sso._set_eai_state_cookie(resp, _make_request(),
                                  OIDCStatePayload(provider="keycloak", state="abc"))
        set_cookie = resp.headers.get("set-cookie", "")
        assert "df_oidc_state_keycloak=" in set_cookie
        assert "Path=/" in set_cookie

    def test_cookie_survives_get_state_cookie_roundtrip(self):
        from app.extensions.auth import sso
        from app.gateway.auth.oidc_state import OIDCStatePayload, get_state_cookie

        resp = Response()
        payload = OIDCStatePayload(provider="keycloak", state="s1", nonce="n1",
                                   code_verifier="v1")
        sso._set_eai_state_cookie(resp, _make_request(), payload)
        from starlette.requests import Request

        raw_cookie = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw_cookie}".encode())],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        req = Request(scope)
        got = get_state_cookie(req, "keycloak")
        assert got is not None
        assert got.state == "s1"
        assert got.nonce == "n1"
        assert got.code_verifier == "v1"
