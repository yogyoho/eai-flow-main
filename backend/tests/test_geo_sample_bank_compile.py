"""bank_compile / resolve_targets 矿种选基线单元测试（Phase 2）。"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "public" / "geological-report"
sys.path.insert(0, str(SKILL / "scripts"))

import build_output  # noqa: E402


def test_normalize_mineral_aliases():
    assert build_output.normalize_mineral("铜") == "copper"
    assert build_output.normalize_mineral("铜银金") == "copper"  # 连写取首命中（优先级序）
    assert build_output.normalize_mineral("岩金") == "gold"
    assert build_output.normalize_mineral("煤矿") == "coal"
    assert build_output.normalize_mineral("铅锌矿") == "lead_zinc"
    assert build_output.normalize_mineral("萤石") is None  # 词表外 → None
    assert build_output.normalize_mineral("") is None
    assert build_output.normalize_mineral(None) is None


def test_resolve_targets_mineral_dir_precedence(tmp_path, capsys):
    """样例库基线存在时优先于三级探测与 CANONICAL 兜底；不打非技能基准警告。"""
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    refs = SKILL / "references"
    mineral_file = refs / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True, exist_ok=True)
    baseline = {
        "coefficient": 0.6,
        "scale_floor": 0.25,
        "per_signal_penalty": 0.05,
        "missing_table_weight": 8,
        "absolute_floor": 0.4,
        "samples": [],
        "per_chapter": {f"ch{i}": {"median_eff": 900, "median_table_rows": 2, "median_paragraphs": 3} for i in range(1, 11)},
    }
    mineral_file.write_text(json.dumps(baseline, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金", "stage": "勘探"}), encoding="utf-8")
    try:
        targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
        assert targets["per_chapter"]["ch1"]["median_eff"] == 900
        assert "gold" in str(src)  # resolve_targets 第二元为 Path
        captured = capsys.readouterr()
        assert "非技能基准" not in captured.err  # 技能自有资产不打非基准警告
    finally:
        # 清理只删本测试写入的文件与因此变空的父目录——绝不 rmtree 整个子树（防误删并行 bank_compile 产物）
        mineral_file.unlink(missing_ok=True)
        for d in (mineral_file.parent, refs / "depth_targets"):
            try:
                d.rmdir()
            except OSError:
                pass


def test_resolve_targets_fallback_unchanged(tmp_path):
    """无矿种/无基线文件时走既有链（data_dir 不存在/词表外），兜底 CANONICAL——向后兼容。"""
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    data_dir = tmp_path / "data"  # 目录不存在
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None  # 兜底 CANONICAL（技能自带铜矿基线）
