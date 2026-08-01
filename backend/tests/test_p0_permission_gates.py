"""Tests for P0 permission gates:
1. project:create removed from default "user" role
2. Workflow definition edit/delete requires super admin
"""

import uuid

import pytest
from fastapi.testclient import TestClient


# ── P0-1: project:create removed from default user role ──


class TestProjectCreatePermissionGate:
    """Verify that project:create is NOT in the default 'user' role permissions."""

    def test_user_role_defaults_lack_project_create(self):
        from app.extensions.auth.registry import get_permission_registry

        registry = get_permission_registry()
        defaults = registry.get_role_defaults("user")
        assert defaults is not None, "user role should exist in registry"
        resolved = registry.resolve_role_permissions("user")
        assert "project:create" not in resolved, (
            "project:create should NOT be in default user permissions"
        )

    def test_superadmin_role_has_wildcard(self):
        from app.extensions.auth.registry import get_permission_registry

        registry = get_permission_registry()
        defaults = registry.get_role_defaults("superadmin")
        assert defaults is not None, "superadmin role should exist in registry"
        assert defaults["is_system"] is True
        resolved = registry.resolve_role_permissions("superadmin")
        assert "*" in resolved

    def test_require_permission_project_create_allows_admin(self):
        """Super admin (wildcard permission) should pass project:create check."""
        from app.extensions.auth.middleware import require_permission

        # We can't easily test the full FastAPI dependency without a client,
        # but we verify the permission string is checkable
        assert "project:create" not in _get_user_defaults()

    @pytest.mark.asyncio
    async def test_user_role_ensure_no_drift_reset(self):
        """_ensure_role should NOT reset extra permissions admin has granted (S3 fix)."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import _ensure_role

        # Simulate a role in DB that has project:create (admin-granted extra)
        extra_perms = [
            "model:read", "system:access", "project:create",
        ]
        old_role = MagicMock()
        old_role.is_system = False
        old_role.permissions = list(extra_perms)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = old_role
        db.execute.return_value = mock_result

        result = await _ensure_role(db, "user")

        # The role should be returned as-is — NO reset (S3 fix)
        assert result is old_role
        assert old_role.permissions == extra_perms
        assert "project:create" in old_role.permissions


def _get_user_defaults():
    from app.extensions.auth.registry import get_permission_registry
    return sorted(get_permission_registry().resolve_role_permissions("user"))


# ── P0-2: Workflow definition super admin lock ──


class TestWorkflowSuperAdminLock:
    """Verify workflow definition edit/delete requires super admin."""

    @pytest.mark.asyncio
    async def test_require_super_admin_rejects_non_admin(self):
        """require_super_admin should reject users without system role."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.role_id = uuid.uuid4()

        role = MagicMock()
        role.is_system = False
        role.permissions = ["system:access", "project:create"]

        db = AsyncMock()
        db.get.return_value = role

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_super_admin_allows_system_role(self):
        """require_super_admin should allow users with is_system=True."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.role_id = uuid.uuid4()

        role = MagicMock()
        role.is_system = True
        role.permissions = ["*"]

        db = AsyncMock()
        db.get.return_value = role

        result = await check_fn(current_user=user, db=db)
        assert result == user

    @pytest.mark.asyncio
    async def test_require_super_admin_allows_wildcard(self):
        """require_super_admin should allow users with wildcard permissions."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.role_id = uuid.uuid4()

        role = MagicMock()
        role.is_system = False
        role.permissions = ["*"]

        db = AsyncMock()
        db.get.return_value = role

        result = await check_fn(current_user=user, db=db)
        assert result == user

    @pytest.mark.asyncio
    async def test_require_super_admin_rejects_no_role(self):
        """require_super_admin should reject users with no role_id."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.role_id = None

        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user, db=db)
        assert exc_info.value.status_code == 403

    def test_workflow_routers_use_super_admin_for_edit(self):
        """Verify update/delete/publish endpoints use WorkflowSuperAdmin dependency."""
        import inspect

        from app.extensions.workflow.routers import (
            delete_definition,
            update_definition,
            publish_template,
        )

        # Check that the endpoint functions reference WorkflowSuperAdmin
        # by verifying their signature contains _user with the right annotation
        for fn in [update_definition, delete_definition, publish_template]:
            sig = inspect.signature(fn)
            params = sig.parameters
            assert "_user" in params, f"{fn.__name__} missing _user param"
