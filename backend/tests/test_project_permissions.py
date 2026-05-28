"""Tests for project RBAC permission matrix — simplified owner/member model."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.project.permissions import (
    PERMISSION_MATRIX,
    ROLE_ORDER,
    check_permission,
    get_permissions_for_role,
    get_project_role,
    get_user_project_permissions,
    require_resource_permission,
)


# ── TestPermissionMatrix ──


class TestPermissionMatrix:
    """Verify the simplified permission matrix structure."""

    def test_role_order_has_two_roles(self):
        assert ROLE_ORDER == ["owner", "member"]

    def test_all_actions_have_two_bools(self):
        for action, perms in PERMISSION_MATRIX.items():
            assert len(perms) == 2, f"Action '{action}' has {len(perms)} permissions, expected 2"
            for i, p in enumerate(perms):
                assert isinstance(p, bool), f"Action '{action}' index {i} is {type(p).__name__}, expected bool"

    def test_owner_has_all_permissions(self):
        for action, perms in PERMISSION_MATRIX.items():
            assert perms[0] is True, f"Owner should have '{action}' permission"

    def test_unknown_action_returns_false(self):
        assert check_permission("owner", "nonexistent:action") is False

    def test_has_seven_actions(self):
        assert len(PERMISSION_MATRIX) == 7


# ── TestCheckPermission ──


class TestCheckPermission:
    """Verify check_permission returns correct booleans for owner/member."""

    # -- Owner: can do everything --
    def test_owner_can_edit_project(self):
        assert check_permission("owner", "project:edit") is True

    def test_owner_can_delete_project(self):
        assert check_permission("owner", "project:delete") is True

    def test_owner_can_add_members(self):
        assert check_permission("owner", "member:add") is True

    def test_owner_can_remove_members(self):
        assert check_permission("owner", "member:remove") is True

    def test_owner_can_submit_approval(self):
        assert check_permission("owner", "approval:submit") is True

    def test_owner_can_review(self):
        assert check_permission("owner", "approval:review") is True

    def test_owner_can_view_approval(self):
        assert check_permission("owner", "approval:view") is True

    # -- Member: limited permissions --
    def test_member_cannot_edit_project(self):
        assert check_permission("member", "project:edit") is False

    def test_member_cannot_delete_project(self):
        assert check_permission("member", "project:delete") is False

    def test_member_cannot_add_members(self):
        assert check_permission("member", "member:add") is False

    def test_member_cannot_remove_members(self):
        assert check_permission("member", "member:remove") is False

    def test_member_cannot_submit_approval(self):
        assert check_permission("member", "approval:submit") is False

    def test_member_can_review(self):
        assert check_permission("member", "approval:review") is True

    def test_member_can_view_approval(self):
        assert check_permission("member", "approval:view") is True

    # -- Unknown role --
    def test_unknown_role_returns_false(self):
        assert check_permission("unknown_role", "project:edit") is False
        assert check_permission("ghost", "approval:view") is False
        assert check_permission("", "member:add") is False


# ── TestGetPermissionsForRole ──


class TestGetPermissionsForRole:
    """Verify get_permissions_for_role returns correct action lists."""

    def test_owner_has_all_permissions(self):
        perms = get_permissions_for_role("owner")
        assert set(perms) == set(PERMISSION_MATRIX.keys())

    def test_member_has_review_and_view_only(self):
        perms = set(get_permissions_for_role("member"))
        assert "approval:review" in perms
        assert "approval:view" in perms
        assert "project:edit" not in perms
        assert "member:add" not in perms

    def test_unknown_role_returns_empty(self):
        assert get_permissions_for_role("unknown") == []
        assert get_permissions_for_role("") == []


# ── TestGetProjectRole ──


class TestGetProjectRole:
    """Verify get_project_role queries ProjectMember correctly."""

    @pytest.mark.asyncio
    async def test_returns_role_when_member_exists(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "member"
        mock_db.execute = AsyncMock(return_value=mock_result)

        role = await get_project_role(mock_db, uuid.uuid4(), uuid.uuid4())
        assert role == "member"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_member(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        role = await get_project_role(mock_db, uuid.uuid4(), uuid.uuid4())
        assert role is None


# ── TestGetUserProjectPermissions ──


class TestGetUserProjectPermissions:
    """Verify get_user_project_permissions combines role + admin override."""

    @pytest.mark.asyncio
    async def test_admin_gets_owner_perms(self):
        """Admin users should get owner-level permissions."""
        mock_db = AsyncMock()
        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=True
        )
        assert role == "owner"
        assert set(perms) == set(PERMISSION_MATRIX.keys())

    @pytest.mark.asyncio
    async def test_non_admin_member_gets_their_perms(self):
        """Non-admin members should get their actual role permissions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "member"
        mock_db.execute = AsyncMock(return_value=mock_result)

        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=False
        )
        assert role == "member"
        member_perms = set(get_permissions_for_role("member"))
        assert set(perms) == member_perms

    @pytest.mark.asyncio
    async def test_non_admin_non_member_gets_nothing(self):
        """Non-admin non-members should get no role and empty permissions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=False
        )
        assert role is None
        assert perms == []

    @pytest.mark.asyncio
    async def test_admin_override_even_if_member(self):
        """Admin override takes precedence even if user is a project member."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(role="member")
        mock_db.execute.return_value = mock_result

        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=True
        )
        assert role == "owner"


# ── TestRequireResourcePermission ──


class TestRequireResourcePermission:
    """Verify require_resource_permission FastAPI dependency factory."""

    def test_returns_callable(self):
        dep = require_resource_permission("project:edit")
        assert callable(dep)

    def _make_request(self, project_id: str | None = None):
        req = MagicMock()
        req.path_params = {"project_id": project_id} if project_id else {}
        return req

    def _make_non_admin_user(self):
        user = MagicMock()
        user.role_id = uuid.uuid4()
        user.id = uuid.uuid4()
        return user

    def _mock_non_admin_db(self, mock_db):
        admin_role = MagicMock()
        admin_role.permissions = []
        admin_role.is_system = False
        mock_db.get = AsyncMock(return_value=admin_role)

    def _mock_admin_db(self, mock_db, permissions=None):
        admin_role = MagicMock()
        admin_role.permissions = permissions if permissions is not None else ["*"]
        admin_role.is_system = permissions is None
        mock_db.get = AsyncMock(return_value=admin_role)

    def _mock_project_member(self, mock_db, role: str):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = role
        mock_db.execute = AsyncMock(return_value=mock_result)

    @pytest.mark.asyncio
    async def test_owner_with_permission_succeeds(self):
        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "owner")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_member_without_permission_raises(self):
        from fastapi import HTTPException

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "member")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_bypasses_project_role_check(self):
        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_admin_db(mock_db)
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_system_role_bypasses_project_role_check(self):
        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(
            return_value=MagicMock(permissions=[], is_system=True)
        )
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_no_role_assigned_raises(self):
        from fastapi import HTTPException

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.role_id = None
        mock_request = self._make_request()

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_not_a_member_raises_403(self):
        from fastapi import HTTPException

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 403
        assert "not a member" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_member_can_review_approval(self):
        dep = require_resource_permission("approval:review")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "member")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "member"

    @pytest.mark.asyncio
    async def test_member_cannot_add_member(self):
        from fastapi import HTTPException

        dep = require_resource_permission("member:add")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "member")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 403
