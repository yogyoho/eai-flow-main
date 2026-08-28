# 地质报告技能控制器化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把步骤 4 从「单 agent 顺序写 10 章」改成控制器-派发-验证循环：progress.py 状态机做唯一事实源，每章由 task() 子代理直写、单章门验证、BLOCKED 走用户降档协商、--allow-partial 诚实分级交付。

**Architecture:** 主 agent 薄上下文只协调（读 `progress.py next` → 派发 → 跑门 → 记账）；写作工艺下沉 `references/chapter_craft.md`（渐进披露）；`build_output.py` 增 `--chapter N`（单章全门）与 `--allow-partial`（批准集放行 BLOCKED 章 L2 门 + manifest 留痕）两模式；config.yaml 派发额度 6→16。

**Tech Stack:** Python 3.12 标准库（argparse/json/pathlib，与既有六脚本同构）；pytest 子进程回归（复用 e2e-full 数据包夹具模式）；SKILL.md 文档协议 + 既有结构测试锁关键词。

**Spec:** `docs/superpowers/specs/2026-08-28-geo-skill-controller-design.md`（commit c10dafbff）

---

## 运行约定（每个任务都适用）

- **分支 main-dev-fork**。提交一律**显式 pathspec，严禁 `git add -A` / `git add .`**（共享工作树，~40 并发会话）。
- Windows 下跑脚本一律 `python -X utf8`；测试统一 `cd backend && PYTHONPATH=. uv run pytest tests/<file> -v`。
- 技能脚本属 EAI 自有代码，无需 EAI-CUSTOM 注释；**config.yaml 是上游跟踪文件，改动必须带 EAI-CUSTOM 注释**。
- 派发额度 config 键已核实：`subagents.max_total_per_run`（`backend/packages/harness/deerflow/subagents/runtime.py:91-97`，clamp [1,50]，per-run 热加载——改完下一条消息生效，无需重启）。
- 派发 prompt 模板**不**单独落文件——内嵌 SKILL.md 步骤 4.1（保住 `test_knowledge_search_wiring` 的 600 字符窗口断言：knowledge_search / 矿名/地名 / standards_index 必须同窗在场）。
- 每个任务完成后按 OpenWolf 协议追加 `.wolf/memory.md` 一行；Task 6 收尾时更新 `.wolf/anatomy.md`（新增 3 文件）。

## 关键现状锚（写码前核对，防漂移）

| 锚 | 位置 | 事实 |
|---|---|---|
| `assemble()` | `skills/public/geological-report/scripts/build_output.py:315` | 签名 `assemble(stage, data_dir, state_dir, targets=None) -> tuple[str, dict]`；`backend/tests/test_geological_report_v2_scripts.py:783` 位置调用 `build_output.assemble(stage, ws["data"], st, targets=None)`——**新增参数必须带默认值** |
| 手改检测 | build_output.py:321-326 | bug-2223 source 键检查（Task 2 提取为 `load_state_and_check`，行为字节不变） |
| inject 闭包 | build_output.py:334-346 | `{{SLOT:key}}`/`{{TABLE:fam}}` 替换（Task 2 提取为 `make_inject`） |
| L2 门 | build_output.py:257-273 | `validate_depth_target`（跳过机制挂在调用点，不动函数本体） |
| 一次报齐 | build_output.py:350-373 | 全章 errors 汇总后 raise——`--chapter` 复用同格式 |
| `hash_manifest` | `skills/public/geological-report/scripts/snapshot.py:61` | `rglob state/**` 全量 SHA-256，键形如 `state/progress.json`——**progress/key_points 落 state/ 即自动纳哈希，snapshot.py 零改码**（spec §5.7 降级为测试断言） |
| SKILL.md 步骤 4 | `skills/public/geological-report/SKILL.md:83-101` | Task 4 整段替换；测试关键词锁见 Task 4 Step 1 |
| config.yaml | `config.yaml:1622` | 活动 `subagents:` 块现只有 `custom_agents:` 键（无 max_total_per_run → 默认 6） |
| e2e-full 夹具 | `backend/tests/test_geological_report_e2e_full.py` | 19 族 JSON + 2 CSV 灌数模式；`fam = f.stem.split("_", 1)[1]`；新测试文件复刻此模式 |

---

### Task 1: progress.py 状态机 + 单元测试

**Files:**
- Create: `skills/public/geological-report/scripts/progress.py`
- Test: `backend/tests/test_geo_progress.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_geo_progress.py`（完整文件）：

```python
"""progress.py 状态机单元测试（spec 2026-08-28 控制器化改造 §5.1）。

覆盖：init 全 PENDING / next 五相位路由（WAVE1→NEGOTIATE→KEY_POINTS→WAVE2→FINAL）/
mark 转移合法性（VERIFIED 必带 --gate PASS；非法转移拒）/ approve-downgrade 留痕 /
预算耗尽路由 / snapshot.hash_manifest 对 state/ 新文件的自动覆盖（spec §5.7）。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geo_progress.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "public" / "geological-report" / "scripts"
STAGE = REPO_ROOT / "skills" / "public" / "geological-report" / "references/stages/exploration.json"

sys.path.insert(0, str(SCRIPTS))


def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "progress.py"), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout}\n{r.stderr}"
    return r


@pytest.fixture()
def ws(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    run("init", "--stage", STAGE, "--state-dir", state, "--data-dir", tmp_path / "data")
    return state


class TestInitAndNext:
    def test_init_all_pending(self, ws):
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert list(doc["chapters"]) == [f"ch{i}" for i in range(1, 11)]  # 插入序=数值序（save 不 sort_keys）
        assert all(s["status"] == "PENDING" for s in doc["chapters"].values())
        assert doc["phase"] == "WAVE1" and doc["total_dispatches"] == 0

    def test_double_init_refused(self, ws):
        r = run("init", "--stage", STAGE, "--state-dir", ws, expect=(1,))
        assert "已存在" in r.stderr

    def test_next_without_init_fails(self, tmp_path):
        r = run("next", "--state-dir", tmp_path / "nope", expect=(1,))
        assert "不存在" in r.stderr

    def test_next_dispatches_pending(self, ws):
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: WAVE1" in out and "[NEXT] 派发: ch1" in out and "≤3" in out

    def test_drafted_gating_priority_over_pending(self, ws):
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)
        run("mark", "ch2", "DRAFTED", "--state-dir", ws)
        run("mark", "ch1", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        out = run("next", "--state-dir", ws).stdout  # ch2 已起草 → 先跑门，不派 ch3
        assert "跑门: ch2" in out and "--chapter ch2" in out
        assert "派发: ch3" not in out

    def test_gate_command_rendered_with_paths(self, ws):
        run("mark", "ch3", "DRAFTED", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        # init 记录的 stage/data 路径直接渲染进命令（断点续跑新会话可复制执行）
        assert "build_output.py" in out and "--chapter ch3" in out and str(STAGE) in out

    def test_blocked_chapter_does_not_stall_wave1(self, ws):
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--detail", "深度缺口 2400 eff")
        out = run("next", "--state-dir", ws).stdout
        assert "[NEXT] 派发: ch1" in out  # 单章 BLOCKED 不拖停全书（先写完能写的）

    def test_budget_exhaustion_routes_to_block(self, ws):
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        doc["total_dispatches"] = 16  # 测试直改（夹具特权；agent 面前唯一写者是 progress.py）
        (ws / "progress.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        out = run("next", "--state-dir", ws).stdout
        assert "额度耗尽" in out and "BLOCKED" in out

    def test_wave1_closed_with_unapproved_blocked_negotiates(self, ws):
        for i in range(1, 10):
            if i == 3:
                continue
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
            run("mark", f"ch{i}", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL", "--detail", "eff 800 < 目标 2894")
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: NEGOTIATE" in out and "ch3" in out and "approve-downgrade" in out and "差距表" in out

    def test_key_points_then_wave2_then_clean_final(self, ws):
        for i in range(1, 10):
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
            run("mark", f"ch{i}", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: KEY_POINTS" in out and "key_points.json" in out
        (ws / "key_points.json").write_text(json.dumps({"chapters": {"ch1": ["要点"]}, "highlights": {}, "issues": []}, ensure_ascii=False), encoding="utf-8")
        run("confirm-key-points", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: WAVE2" in out and "ch10" in out and "要点包" in out
        run("mark", "ch10", "DRAFTED", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        assert "跑门: ch10" in out
        run("mark", "ch10", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: FINAL" in out and "--allow-partial" not in out  # 全 VERIFIED → 干净终验

    def test_final_with_approval_uses_allow_partial(self, ws):
        for i in range(1, 10):
            if i == 3:
                continue
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
            run("mark", f"ch{i}", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL", "--detail", "eff 1200 < 2894")
        run("approve-downgrade", "--state-dir", ws, "--chapters", "ch3", "--note", "用户批准 2026-08-28")
        run("confirm-key-points", "--state-dir", ws)
        run("mark", "ch10", "DRAFTED", "--state-dir", ws)
        run("mark", "ch10", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: FINAL" in out and "--allow-partial" in out and "ch3" in out


class TestMarkValidation:
    def test_verified_requires_gate_pass(self, ws):
        r = run("mark", "ch1", "VERIFIED", "--state-dir", ws, expect=(1,))
        assert "--gate PASS" in r.stderr  # 只信产物，不信摘要

    def test_illegal_transition_refused(self, ws):
        run("mark", "ch1", "VERIFIED", "--state-dir", ws, "--gate", "PASS")
        r = run("mark", "ch1", "BLOCKED", "--state-dir", ws, expect=(1,))
        assert "非法转移" in r.stderr

    def test_redispatch_increments_counters(self, ws):
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)  # 重派：DRAFTED→DRAFTED 合法
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch1"]["dispatches"] == 2 and doc["total_dispatches"] == 2

    def test_pending_to_blocked_allowed_budget_exhaustion(self, ws):
        run("mark", "ch9", "BLOCKED", "--state-dir", ws, "--detail", "派发额度耗尽")
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch9"]["status"] == "BLOCKED"

    def test_blocked_revival_via_drafted(self, ws):
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL")
        run("mark", "ch3", "DRAFTED", "--state-dir", ws)  # 补数据/批准后复活重写
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch3"]["status"] == "DRAFTED"

    def test_unknown_chapter_refused(self, ws):
        r = run("mark", "ch99", "DRAFTED", "--state-dir", ws, expect=(1,))
        assert "未知章节" in r.stderr


class TestApproveDowngrade:
    def test_approval_recorded_with_note_and_timestamp(self, ws):
        run("approve-downgrade", "--state-dir", ws, "--chapters", "ch3,ch8", "--note", "对话确认 2026-08-28")
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        a = doc["downgrade_approvals"][-1]
        assert a["chapters"] == ["ch3", "ch8"] and a["note"] == "对话确认 2026-08-28"
        assert a["approved_at"]  # ISO 时间戳在场

    def test_unknown_chapter_refused(self, ws):
        r = run("approve-downgrade", "--state-dir", ws, "--chapters", "ch88", "--note", "x", expect=(1,))
        assert "未知章节" in r.stderr


class TestSnapshotCoverage:
    """spec §5.7：progress.json / key_points.json 落 state/ → snapshot rglob 自动纳哈希（零改码，锁定行为）。"""

    def test_state_files_hashed(self, tmp_path):
        import snapshot

        state = tmp_path / "state"
        state.mkdir()
        (state / "progress.json").write_text("{}", encoding="utf-8")
        (state / "key_points.json").write_text("{}", encoding="utf-8")
        m = snapshot.hash_manifest(tmp_path / "data", state)
        assert "state/progress.json" in m and "state/key_points.json" in m
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_progress.py -v
```
Expected: collection error / 全 FAIL（`progress.py` 不存在）。

