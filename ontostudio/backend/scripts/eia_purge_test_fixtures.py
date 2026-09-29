#!/usr/bin/env python3
"""清除 doc_graph 域测试夹具污染（测试写真库事故的存量清理）——EAI-CUSTOM.

背景（实体库被"测试实体/批量实体/E2E"刷屏）: 集成/e2e 测试对 extensions 真库直写且无清理——
tests/test_actions_executor.py 写 '测试实体'、test_actions_batch.py 写 '批量实体'、
test_actions_e2e.py 写 'E2E'；宿主机 5432 恒可达（eai-flow-postgres-ext 已发布端口）,
每次跑 pytest 积累一批。T0 实测（2026-09-30）doc_graph 域 1254 行全是夹具:
    LIKE '测试%' 792 + '批量实体%' 236 + 'E2E%' 226（三族之和恰为域内全部行）。
eia 域 2521 行是真数据——**红线, 绝不动**: 本脚本选择集恒带 domain='doc_graph' 过滤,
且前后各打印一次 eia 行数自证不变。

删除范围: doc_graph 域内三族命名行及其下游（FK 依赖序, 手法照抄 eia_purge_v1.py）:
    mentions(entity 圈) → mentions(relation 圈) → relations(两端圈) → merges → entities
（dg_merges.candidate_id/canonical_id 外键指向 dg_entities 且无级联, 实体删除前必须清;
 dg_action_audit 无外键, 纯日志, 保留作操作留痕, 不在本脚本范围。）
防误删红线: doc_graph 域中名字不像夹具的行一律保留并列报告（宁可少删）。

DSN 解析与 eia_purge_v1.py 同法: --dsn > env ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig
（EXTENSIONS_DB_HOST/PORT/USER/PASSWORD/NAME, 与 app/config.py 同源; asyncpg 不认
 postgresql+asyncpg:// scheme, 在此归一为 postgresql://）。

用法:
    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_purge_test_fixtures.py             # dry-run（默认）, 只打印计数与抽样
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_purge_test_fixtures.py --apply                             # 真删（用户已批准 2026-09-30）
配套根治: tests 写库门禁见 tests/conftest.py（ONTOSTUDIO_TEST_ALLOW_REAL_DB=1 才放行）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ 非包: 运行时补 backend 根（与 eia_purge_v1.py 同法）

from app.config import DatabaseConfig  # noqa: E402 (sys.path 先插入)

_DOMAIN = "doc_graph"  # 红线: 选择集恒带域过滤, eia 域绝不触碰
_NAME_FAMILIES = ("测试%", "批量实体%", "E2E%")

_NAME_PREDICATE = " OR ".join(f"canonical_name LIKE '{fam}'" for fam in _NAME_FAMILIES)
_SELECT_IDS = f"SELECT id FROM dg_entities WHERE domain='{_DOMAIN}' AND ({_NAME_PREDICATE})"

# (label, DELETE, COUNT) 三元组; 顺序即执行顺序（FK 依赖序, 见模块 docstring）; $1 = 夹具实体 id 数组
_STEPS: list[tuple[str, str, str]] = [
    ("mentions_by_entity", "DELETE FROM dg_mentions WHERE entity_id = ANY($1)", "SELECT count(*) FROM dg_mentions WHERE entity_id = ANY($1)"),
    (
        "mentions_by_relation",
        "DELETE FROM dg_mentions WHERE relation_id IN (SELECT id FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1))",
        "SELECT count(*) FROM dg_mentions WHERE relation_id IN (SELECT id FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1))",
    ),
    ("relations", "DELETE FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1)", "SELECT count(*) FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1)"),
    # FK 加固（与 eia_purge_v1.py 同）: dg_merges 外键指向 dg_entities, 实体删除前必须清
    ("merges", "DELETE FROM dg_merges WHERE candidate_id = ANY($1) OR canonical_id = ANY($1)", "SELECT count(*) FROM dg_merges WHERE candidate_id = ANY($1) OR canonical_id = ANY($1)"),
    ("entities", "DELETE FROM dg_entities WHERE id = ANY($1)", "SELECT count(*) FROM dg_entities WHERE id = ANY($1)"),
]


def resolve_dsn(explicit: str | None = None) -> str:
    """DSN 解析: --dsn > env ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig（EXTENSIONS_DB_*）.

    asyncpg 不认 SQLAlchemy 的 postgresql+asyncpg:// scheme → 统一归一为 postgresql://。
    """
    dsn = explicit or os.getenv("ONTOSTUDIO_PG_DSN") or DatabaseConfig.from_env().sync_url
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def purge(dsn: str, dry_run: bool) -> dict[str, object]:
    """按依赖序清除 doc_graph 域夹具; dry_run 只 COUNT 不删。返回计数与留痕信息（直接打印报告）。"""
    conn = await asyncpg.connect(dsn)
    try:
        eia_before = int(await conn.fetchval("SELECT count(*) FROM dg_entities WHERE domain='eia'"))
        domain_total = int(await conn.fetchval(f"SELECT count(*) FROM dg_entities WHERE domain='{_DOMAIN}'"))
        ids = [r["id"] for r in await conn.fetch(_SELECT_IDS)]

        # 抽样留痕: 将删行首 10 例（红线条目: 删除前必须列出样例）
        samples = await conn.fetch(
            f"SELECT id, canonical_name, status FROM dg_entities WHERE domain='{_DOMAIN}' AND ({_NAME_PREDICATE}) ORDER BY created_at LIMIT 10"
        )
        print(f"\n[将删实体] {len(ids)} 行 / doc_graph 域共 {domain_total} 行; 抽样首 10 例:")
        for s in samples:
            print(f"    {s['id']}  {s['canonical_name']!r}  status={s['status']}")

        # 防误删红线: 域内不像夹具命名的行 = 全域 − 三族选择集; 一律保留
        kept = domain_total - len(ids)
        print(f"[保留例外] doc_graph 域不像夹具命名的行: {kept} 行（一律不动, 宁可少删）")
        if kept:
            for r in await conn.fetch(
                f"SELECT id, canonical_name, status FROM dg_entities WHERE domain='{_DOMAIN}' AND NOT ({_NAME_PREDICATE}) ORDER BY created_at LIMIT 10"
            ):
                print(f"    KEPT {r['id']}  {r['canonical_name']!r}  status={r['status']}")
        print(f"[红线自证] eia 域行数（删前）: {eia_before}")

        counts: dict[str, object] = {"entities_total": len(ids), "kept_exceptions": kept, "eia_before": eia_before}
        if not ids:  # 空集短路: 免空数组 ANY($1) 的类型推断坑, 也省连接内往返
            counts["eia_after"] = eia_before
            return counts
        for label, del_sql, cnt_sql in _STEPS:
            # 同一 SQL 语义的显式双分支: dry-run 走 COUNT, --apply 走 DELETE（状态串 'DELETE n' 取尾数）
            counts[label] = int(await conn.fetchval(cnt_sql, ids)) if dry_run else int((await conn.execute(del_sql, ids)).split()[-1])

        # 复核: --apply 后 doc_graph 域残留（应恰等于保留例外数）与 eia 红线
        resid_total = int(await conn.fetchval(f"SELECT count(*) FROM dg_entities WHERE domain='{_DOMAIN}'"))
        resid_fams = await _family_counts(conn)
        eia_after = int(await conn.fetchval("SELECT count(*) FROM dg_entities WHERE domain='eia'"))
        counts["doc_graph_residual"] = resid_total
        counts["residual_family_hits"] = resid_fams
        counts["eia_after"] = eia_after
        return counts
    finally:
        await conn.close()


async def _family_counts(conn: asyncpg.Connection) -> dict[str, int]:
    """doc_graph 域内三族命中数（复核残留用; 全为 0 才算清干净）。"""
    sel = ", ".join(f"count(*) FILTER (WHERE canonical_name LIKE '{fam}') AS f{i}" for i, fam in enumerate(_NAME_FAMILIES))
    row = await conn.fetchrow(f"SELECT {sel} FROM dg_entities WHERE domain='{_DOMAIN}'")
    return {fam: row[f"f{i}"] for i, fam in enumerate(_NAME_FAMILIES)}


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台/管道打印中文不炸（与 eia_purge_v1.py 同法）
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description=f"清除 doc_graph 域测试夹具（{_NAME_FAMILIES} 三族及下游）; 默认 dry-run, eia 域绝不触碰")
    ap.add_argument("--dry-run", action="store_true", help="只打印计数不删（默认行为, 显式写出仅为可读性）")
    ap.add_argument("--apply", action="store_true", help="不加此参数一律 dry-run")
    ap.add_argument("--dsn", default=None, help="显式 asyncpg DSN; 缺省走 ONTOSTUDIO_PG_DSN 或 EXTENSIONS_DB_* 平台配置")
    args = ap.parse_args(argv)
    counts = asyncio.run(purge(resolve_dsn(args.dsn), dry_run=not args.apply))
    mode = "APPLY(已删除)" if args.apply else "dry-run(未删任何行)"
    print(f"\n[{mode}] {counts}")
    if not args.apply:
        print("确认计数与抽样无误后, 追加 --apply 真删。")
    elif counts.get("residual_family_hits") and any(counts["residual_family_hits"].values()):
        sys.exit("残留三族命中非零——删除不彻底, 请人工核查。")


if __name__ == "__main__":
    main()
