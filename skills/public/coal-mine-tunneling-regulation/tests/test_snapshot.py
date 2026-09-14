"""snapshot 快照往返 + 篡改检测 + 正典名守卫。"""
import json
from pathlib import Path

import snapshot  # conftest.py 已注入 scripts/
from conftest import run_cli

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")


def _env(tmp_path):
    data = tmp_path / "data"
    state = tmp_path / "state"
    out = tmp_path / "outputs"
    for d in (data, state, out):
        d.mkdir()
    (data / "01_roadway.json").write_text("{}", encoding="utf-8")
    (state / "progress.json").write_text("{}", encoding="utf-8")
    return data, state, out


def test_save_show_verify_roundtrip(tmp_path):
    data, state, out = _env(tmp_path)
    snap = str(out / "project_snapshot.json")
    rc, out1 = run_cli(snapshot.main, ["save", "--task", "波1收口", "--stage", STAGE, "--data-dir", str(data),
                                       "--state-dir", str(state), "--output", snap])
    assert rc == 0 and "SNAPSHOT_READY" in out1
    rc2, out2 = run_cli(snapshot.main, ["show", "--input", snap, "--verify"])
    assert rc2 == 0 and "SNAPSHOT_VERIFIED" in out2


def test_tamper_detected_rc3(tmp_path):
    data, state, out = _env(tmp_path)
    snap = str(out / "project_snapshot.json")
    run_cli(snapshot.main, ["save", "--task", "t", "--stage", STAGE, "--data-dir", str(data),
                            "--state-dir", str(state), "--output", snap])
    (state / "progress.json").write_text('{"tampered": true}', encoding="utf-8")
    rc, out2 = run_cli(snapshot.main, ["show", "--input", snap, "--verify"])
    assert rc == 3 and "SNAPSHOT_TAMPERED" in out2  # rc=3=篡改→步骤0 停


def test_canonical_name_guard_bug2198(tmp_path):
    data, state, out = _env(tmp_path)
    rc, out1 = run_cli(snapshot.main, ["save", "--task", "t", "--stage", STAGE, "--data-dir", str(data),
                                       "--state-dir", str(state), "--output", str(out / "wrong_name.json")])
    assert rc == 1  # 快照必须恰名 project_snapshot.json（bug-2198）
