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
