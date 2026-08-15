"""formula_runner CLI 端到端测试（反馈6 值差分流程）。

subprocess 调真实 CLI（execute → chapter_planner manifest → impacted），锁住
「改一个参 → 仅结果真变化的公式 → 仅受影响章节」的值差分裁剪，防止后续误改成
update_param 全量标记（评审 I2）。依赖 bug-1167 修复（parents[4]），脚本可独立运行。
"""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _REPO_ROOT / "skills" / "public" / "water-drainage-report"
_SCRIPT = _SKILL / "scripts" / "formula_runner.py"
_CHAPTER_PLANNER = _SKILL / "scripts" / "chapter_planner.py"
_FORMULAS = _SKILL / "references" / "formulas.json"

# 导入 formula_runner 模块以单测 _resolve_backend（bug-1168 回归）。scripts 目录加入 sys.path。
sys.path.insert(0, str(_SKILL / "scripts"))
import formula_runner  # noqa: E402
import pytest  # noqa: E402

# 已知好的完整参数集（与 SKILL.md 一致）；Q=20000 是基准。
_GOOD_PARAMS = json.dumps(
    {
        "Q": 20000,
        "delta_t": 10,
        "N": 5,
        "pool_area": 912,
        "V_suction": 2099.5,
        "pump_motor_spacing": 5.2,
        "filter_unit_capacity": 40,
        "filter_area": 1.13,
        "concurrent_backwash": 5,
        "total_filters": 25,
    }
)


def _run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


class TestImpactedEndToEnd:
    def test_q_change_value_diff_and_chapter_scope(self, tmp_path):
        # 1. execute → state.json（基准：Q=20000）
        state = tmp_path / "state.json"
        r = _run_script(
            _SCRIPT,
            ["execute", "--formulas", str(_FORMULAS), "--params", _GOOD_PARAMS, "--output", str(state)],
        )
        assert r.returncode == 0, r.stderr
        assert state.exists()

        # 2. chapter_planner manifest → manifest.json
        manifest = tmp_path / "manifest.json"
        rm = _run_script(
            _CHAPTER_PLANNER,
            ["manifest", "--formulas", str(_FORMULAS), "--output", str(manifest)],
        )
        assert rm.returncode == 0, rm.stderr

        # 3. impacted --param Q --value 25000（改一个根参）
        out = tmp_path / "impacted.json"
        ri = _run_script(
            _SCRIPT,
            [
                "impacted",
                "--formulas",
                str(_FORMULAS),
                "--state",
                str(state),
                "--param",
                "Q",
                "--value",
                "25000",
                "--manifest",
                str(manifest),
                "--output",
                str(out),
            ],
        )
        assert ri.returncode == 0, ri.stderr
        assert "IMPACTED_READY" in ri.stdout
        result = json.loads(out.read_text(encoding="utf-8"))

        # 值差分生效：Q 变 → Qe 等下游公式输出真变化 → 收进 affected_formulas
        assert result["param"] == "Q"
        assert "Qe" in result["affected_formulas"]
        # 紧致性：不是全部 12 公式（证明用了值差分,而非 update_param 全量标记）
        assert 0 < len(result["affected_formulas"]) < 12

        # 章节级定点：ch5_calc（Qe/Qm 计算章）必在
        assert "ch5_calc" in result["affected_chapters"]
        # ch9_equiplist（设备一览表,显式展示 filter_count）必在——评审 I1 回归锚
        assert "ch9_equiplist" in result["affected_chapters"]
        # 紧致性：不是全部 10 章（反馈6 的核心承诺：只重生成受影响章节）
        assert len(result["affected_chapters"]) < 10

    def test_unchanged_param_yields_empty_diff(self, tmp_path):
        """改参后的值与原值相同 → 无公式输出变化 → affected_formulas 为空（值差分边界）。"""
        state = tmp_path / "state.json"
        _run_script(
            _SCRIPT,
            ["execute", "--formulas", str(_FORMULAS), "--params", _GOOD_PARAMS, "--output", str(state)],
        )
        out = tmp_path / "impacted.json"
        ri = _run_script(
            _SCRIPT,
            [
                "impacted",
                "--formulas",
                str(_FORMULAS),
                "--state",
                str(state),
                "--param",
                "Q",
                "--value",
                "20000",  # 与基准相同
                "--output",
                str(out),
            ],
        )
        assert ri.returncode == 0, ri.stderr
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["affected_formulas"] == []


class TestResolveBackend:
    """bug-1168 回归：_resolve_backend 必须在宿主 + 容器两种布局下都定位到 backend。

    容器内 agent 走 /mnt/skills → skills_view 投影，脚本物理路径为
    /app/backend/.deer-flow/skills_view/public/.../scripts/。旧代码写死 parents[4] 在此处
    指向 .deer-flow（无 backend），import app 直接失败 → formula_runner trace/check 全部
    不可用 → agent 无法跑规范管线 → 陷入反复 ask_clarification 的死循环（反馈3/4/5/6/7 在
    页面全失效）。改为向上搜索「含 app/extensions/formula_engine 的目录」后两种布局都命中。
    """

    def test_host_layout(self, tmp_path):
        """宿主：<repo>/backend/app/extensions/formula_engine，脚本在 <repo>/skills/public/.../scripts。"""
        repo = tmp_path / "repo"
        (repo / "backend" / "app" / "extensions" / "formula_engine").mkdir(parents=True)
        start = repo / "skills" / "public" / "water-drainage-report" / "scripts" / "formula_runner.py"
        start.parent.mkdir(parents=True)
        start.touch()
        assert formula_runner._resolve_backend(start.resolve()) == (repo / "backend").resolve()

    def test_container_layout(self, tmp_path):
        """容器：/app/backend 下直接挂 app/...；脚本在 .deer-flow/skills_view/.../scripts。

        parents[4] 从此处指向 .deer-flow（旧 bug 现场），向上搜索应命中 /app/backend 本身。"""
        app_backend = tmp_path / "app" / "backend"
        (app_backend / "app" / "extensions" / "formula_engine").mkdir(parents=True)
        start = app_backend / ".deer-flow" / "skills_view" / "public" / "water-drainage-report" / "scripts" / "formula_runner.py"
        start.parent.mkdir(parents=True)
        start.touch()
        assert formula_runner._resolve_backend(start.resolve()) == app_backend.resolve()

    def test_not_found_raises(self, tmp_path):
        """上溯链上没有 backend → 明确报错（而非静默 import 失败）。"""
        start = tmp_path / "scripts" / "formula_runner.py"
        start.parent.mkdir(parents=True)
        start.touch()
        with pytest.raises(RuntimeError):
            formula_runner._resolve_backend(start.resolve())
