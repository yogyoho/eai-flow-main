#!/usr/bin/env python3
"""Contract library: persist successful mapping contracts and find the best match for a new document.

Store: skills/public/fire-protection-extract/contracts/
  contracts/{name}.json          — per-project mapping
  contracts/_index.json          — fingerprint index for similarity search

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


def save_contract(name, mapping, structure):
    """Save a mapping contract with its structural fingerprint.

    Args:
        name: project type name (e.g. '基地项目', '仓库项目')
        mapping: fire_spec_mapping.json-compatible dict
        structure: parse_spec.py output (used for fingerprinting)
    """
    _ensure_dir()
    contract_path = CONTRACTS_DIR / f"{name}.json"
    fp = fingerprint_from_structure(structure)

    # Save contract with embedded fingerprint (atomic write: temp file + rename)
    contract = dict(mapping)
    contract["_fingerprint"] = fp
    contract["_saved_at"] = datetime.now().isoformat()
    tmp_path = contract_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, contract_path)

    # Update index (atomic via _write_index)
    index = _read_index()
    index[name] = fp
    _write_index(index)
    return contract_path


def load_contract(name):
    """Load a saved mapping contract by name.  Returns None if not found."""
    try:
        contract_path = CONTRACTS_DIR / f"{name}.json"
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def find_best(structure, min_similarity=0.3):
    """Find the best-matching saved contract for a new document structure.

    Args:
        structure: parse_spec.py output
        min_similarity: minimum similarity threshold (0-1)

    Returns:
        (name, mapping, similarity) or None
    """
    index = _read_index()
    if not index:
        return None

    target_fp = fingerprint_from_structure(structure)
    best_name, best_sim = None, 0.0
    for name, stored_fp in index.items():
        sim = _combined_similarity(target_fp, stored_fp)
        if sim > best_sim:
            best_sim = sim
            best_name = name

    if best_name and best_sim >= min_similarity:
        mapping = load_contract(best_name)
        if mapping:
            return best_name, mapping, best_sim
    return None


def list_contracts():
    """Return [(name, fingerprint)] for all saved contracts."""
    index = _read_index()
    return list(index.items())


# ── CLI ────────────────────────────────────────────────────────────

def main(argv):
    if len(argv) < 1:
        print("usage: contract_store.py <save|load|find|list> [args...]", file=sys.stderr)
        return 2

    cmd = argv[0]
    if cmd == "save":
        if len(argv) != 3:
            print("usage: contract_store.py save <name> <structure.json>", file=sys.stderr)
            return 2
        name = argv[1]
        structure = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        mapping = json.loads(sys.stdin.read())
        path = save_contract(name, mapping, structure)
        print(f"SAVED {name} -> {path}")
        return 0

    if cmd == "load":
        if len(argv) != 2:
            print("usage: contract_store.py load <name>", file=sys.stderr)
            return 2
        mapping = load_contract(argv[1])
        if mapping:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
        else:
            print("NOT_FOUND")
        return 0

    if cmd == "find":
        if len(argv) != 2:
            print("usage: contract_store.py find <structure.json>", file=sys.stderr)
            return 2
        structure = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        result = find_best(structure)
        if result:
            name, mapping, sim = result
            # strip internal fields for output
            out = {k: v for k, v in mapping.items() if not k.startswith("_")}
            print(json.dumps({"name": name, "similarity": round(sim, 3), "mapping": out},
                             ensure_ascii=False, indent=2))
        else:
            print("NO_MATCH")
        return 0

    if cmd == "list":
        for name, fp in list_contracts():
            nh = len(fp.get("heading_texts", []))
            nt = len(fp.get("table_nos", []))
            print(f"{name}: {nh} headings, {nt} tables, {fp.get('para_count', 0)} paras")
        return 0

    print(f"unknown command: {cmd}", file=__import__("sys").stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
