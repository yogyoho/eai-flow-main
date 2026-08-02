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