- [ ] **Step 3: 实现 progress.py（完整文件）**

创建 `skills/public/geological-report/scripts/progress.py`：

```python
#!/usr/bin/env python3
"""geological-report v2 — progress.py：章节进度状态机（步骤4 控制器）。

spec 2026-08-28 控制器化改造：主 agent 薄上下文只协调——每轮读 `next`（输出恰好一个
下一步动作 + 精确命令 + 期望 rc），派发/跑门/记账，不亲自写章。progress.json 是唯一
事实源（本脚本唯一写者，防手改同 formula_state 惯例）；断点续跑靠磁盘不靠对话记忆
（FORCED STOP / 上下文摘要压缩 / 新会话均无损恢复，spec §6 流4）。

状态机：
  PENDING  --派发--> DRAFTED --门PASS--> VERIFIED --修改回路--> DRAFTED
  DRAFTED  --重派--> DRAFTED（dispatches 递增；每章重派 ≤1 次由 SKILL.md 协议约束）
  DRAFTED  --门FAIL且重派耗尽--> BLOCKED --补数据/批准降档--> DRAFTED
  PENDING  --额度耗尽--> BLOCKED
VERIFIED 只能来自单章门 rc=0（--gate PASS 强制）——只信产物，不信子代理摘要。

相位推导（derive_phase，单一事实）：
  wave1 有 PENDING/DRAFTED → WAVE1（单章 BLOCKED 不拖停全书）
  存在未批准 BLOCKED → NEGOTIATE（先协商再定要点包范围）
  要点包未确认 → KEY_POINTS；ch10 未收口 → WAVE2；否则 FINAL。

退出码：0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

# 派发额度 = config.yaml subagents.max_total_per_run（本计划 Task 5 提额到 16；clamp [1,50]）。
# progress.py 不读 harness 配置（技能脚本自包含），按 16 做预算展示与耗尽判定。
DISPATCH_BUDGET = 16

TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DRAFTED", "BLOCKED"},  # PENDING→BLOCKED = 派发额度耗尽
    "DRAFTED": {"DRAFTED", "VERIFIED", "BLOCKED"},  # DRAFTED→DRAFTED = 重派
    "VERIFIED": {"DRAFTED"},  # 修改回路重写
    "BLOCKED": {"DRAFTED"},  # 补数据/批准降档后复活
}


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def load(state_dir: Path) -> dict:
    p = state_dir / "progress.json"
    if not p.exists():
        print(f"[progress] {p} 不存在——新任务先 init；续跑检查 --state-dir 路径", file=sys.stderr)
        raise SystemExit(EXIT_ERROR)
    return json.loads(p.read_text(encoding="utf-8"))


def save(state_dir: Path, doc: dict) -> None:
    """原子写（tmp + os.replace，build_output 同款）。不用 sort_keys：chapters 插入序=数值序。"""
    p = state_dir / "progress.json"
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, p)


def approved_set(doc: dict) -> set[str]:
    out: set[str] = set()
    for a in doc.get("downgrade_approvals", []):
        out.update(a.get("chapters", []))
    return out


def derive_phase(doc: dict) -> str:
    chs = doc["chapters"]
    order = chapter_order(chs)
    wave1 = order[:-1]
    wave2 = [order[-1]] if order else []
    unapproved = {c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc)
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave1):
        return "WAVE1"
    if unapproved:
        return "NEGOTIATE"
    if not doc.get("key_points_confirmed"):
        return "KEY_POINTS"
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave2):
        return "WAVE2"
    return "FINAL"


def _build_cmd(stage: str, data: str, sd: str, *extra: str) -> str:
    return "python -X utf8 " + str(Path(__file__).resolve().parent / "build_output.py") + f" --stage {stage} --data-dir {data} --state-dir {sd} " + " ".join(extra)


def next_action(doc: dict, state_dir: Path) -> str:
    phase = derive_phase(doc)
    chs = doc["chapters"]
    order = chapter_order(chs)
    wave1 = order[:-1]
    last = order[-1] if order else None
    stage = doc.get("stage_path") or "<STAGE>"
    data = doc.get("data_dir") or "<DATA>"
    sd = str(state_dir)
    lines = [f"PHASE: {phase}"]

    if phase == "WAVE1":
        drafted = next((c for c in wave1 if chs[c]["status"] == "DRAFTED"), None)  # 先收口已起草的
        if drafted:
            lines += [
                f"[NEXT] 跑门: {drafted}（DRAFTED——只信产物，不信子代理摘要）",
                f"命令: {_build_cmd(stage, data, sd, '--chapter', drafted)}",
                f"期望 rc: 0 → python -X utf8 progress.py mark {drafted} VERIFIED --state-dir {sd} --gate PASS",
                f"        1 → 原 prompt + stderr 原文重派（每章 ≤1 次）；重派仍 FAIL → progress.py mark {drafted} BLOCKED --state-dir {sd} --gate FAIL --detail \"<一句话差距>\"",
            ]
            return "\n".join(lines)
        pending = [c for c in wave1 if chs[c]["status"] == "PENDING"]
        if doc.get("total_dispatches", 0) >= DISPATCH_BUDGET:
            lines += [
                f"[NEXT] 额度耗尽: 总派发 {doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET}，剩余 PENDING {pending}",
                f"动作: 逐章 progress.py mark <chN> BLOCKED --state-dir {sd} --detail \"派发额度耗尽\" → 进协商（或请用户新会话续跑，progress 无损）",
            ]
            return "\n".join(lines)
        c = pending[0]
        lines += [
            f"[NEXT] 派发: {c}（PENDING，wave1 独立章）",
            f"动作: 按 SKILL.md 步骤4 派发契约组装 prompt，task(subagent_type=\"general-purpose\") 派子代理直写 state/chapters/{c}.md",
            "约束: 每轮 ≤3 个并发 task()（超发被运行时静默丢弃）；子代理只回 ≤10 行摘要（含本章要点 3-5 条）",
            f"派发后记账: progress.py mark {c} DRAFTED --state-dir {sd}（收章后跑单章门，见 DRAFTED 分支）",
        ]
        return "\n".join(lines)

    if phase == "NEGOTIATE":
        un = sorted({c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc))
        lines += [
            f"[NEXT] 协商: 未批准 BLOCKED: {', '.join(un)}",
            "动作: 组差距表（章/实际 eff/目标/缺口——取各章 gate_detail 与单章门 stderr）单表单 ask_clarification 三选项:",
            "  ① 补数据（回 ingest → formula_runner → 相关章 mark DRAFTED 重派）",
            f"  ② 批准降档（progress.py approve-downgrade --state-dir {sd} --chapters {','.join(un)} --note \"<用户批准依据>\"）",
            "  ③ [待确认] 收尾（缺数信号放宽覆盖缩放，重写即可能达标）",
            "期望: 用户答复后才推进（单回合至多一次 ask_clarification；挂起即停，不推进）",
        ]
        return "\n".join(lines)

    if phase == "KEY_POINTS":
        lines += [
            "[NEXT] 要点包: wave1 已收口，蒸馏 state/key_points.json",
            "动作: 聚合各子代理摘要的「本章要点 3-5 条」+ formula_state 关键值（L9 总量/分类量、L10 对比、E 链经济指标）",
            f"      写 state/key_points.json: {{\"chapters\":{{\"ch1\":[...],...}},\"highlights\":{{...}},\"issues\":[...]}}",
            f"      单表单 ask_clarification 呈现用户确认 → progress.py confirm-key-points --state-dir {sd}",
            "要点包 = ch10 唯一事实来源（不重读 9 章全文）",
        ]
        return "\n".join(lines)

    if phase == "WAVE2":
        if chs[last]["status"] == "DRAFTED":
            lines += [
                f"[NEXT] 跑门: {last}（DRAFTED，wave2 结论章）",
                f"命令: {_build_cmd(stage, data, sd, '--chapter', last)}",
                "期望 rc: 同 WAVE1 跑门分支（PASS→VERIFIED / FAIL→重派 ≤1 次→BLOCKED）",
            ]
            return "\n".join(lines)
        lines += [
            f"[NEXT] 派发: {last}（PENDING，wave2 结论章）",
            "动作: 派发契约同 wave1，输入追加 state/key_points.json——只依据要点包写投影式结论，不引入 wave1 之外的新数字",
        ]
        return "\n".join(lines)

    # FINAL
    blocked = sorted(c for c, s in chs.items() if s["status"] == "BLOCKED")
    if blocked:
        lines += [
            f"[NEXT] 终验（分级交付）: 已批准降档 {blocked}",
            f"命令: {_build_cmd(stage, data, sd, '--allow-partial', '--output', '<OUTPUTS>/<项目名>-<阶段>-地质勘查报告.md')}",
            "期望 rc: 0 BUILD_READY（stdout PARTIAL_DELIVERY 行明示 N 章降档；manifest.partial 逐章留痕）→ consistency.py → snapshot.py save → present_files（向用户汇报降档章节与差距）",
        ]
        return "\n".join(lines)
    lines += [
        "[NEXT] 终验: 全部章节 VERIFIED",
        f"命令: {_build_cmd(stage, data, sd, '--output', '<OUTPUTS>/<项目名>-<阶段>-地质勘查报告.md')}",
        "期望 rc: 0 BUILD_READY → consistency.py → snapshot.py save → present_files",
    ]
    return "\n".join(lines)


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    p = state_dir / "progress.json"
    if p.exists():
        print(f"[progress] {p} 已存在——续跑请用 next/status，勿重复 init 抹掉进度", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
    doc = {
        "stage_path": str(Path(args.stage).resolve()),
        "data_dir": str(Path(args.data_dir).resolve()) if args.data_dir else None,
        "phase": "WAVE1",
        "total_dispatches": 0,
        "chapters": {c: {"status": "PENDING", "dispatches": 0, "last_gate": None, "gate_detail": "", "blocked_reason": None} for c in chapter_order(stage.get("chapters", {}))},
        "key_points_confirmed": False,
        "downgrade_approvals": [],
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    save(state_dir, doc)
    n = len(doc["chapters"])
    print(f"PROGRESS_INIT: {n} 章全部 PENDING（{', '.join(doc['chapters'])}）→ 下一步 progress.py next")
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    print(next_action(doc, Path(args.state_dir)))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    print(f"phase={derive_phase(doc)} 总派发={doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET} 要点包确认={doc.get('key_points_confirmed', False)}")
    for c in chapter_order(doc["chapters"]):
        s = doc["chapters"][c]
        extra = f" reason={s['blocked_reason']}" if s.get("blocked_reason") else ""
        print(f"  {c}: {s['status']} 派发{s.get('dispatches', 0)} 门={s.get('last_gate')}{extra}")
    return EXIT_OK


def cmd_mark(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    ch_id, status = args.chapter, args.status
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    if status not in ("DRAFTED", "VERIFIED", "BLOCKED"):
        print(f"[progress] mark 只接受 DRAFTED/VERIFIED/BLOCKED（收到 {status}）", file=sys.stderr)
        return EXIT_ERROR
    cur = doc["chapters"][ch_id]["status"]
    if status not in TRANSITIONS[cur]:
        print(f"[progress] 非法转移 {ch_id}: {cur} → {status}（合法: {cur} → {sorted(TRANSITIONS[cur])}）", file=sys.stderr)
        return EXIT_ERROR
    if status == "VERIFIED" and args.gate != "PASS":
        print(f"[progress] {ch_id} VERIFIED 必须带 --gate PASS——VERIFIED 只能来自单章门 rc=0（只信产物，不信子代理摘要）", file=sys.stderr)
        return EXIT_ERROR
    ent = doc["chapters"][ch_id]
    ent["status"] = status
    if status == "DRAFTED":
        ent["dispatches"] = ent.get("dispatches", 0) + 1
        doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    elif status == "VERIFIED":
        ent["last_gate"] = "PASS"
        ent["gate_detail"] = args.detail or ""
    else:  # BLOCKED
        ent["last_gate"] = args.gate or "FAIL"
        ent["gate_detail"] = args.detail or ""
        ent["blocked_reason"] = args.detail or ("门 FAIL 且重派耗尽" if args.gate != "PASS" else "派发额度耗尽")
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"MARKED: {ch_id} {cur} → {status}（phase={doc['phase']}）")
    return EXIT_OK


def cmd_confirm(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    doc["key_points_confirmed"] = True
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"KEY_POINTS_CONFIRMED（phase={doc['phase']}）")
    return EXIT_OK


def cmd_approve(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    chs = [c.strip() for c in args.chapters.split(",") if c.strip()]
    unknown = [c for c in chs if c not in doc["chapters"]]
    if unknown:
        print(f"[progress] 未知章节 {unknown}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    doc.setdefault("downgrade_approvals", []).append({"chapters": chs, "note": args.note or "", "approved_at": datetime.now().astimezone().isoformat(timespec="seconds")})
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"APPROVED: 降档批准 {chs}（累计批准集 {sorted(approved_set(doc))}，phase={doc['phase']}）")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 章节进度状态机（步骤4 控制器）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init", help="按 stage 章节清单初始化 progress.json（全 PENDING；已存在=续跑拒重置）")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--data-dir", help="记录数据目录（next 渲染精确命令用；缺省输出 <DATA> 占位）")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("next", help="控制器每轮先读：恰好一个下一步动作 + 精确命令 + 期望 rc")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_next)
    sp = sub.add_parser("status", help="全章状态表 + 派发计数 + 额度余量")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("mark", help="状态转移（DRAFTED/VERIFIED/BLOCKED）")
    sp.add_argument("chapter")
    sp.add_argument("status")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--gate", choices=["PASS", "FAIL"])
    sp.add_argument("--detail", default="")
    sp.set_defaults(fn=cmd_mark)
    sp = sub.add_parser("confirm-key-points", help="要点包已经用户单表单确认（解锁 ch10）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_confirm)
    sp = sub.add_parser("approve-downgrade", help="记录用户批准的降档（--allow-partial 放行凭据）")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", required=True, help="逗号分隔，如 ch3,ch8")
    sp.add_argument("--note", default="")
    sp.set_defaults(fn=cmd_approve)
    args = p.parse_args()
    try:
        return args.fn(args)
    except json.JSONDecodeError as e:
        print(f"[progress] JSON 损坏: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_progress.py -v
```
Expected: 20 passed（TestInitAndNext 11 + TestMarkValidation 6 + TestApproveDowngrade 2 + TestSnapshotCoverage 1）。

