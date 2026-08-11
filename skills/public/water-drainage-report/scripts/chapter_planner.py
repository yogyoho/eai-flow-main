#!/usr/bin/env python3
"""给排水设计专篇 — 章节规划器（反馈6 定点重生成的中枢）。

两个纯函数 + 一个 CLI：
    build_manifest(formulas)   — 把公式按 section 归入 fallback 10 章结构，产出 chapter_manifest.json
    impacted_chapters(fids, m) — 给定受影响 formula_id 集 + manifest，反查受影响 chapter_id

manifest 是「改参 → 受影响章节」的反查表：formula_runner impacted --manifest 用它把
受影响公式收窄到受影响章节，技能只重生成这些章节（反馈6 热更新）。

机械 table 渲染延后（spec §14⑥）；v1 只做映射 + 反查。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# fallback 10 章结构：section_prefixes 指明该章吸收哪些 section 首段（报告章节号 ≠ 文档 section 号）
FALLBACK_CHAPTERS = [
    {"id": "ch1_basis",      "title": "设计依据及采用的标准",         "type": "narrative", "section_prefixes": []},
    {"id": "ch2_scope",      "title": "设计范围与设计规模",           "type": "narrative", "section_prefixes": []},
    {"id": "ch3_params",     "title": "设计参数",                     "type": "table",    "section_prefixes": [], "render": "param_table"},
    {"id": "ch4_standards",  "title": "设计中采用的主要标准及规范",   "type": "narrative", "section_prefixes": []},
    {"id": "ch5_calc",       "title": "循环水装置工艺计算",           "type": "table",    "section_prefixes": ["6"], "render": "calc_steps"},
    {"id": "ch6_pool",       "title": "塔底水池、吸水池、滤网及滤网井", "type": "narrative", "section_prefixes": ["7"]},
    {"id": "ch7_pumphouse",  "title": "吸水池及循环水泵房工艺计算",   "type": "narrative", "section_prefixes": ["8"]},
    {"id": "ch8_filter",     "title": "旁滤设备",                     "type": "narrative", "section_prefixes": ["9"]},
    {"id": "ch9_equiplist",  "title": "设备一览表",                   "type": "table",    "section_prefixes": [], "render": "equipment_table"},
    {"id": "ch10_drawings",  "title": "图纸清单",                     "type": "narrative", "section_prefixes": []},
]


def _section_prefix(section: str) -> str:
    """section "6.1.1" → "6"；空 → ""。"""
    return section.split(".", 1)[0] if section else ""


def build_manifest(formulas_data: list[dict]) -> dict:
    """把公式按 section 首段归入 fallback 10 章，返回 chapter_manifest 结构。

    每个 chapter 增加 formula_ids（落入该章的公式 id 列表）。
    未匹配任何章前缀的公式 → 忽略（不阻塞；通常是新增公式尚未配章）。
    """
    chapters = []
    for ch in FALLBACK_CHAPTERS:
        chapters.append({**ch, "formula_ids": []})

    prefix_to_chidx: dict[str, int] = {}
    for idx, ch in enumerate(chapters):
        for pfx in ch["section_prefixes"]:
            prefix_to_chidx[pfx] = idx

    for fdef in formulas_data:
        pfx = _section_prefix(fdef.get("section", ""))
        idx = prefix_to_chidx.get(pfx)
        if idx is not None:
            chapters[idx]["formula_ids"].append(fdef["id"])

    return {"version": 1, "chapters": chapters}


def impacted_chapters(affected_formula_ids: list[str], manifest: dict) -> list[str]:
    """反查受影响 chapter_id（去重、保序）。空集 → []。"""
    hit: list[str] = []
    affected = set(affected_formula_ids)
    for ch in manifest.get("chapters", []):
        if affected & set(ch.get("formula_ids", [])):
            if ch["id"] not in hit:
                hit.append(ch["id"])
    return hit


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: manifest / impacted
# ═══════════════════════════════════════════════════════════════════════════════

def _load_formulas(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["formulas"]


def main() -> None:
    parser = argparse.ArgumentParser(description="给排水设计专篇 — 章节规划器")
    sub = parser.add_subparsers(dest="command")

    p_manifest = sub.add_parser("manifest", help="从 formulas.json 生成 chapter_manifest.json")
    p_manifest.add_argument("--formulas", required=True, help="formulas.json 路径")
    p_manifest.add_argument("--output", required=True, help="输出 manifest 路径")

    args = parser.parse_args()

    if args.command == "manifest":
        formulas = _load_formulas(args.formulas)
        manifest = build_manifest(formulas)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"MANIFEST_READY: {args.output}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
