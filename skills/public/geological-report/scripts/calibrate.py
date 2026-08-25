#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate.py — 从样例章节统计深度基线，生成 depth_targets.json（深度目标门的 targets）。

用法：
    python -X utf8 calibrate.py --samples-dir ../references/samples/exploration --output ../references/depth_targets.json

- 样例文件命名 chN*.md（同章多样例 chN_a.md/chN_b.md，按章聚中位数；Phase 1 每章 1 份）。
- 非 chN 开头的 .md（如 source.md）自动过滤。
- 输出确定性幂等：sort_keys、无时间戳——同输入必同字节。
- 样例缺节号标题 → rc=1 绝不静默产出空 targets（维护者脚本，崩溃即停）。
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from build_output import effective_chars

FNAME_RE = re.compile(r"^ch(\d+)")
SAMPLE_NO_RE = re.compile(r"^#{2,4}\s+\d+(?:\.\d+)*\s", re.MULTILINE)
SEPARATOR_RE = re.compile(r"^\|[\s\-|:]+\|?$")


def chapter_stats(text: str) -> dict:
    """单份样例统计：eff（与 build 门同口径）/ 表行数（separator 不计）/ 叙述段落数。"""
    lines = text.splitlines()
    table_rows = sum(1 for l in lines if l.strip().startswith("|") and not SEPARATOR_RE.match(l.strip()))
    paragraphs, in_para = 0, False
    for l in lines:
        s = l.strip()
        narrative = bool(s) and not s.startswith("#") and not s.startswith("|")
        if narrative and not in_para:
            paragraphs += 1
        in_para = narrative
    return {"eff": effective_chars(text), "table_rows": table_rows, "paragraphs": paragraphs}


def main() -> int:
    ap = argparse.ArgumentParser(description="样例章节 → depth_targets.json 深度基线")
    ap.add_argument("--samples-dir", required=True, help="样例目录（chN*.md）")
    ap.add_argument("--output", required=True, help="depth_targets.json 输出路径")
    args = ap.parse_args()

    samples_dir = Path(args.samples_dir)
    if not samples_dir.is_dir():
        print(f"[calibrate] 样例目录不存在：{samples_dir}", file=sys.stderr)
        return 1

    files = sorted(p for p in samples_dir.glob("*.md") if FNAME_RE.match(p.name))
    grouped = defaultdict(list)
    for p in files:
        text = p.read_text(encoding="utf-8")
        if not SAMPLE_NO_RE.search(text):
            print(f"[calibrate] {p.name} 无节号标题（需 `## N …` / `### N.M …` 形式）——拒绝生成空基线", file=sys.stderr)
            return 1
        grouped[f"ch{FNAME_RE.match(p.name).group(1)}"].append(chapter_stats(text))

    if not grouped:
        print(f"[calibrate] {samples_dir} 下无 chN*.md 样例", file=sys.stderr)
        return 1

    per_chapter = {
        ch_id: {
            "median_eff": int(statistics.median(s["eff"] for s in stats)),
            "median_table_rows": int(statistics.median(s["table_rows"] for s in stats)),
            "median_paragraphs": int(statistics.median(s["paragraphs"] for s in stats)),
        }
        for ch_id, stats in sorted(grouped.items())
    }
    doc = {
        "coefficient": 0.6,
        "scale_floor": 0.25,
        "per_signal_penalty": 0.05,
        "missing_table_weight": 8,
        "samples": [p.name for p in files],
        "per_chapter": per_chapter,
    }
    out = Path(args.output)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"CALIBRATED: {len(per_chapter)} chapters -> {out}")
    for ch_id, c in per_chapter.items():
        print(f"  {ch_id}: median_eff={c['median_eff']} tables={c['median_table_rows']} paras={c['median_paragraphs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
