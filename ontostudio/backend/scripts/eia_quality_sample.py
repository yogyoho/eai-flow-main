#!/usr/bin/env python3
"""EIA 实体质量抽检清单生成（ontostudio 子项目 3.5 §4）——先于全量打标，抽检结果指导分诊.

EAI-CUSTOM(2026-09-30, 子项目 3.5): 从 dg_entities(domain='eia') 按 etype 分层随机抽样
（每 etype 至少 3 条——条数不足 3 的 etype 全取；大 etype 按比例补足到 --n 条；固定 seed 可复现）。
产出「待判定清单」（JSON + Markdown 双格式）到 scripts/eia_quality_sample_out/，每条含
id/canonical_name/etype/source_report/邻接关系摘要。真实 LLM 判定（正确实体/错误抽取/
无意义碎片 三档）由主会话完成后再回填——本脚本只产清单，不做任何打标/写库（只读真库）。

覆盖约束优先：当「每 etype ≥3」的最小覆盖总量超过 --n 时（2026-09-30 实测 35 etype
最小覆盖 102 > 100），以覆盖为先、实际抽样数 > n，并在输出 strata 约束说明里如实记录。

用法:
    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_quality_sample.py            # 默认 n=100 seed=42
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_quality_sample.py --n 100 --seed 42 --out-dir <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ 非包: 运行时补 backend 根（与 eia_purge_v1.py 同法）

from app.config import DatabaseConfig  # noqa: E402 (sys.path 先插入)

DEFAULT_OUT_DIR = Path(__file__).parent / "eia_quality_sample_out"
ADJ_CAP = 15  # 单实体邻接边在清单里的展示上限（total 恒为真实总数）

# 三档判定标准（§4）——清单里原样携带，判定方按此逐条打 verdict
JUDGMENT_STANDARD = {
    "correct_entity": "正确实体——真实存在于源文档、指代边界清晰、etype 挂挂正确的抽取结果",
    "wrong_extraction": "错误抽取——指向错误对象/边界错切/etype 错挂/张冠李戴（判定结果决定后续噪声清除范围，本轮仍保留不清除）",
    "meaningless_fragment": "无意义碎片——非实体的碎片字符串（截断残句/表头残留/编号碎屑）；v1 一律保留不清除，仅标记",
}

# 已知 document_id 前缀 → slug 反解（§1）；异形前缀保留原值不丢信息
_DOC_PREFIXES = ("eia-batch:", "eia-sample:")


def parse_slug(document_id: str | None) -> str | None:
    """dg_mentions.document_id → source_report slug（`eia-batch:<slug>` 主形态，兼容 eia-sample:）。"""
    if not document_id:
        return None
    for prefix in _DOC_PREFIXES:
        if document_id.startswith(prefix):
            return document_id[len(prefix):] or None
    return document_id


def resolve_dsn(explicit: str | None = None) -> str:
    """DSN 解析: --dsn > env ONTOSTUDIO_PG_DSN > 平台 DatabaseConfig（EXTENSIONS_DB_*；与 eia_purge_v1.py 同源同法）。"""
    dsn = explicit or os.getenv("ONTOSTUDIO_PG_DSN") or DatabaseConfig.from_env().sync_url
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _parse_attrs(raw: object) -> object:
    """JSONB 列 asyncpg 返回 str——尽力 parse，坏 JSON 原样透传（清单不因脏 attrs 中断）。"""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def primary_source(counter: Counter | None) -> str:
    """多源 slug 取提及数最多者，平局取字典序——确定可复现；无 mention → "unknown"（§1 计数项）。"""
    if not counter:
        return "unknown"
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def stratified_sample(pools: dict[str, list[dict]], n: int, seed: int) -> tuple[list[dict], list[dict]]:
    """按 etype 分层抽样：每层先保底 min(3, 层大小)，余量按层大小比例（最大余数法）补足。

    返回 (样本行列表(按 etype, id 排序), strata 统计列表)。rng 只吃排序后的确定序列——
    同输入 + 同 seed 严格可复现。覆盖约束优先：保底总量超 n 时全取保底（实际数 > n）。
    """
    rng = random.Random(seed)
    etypes = sorted(pools)
    taken: dict[str, list[dict]] = {}
    for et in etypes:  # 保底轮：迭代序 = etype 字典序（确定）
        pool = sorted(pools[et], key=lambda r: str(r["id"]))
        k = min(3, len(pool))
        taken[et] = rng.sample(pool, k)
    guaranteed = sum(len(v) for v in taken.values())
    remaining = n - guaranteed
    constraint_note = None
    if remaining < 0:
        constraint_note = f"每 etype ≥3 的最小覆盖总量 {guaranteed} 超过目标 {n}——覆盖优先，实际抽样 {guaranteed} 条"
        remaining = 0
    if remaining > 0:
        leftover = {et: len(pools[et]) - len(taken[et]) for et in etypes}
        total_left = sum(leftover.values())
        if total_left:
            # 最大余数法分配（份额按未抽层大小比例）；迭代序确定 → rng 调用序确定
            raw_share = {et: leftover[et] * remaining / total_left for et in etypes}
            alloc = {et: int(raw_share[et]) for et in etypes}
            rest = remaining - sum(alloc.values())
            for et in sorted(etypes, key=lambda e: (-(raw_share[e] - int(raw_share[e])), e))[:rest]:
                alloc[et] += 1
            for et in etypes:
                if alloc[et] > 0:
                    pool = sorted((r for r in pools[et] if r not in taken[et]), key=lambda r: str(r["id"]))
                    taken[et] += rng.sample(pool, min(alloc[et], len(pool)))
    sample_rows = [dict(r, _etype=et) for et in etypes for r in sorted(taken[et], key=lambda r: str(r["id"]))]
    strata = [
        {"etype": et, "population": len(pools[et]), "sampled": len(taken[et])}
        for et in etypes
    ]
    if constraint_note:
        for s in strata:
            s["constraint_note"] = constraint_note
    return sample_rows, strata


async def collect(conn, *, n: int, seed: int) -> dict:
    """只读采集 + 抽样 + 组装清单数据（不写库）。"""
    ent_rows = await conn.fetch(
        "SELECT id, etype, canonical_name, norm_name, attrs, status, confidence FROM dg_entities WHERE domain='eia'"
    )
    entities = [dict(r) for r in ent_rows]
    # 实体 → document_id 计数（跨报告去重归并到 slug；多源经 primary_source 取提及最多者）
    doc_counts: dict[str, Counter] = {}
    for r in await conn.fetch(
        "SELECT m.entity_id AS eid, m.document_id AS doc, count(*) AS n FROM dg_mentions m JOIN dg_entities e ON e.id = m.entity_id "
        "WHERE e.domain='eia' AND m.entity_id IS NOT NULL GROUP BY 1, 2"
    ):
        slug = parse_slug(r["doc"])
        if slug:
            doc_counts.setdefault(str(r["eid"]), Counter())[slug] += int(r["n"])

    pools: dict[str, list[dict]] = {}
    for row in entities:
        eid = str(row["id"])
        counter = doc_counts.get(eid)
        pools.setdefault(row["etype"], []).append(
            {
                "id": eid,
                "etype": row["etype"],
                "canonical_name": row["canonical_name"],
                "norm_name": row["norm_name"],
                "attrs": _parse_attrs(row["attrs"]),
                "status": row["status"],
                "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
                "source_report": primary_source(counter),
                "source_reports": sorted(counter) if counter else [],
            }
        )
    sample_rows, strata = stratified_sample(pools, n=n, seed=seed)

    # 邻接关系摘要（只查被抽中实体触达的边）
    ids = [r["id"] for r in sample_rows]
    adj: dict[str, list[dict]] = {r["id"]: [] for r in sample_rows}
    if ids:
        for r in await conn.fetch(
            "SELECT r.subject_id AS sid, r.object_id AS oid, r.predicate AS pred, "
            "se.canonical_name AS s_name, se.etype AS s_etype, oe.canonical_name AS o_name, oe.etype AS o_etype "
            "FROM dg_relations r JOIN dg_entities se ON se.id = r.subject_id JOIN dg_entities oe ON oe.id = r.object_id "
            "WHERE r.subject_id = ANY($1) OR r.object_id = ANY($1)",
            ids,
        ):
            for side in ("sid", "oid"):
                key = str(r[side])
                if key in adj:
                    adj[key].append(
                        {
                            "dir": "out" if side == "sid" else "in",
                            "predicate": r["pred"],
                            "other": r["o_name"] if side == "sid" else r["s_name"],
                            "other_etype": r["o_etype"] if side == "sid" else r["s_etype"],
                        }
                    )
    for row in sample_rows:
        edges = sorted(adj[row["id"]], key=lambda e: (e["dir"], e["predicate"], e["other"] or ""))
        row["adjacency"] = {"total": len(edges), "edges": edges[:ADJ_CAP]}
    unknown_cnt = sum(1 for pools_list in pools.values() for r in pools_list if r["source_report"] == "unknown")
    return {
        "entries": sample_rows,
        "strata": strata,
        "corpus": {"entities": len(entities), "etypes": len(pools), "unknown_source_entities": unknown_cnt},
    }


def build_report(data: dict, *, n: int, seed: int) -> dict:
    """清单 JSON 报告体：元数据 + 分层统计 + 判定标准/统计骨架 + 待判定条目。"""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": "ontostudio 子项目 3.5 §4 实体质量抽检——待判定清单（判定由主会话 LLM 回填，本文件不含判定结果）",
        "domain": "eia",
        "seed": seed,
        "target_n": n,
        "sampled_total": len(data["entries"]),
        "corpus": data["corpus"],
        "strata": data["strata"],
        "judgment": {
            "status": "pending",
            "standard": JUDGMENT_STANDARD,
            "how_to_fill": "主会话跑 LLM 逐条判 entries[*].verdict ∈ {correct_entity, wrong_extraction, meaningless_fragment}（可附 note），回填 judgment.results（per_etype/per_verdict 统计）后交回打标脚本分诊",
            "results": None,
            "stats_skeleton": {"per_verdict": {"correct_entity": None, "wrong_extraction": None, "meaningless_fragment": None}, "per_etype": {}},
        },
        "entries": [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in data["entries"]
        ],
    }


def build_markdown(report: dict) -> str:
    """判定工作表 Markdown：三档标准 + 分层统计骨架 + 逐条待判定块（verdict 留空）。"""
    lines = [
        "# EIA 实体质量抽检清单（子项目 3.5 §4）",
        "",
        f"- 生成: {report['generated_at']}　seed={report['seed']}　目标 n={report['target_n']}　实际抽样 **{report['sampled_total']}** 条",
        f"- 语料: {report['corpus']['entities']} 实体 / {report['corpus']['etypes']} etype / 无 mention 行 {report['corpus']['unknown_source_entities']}（source_report=unknown）",
        "- 判定由主会话 LLM 逐条填写 `verdict` 后回填（本清单不含判定结果）；判定结果决定噪声清除范围——本轮一律保留不清除。",
        "",
        "## 三档判定标准",
        "",
    ]
    for key, desc in JUDGMENT_STANDARD.items():
        lines.append(f"- **{key}**: {desc}")
    lines += ["", "## 分层统计（population / sampled）", "", "| etype | 语料 | 抽样 |", "|---|---|---|"]
    for s in report["strata"]:
        lines.append(f"| {s['etype']} | {s['population']} | {s['sampled']} |")
    lines += ["", "## 统计骨架（判定回填）", "", "```json", json.dumps(report["judgment"]["stats_skeleton"], ensure_ascii=False, indent=2), "```", "", "## 待判定条目", ""]
    for i, row in enumerate(report["entries"], 1):
        attrs = json.dumps(row["attrs"], ensure_ascii=False)
        if len(attrs) > 400:
            attrs = attrs[:400] + "…"
        lines.append(f"### {i}. [{row['etype']}] {row['canonical_name']}")
        lines.append(f"- id: `{row['id']}`　status: {row['status']}　confidence: {row['confidence']}　source_report: {row['source_report']}")
        if len(row.get("source_reports") or []) > 1:
            lines.append(f"- 多源: {', '.join(row['source_reports'])}")
        lines.append(f"- attrs: {attrs}")
        adj = row["adjacency"]
        if adj["total"]:
            desc = "; ".join(f"{'出' if e['dir'] == 'out' else '入'}边 {e['predicate']} → {e['other']}({e['other_etype']})" for e in adj["edges"])
            lines.append(f"- 邻接({adj['total']}): {desc}")
        else:
            lines.append("- 邻接: 无")
        lines.append("- verdict(正确实体/错误抽取/无意义碎片): ______")
        lines.append("")
    return "\n".join(lines)


async def run(dsn: str, *, n: int, seed: int, out_dir: Path) -> Path:
    conn = await asyncpg.connect(dsn)
    try:
        data = await collect(conn, n=n, seed=seed)
    finally:
        await conn.close()
    report = build_report(data, n=n, seed=seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eia_quality_sample.json"
    md_path = out_dir / "eia_quality_sample.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")
    return json_path


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台中文不炸（eia_purge_v1.py 同法）
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description="EIA 实体质量抽检清单生成（只读真库；判定由主会话回填）")
    ap.add_argument("--n", type=int, default=100, help="目标抽样条数（默认 100；覆盖约束优先时实际数可 > n）")
    ap.add_argument("--seed", type=int, default=42, help="随机种子（默认 42，可复现）")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 scripts/eia_quality_sample_out/）")
    ap.add_argument("--dsn", default=None, help="显式 asyncpg DSN; 缺省走 ONTOSTUDIO_PG_DSN 或 EXTENSIONS_DB_* 平台配置")
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    json_path = asyncio.run(run(resolve_dsn(args.dsn), n=args.n, seed=args.seed, out_dir=out_dir))
    print(f"抽检清单落盘: {json_path}（+ 同名 .md）")
    print("下一步: 主会话跑 LLM 逐条判定（三档标准见清单头），回填后再跑 eia_scope_tag.py 分诊打标。")


if __name__ == "__main__":
    main()
