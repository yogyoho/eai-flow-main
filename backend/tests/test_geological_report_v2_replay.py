"""geological-report v2 样例回放 eval（T7，设计 D9）。

数据面（本文件，可自动跑）：用东川样例**可复原**的真实参数回放 W1 比拟法，
断言公式正确值 10183/18136——样例正文写的 908/5531 已被走查定性为样例数字
错误（内部互不洽：908/5531≠6898/12285 比值，任何单一乘法公式下不可能），
eval 不断言样例原值（spec 2026-08-21-geol-v2-ch8-walkthrough.md §5.2）。

LLM 面（残留=0/编造=0/门呈现/KF 兜底话术）无法离线自动化，基线清单在
走查文档 §8，首次真实 agent 运行时按清单执行。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_replay.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "geological-report"
SCRIPTS = SKILL / "scripts"
STAGE = SKILL / "references/stages/exploration.json"

sys.path.insert(0, str(SCRIPTS))

# 东川样例 8.6 比拟法真实参数（未脱敏，走查 §5.2 视觉转录自 MathType OLE）
SAMPLE_W1 = {"Q0_min": 6898, "Q0_max": 12285, "F": 169285, "F0": 114671, "S": 1.0, "S0": 1.0}
# 公式正确值（Q = Q0 × F/F0 × √(S/S0)）；样例原值 908/5531 = 样例数字错误
EXPECT_Q_MIN, EXPECT_Q_MAX = 10183, 18136


def _run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode}\n{r.stdout[-600:]}"
    return r.stdout


def test_w1_replay_formula_correct_not_sample_wrong(tmp_path):
    """样例参数 → W1 输出=公式正确值；样例原值 908/5531 不得出现（不静默抄录）。"""
    import ingest

    data, state = tmp_path / "data", tmp_path / "state"
    data.mkdir(parents=True)
    state.mkdir(parents=True)
    ingest.write_form_values(str(STAGE), str(data), "hydro_eng_env", {"hydro.inflow_analogy": SAMPLE_W1})
    # 其余表单空白 → execute 走缺参降级路径（anomaly 记录），W1 链照算
    _run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--output", state / "formula_state.json", expect=(0, 3))
    st = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
    v = st["values"]
    assert abs(v["W1.Q_min"]["value"] - EXPECT_Q_MIN) <= 1, v["W1.Q_min"]
    assert abs(v["W1.Q_max"]["value"] - EXPECT_Q_MAX) <= 1, v["W1.Q_max"]
    # 样例错误值不得混入任何公式输出（防"抄录样例"实现捷径）
    for key, item in v.items():
        assert item.get("value") not in (908, 5531), f"{key} 疑似抄录样例错误值"


def test_w1_ratio_inconsistency_detector_on_sample_numbers():
    """样例 908/5531 与 6898/12285 比值互不洽——bug-2210 比值探测若在数据中
    遇到此组合会记 anomaly。此处锁数学事实本身（eval 定性依据，防回归改口径）。"""
    r1 = 908 / 5531
    r2 = 6898 / 12285
    assert abs(r1 - r2) > 0.3, "样例数字错误定性依赖两比值显著不等"
