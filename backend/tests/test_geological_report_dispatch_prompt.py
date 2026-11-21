"""geological-report 派发契约内联渲染回归（硬化 2026-11 · 审查两点之二）。

chapter_planner.py prompt 把 toc 骨架 / 逐节 elements 要点 / 黄金范文切片（bank 同矿种
优先）/ 槽位词汇表 / rubric / 输出契约全部内联进子代理 prompt——子代理不再依赖沙箱
自读 references（路径不可达时任务面仍完整可执行）。

运行: cd backend && python -m pytest tests/test_geological_report_dispatch_prompt.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "public" / "geological-report" / "scripts"
STAGE = REPO_ROOT / "skills" / "public" / "geological-report" / "references" / "stages" / "exploration.json"


def _run(*args, expect=0):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / "chapter_planner.py"), "prompt", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == expect, f"rc={r.returncode}\n{r.stdout[-400:]}\n{r.stderr[:400]}"
    return r


def test_full_inline_sections(tmp_path):
    """金项目 + bank 仅铜：切片跨矿种回退仍内联；rubric/骨架/要点/截断/词汇降级全在场。"""
    data = tmp_path / "data"
    data.mkdir()
    (data / "00_project.json").write_text(json.dumps({"commodity": "岩金矿"}, ensure_ascii=False), encoding="utf-8")
    r = _run("--stage", STAGE, "--chapter", "ch4", "--data-dir", data, "--bank-limit", 300)
    p = r.stdout
    assert "第 4 章撰写任务" in p
    assert "## 本章目录骨架" in p and "4.1 矿体特征" in p
    assert "## 逐节内容要点" in p and "八要素链" in p  # stage ch4 elements 实词
    assert "## 写作 rubric" in p and "五步解读" in p and "{{SLOT:" in p
    assert "范文来源" in p and "gsb-kc-cu-0001" in p  # bank 无金切片 → 铜切片回退并声明
    assert "切片超限截断" in p  # --bank-limit 300 生效
    assert "## 槽位词汇表" in p and "formula_state 不在/为空" in p  # 未传 --state-dir → 降级声明
    assert "## 输出契约" in p and "chapters/ch4.md" in p
    assert "补充自读" in p  # 自读降级为可选补充


def test_state_dir_slot_vocab_inlined(tmp_path):
    st = tmp_path / "state"
    st.mkdir()
    (st / "formula_state.json").write_text(
        json.dumps(
            {
                "values": {
                    "L9.total_ore_wt": {"unit": "万吨"},
                    "C9.outlier_threshold": {"unit": "%"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    r = _run("--stage", STAGE, "--chapter", "ch8", "--state-dir", st)
    assert "L9.total_ore_wt（万吨）" in r.stdout
    assert "C9.outlier_threshold（%）" in r.stdout
    assert "formula_state 不在/为空" not in r.stdout


def test_unknown_chapter_rc1():
    r = _run("--stage", STAGE, "--chapter", "ch99", expect=1)
    assert "未知章节" in r.stderr


def test_output_file_ready_marker(tmp_path):
    out = tmp_path / "dispatch_ch4.md"
    r = _run("--stage", STAGE, "--chapter", "ch4", "--data-dir", tmp_path, "--output", out)
    assert "PROMPT_READY" in r.stdout
    assert out.exists() and "第 4 章撰写任务" in out.read_text(encoding="utf-8")
