"""EIA 归属打标脚本单测——fake 连接层, 不碰真库（子项目 3.5 §1/§3, test_eia_purge.py 同法）.

覆盖: dry-run 零写 / apply 只 merge attrs 且实体 SQL 带 domain='eia' 零触碰保险 /
幂等已符跳过 / distillable 仅默认三 etype / 无 mention → unknown 计数 / 跨域边计报 /
report-only 只看分布 / --ids-file 限定范围 / DSN 解析优先级。
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# scripts/ 不是包——importlib 直接按文件路径加载脚本模块（test_eia_purge.py 同法）
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eia_scope_tag.py"
_spec = importlib.util.spec_from_file_location("eia_scope_tag", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["eia_scope_tag"] = _mod
_spec.loader.exec_module(_mod)

build_plan = _mod.build_plan
apply_plan = _mod.apply_plan
run = _mod.run
resolve_dsn = _mod.resolve_dsn
DISTILLABLE_DEFAULT = _mod.DISTILLABLE_ETYPES_DEFAULT

E1, E2, E3 = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000003"
R1, R2 = "10000000-0000-0000-0000-000000000001", "10000000-0000-0000-0000-000000000002"


class _FakeConn:
    """asyncpg 连接 stub: 按 SQL 特征分发（实体/关系/圈定/提及计数/分布）; execute 记账。

    实体/关系取数若带 ANY($1)（--ids-file 限定）则按参数模拟 SQL 层过滤。
    """

    def __init__(self, entity_rows: list[dict], rel_rows: list[dict], doc_counts: list[dict] | None = None, rel_docs: list[dict] | None = None):
        self.entity_rows = entity_rows
        self.rel_rows = rel_rows
        self.doc_counts = doc_counts or []
        self.rel_docs = rel_docs or []
        self.executes: list[tuple[str, object, object]] = []

    @staticmethod
    def _filter_by_ids(rows: list[dict], args: tuple) -> list[dict]:
        if not args:
            return rows
        wanted = {str(x) for x in args[0]}
        return [r for r in rows if str(r["id"]) in wanted]

    async def fetch(self, sql, *args):
        if sql.startswith("SELECT id, etype"):
            return self._filter_by_ids(self.entity_rows, args)
        if sql.startswith("SELECT r.id, r.subject_id"):
            return self._filter_by_ids(self.rel_rows, args)
        if sql.startswith("SELECT id FROM dg_entities"):
            return [{"id": r["id"]} for r in self.entity_rows]
        if "FROM dg_mentions m JOIN" in sql:
            return self.doc_counts
        if "FROM dg_mentions WHERE relation_id" in sql:
            return self.rel_docs
        if "COALESCE(attrs->>'scope'" in sql:
            return [{"scope": "(untagged)", "n": len(self.entity_rows)}]
        if "COALESCE(r.attrs->>'scope'" in sql:
            return [{"scope": "(untagged)", "n": len(self.rel_rows)}]
        raise AssertionError(f"unexpected sql: {sql[:80]}")

    async def execute(self, sql, *args):
        self.executes.append((sql, *args))
        return "UPDATE 1"

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def _out_dir(tmp_path, monkeypatch):
    """OUT_DIR 是模块级绝对路径——测试统一改指 tmp（run() 每次都落报告，绝不写真仓目录）。"""
    monkeypatch.setattr(_mod, "OUT_DIR", tmp_path / "out")


def _rows():
    ents = [
        {"id": E1, "etype": "treatment_measure", "attrs": None},
        {"id": E2, "etype": "place", "attrs": json.dumps({"scope": "sample", "source_report": "lingtai"})},  # 幂等已符
        {"id": E3, "etype": "pollutant", "attrs": json.dumps({"legacy": 1})},
    ]
    rels = [
        {"id": R1, "subject_id": E1, "object_id": E2, "attrs": None},
        {"id": R2, "subject_id": E2, "object_id": "99999999-ffff-0000-0000-000000000009", "attrs": json.dumps({"scope": "sample", "source_report": "unknown"})},  # 跨域边 + 幂等已符
    ]
    docs = [
        {"eid": E1, "doc": "eia-batch:lingtai", "n": 4},
        {"eid": E1, "doc": "eia-batch:yining", "n": 1},
        {"eid": E2, "doc": "eia-batch:lingtai", "n": 1},  # E2 预打标 source_report=lingtai 的证据源（幂等已符的前提）
    ]
    return ents, rels, docs


@pytest.fixture()
def connect_fake(monkeypatch):
    """run() 的 asyncpg.connect 打桩（test_eia_purge.py 同法），实参 dsn 记入 holder。"""
    holder: dict = {}

    def _install(conn: _FakeConn) -> dict:
        async def _connect(dsn):
            holder["dsn"] = dsn
            return conn

        monkeypatch.setattr(_mod.asyncpg, "connect", _connect)
        return holder

    return _install


def test_dry_run_writes_nothing(connect_fake):
    ents, rels, docs = _rows()
    conn = _FakeConn(ents, rels, docs)
    holder = connect_fake(conn)
    report = asyncio.run(run("postgresql://x/db", apply=False, report_only=False, distillable_etypes=DISTILLABLE_DEFAULT, ids_file=None))
    assert holder["dsn"] == "postgresql://x/db"
    assert report["mode"] == "dry-run" and "hint" in report
    assert report["plan"]["entities"]["to_tag"] == 2 and report["plan"]["entities"]["already"] == 1
    assert report["plan"]["entities"]["distillable"] == 2  # 本次写入口径: E1(treatment_measure) + E3(pollutant)
    assert report["plan"]["entities"]["unknown_source"] == 1  # E3 无 mention
    assert report["plan"]["relations"]["to_tag"] == 1 and report["plan"]["relations"]["already"] == 1
    assert report["plan"]["relations"]["cross_domain"] == 1  # R2 客体非 eia
    assert conn.executes == []  # dry-run 零写


def test_apply_merges_attrs_with_eia_guard(connect_fake):
    """apply: 实体 UPDATE 带 AND domain='eia' 谓词级保险；patch 走 COALESCE||jsonb merge。"""
    ents, rels, docs = _rows()
    conn = _FakeConn(ents, rels, docs)
    connect_fake(conn)
    report = asyncio.run(run("postgresql://x/db", apply=True, report_only=False, distillable_etypes=DISTILLABLE_DEFAULT, ids_file=None))
    ent_sqls = [s for s, *_ in conn.executes if s.startswith("UPDATE dg_entities")]
    rel_sqls = [s for s, *_ in conn.executes if s.startswith("UPDATE dg_relations")]
    assert len(ent_sqls) == 2 and len(rel_sqls) == 1
    assert all("AND domain = 'eia'" in s for s in ent_sqls)  # 零触碰保险
    assert all("COALESCE(attrs, '{}'::jsonb) || $2::jsonb" in s for s, *_ in conn.executes)  # 只 merge attrs
    patch = json.loads(conn.executes[0][2])
    assert patch == {"scope": "sample", "source_report": "lingtai", "distillable": True}  # E1 多源取提及最多者
    assert report["written"] == {"entities": 2, "relations": 1}
    assert report["after"]["entities"] == {"(untagged)": 3}  # stub 分布恒返 untagged（真库由 SQL 算）


def test_distillable_flag_default_etypes_only():
    ents, rels, docs = _rows()
    conn = _FakeConn(ents, rels, docs)
    plan = asyncio.run(build_plan(conn, distillable_etypes=DISTILLABLE_DEFAULT, ids_filter=None))
    patches = {rid: p for rid, p in plan["entities"]["rows"]}
    assert "distillable" in patches[E1] and "distillable" in patches[E3]
    assert "distillable" not in (patches.get(E2) or {})  # 幂等行根本不在 rows
    # place 永不进默认集——用 E2 强制重打场景验证：清空 distillable 后 place 行也无标记
    plan2 = asyncio.run(build_plan(_FakeConn(ents, rels, docs), distillable_etypes=(), ids_filter=None))
    assert plan2["entities"]["distillable"] == 0


def test_unknown_source_counted():
    ents, rels, docs = _rows()
    conn = _FakeConn(ents, rels, docs, rel_docs=[])  # R1 无 relation mention → unknown
    plan = asyncio.run(build_plan(conn, distillable_etypes=DISTILLABLE_DEFAULT, ids_filter=None))
    assert plan["relations"]["unknown_source"] == 1
    patch = {rid: p for rid, p in plan["relations"]["rows"]}[R1]
    assert patch == {"scope": "sample", "source_report": "unknown"}


def test_ids_file_restricts_scope(tmp_path):
    ents, rels, docs = _rows()
    ids_file = tmp_path / "ids.json"
    ids_file.write_text(json.dumps({"entities": [E1, E2], "relations": [R2]}), encoding="utf-8")
    conn = _FakeConn(ents, rels, docs)
    plan = asyncio.run(build_plan(conn, distillable_etypes=DISTILLABLE_DEFAULT, ids_filter=json.loads(ids_file.read_text(encoding="utf-8"))))
    assert {rid for rid, _ in plan["entities"]["rows"]} == {E1}  # E3 被 ids 限定排除
    assert plan["relations"]["to_tag"] == 0  # R2 幂等已符且是唯一范围内关系


def test_report_only_distribution(connect_fake):
    ents, rels, docs = _rows()
    conn = _FakeConn(ents, rels, docs)
    connect_fake(conn)
    report = asyncio.run(run("postgresql://x/db", apply=False, report_only=True, distillable_etypes=DISTILLABLE_DEFAULT, ids_file=None))
    assert report["mode"] == "report-only" and "before" in report and "plan" not in report


def test_resolve_dsn_priority(monkeypatch):
    assert resolve_dsn("postgresql://explicit/db") == "postgresql://explicit/db"
    monkeypatch.delenv("ONTOSTUDIO_PG_DSN", raising=False)
    monkeypatch.setenv("EXTENSIONS_DB_HOST", "pg-host")
    monkeypatch.setenv("EXTENSIONS_DB_PORT", "6543")
    monkeypatch.setenv("EXTENSIONS_DB_USER", "u1")
    monkeypatch.setenv("EXTENSIONS_DB_PASSWORD", "p1")
    monkeypatch.setenv("EXTENSIONS_DB_NAME", "d1")
    assert resolve_dsn(None) == "postgresql://u1:p1@pg-host:6543/d1"
