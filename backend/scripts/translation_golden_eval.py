"""Golden-set translation quality eval (EAI-CUSTOM, T7).

自动判两轴（设计构件 5 翻译质量轨的可机检部分）：
  数值保真 = checks.numeric_multiset_violations（fr/en 约定分侧归一）
  术语一致 = checks.terminology_violations（force 命中 + forbid 原样保留）
可读性/忠实度 = 人工盲评列（不在本脚本范围——设计前提 5：不入机检）。

用法:
  PYTHONPATH=. uv run python scripts/translation_golden_eval.py translation_golden_set.jsonl [--lang fr]
  （--lang 覆盖行内缺省 source_lang；退出码 0=全绿 1=有违例）
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from app.extensions.translation import checks  # noqa: E402


def evaluate_row(row: dict, default_lang: str) -> dict:
    lang = row.get("source_lang") or default_lang
    source = row.get("source", "")
    reference = row.get("reference", "")
    violations = checks.numeric_multiset_violations(source, reference, lang)
    term_violations = checks.terminology_violations(
        source, reference, row.get("force_terms") or {}, set(row.get("dont_translate") or [])
    )
    return {
        "category": row.get("category", ""),
        "numeric_ok": not violations,
        "numeric_detail": violations,
        "terminology_ok": not term_violations,
        "terminology_detail": term_violations,
        "readability": "manual",  # 人工盲评列（MQM 式标注更佳）
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden-set numeric+terminology eval")
    parser.add_argument("golden_set", help="translation_golden_set.jsonl 路径")
    parser.add_argument("--lang", default="en", help="行内未标 source_lang 时的缺省")
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in Path(args.golden_set).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith('{"_readme"')
    ]
    if not rows:
        print("golden set empty — 样例闸产出后填入", file=sys.stderr)
        return 1

    results = [evaluate_row(row, args.lang) for row in rows]
    numeric_pass = sum(1 for r in results if r["numeric_ok"])
    term_pass = sum(1 for r in results if r["terminology_ok"])
    for row, r in zip(rows, results):
        if not r["numeric_ok"] or not r["terminology_ok"]:
            print(f"[FAIL] ({r['category']}) {row['source'][:60]}")
            if r["numeric_detail"]:
                print(f"   numeric: {r['numeric_detail']}")
            if r["terminology_detail"]:
                print(f"   terminology: {r['terminology_detail']}")
    print(f"\nnumeric fidelity : {numeric_pass}/{len(results)}")
    print(f"terminology match: {term_pass}/{len(results)}")
    print("readability      : manual（人工盲评，不入机检——设计前提 5）")
    return 0 if numeric_pass == len(results) and term_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
