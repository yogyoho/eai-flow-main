#!/usr/bin/env python3
"""EIA 头部 pattern 精炼工作台（ontostudio 子项目 5 深化交付）——LLM 精炼的事实清单 + 人审清单生成.

EAI-CUSTOM(2026-09-30, 子项目 5): 本地脚本，不写库、不碰容器。精炼正文由 LLM 撰写（数据事实为锚：
subject→object 关系 + support + 来源报告；纪律=不编造数值区间/标准号，support/来源保持数据原值）。

用法:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_refine.py --facts [--top N] [--min-support S]
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_refine.py --review

模式：
  --facts   读 patterns.json，取 support≥--min-support 按 (support,occurrence) 降序前 --top 条，
            补项目显示名后落 refined_facts.json（LLM 撰写底稿）。
  --review  读 refined_desc.json + patterns.json，生成人审抽检清单 refined_review.md
            （Markdown 表：pattern/精炼描述/support/来源）。

slug 显示名真源 = scripts/eia_schema_mining/parse_docx.py SLUG_FILES（kf_samples_seed.json 对账定稿），
此处存人工提炼短名（与文件名逐一对应，新增样例须同步）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT_DIR = Path(__file__).parent / "eia_pattern_mine_out"
PATTERNS_JSON = OUT_DIR / "patterns.json"
REFINED_JSON = OUT_DIR / "refined_desc.json"
FACTS_JSON = OUT_DIR / "refined_facts.json"
REVIEW_MD = OUT_DIR / "refined_review.md"

# slug → 项目短名（parse_docx.py SLUG_FILES 22 份样例；用于精炼描述与人审清单可读性）
SLUG_DISPLAY = {
    "baiyinhua2": "白音华二号露天矿",
    "baiyinhua3": "白音华三号露天矿",
    "balasu": "巴拉素",
    "gaotaoyao": "高头窑矿区",
    "guojiatai": "郭家台二号矿井",
    "hegang": "鹤岗矿区",
    "hengcheng": "横城矿区",
    "huating": "华亭矿区",
    "jiulongchuan": "九龙川矿井",
    "lingtai": "灵台矿区",
    "nalinxili": "纳林希里矿区",
    "naomaohu2025": "淖毛湖矿区",
    "santanghu": "三塘湖矿区",
    "sijitun": "四季屯",
    "weizhou": "韦州矿区",
    "wujianfang": "五间房矿区",
    "yakeshi2026": "牙克石（五九煤田）",
    "yimin": "伊敏矿区（总规）",
    "yimin3500": "伊敏3500万吨",
    "yining": "伊宁矿区北区",
    "yitai": "伊泰煤矿（露天）",
    "yueerwan": "月儿湾矿井",
}

PRED_DISPLAY = {"emitted_as+treated_by": "产污+治理", "governed_by": "执行标准", "disposed_by": "处置", "utilized_by": "综合利用"}


def _display(slug: str) -> str:
    return SLUG_DISPLAY.get(slug, slug)


def _load_patterns() -> list[dict]:
    payload = json.loads(PATTERNS_JSON.read_text(encoding="utf-8"))
    entries = [e for v in payload["patterns"].values() for e in v]
    total_samples = len({s for e in entries for s in e["source_reports"]})
    return total_samples, entries  # type: ignore[return-value]


def emit_facts(type_cut: dict[str, int]) -> None:
    """按类型分别取头部：治理/处置/标准各自的 support 门槛（头部形态按类型差异大，全局排序会单类型倾斜）。"""
    total_samples, entries = _load_patterns()
    cand: list[dict] = []
    for t, floor in type_cut.items():
        cand += [e for e in entries if e["pattern_type"] == t and e["support_count"] >= floor]
    cand.sort(key=lambda e: ({"治理": 0, "处置": 1, "标准": 2}.get(e["pattern_type"], 3), -e["support_count"], -e["occurrence_count"], e["subject_name"], e["object_name"]))
    facts = []
    for e in cand:
        facts.append(
            {
                "pattern_id": e["pattern_id"],
                "pattern_type": e["pattern_type"],
                "pair": f"{e['subject_name']}（{e['subject_etype']}）→ {e['object_name']}（{e['object_etype']}）",
                "predicate": e["predicate"],
                "support": e["support_count"],
                "occurrence": e["occurrence_count"],
                "total_samples": total_samples,
                "source_reports": [_display(s) for s in e["source_reports"]],
                "subject_variants": [v["name"] for v in e.get("subject_variants", [])],
                "object_variants": [v["name"] for v in e.get("object_variants", [])],
                "mechanical_desc": e["pattern_desc"],
            }
        )
    FACTS_JSON.write_text(json.dumps({"emitted_at": datetime.now(UTC).isoformat(), "count": len(facts), "facts": facts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"落盘: {FACTS_JSON}（{len(facts)} 条；全库样例 {total_samples} 份）")
    band: dict[int, int] = {}
    for f in facts:
        band[f["support"]] = band.get(f["support"], 0) + 1
    print("support 分布（所选头部）:", dict(sorted(band.items(), reverse=True)))
    by_type: dict[str, int] = {}
    for f in facts:
        by_type[f["pattern_type"]] = by_type.get(f["pattern_type"], 0) + 1
    print("类型分布:", by_type)


def emit_review() -> None:
    refined = json.loads(REFINED_JSON.read_text(encoding="utf-8"))
    _, entries = _load_patterns()
    by_id = {e["pattern_id"]: e for e in entries}
    rows = []
    for pid, ref in refined.items():
        if pid.startswith("_"):
            continue
        e = by_id.get(pid)
        if e is None:
            print(f"告警：refined_desc 中 {pid} 不在当前 patterns.json，跳过")
            continue
        rows.append((e["support_count"], e, ref))
    rows.sort(key=lambda x: (-x[0], x[0] and -x[1]["occurrence_count"]))
    now = datetime.now(UTC).isoformat()
    L = [
        "# EIA B 库头部规律精炼人审清单",
        "",
        f"- 生成时间：{now}",
        f"- 待审 {len(rows)} 条（头部精炼，refined=true）；支持度定义=配对级去重报告数（全库样例 22 份）",
        "- 纪律声明：精炼仅做表述专业化与领域通识补充，support/来源为数据原值，未引入任何数值区间或标准号",
        "- 审法建议：抽检优先看「领域通识补充」是否越界（出现数据之外的数字/标准号即不合格）+ 领域表述是否准确",
        "",
        "| # | 类型 | 配对 | 谓词 | support | 精炼描述 | 来源报告（去重报告数=support） |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, (sup, e, ref) in enumerate(rows, 1):
        pair = f"{e['subject_name']}（{e['subject_etype']}）→ {e['object_name']}（{e['object_etype']}）"
        pred = PRED_DISPLAY.get(e["predicate"], e["predicate"])
        src = "、".join(_display(s) for s in e["source_reports"][:6]) + ("…" if len(e["source_reports"]) > 6 else "")
        desc = ref["refined_desc"].replace("|", "\\|")
        L.append(f"| {i} | {e['pattern_type']} | {pair} | {pred} | {sup} | {desc} | {src} |")
    REVIEW_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"落盘: {REVIEW_MD}（{len(rows)} 条）")


def main() -> None:
    parser = argparse.ArgumentParser(description="EIA 头部 pattern 精炼工作台（facts / review）")
    parser.add_argument("--facts", action="store_true", help="生成 LLM 撰写底稿 refined_facts.json")
    parser.add_argument("--review", action="store_true", help="生成人审清单 refined_review.md")
    parser.add_argument("--g-min", type=int, default=19, help="治理规律 support 门槛（默认 19）")
    parser.add_argument("--d-min", type=int, default=12, help="处置规律 support 门槛（默认 12）")
    parser.add_argument("--s-min", type=int, default=1, help="标准规律 support 门槛（默认 1，全量）")
    args = parser.parse_args()
    if args.facts:
        emit_facts({"治理": args.g_min, "处置": args.d_min, "标准": args.s_min})
    if args.review:
        emit_review()


if __name__ == "__main__":
    main()
