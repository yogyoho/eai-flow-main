#!/usr/bin/env python3
"""Contract library: persist successful mapping contracts and find the best match for a new document.

Store: skills/public/fire-protection-extract/contracts/
  contracts/{stage}/{name}.json — per-project mapping, grouped by design stage (初步设计/基础设计)
  contracts/_index.json         — {stage: {name: fingerprint}} index for similarity search

Format: only index-based sources (paras:[i]) are accepted; the deprecated string-anchor
format (anchor/from/to) is rejected by validate_format().

Fault tolerance: silent degradation — if the store is unavailable, find_best returns null.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
INDEX_PATH = CONTRACTS_DIR / "_index.json"


def _ensure_dir():
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)


def _read_index():
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_index(data):
    _ensure_dir()
    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, INDEX_PATH)  # atomic on POSIX; best-effort atomic on Windows


def fingerprint_from_structure(structure):
    """Extract a lightweight structural fingerprint from parse_spec.py output."""
    headings = structure.get("headings", [])
    heading_texts = [h["text"] for h in headings]
    table_nos = list(structure.get("tables", {}).keys())
    para_count = len(structure.get("paras", []))
    return {
        "heading_texts": heading_texts,
        "table_nos": table_nos,
        "para_count": para_count,
    }


def _jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _heading_similarity(fp_a, fp_b):
    """Similarity based on heading keyword overlap (0-1)."""
    # Extract keywords from headings (first 4 chars of each heading, for CJK)
    kw_a = set(h[:4] for h in fp_a.get("heading_texts", []))
    kw_b = set(h[:4] for h in fp_b.get("heading_texts", []))
    return _jaccard(kw_a, kw_b)


def _table_similarity(fp_a, fp_b):
    """Similarity based on table number prefix overlap (0-1)."""
    prefixes_a = set(t.split(".")[0] if "." in t else t for t in fp_a.get("table_nos", []))
    prefixes_b = set(t.split(".")[0] if "." in t else t for t in fp_b.get("table_nos", []))
    return _jaccard(prefixes_a, prefixes_b)


def _combined_similarity(fp_a, fp_b):
    """Weighted similarity: 70% heading + 30% table structure."""
    return 0.7 * _heading_similarity(fp_a, fp_b) + 0.3 * _table_similarity(fp_a, fp_b)


def validate_format(mapping):
    """新格式合法返回 None；旧字符串锚格式返回错误说明。"""
    if not isinstance(mapping, dict):
        return "契约必须是 JSON 对象"
    def _has_anchor(node):
        # 递归检查旧格式锚标记(anchor/from/to)。新格式 sources 是
        # 按章节对齐的嵌套结构 ([None, [{"kind":"range","paras":[...]}], ...])，
        # None/列表/占位标量均不是锚标记。
        if isinstance(node, dict):
            return "anchor" in node or "from" in node or "to" in node
        if isinstance(node, list):
            return any(_has_anchor(x) for x in node)
        return False
    if "sections" in mapping and any(_has_anchor(s.get("sources")) for s in mapping.get("sections", [])):
        return "旧字符串锚格式(anchor/from/to)已废弃，请用 paras 索引新格式并重跑 E3"
    if "sources" in mapping and _has_anchor(mapping["sources"]):
        return "旧字符串锚格式(anchor/from/to)已废弃，请用 paras 索引新格式并重跑 E3"
    return None


def save_contract(name, stage, mapping, structure):
    _ensure_dir()
    contract_dir = CONTRACTS_DIR / stage
    contract_dir.mkdir(parents=True, exist_ok=True)
    contract_path = contract_dir / f"{name}.json"
    fp = fingerprint_from_structure(structure)
    contract = dict(mapping)
    contract.setdefault("_stage", stage)
    contract["_saved_at"] = datetime.now().isoformat()
    contract["_fingerprint"] = fp
    tmp_path = contract_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, contract_path)
    index = _read_index()
    index.setdefault(stage, {})[name] = fp
    _write_index(index)
    return contract_path


def load_contract(name, stage):
    try:
        contract_path = CONTRACTS_DIR / stage / f"{name}.json"
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _stage_of(name, index):
    for st, names in index.items():
        if name in names:
            return st
    return None


def find_best(structure, stage=None, min_similarity=0.3):
    """找到 best-matching contract。同分时取 _saved_at 最新者；旧格式契约跳过。"""
    index = _read_index()
    if not index:
        return None
    stages = [stage] if stage else list(index.keys())
    target_fp = fingerprint_from_structure(structure)
    best_name, best_sim, best_saved = None, 0.0, ""
    best_stage = None
    for st in stages:
        for name, stored_fp in index.get(st, {}).items():
            sim = _combined_similarity(target_fp, stored_fp)
            if sim < min_similarity or sim < best_sim:
                continue
            mapping = load_contract(name, st)
            if mapping is None or validate_format(mapping):
                continue  # 旧格式/不可读 → 跳过
            saved = mapping.get("_saved_at", "")
            if sim > best_sim or (sim == best_sim and saved > best_saved):
                best_name, best_sim, best_saved, best_stage = name, sim, saved, st
    if best_name:
        mapping = load_contract(best_name, best_stage)
        if mapping:
            return best_name, mapping, best_sim
    return None


# ── CLI ────────────────────────────────────────────────────────────

def main(argv):
    if len(argv) < 1:
        print("usage: contract_store.py <save|load|find|list> [args...]", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "save":
        # usage: save <stage> <name> <structure.json>   (mapping 从 stdin 读)
        if len(argv) != 4:
            print("usage: contract_store.py save <stage> <name> <structure.json>", file=sys.stderr)
            return 2
        stage, name = argv[1], argv[2]
        structure = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        mapping = json.loads(sys.stdin.read())
        err = validate_format(mapping)
        if err:
            print(f"CONTRACT_FORMAT_MISMATCH: {err}", file=sys.stderr)
            return 3
        path = save_contract(name, stage, mapping, structure)
        print(f"SAVED {name} ({stage}) -> {path}")
        return 0
    if cmd == "load":
        # usage: load <stage> <name>
        if len(argv) != 3:
            print("usage: contract_store.py load <stage> <name>", file=sys.stderr)
            return 2
        mapping = load_contract(argv[2], argv[1])
        if mapping:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
        else:
            print("NOT_FOUND")
        return 0
    if cmd == "find":
        # usage: find <stage> <structure.json>
        if len(argv) != 3:
            print("usage: contract_store.py find <stage> <structure.json>", file=sys.stderr)
            return 2
        structure = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        result = find_best(structure, stage=argv[1])
        if result:
            name, mapping, sim = result
            out = {k: v for k, v in mapping.items() if not k.startswith("_")}
            print(json.dumps({"name": name, "similarity": round(sim, 3), "mapping": out},
                             ensure_ascii=False, indent=2))
        else:
            print("NO_MATCH")
        return 0
    if cmd == "list":
        for st, names in _read_index().items():
            for name in names:
                print(f"{st}/{name}")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
