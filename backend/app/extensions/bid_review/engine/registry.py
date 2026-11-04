"""规则包注册表——跨源索引+lint(EAI-CUSTOM 2026-11-05 R1,spec 裁决②③修正版)。

单一事实源各居其位:字段 inputs=规则包 yaml;锚点=anchors.ANCHOR_REGISTRY(代码单源);
形状契约=extract.FIELD_TYPE_CONTRACTS。本模块只做三件事,不复制任何账本:
1. universe():抽取请求字段宇宙 = 包 inputs ∪ 锚点路径 ∪ 投影字段
2. consumed_by():字段→消费者反查(改字段前先查炸谁,设计一 absorbed)
3. lint_rules():包语义校验(load_rulepack 硬拒载 + pytest 全量 lint)
依赖方向: extract → registry → anchors;rule_runner → registry。禁止反向(防环)。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.extensions.bid_review.engine.anchors import ANCHOR_REGISTRY

RULEPACK_DIR = Path(__file__).parent / "rulepacks" / "bid-review-core"

# 投影字段(spec §0 病灶③):被 worker/routers 消费但无规则 inputs 声明处的 3 条,此处即声明处。
PROJECTION_FIELDS: dict[str, str] = {
    "deviation.items": "B9 偏离表投影(routers.py)",
    "tender.scoring_items": "B4 评分办法投影(routers.py)",
    "tender.project_identity.lot_section": "task.lot_name 标段投影(worker.py)",
}

# severity 层白名单(EAI-CUSTOM 2026-11-05 R1,spec §1 enums 收敛):L1 major=业绩达标特例、
# 禁 minor(否决层无提示级);L3 禁 fatal(一致性层不否决);L2 中间层三档全放行(eval_core
# 夹具 EX-001 L2/minor 既有语义,取证修正)。
SEVERITY_BY_LAYER: dict[str, set[str]] = {
    "L1": {"fatal", "major"},
    "L2": {"fatal", "major", "minor"},
    "L3": {"major", "minor"},
}


def _pack_rules() -> list[dict]:
    out: list[dict] = []
    for p in sorted(RULEPACK_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out += data.get("rules") or []
    return out


def pack_inputs() -> set[str]:
    paths: set[str] = set()
    for r in _pack_rules():
        for p in r.get("inputs") or []:
            if isinstance(p, str):
                paths.add(p)
    return paths


def anchor_paths() -> set[str]:
    return {p for a in ANCHOR_REGISTRY.values() for p in a.get("paths", [])}


def universe() -> list[str]:
    """抽取请求字段宇宙(=改造前 collect_field_paths() 输出,逐位相等是零行为门)。"""
    return sorted(pack_inputs() | anchor_paths() | set(PROJECTION_FIELDS))


def consumed_by(path: str) -> dict[str, list[str]]:
    """字段→消费者反查索引:改字段前先查炸谁。"""
    rules = sorted({str(r["id"]) for r in _pack_rules() if path in (r.get("inputs") or [])})
    anchors = sorted(k for k, a in ANCHOR_REGISTRY.items() if path in a.get("paths", []))
    projections = [PROJECTION_FIELDS[path]] if path in PROJECTION_FIELDS else []
    return {"rules": rules, "anchors": anchors, "projections": projections}


def lint_rules(rules) -> list[str]:
    """包语义 lint;rules=Rule 列表(duck-typed,不 import rule_runner 防环)。"""
    problems: list[str] = []
    for r in rules:
        rid = str(getattr(r, "id", "?"))
        for ev in getattr(r, "evidence", []) or []:
            if ev not in ANCHOR_REGISTRY:
                problems.append(f"规则 {rid}: evidence 锚 {ev} 未注册(ANCHOR_REGISTRY 无此名,运行时会静默丢)")
        layer = str(getattr(r, "layer", ""))
        whitelist = SEVERITY_BY_LAYER.get(layer)
        if whitelist is None:
            problems.append(f"规则 {rid}: 未知层 {layer!r}")
        elif str(getattr(r, "severity", "")) not in whitelist:
            problems.append(f"规则 {rid}: severity {getattr(r, 'severity', '')!r} 不在 {layer} 白名单 {sorted(whitelist)}")
        for p in getattr(r, "inputs", []) or []:
            if not isinstance(p, str) or not p.strip() or "." not in p:
                problems.append(f"规则 {rid}: input {p!r} 非点路径")
    return problems


if __name__ == "__main__":  # consumed_by 反查 CLI:无参打全表,带参打单字段
    import sys

    args = sys.argv[1:]
    if args:
        info = consumed_by(args[0])
        print(f"{args[0]}:")
        for kind, items in info.items():
            print(f"  {kind}: {', '.join(items) if items else '(无)'}")
    else:
        uni = universe()
        print(f"宇宙 {len(uni)} 路径:")
        for p in uni:
            info = consumed_by(p)
            consumers = info["rules"] + [f"@{a}" for a in info["anchors"]] + [f"→{x}" for x in info["projections"]]
            print(f"  {p:45s} {' '.join(consumers) if consumers else '(仅宇宙,无消费者)'}")
