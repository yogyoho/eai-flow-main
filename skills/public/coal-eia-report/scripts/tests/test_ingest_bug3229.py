"""bug-3229 回归测试：预测链纪律（参数未定案，预测结果不得落盘）。

背景（线程 11680ec0 页面实测）：agent 在 subsidence_params.param_source 未定案、
formula_runner 零调用的状态下直写 14/15/16 预测结果族且 _meta.status=filled——
LLM 推演数字冒充权威。修复：
  1. ingest forms 写入预测结果族前强制校验 12 号 param_source 枚举 + 13 号 stages 非空；
  2. check 门把"结果先于参数"与"绕过唯一写者的直写文件"记为 blocking（GATE1_MISSING）。

用最小内联 stage（3 族）驱动 ingest.main()，stdlib-only，不依赖容器。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import ingest  # noqa: E402

STAGE = {
    "forms": {
        "subsidence_params": {
            "file": "12_subsidence_params.json",
            "required": True,
            "fields": [
                {"name": "q", "type": "number", "required": True},
                {"name": "param_source", "type": "enum:规范推荐值|实测回归|类比矿实测", "required": True},
            ],
        },
        "mining_stages": {
            "file": "13_mining_stages.json",
            "required": True,
            "fields": [{"name": "stages", "type": "array<object>", "required": True}],
        },
        "stage_prediction_results": {
            "file": "14_stage_prediction_results.json",
            "required": True,
            "fields": [{"name": "results", "type": "array<object>", "required": True}],
        },
    }
}

PREDICTION_VALUES = {"results": [{"stage_id": "一期", "W_max_mm": 1500}]}


@pytest.fixture()
def env(tmp_path: Path) -> tuple[Path, Path, Path]:
    stage_file = tmp_path / "stage.json"
    stage_file.write_text(json.dumps(STAGE, ensure_ascii=False), encoding="utf-8")
    data_dir = tmp_path / "data"
    return stage_file, data_dir, tmp_path


def _forms(stage: Path, data_dir: Path, family: str, values: dict) -> int:
    return ingest.main(
        ["forms", "--stage", str(stage), "--data-dir", str(data_dir), "--family", family, "--values", json.dumps(values, ensure_ascii=False)]
    )


def _check(stage: Path, data_dir: Path) -> int:
    return ingest.main(["check", "--stage", str(stage), "--data-dir", str(data_dir)])


def _confirm_prereqs(stage: Path, data_dir: Path) -> None:
    assert _forms(stage, data_dir, "subsidence_params", {"q": 0.75, "param_source": "规范推荐值"}) == ingest.EXIT_OK
    assert _forms(stage, data_dir, "mining_stages", {"stages": [{"stage_id": "一期", "panel": "101"}]}) == ingest.EXIT_OK


def test_prediction_write_refused_without_param_source(env):
    stage, data_dir, _ = env
    rc = _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES)
    assert rc == ingest.EXIT_ERROR
    assert not (data_dir / "14_stage_prediction_results.json").exists()


def test_prediction_write_refused_on_invalid_enum(env):
    stage, data_dir, _ = env
    assert _forms(stage, data_dir, "subsidence_params", {"q": 0.75, "param_source": "拍脑袋"}) == ingest.EXIT_OK or True
    # 枚举外取值在 schema 校验层就会被拒（validate_values）——直接手写模拟绕过后，预测族仍被前置守卫拦住
    dd = data_dir / "12_subsidence_params.json"
    dd.write_text(json.dumps({"_meta": {"status": "filled"}, "q": 0.75, "param_source": "拍脑袋"}, ensure_ascii=False), encoding="utf-8")
    ingest.register_file(data_dir, "12_subsidence_params.json", "subsidence_params", True, "json")
    rc = _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES)
    assert rc == ingest.EXIT_ERROR
    assert not (data_dir / "14_stage_prediction_results.json").exists()


def test_prediction_write_allowed_after_params_confirmed(env):
    stage, data_dir, _ = env
    _confirm_prereqs(stage, data_dir)
    rc = _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES)
    assert rc == ingest.EXIT_OK
    doc = json.loads((data_dir / "14_stage_prediction_results.json").read_text(encoding="utf-8"))
    assert doc["_meta"]["status"] == "filled"


def test_check_blocks_unregistered_direct_write_and_premature_prediction(env):
    """复现 bug-3229 现场：直写 14 号（status=filled、无 param_source）→ 门1 阻断。"""
    stage, data_dir, _ = env
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "14_stage_prediction_results.json").write_text(
        json.dumps({"_meta": {"status": "filled"}, "results": PREDICTION_VALUES["results"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    rc = _check(stage, data_dir)
    assert rc == ingest.EXIT_MANUAL
    # 直接复用 ingest 内部函数核对阻断项文本
    errs = ingest.prediction_prereq_errors(json.loads(stage.read_text(encoding="utf-8")), data_dir, "stage_prediction_results")
    assert errs and "bug-3229" in errs[0]


def test_check_passes_clean_registered_pipeline(env, capsys):
    stage, data_dir, _ = env
    _confirm_prereqs(stage, data_dir)
    assert _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES) == ingest.EXIT_OK
    rc = _check(stage, data_dir)
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_OK
    assert "GATE1_COMPLETE" in out


def test_check_blocks_registered_file_modified_externally(env, capsys):
    """登记名字后被直写覆盖内容 → manifest sha256 不符 → 门1 阻断（bug-3229 残余通道）。"""
    stage, data_dir, _ = env
    _confirm_prereqs(stage, data_dir)
    assert _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES) == ingest.EXIT_OK
    # 绕过 ingest 直改已登记文件内容（保持 status=filled 不变，仅改数字——模拟 LLM 编数覆盖）
    p = data_dir / "12_subsidence_params.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["q"] = 0.99
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    rc = _check(stage, data_dir)
    out = capsys.readouterr().out
    assert rc == ingest.EXIT_MANUAL
    assert "指纹不符 12_subsidence_params.json" in out


def test_check_blocks_prediction_filled_before_params(env, capsys):
    """经 ingest 正常写入预测族被拒后，改为：先写 params 但缺 param_source 字段值——
    schema 必填校验会拦；此处验证另一形态：mining_stages 空时 check 阻断已填充的预测族。"""
    stage, data_dir, _ = env
    assert _forms(stage, data_dir, "subsidence_params", {"q": 0.8, "param_source": "类比矿实测"}) == ingest.EXIT_OK
    # mining_stages 未写（空）——直接经 ingest 写预测族应被前置守卫拒收
    assert _forms(stage, data_dir, "stage_prediction_results", PREDICTION_VALUES) == ingest.EXIT_ERROR
    # 模拟"守卫上线前已落盘"的存量脏数据：直写后 check 必须阻断
    (data_dir / "14_stage_prediction_results.json").write_text(
        json.dumps({"_meta": {"status": "filled"}, "results": PREDICTION_VALUES["results"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    ingest.register_file(data_dir, "14_stage_prediction_results.json", "stage_prediction_results", True, "json")
    rc = _check(stage, data_dir)
    assert rc == ingest.EXIT_MANUAL
    out = capsys.readouterr().out
    assert "mining_stages.stages 为空" in out
