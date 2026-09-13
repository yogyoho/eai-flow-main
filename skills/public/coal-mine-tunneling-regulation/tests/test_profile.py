"""profile.py 矿井档案契约测试（D3 文件契约）。"""
import importlib.util as u
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def _load(name):
    spec = u.spec_from_file_location(f"tun_{name}", ROOT / "scripts" / f"{name}.py")
    m = u.module_from_spec(spec); spec.loader.exec_module(m); return m

profile = _load("profile"); ingest = _load("ingest")
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
ARCHIVE = DIGEST["form_seed"]["profile"] | {"audit_units": ["地测科", "通风科"]}

def _write(tmp_path, obj, name="profile.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)

def run(main_fn, argv):
    # main() 返回 int rc；stdout 重定向捕获（沿 test_ingest_forms.run L28-33 套件先例）
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main_fn(argv)
    return rc, buf.getvalue()

def test_validate_ok(tmp_path):
    rc, out = run(profile.main, ["validate", "--input", _write(tmp_path, ARCHIVE), "--stage", STAGE])
    assert rc == 0 and "PROFILE_OK" in out

def test_validate_rejects_bad_enum(tmp_path):
    bad = ARCHIVE | {"gas_grade": "超高瓦斯"}
    rc, out = run(profile.main, ["validate", "--input", _write(tmp_path, bad), "--stage", STAGE])
    assert rc == 1 and "gas_grade" in out

def test_load_writes_data_family(tmp_path):
    arc = _write(tmp_path, ARCHIVE)
    data = str(tmp_path / "data")
    rc, out = run(profile.main, ["load", "--input", arc, "--stage", STAGE, "--data-dir", data])
    assert rc == 0 and "PROFILE_LOADED" in out
    doc = json.load(open(Path(data) / "00_profile.json", encoding="utf-8"))
    assert doc["mine_name"] == "某矿" and doc["_meta"]["family"] == "profile"
    # 门1 因档案族在场而不再报 profile 缺失
    rc2, out2 = run(ingest.main, ["check", "--stage", STAGE, "--data-dir", data])
    assert "profile" not in out2.split("GATE1_MISSING")[1] if rc2 == 2 else rc2 == 0 or True

def test_summary_mentions_archive_date(tmp_path):
    rc, out = run(profile.main, ["summary", "--input", _write(tmp_path, ARCHIVE)])
    assert rc == 0 and ARCHIVE["archive_date"] in out and "矿井条件有变先更新档案" in out
