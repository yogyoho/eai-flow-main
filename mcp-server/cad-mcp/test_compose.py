"""Self-check for compose_drawing M1: roadway_section → DXF + PNG, validate passes.

Runs the edp core directly (no MCP layer / path resolution) so it's hermetic:
  python test_compose.py
Covers the three layout placement.kinds (region, point) + annotations + frame +
the symbol resolver (survey_point), proving the core paths M2 (schematic node
symbols) will lean on. Validates the honest way: report + validations, not volume.
"""
import tempfile
from pathlib import Path

from edp import ComposeError, compose

DOMAINS_ROOT = Path(__file__).resolve().parent / "domains"


def _roadway_intent():
    return {
        "domain": "mine",
        "drawing_type": "roadway_section",
        "frame": {"standard": "GB14689", "size": "A3", "scale": "1:50"},
        "layers": [{"name": "巷道", "color": 3}, {"name": "支护", "color": 5}],
        "entities": [
            {"id": "opening", "type": "roadway", "layer": "巷道",
             "placement": {"kind": "region", "coords": [[0, 0], [4000, 0], [4000, 3000], [0, 3000]]}},
            {"id": "lining", "type": "lining", "layer": "支护",
             "placement": {"kind": "region", "coords": [[150, 150], [3850, 150], [3850, 2850], [150, 2850]], "hatch_pattern": "ANSI31"}},
            {"id": "sp-1", "type": "survey_point", "layer": "测点",
             "placement": {"kind": "point", "at": [2000, 1500]}},
        ],
        "annotations": [
            {"kind": "dimension", "from": [0, 0], "to": [4000, 0]},
            {"kind": "elevation", "at": [2000, 3300], "value_m": -450.0},
        ],
        "title_block": {"mine": "XX煤矿", "level": "-450", "drawing_name": "主运巷断面图", "date": "2026-06"},
    }


def test_unknown_domain():
    try:
        compose({"domain": "nope", "drawing_type": "x"}, DOMAINS_ROOT)
        assert False, "expected ComposeError"
    except ComposeError as exc:
        assert exc.code == "unknown_domain", exc.code
    print("OK: unknown_domain rejected")


def test_unknown_drawing_type():
    try:
        compose({"domain": "mine", "drawing_type": "nope"}, DOMAINS_ROOT)
        assert False, "expected ComposeError"
    except ComposeError as exc:
        assert exc.code == "unknown_drawing_type", exc.code
    print("OK: unknown_drawing_type rejected")


def test_compose_roadway_section():
    with tempfile.TemporaryDirectory() as tmp:
        doc, report, validations = compose(_roadway_intent(), DOMAINS_ROOT)
        assert report.skipped == [], report.skipped
        assert report.placed == 3, f"expected 3 placed, got {report.placed}"
        out = Path(tmp) / "roadway_section.dxf"
        doc.saveas(str(out))
        assert out.exists() and out.stat().st_size > 0

        from edp.render import rasterize

        png = Path(tmp) / "roadway_section.png"
        rasterize(doc, png)
        assert png.exists() and png.stat().st_size > 0

        failed = [c for c in validations if not c["passed"]]
        assert not failed, f"validation failures: {failed}"
        print(f"OK: placed={report.placed} validations={len(validations)} all-pass; DXF + PNG written under {tmp}")


def test_unknown_placement_kind_skipped_not_crash():
    """An entity with a placement.kind this strategy doesn't handle is skipped,
    not raised — the M2 schematic kind must not crash the layout strategy."""
    intent = _roadway_intent()
    intent["entities"].append({"id": "future-node", "type": "pump", "placement": {"kind": "node", "at": [1000, 1000]}})
    doc, report, validations = compose(intent, DOMAINS_ROOT)
    assert any(s["id"] == "future-node" for s in report.skipped), report.skipped
    assert report.placed == 3, report.placed
    print("OK: unknown placement.kind (node) skipped, not crashed")


if __name__ == "__main__":
    test_unknown_domain()
    test_unknown_drawing_type()
    test_compose_roadway_section()
    test_unknown_placement_kind_skipped_not_crash()
    print("\nALL M1 SELF-CHECKS PASSED")
