"""源②：fulltext/parse.json → 五类金矿表候选行（源强/沉陷/监测/措施/敏感点）。

# ponytail: txt 无版式 → 关键词锚点+数值行启发式，召回优先、精度靠人审；
# 子项目 2 重新解析 docx 拿真表格后本脚本退役为对照器。
用法：python table_extract.py --src .wolf/tmp/eia-samples --out out/table_candidates.json

执行时已核查 corpus 全部 *-parse.json（2026-09-28）：键层只有 table_count/tbl_count/
n_tables/tables(int) 等计数，无任何可提取的单元格/行级表格数据（sijitun-parse.json
的 tables=197 也是 int）——故无 parse.json 表格层可并入，结构化仅来自 fulltext txt。
"""
import argparse
import json
import re
from pathlib import Path

TABLE_ANCHORS: dict[str, tuple[str, ...]] = {
    "source_strength": ("源强", "排放源源强", "产生量", "削减量", "排放量"),
    "subsidence": ("沉陷预测", "地表沉陷", "最大下沉", "岩移预计"),
    "monitoring": ("监测计划", "监控计划", "监测点位", "跟踪监测"),
    "measures": ("环保措施", "治理措施", "污染防治措施", "综合整治方案"),
    "sensitive": ("环境保护目标", "敏感点", "保护目标一览", "敏感目标"),
}
NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")
CONTEXT_WINDOW = 3  # 锚点命中行 ±N 行


def extract_rows(text: str) -> dict[str, list[dict]]:
    lines = text.splitlines()
    out: dict[str, list[dict]] = {}
    for cat, anchors in TABLE_ANCHORS.items():
        rows: list[dict] = []
        for i, line in enumerate(lines):
            if not any(a in line for a in anchors):
                continue
            nums = NUM.findall(line)
            if not nums:  # 锚点行本身无数值 → 看后续窗口
                window = "\n".join(lines[i + 1: i + 1 + CONTEXT_WINDOW])
                nums = NUM.findall(window)
            if nums:
                rows.append({"line": i + 1, "text": line.strip()[:200], "values": nums[:8]})
        out[cat] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".wolf/tmp/eia-samples")
    ap.add_argument("--out", default="out/table_candidates.json")
    args = ap.parse_args()
    src = Path(args.src)
    reports: dict[str, dict] = {}
    for txt in sorted(src.glob("*-fulltext.txt")) + ([src / "fulltext.txt"] if (src / "fulltext.txt").exists() else []):
        reports[txt.name] = extract_rows(txt.read_text(encoding="utf-8", errors="ignore"))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, cats in reports.items():
        print(name, {k: len(v) for k, v in cats.items()})


if __name__ == "__main__":
    main()
