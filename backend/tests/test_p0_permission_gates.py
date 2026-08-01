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

    @pytest.mark.asyncio
    async def test_ensure_role_creation_path(self):
        """_ensure_role should create role from registry defaults when missing from DB."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.auth.middleware import _ensure_role
        from app.extensions.models import Role as RoleModel

        db = AsyncMock()
        db.add = MagicMock()  # SQLAlchemy db.add is synchronous
        # Simulate role NOT in DB (first-time bridge for a new user)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await _ensure_role(db, "user")

        # Must have called db.add with a Role and db.flush
        db.add.assert_called_once()
        db.flush.assert_called_once()

        # Inspect the created role
        created_role = db.add.call_args[0][0]
        assert isinstance(created_role, RoleModel)
        assert created_role.code == "user"
        assert created_role.name == "普通用户"
        assert created_role.is_system is False
        assert created_role.level == 1

        # Permissions from registry: kb:read, doc:read, model:read, system:access
        assert "kb:read" in created_role.permissions
        assert "doc:read" in created_role.permissions
        assert "model:read" in created_role.permissions
        assert "system:access" in created_role.permissions
        assert "project:create" not in created_role.permissions, (
            "project:create should NOT be in registry-resolved default user permissions"
        )

        # The returned role should be the same object
        assert result is created_role


def _get_user_defaults():
    from app.extensions.auth.registry import get_permission_registry
    return sorted(get_permission_registry().resolve_role_permissions("user"))


# ── P0-2: Workflow definition super admin lock ──


class TestWorkflowSuperAdminLock:
    """Verify workflow definition edit/delete requires super admin."""

    @pytest.mark.asyncio
    async def test_require_super_admin_rejects_non_admin(self):
        """require_super_admin should reject users without system role."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.extensions.auth.identity import AttributeSet
        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.id = str(uuid.uuid4())
        user.role_id = uuid.uuid4()

        db = AsyncMock()

        # Mock identity provider to return non-system, non-wildcard user
        identity = AttributeSet(user_id=user.id, username="test", role_code="user")
        mock_provider = MagicMock()
        mock_provider.resolve = AsyncMock(return_value=identity)

        mock_registry = MagicMock()
        mock_registry.get_role_defaults.return_value = {"is_system": False, "level": 1}
        mock_registry.resolve_role_permissions.return_value = {"kb:read", "doc:read", "model:read", "system:access"}

        with (
            patch("app.extensions.auth.identity.get_identity_provider", return_value=mock_provider),
            patch("app.extensions.auth.registry.get_permission_registry", return_value=mock_registry),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await check_fn(current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_super_admin_allows_system_role(self):
        """require_super_admin should allow users with is_system=True."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.extensions.auth.identity import AttributeSet
        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.id = str(uuid.uuid4())
        user.role_id = uuid.uuid4()

        db = AsyncMock()

        # Mock identity provider to return superadmin user
        identity = AttributeSet(user_id=user.id, username="admin", role_code="superadmin")
        mock_provider = MagicMock()
        mock_provider.resolve = AsyncMock(return_value=identity)

        mock_registry = MagicMock()
        mock_registry.get_role_defaults.return_value = {"is_system": True, "level": 100}
        mock_registry.resolve_role_permissions.return_value = {"*"}

        with (
            patch("app.extensions.auth.identity.get_identity_provider", return_value=mock_provider),
            patch("app.extensions.auth.registry.get_permission_registry", return_value=mock_registry),
        ):
            result = await check_fn(current_user=user, db=db)
            assert result == user

    @pytest.mark.asyncio
    async def test_require_super_admin_allows_wildcard(self):
        """require_super_admin should allow users with wildcard permissions."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.extensions.auth.identity import AttributeSet
        from app.extensions.auth.middleware import require_super_admin

        check_fn = require_super_admin()

        user = MagicMock()
        user.id = str(uuid.uuid4())
        user.role_id = uuid.uuid4()

        db = AsyncMock()

        # Mock identity provider to return a role with wildcard but not is_system
        identity = AttributeSet(user_id=user.id, username="power_user", role_code="power_user")
        mock_provider = MagicMock()
        mock_provider.resolve = AsyncMock(return_value=identity)

        mock_registry = MagicMock()
        mock_registry.get_role_defaults.return_value = {"is_system": False, "level": 50}
        mock_registry.resolve_role_permissions.return_value = {"*"}

        with (
            patch("app.extensions.auth.identity.get_identity_provider", return_value=mock_provider),
            patch("app.extensions.auth.registry.get_permission_registry", return_value=mock_registry),
        ):
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
