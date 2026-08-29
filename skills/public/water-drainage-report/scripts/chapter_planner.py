#!/usr/bin/env python3
"""给排水设计专篇 — 章节规划器（反馈6 定点重生成的中枢）。

两个纯函数 + 一个 CLI：
    build_manifest(formulas)   — 把公式按 section 归入样例体例结构（9 个数字节 + 合规附录），产出 chapter_manifest.json
    impacted_chapters(fids, m) — 给定受影响 formula_id 集 + manifest，反查受影响 chapter_id

体例严格对齐吉林院样例（2026-08-29 用户定案）：章节标题 = 数字+空格+标题（"1 设计依据"，禁"第X章"）；
formulas.json 的 section 编号即报告编号（公式 section 6.1.1 → 报告 6.1.1 节），不再有
"报告章节号 ≠ 文档 section 号"的错位。样例不单设设备一览表/图纸清单章——设备规格并入 8.2.1/7.2.4 叙述。

manifest 是「改参 → 受影响章节」的反查表：formula_runner impacted --manifest 用它把
受影响公式收窄到受影响章节，技能只重生成这些章节（反馈6 热更新）。

机械 table 渲染延后（spec §14⑥）；v1 只做映射 + 反查。
"""

from __future__ import annotations

import argparse
import json
import sys

# 样例体例结构（吉林院计算书 9 个数字节 + 不编号合规附录）：section_prefixes 指明该节
# 吸收哪些 section 首段——样例体例下公式 section 编号即报告编号（6.1.1 → 报告 6.1.1）。
FALLBACK_CHAPTERS = [
    {"id": "ch1_basis",      "title": "设计依据",                     "type": "narrative", "section_prefixes": []},  # 样例第1节仅委托书/统一规定，标准归第5节
    {"id": "ch2_scope",      "title": "设计范围",                     "type": "narrative", "section_prefixes": []},
    {"id": "ch3_scale",      "title": "设计规模",                     "type": "table",    "section_prefixes": [], "render": "water_stats_table"},  # 样例 3.1 工艺装置循环水量统计表（7列）+ 定水量依据句
    {"id": "ch4_params",     "title": "设计参数",                     "type": "table",    "section_prefixes": [], "render": "param_table"},  # 样例第4节：气象5参数
    {"id": "ch5_standards",  "title": "设计中采用的主要标准及规范",   "type": "narrative", "section_prefixes": []},  # 两列表逐项列规范号+名称（样例12项），标准依据只此一节
    {"id": "ch6_calc",       "title": "循环水装置工艺计算",           "type": "table",    "section_prefixes": ["6"], "render": "calc_steps"},
    {"id": "ch7_pool",       "title": "塔底水池、吸水池、滤网及滤网井", "type": "narrative", "section_prefixes": ["7"]},
    {"id": "ch8_pumphouse",  "title": "吸水池及循环水泵房工艺计算",   "type": "narrative", "section_prefixes": ["8"]},
    {"id": "ch9_filter",     "title": "旁滤设备",                     "type": "narrative", "section_prefixes": ["9"]},  # 设备规格叙述并入本节与 7.2.4/8.2.1（样例不单设设备表章）
    # bug-2199：合规附录/建议区整表由 consistency_check.json 渲染，check 又引用全部公式/参数——
    # 任意公式变化它都受影响。formula_ids 留空占位，由 build_manifest 填成全量公式 id（见下）。
    {"id": "ch10_compliance", "title": "合规校验结果与调整建议（附录，不编号）", "type": "table",  "section_prefixes": [], "render": "compliance_appendix"},
]


def _section_prefix(section: str) -> str:
    """section "6.1.1" → "6"；空 → ""。"""
    return section.split(".", 1)[0] if section else ""


def build_manifest(formulas_data: list[dict]) -> dict:
    """把公式按 section 首段归入样例体例 9 节 + 合规附录，返回 chapter_manifest 结构。

    每个 chapter 的 formula_ids = section 首段匹配到的公式 ∪ 显式声明。样例体例下
    filter_count（section 9.1.2）落在 ch9_filter（旁滤设备节），其规格叙述并入
    7.2.4/8.2.1 设备选型段——样例无设备一览表章，改参后由受影响计算节连带重生成。
    未匹配任何节前缀的公式 → 忽略（不阻塞；通常是新增公式尚未配章）。

    注：ch3_scale（水量统计表）与 ch4_params（设计参数表）展示的是输入参数，不是公式
    输出，值差分流程（last_change_summary 只报告公式输出变化）不会标记它们——这是有意
    为之：参数表是输入回显，agent 重生成报告时天然刷新，无需走 impacted_chapters。
    """
    chapters = []
    for ch in FALLBACK_CHAPTERS:
        chapters.append({**ch, "formula_ids": list(ch.get("formula_ids", []))})

    prefix_to_chidx: dict[str, int] = {}
    for idx, ch in enumerate(chapters):
        for pfx in ch["section_prefixes"]:
            prefix_to_chidx[pfx] = idx

    for fdef in formulas_data:
        pfx = _section_prefix(fdef.get("section", ""))
        idx = prefix_to_chidx.get(pfx)
        if idx is not None:
            chapters[idx]["formula_ids"].append(fdef["id"])

    # bug-2199：ch10_compliance（合规附录+建议区）引用全部 check 结果 → 依赖全量公式，
    # 任一公式变化都必须重生成，否则报告会出现"参数表 N=5 / 合规表 N=4"并存的自相矛盾。
    for ch in chapters:
        if ch["id"] == "ch10_compliance":
            ch["formula_ids"] = [f["id"] for f in formulas_data]

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
