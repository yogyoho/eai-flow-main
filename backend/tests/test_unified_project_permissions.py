"""Tests for unified project permission resolution (registry-backed).

Verifies get_user_permissions / resolve_user_project_role read the
project_roles section from permissions.yaml via the registry, with the
admin (is_system / wildcard) union bypass.
"""

import asyncio

from app.extensions.auth.unified_permissions import get_user_permissions, resolve_user_project_role


class _FakeResult:
    """Mimics a sqlalchemy Result for scalar_one_or_none()."""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self._it = iter(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Member:
    role = "reviewer"
    phase_duties = None


class _User:
    def __init__(self, role_id=None):
        self.id = "u1"
        self.role_id = role_id


class _Role:
    def __init__(self):
        self.is_system = False
        self.permissions = ["kb:read"]


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


def test_get_user_permissions_non_admin_member(tmp_path, monkeypatch):
    """普通成员按 project_roles 取权限，不属于自己的权限不可见。"""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles: {}
project_roles:
  reviewer: [chapter:review, approval:review]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    db = _FakeDb(member=_Member())
    perms = asyncio.run(get_user_permissions(db, "u1", "p1"))
    assert "chapter:review" in perms
    assert "approval:review" in perms
    assert "project:edit" not in perms


def test_get_user_permissions_admin_union(tmp_path, monkeypatch):
    """管理员（is_system）应拿到所有 project_roles 权限的并集。"""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles: {}
project_roles:
  writer:   [chapter:write_own]
  reviewer: [chapter:review]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    admin_role = _Role()
    admin_role.is_system = True
    db = _FakeDb(user=_User(role_id="r1"), role=admin_role)
    perms = asyncio.run(get_user_permissions(db, "u1", "p1"))
    assert "chapter:write_own" in perms
    assert "chapter:review" in perms


def test_resolve_user_project_role_member(tmp_path, monkeypatch):
    """resolve_user_project_role 返回 ProjectRole 枚举；非成员返回 None。"""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles: {}
project_roles:
  reviewer: [chapter:review]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: reg)

    db = _FakeDb(member=_Member())
    role = asyncio.run(resolve_user_project_role(db, "u1", "p1"))
    assert role is not None
    assert role.value == "reviewer"

    empty_db = _FakeDb(member=None)
    assert asyncio.run(resolve_user_project_role(empty_db, "u1", "p1")) is None
