"""Tests for the new project-level permission system (project_permissions.py)."""
import pytest
from unittest.mock import MagicMock

from app.extensions.project.project_permissions import (
    PROJECT_PERMISSIONS,
    get_effective_permissions,
    has_permission,
    get_project_role_permissions,
)


class TestProjectPermissionsList:
    def test_contains_core_permissions(self):
        required = [
            "project:create", "project:edit", "project:delete",
            "chapter:write_any", "chapter:write_own", "chapter:review",
            "approval:submit", "approval:review", "approval:approve", "approval:view",
            "settings:edit", "ai:start_writing", "source:view",
            "member:add", "member:remove", "outline:edit",
            "version:rollback", "export:generate",
        ]
        for perm in required:
            assert perm in PROJECT_PERMISSIONS, f"Missing permission: {perm}"

    def test_has_no_duplicates(self):
        assert len(PROJECT_PERMISSIONS) == len(set(PROJECT_PERMISSIONS))


class TestGetEffectivePermissions:
    def test_admin_gets_all(self):
        result = get_effective_permissions(is_admin=True)
        assert set(result) == set(PROJECT_PERMISSIONS)

    def test_role_with_permissions(self):
        mock_role = MagicMock()
        mock_role.permissions = ["project:create", "chapter:write_own", "ai:start_writing"]
        result = get_effective_permissions(role=mock_role)
        assert "project:create" in result
        assert "chapter:write_own" in result
        assert "settings:edit" not in result

    def test_role_with_no_project_permissions(self):
        mock_role = MagicMock()
        mock_role.permissions = ["model:read", "kb:read"]
        result = get_effective_permissions(role=mock_role)
        assert result == []

    def test_no_role_no_admin(self):
        result = get_effective_permissions()
        assert result == []

    def test_filters_non_project_permissions(self):
        mock_role = MagicMock()
        mock_role.permissions = ["project:create", "user:manage", "chapter:write_own", "system:admin"]
        result = get_effective_permissions(role=mock_role)
        assert "project:create" in result
        assert "chapter:write_own" in result
        assert "user:manage" not in result
        assert "system:admin" not in result


class TestGetProjectRolePermissions:
    def test_owner_gets_all(self):
        result = get_project_role_permissions(project_role="owner")
        assert set(result) == set(PROJECT_PERMISSIONS)

    def test_member_gets_system_role_permissions(self):
        mock_role = MagicMock()
        mock_role.permissions = ["chapter:write_own", "approval:review", "approval:view"]
        result = get_project_role_permissions(project_role="member", system_role=mock_role)
        assert "chapter:write_own" in result
        assert "approval:review" in result
        assert "project:edit" not in result
        assert "settings:edit" not in result

    def test_member_with_lead_duty_gets_extra(self):
        mock_role = MagicMock()
        mock_role.permissions = ["chapter:write_own"]
        duties = {"phase-a": {"duty": "lead", "role": "阶段负责人"}}
        result = get_project_role_permissions(
            project_role="member", system_role=mock_role, phase_duties=duties
        )
        assert "chapter:write_own" in result
        assert "member:add" in result
        assert "outline:edit" in result
        assert "ai:start_writing" in result

    def test_member_with_writer_duty(self):
        mock_role = MagicMock()
        mock_role.permissions = []
        duties = {"chapter-1": {"duty": "writer"}}
        result = get_project_role_permissions(
            project_role="member", system_role=mock_role, phase_duties=duties
        )
        assert "chapter:write_own" in result

    def test_member_with_reviewer_duty(self):
        mock_role = MagicMock()
        mock_role.permissions = []
        duties = {"phase-b": {"duty": "reviewer", "dimension": "technical"}}
        result = get_project_role_permissions(
            project_role="member", system_role=mock_role, phase_duties=duties
        )
        assert "chapter:review" in result
        assert "approval:review" in result

    def test_member_no_role_no_duties(self):
        result = get_project_role_permissions(project_role="member", system_role=None)
        assert result == []


class TestHasPermission:
    def test_has(self):
        assert has_permission(["chapter:write_own", "approval:review"], "chapter:write_own") is True

    def test_has_not(self):
        assert has_permission(["chapter:write_own"], "settings:edit") is False

    def test_empty_list(self):
        assert has_permission([], "chapter:write_own") is False
