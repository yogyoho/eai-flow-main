#!/usr/bin/env python3
"""EIA domain_pattern 入图（ontostudio 子项目 5 交付 2；2026-09-30 归并深化版）——B 库蒸馏产物写 dg_* 真相源.

EAI-CUSTOM(2026-09-30, 子项目 5): 写库脚本（eia 域内），不碰容器。

用法:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py            # dry-run（默认）
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --apply                            # 真写
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --min-support 2 --apply            # 扩量门槛
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --min-support 2 --apply --prune    # + 归并同步（删除已吸收旧节点）
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --refined scripts/eia_pattern_mine_out/refined_desc.json --apply   # 精炼描述入 attrs

输入 = scripts/eia_pattern_mine_out/patterns.json（交付 1 归并版产物），取 support_count >= --min-support 的候选：
  - 每条一个 domain_pattern 节点：etype=domain_pattern（B 库挂载点, eia.yaml 已注册 DomainPattern）、
    scope=domain_common、attrs 记 pattern_type/subject/object/support/source_reports/pattern_desc
    （+归并版 subject_variants/object_variants 变体名清单）；--refined 时叠加 refined=true/refined_desc/refined_at；
  - 两侧 analogous_to 边连到既有实体：subject —analogous_to→ pattern，object 侧按既有部署语义对调端点。
    **变体连边（归并深化）**：挖掘侧把变体名（ss/悬浮/悬浮物…、有资质的单位/有资质的危废处置公司…）
    记入 subject_variants/object_variants（变体名+实际 etype），本脚本逐变体按自然键 (domain,etype,norm_name)
    查找端点实体并全部连边——规范名实体与变体实例都指向同一 pattern；查无即跳过该边（不强行连边）。
    兼容旧 patterns.json（无 variants 字段时回退单端点 subject_name/object_etype）。

幂等：节点走 uq_dg_entities_natural ON CONFLICT 原位更新（attrs JSONB || 合并）；边先查
(s,predicate,o) 已存在即跳过（dg_relations 无唯一约束）；--prune 重跑删 0。重跑不重复。
事务：单事务全量提交，失败整体回滚。

--prune（归并同步，显式 opt-in）：归并后规范 pattern 换 pattern_id（md5 含规范名），旧变体节点
不再在新候选集内——删除其 analogous_to 边后再删节点（dg_relations 先行，防 FK）；只删
attrs->>'pattern_id' 非空且不在新候选集的脚本自产节点（人工 pattern 无 pattern_id 不触碰）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DatabaseConfig  # noqa: E402

MINE_OUT = Path(__file__).parent / "eia_pattern_mine_out" / "patterns.json"
DOMAIN = "eia"
PATTERN_ETYPE = "domain_pattern"
EDGE_PREDICATE = "analogous_to"  # 实例 —类比于→ 领域模式（既有谓词，语义=该实体是模式的样例实例）
CONFIDENCE = 0.95
NAME_MAX = 300  # dg_entities.norm_name String(300)


def _clip(name: str, pattern_id: str) -> str:
    """pattern_name 超 norm_name 列宽时截断并拼 pattern_id 保唯一。EAI-CUSTOM bug-3412:
    旧式 `NAME_MAX - 11` 假设 pattern_id 长 10，实际 dp-+10hex=13 → 截断后仍 303>300 溢列宽，按实际长度计算。"""
    if len(name) <= NAME_MAX:
        return name
    return name[: NAME_MAX - len(pattern_id) - 1] + "-" + pattern_id


def _load_candidates(min_support: int) -> list[dict]:
    payload = json.loads(MINE_OUT.read_text(encoding="utf-8"))
    entries = [e for entries in payload["patterns"].values() for e in entries]
    candidates = sorted(
        (e for e in entries if e["support_count"] >= min_support),
        key=lambda e: (-e["support_count"], e["pattern_id"]),
    )
    print(f"输入 {len(entries)} 配对，support>={min_support} 候选 {len(candidates)} 条")
    return candidates


def _load_refined(path: Path | None) -> dict[str, dict]:
    """精炼描述 JSON：{pattern_id: {refined_desc: str, ...}}；`_` 前缀键（_meta 等）跳过；缺字段显式报错。"""
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    bad = [k for k, v in data.items() if not isinstance(v, dict) or not v.get("refined_desc")]
    if bad:
        raise SystemExit(f"--refined 文件存在缺 refined_desc 的条目: {bad[:5]}")
    print(f"精炼描述 {len(data)} 条（{path.name}）")
    return data


def _variant_endpoints(e: dict, role: str) -> list[tuple[str, str | None]]:
    """role 侧端点 (norm_name, etype) 清单：归并版用 variants（变体名+实际 etype），旧格式回退单端点。"""
    variants = e.get(f"{role}_variants") or []
    if variants:
        return [(v["name"], v.get("etype")) for v in variants]
    return [(e[f"{role}_name"], e.get(f"{role}_etype"))]


async def _run(candidates: list[dict], apply: bool, refined: dict[str, dict], prune: bool) -> None:
    cfg = DatabaseConfig.from_env()
    dsn = f"postgresql://{cfg.username}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.name}"
    conn = await asyncpg.connect(dsn)
    counts = {
        "nodes_insert": 0,
        "nodes_update": 0,
        "edges_add": 0,
        "edges_exist": 0,
        "endpoint_missing": 0,
        "name_clipped": 0,
        "refined_applied": 0,
        "prune_edges_del": 0,
        "prune_nodes_del": 0,
    }
    missing_samples: list[str] = []
    pruned_samples: list[str] = []
    derived_edges: set[tuple[str, str]] = set()  # 本轮候选推导出的 (instance_id, pattern_side) 实边集（--prune 边同步基准）
    try:
        async with conn.transaction():
            now = datetime.now(UTC).isoformat()
            for e in candidates:
                is_placeholder = False  # dry-run 新建场景：pattern 无库内 id，边推导跳过
                attrs = {
                    "scope": "domain_common",
                    "pattern_id": e["pattern_id"],
                    "pattern_type": e["pattern_type"],
                    "subject_name": e["subject_name"],
                    "subject_etype": e["subject_etype"],
                    "object_name": e["object_name"],
                    "object_etype": e["object_etype"],
                    "predicate": e["predicate"],
                    "support_count": e["support_count"],
                    "occurrence_count": e["occurrence_count"],
                    "source_reports": "、".join(e["source_reports"]),  # 图内 attr 投影为字符串字面量，列表存「、」串
                    "pattern_desc": e["pattern_desc"],
                    "mined_at": now,
                }
                for role in ("subject", "object"):
                    names = [v["name"] for v in e.get(f"{role}_variants", [])]
                    if names:
                        attrs[f"{role}_variants"] = "、".join(names)
                ref = refined.get(e["pattern_id"])
                if ref:
                    attrs["refined"] = True
                    attrs["refined_desc"] = ref["refined_desc"]
                    attrs["refined_at"] = ref.get("refined_at", now)
                    counts["refined_applied"] += 1
                norm = _clip(e["pattern_name"], e["pattern_id"])
                if norm != e["pattern_name"]:
                    counts["name_clipped"] += 1
                if apply:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status)
                        VALUES ($1, $2, $3, $3, CAST($4 AS jsonb), $5, 'active')
                        ON CONFLICT (domain, etype, norm_name)
                          DO UPDATE SET attrs = dg_entities.attrs || EXCLUDED.attrs,
                            confidence = GREATEST(dg_entities.confidence, EXCLUDED.confidence),
                            updated_at = NOW()
                        RETURNING id, (xmax = 0) AS inserted
                        """,
                        DOMAIN,
                        PATTERN_ETYPE,
                        norm,
                        json.dumps(attrs, ensure_ascii=False),
                        CONFIDENCE,
                    )
                    counts["nodes_insert" if row["inserted"] else "nodes_update"] += 1
                    pattern_id = row["id"]
                else:
                    # dry-run 只读判存在：命中=将原位更新，未命中=将新建（不写任何行）
                    existing = await conn.fetchrow(
                        "SELECT id FROM dg_entities WHERE domain=$1 AND etype=$2 AND norm_name=$3",
                        DOMAIN,
                        PATTERN_ETYPE,
                        norm,
                    )
                    counts["nodes_update" if existing else "nodes_insert"] += 1
                    if existing:
                        pattern_id = existing["id"]
                    else:
                        pattern_id = uuid4()  # 占位：新节点在 dry-run 中无真实 id
                        is_placeholder = True

                edge_attrs = json.dumps({"scope": "domain_common", "pattern_name": norm, "mined_by": "eia_pattern_mine"}, ensure_ascii=False)
                for role in ("subject", "object"):
                    # 变体连边：规范名实体 + 各变体实例都指向同一 pattern（查无即跳过，不强行连边）
                    connected: set = set()
                    for vname, vetype in _variant_endpoints(e, role):
                        endpoint = await conn.fetchrow(
                            "SELECT id FROM dg_entities WHERE domain=$1 AND etype=$2 AND norm_name=$3",
                            DOMAIN,
                            vetype,
                            vname,
                        )
                        if endpoint is None or endpoint["id"] in connected:
                            if endpoint is None:
                                counts["endpoint_missing"] += 1
                                missing_samples.append(f"{e['pattern_id']}:{role}={vname}({vetype})")
                            continue
                        connected.add(endpoint["id"])
                        instance_id, pattern_side = endpoint["id"], pattern_id
                        if role == "object":  # object 侧按既有部署语义对调端点
                            instance_id, pattern_side = pattern_id, endpoint["id"]
                        if not is_placeholder:
                            derived_edges.add((instance_id, pattern_side))  # dry-run 占位节点跳过（新节点无库内边）
                        exists = await conn.fetchval(
                            "SELECT 1 FROM dg_relations WHERE subject_id=$1 AND predicate=$2 AND object_id=$3",
                            instance_id,
                            EDGE_PREDICATE,
                            pattern_side,
                        )
                        if exists:
                            counts["edges_exist"] += 1
                            continue
                        if apply:
                            await conn.execute(
                                "INSERT INTO dg_relations (subject_id, predicate, object_id, attrs, confidence) VALUES ($1, $2, $3, CAST($4 AS jsonb), $5)",
                                instance_id,
                                EDGE_PREDICATE,
                                pattern_side,
                                edge_attrs,
                                CONFIDENCE,
                            )
                        counts["edges_add"] += 1

            if prune:
                # 归并同步 A：删除不再在新候选集内的脚本自产 pattern 节点（先删边后删点）
                keep_ids = [e["pattern_id"] for e in candidates]
                stale = await conn.fetch(
                    """
                    SELECT id, norm_name, attrs->>'pattern_id' AS pid FROM dg_entities
                    WHERE domain=$1 AND etype=$2 AND attrs->>'pattern_id' IS NOT NULL
                      AND NOT (attrs->>'pattern_id' = ANY($3::text[]))
                    """,
                    DOMAIN,
                    PATTERN_ETYPE,
                    keep_ids,
                )
                stale_db_ids = set()
                for row in stale:
                    stale_db_ids.add(row["id"])
                    edge_n = await conn.fetchval("SELECT COUNT(*) FROM dg_relations WHERE subject_id=$1 OR object_id=$1", row["id"])
                    if apply:
                        await conn.execute("DELETE FROM dg_relations WHERE subject_id=$1 OR object_id=$1", row["id"])
                        await conn.execute("DELETE FROM dg_entities WHERE id=$1", row["id"])
                    counts["prune_edges_del"] += edge_n
                    counts["prune_nodes_del"] += 1
                    pruned_samples.append(f"{row['pid']}:{row['norm_name']}")
                # 归并同步 B：边层收敛——pattern 节点上不可由本轮候选推导的 domain_common analogous_to 旧边
                # （如旧版多数 etype 连边留下的同名跨 etype 端点）一并删除，使「apply+prune 重跑」成为真不动点。
                # dry-run 不真删，A 段已计的将删节点边在此按 stale_db_ids 排除避免重复计数。
                pat_ids = [r[0] for r in await conn.fetch("SELECT id FROM dg_entities WHERE domain=$1 AND etype=$2", DOMAIN, PATTERN_ETYPE)]
                if pat_ids:
                    attached = await conn.fetch(
                        "SELECT id, subject_id, object_id FROM dg_relations WHERE predicate=$1 AND attrs->>'scope'='domain_common' AND (subject_id = ANY($2::uuid[]) OR object_id = ANY($2::uuid[]))",
                        EDGE_PREDICATE,
                        pat_ids,
                    )
                    for rel in attached:
                        pair = (rel["subject_id"], rel["object_id"])
                        if pair in derived_edges or (rel["subject_id"] in stale_db_ids or rel["object_id"] in stale_db_ids):
                            continue
                        if apply:
                            await conn.execute("DELETE FROM dg_relations WHERE id=$1", rel["id"])
                        counts["prune_edges_del"] += 1
                        pruned_samples.append(f"edge:{pair[0]}→{pair[1]}")
    finally:
        await conn.close()

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] 节点 新建 {counts['nodes_insert']} / 原位更新 {counts['nodes_update']}（attrs || 合并，重跑幂等）")
    if refined:
        print(f"[{mode}] 精炼 命中候选并写入 attrs {counts['refined_applied']} 条（refined=true + refined_desc）")
    print(f"[{mode}] 边   待新增 {counts['edges_add']} / 已存在 {counts['edges_exist']}（谓词 {EDGE_PREDICATE}；含变体实例连边）")
    print(f"[{mode}] 端点缺失跳边 {counts['endpoint_missing']}（节点不受影响）" + (f"  如 {missing_samples[:3]}" if missing_samples else ""))
    if prune:
        print(f"[{mode}] prune 将删 pattern 节点 {counts['prune_nodes_del']} / 相应边 {counts['prune_edges_del']}" + (f"  如 {pruned_samples[:3]}" if pruned_samples else ""))
    if counts["name_clipped"]:
        print(f"[{mode}] 名字截断（>300 拼 pattern_id）: {counts['name_clipped']}")
    if not apply:
        print("dry-run 未写库；确认后加 --apply 执行")


