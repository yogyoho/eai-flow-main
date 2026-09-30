#!/usr/bin/env python3
"""EIA 图谱双库归属打标（ontostudio 子项目 3.5 §1/§3）——attrs JSONB 三态标，零 DDL.

EAI-CUSTOM(2026-09-30, 子项目 3.5): 给 dg_entities/dg_relations（eia 域）打
  attrs.scope = "sample"        （样例类比素材——现存语料主体；§3: 判定回填后按判定分诊，
                                 本轮 v1 一律 sample、碎片不清除）
  attrs.source_report = <slug>  （从 dg_mentions.document_id 反解 `eia-batch:<slug>`；无
                                 mention 的行标 "unknown" 并计数）
  attrs.distillable = true      （仅可蒸馏共性 etype——供 B 库蒸馏筛选；默认
                                 treatment_measure/pollutant/standard_threshold，可覆写）
B 库挂载点 domain_common / C 库 project 本轮只注册类型与机制，不填充数据（§1）。

eia 域之外零触碰：实体 UPDATE 带 `AND domain='eia'` 谓词级保险；关系只取 eia 实体触达边
（与 eia_purge_v1.py 圈定同法），跨域边仅计报不区别对待。

默认 dry-run（只打印计数）；--apply 真写（只写 attrs，不动其他列）；--report-only 只看现状分布。
--ids-file <json> 可传 {"entities": [...], "relations": [...]} 限定打标范围——供判定回填后
的 §3 分诊轮使用（如只打「正确实体+无意义碎片」行）。

用法:
    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_scope_tag.py               # dry-run
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_scope_tag.py --report-only                         # 现状分布
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_scope_tag.py --apply                               # 真打标
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ 非包: 运行时补 backend 根

from app.config import DatabaseConfig  # noqa: E402 (sys.path 先插入)

# 与 eia_quality_sample.py 同目录：子项目 3.5 产物集中一处，主会话判定/打标只看一个目录
OUT_DIR = Path(__file__).parent / "eia_quality_sample_out"
REPORT_NAME = "scope_tag_report.json"

# §3 可蒸馏共性 etype 默认集（"等"字保守取点名三项；判定回填后可用 --distillable-etypes 扩）
DISTILLABLE_ETYPES_DEFAULT = ("treatment_measure", "pollutant", "standard_threshold")

# document_id 前缀 → slug 反解（与 eia_quality_sample.py.parse_slug 同规则，脚本非包故就地复制）
_DOC_PREFIXES = ("eia-batch:", "eia-sample:")

# eia 域触达的关系圈定（与 eia_purge_v1.py 同法定义「eia 的关系」：subject/object 任一触达）
_EIA_REL_TOUCH = (
    "EXISTS (SELECT 1 FROM dg_entities e WHERE e.id = r.subject_id AND e.domain='eia') "
    "OR EXISTS (SELECT 1 FROM dg_entities e WHERE e.id = r.object_id AND e.domain='eia')"
)


def parse_slug(document_id: str | None) -> str | None:
    if not document_id:
        return None
    for prefix in _DOC_PREFIXES:
        if document_id.startswith(prefix):
            return document_id[len(prefix):] or None
    return document_id


def resolve_dsn(explicit: str | None = None) -> str:
    """DSN 解析: --dsn > env ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig（EXTENSIONS_DB_*）——eia_purge_v1.py 同法。"""
    dsn = explicit or os.getenv("ONTOSTUDIO_PG_DSN") or DatabaseConfig.from_env().sync_url
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _parse_attrs(raw: object) -> dict:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _primary_source(counter: Counter | None) -> str:
    """多源取提及数最多者，平局取字典序——确定可复现；无 mention → "unknown"（§1 计数项）。"""
    if not counter:
        return "unknown"
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


async def fetch_distribution(conn) -> dict:
    """现状 attrs.scope 分布（实体=eia 域行；关系=eia 触达边）。"""
    ent = {
        r["scope"]: int(r["n"])
        for r in await conn.fetch(
            "SELECT COALESCE(attrs->>'scope', '(untagged)') AS scope, count(*) AS n FROM dg_entities WHERE domain='eia' GROUP BY 1 ORDER BY 2 DESC, 1"
        )
    }
    rel = {
        r["scope"]: int(r["n"])
        for r in await conn.fetch(
            f"SELECT COALESCE(r.attrs->>'scope', '(untagged)') AS scope, count(*) AS n FROM dg_relations r WHERE {_EIA_REL_TOUCH} GROUP BY 1 ORDER BY 2 DESC, 1"
        )
    }
    return {"entities": ent, "relations": rel}


async def build_plan(conn, *, distillable_etypes: tuple[str, ...], ids_filter: dict | None) -> dict:
    """计算打标计划：每行 patch + 幂等跳过分类；不写库。

    返回 {entities: {rows: [(id, patch)], to_tag, already, unknown_source, distillable},
          relations: {rows, to_tag, already, unknown_source, cross_domain},
          before: 现状分布}
    """
    ent_rows = [
        dict(r)
        for r in await conn.fetch(
            "SELECT id, etype, attrs FROM dg_entities WHERE domain='eia'" + (" AND id = ANY($1)" if ids_filter and ids_filter.get("entities") else ""),
            *( [ids_filter["entities"]] if ids_filter and ids_filter.get("entities") else [] ),
        )
    ]
    rel_rows = [
        dict(r)
        for r in await conn.fetch(
            f"SELECT r.id, r.subject_id, r.object_id, r.attrs FROM dg_relations r WHERE {_EIA_REL_TOUCH}"
            + (" AND r.id = ANY($1)" if ids_filter and ids_filter.get("relations") else ""),
            *( [ids_filter["relations"]] if ids_filter and ids_filter.get("relations") else [] ),
        )
    ]
    eia_ids = {str(r["id"]) for r in await conn.fetch("SELECT id FROM dg_entities WHERE domain='eia'")}

    ent_docs: dict[str, Counter] = {}
    for r in await conn.fetch(
        "SELECT m.entity_id AS eid, m.document_id AS doc, count(*) AS n FROM dg_mentions m JOIN dg_entities e ON e.id = m.entity_id "
        "WHERE e.domain='eia' AND m.entity_id IS NOT NULL GROUP BY 1, 2"
    ):
        slug = parse_slug(r["doc"])
        if slug:
            ent_docs.setdefault(str(r["eid"]), Counter())[slug] += int(r["n"])
    rel_docs: dict[str, Counter] = {}
    for r in await conn.fetch(
        "SELECT relation_id AS rid, document_id AS doc, count(*) AS n FROM dg_mentions WHERE relation_id IS NOT NULL GROUP BY 1, 2"
    ):
        slug = parse_slug(r["doc"])
        if slug and str(r["rid"]) in {str(x["id"]) for x in rel_rows}:
            rel_docs.setdefault(str(r["rid"]), Counter())[slug] += int(r["n"])

    def _plan(rows: list[dict], make_patch, existing_of) -> dict:
        out_rows, to_tag = [], 0
        already = unknown = flag_count = 0
        for row in rows:
            rid = str(row["id"])
            patch = make_patch(row)
            existing = existing_of(row)
            if all(existing.get(k) == v for k, v in patch.items()):
                already += 1  # 幂等：attrs 已与 patch 全等 → 跳过，不重复计数
                continue
            out_rows.append((rid, patch))
            to_tag += 1
            # 计数口径 = 本次写出行（已符行不重复计 unknown/distillable）
            if patch.get("source_report") == "unknown":
                unknown += 1
            if patch.get("distillable") is True:
                flag_count += 1
        return {"rows": out_rows, "to_tag": to_tag, "already": already, "unknown_source": unknown, "distillable": flag_count}

    ent_plan = _plan(
        ent_rows,
        lambda row: {**{"scope": "sample", "source_report": _primary_source(ent_docs.get(str(row["id"])))}, **({"distillable": True} if row["etype"] in distillable_etypes else {})},
        lambda row: _parse_attrs(row["attrs"]),
    )
    rel_plan = _plan(
        rel_rows,
        lambda row: {"scope": "sample", "source_report": _primary_source(rel_docs.get(str(row["id"])))},
        lambda row: _parse_attrs(row["attrs"]),
    )
    rel_plan["cross_domain"] = sum(1 for r in rel_rows if str(r["subject_id"]) not in eia_ids or str(r["object_id"]) not in eia_ids)
    return {"entities": ent_plan, "relations": rel_plan, "before": await fetch_distribution(conn)}


async def apply_plan(conn, plan: dict) -> dict:
    """真写：只 merge attrs（COALESCE||），实体带 domain='eia' 谓词级零触碰保险。返回实际写行数。"""
    ent_sql = "UPDATE dg_entities SET attrs = COALESCE(attrs, '{}'::jsonb) || $2::jsonb WHERE id = $1 AND domain = 'eia'"
    rel_sql = "UPDATE dg_relations SET attrs = COALESCE(attrs, '{}'::jsonb) || $2::jsonb WHERE id = $1"
    written = {"entities": 0, "relations": 0}
    for rid, patch in plan["entities"]["rows"]:
        written["entities"] += int((await conn.execute(ent_sql, rid, json.dumps(patch, ensure_ascii=False))).split()[-1])
    for rid, patch in plan["relations"]["rows"]:
        written["relations"] += int((await conn.execute(rel_sql, rid, json.dumps(patch, ensure_ascii=False))).split()[-1])
    return written


async def run(dsn: str, *, apply: bool, report_only: bool, distillable_etypes: tuple[str, ...], ids_file: str | None) -> dict:
    ids_filter = None
    if ids_file:
        raw = json.loads(Path(ids_file).read_text(encoding="utf-8"))
        ids_filter = raw if isinstance(raw, dict) else None
    conn = await asyncpg.connect(dsn)
    try:
        if report_only:
            return {"mode": "report-only", "executed_at": datetime.now(UTC).isoformat(), "before": await fetch_distribution(conn)}
        plan = await build_plan(conn, distillable_etypes=distillable_etypes, ids_filter=ids_filter)
        report = {
            "mode": "apply" if apply else "dry-run",
            "executed_at": datetime.now(UTC).isoformat(),
            "distillable_etypes": list(distillable_etypes),
            "ids_filter_applied": bool(ids_filter),
            "before": plan.pop("before"),
            "plan": {
                side: {k: v for k, v in p.items() if k != "rows"}
                for side, p in plan.items()
            },
        }
        if apply:
            report["written"] = await apply_plan(conn, plan)
            report["after"] = await fetch_distribution(conn)
        else:
            report["hint"] = "dry-run 未写任何行；确认 plan 计数后加 --apply 真打标（判定回填轮可加 --ids-file 限定范围）"
        return report
    finally:
        await conn.close()


def _fmt_counts(side_plan: dict) -> str:
    return f"待打 {side_plan['to_tag']} / 幂等已符 {side_plan['already']} / unknown 源 {side_plan['unknown_source']}" + (
        f" / distillable {side_plan['distillable']}" if "distillable" in side_plan else f" / 跨域边 {side_plan.get('cross_domain', 0)}"
    )


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description="EIA 归属打标 scope/source_report/distillable（默认 dry-run，只写 attrs）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计数不写（默认行为, 显式写出仅为可读性）")
    ap.add_argument("--apply", action="store_true", help="真写 attrs；不加此参数一律 dry-run")
    ap.add_argument("--report-only", action="store_true", help="只打印现状 attrs.scope 分布，不算计划")
    ap.add_argument("--distillable-etypes", default=",".join(DISTILLABLE_ETYPES_DEFAULT), help="打 distillable 标的 etype 清单（逗号分隔；传空串关闭）")
    ap.add_argument("--ids-file", default=None, help='JSON {"entities": [...], "relations": [...]}——限定打标范围（判定回填轮用；缺省全量）')
    ap.add_argument("--dsn", default=None, help="显式 asyncpg DSN; 缺省走 ONTOSTUDIO_PG_DSN 或 EXTENSIONS_DB_* 平台配置")
    args = ap.parse_args(argv)
    etypes = tuple(e.strip() for e in args.distillable_etypes.split(",") if e.strip())
    report = asyncio.run(run(resolve_dsn(args.dsn), apply=args.apply, report_only=args.report_only, distillable_etypes=etypes, ids_file=args.ids_file))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / REPORT_NAME
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{report['mode']}] 报告落盘: {report_path}")
    if args.report_only:
        print(json.dumps(report["before"], ensure_ascii=False))
        return
    print(f"实体: {_fmt_counts(report['plan']['entities'])}")
    print(f"关系: {_fmt_counts(report['plan']['relations'])}")
    print(f"before 分布: {json.dumps(report['before'], ensure_ascii=False)}")
    if args.apply:
        print(f"已写行: {report['written']}")
        print(f"after 分布: {json.dumps(report['after'], ensure_ascii=False)}")
        print("注意: 内核图需重载（POST /formal/load 或 kernel refresh）后 attr/scope 才对 MCP 消费通道可见。")
    else:
        print("确认无误后加 --apply 真打标。")


if __name__ == "__main__":
    main()
