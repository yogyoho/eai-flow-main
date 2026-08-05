#!/usr/bin/env python3
"""一次性迁移：旧契约 → 阶段子目录 + 新格式（两层：大纲+映射）。

用法:
  migrate_contracts.py <旧契约.json> <struct.json> <阶段> <新大纲.json> <输出.json>
支持旧字符串锚(anchor/from/to)与旧索引(paras)两种来源格式；按 fire 标题对齐新大纲；
保留 conflict_assertions 到对应映射源上（grounding_check 从映射源读取）。

对齐策略：
  - 优先按 fire 标题精确匹配旧节；
  - 标题不匹配但旧节携带 conflict_assertions 时，按节号(§X.Y)兜底对齐
    （如 §5.1 稳高压消防给水系统 → 新大纲 §5.1 室外消防水系统），
    保证项目专属断言（DN200/DN150 守卫）不随迁移丢失；
  - 其余不匹配节留空，由后续 E3 重新锚定。
"""
import json
import re
import sys
from pathlib import Path


def find_para_index(struct, needle):
    for p in struct.get("paras", []):
        if needle in p["text"]:
            return p["i"]
    return None


def convert_source(src, struct):
    """旧源 → 新源（paras 索引）。无法解析返回 None。"""
    if not isinstance(src, dict):
        return None
    kind = src.get("kind")
    if kind == "para":
        if "paras" in src and isinstance(src.get("paras"), list):
            return dict(src)  # 已是新格式
        i = find_para_index(struct, src.get("anchor", ""))
        if i is None:
            return None
        out = {"kind": "para", "paras": [i]}
        for extra in ("authoritative", "conflict_note"):
            if src.get(extra):
                out[extra] = src[extra]
        return out
    if kind in ("range", "para_run"):
        if "paras" in src and isinstance(src.get("paras"), list) and len(src.get("paras", [])) >= 2:
            out = dict(src)
            out["kind"] = "range"
            return out
        a = find_para_index(struct, src.get("from", ""))
        b = find_para_index(struct, src.get("to", ""))
        if a is None or b is None or a > b:
            return None
        return {"kind": "range", "paras": [a, b]}
    if kind == "table":
        return {"kind": "table", "no": src.get("no", "")}
    return None


def _sec_no(fire):
    m = re.match(r"^\d+(\.\d+)*", fire)
    return m.group() if m else None


def align_to_outline(old_mapping, struct, outline):
    """按新大纲逐节对齐：旧映射按 fire 标题匹配（§X.Y 数字兜底，仅断言节）；
    保留 conflict_assertions 到对应映射源上（grounding_check 从映射源读取）。"""
    old_sections = old_mapping.get("sections", [])
    old_by_fire = {s.get("fire", ""): s for s in old_sections}
    old_by_no = {}
    for s in old_sections:
        no = _sec_no(s.get("fire", ""))
        if no and no not in old_by_no:
            old_by_no[no] = s

    sources = []
    for sec in outline["sections"]:
        cls = sec.get("class")
        if cls in ("heading", "template", "compute"):
            sources.append(None)
            continue
        old_sec = old_by_fire.get(sec["fire"])
        if old_sec is None and cls == "verbatim":
            no = _sec_no(sec["fire"])
            if no:
                cand = old_by_no.get(no)
                # 仅当旧节携带 conflict_assertions 才按节号兜底，避免把
                # 标题不同/意义不同的旧节内容错配进新大纲节（如 仓库项目 重E3）。
                if cand and (cand.get("conflict_assertions") or []):
                    old_sec = cand
        if not old_sec:
            sources.append(None)
            continue
        converted = [c for c in (convert_source(s, struct) for s in old_sec.get("sources", []) or []) if c]
        cas = old_sec.get("conflict_assertions", []) or []
        if cas and converted:
            first = converted[0]
            if "conflict_assertions" not in first:
                first = dict(first)
                first["conflict_assertions"] = cas
                converted[0] = first
        sources.append(converted or None)
    return {"sources": sources}


def main(argv):
    if len(argv) != 5:
        print("usage: migrate_contracts.py <旧契约.json> <struct.json> <阶段> <新大纲.json> <输出.json>", file=sys.stderr)
        return 2
    old = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    struct = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    stage = argv[2]
    outline = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
    out_path = Path(argv[4])
    mapping = align_to_outline(old, struct, outline)
    mapping["_stage"] = stage
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = [sec["fire"] for idx, sec in enumerate(outline["sections"])
               if sec.get("class") == "verbatim" and not (mapping["sources"][idx])]
    print(f"MIGRATED -> {out_path} ({len(mapping['sources'])} sections)")
    if missing:
        print("MISSING (需E3补齐): " + "; ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