async def _verify() -> None:
    """--apply 后图内对账：domain_pattern 节点数 + domain_common 关系数（DB 层）。"""
    cfg = DatabaseConfig.from_env()
    dsn = f"postgresql://{cfg.username}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.name}"
    conn = await asyncpg.connect(dsn)
    try:
        nodes = await conn.fetchval("SELECT COUNT(*) FROM dg_entities WHERE domain='eia' AND etype='domain_pattern'")
        edges = await conn.fetchval("SELECT COUNT(*) FROM dg_relations r WHERE r.predicate='analogous_to' AND r.attrs->>'scope'='domain_common'")
        refined = await conn.fetchval("SELECT COUNT(*) FROM dg_entities WHERE domain='eia' AND etype='domain_pattern' AND (attrs->>'refined')::boolean IS TRUE")
        sample_scope = await conn.fetchval("SELECT COUNT(*) FROM dg_entities WHERE domain='eia' AND (attrs->>'scope' IS NULL OR attrs->>'scope'='sample')")
        orphan = await conn.fetchval(
            """
            SELECT COUNT(*) FROM dg_entities p WHERE p.domain='eia' AND p.etype='domain_pattern'
              AND NOT EXISTS (SELECT 1 FROM dg_relations r WHERE r.subject_id=p.id OR r.object_id=p.id)
            """
        )
        print(f"[verify] eia 域 domain_pattern 节点 = {nodes}（refined {refined}）；domain_common analogous_to 边 = {edges}；无连边孤儿 pattern = {orphan}；sample 实体（含未打标）= {sample_scope}（应不受影响）")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="EIA domain_pattern 入图（B 库蒸馏产物，dry-run 默认）")
    parser.add_argument("--apply", action="store_true", help="真写库（缺省 dry-run 只计数）")
    parser.add_argument("--min-support", type=int, default=3, help="入图门槛（跨报告支持度，默认 3；归并扩量用 2）")
    parser.add_argument("--prune", action="store_true", help="归并同步：删除不在新候选集内的旧 pattern 节点（先删边）")
    parser.add_argument("--refined", type=Path, default=None, help="精炼描述 JSON（pattern_id → {refined_desc,...}）写入 attrs")
    parser.add_argument("--skip-verify", action="store_true", help="apply 后跳过 DB 对账")
    args = parser.parse_args()

    candidates = _load_candidates(args.min_support)
    if not candidates:
        print("无候选，退出")
        return
    refined = _load_refined(args.refined)
    asyncio.run(_run(candidates, apply=args.apply, refined=refined, prune=args.prune))
    if args.apply and not args.skip_verify:
        asyncio.run(_verify())


if __name__ == "__main__":
    main()
