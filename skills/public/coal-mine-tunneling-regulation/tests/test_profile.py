"""profile.py 矿井档案契约测试（D3 文件契约）。"""
import importlib.util as u
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def _load(name):
    spec = u.spec_from_file_location(f"tun_{name}", ROOT / "scripts" / f"{name}.py")
    m = u.module_from_spec(spec); spec.loader.exec_module(m); return m

profile = _load("profile"); ingest = _load("ingest")
from conftest import run_cli  # T6 质量评审 M2：套件级 stdout 捕获辅助（conftest 已注入 sys.path）
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
ARCHIVE = DIGEST["form_seed"]["profile"] | {"audit_units": ["地测科", "通风科"]}

def _write(tmp_path, obj, name="profile.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)

def test_validate_ok(tmp_path):
    rc, out = run_cli(profile.main, ["validate", "--input", _write(tmp_path, ARCHIVE), "--stage", STAGE])
    assert rc == 0 and "PROFILE_OK" in out
    assert "22 fields" in out  # I1 回归锚：档案=完整 22 字段（含 J11 refuge 七字段）

def test_validate_rejects_bad_enum(tmp_path):
    bad = ARCHIVE | {"gas_grade": "超高瓦斯"}
    rc, out = run_cli(profile.main, ["validate", "--input", _write(tmp_path, bad), "--stage", STAGE])
    assert rc == 1 and "gas_grade" in out

def test_rejects_non_object_archive(tmp_path):
    # I2 形状守卫：档案必须是 JSON 对象——数组/标量直接 PROFILE_ERROR rc=1
    p = tmp_path / "bad_shape.json"
    p.write_text(json.dumps([1, 2, 3], ensure_ascii=False), encoding="utf-8")
    rc, out = run_cli(profile.main, ["validate", "--input", str(p), "--stage", STAGE])
    assert rc == 1 and "档案必须是 JSON 对象" in out

def test_load_writes_data_family(tmp_path):
    arc = _write(tmp_path, ARCHIVE)
    data = str(tmp_path / "data")
    rc, out = run_cli(profile.main, ["load", "--input", arc, "--stage", STAGE, "--data-dir", data])
    assert rc == 0 and "PROFILE_LOADED" in out
    doc = json.load(open(Path(data) / "00_profile.json", encoding="utf-8"))
    assert doc["mine_name"] == "某矿" and doc["_meta"]["family"] == "profile"
    # 门1 因档案族在场而不再报 profile 缺失（其余 11 族仍缺 → 门1 拦 rc=2）
    rc2, out2 = run_cli(ingest.main, ["check", "--stage", STAGE, "--data-dir", data])
    assert rc2 == 2
    tail = out2.split("GATE1_MISSING")[-1]
    assert "profile" not in tail

def test_summary_mentions_archive_date(tmp_path):
    rc, out = run_cli(profile.main, ["summary", "--input", _write(tmp_path, ARCHIVE)])
    assert rc == 0 and ARCHIVE["archive_date"] in out and "矿井条件有变先更新档案" in out
    assert all(f"[{t}]" in out for t, _ in profile.GROUPS)  # I3：六展示分组逐组在场