- [ ] **Step 5: ruff + 提交**

```bash
cd backend && uv run ruff check --config ruff.toml ../skills/public/geological-report/scripts/progress.py && uv run ruff format --config ruff.toml --check ../skills/public/geological-report/scripts/progress.py
git add skills/public/geological-report/scripts/progress.py backend/tests/test_geo_progress.py
git commit -m "feat(geo-skill): progress.py 章节进度状态机——控制器唯一事实源（init/next/mark/approve-downgrade + 五相位路由 + 派发预算）"
```

---

### Task 2: build_output.py 重构（行为不变）+ --chapter 单章门

**Files:**
- Modify: `skills/public/geological-report/scripts/build_output.py`
- Test: `backend/tests/test_geo_controller_build.py`（新建）

- [ ] **Step 1: 重构提取（先跑既有回归证不变）**

在 build_output.py 中：① 在 `assemble` 之前新增 `load_state_and_check` 与 `make_inject`（代码如下）；② `assemble` 改为调用两者（删原内联块），签名追加 `skip_l2: set[str] | None = None, partial: dict | None = None`（本步内均为默认 None——skip_l2 的守卫行随重构落位、partial 的消费点 Task 3 才加；保证 v2_scripts:783 位置调用兼容）。

```python
def load_state_and_check(state_dir: Path) -> tuple[dict, dict | None]:
    """formula_state 装载 + bug-2223 手改检测门 + consistency 装载（assemble 与单章门共用）。"""
    state_path = state_dir / "formula_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # ── bug-2223 手改检测门：formula_runner.emit() 给每个槽位写 source 键；手改必丢 ──
    for key, slot in state.get("values", {}).items():
        if not isinstance(slot, dict):
            raise ValueError(f"formula_state 槽位 {key} 不是对象（数值裸写=手改特征，formula_runner 是唯一写者，bug-2223）")
        if isinstance(slot.get("value"), (int, float)) and not isinstance(slot.get("value"), bool) and "source" not in slot:
            raise ValueError(f"formula_state 槽位 {key} 缺 source 键——疑似手改（formula_runner 是唯一写者，数字永不经过 LLM，bug-2223）。改数请走 ingest.py forms → formula_runner execute，勿直接编辑 formula_state.json")
    consistency = None
    cc_path = state_dir / "consistency_check.json"
    if cc_path.exists():
        consistency = json.loads(cc_path.read_text(encoding="utf-8"))
    return state, consistency


def make_inject(stage: dict, data_dir: Path, state: dict, unknown_keys: set[str]):
    """{{SLOT:key}}/{{TABLE:fam}} 注入闭包工厂（assemble 与单章门共用；unknown_keys 就地累积）。"""

    def inject(text: str) -> str:
        def slot_sub(m: re.Match) -> str:
            key = m.group(1).strip()
            v = state.get("values", {}).get(key)
            if v is None:
                unknown_keys.add(key)
                return m.group(0)
            return v.get("display", str(v.get("value")))

        def table_sub(m: re.Match) -> str:
            return render_family(m.group(1).strip(), stage, data_dir)

        return TABLE_RE.sub(table_sub, SLOT_RE.sub(slot_sub, text))

    return inject
```

