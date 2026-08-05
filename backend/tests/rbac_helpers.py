"""共享 RBAC 深度测试工具：canned identity、policy mock、smart_db、app builder。

跑在 gateway 容器内；registry 读真实 config/permissions.yaml + roles_custom.yaml。
DB 一律 mock（仓库"无 live-PG 集成测试"惯例），identity 经 monkeypatch get_identity_provider。
"""
from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser


def make_user(role_name: str = "user", **kw) -> CurrentUser:
    return CurrentUser(
        id=kw.get("id", uuid.uuid4()),
        username=kw.get("username", "tester"),
        email=kw.get("email", "tester@eai-flow.com"),
        full_name=kw.get("full_name", "Tester"),
        role_id=kw.get("role_id", uuid.uuid4()),  # require_permission 对所有人先查 role_id
        role_name=role_name,
        dept_id=kw.get("dept_id"),
        dept_name=kw.get("dept_name"),
        status="active",
    )


def fake_identity(role_code: str = "user", **kw) -> AttributeSet:
    return AttributeSet(
        user_id=kw.get("user_id", str(uuid.uuid4())),
        username=kw.get("username", "tester"),
        role_code=role_code,
        role_level=kw.get("role_level", 0),
        dept_id=kw.get("dept_id"),
        dept_ids=kw.get("dept_ids", []),
        member_projects=kw.get("member_projects", []),
        project_roles=kw.get("project_roles", {}),
        tags=kw.get("tags", []),
        labels=kw.get("labels", {}),
    )


class FakeIdentityProvider:
    """resolve() 返回 canned identity；monkeypatch get_identity_provider 指向它。"""

    def __init__(self, identity: AttributeSet):
        self._identity = identity

    async def resolve(self, user_id, db):  # noqa: ARG002
        return self._identity


def patch_identity(monkeypatch, identity: AttributeSet) -> FakeIdentityProvider:
    """让 with_data_scope / /me / require_permission / require_resource_permission 拿到 canned identity。

    源模块（identity）必有 get_identity_provider，patch 它覆盖所有惰性 import 调用点；
    消费模块若在模块顶层 import（如 permission_routers），则属性已绑定，需在消费模块上
    再 patch 一次。逐个探测：模块没有该属性（=纯惰性 import）就跳过。
    """
    provider = FakeIdentityProvider(identity)
    for mod_name in (
        "app.extensions.auth.identity",
        "app.extensions.auth.permission_routers",
        "app.extensions.auth.unified_permissions",
        "app.extensions.auth.middleware",
    ):
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "get_identity_provider"):
            monkeypatch.setattr(mod, "get_identity_provider", lambda: provider)
    return provider


def policy_row(name: str = "p", priority: int = 0, conditions: dict | None = None, grants: dict | None = None) -> SimpleNamespace:
    """duck-typed PolicyModel 行——load_active_policies 只读 name/priority/conditions/grants。"""
    return SimpleNamespace(name=name, priority=priority, conditions=conditions or {}, grants=grants or {})


def policy_rows_db(rows: list | None = None):
    """mock 的 AsyncSession：execute().scalars().all() 返回 rows（load_active_policies 专属）。

    用于不涉及端点数据查询、只走 policy 加载的测试（/me、deny→端点、with_data_scope）。
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows or [])
    db.execute.return_value = result
    return db


def smart_db(*, policy_rows: list | None = None, doc_row=None, kb_row=None, member_row=None):
    """AsyncMock session 按 SQL 形状路由 execute() 结果。

    - 含 "policies" → scalars().all() = policy_rows（load_active_policies 用）
    - 含 "ai_documents" / "folders" → scalar_one_or_none = doc_row；scalars().all = [doc_row]
    - 含 "knowledge_bases" → scalar_one_or_none = kb_row
    - 含 "project_members" → scalar_one_or_none = member_row
    - 其它 → 空
    """
    db = AsyncMock()

    def _execute(stmt, *a, **k):  # noqa: ARG001
        sql = str(stmt)
        result = MagicMock()
        if "policies" in sql:
            result.scalars.return_value.all.return_value = list(policy_rows or [])
        elif "ai_documents" in sql or "folders" in sql:
            result.scalar_one_or_none.return_value = doc_row
            result.scalars.return_value.all.return_value = [doc_row] if doc_row else []
        elif "knowledge_bases" in sql:
            result.scalar_one_or_none.return_value = kb_row
            result.scalars.return_value.all.return_value = [kb_row] if kb_row else []
        elif "project_members" in sql:
            result.scalar_one_or_none.return_value = member_row
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    return db


def build_app(router, *, user: CurrentUser | None = None, db=None) -> TestClient:
    """TestClient app：override get_current_user + get_db，含目标 router。

    每请求清 permission ContextVar 缓存——真实 uvicorn 每请求独立 task 天然隔离，
    TestClient 在同一 context 连续请求会泄漏（_request_engine/_request_identity），
    这里镜像真实隔离语义。
    """
    app = FastAPI()
    app.include_router(router)
    u = user or make_user()
    session = db if db is not None else AsyncMock()

    @app.middleware("http")
    async def _clear_perm_cache(request, call_next):  # noqa: ARG001
        from app.extensions.auth.cache import clear_permission_cache
        clear_permission_cache()
        return await call_next(request)

    async def _user():
        return u

    async def _db():
        yield session

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app, raise_server_exceptions=False)


def capture_sql(db):
    """取最近一次 db.execute 的编译 SQL（小写、含字面值）。"""
    stmt = db.execute.await_args.args[0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
