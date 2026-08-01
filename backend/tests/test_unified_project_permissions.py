"""Tests for unified project permission resolution (registry-backed).

Verifies get_user_permissions / resolve_user_project_role read the
project_roles section from permissions.yaml via the registry, with the
admin (is_system / wildcard) union bypass, plus legacy role mapping and
the require_resource_permission compat shim.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.unified_permissions import (
    get_user_permissions,
    require_resource_permission,
    resolve_user_project_role,
)
from app.extensions.models.role_permission import ProjectRole

# Shared registry yaml: superadmin (is_system) + user (system:access) roles,
# plus project_roles for writer/reviewer.
_SHARED_YAML = """
version: 3
modules: {}
roles:
  superadmin: { display_name: "超管", is_system: true, level: 100, permissions: ["*"], nav: [], data_scopes: [] }
  user: { display_name: "用户", is_system: false, level: 1, permissions: ["system:access", "kb:read"], nav: [], data_scopes: [] }
project_roles:
  writer:   [chapter:write_own]
  reviewer: [chapter:review, approval:review]
"""


class _FakeResult:
    """Mimics a sqlalchemy Result for scalar_one_or_none()."""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self._it = iter(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Member:
    def __init__(self, role="reviewer", phase_duties=None):
        self.role = role
        self.phase_duties = phase_duties


class _User:
    def __init__(self, role_id=None):
        self.id = "u1"
        self.role_id = role_id


class _Role:
    def __init__(self):
        self.is_system = False
        self.permissions = ["kb:read"]


class _Request:
    """Minimal stand-in for a FastAPI Request (path_params only)."""

    def __init__(self, project_id="11111111-1111-1111-1111-111111111111"):
        self.path_params = {"project_id": project_id}


class _FakeDb:
    """Stub AsyncSession: returns the configured User/Role/member rows."""

    def __init__(self, member=None, user=None, role=None):
        self._member = member
        self._user = user or _User()
        self._role = role or _Role()

    async def get(self, model, id_):
        name = getattr(model, "__name__", "")
        if name == "User":
            return self._user
        if name == "Role":
            return self._role
        return None

    async def execute(self, stmt, params=None):
        # ProjectMember select returns the member row
        return _FakeResult(rows=[self._member] if self._member else [])


def _make_registry(tmp_path, yaml_text=_SHARED_YAML):
    """Build an isolated PermissionRegistry (no real roles_custom.yaml overlay)."""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text(yaml_text, encoding="utf-8")
    # Explicit missing overlay path so the real roles_custom.yaml can't override.
    return PermissionRegistry(str(main_yaml), overlay_path=str(tmp_path / "roles_custom.yaml"))


def _patch_registry_and_provider(monkeypatch, reg, *, role_code="user"):
    """Monkeypatch get_permission_registry + get_identity_provider for the shim."""
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)
    mock_provider = MagicMock()
    mock_provider.resolve = AsyncMock(
        return_value=AttributeSet(user_id="u1", username="u", role_code=role_code)
    )
    monkeypatch.setattr("app.extensions.auth.identity.get_identity_provider", lambda: mock_provider)


# ── get_user_permissions ──


def test_get_user_permissions_non_admin_member(tmp_path, monkeypatch):
    """普通成员按 project_roles 取权限，不属于自己的权限不可见。"""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    db = _FakeDb(member=_Member())
    perms = asyncio.run(get_user_permissions(db, "u1", "p1"))
    assert "chapter:review" in perms
    assert "approval:review" in perms
    assert "project:edit" not in perms


def test_get_user_permissions_admin_union(tmp_path, monkeypatch):
    """管理员（is_system）应拿到所有 project_roles 权限的并集。"""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    admin_role = _Role()
    admin_role.is_system = True
    db = _FakeDb(user=_User(role_id="r1"), role=admin_role)
    perms = asyncio.run(get_user_permissions(db, "u1", "p1"))
    assert "chapter:write_own" in perms
    assert "chapter:review" in perms
    assert "approval:review" in perms


# ── resolve_user_project_role: legacy mapping + phase-duty override ──


def test_resolve_user_project_role_member(tmp_path, monkeypatch):
    """resolve_user_project_role 返回 ProjectRole 枚举；非成员返回 None。"""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    db = _FakeDb(member=_Member())
    role = asyncio.run(resolve_user_project_role(db, "u1", "p1"))
    assert role is not None
    assert role.value == "reviewer"

    empty_db = _FakeDb(member=None)
    assert asyncio.run(resolve_user_project_role(empty_db, "u1", "p1")) is None


def test_resolve_user_project_role_legacy_member_roles():
    """Legacy member.role values map into the unified taxonomy (I1)."""
    cases = {
        "leader": ProjectRole.PHASE_LEAD,
        "manager": ProjectRole.PHASE_LEAD,
        "editor": ProjectRole.WRITER,
        "member": ProjectRole.WRITER,
        "dept_reviewer": ProjectRole.REVIEWER,
        "company_reviewer": ProjectRole.APPROVER,
        "writer": ProjectRole.WRITER,
    }
    for raw, expected in cases.items():
        db = _FakeDb(member=_Member(role=raw))
        role = asyncio.run(resolve_user_project_role(db, "u1", "p1"))
        assert role == expected, f"{raw!r} should map to {expected}"


def test_resolve_user_project_role_phase_duty_slot_type():
    """phase_duties slot_type overrides member.role; display label is ignored (I2)."""
    # slot_type present → override member.role
    member = _Member(role="member", phase_duties={"p1": {"slot_type": "leader", "role": "组长"}})
    role = asyncio.run(resolve_user_project_role(_FakeDb(member=member), "u1", "p1", phase_node="p1"))
    assert role == ProjectRole.PHASE_LEAD

    # legacy duty key "lead" also maps
    member = _Member(role="member", phase_duties={"p1": {"duty": "lead"}})
    role = asyncio.run(resolve_user_project_role(_FakeDb(member=member), "u1", "p1", phase_node="p1"))
    assert role == ProjectRole.PHASE_LEAD

    # no slot_type (old row with only a display label) → falls back to member.role
    member = _Member(role="writer", phase_duties={"p1": {"role": "组员"}})
    role = asyncio.run(resolve_user_project_role(_FakeDb(member=member), "u1", "p1", phase_node="p1"))
    assert role == ProjectRole.WRITER


# ── require_resource_permission compat shim ──


def test_require_resource_permission_admin_returns_owner(tmp_path, monkeypatch):
    """Admin (is_system role) bypasses the permission check and returns 'owner'."""
    reg = _make_registry(tmp_path)
    _patch_registry_and_provider(monkeypatch, reg, role_code="superadmin")

    db = _FakeDb(member=_Member(role="reviewer"))
    dep = require_resource_permission("project:edit")
    result = asyncio.run(dep(current_user=_User(), request=_Request(), db=db))
    assert result == "owner"


def test_require_resource_permission_member_with_action(tmp_path, monkeypatch):
    """Non-admin member WITH the action → returns the resolved role string."""
    reg = _make_registry(tmp_path)
    _patch_registry_and_provider(monkeypatch, reg, role_code="user")

    db = _FakeDb(member=_Member(role="writer"))
    dep = require_resource_permission("chapter:write_own")
    result = asyncio.run(dep(current_user=_User(), request=_Request(), db=db))
    assert result == "writer"


def test_require_resource_permission_member_without_action_raises_403(tmp_path, monkeypatch):
    """Non-admin member WITHOUT the action → HTTP 403."""
    reg = _make_registry(tmp_path)
    _patch_registry_and_provider(monkeypatch, reg, role_code="user")

    db = _FakeDb(member=_Member(role="writer"))
    dep = require_resource_permission("project:edit")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(current_user=_User(), request=_Request(), db=db))
    assert exc.value.status_code == 403


def test_require_resource_permission_member_without_system_access_raises_403(tmp_path, monkeypatch):
    """A global role lacking system:access is denied even as a project member."""
    reg = _make_registry(tmp_path, """
