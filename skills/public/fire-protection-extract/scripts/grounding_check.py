#!/usr/bin/env python3
"""逐字溯源校验 + 锚可达性 + 覆盖检查（两层：大纲+映射）。

三件事：
1. 锚可达：mapping 里每个 verbatim 节的 para/range/table 锚都能在 structure 里找到。
2. 逐字溯源：report 里每个被抄录块必须是源语料的子串（空格/换行归一化后比对）。
3. 完整性：大纲里每个 verbatim 节必须有非空 sources——杜绝静默漏抄（空章节）。
"""
import json
import re
import sys
from pathlib import Path


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
    if b.startswith("[需") or b.startswith("[⚠"):
        return True
    if b.startswith("<!--"):
        return True
    if b.startswith("> 源:"):
        return True
    return False


def _search_text(block):
    b = block.strip()
    if b.startswith("|"):
        cells = []
        for line in b.splitlines():
            line = line.strip()
            if not line or not line.startswith("|"):
                continue
            row_cells = [c.strip() for c in line.strip("|").split("|")]
            if row_cells and all(c == "" or set(c) <= set("-") for c in row_cells):
                continue
            cells.extend(row_cells)
        return "".join(cells)
    lines = [ln for ln in b.splitlines()
             if not (ln.strip().startswith("<!--") or ln.strip().startswith("> 源:"))]
    return "\n".join(lines)


def check(report_md, structure, outline, mapping):
    paras, tables = structure["paras"], structure["tables"]
    missing = []
    n_paras = len(paras)
    sections = outline.get("sections", [])
    sources_by_idx = mapping.get("sources", [])

    # 1. 锚可达（仅 verbatim 节）
    for idx, sec in enumerate(sections):
        if sec.get("class") != "verbatim":
            continue
        sources = sources_by_idx[idx] if idx < len(sources_by_idx) else []
        sources = sources or []
        if not isinstance(sources, list):  # 非列表源（如 dict/str）一律视为无源，防逐字遍历报错
            sources = []
        for src in sources:
            ok = False
            kind = src.get("kind", "")
            if kind in ("para", "range", "para_run"):
                idxs = src.get("paras", [])
                # 语义与 extract.py 对齐：range 需 len>=2 且正序；para 只用 idxs[0]
                if kind in ("range", "para_run"):
                    ok = (len(idxs) >= 2 and all(isinstance(i, int) and 0 <= i < n_paras for i in idxs)
                          and idxs[0] <= idxs[1])
                    used = idxs[:2]
                else:  # para — extract uses only idxs[0]
                    ok = (len(idxs) >= 1 and isinstance(idxs[0], int) and 0 <= idxs[0] < n_paras)
                    used = [idxs[0]]
                if ok:
                    ok = all(paras[i].get("text", "").strip() for i in used)
            elif kind == "table":
                ok = src.get("no", "") in tables
            if not ok:
                label = src.get("no") or str(src.get("paras", src))
                missing.append((sec["fire"], label))

    # 2. 逐字溯源
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

    # 3. 完整性：大纲每个 verbatim 节必须有非空 sources
    uncovered = [sec["fire"] for idx, sec in enumerate(sections)
                 if sec.get("class") == "verbatim"
                 and not (sources_by_idx[idx] if idx < len(sources_by_idx) else [])]

    # 4. 冲突断言（大纲节级 + 映射源级）
    conflict_failures = []
    for idx, sec in enumerate(sections):
        for ca in sec.get("conflict_assertions", []) or []:
            mc = ca.get("must_contain")
            mnc = ca.get("must_not_contain")
            if mc and mc not in report_md:
                conflict_failures.append((sec["fire"], "missing", mc))
            if mnc and mnc in report_md:
                conflict_failures.append((sec["fire"], "unexpected", mnc))
        # 映射源级：项目专属断言（如 §5.1 必须含 DN200、不得含 DN150）
        sources = sources_by_idx[idx] if idx < len(sources_by_idx) else []
        sources = sources or []
        for src in sources:
            if not isinstance(src, dict):
                continue
            for ca in src.get("conflict_assertions", []) or []:
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
    if len(argv) != 4:
        print("usage: grounding_check.py <report.md> <structure.json> <outline.json> <mapping.json>", file=sys.stderr)
        return 2
    report = Path(argv[0]).read_text(encoding="utf-8")
    structure = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    outline = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    mapping = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
    res = check(report, structure, outline, mapping)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if (res["rate"] >= 0.85 and not res["missing_anchors"]
                 and not res["uncovered_sections"] and not res["conflict_failures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
