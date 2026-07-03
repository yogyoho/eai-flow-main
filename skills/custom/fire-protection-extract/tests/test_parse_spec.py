import json
from pathlib import Path
from scripts.parse_spec import parse_spec


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