重写后的 `assemble`（行为字节不变；变化点仅注释处）：

```python
def assemble(stage: dict, data_dir: Path, state_dir: Path, targets: dict | None = None, skip_l2: set[str] | None = None, partial: dict | None = None) -> tuple[str, dict[str, dict]]:
    if targets is None:
        # 防绕：直调 assemble（targets=None）也吃技能真基准——页面实测线程 03e18e4a 直调跳过 L2 ~10 次
        targets = load_targets(CANONICAL_TARGETS)
    state_path = state_dir / "formula_state.json"
    state, consistency = load_state_and_check(state_dir)  # 重构：手改检测提取
    unknown_keys: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys)  # 重构：注入闭包提取
    toc_stats: dict[str, dict] = {}

    parts = [render_front_matter(stage, data_dir)]
    chap_dir = state_dir / "chapters"
    # 一次报齐：全部章节全部门跑完汇总（页面实测线程 03e18e4a——fail-fast 逐章打回把一轮扩写切成 N 轮 build 循环，60 次工具熔断的燃料）
    errors: list[str] = []
    for ch_id in sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99):
        cf = chap_dir / f"{ch_id}.md"
        if not cf.exists():
            errors.append(f"章节产物缺失: {cf}（波次生成未完成，不静默跳过）")
            continue
        raw = cf.read_text(encoding="utf-8")
        try:
            validate_chapter(ch_id, raw)
            validate_depth(ch_id, raw)
            toc_stats[ch_id] = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
            injected = inject(raw).rstrip() + "\n"
            if targets is not None and not (skip_l2 and ch_id in skip_l2):  # skip_l2：--allow-partial 批准集（Task 3）
                validate_depth_target(ch_id, injected, targets)
        except ValueError as e:
            errors.append(str(e))
            continue
        parts.append(injected)
    parts.append(render_compliance_appendix(consistency, state, state_path))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if errors:
        raise ValueError(f"{len(errors)} 项未过门（一次报齐，逐项修完再重跑——勿修一章跑一轮）:\n" + "\n".join(errors))
    return "\n\n".join(parts) + "\n", toc_stats
```

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_e2e_full.py -v
```
Expected: 全绿（重构行为不变锚）。

```bash
git add skills/public/geological-report/scripts/build_output.py
git commit -m "refactor(geo-skill): build_output 提取 load_state_and_check/make_inject——assemble 与单章门共用（行为字节不变，既有回归全绿）"
```

- [ ] **Step 2: 写失败测试（单章门）**

创建 `backend/tests/test_geo_controller_build.py`（本任务先落 TestChapterGate + TestControllerFlow 前半；Task 3 再扩展协商/分级交付场景）：

```python
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
_THIN = "本段为合成薄章节正文。语句仅为满足三句下限。不承载地质含义。"
_FAT = "本段为真实全量数据回归专用的合成叙述正文，语句用于把章节有效字符补足到深度目标之上，不承载地质含义。全段不含缺数标记与表格行，覆盖缩放恒为一点零。段落按目标与节数比例机械重复，用于验证深度基准可满足。"


def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:600]}"
    return r


