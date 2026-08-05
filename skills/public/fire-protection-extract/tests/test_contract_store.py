import json
import pytest
from pathlib import Path
from scripts.contract_store import (
    fingerprint_from_structure,
    _jaccard,
    _heading_similarity,
    _table_similarity,
    _combined_similarity,
    save_contract,
    load_contract,
    find_best,
)


# ── fingerprint ─────────────────────────────────────────────────

def test_fingerprint_normal():
    s = {"headings": [{"level": 1, "text": "1 概述", "para_i": 0}],
         "tables": {"表1.1-1": {"title": "test"}},
         "paras": [{"i": 0, "text": "hello"}]}
    fp = fingerprint_from_structure(s)
    assert fp["heading_texts"] == ["1 概述"]
    assert fp["table_nos"] == ["表1.1-1"]
    assert fp["para_count"] == 1


def test_fingerprint_empty():
    fp = fingerprint_from_structure({})
    assert fp["heading_texts"] == []
    assert fp["table_nos"] == []
    assert fp["para_count"] == 0


# ── jaccard ────────────────────────────────────────────────────

def test_jaccard_both_empty():
    assert _jaccard(set(), set()) == 1.0


def test_jaccard_one_empty():
    assert _jaccard({"a"}, set()) == 0.0
    assert _jaccard(set(), {"a"}) == 0.0


def test_jaccard_partial():
    assert _jaccard({"a", "b"}, {"b", "c"}) == 1 / 3


# ── similarity ─────────────────────────────────────────────────

def test_heading_similarity_identical():
    fp = {"heading_texts": ["1 概述", "1.1 概况"]}
    assert _heading_similarity(fp, fp) == 1.0


def test_heading_similarity_disjoint():
    a = {"heading_texts": ["消防设施"]}
    b = {"heading_texts": ["环境保护"]}
    assert _heading_similarity(a, b) == 0.0


def test_table_similarity():
    a = {"table_nos": ["表1.1-1", "表1.1-2"]}
    b = {"table_nos": ["表1.1-1", "表2.1-1"]}
    # prefixes: a={"表1", "表1"}, b={"表1", "表2"} → intersection={"表1"}, union={"表1", "表2"} → 0.5
    sim = _table_similarity(a, b)
    assert 0.4 < sim < 0.6


def test_combined_similarity_range():
    fp = {"heading_texts": ["1 概述"], "table_nos": ["表1.1-1"]}
    s = _combined_similarity(fp, fp)
    assert 0.9 < s <= 1.0


# ── save / load roundtrip ──────────────────────────────────────

def test_save_load_roundtrip(tmp_path, monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "CONTRACTS_DIR", tmp_path / "contracts")
    monkeypatch.setattr(cs, "INDEX_PATH", tmp_path / "contracts" / "_index.json")

    mapping = {"report_title": "test", "sources": []}
    structure = {"headings": [{"level": 1, "text": "概述", "para_i": 0}], "tables": {}, "paras": []}
    save_contract("test_project", "基础设计", mapping, structure)

    loaded = load_contract("test_project", "基础设计")
    assert loaded is not None
    assert loaded["report_title"] == "test"
    assert "_fingerprint" in loaded


def test_load_not_found():
    assert load_contract("nonexistent", "基础设计") is None


def test_save_overwrites(tmp_path, monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "CONTRACTS_DIR", tmp_path / "contracts")
    monkeypatch.setattr(cs, "INDEX_PATH", tmp_path / "contracts" / "_index.json")

    save_contract("proj", "基础设计", {"report_title": "v1", "sources": []},
                  {"headings": [], "tables": {}, "paras": []})
    save_contract("proj", "基础设计", {"report_title": "v2", "sources": []},
                  {"headings": [], "tables": {}, "paras": []})
    assert load_contract("proj", "基础设计")["report_title"] == "v2"


# ── find_best ──────────────────────────────────────────────────

def test_find_best_empty_index(monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "_read_index", lambda: {})
    assert find_best({"headings": [], "tables": {}, "paras": []}) is None


def test_find_best_match(tmp_path, monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "CONTRACTS_DIR", tmp_path / "contracts")
    monkeypatch.setattr(cs, "INDEX_PATH", tmp_path / "contracts" / "_index.json")

    s1 = {"headings": [{"level": 1, "text": "消防设施", "para_i": 0}], "tables": {}, "paras": []}
    save_contract("fire_project", "基础设计", {"report_title": "fire", "sources": []}, s1)

    s2 = {"headings": [{"level": 1, "text": "消防系统", "para_i": 0}], "tables": {}, "paras": []}
    result = find_best(s2, stage="基础设计", min_similarity=0.1)
    assert result is not None
    name, mapping, sim = result
    assert name == "fire_project"
    assert mapping["report_title"] == "fire"
    assert sim > 0


def test_find_best_below_threshold(tmp_path, monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "CONTRACTS_DIR", tmp_path / "contracts")
    monkeypatch.setattr(cs, "INDEX_PATH", tmp_path / "contracts" / "_index.json")

    s1 = {"headings": [{"level": 1, "text": "消防设施", "para_i": 0}], "tables": {}, "paras": []}
    save_contract("fire", "基础设计", {"report_title": "x", "sources": []}, s1)

    s2 = {"headings": [{"level": 1, "text": "环境保护", "para_i": 0}], "tables": {}, "paras": []}
    assert find_best(s2, stage="基础设计", min_similarity=0.9) is None  # very different topics


# ── index ──────────────────────────────────────────────────────

def test_index_grouped_by_stage(tmp_path, monkeypatch):
    import scripts.contract_store as cs
    monkeypatch.setattr(cs, "CONTRACTS_DIR", tmp_path / "contracts")
    monkeypatch.setattr(cs, "INDEX_PATH", tmp_path / "contracts" / "_index.json")

    assert cs._read_index() == {}
    save_contract("a", "基础设计", {"sources": []}, {"headings": [], "tables": {}, "paras": []})
    index = cs._read_index()
    assert "基础设计" in index
    assert "a" in index["基础设计"]