version: 3
modules: {}
roles:
  limited: { display_name: "受限", is_system: false, level: 5, permissions: ["kb:read"], nav: [], data_scopes: [] }
project_roles:
  writer: [chapter:write_own]
""")
    _patch_registry_and_provider(monkeypatch, reg, role_code="limited")

    db = _FakeDb(member=_Member(role="writer"))
    dep = require_resource_permission("chapter:write_own")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(current_user=_User(), request=_Request(), db=db))
    assert exc.value.status_code == 403


def test_require_resource_permission_missing_project_id_raises_400(tmp_path, monkeypatch):
    """Missing project_id in path → HTTP 400."""
    reg = _make_registry(tmp_path)
    _patch_registry_and_provider(monkeypatch, reg, role_code="user")

    db = _FakeDb(member=_Member(role="writer"))
    dep = require_resource_permission("chapter:write_own")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(current_user=_User(), request=_Request(project_id=None), db=db))
    assert exc.value.status_code == 400


def test_require_resource_permission_invalid_project_id_raises_400(tmp_path, monkeypatch):
    """Invalid (non-UUID) project_id → HTTP 400."""
    reg = _make_registry(tmp_path)
    _patch_registry_and_provider(monkeypatch, reg, role_code="user")

    db = _FakeDb(member=_Member(role="writer"))
    dep = require_resource_permission("chapter:write_own")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(current_user=_User(), request=_Request(project_id="not-a-uuid"), db=db))
    assert exc.value.status_code == 400
