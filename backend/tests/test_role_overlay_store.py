"""Tests for RoleOverlayStore — atomic write + mtime optimistic lock."""

import asyncio
import uuid as uuid_mod
from datetime import datetime

import pytest

from app.extensions.models import Role
from app.extensions.role.service import RoleOverlayStore, RoleService
from app.extensions.schemas import RoleUpdate


def test_read_merge_write_roundtrip(tmp_path):
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text(
        """
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: []
""",
        encoding="utf-8",
    )
    store = RoleOverlayStore(overlay_path=str(overlay))
    data = store.read()
    assert "custom" in data["roles"]

    data["roles"]["custom2"] = {"display_name": "自定义2", "permissions": ["kb:read"], "nav": [], "data_scopes": []}
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
            "pages": ["*"],  # T1 review: built-in role default pages (all sub-pages visible)
            "is_system": True,
            "level": 15,
            "description": "默认描述",
        }

    def resolve_role_permissions(self, code):
        return {"doc:write"}

    def get_data_scope(self, scope_id):
        known = {"knowledge_dept", "knowledge_owner"}
        return scope_id if scope_id in known else None

    def get_data_scopes_for_role(self, code):
        return self.get_role_defaults(code).get("data_scopes", [])

    def reload(self):
        pass

    # EAI-CUSTOM: sub-page visibility (pages) fake registry members
    page_ids: set[str] = set()
    role_pages: dict[str, list[str]] = {}

    def page_id_exists(self, page_id):
        return page_id in getattr(self, "page_ids", set())

    def get_page_ids_for_role(self, code):
        return getattr(self, "role_pages", {}).get(code, [])


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
    assert entry["pages"] == ["*"]  # T1 review: non-pages edit preserves sub-page visibility (C1)
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


def test_write_captures_mtime_before_read(tmp_path, monkeypatch):
    """I1: write-through captures mtime BEFORE read, so a concurrent edit landing
    between read and write trips the optimistic lock (was a silent no-op)."""
    import os

    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    # Interpose on read() to simulate a concurrent edit AFTER mtime capture
    # but BEFORE the data is read — the exact window the old code missed.
    orig_mtime = store.mtime
    orig_read = store.read
    orig_write = store.write
    race_fired = False

    def read_spy():
        nonlocal race_fired
        m = orig_mtime()
        os.utime(overlay_path, (m + 2.0, m + 2.0))  # simulate concurrent editor
        race_fired = True
        return orig_read()

    store.mtime = orig_mtime
    store.read = read_spy
    store.write = orig_write

    fake_registry = _FakeRegistry()
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="新角色",
        code="brand_new_role",
        permissions=["doc:write"],
        is_system=False,
        level=1,
        description=None,
        nav=[],
    )
    fake_db = _FakeDb()

    with pytest.raises(RuntimeError):
        asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(name="改名")))
    assert race_fired  # the concurrent edit was simulated and the lock caught it


def test_update_role_preserves_inherit_on_unchanged_permissions(tmp_path, monkeypatch):
    """I3: when the frontend round-trips permissions equal to the resolved set
    (e.g. a name-only edit), the overlay's #inherit markers are preserved —
    the inheritance chain is not flattened."""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text(
        """
roles:
  proj_mgr:
    display_name: "项目经理"
    permissions: ["#inherit:dept_head", "project:edit"]
    nav: []
    data_scopes: []
    is_system: false
    level: 60
disabled_roles: []
""",
        encoding="utf-8",
    )
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()  # resolve_role_permissions returns {"doc:write"}
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="项目经理",
        code="proj_mgr",
        permissions=["doc:write"],  # resolved mirror — what the UI round-trips
        is_system=False,
        level=60,
        description=None,
        nav=[],
    )
    fake_db = _FakeDb()

    # Incoming permissions == resolved set → #inherit markers preserved
    asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(permissions=["doc:write"])))
    entry = store.read()["roles"]["proj_mgr"]
    assert "#inherit:dept_head" in entry["permissions"]  # not flattened

    # Control: a genuinely changed permission set DOES replace the entry
    asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(permissions=["doc:read"])))
    entry = store.read()["roles"]["proj_mgr"]
    assert entry["permissions"] == ["doc:read"]  # replaced (different from resolved)


def test_write_falls_back_to_copy_on_bind_mount(tmp_path, monkeypatch):
    """Docker Desktop bind-mount: os.replace over a mounted file fails with
    Errno 16 (Device or resource busy). write() must fall back to shutil.copy2
    so the overlay update still lands (root cause of 'Extensions database
    is unavailable' 503 on the roles-module toggle)."""
    import shutil

    import app.extensions.role.service as svc

    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))

    def boom(src, dst):
        raise OSError(16, "Device or resource busy")

    monkeypatch.setattr(svc.os, "replace", boom)

    copied = []
    orig_copy2 = shutil.copy2

    def spy_copy2(src, dst):
        copied.append((src, dst))
        return orig_copy2(src, dst)

    monkeypatch.setattr(shutil, "copy2", spy_copy2)

    store.write({"roles": {"x": {"display_name": "X", "permissions": [], "nav": []}}, "disabled_roles": []})

    data = store.read()
    assert "x" in data["roles"]  # write landed via copy2 fallback
    assert len(copied) == 1  # copy2 was used exactly once


def test_update_role_persists_pages(tmp_path, monkeypatch):
    """update_role 写透 pages 到 overlay；校验未知 page id 拒绝。"""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()
    fake_registry.page_ids = {"kf:page:sample", "kf:page:law"}
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(),
        name="部门主管",
        code="dept_head",
        permissions=["kb:read"],
        is_system=False,
        level=50,
        description=None,
        nav=[],
    )
    fake_db = _FakeDb()

    result = asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(pages=["kf:page:sample"])))
    entry = store.read()["roles"]["dept_head"]
    assert entry["pages"] == ["kf:page:sample"]
    assert result is not None and result.code == "dept_head"

    with pytest.raises(ValueError):
        asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(pages=["bogus:page"])))
    entry2 = store.read()["roles"]["dept_head"]
    assert entry2["pages"] == ["kf:page:sample"]


def test_to_response_merges_pages(tmp_path, monkeypatch):
    from app.extensions.role.service import RoleService

    fake_registry = _FakeRegistry()
    fake_registry.role_pages = {"dept_head": ["*"]}
    # to_response 用局部 import 读 app.extensions.auth.registry.get_permission_registry，
    # 两个绑定都 patch 上，否则测试命中真 registry（config-coupled，spec 评审建议）
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    # 瞬时 Role 的 created_at 默认在 flush 时才填充，此处显式提供避免 RoleResponse 校验失败
    role = Role(
        id=uuid_mod.uuid4(),
        name="部门主管",
        code="dept_head",
        permissions=["kb:read"],
        is_system=False,
        level=50,
        description=None,
        nav=[],
        created_at=datetime.now(),
    )
    fake_db = _FakeDb()
    resp = asyncio.run(RoleService.to_response(fake_db, role))
    assert resp.pages == ["*"]
