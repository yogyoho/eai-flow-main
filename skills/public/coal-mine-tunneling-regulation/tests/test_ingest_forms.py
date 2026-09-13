"""ingest 门1/表单写入契约测试（掘进 12 族 + profile 档案族）。
运行: cd skills/public/coal-mine-tunneling-regulation && PYTHONUTF8=1 python -m pytest tests/ -v"""
import json
from pathlib import Path

import ingest  # conftest.py 已注入 scripts/ 到 sys.path
from conftest import run_cli  # T6 质量评审 M2：套件级 stdout 捕获辅助

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
_STAGE_DOC = json.load(open(STAGE, encoding="utf-8"))

def _schema_shaped(fam: str, values: dict) -> dict:
    """form_seed 是脱敏摘要：array 族字段被摘要成描述字符串——按 stage schema
    形状回包成单元素数组（完备性门只看非空数组，不校验内键；文本原样保留）。"""
    fields = {f["name"]: f for f in _STAGE_DOC["forms"][fam]["fields"]}
    out = {}
    for k, v in values.items():
        fd = fields.get(k)
        if fd and str(fd.get("type", "")).startswith("array") and not isinstance(v, list):
            v = [{"描述": v} if isinstance(v, str) else v]
        out[k] = v
    return out

def env(tmp_path):
    return STAGE, str(tmp_path / "data")

def run(argv):
    return run_cli(ingest.main, argv)

def test_forms_generates_all_12_families(tmp_path):
    stage, data = env(tmp_path)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data])
    assert rc == 0 and "FORMS_READY" in out
    files = [p for p in Path(data).iterdir() if p.suffix in (".json", ".csv") and p.name != "state_manifest.json"]
    assert len(files) == 12, [p.name for p in files]  # 7 JSON + 5 CSV（对抗评审 P1：排除 state_manifest.json）

def test_gate1_missing_without_fill(tmp_path):
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2 and "GATE1_MISSING" in out and "profile" in out  # 档案族缺=门1拦（J4）

def test_gate1_partial_fill_still_blocked(tmp_path):
    # 评审更名（I3①）：本用例测的是「部分填充仍被门1拦」——按族粒度，非完备
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    seed = DIGEST["form_seed"]
    minimal = {
        "profile": {k: seed["profile"].get(k, "占位") for k in
                     ["mine_name", "group_name", "reg_no_format", "gas_grade", "hydro_type", "spontaneous_tendency",
                      "coal_dust_explosion", "development_mode", "ventilation_mode", "supply_voltage",
                      "monitoring_system", "team_name", "shift_system", "archive_date"]} | {"audit_units": ["地测科"]},
        "roadway": {**seed["roadway"], "roadway_use": "运输", "working_face_no": "W1", "reg_no": "掘ZJED-2026T/01",
                     "azimuth": "N", "start_end_date": "2026-10~2027-03", "adjacent_relation": "实体煤",
                     "net_height_mm": 3600, "drive_height_mm": 3600},
    }
    for fam, values in minimal.items():
        rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", fam, "--values", json.dumps(values, ensure_ascii=False)])
        assert rc == 0, out
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2  # 只填 2 族，其余族仍缺——门1按族粒度

def test_gate1_complete_all_families_filled(tmp_path):
    # 评审新增（I3②）：正路径——7 个 JSON fields 族用 form_seed 填满 + 5 个 CSV 族各 1 行 → 门1放行
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    for fam, values in DIGEST["form_seed"].items():
        rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", fam,
                       "--values", json.dumps(_schema_shaped(fam, values), ensure_ascii=False)])
        assert rc == 0, out
    csv_one_row = {
        "labor_crew": [["掘砌工", "10", "10", "10", "30", ""]],
        "econ_indicators": [["施工长度", "m", "902.236"]],
        "risk_register": [["1", "冒顶片帮", "过构造带", "重大", "钻探查明", "总工"]],
        "dust_facilities": [["1", "喷雾", "迎头", "20m", "2", ""]],
        "sensor_cutoffs": [["甲烷", "2", "迎头", "1.0", "1.5", "1.0", "掘进巷道", "顶板", ""]],
    }
    for fam, rows in csv_one_row.items():
        rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", fam,
                       "--rows", json.dumps(rows, ensure_ascii=False)])
        assert rc == 0, out
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 0 and "GATE1_COMPLETE" in out, out

def test_qc_gas_string_value_no_crash(tmp_path):
    # I1 回归钉：validate_values 只校验不矫正（coerced 值被丢弃），字符串 "3.4" 原样落盘——
    # check 的数值比较禁裸 TypeError，必须走 _num 收敛后正常出 QUALITY/MISSING
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "geology",
                   "--values", json.dumps({"gas_emission_daily": "3.4"}, ensure_ascii=False)])
    assert rc == 0, out
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2 and "QC_GAS" in out  # 不崩 + 月平均缺失 warn 照发（3.4>0 经 _num 收敛）

def test_qc_bolt_schema_key_spelling(tmp_path):
    # I2 回归钉：按 schema 原拼写「部位(顶板/帮部)」忠实填数，QC_BOLT 不得被键名拼写静默绕过
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "support",
                   "--values", json.dumps({"bolt_specs": [{"部位(顶板/帮部)": "顶板", "长度_m": 1.5}]}, ensure_ascii=False)])
    assert rc == 0, out
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2 and "QC_BOLT" in out

def test_values_rejects_typo_fields(tmp_path):
    stage, data = env(tmp_path)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "roadway",
                   "--values", json.dumps({"roadway_name": "X", "roadway_nmae_typo": "Y"}, ensure_ascii=False)])
    assert rc == 1  # validate_values 防 typo（L198-211 语义）

def test_csv_rows_write(tmp_path):
    stage, data = env(tmp_path)
    rows = json.dumps([["1", "冒顶片帮", "过构造带", "重大", "钻探查明", "总工"]], ensure_ascii=False)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "risk_register", "--rows", rows])
    assert rc == 0 and "FORM_WRITTEN" in out
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "risk_register", "--rows", rows])
    assert rc == 0 and "FORM_NOOP" in out  # 指纹 no-op