def skeleton(stage: dict, ch_id: str, filler: str) -> str:
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

    # ch1：写够 → DRAFTED → 单章门 PASS → VERIFIED
    (state / "chapters" / "ch1.md").write_text(fat_chapter(stage, "ch1"), encoding="utf-8")
    run("progress.py", "mark", "ch1", "DRAFTED", "--state-dir", state)
    gate1 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch1")
    run("progress.py", "mark", "ch1", "VERIFIED", "--state-dir", state, "--gate", "PASS")
    next2 = run("progress.py", "next", "--state-dir", state).stdout

    # ch2：半达标 → DRAFTED → 单章门 FAIL（L2）→ BLOCKED
    (state / "chapters" / "ch2.md").write_text(half_chapter(stage, "ch2"), encoding="utf-8")
    run("progress.py", "mark", "ch2", "DRAFTED", "--state-dir", state)
    gate2 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--chapter", "ch2", expect=(1,))
    run("progress.py", "mark", "ch2", "BLOCKED", "--state-dir", state, "--gate", "FAIL", "--detail", "eff 不足目标")
    next3 = run("progress.py", "next", "--state-dir", state).stdout

    # ch3..ch10 写够直接 VERIFIED（本夹具聚焦门/进度交互，不逐章跑门）
    for i in range(3, 11):
        (state / "chapters" / f"ch{i}.md").write_text(fat_chapter(stage, f"ch{i}"), encoding="utf-8")
        run("progress.py", "mark", f"ch{i}", "DRAFTED", "--state-dir", state)
        run("progress.py", "mark", f"ch{i}", "VERIFIED", "--state-dir", state, "--gate", "PASS")
    run("progress.py", "confirm-key-points", "--state-dir", state)
    next4 = run("progress.py", "next", "--state-dir", state).stdout  # NEGOTIATE（ch2 未批准）

    # —— Task 3 扩展点：协商 → partial 交付 → 复活 → 干净终验 ——

    return {
        "prog": prog, "next1": next1, "next2": next2, "next3": next3, "next4": next4,
        "gate1": gate1, "gate2": gate2, "miss": miss, "tamper": tamper, "badslot": badslot,
        "base": base, "data": data, "state": state, "out": out, "stage": stage,
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
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_controller_build.py -v
```
Expected: FAIL（`--chapter` 未实现——argparse unrecognized arguments / rc=2，夹具探针断言炸）。

- [ ] **Step 4: 实现 --chapter 单章门**

build_output.py 新增（放在 `assemble` 之后）：

```python
def run_chapter_gate(stage: dict, data_dir: Path, state_dir: Path, ch_id: str, targets: dict | None) -> None:
    """--chapter 单章全门（spec §5.2①）：validate_chapter + validate_depth + validate_toc + inject
    + validate_depth_target，一次报齐该章全部问题（同 assemble 章内块格式）。

    不产交付物（交付名门/散文件门不适用）、不写 progress.json（唯一写者=progress.py）。
    PASS 打 CHAPTER_GATE_PASS 行（eff/目标/覆盖缩放——mark VERIFIED 与重派决策的数据面）。
    """
    order = sorted(stage.get("chapters", {}), key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)
    if ch_id not in stage.get("chapters", {}):
        raise ValueError(f"未知章节 {ch_id}（stage 在册: {order}）")
    state, _consistency = load_state_and_check(state_dir)
    unknown_keys: set[str] = set()
    inject = make_inject(stage, data_dir, state, unknown_keys)
    cf = state_dir / "chapters" / f"{ch_id}.md"
    if not cf.exists():
        raise ValueError(f"章节产物缺失: {cf}（子代理未完成或未派发——先按 progress.py next 指引派发/重派该章）")
    raw = cf.read_text(encoding="utf-8")
    errors: list[str] = []
    toc: dict = {}
    injected = ""
    try:
        validate_chapter(ch_id, raw)
        validate_depth(ch_id, raw)
        toc = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
        injected = inject(raw).rstrip() + "\n"
        if targets is not None:
            validate_depth_target(ch_id, injected, targets)
    except ValueError as e:
        errors.append(str(e))
    if unknown_keys:
        errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: {sorted(unknown_keys)}")
    if errors:
        raise ValueError(f"{ch_id} 单章门 FAIL（{len(errors)} 项，一次报齐——补写该章正文后重跑）:\n" + "\n".join(errors))
    ch = (targets or {}).get("per_chapter", {}).get(ch_id)
    if ch:
        scale = coverage_scale(injected, targets)
        t = ch.get("median_eff", 0) * targets.get("coefficient", 0.6) * scale
        print(f"CHAPTER_GATE_PASS: {ch_id} toc {toc['toc_covered']}/{toc['toc_entries']} eff {effective_chars(injected)} ≥ 目标 {t:.0f}（样例 median {ch.get('median_eff')} × {targets.get('coefficient', 0.6)} × 覆盖缩放 {scale:.2f}）")
    else:
        print(f"CHAPTER_GATE_PASS: {ch_id} toc {toc['toc_covered']}/{toc['toc_entries']} eff {effective_chars(injected)}（L2 基准未覆盖该章，地板门通过）")
```

`main()` 改动（argparse 区 + 分发）：

```python
    p.add_argument("--chapter", help="单章门模式：只验证该章（ch_id 如 ch3），不产交付物/不写 progress.json")
    p.add_argument("--allow-partial", action="store_true", help="分级交付：progress.json 已批准的 BLOCKED 章跳过 L2 深度目标门（L0/L1/toc/槽位门仍在场），manifest 留痕")
    p.add_argument("--output", help="交付物输出路径（--chapter 模式不需要）")
```

（`--output` 从 `required=True` 改为可选，`main` 开头加互斥校验：）

```python
    args = p.parse_args()
    if args.chapter and (args.output or args.allow_partial):
        print("[build] --chapter 与 --output/--allow-partial 互斥（单章门不产交付物）", file=sys.stderr)
        return EXIT_ERROR
    if not args.chapter and not args.output:
        print("[build] 需要 --output（或用 --chapter 走单章门）", file=sys.stderr)
        return EXIT_ERROR
    try:
        stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
        targets, targets_src = resolve_targets(args.targets, Path(args.stage))
        if args.chapter:
            run_chapter_gate(stage, Path(args.data_dir), Path(args.state_dir), args.chapter, targets)
            return EXIT_OK
        # ……以下原交付名门/散文件门/assemble 逻辑不变……
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_controller_build.py -v
```
Expected: TestChapterGate 5 passed + TestControllerFlow 4 passed。

- [ ] **Step 6: 既有回归 + ruff + 提交**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_e2e_full.py tests/test_geo_progress.py -v
cd backend && uv run ruff check --config ruff.toml ../skills/public/geological-report/scripts/build_output.py
git add skills/public/geological-report/scripts/build_output.py backend/tests/test_geo_controller_build.py
git commit -m "feat(geo-skill): build_output --chapter N 单章全门——控制器收章即验（一次报齐/不产交付物/不写 progress），缺章+手改+伪槽位探针锚"
```

---

### Task 3: build_output.py --allow-partial 分级交付

**Files:**
- Modify: `skills/public/geological-report/scripts/build_output.py`
- Test: `backend/tests/test_geo_controller_build.py`（扩展夹具后半 + 新测试类）

- [ ] **Step 1: 写失败测试（扩展夹具 + TestPartialDelivery）**

`backend/tests/test_geo_controller_build.py` 中，把夹具的 `# —— Task 3 扩展点 ——` 注释替换为以下后半段（`return` 之前）：

```python
    project = json.loads((data / "00_project.json").read_text(encoding="utf-8"))
    deliv = out / f"{project['project_name']}-{project['stage']}-地质勘查报告.md"

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
    run("progress.py", "mark", "ch2", "VERIFIED", "--state-dir", state, "--gate", "PASS")
    clean_build = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", deliv)
    clean_manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))
```

`return` 字典扩为：

```python
    return {
        "prog": prog, "next1": next1, "next2": next2, "next3": next3, "next4": next4, "next5": next5,
        "gate1": gate1, "gate2": gate2, "miss": miss, "tamper": tamper, "badslot": badslot,
        "noappr": noappr, "partial_build": partial_build, "partial_manifest": partial_manifest,
        "revival_gate": revival_gate, "clean_build": clean_build, "clean_manifest": clean_manifest,
        "base": base, "data": data, "state": state, "out": out, "stage": stage,
    }
```

文件末尾追加测试类：

```python
class TestPartialDelivery:
    """--allow-partial 分级交付（spec §5.2②）：无批准拒 / 批准后放行 / manifest 逐章留痕 / 复活后干净终验。"""

    def test_without_approval_refused(self, ctrl):
        assert "未获用户批准" in ctrl["noappr"].stderr and "approve-downgrade" in ctrl["noappr"].stderr

    def test_final_next_routes_to_allow_partial(self, ctrl):
        assert "PHASE: FINAL" in ctrl["next5"] and "--allow-partial" in ctrl["next5"]

    def test_partial_build_ready_with_banner(self, ctrl):
        assert "BUILD_READY" in ctrl["partial_build"].stdout and "MANIFEST_READY" in ctrl["partial_build"].stdout
        assert "PARTIAL_DELIVERY" in ctrl["partial_build"].stdout and "ch2" in ctrl["partial_build"].stdout

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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_controller_build.py -v
```
Expected: TestPartialDelivery FAIL（`--allow-partial` 未实现——rc=2 unrecognized / noappr 断言炸）。

- [ ] **Step 3: 实现 --allow-partial**

build_output.py 新增两个 helper（放在 `assemble` 之后、`run_chapter_gate` 之前）：

```python
def load_progress(state_dir: Path) -> dict:
    """progress.json 装载（--allow-partial 前置：进度档案不在场=没走控制器流程，拒绝）。"""
    p = state_dir / "progress.json"
    if not p.exists():
        raise ValueError(f"{p} 不存在——分级交付需要 progress.py 建立的进度档案（先走步骤4 控制器流程）")
    return json.loads(p.read_text(encoding="utf-8"))


def approved_chapters(progress: dict) -> set[str]:
    out: set[str] = set()
    for a in progress.get("downgrade_approvals", []):
        out.update(a.get("chapters", []))
    return out


def _depth_row(ch_id: str, injected: str, targets: dict | None, downgraded: bool) -> dict:
    """交付清单逐章深度行（--allow-partial 留痕：达标章与降档章同表可见，差多少可查）。"""
    eff = effective_chars(injected)
    ch = (targets or {}).get("per_chapter", {}).get(ch_id)
    target_eff = ch.get("median_eff", 0) * (targets or {}).get("coefficient", 0.6) * coverage_scale(injected, targets or {}) if ch else 0
    return {"chapter": ch_id, "effective_chars": eff, "target": int(round(target_eff)), "ratio": round(eff / target_eff, 2) if target_eff > 0 else None, "status": "DOWNGRADED" if downgraded else "VERIFIED"}
```

`assemble` 循环体内、`validate_depth_target` 调用之后追加一行（`partial` 参数消费点）：

```python
            if partial is not None:
                partial.setdefault("chapter_depth", []).append(_depth_row(ch_id, injected, targets, bool(skip_l2 and ch_id in skip_l2)))
```

`main()` 的 try 块中，交付名门/散文件门通过之后、`assemble` 调用之前插入：

```python
        partial: dict | None = None
        skip_l2: set[str] = set()
        if args.allow_partial:
            progress = load_progress(Path(args.state_dir))
            blocked = {c for c, s in progress.get("chapters", {}).items() if s.get("status") == "BLOCKED"}
            unapproved = blocked - approved_chapters(progress)
            if unapproved:
                print(f"[build] 分级交付 FAIL: BLOCKED 章未获用户批准: {sorted(unapproved)}——先走协商（progress.py next 指引）；批准: progress.py approve-downgrade --chapters {','.join(sorted(unapproved))} --note \"<用户批准依据>\"", file=sys.stderr)
                return EXIT_ERROR
            skip_l2 = blocked  # 只放行 L2；L0/L1/toc/槽位门在场；产物缺失章仍由 assemble 硬 FAIL（含 PENDING 未派发）
            partial = {"downgrade_approvals": progress.get("downgrade_approvals", []), "chapter_depth": [], "downgraded": sorted(blocked)}
        content, toc_stats = assemble(stage, Path(args.data_dir), Path(args.state_dir), targets=targets, skip_l2=skip_l2 or None, partial=partial)
```

（原 `content, toc_stats = assemble(...)` 行替换为上面最后两行。）

manifest 构造之后追加：

```python
    if partial is not None:
        manifest["partial"] = partial  # 仅 --allow-partial 模式加 → 全量 build manifest 字节不变
```

`MANIFEST_READY` 打印行之后追加：

```python
    if partial is not None:
        print(f"PARTIAL_DELIVERY: 分级交付 {len(partial['downgraded'])} 章降档 {partial['downgraded']}（深度未达标明细见 delivery_manifest.json → partial.chapter_depth，交付时向用户如实汇报）")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geo_controller_build.py -v
```
Expected: 14 passed（TestChapterGate 5 + TestControllerFlow 4 + TestPartialDelivery 5）。

- [ ] **Step 5: 既有回归 + ruff + 提交**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_e2e_full.py tests/test_geo_progress.py -v
cd backend && uv run ruff check --config ruff.toml ../skills/public/geological-report/scripts/build_output.py
git add skills/public/geological-report/scripts/build_output.py backend/tests/test_geo_controller_build.py
git commit -m "feat(geo-skill): build_output --allow-partial 分级交付——批准集放行 BLOCKED 章 L2 门+manifest 逐章深度表留痕（D2 诚实部分交付终态）"
```

---

### Task 4: chapter_craft.md 迁移 + SKILL.md 步骤 4 派发协议重写

**Files:**
- Create: `skills/public/geological-report/references/chapter_craft.md`
- Modify: `skills/public/geological-report/SKILL.md`（步骤 4 整段替换 L83-101；工作区布局 state/ 行；步骤 5-7 build 行；命令速查表）
- Test: `backend/tests/test_geological_report_skill.py`（追加 TestControllerProtocol 类）

- [ ] **Step 1: 写失败测试（新断言类）**

`backend/tests/test_geological_report_skill.py` 末尾追加：

```python
class TestControllerProtocol:
    """步骤4 派发协议 presence（spec 2026-08-28 控制器化改造 §5.5）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_dispatch_protocol_keywords(self):
        for kw in ("派发协议", "控制器", "task(", "general-purpose", "≤3", "≤10 行摘要", "直写", "重派"):
            assert kw in self.content, kw

    def test_iron_law_and_excuse_reality(self):
        assert "Iron Law" in self.content and "Excuse" in self.content and "Reality" in self.content
        assert "approve-downgrade" in self.content

    def test_progress_commands_wired(self):
        assert "progress.py" in self.content and "confirm-key-points" in self.content

    def test_chapter_gate_and_partial_modes(self):
        assert "--chapter" in self.content and "--allow-partial" in self.content

    def test_key_points_state_file(self):
        assert "key_points.json" in self.content

    def test_chapter_craft_file(self):
        p = SKILL_DIR / "references" / "chapter_craft.md"
        assert p.exists(), "references/chapter_craft.md 未创建"
        t = p.read_text(encoding="utf-8")
        for kw in ("逐要素成段", "五步解读", "判定词", "条目式", "分节写作"):
            assert kw in t, kw
```

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_skill.py -v
```
Expected: 新类 6 个 FAIL（关键词缺席）。

- [ ] **Step 2: 创建 references/chapter_craft.md（完整文件）**

```markdown
# 章节写作工艺（chapter_craft.md）

> 供章节撰写子代理自读（派发 prompt 指向本文件）。主会话/控制器不需要读——工艺细节下沉于此，
> 控制器保持薄上下文（spec 2026-08-28 §5.4 渐进披露）。

## 结构规范

- 首行 `## N 章标题`，子节 `### N.M`，三级节 `#### N.M.K`；段内序号（1）（2）… 递增（NR2）
- 表/图先声明（caption）后引用，编号 `表8-2` 章内递增（NR1）
- 日期/项目名/勘查单位/许可证号与表单一致（NR3）；历史编码（332/333、B+C+D、111b/122b）原样保留（P4）
- 章节文件卫生（bug-2220）：严禁写入前置内容（外封面/签署页/目录/附图附表目录）或合规性附录——build_output 检测到脚本保留标题或首行非 `## N` 即 FAIL

## 骨架全覆盖（bug-2221 根因①）

动笔前先读 STAGE 文件该章 `toc` 与 `sections`（逐节要素链），全部二、三级节逐一落笔，**每节按其 `elements` 逐要素成段**——要素链每个节点 ≥1 段完整专业叙述（定性描述+空间关系+工程意义）。某要素缺数据写 `[待确认]` 占位句（如「矿体平均厚度：[待确认]」）但**不砍段**；禁止删节、并节或以概要代替逐节展开；章成后对照 toc 自检无遗漏。复合条目（如「2.1 …（2.1.1 … / 2.1.2 …）」）拆出的子节号也须逐个落 `####` 标题，缺失任一节号 build_output 以目录覆盖门 exit 1 拦截（bug-2225）。

## 叙述深度下限（bug-2221 根因②）

- 每个三级节 ≥1 段完整叙述（≥3 句）
- 每张表前有引入段、表后**五步解读**——陈述→规律识别→成因解释→规范对比→勘查意义（规范对比只引 `references/standards_index.json` 实有编号，禁凭记忆写条款号）——禁「表后即下一节」

## 条目式叙述范式（bug-2221 根因③）

逐条目分述（矿体/含水层/岩组/块段等）时**每条一段完整专业叙述**，按要素链成文：产出层位/位置 → 中段/勘探线等工程控制 → 形态产状 → 走向/倾向延伸 → 厚度区间+变化系数+稳定型判定 → 品位区间+变化系数+均匀型判定 → 含矿岩性+矿物组合+产出状态 → 资源量占比/结论；某要素缺数据写 `[待确认]` 不砍句。

## 数值与判定词

- 一切数字用 `{{SLOT:key}}`（key ∈ formula_state.values）；数据表用 `{{TABLE:fam}}`；**真数永不经过撰写者**（零数值漂移，比冻结快照更强）
- 判定词（水文/工程/复合类型等 type_verdicts 值）**逐字**写入正文（XS3）

## 动笔前读深度目标（bug-2221 根治）

写每章前读 `references/depth_targets.json` 该章 `median_eff`/`median_table_rows`/`median_paragraphs`，以此为篇幅下限自检；build_output 深度目标门兜底（eff ≥ 样例 median × 0.6 × 覆盖缩放，FAIL exit 1）。缺数写 `[待确认]` 不砍段，数据覆盖不足时门自动放宽目标。**深度基准只认技能自带 references/depth_targets.json**——绝不传 `--targets` 换基准、绝不自造/改写 depth_targets 文件、绝不绕过 build_output 直调 assemble（线程 03e18e4a 死循环取证：伪造基准+直调绕门 → 熔断）。门 FAIL 的唯一合法出路=补写正文。

## 大章分节写作指引（ch6 等最大目标章）

目标 10k+ eff 字符的大章按 toc 分节推进：每节独立达到该节叙事完整（引入+要素+解读）再进下一节；表格式内容（样品分析/工程一览）优先 `{{TABLE:fam}}` 承载数据、正文承载解读；避免全文铺陈后集中补深度。

## 范文与检索（仅范式，禁抄）

动笔前读 `references/samples/exploration/chN_sample.md` 同章范文——只学叙述范式（要素组织成段的方式/专业表述/表格用法），仿写而非摘抄。范文中任何数值/矿名/地名是样例项目的，一律不得进入本项目正文。检索补充（如可用）：harness 工具 `knowledge_search`（本地 RAGFlow，固体矿产报告知识库 / ragflow-laws-standards 等 5 库）；chunk 同样仅限叙述范式，矿名/地名/数值禁入正文，规范引用只从 standards_index 实有编号（ragflow-laws-standards 条文 chunk 仅作人工核实线索，禁直接引条款号）。
```

- [ ] **Step 3: 重写 SKILL.md**

四处修改（Edit 精确替换）：

**① 工作区布局 state/ 行**（原 L39）替换为：

```
  state/    # formula_state.json / chapter_manifest.json / chapters/chN.md / consistency_check.json
            #         progress.json（步骤4 控制器唯一事实源）/ key_points.json（波间要点包）
```

**② 步骤 4 整段替换**（原「### 步骤 4 · 两波生成（LLM 只写叙述）」至「**wave2（ch10 结论）**：只依据要点包写投影式结论，不引入任何 wave1 之外的新数字。」整段）：

```markdown
### 步骤 4 · 派发协议（wave1 全扇出 + wave2 结论，控制器模式）

主会话是**控制器**：薄上下文，只协调——读进度、派发、跑门、记账，**不亲自写章**。章节写作全部走 `task()` 子代理（单上下文写不动 10 章 × 1k-6k 有效字符——薄初稿是 03e18e4a 死循环起点）。

**Iron Law（门 FAIL 的唯一合法出路）**

```
门 FAIL 只有两条合法出路：补写正文、申请用户降档。
编辑 references/ 或绕过 build_output CLI = 伪造基准，直接违反本技能红线。
```

**Excuse | Reality（03e18e4a 死循环逐字取证）**

| Excuse | Reality |
|---|---|
| 「median_eff 目标不合理，我调一下基准」 | 基准=合同。唯一合法变更=用户批准 + `progress.py approve-downgrade` 留痕 |
| 「直接调 assemble() 更快」 | 直调已被脚本拒（强制真基准）；CLI 是唯一门 |
| 「先跑通全流程，深度后面再补」 | 薄初稿是 03e18e4a 死循环起点；每章写够再进下一章 |
| 「一次修一章跑一轮 build」 | 单章门 `--chapter N` 即时验；终验一次报齐 |
| 「摘要里说这章写完了」 | 只信 state/chapters/*.md + progress.json，不信对话记忆 |

**Red Flags**：发现自己在编辑 references/、自造 depth_targets、想跳过单章门直跑终验、重派同一章第 3 次 → STOP，回协商表单。

**4.0 初始化**：`progress.py init --stage S --state-dir T --data-dir D`（progress.json 全 PENDING；已存在=续跑，直接 `progress.py next`）。此后每轮动作由 `progress.py next` 决定——它输出**恰好一个**下一步（动作+精确命令+期望 rc），照做，不自创顺序、不跳步。

**4.1 派发契约**（每个 PENDING 章一次；重派=原 prompt 原文 + 门 stderr 原文，**不重新组装**——防逐次漂移）：

```
角色：第 N 章撰写者，只产出这一章
自读输入（沙箱路径，不贴全文）：
  state/formula_state.json（槽位词汇表——正文数值只写 {{SLOT:key}}）
  /mnt/skills/public/geological-report/references/chapter_craft.md（写作工艺，必读）
  /mnt/skills/public/geological-report/references/samples/exploration/chN_sample.md（同章范文）
  /mnt/skills/public/geological-report/references/depth_targets.json（该章深度目标）
  本章切片（title + toc，直接贴）
输出契约：直写 state/chapters/chN.md（绝对沙箱路径），首行 ## N，缺数标 [待确认]/[数据未提供]
返回：≤10 行摘要（结构 / [待确认] 清单 / 数据缺口 / 本章要点 3-5 条——供要点包蒸馏）
禁令：不改 data/、不碰 references/、不跑 build、不派 task
```

- `subagent_type="general-purpose"`；每轮 **≤3 个并发 task()**（超发被运行时静默丢弃）；总派发 ≤16（config 额度）
- 写作工艺（逐要素成段 / 表后五步解读 / 条目式叙述 / 动笔前读深度目标——缺数写 [待确认] 不砍段）在 `references/chapter_craft.md`——派发 prompt 已指向，子代理自读；主会话不读它（薄上下文）
- 范文与检索红线（随派发契约注入）：范文只学范式禁抄；范文中任何数值/矿名/地名不得进入本项目正文（本项目数值只经 `{{SLOT:key}}`）。可用 harness 工具 `knowledge_search`（本地 RAGFlow 检索，已配置 固体矿产报告知识库 / ragflow-laws-standards 等 5 库）检索同章叙述参考；chunk 同样仅限叙述范式，矿名/地名/数值禁入正文，规范引用仍只从 standards_index 实有编号（ragflow-laws-standards 条文 chunk 仅作人工核实线索，禁直接引条款号）

**4.2 收章跑门（只信产物，不信摘要）**：子代理返回后 `mark chN DRAFTED`，随即跑单章门
`build_output.py --stage S --data-dir D --state-dir T --chapter chN`
rc=0 → `mark chN VERIFIED --gate PASS`；rc=1（含深度目标门 FAIL）→ 原 prompt + stderr 重派（**每章 ≤1 次**）→ 仍 FAIL → `mark chN BLOCKED --gate FAIL --detail "<一句话差距>"`。单章失败不中断全书，继续 next。

**4.3 波间要点包（wave1 全收口后）**：`next` 进入 KEY_POINTS——聚合各子代理摘要的「本章要点 3-5 条」+ formula_state 关键结论数字（L9 总量/分类量、L10 对比、E 链经济指标）写 `state/key_points.json`（`{"chapters":{...},"highlights":{...},"issues":[...]}`），单表单 `ask_clarification` 呈现用户确认（单回合至多一次）→ `progress.py confirm-key-points`。**要点包 = ch10 唯一事实来源**（不重读 9 章全文）。

**4.4 wave2（ch10 结论）**：`next` 指引派发 ch10（派发契约同 4.1，自读输入追加 state/key_points.json）——只依据要点包写投影式结论，不引入任何 wave1 之外的新数字 → 单章门 → VERIFIED。

**4.5 协商（存在 BLOCKED 时）**：`next` 进入 NEGOTIATE——差距表（章/实际 eff/目标/缺口）单表单三选项：① 补数据（回 ingest → formula_runner → 相关章 mark DRAFTED 重派）② 批准降档（`progress.py approve-downgrade --chapters … --note "…"`）③ [待确认] 收尾（缺数信号放宽覆盖缩放，重写即可能达标）。用户不回表单就停在那，不推进。
```

**③ 步骤 5-7 的 build 行**（原「build_output.py   → outputs/…」行）后追加说明行：

```
（存在已批准降档时终验加 --allow-partial：stdout PARTIAL_DELIVERY + manifest partial 留痕，
 交付时向用户如实汇报降档章节与差距——诚实部分交付，D2）
```

**④ 命令速查表**：build_output 行替换 + 追加 5 行 progress.py：

```
| `build_output.py --stage S --data-dir D --state-dir T --chapter chN` | **单章门**：该章全门即时验（一次报齐；不产交付物/不写 progress） | 0=CHAPTER_GATE_PASS / 1 门拦 |
| `build_output.py --stage S --data-dir D --state-dir T --output R [--allow-partial] [--targets P]` | 原子组装+槽位注入+深度目标门（一次报齐）；--allow-partial=分级交付（progress 批准集放行 BLOCKED 章 L2 门，manifest 留痕）；--targets 仅限调试，正式交付绝不传 | 0（BUILD_READY+MANIFEST_READY）/ 1 门拦 |
| `progress.py init --stage S --state-dir T [--data-dir D]` | 章节进度状态机初始化（全 PENDING；已存在=续跑拒重置） | 0 / 1 已存在 |
| `progress.py next --state-dir T` | **控制器每轮先读**：恰好一个下一步动作+精确命令+期望 rc | 0 |
| `progress.py mark chN DRAFTED\|VERIFIED\|BLOCKED [--gate PASS\|FAIL] [--detail …]` | 状态转移+派发记账（VERIFIED 必带 --gate PASS；DRAFTED 记一次派发） | 0 / 1 非法转移 |
| `progress.py confirm-key-points --state-dir T` | 要点包已经用户单表单确认（解锁 ch10） | 0 |
| `progress.py approve-downgrade --state-dir T --chapters ch3,ch8 --note "…"` | 用户批准降档留痕（--allow-partial 放行凭据） | 0 / 1 未知章 |
```

**frontmatter `description` 不动**（触发式匹配面，CSO 陷阱）。

- [ ] **Step 4: 跑测试确认通过（新断言 + 既有结构锁全绿）**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_skill.py -v
```
Expected: 全绿——新 TestControllerProtocol 6 passed；既有断言（wave1/wave2/要点包/逐要素成段/五步解读/动笔前读深度目标/depth_targets.json/深度目标门/不砍段/knowledge_search 600 字符窗口含 矿名/地名+standards_index/六脚本速查/--targets/交付铁律）全部仍在场。

若 `test_knowledge_search_wiring` 失败：检查 4.1 检索红线 bullet——首个 `knowledge_search` 出现后 600 字符内必须同时有「矿名/地名」与「standards_index」。

- [ ] **Step 5: 提交**

```bash
git add skills/public/geological-report/SKILL.md skills/public/geological-report/references/chapter_craft.md backend/tests/test_geological_report_skill.py
git commit -m "feat(geo-skill): SKILL.md 步骤4 重写为派发协议（控制器/task() 扇出/单章门/要点包/降档协商）+ 写作工艺下沉 chapter_craft.md + Iron Law/Excuse|Reality 反合理化表"
```

---

### Task 5: config.yaml 派发提额 + 全量回归

**Files:**
- Modify: `config.yaml`（活动 `subagents:` 块，约 L1622）

- [ ] **Step 1: config.yaml 提额**

在活动块 `subagents:`（EAI-CUSTOM 注释行之下、`custom_agents:` 之前）插入：

```yaml
subagents:
  # EAI-CUSTOM: geological-report 步骤4 控制器全扇出需 10 初派+重派余量（默认 6 不够；clamp [1,50]，
  # per-run 热加载——改完下一条消息生效）。设计: docs/superpowers/specs/2026-08-28-geo-skill-controller-design.md §5.6
  max_total_per_run: 16
  custom_agents:
    ……（原内容不动）
```

验证（热加载不重启）：

```bash
docker compose -p eai-docker logs --tail 5 gateway
python -X utf8 -c "import yaml,io; d=yaml.safe_load(io.open('config.yaml',encoding='utf-8')); print(d['subagents']['max_total_per_run'])"
```
Expected: `16`。

- [ ] **Step 2: 全量 geo 回归（118 既有 + 新增全部）**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_e2e_full.py tests/test_geological_report_skill.py tests/test_geo_progress.py tests/test_geo_controller_build.py -v
```
Expected: 全绿（既有 0 回归 + 新 ~40 例：test_geo_progress 20 + test_geo_controller_build 14 + test_geological_report_skill 新增 6）。

- [ ] **Step 3: 提交**

```bash
git add config.yaml
git commit -m "feat(geo-skill): config subagents.max_total_per_run 6→16——控制器全扇出派发额度（EAI-CUSTOM，热加载）"
```

---

### Task 6: 页面测试交接（用户执行，真验收）

**Files:** 无代码改动；产出观测记录。

- [ ] **Step 1: 前置确认（agent 做）**

```bash
docker compose -p eai-docker ps   # gateway/frontend/nginx Up
```
确认 config.yaml 已提额（Task 5）；废弃旧线程 03e18e4a（不复用——其 data/state 是三门硬化前产物）。

- [ ] **Step 2: 请用户执行页面测试（agent 交接话术要点）**

- 新建线程，按 `backend/tests/fixtures/geological_report/e2e-full/README.md` §0「直接灌数据」路径上传数据包。
- 说一句话触发技能：「请编写固体矿产地质勘查报告（详查阶段）」。
- 观察点（D1 成功标准=可靠跑通+少量问询）：
  1. 步骤 1-3 与既有行为一致（开题三件套/单表单节奏/GATE1/门2 anomalies 呈现）；
  2. 步骤 4 是否真走控制器：跑 `progress.py init` → 每轮读 `next` → **每轮 ≤3 个 task() 并发** → 收章跑 `--chapter` 门 → `mark`（浏览器里子代理事件流可见 task_started/task_completed 成组出现）；
  3. 薄章 FAIL 时是否走重派（≤1 次）→ BLOCKED → 单表单协商（**不是**调基准/直调 assemble/循环 build——那些已在 03e18e4a 出现过，复发=设计失败）；
  4. 工具调用总量：全程无 60 次 bash 熔断、无 FORCED STOP、无 GraphRecursionError；
  5. 终态：BUILD_READY（全绿）或 PARTIAL_DELIVERY（降档且 manifest 留痕）+ present_files 交付唯一单文件。
- 用户跑测期间 agent 可挂监控：gateway 日志 grep FORCED STOP / GraphRecursionError。

- [ ] **Step 3: 收尾（agent 做）**

- 更新 `.wolf/anatomy.md`（新增 progress.py / chapter_craft.md / 两个测试文件条目）+ `.wolf/memory.md` 会话摘要。
- 页面测试若暴露 agent 依从性问题（不照轮次/不真派发/照抄 prompt 外内容），记录到 `.wolf/buglog.json` 并回 spec §8「诚实盲区」——协议措辞迭代，不动脚本门。

---

## 执行期勘误（controller 裁定）

1. **Task 1 TRANSITIONS 表（2026-08-28，实施时发现）**：计划正文的 `TRANSITIONS["PENDING"] = {"DRAFTED","BLOCKED"}` 与计划测试 `test_verified_requires_gate_pass` / `test_illegal_transition_refused`（均从 PENDING 直接 mark VERIFIED）自相矛盾——按原表两测必 FAIL。裁定取测试语义：`"PENDING": {"DRAFTED", "VERIFIED", "BLOCKED"}`（PENDING→VERIFIED = 记账滞后凭门 PASS 补记，仍强制 `--gate PASS`，"只信产物" 不变量不变；spec §5.1 未枚举转移表，不构成 spec 偏离）。
2. **Task 1 质量评审追加（2026-08-28）**：`main()` 异常捕获从 `json.JSONDecodeError` 扩为 `(json.JSONDecodeError, KeyError, TypeError, OSError)` 统一诊断行（手改 progress.json / stage 缺文件不再裸 traceback）；DISPATCH_BUDGET 加"展示与 WAVE1 路由提示、硬执行在 harness"注释。另裁定**有意语义**：wave1 章 VERIFIED→DRAFTED 修改回路不重置 `key_points_confirmed`——章节散文编辑不改槽位值（数字只来自 formula_state），不为局部修补强制 ch10 重写。
3. **Task 2 质量评审追加（2026-08-28）**：`run_chapter_gate` 补 `targets=None → load_targets(CANONICAL_TARGETS)` 防绕钳制（对齐 assemble，03e18e4a 直调教训）；两处五步门序列加同步改注释；删测试死常量 `_THIN`。**裁定拒绝**（YAGNI）：`validate_chapter_block` 五步序列合并重构——两消费点 ~8 行且均有测试锚，刚双重认证过的门不再动；若页面测试暴露门漂移再议。
4. **Task 3 质量评审追加（2026-08-29）**：`load_progress`/`approved_chapters` 补手改形状校验（chapters 非字典 / downgrade_approvals 为 null / 条目非字符串列表 → `[build] 错误:` 手改特征诊断行而非裸 traceback，对齐 progress.py 四类捕获惯例；评审六种对抗形状全闭）；目标公式三处（validate_depth_target / _depth_row / run_chapter_gate PASS 行）加同步改注释（**裁定拒绝**抽取共享函数——门代码刚双重认证不再动）；`PARTIAL_DELIVERY` 断言收紧为 `1 章降档 ['ch2']`；新增 2 个对抗形状回归测试（TestPartialDelivery 7 测）。批准偏差：拒绝消息经 `msg` 变量过 E501（内容等价）；return 字典 ruff 逐行规范化；消费点一行内联注释。
5. **Task 4 目录覆盖门关键词冲突（2026-08-29，实施时发现）**：既有测试 `TestDeliveryIronLaw.test_toc_gate_script_enforced` 断言 SKILL.md 含 `目录覆盖门`，而计划的替换块恰好删除其在 SKILL.md 的两处出现（L87 骨架全覆盖 bullet 随步骤4 整段删除；L142 速查表 build_output 行被替换）——与计划自己的"既有断言全绿"要求自相矛盾（计划断言枚举漏列此项）。裁定取方案 (a)：速查表全量 build 行出口单元格恢复门枚举 `0（BUILD_READY+MANIFEST_READY）/ 1 门拦（未知槽位/目录覆盖门/深度目标门，一次报齐）`——测试保绿、无计划内容损失、行信息更完整。另批准真签名修正：速查表 `mark` 行补必填 `--state-dir T`（实施者以 `--help` 实测 progress.py argparse 为准）。
6. **Task 4 质量评审追加（2026-08-29）**：①**C1 派发契约路径锚定（Critical）**——子代理 bash 被 `cd /mnt/user-data/workspace; <cmd>` 包裹（sandbox/tools.py），契约内相对 `state/` 路径解析到 workspace 根而非 `geo-report/state/`，输出会静默写错目录且重派防漂移规则确定性复现同一错误 → 契约四处（4.1 formula_state 自读/chN.md 输出、4.3 key_points 写、4.4 追加自读）全改绝对路径 `/mnt/user-data/workspace/geo-report/state/...`，并加关键词断言 `/mnt/user-data/workspace/geo-report/state` 钉死该回归类。②契约自读清单补 `references/stages/<S>.json`（chapter_craft 骨架全覆盖要求读 sections 要素链但契约只贴 title+toc——逐要素成段不可执行且无门可检）；③4.3 补 confirm-key-points 停机条件（自 confirm=伪造用户确认）+Red Flags 加条目；④4.1 补额度拒绝处置 bullet（SUBAGENT LIMIT REACHED ≠ 亲写许可——正面对冲 SubagentLimitMiddleware 停止消息里"自己直接完成剩余工作"的建议）；⑤4.4 补门 FAIL 分支、4.3 标题补"无待协商 BLOCKED 时"（对齐 derive_phase 的 NEGOTIATE 优先序）。评审确认：4.0-4.5 对真实状态机全路由可执行（live walkthrough）；"BLOCKED 时擅自终验"已被脚本层关死（--allow-partial 无批准即 FAIL）。

## Self-Review 记录（写完计划后已核对）

1. **Spec 覆盖**：§5.1 progress.py→Task 1；§5.2 --chapter/--allow-partial→Task 2/3；§5.3 key_points.json→Task 1（progress 命令）+Task 4（4.3 流程+测试断言）；§5.4 chapter_craft.md→Task 4；§5.5 SKILL.md 五要素+Iron Law+Excuse|Reality+Red Flags→Task 4；§5.6 config 提额→Task 5；§5.7 snapshot 哈希→Task 1 TestSnapshotCoverage（rglob 零改码，测试锁定）；§6 派发契约模板→Task 4.1（内嵌 SKILL.md，不另立文件）；§7 错误矩阵→Task 1（预算/转移拒）+Task 2（缺章/手改/伪槽位探针）+Task 4（Excuse|Reality）；§8 测试策略→Task 1/2/3/5/6 各层；§9 六步切分→Task 1-6 一一对应。
2. **占位符扫描**：无 TBD/TODO；每个代码步骤给完整文件或精确 Edit 块；命令带期望输出。
3. **类型一致性**：`assemble(stage, data_dir, state_dir, targets=None, skip_l2=None, partial=None)` 在 Task 2 定义、Task 3 消费；`run_chapter_gate(stage, data_dir, state_dir, ch_id, targets)` Task 2 定义即用；progress.py 的 `TRANSITIONS/derive_phase/next_action/approved_set` 与测试断言的状态字面量逐一核对（PENDING/DRAFTED/VERIFIED/BLOCKED、WAVE1/KEY_POINTS/WAVE2/NEGOTIATE/FINAL）；`partial` dict 形状（downgrade_approvals/chapter_depth/downgraded）与 Task 3 测试断言一致；`_depth_row` 键名（chapter/effective_chars/target/ratio/status）与 manifest 断言一致。
4. **兼容性**：`test_geological_report_v2_scripts.py:783` 位置调用 assemble——新参数全默认值；全量 build manifest 不加 partial 键（字节不变，SC-4 幂等锚保持）；snapshot.py 零改码。


