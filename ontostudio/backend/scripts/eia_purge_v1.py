#!/usr/bin/env python3
"""清除 v1 环评实例数据（domain='eia'）——spec 2026-09-28 §6 同步动作.

EAI-CUSTOM（计划 docs/superpowers/plans/2026-09-28-eia-ontology-v2-subproject1.md Task 2）:
用户定案完全重构, dg_entities/dg_relations/dg_mentions 中 eia 域 v1 数据（1041 实体+关系+提及）清除。
dg_relations/dg_mentions 无 domain 列 → 以实体 id 间接圈定（关系按 subject/object 触达,
提及按 entity_id / relation_id 双圈）。

删除顺序（依赖序, 防外键约束）:
    mentions(entity 圈) → mentions(relation 圈) → relations → merges → entities
  计划外加固说明: 计划骨架为四步（无 merges）; dg_merges.candidate_id/canonical_id 外键指向
  dg_entities.id 且无 ON DELETE 级联（app/doc_graph/tables.py DgMerge）——实体删除前不清合并
  留痕, --apply 必撞 ForeignKeyViolation。故在 relations 与 entities 之间插入 merges 一步,
  其余顺序与计划一致。dry-run 会一并打印 merges 计数供 Task 11 执行前复核。

DSN 解析优先级（计划 Step 1 勘误: 本仓无单值 DSN env, 平台约定为 EXTENSIONS_DB_* 五元组）:
    1) --dsn 显式参数
    2) env ONTOSTUDIO_PG_DSN（计划占位名, 保留作覆盖口）
    3) 平台配置 DatabaseConfig.from_env().sync_url（EXTENSIONS_DB_HOST/PORT/USER/PASSWORD/NAME,
       与 app/config.py 同源; asyncpg 不认 postgresql+asyncpg:// scheme, 在此归一为 postgresql://）

用法:
    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_purge_v1.py             # dry-run（默认）, 只打印计数
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_purge_v1.py --apply                             # 真删（计划: 推迟到 Task 11 定型后执行）
清除后由调用方触发 kernel 重新 load（/formal/load 空态）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ 非包: 运行时补 backend 根（与 import_eia_samples.py 同法）

from app.config import DatabaseConfig  # noqa: E402 (sys.path 先插入)

# (label, DELETE, COUNT) 三元组; 顺序即执行顺序（依赖序, 见模块 docstring）; $1 = eia 实体 id 数组
_STEPS: list[tuple[str, str, str]] = [
    ("mentions_by_entity", "DELETE FROM dg_mentions WHERE entity_id = ANY($1)", "SELECT count(*) FROM dg_mentions WHERE entity_id = ANY($1)"),
    (
        "mentions_by_relation",
        "DELETE FROM dg_mentions WHERE relation_id IN (SELECT id FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1))",
        "SELECT count(*) FROM dg_mentions WHERE relation_id IN (SELECT id FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1))",
    ),
    ("relations", "DELETE FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1)", "SELECT count(*) FROM dg_relations WHERE subject_id = ANY($1) OR object_id = ANY($1)"),
    # 计划外加固（见模块 docstring）: dg_merges 外键指向 dg_entities, 实体删除前必须清
    ("merges", "DELETE FROM dg_merges WHERE candidate_id = ANY($1) OR canonical_id = ANY($1)", "SELECT count(*) FROM dg_merges WHERE candidate_id = ANY($1) OR canonical_id = ANY($1)"),
    ("entities", "DELETE FROM dg_entities WHERE id = ANY($1)", "SELECT count(*) FROM dg_entities WHERE id = ANY($1)"),
]


def resolve_dsn(explicit: str | None = None) -> str:
    """DSN 解析: --dsn > env ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig（EXTENSIONS_DB_*）.

    asyncpg 不认 SQLAlchemy 的 postgresql+asyncpg:// scheme → 统一归一为 postgresql://。
    """
    dsn = explicit or os.getenv("ONTOSTUDIO_PG_DSN") or DatabaseConfig.from_env().sync_url
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def purge(dsn: str, dry_run: bool) -> dict[str, int]:
    """按依赖序清除 eia 域实例; dry_run 只 COUNT 不删。返回各步计数（entities_total=圈定实体数）。"""
    conn = await asyncpg.connect(dsn)
    try:
        ids = [r["id"] for r in await conn.fetch("SELECT id FROM dg_entities WHERE domain='eia'")]
        counts: dict[str, int] = {"entities_total": len(ids)}
        if not ids:  # 空集短路: 免空数组 ANY($1) 的类型推断坑, 也省连接内往返
            return counts
        for label, del_sql, cnt_sql in _STEPS:
            # 同一 SQL 语义的显式双分支: dry-run 走 COUNT, --apply 走 DELETE（状态串 'DELETE n' 取尾数）
            counts[label] = int(await conn.fetchval(cnt_sql, ids)) if dry_run else int((await conn.execute(del_sql, ids)).split()[-1])
        return counts
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台/管道打印中文不炸（与 import_eia_samples.py 同法）
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description="清除 v1 环评实例数据（domain='eia'）; 默认 dry-run")
    ap.add_argument("--dry-run", action="store_true", help="只打印计数不删（默认行为, 显式写出仅为可读性）")
    ap.add_argument("--apply", action="store_true", help="不加此参数一律 dry-run")
    ap.add_argument("--dsn", default=None, help="显式 asyncpg DSN; 缺省走 ONTOSTUDIO_PG_DSN 或 EXTENSIONS_DB_* 平台配置")
    args = ap.parse_args(argv)
    counts = asyncio.run(purge(resolve_dsn(args.dsn), dry_run=not args.apply))
    mode = "APPLY(已删除)" if args.apply else "dry-run(未删任何行)"
    print(f"[{mode}] {counts}")
    if not args.apply:
        print("确认计数无误后, 追加 --apply 真删（计划: 真删推迟到 Task 11 定型后执行）。")


if __name__ == "__main__":
    main()
