import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

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


def test_container_sections_have_heading_level():
    """X.Y-depth 容器节必须有 heading_level=3，否则渲染成顶级章节。"""
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        for sec in o["sections"]:
            fire = sec["fire"]
            if sec["class"] == "heading" and re.match(r"^\d+\.\d+($|\s)", fire):
                assert sec.get("heading_level") == 3, f"{stage}: {fire} 容器节缺 heading_level=3"
            elif sec["class"] == "heading" and re.match(r"^\d+\s", fire):
                assert "heading_level" not in sec, f"{stage}: 顶级章节 {fire} 不应设 heading_level"


def test_verbatim_sections_have_guide():
    """每个 verbatim 节必须有非空 guide（E3 搜索锚点提示，缺了会空章节）。"""
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        for sec in o["sections"]:
            if sec["class"] == "verbatim":
                assert sec.get("guide"), f"{stage}: verbatim 节 {sec['fire']} 缺 guide"


import detect_stage


def test_detect_from_paras_initial():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "初步设计"}, {"i": 2, "text": "消防设计专篇"}]}
    assert detect_stage.detect_from_struct(struct) == "初步设计"


def test_detect_from_paras_basic():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "基础设计"}, {"i": 2, "text": "第一册 说明书"}]}
    assert detect_stage.detect_from_struct(struct) == "基础设计"


def test_detect_default_when_absent():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "消防设计专篇"}], "headings": []}
    assert detect_stage.detect_from_struct(struct) == detect_stage.DEFAULT_STAGE


def test_detect_both_markers_treats_ambiguous_as_default():
    # 封面同页含两词时，优先精确段落命中；命中歧义 → 默认
    struct = {"paras": [{"i": 0, "text": "初步设计及基础设计说明"}]}
    assert detect_stage.detect_from_struct(struct) == detect_stage.DEFAULT_STAGE


def test_detect_from_headings_fallback():
    # 标题兜底：paras 无标记，标记只在 headings 里
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "第一册 说明书"}], "headings": [{"level": 1, "text": "初步设计", "para_i": 1}]}
    assert detect_stage.detect_from_struct(struct) == "初步设计"


def test_detect_para_precedes_heading():
    # para 优先于 heading：paras 说基础设计、headings 说初步设计 → 取 paras
    struct = {
        "paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "基础设计"}, {"i": 2, "text": "第一册 说明书"}],
        "headings": [{"level": 1, "text": "初步设计", "para_i": 2}],
    }
    assert detect_stage.detect_from_struct(struct) == "基础设计"


def _mini_outline():
    return {
        "report_title": "{项目名} 消防设计专篇",
        "sections": [
            {"fire": "1 设计依据", "class": "heading"},
            {"fire": "1.1 设计依据", "class": "verbatim", "heading_level": 3},
            {"fire": "1.2 标准", "class": "template", "heading_level": 3, "template": "gb_standards"},
            {"fire": "7 投资概算", "class": "compute", "note": "无数据"},
        ],
        "templates": {"gb_standards": "GB50016-2014"},
    }


def _mini_struct():
    return {"paras": [{"i": 0, "text": "依据A"}, {"i": 1, "text": "依据B"}, {"i": 2, "text": "无关段"}], "tables": {}}


def _mini_mapping():
    return {"sources": [None, [{"kind": "range", "paras": [0, 1]}], None, None]}


import extract


def test_two_layer_extract_merges_outline_and_sources():
    out, _ = extract.extract(_mini_struct(), _mini_outline(), _mini_mapping())
    assert "1 设计依据" in out
    assert "1.1 设计依据" in out
    assert "依据A" in out and "依据B" in out
    assert "无关段" not in out          # 未锚定的段落不得抄入
    assert "GB50016-2014" in out        # template 从大纲取
    assert "[需计算] 无数据" in out


def test_two_layer_title_uses_project_name():
    report = extract.build_report(_mini_struct(), _mini_outline(), _mini_mapping(), project_name="吉林石化新装置")
    assert report.startswith("# 吉林石化新装置 消防设计专篇")
    assert "XX" not in report.splitlines()[0]


def test_two_layer_missing_sources_mark_not_found():
    mapping = {"sources": [None, None, None, None]}
    out, _ = extract.extract(_mini_struct(), _mini_outline(), mapping)
    assert "[⚠未找到段落" in out
