"""snapshot.py CLI 测试（反馈7 跨轮承接 + 版本历史）。

锁住 project_snapshot.json 的读-改-写语义：首次 save=version 1、后续 save
version++ 并保留 created_at、changelog 追加、value_diffs/affected 捕获、
show 锚点摘要、损坏 JSON 降级全新。防止后续误改成"每次 save 覆盖丢历史"
或"不追加 changelog"。

bug-1171 根因：agent 从不写 project_snapshot.json → 第 2 轮改参无 last_task
锚点 → 漂移回"重新生成整篇"。snapshot.py + 多轮承接铁律为该 bug 的修复。
"""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _REPO_ROOT / "skills" / "public" / "water-drainage-report"
_SCRIPT = _SKILL / "scripts" / "snapshot.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True)


def _make_params(p: Path) -> None:
    p.write_text(json.dumps({"Q": 20000, "delta_t": 10, "N": 5}), encoding="utf-8")


class TestSnapshotSaveIncrement:
    def test_first_save_is_version_1(self, tmp_path):
        params = tmp_path / "params.json"
        _make_params(params)
        out = tmp_path / "project_snapshot.json"
        r = _run(
            [
                "save",
                "--task",
                "首次生成 Q=20000",
                "--params",
                str(params),
                "--report",
                "/mnt/user-data/outputs/r.md",
                "--standards",
                '["GB/T 50746-2012"]',
                "--output",
                str(out),
            ]
        )
        assert r.returncode == 0, r.stderr
        assert "SNAPSHOT_READY: version=1" in r.stdout
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["version"] == 1
        assert snap["last_task"] == "首次生成 Q=20000"
        assert snap["params"] == {"Q": 20000, "delta_t": 10, "N": 5}
        assert snap["standards_selected"] == ["GB/T 50746-2012"]
        assert snap["report_path"] == "/mnt/user-data/outputs/r.md"
        assert len(snap["changelog"]) == 1
        assert snap["changelog"][0]["version"] == 1
        # change_log alias kept for backward compat with old SKILL references
        assert snap["change_log"] == snap["changelog"]
        # created_at == first changelog timestamp
        assert snap["created_at"] == snap["changelog"][0]["timestamp"]

    def test_second_save_increments_and_preserves_created_at(self, tmp_path):
        params = tmp_path / "params.json"
        _make_params(params)
        out = tmp_path / "project_snapshot.json"
        # v1
        _run(["save", "--task", "v1", "--params", str(params), "--output", str(out)])
        snap1 = json.loads(out.read_text(encoding="utf-8"))
        created_v1 = snap1["created_at"]
        # v2 with diff + affected
        r = _run(
            [
                "save",
                "--task",
                "改参 Q 20000->25000",
                "--params",
                str(params),
                "--diff",
                '{"Q":{"old":20000,"new":25000}}',
                "--affected",
                "Qe,Qm,ch5_calc",
                "--output",
                str(out),
            ]
        )
        assert "SNAPSHOT_READY: version=2" in r.stdout
        snap2 = json.loads(out.read_text(encoding="utf-8"))
        assert snap2["version"] == 2
        # created_at preserved across versions (反馈7 版本历史)
        assert snap2["created_at"] == created_v1
        # changelog accumulates, not overwrites
        assert [c["version"] for c in snap2["changelog"]] == [1, 2]
        assert [c["task"] for c in snap2["changelog"]] == ["v1", "改参 Q 20000->25000"]
        # last_task tracks latest
        assert snap2["last_task"] == "改参 Q 20000->25000"
        # diff + affected captured in the v2 changelog entry
        v2 = snap2["changelog"][1]
        assert v2["value_diffs"] == {"Q": {"old": 20000, "new": 25000}}
        assert v2["affected"] == "Qe,Qm,ch5_calc"

    def test_three_saves_version_sequence(self, tmp_path):
        """连续 3 轮（首次/改参/补参）→ version [1,2,3]，changelog 不丢。"""
        out = tmp_path / "project_snapshot.json"
        for i, task in enumerate(["first", "second", "third"], start=1):
            r = _run(["save", "--task", task, "--output", str(out)])
            assert f"SNAPSHOT_READY: version={i}" in r.stdout, r.stderr
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["version"] == 3
        assert [c["version"] for c in snap["changelog"]] == [1, 2, 3]
        assert snap["last_task"] == "third"


class TestSnapshotShow:
    def test_show_none_when_absent(self, tmp_path):
        r = _run(["show", "--input", str(tmp_path / "nope.json")])
        assert r.returncode == 0, r.stderr
        assert "SNAPSHOT_NONE" in r.stdout

    def test_showprints_anchor_summary(self, tmp_path):
        out = tmp_path / "project_snapshot.json"
        _run(["save", "--task", "首次生成", "--report", "/mnt/r.md", "--output", str(out)])
        _run(["save", "--task", "改参 Q", "--output", str(out)])
        r = _run(["show", "--input", str(out)])
        assert "SNAPSHOT_VERSION: 2" in r.stdout
        assert "SNAPSHOT_LAST_TASK: 改参 Q" in r.stdout
        assert "SNAPSHOT_REPORT: /mnt/r.md" in r.stdout
        assert "SNAPSHOT_LAST_CHANGE: v2 改参 Q" in r.stdout


class TestSnapshotRobustness:
    def test_corrupt_json_degrades_to_fresh(self, tmp_path):
        """损坏的快照 → 当作无快照，save 重新从 version 1 开始（与步骤0 降级一致）。"""
        out = tmp_path / "project_snapshot.json"
        out.write_text("{ not valid json @@@ ", encoding="utf-8")
        r = _run(["save", "--task", "从损坏恢复", "--output", str(out)])
        assert r.returncode == 0, r.stderr
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["version"] == 1
        assert snap["last_task"] == "从损坏恢复"

    def test_invalid_diff_falls_back_to_raw_string(self, tmp_path):
        """--diff 给了非 JSON 字符串 → 不崩，落 value_diffs_raw。"""
        out = tmp_path / "project_snapshot.json"
        r = _run(["save", "--task", "t", "--diff", "not-json", "--output", str(out)])
        assert r.returncode == 0, r.stderr
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["changelog"][0]["value_diffs_raw"] == "not-json"

    def test_no_backend_import_required(self, tmp_path):
        """snapshot.py 必须 stdlib-only：即便 backend 不可 import 也能跑（容器挂载稳健性）。

        formula_runner.py 依赖 _resolve_backend 找 app.extensions.formula_engine；
        snapshot.py 刻意不 import backend，故无此依赖。本测试间接验证：脚本在无
        PYTHONPATH/backend 的纯 subprocess 下正常工作（上面所有用例已证）。
        """
        # 显式断言脚本源码不含 backend/formula_engine import
        src = _SCRIPT.read_text(encoding="utf-8")
        assert "formula_engine" not in src
        assert "from app" not in src
        assert "import deerflow" not in src
