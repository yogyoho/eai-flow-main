"""Tests for _calibrate_roles_from_registry — ensures DB roles mirror yaml registry."""

import asyncio

import pytest

from app.extensions.auth.registry import PermissionRegistry


class FakeResult:
    """Mimics sqlalchemy Result: fetchone/fetchall/scalar."""

    def __init__(self, rows=None, scalar_val=None):
        self._rows = list(rows or [])
        self._scalar_val = scalar_val
        self._it = iter(self._rows)

    def fetchone(self):
        return next(self._it, None)

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar_val


class FakeConn:
    """Records executed SQL; returns configured results per statement shape."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self.db_role_rows = []  # (id, code) returned by SELECT id, code FROM roles

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        sql = str(stmt)
        if "SELECT id, code FROM roles" in sql:
            return FakeResult(rows=self.db_role_rows)
        if "COUNT(*) FROM users" in sql:
            return FakeResult(scalar_val=0)
        if "SELECT id FROM roles WHERE code" in sql:
            return FakeResult()  # no existing row -> INSERT path
        return FakeResult()


def test_calibrate_inserts_all_registry_roles(tmp_path):
    """当 DB 无角色时，所有 registry 角色应走 INSERT 路径。"""
    from app.extensions.database import _calibrate_roles_from_registry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text(
        """
version: 3
modules: {}
roles:
  builtin:
    display_name: "内置"
    is_system: false
    level: 10
    permissions: ["kb:read"]
    nav: ["nav:knowledge"]
    data_scopes: []
disabled_roles: ["stale"]
""",
        encoding="utf-8",
    )
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text(
        """
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: []
""",
        encoding="utf-8",
    )
    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))

    conn = FakeConn()
    asyncio.run(_calibrate_roles_from_registry(conn, reg))
    sql = " ".join(c[0] for c in conn.calls)
    assert "INSERT INTO roles" in sql
    assert reg.list_role_codes()  # builtin + custom exist


def test_calibrate_does_not_delete_disabled_role_with_users(tmp_path):
    """禁用角色仍有用户引用时不得 DELETE（安全守卫）。"""
    from app.extensions.database import _calibrate_roles_from_registry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text(
        """
version: 3
modules: {}
roles:
  keep:
    display_name: "保留"
    is_system: false
    level: 10
    permissions: ["kb:read"]
    nav: []
    data_scopes: []
disabled_roles: ["gone"]
""",
        encoding="utf-8",
    )
    reg = PermissionRegistry(str(main_yaml))

    conn = FakeConn()
    conn.db_role_rows = [("g1", "gone")]

    async def exec_(stmt, params=None):
        conn.calls.append((str(stmt), params))
        sql = str(stmt)
        if "SELECT id FROM roles WHERE code" in sql:
            return FakeResult(rows=[("g1",)])  # gone exists in DB
        if "SELECT id, code FROM roles" in sql:
            return FakeResult(rows=conn.db_role_rows)
        if "COUNT(*) FROM users" in sql:
            return FakeResult(scalar_val=1)  # users still assigned -> must NOT delete
        return FakeResult()

    conn.execute = exec_
    asyncio.run(_calibrate_roles_from_registry(conn, reg))
    sql = " ".join(c[0] for c in conn.calls)
    assert "DELETE FROM roles" not in sql


def test_calibrate_updates_existing_and_deletes_disabled(tmp_path):
    """已有角色走 UPDATE，禁用且无用户引用的角色走 DELETE。"""
    from app.extensions.database import _calibrate_roles_from_registry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text(
        """
version: 3
modules: {}
roles:
  keep:
    display_name: "保留"
    is_system: false
    level: 10
    permissions: ["kb:read"]
    nav: []
    data_scopes: []
disabled_roles: ["gone"]
""",
        encoding="utf-8",
    )
    reg = PermissionRegistry(str(main_yaml))

    conn = FakeConn()
    # Simulate DB already has: keep (id=k1) -> UPDATE path; gone (id=g1) -> DELETE path
    conn.db_role_rows = [("k1", "keep"), ("g1", "gone")]

    # Override the per-code existence lookup so "keep" returns an existing row
    async def exec_(stmt, params=None):
        conn.calls.append((str(stmt), params))
        sql = str(stmt)
        if "SELECT id FROM roles WHERE code" in sql:
            code = (params or {}).get("code")
            if code == "keep":
                return FakeResult(rows=[("k1",)])
            return FakeResult()  # others -> INSERT
        if "SELECT id, code FROM roles" in sql:
            return FakeResult(rows=conn.db_role_rows)
        if "COUNT(*) FROM users" in sql:
            return FakeResult(scalar_val=0)
        return FakeResult()

    conn.execute = exec_
    asyncio.run(_calibrate_roles_from_registry(conn, reg))
    sql = " ".join(c[0] for c in conn.calls)
    assert "UPDATE roles" in sql
    assert "DELETE FROM roles" in sql
