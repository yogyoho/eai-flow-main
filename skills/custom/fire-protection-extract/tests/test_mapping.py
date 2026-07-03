import json
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[1] / "references" / "fire_spec_mapping.json"


def load_mapping():
    return json.loads(MAPPING.read_text(encoding="utf-8"))


def test_mapping_schema():
    m = load_mapping()
    assert "sections" in m and len(m["sections"]) >= 20
    valid_classes = {"verbatim", "template", "compute"}
    valid_kinds = {"para", "para_run", "table"}
    for sec in m["sections"]:
        assert "fire" in sec and "class" in sec
        assert sec["class"] in valid_classes
        for src in sec.get("sources", []) or []:
            assert src["kind"] in valid_kinds
            if src["kind"] == "para":
                assert src.get("anchor")
            elif src["kind"] == "para_run":
                assert src.get("from") and src.get("to")
            elif src["kind"] == "table":
                assert src.get("no")


def test_conflict_field_has_authoritative_source():
    m = load_mapping()
    sec511 = next(s for s in m["sections"] if s["fire"].startswith("5.1"))
    auth = [s for s in sec511["sources"] if s.get("authoritative")]
    assert auth and "10L/s" in auth[0]["anchor"]
