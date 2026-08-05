"""Tests for Policy model and engine integration."""

import pytest
from fastapi import HTTPException

from app.extensions.auth.engine import Policy as EnginePolicy
from app.extensions.auth.policy_routers import _validate_grants
from app.extensions.auth.registry import get_permission_registry


class TestPolicyEngine:
    def test_policy_from_db_row(self):
        p = EnginePolicy(
            name="test",
            priority=10,
            conditions={"attr": "role_level", "op": "gte", "value": 5},
            grants={"permissions": ["kb:create"]},
        )
        assert p.name == "test"
        assert p.priority == 10
        assert p.conditions["attr"] == "role_level"
        assert "kb:create" in p.grants["permissions"]


class TestValidateGrants:
    """EAI-CUSTOM (T9): validate policy grants deny_permissions / deny_data_scopes shape."""

    def test_validate_grants_rejects_unknown_deny_data_scope(self):
        reg = get_permission_registry()
        # unknown scope id -> 400
        with pytest.raises(HTTPException) as exc:
            _validate_grants({"deny_data_scopes": ["this_scope_does_not_exist"]}, reg)
        assert exc.value.status_code == 400
        # valid: empty deny_data_scopes passes (no raise)
        _validate_grants(
            {"permissions": ["kb:read"], "deny_permissions": ["kb:delete"], "deny_data_scopes": []},
            reg,
        )

    def test_validate_grants_rejects_non_list_deny_permissions(self):
        reg = get_permission_registry()
        with pytest.raises(HTTPException) as exc:
            _validate_grants({"deny_permissions": "kb:delete"}, reg)  # str, not list
        assert exc.value.status_code == 400

    # EAI-CUSTOM (M4): deny_permissions non-wildcard ids must be real permission points.
    def test_validate_grants_rejects_unknown_deny_permission_id(self):
        reg = get_permission_registry()
        # unknown non-wildcard id -> 400
        with pytest.raises(HTTPException) as exc:
            _validate_grants({"deny_permissions": ["kb:nonexistent"]}, reg)
        assert exc.value.status_code == 400

    def test_validate_grants_allows_wildcard_deny_permission(self):
        reg = get_permission_registry()
        # module wildcard passes through (not registry-checked)
        _validate_grants({"deny_permissions": ["kb:*"]}, reg)

    def test_validate_grants_allows_known_deny_permission_id(self):
        reg = get_permission_registry()
        # a real permission id (kb:read is declared in the knowledge module) passes
        _validate_grants({"deny_permissions": ["kb:read"]}, reg)
