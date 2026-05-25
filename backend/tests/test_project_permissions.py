"""Tests for project RBAC permission matrix and check functions."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.project.permissions import (
    PERMISSION_MATRIX,
    ROLE_ORDER,
    check_permission,
    get_default_tab,
    get_permissions_for_role,
    get_project_role,
    get_user_project_permissions,
)


# ── TestPermissionMatrix ──


class TestPermissionMatrix:
    """Verify the permission matrix structure is correct."""

    def test_role_order_has_five_roles(self):
        assert ROLE_ORDER == ["manager", "editor", "writer", "reviewer", "approver"]

    def test_all_actions_have_five_bools(self):
        for action, perms in PERMISSION_MATRIX.items():
            assert len(perms) == 5, (
                f"Action '{action}' has {len(perms)} permissions, expected 5"
            )
            for i, p in enumerate(perms):
                assert isinstance(p, bool), (
                    f"Action '{action}' index {i} ({ROLE_ORDER[i]}) is {type(p).__name__}, expected bool"
                )

    def test_manager_has_all_permissions(self):
        """Manager (index 0) should have True for all actions."""
        for action, perms in PERMISSION_MATRIX.items():
            assert perms[0] is True, f"Manager should have '{action}' permission"

    def test_unknown_action_returns_false(self):
        assert check_permission("manager", "nonexistent:action") is False


# ── TestCheckPermission ──


class TestCheckPermission:
    """Verify check_permission returns correct booleans for each role."""

    # -- Manager: can do almost everything --
    def test_manager_can_edit_project(self):
        assert check_permission("manager", "project:edit") is True

    def test_manager_can_delete_project(self):
        assert check_permission("manager", "project:delete") is True

    def test_manager_can_advance_stage(self):
        assert check_permission("manager", "project:advance") is True

    def test_manager_can_add_members(self):
        assert check_permission("manager", "member:add") is True

    def test_manager_can_remove_members(self):
        assert check_permission("manager", "member:remove") is True

    def test_manager_can_edit_outline(self):
        assert check_permission("manager", "outline:edit") is True

    def test_manager_can_write_any_chapter(self):
        assert check_permission("manager", "chapter:write_any") is True

    def test_manager_can_assign_chapters(self):
        assert check_permission("manager", "chapter:assign") is True

    def test_manager_can_start_writing_ai(self):
        assert check_permission("manager", "ai:start_writing") is True

    def test_manager_can_submit_approval(self):
        assert check_permission("manager", "approval:submit") is True

    def test_manager_can_review(self):
        assert check_permission("manager", "approval:review") is True

    def test_manager_can_approve(self):
        assert check_permission("manager", "approval:approve") is True

    # -- Editor: can edit outline and chapters, but not project settings --
    def test_editor_cannot_edit_project(self):
        assert check_permission("editor", "project:edit") is False

    def test_editor_cannot_delete_project(self):
        assert check_permission("editor", "project:delete") is False

    def test_editor_cannot_advance_stage(self):
        assert check_permission("editor", "project:advance") is False

    def test_editor_can_edit_outline(self):
        assert check_permission("editor", "outline:edit") is True

    def test_editor_can_write_own_chapters(self):
        assert check_permission("editor", "chapter:write_own") is True

    def test_editor_cannot_write_any_chapter(self):
        assert check_permission("editor", "chapter:write_any") is False

    def test_editor_can_start_editing_ai(self):
        assert check_permission("editor", "ai:start_editing") is True

    def test_editor_cannot_start_writing_ai(self):
        assert check_permission("editor", "ai:start_writing") is False

    def test_editor_cannot_assign_chapters(self):
        assert check_permission("editor", "chapter:assign") is False

    # -- Writer: can only write own chapters --
    def test_writer_cannot_edit_project(self):
        assert check_permission("writer", "project:edit") is False

    def test_writer_cannot_edit_outline(self):
        assert check_permission("writer", "outline:edit") is False

    def test_writer_can_write_own_chapters(self):
        assert check_permission("writer", "chapter:write_own") is True

    def test_writer_cannot_write_any_chapter(self):
        assert check_permission("writer", "chapter:write_any") is False

    def test_writer_can_view_outline(self):
        assert check_permission("writer", "outline:view") is True

    def test_writer_can_use_toolbox(self):
        assert check_permission("writer", "ai:toolbox") is True

    def test_writer_cannot_submit_approval(self):
        assert check_permission("writer", "approval:submit") is False

    # -- Reviewer: can review but not approve --
    def test_reviewer_can_review(self):
        assert check_permission("reviewer", "approval:review") is True

    def test_reviewer_cannot_approve(self):
        assert check_permission("reviewer", "approval:approve") is False

    def test_reviewer_can_view_all(self):
        assert check_permission("reviewer", "chapter:view_all") is True

    def test_reviewer_cannot_edit_outline(self):
        assert check_permission("reviewer", "outline:edit") is False

    def test_reviewer_cannot_write_chapters(self):
        assert check_permission("reviewer", "chapter:write_own") is False

    # -- Approver: can approve but not review --
    def test_approver_can_approve(self):
        assert check_permission("approver", "approval:approve") is True

    def test_approver_cannot_review(self):
        assert check_permission("approver", "approval:review") is False

    def test_approver_can_view_all(self):
        assert check_permission("approver", "chapter:view_all") is True

    def test_approver_cannot_edit_outline(self):
        assert check_permission("approver", "outline:edit") is False

    # -- Unknown role --
    def test_unknown_role_returns_false(self):
        assert check_permission("unknown_role", "project:edit") is False
        assert check_permission("ghost", "outline:view") is False
        assert check_permission("", "chapter:view_all") is False


# ── TestGetPermissionsForRole ──


class TestGetPermissionsForRole:
    """Verify get_permissions_for_role returns correct action lists."""

    def test_manager_has_all_permissions(self):
        perms = get_permissions_for_role("manager")
        assert set(perms) == set(PERMISSION_MATRIX.keys())

    def test_writer_perms_subset_of_editor(self):
        writer_perms = set(get_permissions_for_role("writer"))
        editor_perms = set(get_permissions_for_role("editor"))
        assert writer_perms.issubset(editor_perms), (
            f"Writer perms not subset of editor: {writer_perms - editor_perms}"
        )

    def test_unknown_role_returns_empty(self):
        assert get_permissions_for_role("unknown") == []
        assert get_permissions_for_role("") == []

    def test_reviewer_has_only_view_and_review(self):
        perms = set(get_permissions_for_role("reviewer"))
        assert "approval:review" in perms
        assert "approval:approve" not in perms
        assert "outline:edit" not in perms

    def test_approver_has_only_view_and_approve(self):
        perms = set(get_permissions_for_role("approver"))
        assert "approval:approve" in perms
        assert "approval:review" not in perms
        assert "outline:edit" not in perms


# ── TestGetDefaultTab ──


class TestGetDefaultTab:
    """Verify get_default_tab returns correct tab for each role."""

    def test_manager_gets_dashboard(self):
        assert get_default_tab("manager") == "dashboard"

    def test_editor_gets_my_workspace(self):
        assert get_default_tab("editor") == "my-workspace"

    def test_writer_gets_my_workspace(self):
        assert get_default_tab("writer") == "my-workspace"

    def test_reviewer_gets_kanban(self):
        assert get_default_tab("reviewer") == "kanban"

    def test_approver_gets_kanban(self):
        assert get_default_tab("approver") == "kanban"

    def test_unknown_role_gets_dashboard(self):
        assert get_default_tab("unknown") == "dashboard"


# ── TestGetProjectRole ──


class TestGetProjectRole:
    """Verify get_project_role queries ProjectMember correctly."""

    @pytest.mark.asyncio
    async def test_returns_role_when_member_exists(self):
        """When user is a member, return their role."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "editor"
        mock_db.execute = AsyncMock(return_value=mock_result)

        role = await get_project_role(mock_db, uuid.uuid4(), uuid.uuid4())
        assert role == "editor"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_member(self):
        """When user is not a member, return None."""
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
    async def test_admin_gets_manager_perms(self):
        """Admin users should get manager-level permissions."""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        role, perms = await get_user_project_permissions(
            mock_db, project_id, user_id, is_admin=True
        )
        assert role == "manager"
        assert set(perms) == set(PERMISSION_MATRIX.keys())

    @pytest.mark.asyncio
    async def test_non_admin_member_gets_their_perms(self):
        """Non-admin members should get their actual role permissions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "writer"
        mock_db.execute = AsyncMock(return_value=mock_result)

        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=False
        )
        assert role == "writer"
        writer_perms = set(get_permissions_for_role("writer"))
        assert set(perms) == writer_perms

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
        # Even if they're a "writer" in the project, admin should get manager perms
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(role="writer")
        mock_db.execute.return_value = mock_result

        role, perms = await get_user_project_permissions(
            mock_db, uuid.uuid4(), uuid.uuid4(), is_admin=True
        )
        assert role == "manager"


# ── TestRequireResourcePermission ──


class TestRequireResourcePermission:
    """Verify require_resource_permission FastAPI dependency factory."""

    def test_returns_callable(self):
        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        assert callable(dep)

    def _make_request(self, project_id: str | None = None):
        """Create a mock Request with optional project_id in path_params."""
        req = MagicMock()
        req.path_params = {"project_id": project_id} if project_id else {}
        return req

    def _make_non_admin_user(self):
        """Create a mock non-admin CurrentUser."""
        user = MagicMock()
        user.role_id = uuid.uuid4()
        user.id = uuid.uuid4()
        return user

    def _mock_non_admin_db(self, mock_db):
        """Set up mock db to return a non-admin Role."""
        admin_role = MagicMock()
        admin_role.permissions = []
        admin_role.is_system = False
        mock_db.get = AsyncMock(return_value=admin_role)

    def _mock_admin_db(self, mock_db, permissions=None):
        """Set up mock db to return an admin Role."""
        admin_role = MagicMock()
        admin_role.permissions = permissions if permissions is not None else ["*"]
        admin_role.is_system = permissions is None  # default is_system=False
        mock_db.get = AsyncMock(return_value=admin_role)

    def _mock_project_member(self, mock_db, role: str):
        """Set up mock db to return a ProjectMember with given role."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = role
        mock_db.execute = AsyncMock(return_value=mock_result)

    @pytest.mark.asyncio
    async def test_non_admin_with_permission_succeeds(self):
        """Non-admin member with the right role/action passes."""
        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "manager")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "manager"

    @pytest.mark.asyncio
    async def test_non_admin_without_permission_raises(self):
        """Non-admin member without permission raises 403."""
        from fastapi import HTTPException

        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        self._mock_project_member(mock_db, "writer")
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_bypasses_project_role_check(self):
        """Admin user gets manager role regardless of project membership."""
        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_admin_db(mock_db)
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "manager"

    @pytest.mark.asyncio
    async def test_system_role_bypasses_project_role_check(self):
        """System role user gets manager role regardless of project membership."""
        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_admin_db(mock_db, permissions=[])
        # Override is_system to True
        mock_db.get = AsyncMock(
            return_value=MagicMock(permissions=[], is_system=True)
        )
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        role = await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert role == "manager"

    @pytest.mark.asyncio
    async def test_no_role_assigned_raises(self):
        """User with no role_id is not admin, so needs project membership.
        Without project_id in path, raises 400.
        """
        from fastapi import HTTPException

        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.role_id = None
        mock_request = self._make_request()

        # No role_id means not admin -> needs project_id -> 400
        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_not_a_member_raises_403(self):
        """Non-admin user who is not a project member raises 403."""
        from fastapi import HTTPException

        from app.extensions.project.permissions import require_resource_permission

        dep = require_resource_permission("project:edit")
        mock_db = AsyncMock()
        self._mock_non_admin_db(mock_db)
        # User is not a member (no ProjectMember row)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_user = self._make_non_admin_user()
        mock_request = self._make_request(str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await dep(current_user=mock_user, request=mock_request, db=mock_db)
        assert exc_info.value.status_code == 403
        assert "not a member" in exc_info.value.detail
