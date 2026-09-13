"""chapter_planner 冒烟回归（T8）：manifest 章集/无 ch10 残留、F3 反查命中 ch4、空 stage 守卫。"""
import json
from pathlib import Path

import pytest

import chapter_planner  # conftest.py 已注入 scripts/
from conftest import run_cli

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")


def _build_manifest(tmp_path):
    out = str(tmp_path / "m.json")
    rc, printed = run_cli(chapter_planner.main, ["manifest", "--stage", STAGE, "--output", out])
    assert rc == 0, printed
    return out, printed, json.load(open(out, encoding="utf-8"))


def test_manifest_chapter_set_no_ch10(tmp_path):
    _, printed, m = _build_manifest(tmp_path)
    assert "MANIFEST_READY" in printed and "chapters=11" in printed
    ids = [c["id"] for c in m["chapters"]]
    assert ids == ["front_matter"] + [f"ch{i}" for i in range(1, 10)] + ["compliance_appendix"]
    assert len(ids) == 11 and "ch10" not in ids
    assert m["always_dependent"] == ["compliance_appendix"]  # 掘进无投影章（J3）


def test_impacted_f3_hits_ch4_not_ch10(tmp_path):
    _, _, m = _build_manifest(tmp_path)
    hit = chapter_planner.impacted_chapters(["F3"], ["equipment"], m)
    assert "ch4" in hit           # F3 渲染在 ch4 管线敷设表——T7 评审 Important-4 反查断链修正
    assert "ch5" in hit and "ch3" in hit  # C5 联锁 + equipment 族
    assert "ch10" not in hit
    assert "compliance_appendix" in hit


def test_empty_stage_guard_fails(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"chapters": {}}), encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        run_cli(chapter_planner.main, ["manifest", "--stage", str(empty),
                                       "--output", str(tmp_path / "m.json")])
    assert ei.value.code != 0 and "MANIFEST_INVALID" in str(ei.value.code)
