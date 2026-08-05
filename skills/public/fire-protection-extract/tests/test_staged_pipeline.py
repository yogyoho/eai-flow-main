import json
from pathlib import Path

OUTLINES = Path(__file__).resolve().parents[1] / "references" / "stage-outlines"


def _load(stage: str) -> dict:
    return json.loads((OUTLINES / f"{stage}.json").read_text(encoding="utf-8"))


def test_outline_files_exist():
    assert (OUTLINES / "初步设计.json").exists()
    assert (OUTLINES / "基础设计.json").exists()


def test_outline_structure_valid():
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        assert o["stage"] == stage
        assert "{项目名}" in o["report_title"]
        assert len(o["sections"]) > 15
        for sec in o["sections"]:
            assert sec["class"] in ("heading", "verbatim", "template", "compute")
            if sec["class"] == "template":
                assert sec["template"] in o["templates"]


def test_preliminary_outline_titles():
    o = _load("初步设计")
    titles = [s["fire"] for s in o["sections"]]
    assert "1 设计依据" in titles
    assert "1.1 设计依据的文件" in titles
    assert "2.4 工程的消防环境状况" in titles
    assert "4.1.1 装置的平面布置" in titles
    assert "4.6.1 建筑防火" in titles          # 样例正文含此节
    assert "5 消防系统设计" in titles
    assert "6 消防设施专项投资概算" in titles
    assert "7 图纸及表格" in titles
    assert not any("消防设施专项投资概算" in s["fire"] for s in o["sections"] if "8 " in s["fire"])


def test_basic_outline_titles():
    o = _load("基础设计")
    titles = [s["fire"] for s in o["sections"]]
    assert "1.3 及地方相关法规" in titles
    assert "4.5 建筑物通风措施" in titles
    assert "5.5 视频监控系统" in titles
    assert "6 灭火救援设施" in titles
    assert "8 图纸及表格" in titles
    assert "5.1 室外消防水系统" in titles       # 以样例正文为准（非目录"稳高压"）


def test_container_sections_have_no_guide():
    """容器节（自身无正文）不带 guide，避免 E3 误配锚点。"""
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        for sec in o["sections"]:
            if sec["class"] == "heading":
                assert "guide" not in sec
