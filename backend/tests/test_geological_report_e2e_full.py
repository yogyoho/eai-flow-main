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

# 薄章句（3 句，每块 ~28 eff 字符）：全部章节压到 L0（<1000）或 L2 之下 → 10 章必各报 1 项
_THIN = "本段为合成薄章节正文。语句仅为满足三句下限。不承载地质含义。"
# 扩写段（3 句，~104 eff 字符）：pad 时整段重复
_FAT = "本段为真实全量数据回归专用的合成叙述正文，语句用于把章节有效字符补足到深度目标之上，不承载地质含义。全段不含缺数标记与表格行，覆盖缩放恒为一点零。段落按目标与节数比例机械重复，用于验证深度基准可满足。"


def _run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:400]}"
    return r


def _skeleton(stage: dict, ch_id: str, filler: str) -> str:
    """stage toc 骨架：全部节号落真实节标题（build_output._toc_index 同源解析，bug2223 同款）、每叶子块 filler（L1/toc 门恒过；eff 由 filler 尺寸决定）。

    占位「小节」在 bug-3036 标题比对门下必 FAIL（P4-T7 双修：与交付名门同 commit）。
    """
    import build_output

    ch = stage["chapters"][ch_id]
    n = ch_id[2:]
    md = [f"## {n} {ch.get('title', '')}", "", filler]
    _nos, _titles = build_output._toc_index(ch.get("toc", []))
    for no in sorted(_nos, key=lambda s: [int(p) for p in s.split(".")]):
        md += [f"{'###' if no.count('.') == 1 else '####'} {no} {_titles.get(no, '小节')}".rstrip(), "", filler]
    return "\n".join(md) + "\n"


def _contract_block(stage: dict, data: Path) -> str:
    """一致性合约门（XS3 判定词逐字在场 / XS5 采空区两值在场）口径句——hydro_eng_env 表单直读（P4-T7 第三重连锁门）。

    合成骨架不含真实判定口径 → XS3/XS5 必 FAIL；仅注入补足深度 build（薄 build 保持恰好 10 项深度未过，
    「一次报齐」锚不被口径项稀释）。纯正文段落无标题——目录覆盖门契约外自创节拦截只看 # 标题。
    """
    spec = stage["forms"]["hydro_eng_env"]
    p = data / spec["file"]
    hee = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    vs = hee.get("type_verdicts") or {}
    goaf = hee.get("engineering.goaf") or {}
    lines: list[str] = []
    for k in ("hydro_type", "engineering_type", "environment_type", "combined_type"):
        if vs.get(k):
            lines += [f"综合判定：{vs[k]}。", ""]
    if goaf.get("count") is not None:
        lines += [f"区内采空区共 {goaf.get('count')} 处，总体积 {goaf.get('volume_wm3')} 万立方米。", ""]
    return "\n".join(lines)


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
    # 交付名门同源（bug-3036 去重：项目名尾缀已含阶段词不重复拼接——「勘探-勘探」双叠名回归锚）
    deliv = out / build_output.expected_deliverable_name(stage, data)

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

    # ③ 补足深度 build：每章 eff ≥ 目标×1.15 → BUILD_READY；合约章节（stage forms.chapters）注入 XS3/XS5 口径块
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    contract = _contract_block(stage, data)
    contract_chs = set(stage["forms"]["hydro_eng_env"].get("chapters", []))
    for ch_id in stage["chapters"]:
        target = targets["per_chapter"][ch_id]["median_eff"] * targets.get("coefficient", 0.6) * 1.15
        md = _skeleton(stage, ch_id, _FAT)
        if ch_id in contract_chs:
            md += contract
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
