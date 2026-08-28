"""geological-report e2e-full fixture 回归：真实全量数据（19 族值 + 2 CSV）→ 门行为锚。

数据包: tests/fixtures/geological_report/e2e-full（页面测试数据包，README §0「直接灌数据」路径）。
回归三锚（门硬化，页面实测线程 03e18e4a 死循环取证）:
  ① 冻结值 spot 锚：全量数据 → formula_runner → L9/L11 与 expected_frozen.json 一致（数据面不变式）
  ② 薄章节 → rc=1 且**一次报齐全部 10 章**（不再 fail-fast 逐章打回——那是 60 次工具熔断的燃料）
  ③ 补足深度 → rc=0 BUILD_READY（真实基准可满足性：门不是死门）+ manifest 基准溯源=技能基准

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_e2e_full.py -v
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "geological-report"
SCRIPTS = SKILL / "scripts"
STAGE = SKILL / "references/stages/exploration.json"
FIXTURE = REPO_ROOT / "backend/tests/fixtures/geological_report/e2e-full"
TARGETS = SKILL / "references" / "depth_targets.json"

sys.path.insert(0, str(SCRIPTS))

_NUM_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")
# 薄章句（3 句，每块 ~28 eff 字符）：全部章节压到 L0（<1000）或 L2 之下 → 10 章必各报 1 项
_THIN = "本段为合成薄章节正文。语句仅为满足三句下限。不承载地质含义。"
# 扩写段（3 句，~104 eff 字符）：pad 时整段重复
_FAT = "本段为真实全量数据回归专用的合成叙述正文，语句用于把章节有效字符补足到深度目标之上，不承载地质含义。全段不含缺数标记与表格行，覆盖缩放恒为一点零。段落按目标与节数比例机械重复，用于验证深度基准可满足。"


def _run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:400]}"
    return r


def _skeleton(stage: dict, ch_id: str, filler: str) -> str:
    """stage toc 骨架：全部节号落标题、每叶子块 filler（L1/toc 门恒过；eff 由 filler 尺寸决定）。"""
    ch = stage["chapters"][ch_id]
    n = ch_id[2:]
    md = [f"## {n} {ch.get('title', '')}", "", filler]
    seen: set[str] = set()
    for sub in ch.get("toc", []):
        for no in _NUM_RE.findall(sub):
            if no in seen:
                continue
            seen.add(no)
            md += [f"{'###' if no.count('.') == 1 else '####'} {no} 小节", "", filler]
    return "\n".join(md) + "\n"


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    """全量数据灌入（19 族 JSON + 2 CSV）→ gate1 → formula_runner → 两次 build。"""
    import build_output

    base = tmp_path_factory.mktemp("geoe2e")
    data, state, out = base / "data", base / "state", base / "out"
    for d in (data, state, state / "chapters", out):
        d.mkdir(parents=True)

    for f in sorted((FIXTURE / "forms").glob("*.json")):
        fam = f.stem.split("_", 1)[1]
        _run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data, "--family", fam, "--values", f.read_text(encoding="utf-8"))
    for f in sorted((FIXTURE / "uploads").glob("*.csv")):
        fam = f.stem.split("_", 1)[1]
        _run("ingest.py", "file", "--stage", STAGE, "--data-dir", data, "--family", fam, "--input", f, expect=(0, 2, 3))
    gate1 = _run("ingest.py", "check", "--stage", STAGE, "--data-dir", data)
    _run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--output", state / "formula_state.json", expect=(0, 2, 3))

    stage = json.loads(STAGE.read_text(encoding="utf-8"))
    frozen = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
    project = json.loads((data / "00_project.json").read_text(encoding="utf-8"))
    deliv = out / f"{project['project_name']}-{project['stage']}-地质勘查报告.md"

    # ② 薄章节 build：全 10 章压瘦 → 一次报齐
    for ch_id in stage["chapters"]:
        (state / "chapters" / f"{ch_id}.md").write_text(_skeleton(stage, ch_id, _THIN), encoding="utf-8")
    thin = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(data), "--state-dir", str(state), "--output", str(deliv)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # ③ 补足深度 build：每章 eff ≥ 目标×1.15 → BUILD_READY
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    for ch_id in stage["chapters"]:
        target = targets["per_chapter"][ch_id]["median_eff"] * targets.get("coefficient", 0.6) * 1.15
        md = _skeleton(stage, ch_id, _FAT)
        while build_output.effective_chars(md) < target:
            md += "\n" + _FAT
        (state / "chapters" / f"{ch_id}.md").write_text(md, encoding="utf-8")
    fat = _run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", deliv)
    manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))

    return {"frozen": frozen, "gate1": gate1.stdout, "thin": thin, "fat": fat.stdout, "manifest": manifest, "deliv": deliv, "out": out}


class TestE2EFullGates:
    def test_gate1_complete(self, e2e):
        assert "GATE1_COMPLETE" in e2e["gate1"]

    def test_frozen_spot_anchors(self, e2e):
        """expected_frozen.json spot 锚：全量数据 → L9 总量 899.0 / L11 伴生银品位 5.42。"""
        v = e2e["frozen"]["values"]
        assert abs(v["L9.total_ore_wt"]["value"] - 899.0) < 0.05, v["L9.total_ore_wt"]
        assert abs(v["L11.ag_grade"]["value"] - 5.42) < 0.05, v.get("L11.ag_grade")

    def test_thin_build_reports_all_chapters_at_once(self, e2e):
        """薄章节：rc=1 且一次报齐全部 10 章（fail-fast 回归锚——逐章打回是 03e18e4a 死循环燃料）。"""
        r = e2e["thin"]
        assert r.returncode == 1
        assert "10 项未过门" in r.stderr and "一次报齐" in r.stderr, r.stderr
        for i in range(1, 11):
            assert f"ch{i}.md" in r.stderr, f"ch{i} 缺席:\n{r.stderr}"

    def test_fat_build_ready_real_targets_satisfiable(self, e2e):
        """补足深度：rc=0 BUILD_READY + MANIFEST_READY——真实基准可满足（门不是死门）。"""
        assert "BUILD_READY" in e2e["fat"] and "MANIFEST_READY" in e2e["fat"]

    def test_manifest_targets_provenance_canonical(self, e2e):
        """基准溯源：不传 --targets → manifest 记技能基准（references/depth_targets.json）。"""
        t = e2e["manifest"]["targets"]
        assert t["path"].replace("\\", "/").endswith("references/depth_targets.json"), t
        assert t["sha256"], t
