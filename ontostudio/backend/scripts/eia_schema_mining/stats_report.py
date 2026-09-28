"""T3：合并三源产物 → schema 候选统计报告（用户定型唯一依据）。

输入：out/digest_stats.json + out/table_candidates.json + out/llm_candidates.jsonl
输出：out/t3_schema_report.md——四节：
  ① 候选类提名频次表（类 → digest 命中报告数 / LLM 提名(subject/object) / A-E 档位；
    表格锚点证据只在族级可归因，放 ③ 覆盖度矩阵，不冒充类级证据）
  ② 候选关系提名频次表（LLM 谓词计数 + v1 既有 / v2 草案 / 未登记 标注）
  ③ 三层覆盖度矩阵（L1 六族 / L2 / L3 × digest / 表格锚点 / LLM 三证据源）
  ④ A-E 组对照表（采纳 / 语料无证据 / 二期 三档）+ CQ 草案清单（cq/*.rq）

执行前提：Task 6 GATE 后 out/llm_candidates.jsonl 才存在——三输入缺一即 fail-fast
并指名缺哪个文件（Task 7 Step 2 跑报告 deferred，等 Task 6 抽样数据）。
用法：python stats_report.py [--out-dir out]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from coal_terms import COAL_TERMS

A_E_GROUPS: dict[str, str] = {  # 三轮参考资料 → spec 裁定档位
    "coal_seam": "采纳", "aquifer": "采纳", "stratigraphic_unit": "采纳", "fault": "采纳",
    "goaf": "采纳", "mine_field": "采纳", "mining_district": "采纳", "working_face": "采纳",
    "mining_method": "采纳", "engineering_site": "采纳", "coal_prep_plant": "采纳",
    "emission_point": "采纳", "waste_stream": "采纳", "receiving_medium": "采纳",
    "impact_result": "采纳", "planning_scheme": "采纳", "planning_change": "采纳",
    "carrying_capacity": "采纳", "retrospective_problem": "采纳",
    "openpit_mining": "T3候选", "methane_source": "二期", "ghg_account": "二期", "risk_scenario": "二期",
}

# L1 六族（spec §4.2 表）+ L2/L3 分层归属——③ 覆盖度矩阵的行序
LAYER_FAMILIES: dict[str, list[str]] = {
    "L1 资源地质": ["coal_seam", "aquifer", "stratigraphic_unit", "fault", "goaf", "mine_field"],
    "L1 开采工程": ["mining_district", "working_face", "mining_method", "engineering_site", "coal_prep_plant"],
    "L1 排放骨架": ["emission_point", "waste_stream", "receiving_medium"],
    "L1 影响结果": ["impact_result"],
    "L1 规划环评": ["planning_scheme", "planning_change", "carrying_capacity", "retrospective_problem"],
    "L1 受体(既有)": ["sensitive_point"],
    "L2 约束": ["standard_threshold", "regulation_clause", "pollutant_concept",
                "measure_process_concept", "pollution_process_concept"],
    "L3 佐证素材": ["evidence_requirement", "evidence_artifact", "analogy_case", "measure_spec"],
}

# 源② 表格锚点类目 → 覆盖度矩阵行（表格源只在族级给证据的近似映射）
TABLE_CAT_FAMILY: dict[str, str] = {
    "source_strength": "L1 排放骨架",
    "subsidence": "L1 影响结果",
    "monitoring": "L2 约束",
    "measures": "L3 佐证素材",
    "sensitive": "L1 受体(既有)",
}

# v1 既有谓词（app/ontology/registry/eia.yaml enum）——② 表登记标注用
V1_PREDICATES = frozenset({
    "has_chapter", "has_subsection", "part_of", "precedes", "pollutes", "emitted_as",
    "treated_by", "governed_by", "monitored_by", "threatens", "impact_to",
    "specifies_threshold", "complies_with", "cites_clause", "regulated_by",
    "requires_evidence", "evidenced_by", "located_in",
})

# v2 草案新增谓词（计划 Task 8 清单）——② 表登记标注用
V2_DRAFT_PREDICATES = frozenset({
    "mines", "method_of", "develops", "causes", "affects", "protected_by", "drawdown_of",
    "emitted_via", "drains_to", "generates_waste", "disposed_by", "utilized_by",
    "sub_plan_of", "changes", "constrained_by", "problem_of", "specified_by",
    "analogous_to", "conflicts_with",
})


def _base(etype: str) -> str:
    """impact_result:drawdown → impact_result（COAL_TERMS 的细化枚举记法归并到基类）。"""
    return etype.split(":")[0]


def _require(path: Path) -> None:
    if not path.exists():
        sys.exit(f"[stats_report] 缺输入 {path}——Task 6 GATE 前属预期，等抽样数据后再跑")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args()
    d = Path(args.out_dir)

    _require(d / "digest_stats.json")
    _require(d / "table_candidates.json")
    llm_path = d / "llm_candidates.jsonl"
    _require(llm_path)

    digest = json.loads((d / "digest_stats.json").read_text(encoding="utf-8"))
    tables = json.loads((d / "table_candidates.json").read_text(encoding="utf-8"))
    llm_pred: Counter[str] = Counter()
    llm_type: Counter[str] = Counter()
    for line in llm_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        it = json.loads(line)
        llm_pred[str(it.get("predicate", "?"))] += 1
        for side in ("subject_type", "object_type"):
            if it.get(side):
                llm_type[_base(str(it[side]))] += 1

    # 术语 → 基类倒排（供 digest 按类聚合）；保持 COAL_TERMS 首现顺序
    terms_of_base: dict[str, list[str]] = {}
    for term, etype in COAL_TERMS.items():
        if etype is not None:
            terms_of_base.setdefault(_base(etype), []).append(term)

    def digest_reports(*bases: str) -> int:
        """digest 源证据：命中任一归属术语的报告数（出现即计 1，不看次数）。"""
        want = {t for b in bases for t in terms_of_base.get(b, ())}
        return sum(1 for r in digest["per_report"] if any(r["term_hits"].get(t) for t in want))

    # ① 候选类提名频次（按基类聚合去重）
    lines = [
        "# T3 schema 候选统计报告", "",
        "> 三源合并：digest_stats.json（源①）+ table_candidates.json（源②）+ llm_candidates.jsonl（源③）。",
        "> 生成：scripts/eia_schema_mining/stats_report.py；用户定型唯一依据（spec §5）。", "",
        "## ① 候选类提名频次", "",
        "| 提名类 | digest 命中报告数 | LLM 提名(subject/object) | A-E 档位 |", "|---|---|---|---|",
    ]
    seen: list[str] = []
    for etype in COAL_TERMS.values():
        if etype is None:
            continue
        base = _base(etype)
        if base in seen:
            continue
        seen.append(base)
        lines.append(f"| {base} | {digest_reports(base)} | {llm_type.get(base, 0)} | {A_E_GROUPS.get(base, '采纳')} |")

    # ② 候选关系提名频次（LLM 谓词计数 + 登记状态标注）
    lines += ["", "## ② 候选关系提名频次", "",
              "| 谓词 | LLM 提名次数 | 登记 |", "|---|---|---|"]
    for pred, n in llm_pred.most_common():
        reg = "v1 既有" if pred in V1_PREDICATES else "v2 草案" if pred in V2_DRAFT_PREDICATES else "未登记(待裁)"
        lines.append(f"| {pred} | {n} | {reg} |")

    # ③ 三层覆盖度矩阵（表格锚点只在族级归因——见模块 docstring）
    cat_rows: Counter[str] = Counter()
    for _report, cats in tables.items():
        for cat, rows in cats.items():
            cat_rows[cat] += len(rows)
    lines += ["", "## ③ 三层覆盖度矩阵", "",
              "| 层/族 | digest 命中报告数 | 表格候选行 | LLM 提名 |", "|---|---|---|---|"]
    for layer, etypes in LAYER_FAMILIES.items():
        table_n = sum(n for cat, n in cat_rows.items() if TABLE_CAT_FAMILY.get(cat) == layer)
        lines.append(f"| {layer} | {digest_reports(*etypes)} | {table_n} | {sum(llm_type.get(e, 0) for e in etypes)} |")
    lines += ["", "表格候选行类目计数：" + "；".join(f"{cat}={cat_rows.get(cat, 0)}" for cat in TABLE_CAT_FAMILY)]

    # ④ A-E 组对照（采纳 / 语料无证据 / 二期 三档）+ CQ 草案清单
    lines += ["", "## ④ A-E 组对照（采纳/语料无证据/二期 三档）", "",
              "| 提名类 | 计划档位 | digest 命中报告数 | LLM 提名 | 终判 |", "|---|---|---|---|---|"]
    for base, tier in A_E_GROUPS.items():
        n_d, n_l = digest_reports(base), llm_type.get(base, 0)
        final = f"语料无证据（原 {tier}）" if tier == "采纳" and n_d == 0 and n_l == 0 else tier
        lines.append(f"| {base} | {tier} | {n_d} | {n_l} | {final} |")

    lines += ["", "### 仅提名未归类术语（COAL_TERMS 值为 None）", ""]
    for term, etype in COAL_TERMS.items():
        if etype is None:
            n = sum(1 for r in digest["per_report"] if r["term_hits"].get(term))
            lines.append(f"- {term}：{n} 份报告命中")

    lines += ["", "## CQ 草案清单（cq/）", ""]
    cq_dir = Path(__file__).parent / "cq"
    rqs = sorted(cq_dir.glob("*.rq"))
    if rqs:
        for rq in rqs:
            title = next(
                (ln.lstrip("# ").strip() for ln in rq.read_text(encoding="utf-8").splitlines() if ln.startswith("#")),
                rq.name,
            )
            lines.append(f"- `{rq.name}` {title}")
    else:
        lines.append("- cq/ 未落盘")
    lines += ["", "> CQ 判据：定型评审以「CQ 全部可答」为 schema 够用标准（spec §5）。", ""]

    out = d / "t3_schema_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
