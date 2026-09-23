"""数据范围端点 + 授权缓存键回归。

EAI-CUSTOM (2026-09-22): 本体动作层经 ``GET /api/permissions/scope`` 取序列化的
``FilterRule`` 做实例级判定（设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3）。
本文件守两件事：
① 缓存键必须是 ``(user_id, permission)`` 复合键——历史实现只按 ``user_id`` 做键，
   而值的语义是"某一次查询的那个权限"，引入第二个权限后即跨权限串味；
② 端点两态（``none_allow`` / ``allow_all``）与未知资源 fail-closed。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rbac_helpers import build_app, make_user

from app.extensions.auth.authz_cache import AuthzCache
from app.extensions.auth.permission_routers import router

# ── 缓存键 ────────────────────────────────────────────────────────────


def test_authz_cache_keys_by_user_and_permission():
    """同一用户查两个权限不得互相污染——历史实现只按 user_id 做键。"""
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "system:access", True)
    c.put(uid, "ontology:action:review", False)
    assert c.get(uid, "system:access") is True
    assert c.get(uid, "ontology:action:review") is False


def test_authz_cache_expires():
    c = AuthzCache(ttl_seconds=0.0)
    uid = uuid.uuid4()
    c.put(uid, "p", True)
    assert c.get(uid, "p") is None


def test_authz_cache_invalidate_user_drops_all_permissions():
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "a", True)
    c.put(uid, "b", False)
    c.invalidate_user(uid)
    assert c.get(uid, "a") is None and c.get(uid, "b") is None


# ── /api/permissions/scope ────────────────────────────────────────────


def _db_with_role(role_code: str) -> AsyncMock:
    """mock session：``db.get(Role, role_id)`` → 带 ``code`` 的行。

    端点用 ``current_user.role_id`` 反查 ``roles.code`` 取 role_code（**不是** ``role_name``，
    实测 ``roles.name`` 是显示名如"超级管理员"，与 registry 的角色 code 不同名）。
    """
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(code=role_code))
    return db


def test_scope_endpoint_none_allow_for_role_without_scope():
    """能访问本体但角色不带 ontology_all → none_allow（域级拒绝，spec §3 今日形态）。"""
    tc = build_app(router, user=make_user(role_name="普通用户"), db=_db_with_role("user"))
    r = tc.get("/api/permissions/scope", params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json() == {"resource": "ontology", "rule": {"operator": "none_allow"}}


def test_scope_endpoint_allow_all_for_role_with_ontology_all():
    """角色带 ontology_all（rule_template: {}）→ allow_all（空模板 = 全量）。"""
    tc = build_app(router, user=make_user(role_name="超级管理员"), db=_db_with_role("superadmin"))
    r = tc.get("/api/permissions/scope", params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json() == {"resource": "ontology", "rule": {"operator": "allow_all"}}


def test_scope_endpoint_unknown_resource_is_none_allow():
    tc = build_app(router, user=make_user(role_name="超级管理员"), db=_db_with_role("superadmin"))
    r = tc.get("/api/permissions/scope", params={"resource": "no_such_module"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] == "none_allow"
