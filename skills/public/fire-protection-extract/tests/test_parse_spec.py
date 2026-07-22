import json
from pathlib import Path

import pytest

from scripts.parse_spec import parse_spec
from ._fixtures import build_continuation_spec


def test_parse_extracts_paras_and_table(tiny_spec):
    data = parse_spec(tiny_spec)
    texts = [p["text"] for p in data["paras"]]
    assert "本项目为基地综合大队，占地面积23.8亩，特勤消防站。" in texts
    assert any("表2.1-1" in t for t in texts)
    assert "表2.1-1" in data["tables"]
    rows = data["tables"]["表2.1-1"]["rows"]
    assert rows[0] == ["项目", "水量"]
    assert rows[1] == ["室外消火栓", "30L/s"]
    assert data["paras"][0]["i"] == 0


def test_parse_writes_json(tmp_path, tiny_spec):
    from scripts.parse_spec import main
    out = tmp_path / "struct.json"
    rc = main([tiny_spec, str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["paras"]) > 0


@pytest.fixture
def continuation_spec(tmp_path):
    return build_continuation_spec(tmp_path / "cont.docx")


def test_parse_merges_continuation_table(continuation_spec):
    """续表4.5-1 rows must merge into 表4.5-1 (header deduped), not become a
    separate __autoN table. Without this, a mapping referencing 表4.5-1 only
    sees the first chunk — e.g. the weather table's 降雨/风向/地震 rows live in
    续表3.1-1 and would be missed."""
    data = parse_spec(continuation_spec)
    assert "表4.5-1" in data["tables"]
    t = data["tables"]["表4.5-1"]
    # header + 2 data rows (continuation's repeated header deduped)
    assert t["n_rows"] == 3, f"expected 3 merged rows, got {t['n_rows']}: {t['rows']}"
    rows = t["rows"]
    assert rows[0] == ["建筑", "部位", "风量"]
    assert rows[1] == ["执勤楼", "卫生间", "4788"]
    assert rows[2] == ["执勤楼", "淋浴间", "3600"]
    # no orphan continuation table
    assert not any(k.startswith("__auto") for k in data["tables"])
