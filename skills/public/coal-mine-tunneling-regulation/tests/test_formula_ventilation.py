"""通风域冻结计算数值回归（样例实证值锚定）。"""
import json
from pathlib import Path

import formula_runner  # conftest.py 已注入 scripts/
import ingest
from conftest import run_cli  # T7：计划稿 _io 本地助手改用套件级 run_cli（T6 质量评审 M2 先例）

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
SEED = DIGEST["form_seed"]

def _fill(tmp_path):
    data = str(tmp_path / "data")
    fills = {"roadway": SEED["roadway"] | {"roadway_use": "运输", "working_face_no": "W1", "reg_no": "T/01",
                                            "azimuth": "N", "start_end_date": "x", "adjacent_relation": "实体煤",
                                            "net_height_mm": 3600, "drive_height_mm": 3600},
             "geology": SEED["geology"] | {"ground_elevation": "+1000", "face_elevation": "+500",
                                            "strata": [], "structure_desc": "无", "hydro_verdict": "中等"},
             "ventilation": SEED["ventilation"] | {"duct_leak_rate_per100m": 10, "fan_model": "FBD-6.0/2×15"}}
    for fam, values in fills.items():
        rc, _ = run_cli(ingest.main, ["forms", "--stage", STAGE, "--data-dir", data, "--family", fam,
                                      "--values", json.dumps(values, ensure_ascii=False)])
        assert rc == 0
    return data

def test_execute_freezes_ventilation_slots(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    rc, out = run_cli(formula_runner.main, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    assert rc == 3, out  # 待核实 anomaly 恒在场（F2 线性近似/F4 风阻系数）
    assert "STATE_READY" in out
    st = json.load(open(state, encoding="utf-8"))
    v = st["values"]
    assert v["Q1.need_by_gas"]["value"] == 472.60   # 100×3.4×1.39
    assert v["Q2.need_by_persons"]["value"] == 48.0
    assert v["Q0.need_final"]["value"] == 472.60 and v["Q0.need_final"]["basis"] == "Q1"
    assert v["Q4.v_min_q"]["value"] == 270.0 and v["Q4.v_max_q"]["value"] == 8640.0
    assert v["F1.duct_gap_m"]["value"] == 21.21     # 5×√18
    assert v["F3.duct_count"]["value"] == 91        # ceil(902.236/10)
    assert "F4.drag_head" in v and v["F4.drag_head"]["source"] == "formula:F4"
    assert all(s["source"].startswith("formula:") for s in v.values())
    assert any("F4" in a and "待人工核实" in a for a in st["anomalies"])

def test_check_anchor_regression(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    run_cli(formula_runner.main, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    anchors = json.dumps({"Q1.need_by_gas": 472.60, "F1.duct_gap_m": 21.21}, ensure_ascii=False)
    rc, out = run_cli(formula_runner.main, ["check", "--stage", STAGE, "--data-dir", data, "--state", state,
                                            "--anchors", anchors, "--output", str(tmp_path / "check.json")])
    assert rc == 0 and "CHECK_READY" in out  # CHECK_READY 仅在 --output 时打印（对抗评审 P1）
    anchors_bad = json.dumps({"Q1.need_by_gas": 999.0}, ensure_ascii=False)
    rc2, out2 = run_cli(formula_runner.main, ["check", "--stage", STAGE, "--data-dir", data, "--state", state,
                                              "--anchors", anchors_bad, "--output", str(tmp_path / "check2.json")])
    assert rc2 == 1  # anchor 不一致=fail

def test_impacted_update_order_law(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    run_cli(formula_runner.main, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    manifest = str(tmp_path / "chapter_manifest.json")
    manifest_obj = {"version": 2, "always_dependent": ["compliance_appendix"],
                    "chapters": [{"id": f"ch{i}", "title": "", "formula_ids": ["Q1"] if i in (2, 5) else [],
                                   "form_families": ["geology"] if i == 2 else [], "type": "narrative"} for i in range(1, 10)]}
    Path(manifest).write_text(json.dumps(manifest_obj, ensure_ascii=False), encoding="utf-8")
    # --field 语法：JSON 字段 = '<文件名数字前缀>.<字段名>'（fam_by_prefix 匹配 file.split('_',1)[0]）
    rc, out = run_cli(formula_runner.main, ["impacted", "--stage", STAGE, "--data-dir", data, "--state", state,
                                            "--field", "02.gas_emission_daily", "--value", "4.0",
                                            "--manifest", manifest, "--output", str(tmp_path / "impacted.json")])
    assert rc == 0, out  # 硬断言（对抗评审 P1：不可证伪的 if imp: 守卫已删）
    imp = json.load(open(tmp_path / "impacted.json", encoding="utf-8"))
    assert "Q1.need_by_gas" in imp["changes"]
    assert "ch5" in imp["affected_chapters"]

def test_missing_air_supply_distance_records_anomaly(tmp_path):
    # 质量评审 I1：F2/F4 缺参不得静默跳过——「缺输入必记 anomaly」纪律（rc=0 唯一可达路径堵漏）
    data = _fill(tmp_path)
    vent_path = Path(data) / "05_ventilation.json"
    vent = json.loads(vent_path.read_text(encoding="utf-8"))
    vent.pop("air_supply_distance_m", None)
    vent_path.write_text(json.dumps(vent, ensure_ascii=False), encoding="utf-8")
    state = str(tmp_path / "formula_state.json")
    rc, out = run_cli(formula_runner.main, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    assert rc == 3, out
    st = json.load(open(state, encoding="utf-8"))
    joined = " ".join(st["anomalies"])
    assert "F2 缺 duct_leak_rate_per100m/air_supply_distance_m" in joined
    assert "F4 缺 air_supply_distance_m" in joined
    assert "F2.fan_need" not in st["values"] and "F4.drag_head" not in st["values"]

def test_nonpositive_section_skips_block(tmp_path):
    # 质量评审 I2：断面非正数=源数据错误——Q4/F1/F2/F4 整块跳过，禁冻结零值槽位
    data = _fill(tmp_path)
    road_path = Path(data) / "01_roadway.json"
    road = json.loads(road_path.read_text(encoding="utf-8"))
    road["drive_section_m2"] = 0
    road_path.write_text(json.dumps(road, ensure_ascii=False), encoding="utf-8")
    state = str(tmp_path / "formula_state.json")
    rc, out = run_cli(formula_runner.main, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    assert rc == 3, out
    st = json.load(open(state, encoding="utf-8"))
    assert any("非正数" in a and "检查源数据" in a for a in st["anomalies"])
    v = st["values"]
    assert not any(k.startswith("Q4.") for k in v)
    assert "F1.duct_gap_m" not in v and "F2.fan_need" not in v and "F4.drag_head" not in v
    assert v["Q1.need_by_gas"]["value"] == 472.60 and v["Q0.need_final"]["basis"] == "Q1"  # 不依赖断面的链照常
    assert v["F3.duct_count"]["value"] == 91
