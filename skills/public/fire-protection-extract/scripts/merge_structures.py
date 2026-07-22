#!/usr/bin/env python3
"""Merge multiple parse_spec.py structure.jsons into one.

Paragraph indices are offset. Table numbers from non-primary docs are prefixed
with [N] to avoid collisions. Headings track source_doc origin.
"""
import json
import sys
from pathlib import Path


def merge_structures(structures):
    merged_paras = []
    merged_tables = {}
    merged_headings = []

    for si, s in enumerate(structures):
        offset = len(merged_paras)
        for p in s["paras"]:
            p2 = dict(p)
            p2["i"] = offset + p["i"]
            p2["source_doc"] = si
            merged_paras.append(p2)

        for h in s.get("headings", []):
            h2 = dict(h)
            h2["para_i"] = offset + h["para_i"]
            h2["source_doc"] = si
            merged_headings.append(h2)

        for no, t in s.get("tables", {}).items():
            key = no if si == 0 else f"[{si}]{no}"
            merged_tables[key] = dict(t)

    return {
        "paras": merged_paras,
        "tables": merged_tables,
        "headings": merged_headings,
    }


def main(argv):
    if len(argv) < 2:
        print("usage: merge_structures.py <out.json> <s1.json> [s2.json ...]", file=sys.stderr)
        return 2

    out_path = Path(argv[0])
    structures = [json.loads(Path(p).read_text(encoding="utf-8")) for p in argv[1:]]
    merged = merge_structures(structures)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK merged {len(structures)} docs: {len(merged['paras'])} paras, {len(merged['tables'])} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
