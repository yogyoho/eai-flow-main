#!/usr/bin/env python3
"""geological-report v2 — chapter_planner.py：章节清单 + 「改参 → 受影响章节」反查中枢。

manifest 生成不再硬编码章节（water 版教训）：直接由 references/stages/{stage}.json 的
chapters（每章 forms/formulas/contracts 声明）驱动。两类伪章节追加：
  front_matter      前置部分（表单渲染，零 LLM）
  compliance_appendix 合规性附录（consistency_check.json 渲染——引用全量公式与合约，
                      任一公式输出变化必受影响，bug-2199 同构）

合约 → 公式覆盖表（CONTRACT_FORMULA_REFS）来自 ch8 走查 §4 与 exploration.json 章级
contracts 声明：XS2（资源量数字族）把 L8-L12 链到 ch1/ch4/ch9/ch10——这是 SC-3
「改小体重 D → impacted ⊇ {ch1,ch4,ch8,ch9,ch10}+附录」的机制来源。

CLI:
  manifest --stage references/stages/exploration.json --output state/chapter_manifest.json
  impacted --manifest state/chapter_manifest.json --formulas L8,L9 [--families 13a]
       --formulas: 受影响公式 id 逗号清单（formula_runner impacted 的输出直接喂入）
       --families: 受影响表单族名（非公式数据变更路径，如 04_geography 文本改动）
输出打印 IMPACTED_READY + JSON；退出码 0/1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 全量依赖伪章节：任一公式/表单变化都必受影响
ALWAYS_DEPENDENT = ("ch10", "compliance_appendix")

# 合约 → 其校验/引用的公式族（exploration.json 章级 contracts 声明的反向边）
CONTRACT_FORMULA_REFS: dict[str, list[str]] = {
    "XS2": ["L7", "L8", "L9", "L10", "L11", "L12"],   # 资源量数字族（表8-2 同源槽位）
    "XS1": ["L3", "L4"],                              # 矿体参数统计
    "FC1": ["L9"],
    "FC2": ["L10"],
    "FC3": ["S1"],
    "FC4": ["C9"],
    "FC5": ["L12"],
    "FC6": ["L11"],
    "FC7": ["E1", "E2", "E3", "E4", "E5", "E6", "E7"],
    "FC8": ["L13"],
    "B1C": ["B1"],
    "CC1": ["S2"],
}


def build_manifest(stage: dict) -> dict:
    chapters = []
    for ch_id, ch in stage.get("chapters", {}).items():
        chapters.append({
            "id": ch_id,
            "title": ch.get("title", ch_id),
            "type": "narrative" if ch_id.startswith("ch") and ch_id != "ch10" else ("projection" if ch_id == "ch10" else "narrative"),
            "formula_ids": list(ch.get("formulas", [])),
            "contract_ids": list(ch.get("contracts", [])),
            "form_families": list(ch.get("forms", [])),
        })
    chapters.insert(0, {
        "id": "front_matter", "title": "前置部分", "type": "table",
        "formula_ids": [], "contract_ids": ["NR3"],
        "form_families": ["figures_tables", "project"],
    })
    chapters.append({
        "id": "compliance_appendix", "title": "合规性附录", "type": "table",
        "formula_ids": [], "contract_ids": [], "form_families": [],
        "always_dependent": True,
    })
    # 每章追加合约反查到的公式（formula_ids ∪ contracts 覆盖的公式）
    for ch in chapters:
        extra = set()
        for cid in ch["contract_ids"]:
            extra.update(CONTRACT_FORMULA_REFS.get(cid, []))
        for f in sorted(extra):
            if f not in ch["formula_ids"]:
                ch["formula_ids"].append(f)
        if ch["id"] == "ch10":
            ch.setdefault("always_dependent", True)
    return {"version": 2, "always_dependent": list(ALWAYS_DEPENDENT), "chapters": chapters}


def impacted_chapters(affected_formulas: list[str], affected_families: list[str], manifest: dict) -> list[str]:
    """反查受影响章节 id（去重保序）。ch10/compliance_appendix 只要非空影响集就追加。"""
    hit: list[str] = []
    formulas = set(affected_formulas)
    families = set(affected_families)
    any_hit = bool(formulas or families)
    for ch in manifest.get("chapters", []):
        fids = set(ch.get("formula_ids", []))
        fams = set(ch.get("form_families", []))
        cids = set(ch.get("contract_ids", []))
        via_contract = any(
            formulas & set(CONTRACT_FORMULA_REFS.get(cid, [])) for cid in cids
        )
        if (formulas & fids) or (families & fams) or via_contract:
            if ch["id"] not in hit:
                hit.append(ch["id"])
    if any_hit:
        for cid in manifest.get("always_dependent", ALWAYS_DEPENDENT):
            if cid not in hit:
                hit.append(cid)
    return hit


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 章节规划器")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("manifest", help="由 stage 模板生成 chapter_manifest.json")
    m.add_argument("--stage", required=True)
    m.add_argument("--output", required=True)

    i = sub.add_parser("impacted", help="受影响公式/表单族 → 受影响章节反查")
    i.add_argument("--manifest", required=True)
    i.add_argument("--formulas", default="", help="逗号分隔公式 id")
    i.add_argument("--families", default="", help="逗号分隔表单族名")
    i.add_argument("--output", help="结果 JSON 落盘路径（可选）")

    args = p.parse_args()
    if args.command == "manifest":
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        manifest = build_manifest(stage)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"MANIFEST_READY: {args.output} chapters={len(manifest['chapters'])}")
        return 0

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    formulas = [x for x in args.formulas.split(",") if x.strip()]
    families = [x for x in args.families.split(",") if x.strip()]
    result = {
        "affected_formulas": formulas,
        "affected_families": families,
        "affected_chapters": impacted_chapters(formulas, families, manifest),
    }
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"IMPACTED_READY: {args.output}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
