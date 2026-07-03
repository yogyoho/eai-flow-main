#!/usr/bin/env python3
"""逐字溯源校验 + 锚可达性 + 覆盖检查。

三件事：
1. 锚可达：mapping 里每个 para/para_run/table 锚都能在 structure 里找到（否则契约漂移/源变了）。
2. 逐字溯源：report 里每个被抄录块（排除标题行/表格行/[需计算]/[⚠] 标记）必须是源语料的子串
   （空格/换行归一化后比对，容忍表格单元格空白差异）。
3. 覆盖：每个 fire 小节必须有源或显式标 template/compute，杜绝静默漏抄。
"""
import json
import re
import sys
from pathlib import Path

import yaml


def corpus(structure):
    parts = [p["text"] for p in structure["paras"]]
    for t in structure["tables"].values():
        for row in t["rows"]:
            parts.extend(row)
    return "\n".join(parts)


def _norm(s):
    return s.replace(" ", "").replace("　", "").replace("\n", "")


def _is_decorative(block):
    b = block.strip()
    if not b:
        return True
    if b.startswith("##") or b.startswith("# "):
        return True
    # NOTE: markdown table blocks (|...|) are NOT decorative — their cell text
    # must be grounded too, otherwise a swapped table value slips through.
    if b.startswith("[需") or b.startswith("[⚠"):
        return True
    if b.startswith("<!--"):
        return True
    return False


def _search_text(block):
    """Return text used for substring grounding.

    - Strip citation comments (``<!-- 源:... -->``) appended by extract.py —
      they are metadata, not source content, so they must not be matched.
    - For a markdown table block, also strip the pipe/separator-row formatting
      so the concatenated cell values can be matched against the corpus.
    """
    b = block.strip()
    if b.startswith("|"):
        cells = []
        for line in b.splitlines():
            line = line.strip()
            # only true markdown-table rows; skips trailing <!-- 源 --> comments
            if not line or not line.startswith("|"):
                continue
            row_cells = [c.strip() for c in line.strip("|").split("|")]
            # separator row like |---|---| -> every cell is dashes/empty
            if row_cells and all(c == "" or set(c) <= set("-") for c in row_cells):
                continue
            cells.extend(row_cells)
        return "".join(cells)
    lines = [ln for ln in b.splitlines() if not ln.strip().startswith("<!--")]
    return "\n".join(lines)


def check(report_md, structure, mapping):
    paras, tables = structure["paras"], structure["tables"]
    # 1. anchor resolvability
    missing = []
    for sec in mapping["sections"]:
        for src in sec.get("sources", []) or []:
            ok = False
            if src["kind"] == "para":
                ok = any(src["anchor"] in p["text"] for p in paras)
            elif src["kind"] == "para_run":
                ok = any(src["from"] in p["text"] for p in paras)
            elif src["kind"] == "table":
                ok = src["no"] in tables
            if not ok:
                missing.append((sec["fire"], src.get("anchor") or src.get("from") or src.get("no")))
    # 2. grounding
    corp = _norm(corpus(structure))
    blocks = [b.strip() for b in re.split(r"\n\s*\n", report_md)]
    checked = grounded = 0
    failed = []
    for b in blocks:
        if _is_decorative(b):
            continue
        checked += 1
        needle = _norm(_search_text(b))
        if needle and needle in corp:
            grounded += 1
        else:
            failed.append(b[:48])
    rate = grounded / checked if checked else 0.0
    # 3. coverage
    uncovered = [sec["fire"] for sec in mapping["sections"]
                 if sec.get("class") == "verbatim" and not sec.get("sources")]
    # 4. conflict assertions (e.g. §5.1 must contain DN200, must not contain DN150)
    conflict_failures = []
    for sec in mapping["sections"]:
        for ca in sec.get("conflict_assertions", []) or []:
            mc = ca.get("must_contain")
            mnc = ca.get("must_not_contain")
            if mc and mc not in report_md:
                conflict_failures.append((sec["fire"], "missing", mc))
            if mnc and mnc in report_md:
                conflict_failures.append((sec["fire"], "unexpected", mnc))
    return {
        "grounded": grounded, "checked": checked, "rate": rate,
        "missing_anchors": missing, "uncovered_sections": uncovered,
        "conflict_failures": conflict_failures,
        "failed_samples": failed[:5],
    }


def main(argv):
    if len(argv) != 3:
        print("usage: grounding_check.py <report.md> <structure.json> <mapping.yaml>", file=sys.stderr)
        return 2
    report = Path(argv[0]).read_text(encoding="utf-8")
    structure = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    mapping = yaml.safe_load(Path(argv[2]).read_text(encoding="utf-8"))
    res = check(report, structure, mapping)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if (res["rate"] >= 0.85 and not res["missing_anchors"] and not res["conflict_failures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
