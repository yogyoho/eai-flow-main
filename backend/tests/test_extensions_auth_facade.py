"""Tests for the EAI auth facade (username+password / email+OTP login)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.config import ExtensionsConfig


@pytest.fixture(autouse=True)
def _ensure_gateway_auth_config():
    """Ensure the Gateway AuthConfig singleton is set so token issuance works in tests
    (otherwise get_auth_config() would auto-generate/persist a real .jwt_secret)."""
    from app.gateway.auth.config import AuthConfig, set_auth_config

    set_auth_config(AuthConfig(jwt_secret="test-secret"))
    yield


class TestAuthConfig:
    def test_smtp_defaults_disabled(self):
        cfg = ExtensionsConfig()
        assert cfg.smtp.enabled is False
        assert cfg.smtp.usable is False

    def test_smtp_usable_when_enabled_and_host(self):
        cfg = ExtensionsConfig()
        cfg.smtp.host = "smtp.example.com"
        cfg.smtp.enabled = True
        assert cfg.smtp.usable is True

    def test_otp_defaults(self):
        cfg = ExtensionsConfig()
        assert cfg.otp.length == 6
        assert cfg.otp.ttl_seconds == 300
        assert cfg.otp.send_cooldown_seconds == 60


class TestOtpModel:
    def test_otp_codes_registered_on_shared_base(self):
        import app.extensions.auth  # noqa: F401  # ensure facade imported
        from app.extensions.database import Base

        assert "otp_codes" in Base.metadata.tables

    def test_otp_code_columns(self):
        from app.extensions.models import OtpCode

        row = OtpCode(email="a@b.com", code_hash="x", expires_at=datetime.now(UTC))
        assert row.email == "a@b.com"
        assert row.used_at is None


class TestOtpCore:
    def test_generate_code_is_numeric_length(self):
        from app.extensions.auth.otp import generate_code

        code = generate_code(6)
        assert len(code) == 6
        assert code.isdigit()

    def test_code_is_valid_rejects_wrong_and_expired(self):
        from app.extensions.auth.jwt import hash_password
        from app.extensions.auth.otp import code_is_valid
        from app.extensions.models import OtpCode

        row = OtpCode(email="a@b.com", code_hash=hash_password("123456"), expires_at=datetime.now(UTC) + timedelta(minutes=5))
        assert code_is_valid(row, "123456", datetime.now(UTC)) is True
        assert code_is_valid(row, "000000", datetime.now(UTC)) is False

        expired = OtpCode(email="a@b.com", code_hash=hash_password("123456"), expires_at=datetime.now(UTC) - timedelta(minutes=1))
        assert code_is_valid(expired, "123456", datetime.now(UTC)) is False

    @pytest.mark.asyncio
    async def test_send_otp_echoes_when_smtp_disabled(self, monkeypatch):
        from app.extensions.auth import otp
        from app.extensions.config import ExtensionsConfig

        # Force SMTP-disabled config for the module singleton (auto-restored by monkeypatch).
        monkeypatch.setattr("app.extensions.config._extensions_config", ExtensionsConfig())

        code = await otp.send_otp_email("a@b.com", "123456")
        assert code == "123456"


def _make_request(host: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = host
    req.url.scheme = "http"
    return req


class TestPasswordLogin:
    @pytest.mark.asyncio
    async def test_login_success_issues_cookie(self, monkeypatch):
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        gw_user = MagicMock()
        gw_user.id = uuid.uuid4()
        gw_user.token_version = 0

        async def fake_authenticate(creds):
            assert creds["email"] == "zhangsan@eai-flow.com"
            return gw_user

        provider = MagicMock()
        provider.authenticate = fake_authenticate
        provider.get_user_by_email = AsyncMock(return_value=gw_user)
        monkeypatch.setattr("app.gateway.deps.get_local_provider", lambda: provider)

        from fastapi import Response

        from app.extensions.auth.routers import LoginRequest, login

        resp = Response()
        result = await login(_make_request(), resp, LoginRequest(username="zhangsan", password="secret123"), db)
        assert result.expires_in > 0
        assert resp.headers["set-cookie"].startswith("access_token=")

    @pytest.mark.asyncio
    async def test_login_wrong_password_401(self, monkeypatch):
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        async def fake_authenticate(creds):
            return None

        provider = MagicMock()
        provider.authenticate = fake_authenticate
        monkeypatch.setattr("app.gateway.deps.get_local_provider", lambda: provider)
        monkeypatch.setattr("app.extensions.user.sync.sync_user_created", AsyncMock())

        from fastapi import HTTPException, Response

        from app.extensions.auth.routers import LoginRequest, login

        resp = Response()
        with pytest.raises(HTTPException) as exc:
            await login(_make_request(), resp, LoginRequest(username="zhangsan", password="bad"), db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user_401(self):
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="disabled")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        from fastapi import HTTPException, Response

        from app.extensions.auth.routers import LoginRequest, login

        with pytest.raises(HTTPException) as exc:
            await login(_make_request(), Response(), LoginRequest(username="zhangsan", password="x"), db)
        assert exc.value.status_code == 401
