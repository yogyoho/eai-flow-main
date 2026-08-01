"""Tests for RoleOverlayStore — atomic write + mtime optimistic lock."""

import asyncio
import uuid as uuid_mod

import pytest

from app.extensions.models import Role
from app.extensions.role.service import RoleOverlayStore, RoleService
from app.extensions.schemas import RoleUpdate


def test_read_merge_write_roundtrip(tmp_path):
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("""
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: []
""", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    data = store.read()
    assert "custom" in data["roles"]

    data["roles"]["custom2"] = {
        "display_name": "自定义2", "permissions": ["kb:read"], "nav": [], "data_scopes": []
    }
    store.write(data)
    reloaded = store.read()
    assert "custom2" in reloaded["roles"]


def test_stale_overlay_rejected(tmp_path):
    import os

    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    mtime0 = store.mtime()
    overlay.write_text(
        "roles:\n  a: { display_name: 'A', permissions: [], nav: [], data_scopes: [] }\ndisabled_roles: []\n",
        encoding="utf-8",
    )
    # Simulate a concurrent edit advancing the file mtime. Direct re-write is
    # insufficient on coarse-mtime filesystems (two writes within the same
    # resolution quantum keep an identical st_mtime), so advance it explicitly.
    os.utime(overlay, (mtime0 + 2.0, mtime0 + 2.0))
    with pytest.raises(RuntimeError):
        store.write(store.read(), expect_mtime=mtime0)


class _FakeResult:
    """Mimics sqlalchemy Result for fetchone/scalar_one_or_none."""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self._it = iter(self._rows)

    def fetchone(self):
        return next(self._it, None)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    """Minimal AsyncSession stand-in for RoleService.update_role unit test.

    Raw `SELECT id FROM roles` (used by _calibrate_single_role) returns an
    empty result so the INSERT path is taken; ORM `select(Role)` returns the
    newly-added role.
    """

    def __init__(self, existing_role=None):
        self.existing_role = existing_role
        self.added = []
        self.committed = False

    async def execute(self, stmt, params=None):
        if "SELECT id FROM roles" in str(stmt):
            return _FakeResult()
        row = self.existing_role or (self.added[0] if self.added else None)
        return _FakeResult(rows=[row] if row is not None else [])

    async def commit(self):
        self.committed = True

    def add(self, obj):
        self.added.append(obj)


class _FakeRegistry:
    """Registry whose defaults carry a built-in role's yaml definition."""

    def get_role_defaults(self, code):
        return {
            "display_name": "部门主管",
            "permissions": ["#inherit:base", "doc:write"],
            "nav": ["nav:knowledge"],
            "data_scopes": ["knowledge_dept"],
            "is_system": True,
            "level": 15,
            "description": "默认描述",
        }

    def resolve_role_permissions(self, code):
        return {"doc:write"}

    def get_data_scope(self, scope_id):
        known = {"knowledge_dept", "knowledge_owner"}
        return scope_id if scope_id in known else None

    def reload(self):
        pass


def test_update_role_builtin_preserves_registry_defaults(tmp_path, monkeypatch):
    """update_role on a built-in role (not yet in overlay) synthesizes the overlay
    entry from registry defaults — preserving data_scopes/is_system and keeping
    #inherit markers so inheritance stays dynamic (not flattened)."""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()
    # update_role's bare get_permission_registry() uses service's module-level binding;
    # notify_registry_reload() re-imports from auth.registry inside the store method.
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="部门主管",
        code="dept_head",
        permissions=["doc:write"],
        is_system=True,
        level=15,
        description="旧描述",
        nav=["nav:knowledge"],
    )
    fake_db = _FakeDb()

    result = asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(name="新名称")))

    entry = store.read()["roles"]["dept_head"]
    assert entry["display_name"] == "新名称"  # data.name applied on top of defaults
    assert entry["data_scopes"] == ["knowledge_dept"]  # preserved from defaults
    assert entry["is_system"] is True  # preserved from defaults
    assert entry["permissions"] == ["#inherit:base", "doc:write"]  # #inherit kept, not flattened
    assert entry["level"] == 15
    assert entry["description"] == "默认描述"
    assert result is not None and result.code == "dept_head"
    assert fake_db.committed


def test_update_role_rejects_unknown_data_scope(tmp_path, monkeypatch):
    """update_role must reject scope ids absent from the registry (deny-by-default
    hardening) — the overlay must not be written for an unknown scope."""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="部门主管",
        code="dept_head",
        permissions=["doc:write"],
        is_system=True,
        level=15,
        description="旧描述",
        nav=["nav:knowledge"],
    )
    fake_db = _FakeDb()

    with pytest.raises(ValueError):
        asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(data_scopes=["bogus_scope"])))

    # validation happens before store.write → nothing persisted on disk
    assert "dept_head" not in store.read()["roles"]


def test_update_role_persists_valid_data_scope(tmp_path, monkeypatch):
    """update_role persists data_scopes only when every id exists in the registry."""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="部门主管",
        code="dept_head",
        permissions=["doc:write"],
        is_system=True,
        level=15,
        description="旧描述",
        nav=["nav:knowledge"],
    )
    fake_db = _FakeDb()

    result = asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(data_scopes=["knowledge_dept"])))

    entry = store.read()["roles"]["dept_head"]
    assert entry["data_scopes"] == ["knowledge_dept"]
    assert result is not None and result.code == "dept_head"
    assert fake_db.committed
