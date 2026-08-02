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


class TestStartEndpoint:
    @pytest.mark.asyncio
    async def test_unknown_provider_404(self, monkeypatch):
        from app.extensions.auth import sso

        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        from fastapi import HTTPException, Response

        with pytest.raises(HTTPException) as exc:
            await sso.sso_start(_make_request(), "nope", Response())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_start_redirects_and_sets_state_cookie(self, monkeypatch):
        from app.extensions.auth import sso

        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "client1"
        pc.client_secret = "secret"
        pc.redirect_uri = None
        pc.scopes = ["openid", "email", "profile"]
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock(authorization_endpoint="https://idp.example.com/auth"))
        svc.build_authorization_url = lambda *a, **k: "https://idp.example.com/auth?client_id=client1"
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        resp = Response()
        result = await sso.sso_start(req, "keycloak", resp)
        from starlette.responses import RedirectResponse

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"].startswith("https://idp.example.com/auth")
        assert "df_oidc_state_keycloak=" in resp.headers["set-cookie"]
        assert "Path=/" in resp.headers["set-cookie"]


class TestCallbackEndpoint:
    @pytest.mark.asyncio
    async def test_callback_join_by_工号_and_issue_session(self, monkeypatch):
        from app.extensions.auth import sso
        from app.extensions.models import User

        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "client1"
        pc.client_secret = "secret"
        pc.redirect_uri = None
        pc.scopes = ["openid", "email", "profile"]
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        identity = MagicMock()
        identity.subject = "sub-123"
        identity.email = "zhangsan@eai-flow.com"
        identity.claims = {"employee_number": "zhangsan", "sub": "sub-123"}
        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock())
        svc.authenticate_callback = AsyncMock(return_value=identity)
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        # _issue_gateway_session 需要 gateway 侧 provider（同 test_login_success_issues_cookie
        # 的既有做法：patch app.gateway.deps.get_local_provider，跳过真实持久化引擎）
        gw_user = MagicMock()
        gw_user.id = uuid.uuid4()
        gw_user.token_version = 0
        provider = MagicMock()
        provider.get_user_by_email = AsyncMock(return_value=gw_user)
        monkeypatch.setattr("app.gateway.deps.get_local_provider", lambda: provider)

        from fastapi import Response

        from app.gateway.auth.oidc_state import OIDCStatePayload

        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        resp = Response()
        sso._set_eai_state_cookie(resp, req, OIDCStatePayload(provider="keycloak", state="the-state"))
        raw = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        from starlette.requests import Request as SRequest

        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw}".encode()),
                        (b"host", b"localhost:2026")],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        real_req = SRequest(scope)

        result = await sso.sso_callback(real_req, "keycloak", resp, code="code1", state="the-state", db=db)
        assert result.expires_in > 0

    @pytest.mark.asyncio
    async def test_callback_unknown_工号_401(self, monkeypatch):
        from app.extensions.auth import sso

        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "c"
        pc.client_secret = "s"
        pc.redirect_uri = None
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        identity = MagicMock()
        identity.subject = "sub-1"
        identity.email = "nobody@eai-flow.com"
        identity.claims = {"employee_number": "nobody"}
        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock())
        svc.authenticate_callback = AsyncMock(return_value=identity)
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        from fastapi import HTTPException, Response

        from app.gateway.auth.oidc_state import OIDCStatePayload

        resp = Response()
        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        sso._set_eai_state_cookie(resp, req, OIDCStatePayload(provider="keycloak", state="st"))
        raw = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        from starlette.requests import Request as SRequest

        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw}".encode()),
                        (b"host", b"localhost:2026")],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        real_req = SRequest(scope)

        with pytest.raises(HTTPException) as exc:
            await sso.sso_callback(real_req, "keycloak", resp, code="c", state="st", db=db)
        assert exc.value.status_code == 401  # 仅预建号，不自动建
