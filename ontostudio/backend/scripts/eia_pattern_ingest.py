#!/usr/bin/env python3
"""EIA domain_pattern 入图（ontostudio 子项目 5 交付 2）——B 库蒸馏产物写 dg_* 真相源.

EAI-CUSTOM(2026-09-30, 子项目 5): 写库脚本（eia 域内），不碰容器。

用法:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py            # dry-run（默认）
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --apply                            # 真写
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_ingest.py --min-support 5 --apply            # 提门槛

输入 = scripts/eia_pattern_mine_out/patterns.json（交付 1 产物），取 support_count >= --min-support 的候选：
  - 每条一个 domain_pattern 节点：etype=domain_pattern（B 库挂载点, eia.yaml 已注册 DomainPattern）、
    scope=domain_common、attrs 记 pattern_type/subject/object/support/source_reports/pattern_desc；
  - 两侧 analogous_to 边连到既有实体：subject —analogous_to→ pattern ←analogous_to— object
    （实例→模式方向；analogous_to=「类比于」——样例实体是蒸馏模式的实例，语义成立）。
    谓词只用既有 37 谓词不新增；端点实体按自然键 (domain,etype,norm_name) 查无即跳过该边
    （不强行连边），节点与 attrs 仍然落库。

幂等：节点走 uq_dg_entities_natural ON CONFLICT 原位更新（attrs JSONB || 合并）；边先查
(s,predicate,o) 已存在即跳过（dg_relations 无唯一约束）。重跑不重复。
事务：单事务全量提交，失败整体回滚。
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
    """pattern_name 超 norm_name 列宽时截断并拼 pattern_id 保唯一。"""
    if len(name) <= NAME_MAX:
        return name
    return name[: NAME_MAX - 11] + "-" + pattern_id


def _load_candidates(min_support: int) -> list[dict]:
    payload = json.loads(MINE_OUT.read_text(encoding="utf-8"))
    entries = [e for entries in payload["patterns"].values() for e in entries]
    candidates = sorted(
        (e for e in entries if e["support_count"] >= min_support),
        key=lambda e: (-e["support_count"], e["pattern_id"]),
    )
    print(f"输入 {len(entries)} 配对，support>={min_support} 候选 {len(candidates)} 条")
    return candidates


async def _run(candidates: list[dict], apply: bool) -> None:
    cfg = DatabaseConfig.from_env()
    dsn = f"postgresql://{cfg.username}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.name}"
    conn = await asyncpg.connect(dsn)
    counts = {"nodes_insert": 0, "nodes_update": 0, "edges_add": 0, "edges_exist": 0, "endpoint_missing": 0, "name_clipped": 0}
    missing_samples: list[str] = []
    try:
        async with conn.transaction():
            for e in candidates:
                now = datetime.now(UTC).isoformat()
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
                    pattern_id = existing["id"] if existing else uuid4()  # 占位：新节点在 dry-run 中无真实 id

                edge_attrs = json.dumps({"scope": "domain_common", "pattern_name": norm, "mined_by": "eia_pattern_mine"}, ensure_ascii=False)
                for side, role in (("subject", "subject"), ("object", "object")):
                    endpoint = await conn.fetchrow(
                        "SELECT id FROM dg_entities WHERE domain=$1 AND etype=$2 AND norm_name=$3",
                        DOMAIN,
                        e[f"{role}_etype"],
                        e[f"{role}_name"],
                    )
                    if endpoint is None:
                        # 端点在库中无该自然键（如混型多数 etype 判错）→ 不强行连边，节点仍已落库
                        counts["endpoint_missing"] += 1
                        missing_samples.append(f"{e['pattern_id']}:{role}={e[role + '_name']}({e[role + '_etype']})")
                        continue
                    instance_id, pattern_side = endpoint["id"], pattern_id
                    if role == "object":  # 边方向恒为 实例→模式：object 侧对调端点
                        instance_id, pattern_side = pattern_id, endpoint["id"]
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
    finally:
        await conn.close()

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] 节点 新建 {counts['nodes_insert']} / 原位更新 {counts['nodes_update']}（attrs || 合并，重跑幂等）")
    print(f"[{mode}] 边   待新增 {counts['edges_add']} / 已存在 {counts['edges_exist']}（谓词 {EDGE_PREDICATE}，实例→模式）")
    print(f"[{mode}] 端点缺失跳边 {counts['endpoint_missing']}（节点不受影响）" + (f"  如 {missing_samples[:3]}" if missing_samples else ""))
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
        sample_scope = await conn.fetchval("SELECT COUNT(*) FROM dg_entities WHERE domain='eia' AND (attrs->>'scope' IS NULL OR attrs->>'scope'='sample')")
        print(f"[verify] eia 域 domain_pattern 节点 = {nodes}；domain_common analogous_to 边 = {edges}；sample 实体（含未打标）= {sample_scope}（应不受影响）")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="EIA domain_pattern 入图（B 库蒸馏产物，dry-run 默认）")
    parser.add_argument("--apply", action="store_true", help="真写库（缺省 dry-run 只计数）")
    parser.add_argument("--min-support", type=int, default=3, help="入图门槛（跨报告支持度，默认 3）")
    parser.add_argument("--skip-verify", action="store_true", help="apply 后跳过 DB 对账")
    args = parser.parse_args()

    candidates = _load_candidates(args.min_support)
    if not candidates:
        print("无候选，退出")
        return
    asyncio.run(_run(candidates, apply=args.apply))
    if args.apply and not args.skip_verify:
        asyncio.run(_verify())


if __name__ == "__main__":
    main()
