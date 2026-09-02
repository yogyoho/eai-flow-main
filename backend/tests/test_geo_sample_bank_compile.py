"""bank_compile / resolve_targets 矿种选基线单元测试（Phase 2）。"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "public" / "geological-report"
sys.path.insert(0, str(SKILL / "scripts"))

import build_output  # noqa: E402

# 样例库基线形状（照 references/depth_targets.json 契约：load_targets 只硬性要求 per_chapter dict）
_BASELINE = {
    "coefficient": 0.6,
    "scale_floor": 0.25,
    "per_signal_penalty": 0.05,
    "missing_table_weight": 8,
    "absolute_floor": 0.4,
    "samples": [],
    "per_chapter": {f"ch{i}": {"median_eff": 900, "median_table_rows": 2, "median_paragraphs": 3} for i in range(1, 11)},
}


def _make_stage(tmp_path):
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    return stage


def test_normalize_mineral_aliases():
    assert build_output.normalize_mineral("铜") == "copper"
    assert build_output.normalize_mineral("铜银金") == "copper"  # 最早位置胜出：铜(0) < 金(2)
    assert build_output.normalize_mineral("岩金") == "gold"
    assert build_output.normalize_mineral("煤矿") == "coal"
    assert build_output.normalize_mineral("铅锌矿") == "lead_zinc"
    assert build_output.normalize_mineral("铅锌金银") == "lead_zinc"  # 最早位置胜出：铅锌(0) < 金(3)
    assert build_output.normalize_mineral("金银") == "gold"
    assert build_output.normalize_mineral("金矿") == "gold"
    # 负向守卫：「非金属」排除；「金」后接「属」的复合词（金属量/贵金属/多金属）不是矿种名
    assert build_output.normalize_mineral("非金属矿") is None
    assert build_output.normalize_mineral("多金属") is None
    assert build_output.normalize_mineral("贵金属") is None
    assert build_output.normalize_mineral("金属量") is None
    assert build_output.normalize_mineral("萤石") is None  # 词表外
    assert build_output.normalize_mineral("") is None
    assert build_output.normalize_mineral(None) is None


def test_resolve_targets_mineral_dir_precedence(tmp_path, monkeypatch, capsys):
    """样例库基线存在时优先于三级探测与 CANONICAL 兜底；不打非技能基准警告。"""
    stage = _make_stage(tmp_path)
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", tmp_path / "depth_targets.json")  # 探测路径自动重定向到 tmp
    mineral_file = tmp_path / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True)
    mineral_file.write_text(json.dumps(_BASELINE, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金", "stage": "勘探"}), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets["per_chapter"]["ch1"]["median_eff"] == 900
    assert "gold" in str(src)  # resolve_targets 第二元为 Path
    captured = capsys.readouterr()
    assert "非技能基准" not in captured.err  # 技能自有资产不打非基准警告
    assert "矿种基线缺失" not in captured.err


def test_resolve_targets_mineral_beats_stage_adjacent(tmp_path, monkeypatch, capsys):
    """stage 旁 depth_targets.json 可伪造（bug-3058）——gated 的样例库基线优先于 stage 旁扫描。"""
    stage = _make_stage(tmp_path)
    (stage.parent / "depth_targets.json").write_text(json.dumps({"per_chapter": {"ch1": {"median_eff": 99999}}}), encoding="utf-8")
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", tmp_path / "depth_targets.json")
    mineral_file = tmp_path / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True)
    mineral_file.write_text(json.dumps(_BASELINE), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金"}), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets["per_chapter"]["ch1"]["median_eff"] == 900  # mineral 基线胜出，非 stage 旁伪造的 99999
    assert "gold" in str(src)
    captured = capsys.readouterr()
    assert "非技能基准" not in captured.err


def test_resolve_targets_missing_baseline_falls_back(tmp_path, monkeypatch, capsys):
    """矿种命中但基线文件缺失 → stderr 一行提示 + 回退既有探测链/兜底（行为不变）。"""
    stage = _make_stage(tmp_path)
    fake_canonical = tmp_path / "canonical" / "depth_targets.json"  # 可存在的兜底，隔离真实技能目录
    fake_canonical.parent.mkdir(parents=True)
    fake_canonical.write_text(json.dumps({"per_chapter": {"ch1": {"median_eff": 7487}}}), encoding="utf-8")
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", fake_canonical)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金"}), encoding="utf-8")
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None  # 兜底（重定向后的 canonical）
    captured = capsys.readouterr()
    assert "矿种基线缺失" in captured.err
    assert "gold" in captured.err


def test_resolve_targets_fallback_unchanged(tmp_path):
    """无矿种/无基线文件时走既有链（data_dir 不存在/词表外），兜底 CANONICAL——向后兼容。"""
    stage = _make_stage(tmp_path)
    data_dir = tmp_path / "data"  # 目录不存在
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None  # 兜底 CANONICAL（技能自带铜矿基线）


def test_project_mineral_non_dict_json(tmp_path):
    """00_project.json 为非对象 JSON（如 [1,2]）→ .get 抛 AttributeError → 归一化 None（不炸探测链）。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text("[1,2]", encoding="utf-8")
    assert build_output._project_mineral(data_dir) is None
