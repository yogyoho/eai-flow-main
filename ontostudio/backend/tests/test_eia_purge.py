"""eia_purge_v1 清除脚本单测——fake 连接层, 不碰真库.

计划 2026-09-28-eia-ontology-v2-subproject1 Task 2 Step 3: monkeypatch asyncpg.connect
返回 stub（fetch 返假 id 行, execute 返 'DELETE n' 状态串）, 断言:
①计数 dict 形状与取数来源 ②DELETE 依赖序 mentions(entity)→mentions(relation)→relations→merges→entities
③dry-run 只 COUNT 零 DELETE ④空实体集短路 ⑤DSN 解析优先级与 scheme 归一。
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

# scripts/ 不是包——importlib 直接按文件路径加载脚本模块（test_import_eia_samples.py 同法）
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eia_purge_v1.py"
_spec = importlib.util.spec_from_file_location("eia_purge_v1", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["eia_purge_v1"] = _mod
_spec.loader.exec_module(_mod)

purge = _mod.purge
resolve_dsn = _mod.resolve_dsn


class _FakeConn:
    """asyncpg 连接 stub: fetch 恒返假 id 行, execute 恒返固定状态串; 全部 (kind, sql) 记账。"""

    def __init__(self, ids: list[str], delete_status: str = "DELETE 3", count_value: int = 5):
        self.ids = ids
        self.delete_status = delete_status
        self.count_value = count_value
        self.calls: list[tuple[str, str]] = []  # 按到达顺序

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql))
        return [{"id": i} for i in self.ids]

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql))
        return self.count_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql))
        return self.delete_status

    async def close(self):
        self.calls.append(("close", ""))


@pytest.fixture()
def connect_fake(monkeypatch):
    """把脚本模块看到的 asyncpg.connect 换成注入 _FakeConn 的 stub, 实参 dsn 记入 holder。"""
    holder: dict = {}

    def _install(conn: _FakeConn) -> dict:
        async def _connect(dsn):
            holder["dsn"] = dsn
            return conn

        monkeypatch.setattr(_mod.asyncpg, "connect", _connect)
        return holder

    return _install


def test_apply_deletes_in_dependency_order(connect_fake):
    """--apply: DELETE 依赖序钉死——mentions(entity 圈)→mentions(relation 圈)→relations→merges→entities。"""
    conn = _FakeConn(ids=["id-1", "id-2"])
    holder = connect_fake(conn)
    counts = asyncio.run(purge("postgresql://x/db", dry_run=False))
    assert holder["dsn"] == "postgresql://x/db"  # purge 原样把 DSN 交给连接层
    assert "SELECT id FROM dg_entities WHERE domain='eia'" in {sql for _, sql in conn.calls}  # 圈定查询在列
    deletes = [sql for kind, sql in conn.calls if kind == "execute"]
    assert [d.split(" WHERE")[0] for d in deletes] == [
        "DELETE FROM dg_mentions",
        "DELETE FROM dg_mentions",
        "DELETE FROM dg_relations",
        "DELETE FROM dg_merges",
        "DELETE FROM dg_entities",
    ]
    assert "entity_id = ANY($1)" in deletes[0] and "relation_id" in deletes[1]  # 同表两步的圈别可区分
    assert "subject_id = ANY($1) OR object_id = ANY($1)" in deletes[2]  # 关系按实体触达圈定
    assert counts["entities_total"] == 2


def test_apply_returns_deleted_counts(connect_fake):
    """--apply: 计数取自 execute 状态串（'DELETE 3'→3）, 六键齐全。"""
    connect_fake(_FakeConn(ids=["id-1", "id-2"], delete_status="DELETE 3"))
    counts = asyncio.run(purge("postgresql://x/db", dry_run=False))
    assert counts == {
        "entities_total": 2,
        "mentions_by_entity": 3,
        "mentions_by_relation": 3,
        "relations": 3,
        "merges": 3,
        "entities": 3,
    }


def test_dry_run_counts_without_deleting(connect_fake):
    """dry-run: 计数走 COUNT（fetchval）, 全程零 execute——不删任何行。"""
    conn = _FakeConn(ids=["id-1", "id-2"], count_value=7)
    connect_fake(conn)
    counts = asyncio.run(purge("postgresql://x/db", dry_run=True))
    assert counts["entities_total"] == 2
    assert counts["mentions_by_entity"] == 7 and counts["relations"] == 7 and counts["entities"] == 7
    assert all(kind != "execute" for kind, _ in conn.calls)  # 零 DELETE
    assert sum(1 for kind, _ in conn.calls if kind == "fetchval") == 5  # 五步全部只 COUNT


def test_empty_entity_set_short_circuits(connect_fake):
    """无 eia 实体: 仅圈定查询即返回全零计数（防空数组 ANY($1) 类型推断坑）。"""
    conn = _FakeConn(ids=[])
    connect_fake(conn)
    counts = asyncio.run(purge("postgresql://x/db", dry_run=False))
    assert counts == {"entities_total": 0}
    assert [kind for kind, _ in conn.calls] == ["fetch", "close"]  # 零 COUNT 零 DELETE


def test_resolve_dsn_priority_and_scheme_normalization(monkeypatch):
    """--dsn > ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig（EXTENSIONS_DB_*）; +asyncpg scheme 归一。"""
    assert resolve_dsn("postgresql://explicit/db") == "postgresql://explicit/db"  # 显式参数最优先
    monkeypatch.delenv("ONTOSTUDIO_PG_DSN", raising=False)
    monkeypatch.setenv("EXTENSIONS_DB_HOST", "pg-host")
    monkeypatch.setenv("EXTENSIONS_DB_PORT", "6543")
    monkeypatch.setenv("EXTENSIONS_DB_USER", "u1")
    monkeypatch.setenv("EXTENSIONS_DB_PASSWORD", "p1")
    monkeypatch.setenv("EXTENSIONS_DB_NAME", "d1")
    assert resolve_dsn(None) == "postgresql://u1:p1@pg-host:6543/d1"  # 缺省与 app/config.py DatabaseConfig 同源
    monkeypatch.setenv("ONTOSTUDIO_PG_DSN", "postgresql+asyncpg://u:p@h:5432/d")
    assert resolve_dsn(None) == "postgresql://u:p@h:5432/d"  # env 次优先 + SQLAlchemy scheme 归一为 asyncpg 形态
