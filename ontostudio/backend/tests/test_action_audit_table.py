"""审计表随 Base.metadata 注册 + 真实建表路径 + status 枚举含 rejected + 真实 registry 已声明审核动作.

设计: docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §1.2 / §1.3
计划: docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md Task 3
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db import Base
from app.doc_graph.tables import DgActionAudit

_AUDIT_COLUMNS = {
    "id",
    "action_id",
    "domain",
    "target_table",
    "target_pk",
    "actor_id",
    "actor_role",
    "params",
    "before",
    "after",
    "source",
    "created_at",
}


def test_audit_table_registered_in_metadata():
    assert "dg_action_audit" in Base.metadata.tables


def test_audit_columns():
    cols = set(DgActionAudit.__table__.columns.keys())
    assert _AUDIT_COLUMNS <= cols


def test_registry_status_enum_includes_rejected():
    """行为断言（非整份 YAML grep）：graph_entity 的 status enum 必须含 rejected。

    为什么不是 grep：`actions` 段的 `set: rejected` 同样满足「YAML 里有 rejected」——
    从 enum 里删掉 `rejected`（SHACL 无关，但 mcp 属性 dump 与前端过滤会退化）仍是全绿。
    变异检验实测：grep 版 14 passed；本版删 enum 即红。
    """
    from app.ontology.registry import get_registry

    status = next(p for p in get_registry().object_types["graph_entity"].properties if p.name == "status")
    assert status.enum is not None, "graph_entity.status 丢了 enum 声明"
    assert "rejected" in status.enum, status.enum


def test_registry_binds_graph_entity_scope_resource():
    """Task 6 的数据范围解析全按这个 key——缺失即恒 none_allow，动作永远 404。"""
    from app.ontology.registry import get_registry

    assert get_registry().object_types["graph_entity"].scope_resource == "ontology"


def test_real_registry_declares_review_actions():
    """真实 registry 已声明两个审核动作——Task 5/7/8/10 全靠它们。"""
    from app.ontology.registry import get_registry

    reg = get_registry()
    assert reg.get_action("review_entity.confirm") is not None
    assert reg.get_action("review_entity.reject") is not None
    assert reg.get_action("review_entity.confirm").target == "graph_entity"


# ── 真库建表（本任务验收点）────────────────────────────────────────────────────
# 为什么必须是真库测试：本任务第一版只在注释里写了「由 gateway create_all 建表」，而
# 2026-09-17 搬迁把 dg_* 模型从 gateway 的 Base 上摘掉后，**活库里根本没有 dg_action_audit**
# （实测：`\dt dg_*` 只有 4 张表；活 gateway 的 Base.metadata 里 dg_* 为 0）。断言「代码里
# 调了 create_all」抓不到这类洞——metadata 里有表 ≠ 库里有表，故这里读 information_schema。


def _db_ready() -> bool:
    """真库探针（照 tests/test_doc_graph_ingest.py 既有模式）：不可达即跳过。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.ontology.connectors import _ext_url

    async def _probe() -> bool:
        engine = create_async_engine(_ext_url(), poolclass=NullPool, connect_args={"timeout": 2})
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # 任何失败（连接/认证/超时）都视为不可达
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe())
    except Exception:  # 事件循环层面的失败同样视为不可达
        return False


_DB_READY = _db_ready()


async def _audit_columns_in_live_db() -> set[str]:
    """活库 information_schema 里 dg_action_audit 的真实列（不查 metadata）。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.ontology.connectors import _ext_url

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'dg_action_audit'"))
            return {r[0] for r in rows}
    finally:
        await engine.dispose()


def test_lifespan_attempts_table_creation(monkeypatch, caplog):
    """lifespan 必须真的尝试建表——补上面那条真库测试的盲区。

    为什么需要它：真库测试在表**已存在**之后，把 lifespan 里的调用删掉仍然全绿（表在库里）。
    这里不断言「代码里调了某函数」（那正是本轮的教训），而是断言**可观测效果**：把扩展库 URL
    指向不可达地址 → 启动必须留下「建表失败」的 WARNING。删掉那次调用即无日志 → 红。
    顺带钉住降级契约：建表失败不阻断启动（/health 仍 200），只留痕。
    """
    import logging

    from app.main import app
    from app.ontology import connectors

    monkeypatch.setattr(connectors, "_ext_url", lambda: "postgresql+asyncpg://nobody:nope@127.0.0.1:1/none")
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200  # 降级而非致命
        assert health.json()["tables_ready"] is False  # 无表实例必须在 /health 上看得见

    assert any("建表失败" in r.getMessage() for r in caplog.records), [r.getMessage() for r in caplog.records]


def test_health_defaults_tables_ready_false_without_lifespan():
    """未进 lifespan → tables_ready 缺省 False，状态码仍 200。

    用 create_app() 新建实例而非模块级单例：单例的 state 会被别的用例的 lifespan 写过
    （True），读它就成了与用例顺序相关的假断言。
    默认值取 False 而非 None/缺失：读不到就是「没确认建好」，fail-closed 的读法。
    """
    from app.main import create_app

    client = TestClient(create_app())  # 不 with → 不进 lifespan
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["tables_ready"] is False
    assert r.json()["status"] == "ok" and r.json()["service"] == "ontostudio-backend"


def test_ensure_tables_times_out_on_blackhole(monkeypatch):
    """建表不得在黑洞地址上把启动吊死——无 connect_args 时本机实测 21.5s（Linux 可到分钟级）。

    那段窗口里 uvicorn 尚未服务 → healthcheck 失败 → 下游起不来。断言只设上界（10s, 配置值 5s
    的 2 倍裕度）：环境若无路由会立刻失败, 同样通过——本条要抓的是「超时被删掉/被调大」。
    """
    import time

    from app.db import ensure_tables
    from app.ontology import connectors

    monkeypatch.setattr(connectors, "_ext_url", lambda: "postgresql+asyncpg://nobody:nope@10.255.255.1:5432/none")
    started = time.perf_counter()
    with pytest.raises(Exception):  # 黑洞不可达, 必须抛（且必须是超时后抛, 不是吊死）
        asyncio.run(ensure_tables())
    elapsed = time.perf_counter() - started
    assert elapsed < 10.0, f"建表连接没有超时护栏：黑洞地址耗时 {elapsed:.1f}s"


@pytest.mark.integration
@pytest.mark.skipif(not _DB_READY, reason="extensions 库不可达——真库建表验证需 DB（容器内或本地起库后跑）")
def test_lifespan_creates_action_audit_table():
    """验收：进 lifespan（== 容器/服务启动路径）后，dg_action_audit 真的落在活库里。

    走 lifespan 而不是直接调建表函数：覆盖「启动时确实接了这一步」。**残余盲区**：表建出来后
    再把那次调用删掉, 本条仍绿（表已在库）——可观测效果那半边由
    test_lifespan_attempts_table_creation 守, 新环境（离线部署/新库）本条自然变红。
    """
    from app.db import ensure_tables
    from app.main import app

    with TestClient(app) as client:  # lifespan → app.db.ensure_tables()
        # 建表成功必须透出到 /health（否则无表实例照样报健康, 运维看不见）
        assert client.get("/health").json()["tables_ready"] is True

    cols = asyncio.run(_audit_columns_in_live_db())
    assert cols, "lifespan 跑完后 dg_action_audit 仍不在活库里——建表路径没接上"
    assert _AUDIT_COLUMNS <= cols, sorted(_AUDIT_COLUMNS - cols)

    # 幂等（create_all 只建缺失表）：重复启动不得抛错——uvicorn --reload 每轮都进 lifespan
    asyncio.run(ensure_tables())
