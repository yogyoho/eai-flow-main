"""EIA 实体质量抽检脚本单测——fake 连接层, 不碰真库（子项目 3.5 §4, test_eia_purge.py 同法）.

覆盖: seed 可复现 / 分层保底(每 etype ≥ min(3, 层大小)) / 覆盖约束优先(保底总量 > n) /
比例补足(最大余数法) / 无 mention → source_report=unknown / 多源取提及最多者 /
双格式落盘 / slug 反解 / DSN 解析优先级。
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# scripts/ 不是包——importlib 直接按文件路径加载脚本模块（test_eia_purge.py 同法）
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eia_quality_sample.py"
_spec = importlib.util.spec_from_file_location("eia_quality_sample", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["eia_quality_sample"] = _mod
_spec.loader.exec_module(_mod)

collect = _mod.collect
stratified_sample = _mod.stratified_sample
parse_slug = _mod.parse_slug
resolve_dsn = _mod.resolve_dsn
run = _mod.run


class _FakeConn:
    """asyncpg 连接 stub: 按 SQL 特征分发三组结果（实体 / 提及文档计数 / 邻接关系）。"""

    def __init__(self, entity_rows: list[dict], doc_counts: list[dict], rel_rows: list[dict]):
        self.entity_rows = entity_rows
        self.doc_counts = doc_counts
        self.rel_rows = rel_rows
        self.calls: list[str] = []

    async def fetch(self, sql, *args):
        self.calls.append(sql)
        if sql.startswith("SELECT id, etype"):
            return self.entity_rows
        if "FROM dg_mentions m JOIN" in sql:
            return self.doc_counts
        if "FROM dg_relations r JOIN" in sql:
            # 抽中实体 id 由 ANY($1) 传入——stub 直接回全量边（collect 按 adj 字典键自筛）
            return self.rel_rows
        raise AssertionError(f"unexpected sql: {sql[:80]}")

    async def close(self):
        self.calls.append("close")


def _ent(i: int, etype: str, name: str | None = None) -> dict:
    return {"id": f"00000000-0000-0000-0000-{i:012d}", "etype": etype, "canonical_name": name or f"实体{i}", "norm_name": name or f"实体{i}", "attrs": None, "status": "active", "confidence": 0.9}


def _corpus() -> tuple[list[dict], list[dict], list[dict]]:
    ents = [_ent(i, "mine") for i in range(10)] + [_ent(i, "place") for i in range(20, 26)] + [_ent(i, "aquifer") for i in range(30, 32)]
    docs = [{"eid": ents[0]["id"], "doc": "eia-batch:lingtai", "n": 3}, {"eid": ents[0]["id"], "doc": "eia-batch:hengcheng", "n": 5}]
    return ents, docs, []


def _collect_once():
    ents, docs, rels = _corpus()
    return asyncio.run(collect(_FakeConn(ents, docs, rels), n=10, seed=42))


def test_seed_reproducible():
    """同语料同 seed 两次抽样 → 完全同一批 id（固定 seed=42 可复现）。"""
    a, b = _collect_once(), _collect_once()
    assert [e["id"] for e in a["entries"]] == [e["id"] for e in b["entries"]]


def test_seed_changes_sample():
    ents, docs, rels = _corpus()
    conn = _FakeConn(ents, docs, rels)
    a = asyncio.run(collect(conn, n=10, seed=42))
    b = asyncio.run(collect(conn, n=10, seed=7))
    assert [e["id"] for e in a["entries"]] != [e["id"] for e in b["entries"]]


def test_strata_min_coverage_and_proportional_fill():
    """保底 min(3, 层大小) + 余量按层大小比例：A(10) B(6) C(2), n=10 → 每 etype≥3(C 全取2), 总 10。"""
    data = _collect_once()
    by_etype = {s["etype"]: s for s in data["strata"]}
    assert by_etype["mine"]["population"] == 10 and by_etype["mine"]["sampled"] >= 3
    assert by_etype["place"]["population"] == 6 and by_etype["place"]["sampled"] >= 3
    assert by_etype["aquifer"]["sampled"] == 2  # 层大小 < 3 → 全取
    assert sum(s["sampled"] for s in data["strata"]) == len(data["entries"]) == 10


def test_coverage_constraint_dominates_over_n():
    """保底总量 6 > n=1 → 覆盖优先全取保底，strata 带约束说明（§4 实测 35 etype 最小覆盖 102>100 同理）。"""
    ents = [_ent(i, "mine") for i in range(5)] + [_ent(i, "place") for i in range(10, 15)]
    data = asyncio.run(collect(_FakeConn(ents, [], []), n=1, seed=42))
    assert len(data["entries"]) == 6
    assert all("constraint_note" in s for s in data["strata"])


def test_proportional_fill_largest_remainder():
    """A(100) B(5), n=20: 保底 6 + 余量 14 全归 A（B 余量份额 <1 取整为 0）→ A=17, B=3, 总 20。"""
    ents = [_ent(i, "mine") for i in range(100)] + [_ent(i, "place") for i in range(100, 105)]
    data = asyncio.run(collect(_FakeConn(ents, [], []), n=20, seed=42))
    by_etype = {s["etype"]: s["sampled"] for s in data["strata"]}
    assert by_etype == {"mine": 17, "place": 3}
    assert len(data["entries"]) == 20


def test_source_report_majority_and_unknown():
    """primary_source: 多源取提及最多者（hengcheng 5 > lingtai 3）、平局字典序、无 mention → unknown；
    清单 corpus 统计 unknown 行数。"""
    from collections import Counter

    assert _mod.primary_source(Counter({"lingtai": 3, "hengcheng": 5})) == "hengcheng"
    assert _mod.primary_source(Counter({"b": 2, "a": 2})) == "a"  # 平局 → 字典序
    assert _mod.primary_source(None) == "unknown" and _mod.primary_source(Counter()) == "unknown"
    ents, docs, rels = _corpus()
    data = asyncio.run(collect(_FakeConn(ents, docs, rels), n=10, seed=42))
    assert data["corpus"]["unknown_source_entities"] == 17  # 18 实体中仅 ents[0] 有 mention
    sampled_with_docs = [e for e in data["entries"] if e["id"] == ents[0]["id"]]
    if sampled_with_docs:  # ents[0] 恰被抽中时，其多源字段形状须正确
        assert sampled_with_docs[0]["source_report"] == "hengcheng"
        assert sorted(sampled_with_docs[0]["source_reports"]) == ["hengcheng", "lingtai"]


def test_adjacency_summary_in_entries():
    """邻接摘要：层大小 ≤3 全取 → 指定实体必在样本，方向/对端确定性断言。"""
    a1, a2, b1 = _ent(1, "aquifer"), _ent(2, "aquifer"), _ent(3, "place")
    rels = [
        {"sid": a1["id"], "oid": b1["id"], "pred": "located_in", "s_name": "实体1", "s_etype": "aquifer", "o_name": "实体3", "o_etype": "place"},
    ]
    data = asyncio.run(collect(_FakeConn([a1, a2, b1], [], rels), n=10, seed=42))
    assert {e["id"] for e in data["entries"]} == {a1["id"], a2["id"], b1["id"]}
    row = next(e for e in data["entries"] if e["id"] == a1["id"])
    assert row["adjacency"]["total"] == 1
    assert row["adjacency"]["edges"][0] == {"dir": "out", "predicate": "located_in", "other": "实体3", "other_etype": "place"}
    row1 = next(e for e in data["entries"] if e["id"] == b1["id"])
    assert row1["adjacency"]["edges"][0]["dir"] == "in" and row1["adjacency"]["edges"][0]["other"] == "实体1"


@pytest.mark.asyncio
async def test_run_writes_both_formats(tmp_path, monkeypatch):
    """双格式落盘: JSON(判定标准+统计骨架+条目) 与 Markdown(verdict 留空) 均生成。"""
    ents, docs, rels = _corpus()

    async def _connect(dsn):
        assert dsn == "postgresql://x/db"
        return _FakeConn(ents, docs, rels)

    monkeypatch.setattr(_mod.asyncpg, "connect", _connect)
    out = tmp_path / "out"
    json_path = await run("postgresql://x/db", n=10, seed=42, out_dir=out)
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["judgment"]["status"] == "pending"
    assert set(report["judgment"]["standard"]) == {"correct_entity", "wrong_extraction", "meaningless_fragment"}
    assert report["judgment"]["results"] is None
    assert len(report["entries"]) == 10 and all("verdict" not in e for e in report["entries"])
    md = (out / "eia_quality_sample.md").read_text(encoding="utf-8")
    assert "verdict(正确实体/错误抽取/无意义碎片): ______" in md
    assert "| mine | 10 |" in md


def test_parse_slug_prefixes():
    assert parse_slug("eia-batch:lingtai") == "lingtai"
    assert parse_slug("eia-sample:hengcheng") == "hengcheng"
    assert parse_slug("eia-batch:") is None  # 空 slug → None（调用方落 unknown）
    assert parse_slug("other-format:z") == "other-format:z"  # 异形保留原值不丢信息
    assert parse_slug(None) is None and parse_slug("") is None


def test_resolve_dsn_priority(monkeypatch):
    assert resolve_dsn("postgresql://explicit/db") == "postgresql://explicit/db"
    monkeypatch.delenv("ONTOSTUDIO_PG_DSN", raising=False)
    monkeypatch.setenv("EXTENSIONS_DB_HOST", "pg-host")
    monkeypatch.setenv("EXTENSIONS_DB_PORT", "6543")
    monkeypatch.setenv("EXTENSIONS_DB_USER", "u1")
    monkeypatch.setenv("EXTENSIONS_DB_PASSWORD", "p1")
    monkeypatch.setenv("EXTENSIONS_DB_NAME", "d1")
    assert resolve_dsn(None) == "postgresql://u1:p1@pg-host:6543/d1"
    monkeypatch.setenv("ONTOSTUDIO_PG_DSN", "postgresql+asyncpg://u:p@h:5432/d")
    assert resolve_dsn(None) == "postgresql://u:p@h:5432/d"
