"""控制器链路压力回归（spec 2026-08-28 §8 e2e-full 压力场景）。

真实全量数据包（19 族 JSON + 2 CSV）→ progress init → 单章门 PASS/FAIL → BLOCKED 不拖停
→ 协商 → approve-downgrade → --allow-partial 分级交付 → 复活 → 干净终验。
全部脚本级模拟（无真 LLM）；agent 依从性（是否照轮次/真派发/照 prompt 契约）只有页面测试能验（README §0）。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geo_controller_build.py -v
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
import build_output  # noqa: E402

_NUM_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")
_FAT = "本段为真实全量数据回归专用的合成叙述正文，语句用于把章节有效字符补足到深度目标之上，不承载地质含义。全段不含缺数标记与表格行，覆盖缩放恒为一点零。段落按目标与节数比例机械重复，用于验证深度基准可满足。"


def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:600]}"
    return r


def skeleton(stage: dict, ch_id: str, filler: str) -> str:
    ch = stage["chapters"][ch_id]
    n = ch_id[2:]
    # bug-3059：toc 覆盖门 v2 三向校验（编号同须标题相符）——骨架标题必须取 toc 真题
    # （复合条目「1.5 以往工作评述（1.5.1 …」在（处截断），不能再用占位「小节」。
    titles: dict[str, str] = {}
    for sub in ch.get("toc", []):
        for piece in re.split(r"[/／]", sub):
            m = re.match(r"^(\d+(?:\.\d+)*)\s*(.*)", piece.strip())
            if m and m.group(2):
                titles.setdefault(m.group(1), m.group(2).split("（")[0].split("(")[0].strip())
    md = [f"## {n} {ch.get('title', '')}", "", filler]
    seen: set[str] = set()
    for sub in ch.get("toc", []):
        for no in _NUM_RE.findall(sub):
            if no in seen:
                continue
            seen.add(no)
            md += [f"{'###' if no.count('.') == 1 else '####'} {no} {titles.get(no, '小节')}".rstrip(), "", filler]
    return "\n".join(md) + "\n"


def _pad_to(stage: dict, ch_id: str, eff_target: float) -> str:
    md = skeleton(stage, ch_id, _FAT)
    while build_output.effective_chars(md) < eff_target:
        md += "\n" + _FAT
    return md


def fat_chapter(stage: dict, ch_id: str, multiple: float = 1.15) -> str:
    """达标章：eff ≥ 目标 × multiple（L2 PASS）。"""
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    t = targets["per_chapter"][ch_id]["median_eff"] * targets.get("coefficient", 0.6) * multiple
    return _pad_to(stage, ch_id, t)


def half_chapter(stage: dict, ch_id: str) -> str:
    """半达标章：eff ≈ 目标 × 0.75——L0（≥1000）/L1/toc/槽位全过、L2 FAIL（BLOCKED 场景原料）。"""
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    t = targets["per_chapter"][ch_id]["median_eff"] * targets.get("coefficient", 0.6)
    return _pad_to(stage, ch_id, t * 0.75)


@pytest.fixture(scope="module")
def ctrl(tmp_path_factory):
    """控制器全链路（脚本模拟子代理写章）：init → 探针（缺章/手改/伪槽位）→ ch1 过门 →
    ch2 半达标门 FAIL → BLOCKED → ch3..ch10 VERIFIED → NEGOTIATE → approve →
    --allow-partial 交付 → ch2 复活重写 → 干净终验（Task 3 扩展后半）。"""
    base = tmp_path_factory.mktemp("geoctrl")
    data, state, out = base / "data", base / "state", base / "out"
    for d in (data, state, state / "chapters", out):
        d.mkdir(parents=True)
    for f in sorted((FIXTURE / "forms").glob("*.json")):
        fam = f.stem.split("_", 1)[1]
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data, "--family", fam, "--values", f.read_text(encoding="utf-8"))
    for f in sorted((FIXTURE / "uploads").glob("*.csv")):
        fam = f.stem.split("_", 1)[1]
        run("ingest.py", "file", "--stage", STAGE, "--data-dir", data, "--family", fam, "--input", f, expect=(0, 2, 3))
    run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--output", state / "formula_state.json", expect=(0, 2, 3))
    stage = json.loads(STAGE.read_text(encoding="utf-8"))

    prog = run("progress.py", "init", "--stage", STAGE, "--state-dir", state, "--data-dir", data)
    next1 = run("progress.py", "next", "--state-dir", state).stdout

    # 探针①：章节产物缺失
    miss = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch5", expect=(1,))
    # 探针②：formula_state 手改（source 键摘除）——独立副本不污染主链路
    tam = base / "tampered"
    (tam / "chapters").mkdir(parents=True)
    fs = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
    next(iter(fs["values"].values())).pop("source", None)
    (tam / "formula_state.json").write_text(json.dumps(fs, ensure_ascii=False), encoding="utf-8")
    (tam / "chapters" / "ch1.md").write_text(fat_chapter(stage, "ch1"), encoding="utf-8")
    tamper = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", tam, "--chapter", "ch1", expect=(1,))
    # 探针③：未知槽位 key
    slot = base / "badslot"
    (slot / "chapters").mkdir(parents=True)
    (slot / "formula_state.json").write_text((state / "formula_state.json").read_text(encoding="utf-8"), encoding="utf-8")
    (slot / "chapters" / "ch1.md").write_text(fat_chapter(stage, "ch1").rstrip() + "\n\n未知槽位引用 {{SLOT:totally_bogus}} 收尾。\n", encoding="utf-8")
    badslot = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", slot, "--chapter", "ch1", expect=(1,))

    # ch1：写够 → DRAFTED → 单章门 PASS → VERIFIED（bug-3049 后转正唯一通道 = progress.py gate 真跑）
    (state / "chapters" / "ch1.md").write_text(fat_chapter(stage, "ch1"), encoding="utf-8")
    run("progress.py", "mark", "ch1", "DRAFTED", "--state-dir", state)
    gate1 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch1")
    run("progress.py", "gate", "--state-dir", state, "--chapters", "ch1")
    next2 = run("progress.py", "next", "--state-dir", state).stdout

    # ch2：半达标 → DRAFTED → 单章门 FAIL（L2）→ BLOCKED
    (state / "chapters" / "ch2.md").write_text(half_chapter(stage, "ch2"), encoding="utf-8")
    run("progress.py", "mark", "ch2", "DRAFTED", "--state-dir", state)
    gate2 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch2", expect=(1,))
    run("progress.py", "mark", "ch2", "BLOCKED", "--state-dir", state, "--gate", "FAIL", "--detail", "eff 不足目标")
    next3 = run("progress.py", "next", "--state-dir", state).stdout

    # ch3..ch10 写够 → DRAFTED → 批量 gate 真跑转正（bug-3049：手动 mark VERIFIED 已禁用）
    for i in range(3, 11):
        (state / "chapters" / f"ch{i}.md").write_text(fat_chapter(stage, f"ch{i}"), encoding="utf-8")
        run("progress.py", "mark", f"ch{i}", "DRAFTED", "--state-dir", state)
    run("progress.py", "gate", "--state-dir", state, "--chapters", ",".join(f"ch{i}" for i in range(3, 11)))

    # bug-3059：一致性合约门（XS3/XS5）已接入 build——ch6 骨架须含 hydro 判定词逐字表述与
    # 采空区两值（与 data/ 11_hydro_eng_env.json 同源，containment 语义见 consistency.py check_xs）。
    hee = json.loads((data / "11_hydro_eng_env.json").read_text(encoding="utf-8"))
    tv = hee.get("type_verdicts") or {}
    goaf = hee.get("engineering.goaf") or {}
    if tv or goaf:
        ch6f = state / "chapters" / "ch6.md"
        supp = (
            f"水文地质类型为{tv.get('hydro_type', '')}；工程地质类型为{tv.get('engineering_type', '')}；"
            f"环境地质条件为{tv.get('environment_type', '')}；复合类型为{tv.get('combined_type', '')}。"
            f"老窑采空区 {goaf.get('count', '')} 个、体积 {goaf.get('volume_wm3', '')} 万 m3。"
            "本段为一致性合约门回归的合成补充叙述，判定结论与 data/ 同源，不承载额外地质含义。"
        )
        ch6f.write_text(ch6f.read_text(encoding="utf-8") + supp + "\n", encoding="utf-8")
    run("progress.py", "confirm-key-points", "--state-dir", state)
    next4 = run("progress.py", "next", "--state-dir", state).stdout  # NEGOTIATE（ch2 未批准）

    deliv = out / build_output.expected_deliverable_name(stage, data)  # bug-3059：交付名唯一来源=脚本（阶段词去重）

    # 无批准 → --allow-partial 拒绝
    noappr = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--allow-partial", "--output", deliv, expect=(1,))
    run("progress.py", "approve-downgrade", "--state-dir", state, "--chapters", "ch2", "--note", "测试批准 2026-08-28")
    next5 = run("progress.py", "next", "--state-dir", state).stdout  # FINAL --allow-partial

    partial_build = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--allow-partial", "--output", deliv)
    partial_manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))

    # ch2 复活（BLOCKED→DRAFTED）→ 重写达标 → 单章门 → 干净终验（manifest 无 partial 键）
    (state / "chapters" / "ch2.md").write_text(fat_chapter(stage, "ch2"), encoding="utf-8")
    run("progress.py", "mark", "ch2", "DRAFTED", "--state-dir", state)
    revival_gate = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch2")
    run("progress.py", "gate", "--state-dir", state, "--chapters", "ch2")
    clean_build = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", deliv)
    clean_manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))

    return {
        "prog": prog,
        "next1": next1,
        "next2": next2,
        "next3": next3,
        "next4": next4,
        "next5": next5,
        "gate1": gate1,
        "gate2": gate2,
        "miss": miss,
        "tamper": tamper,
        "badslot": badslot,
        "noappr": noappr,
        "partial_build": partial_build,
        "partial_manifest": partial_manifest,
        "revival_gate": revival_gate,
        "clean_build": clean_build,
        "clean_manifest": clean_manifest,
        "base": base,
        "data": data,
        "state": state,
        "out": out,
        "stage": stage,
    }


class TestChapterGate:
    """--chapter 单章门（spec §5.2①）：PASS / FAIL / 缺章 / 手改 / 伪槽位。"""

    def test_missing_chapter_file(self, ctrl):
        assert "章节产物缺失" in ctrl["miss"].stderr

    def test_tampered_formula_state(self, ctrl):
        assert "source" in ctrl["tamper"].stderr and "bug-2223" in ctrl["tamper"].stderr

    def test_unknown_slot_key(self, ctrl):
        assert "未知槽位" in ctrl["badslot"].stderr

    def test_pass_line_carries_numbers(self, ctrl):
        assert "CHAPTER_GATE_PASS: ch1" in ctrl["gate1"].stdout
        assert "toc" in ctrl["gate1"].stdout and "eff" in ctrl["gate1"].stdout and "目标" in ctrl["gate1"].stdout

    def test_fail_reports_depth_target(self, ctrl):
        assert "ch2" in ctrl["gate2"].stderr and "深度目标门 FAIL" in ctrl["gate2"].stderr
        assert "单章门 FAIL" in ctrl["gate2"].stderr  # 一次报齐格式


class TestControllerFlow:
    def test_init_and_first_dispatch(self, ctrl):
        assert "10 章全部 PENDING" in ctrl["prog"].stdout
        assert "PHASE: WAVE1" in ctrl["next1"] and "[NEXT] 派发: ch1" in ctrl["next1"]

    def test_after_verified_dispatches_next(self, ctrl):
        assert "PHASE: WAVE1" in ctrl["next2"] and "[NEXT] 派发: ch2" in ctrl["next2"]

    def test_blocked_does_not_stall_wave1(self, ctrl):
        assert "PHASE: WAVE1" in ctrl["next3"] and "[NEXT] 派发: ch3" in ctrl["next3"]

    def test_negotiate_when_wave1_closed(self, ctrl):
        assert "PHASE: NEGOTIATE" in ctrl["next4"] and "ch2" in ctrl["next4"]


class TestPartialDelivery:
    """--allow-partial 分级交付（spec §5.2②）：无批准拒 / 批准后放行 / manifest 逐章留痕 / 复活后干净终验。"""

    def test_without_approval_refused(self, ctrl):
        assert "未获用户批准" in ctrl["noappr"].stderr and "approve-downgrade" in ctrl["noappr"].stderr

    def test_final_next_routes_to_allow_partial(self, ctrl):
        assert "PHASE: FINAL" in ctrl["next5"] and "--allow-partial" in ctrl["next5"]

    def test_partial_build_ready_with_banner(self, ctrl):
        assert "BUILD_READY" in ctrl["partial_build"].stdout and "MANIFEST_READY" in ctrl["partial_build"].stdout
        assert "PARTIAL_DELIVERY" in ctrl["partial_build"].stdout and "1 章降档 ['ch2']" in ctrl["partial_build"].stdout

    def test_partial_manifest_chapter_depth_table(self, ctrl):
        p = ctrl["partial_manifest"]["partial"]
        assert p["downgraded"] == ["ch2"]
        assert p["downgrade_approvals"][-1]["chapters"] == ["ch2"]  # 批准原文留痕
        rows = {r["chapter"]: r for r in p["chapter_depth"]}
        assert len(rows) == 10
        assert rows["ch2"]["status"] == "DOWNGRADED" and rows["ch2"]["ratio"] < 1  # 差多少可见
        assert all(r["status"] == "VERIFIED" for c, r in rows.items() if c != "ch2")
        assert all(r["effective_chars"] > 0 for r in rows.values())

    def test_revival_then_clean_build_has_no_partial_key(self, ctrl):
        assert "CHAPTER_GATE_PASS: ch2" in ctrl["revival_gate"].stdout  # 复活重写达标
        assert "BUILD_READY" in ctrl["clean_build"].stdout
        assert "partial" not in ctrl["clean_manifest"]  # 全量 build manifest 字节不变（无 partial 键）

    def test_corrupted_progress_refused_cleanly(self, ctrl, tmp_path):
        """手改 progress.json（chapters 值为字符串）→ [build] 诊断行拒绝，非裸 traceback（03e18e4a 伪造门威胁模型）。"""
        bad = tmp_path / "badstate"
        bad.mkdir()
        (bad / "progress.json").write_text(json.dumps({"chapters": {"ch2": "BLOCKED"}}), encoding="utf-8")
        out = tmp_path / build_output.expected_deliverable_name(json.loads(STAGE.read_text(encoding="utf-8")), ctrl["data"])  # 交付名门先于 allow_partial 分支，须规范名（阶段词去重，bug-3059）
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ctrl["data"], "--state-dir", bad, "--allow-partial", "--output", out, expect=(1,))
        assert r.stderr.startswith("[build] 错误:")  # 房风诊断行
        assert "结构损坏" in r.stderr and "手改特征" in r.stderr
        assert "Traceback" not in r.stderr

    def test_null_downgrade_approvals_refused_cleanly(self, ctrl, tmp_path):
        """显式 null downgrade_approvals（.get 默认值不生效的手改形状）→ 同 [build] 诊断行拒绝，非裸 TypeError traceback。"""
        bad = tmp_path / "nullstate"
        bad.mkdir()
        (bad / "progress.json").write_text(json.dumps({"chapters": {"ch2": {"status": "BLOCKED"}}, "downgrade_approvals": None}), encoding="utf-8")
        out = tmp_path / build_output.expected_deliverable_name(json.loads(STAGE.read_text(encoding="utf-8")), ctrl["data"])  # 阶段词去重，bug-3059
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ctrl["data"], "--state-dir", bad, "--allow-partial", "--output", out, expect=(1,))
        assert r.stderr.startswith("[build] 错误:")
        assert "结构损坏" in r.stderr and "手改特征" in r.stderr
        assert "Traceback" not in r.stderr
