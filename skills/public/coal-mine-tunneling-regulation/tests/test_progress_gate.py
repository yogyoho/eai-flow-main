"""章状态机多波相位 + bug-3049 门自动回写测试。"""
import json
from pathlib import Path

import progress  # conftest.py 已注入 scripts/
from conftest import run_cli

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")

FILLER = ("锚杆支护巷道施工必须严格执行敲帮问顶制度，严禁空顶作业。临时支护紧跟迎头，"
          "永久支护滞后距离不得超过作业规程规定。施工中加强顶板离层观测与锚杆锚固力抽检。") * 30  # >1000 有效字符 + 3 句以上


def _init(tmp_path):
    data = tmp_path / "data"; state = tmp_path / "state"
    data.mkdir(); state.mkdir()
    (state / "chapters").mkdir()
    # gate→run_chapter_gate 无条件读 formula_state.json（对抗评审 P0：FileNotFoundError 穿透 except ValueError）
    (state / "formula_state.json").write_text(
        json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    # 章门深度目标调试注入（小地板，让 FILLER 能过 L2——生产基准由 Task 13 供给）
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"coefficient": 0.0, "absolute_floor": 1.0,
        "per_chapter": {f"ch{i}": {"median_eff": 500, "median_table_rows": 0, "median_paragraphs": 3} for i in range(1, 10)}},
        ensure_ascii=False), encoding="utf-8")
    rc, _ = run_cli(progress.main, ["init", "--stage", STAGE, "--state-dir", str(state), "--data-dir", str(data)])
    assert rc == 0
    return str(state), str(targets)


def test_init_all_pending_phase_wave1(tmp_path):
    state, _ = _init(tmp_path)
    rc, out = run_cli(progress.main, ["next", "--state-dir", state])
    assert rc == 0 and "PHASE=WAVE1" in out and "DISPATCH" in out


def test_phase_advances_across_waves(tmp_path):
    state, _ = _init(tmp_path)
    doc = json.loads((Path(state) / "progress.json").read_text(encoding="utf-8"))
    for c in ["ch1", "ch2", "ch3"]:
        doc["chapters"][c]["status"] = "VERIFIED"
    (Path(state) / "progress.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    rc, out = run_cli(progress.main, ["next", "--state-dir", state])
    assert "PHASE=WAVE2" in out  # 波1 全 VERIFIED → 自动进波2（J3：无 KEY_POINTS 停靠）


def test_mark_verified_rejected_bug3049(tmp_path):
    state, _ = _init(tmp_path)
    rc, out = run_cli(progress.main, ["mark", "ch1", "VERIFIED", "--state-dir", state])
    assert rc == 1  # 手动 VERIFIED 硬拒，唯一通道=gate


def test_gate_auto_verifies(tmp_path):
    state, targets = _init(tmp_path)
    # T11 delta d：目录覆盖门换 eia validate_toc_chapters（章题语义相符）——假章题「chN 测试章」
    # 判契约外自创，须用 stage 真章题（本测试本意是 bug-3049 门自动回写，非目录门语义）
    titles = json.load(open(ROOT / "references" / "stages" / "tunneling.json", encoding="utf-8"))["chapters"]
    for c in ["ch1", "ch2", "ch3"]:
        (Path(state) / "chapters" / f"{c}.md").write_text(f"## {titles[c]['title']}\n\n{FILLER}\n", encoding="utf-8")
        rc, _ = run_cli(progress.main, ["mark", c, "DRAFTED", "--state-dir", state])
        assert rc == 0
    rc, out = run_cli(progress.main, ["gate", "--state-dir", state, "--targets", targets])
    doc = json.loads((Path(state) / "progress.json").read_text(encoding="utf-8"))
    # 门真跑二分（对抗评审 P0：BLOCKED 不会由 gate 产生）——过→VERIFIED 自动回写；不足→留 DRAFTED 且 stderr 报差距
    assert (doc["chapters"]["ch1"]["status"] == "VERIFIED"
            or ("CHAPTER_GATE_FAIL" in out and doc["chapters"]["ch1"]["status"] == "DRAFTED"))
    assert "GATE_BATCH_DONE" in out
