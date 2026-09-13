"""ingest 门1/表单写入契约测试（掘进 12 族 + profile 档案族）。
运行: cd skills/public/coal-mine-tunneling-regulation && PYTHONUTF8=1 python -m pytest tests/ -v"""
import json
from pathlib import Path

import ingest  # conftest.py 已注入 scripts/ 到 sys.path

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))

def env(tmp_path):
    return STAGE, str(tmp_path / "data")

def run(argv):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ingest.main(argv)
    return rc, buf.getvalue()

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

def test_gate1_complete_after_seed_fill(tmp_path):
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
