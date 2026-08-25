# geological-report 深度增强 Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec `docs/superpowers/specs/2026-08-25-geological-report-depth-design.md` Phase 1——L2 深度目标门（样例基线 × 系数 × 覆盖缩放）+ calibrate 校准脚本 + SKILL.md 范式升级（逐要素成段/表后五步解读/动笔前读目标）+ 数据预告。

**Architecture:** 全部改动落在 skill 层（`skills/public/geological-report/`）+ 既有测试文件，零 harness/app 改动。门公式：`signals = count("[待确认]") + 8×count("数据未提供")`；`scale = max(0.25, 1 − 0.05×signals)`；FAIL ⟺ `effective_chars(inject后章节文本) < median_eff × 0.6 × scale`。门插在 assemble 循环 inject 之后（量的是注入后叙述文本；表格行/标题本就不计入 eff）。`--targets` 缺省时沿 stage 文件向上三级探测 `depth_targets.json`，缺失/损坏 → stderr「退回地板门」继续跑不阻断。

**Tech Stack:** Python 3.12 stdlib（argparse/json/statistics/re），无新依赖。测试扩既有 `backend/tests/test_geological_report_v2_scripts.py`、`test_geological_report_bug2223.py`、`test_geological_report_skill.py`。

---

## 关键背景（执行者必读）

1. **口径单一来源**：`effective_chars`（排除空行/标题行/表格行，行内剔除 `[\s\|\-*#:{}]`）现以内联表达式写在 `build_output.py` L201 的 `validate_depth` 里。Task 1 抽成模块级函数，calibrate.py 与深度目标门共用——三个统计口径必须逐字符相同。
2. **测试污染问题（本计划最大的坑）**：Task 4 会提交真实 `references/depth_targets.json`（ch6 median_eff≈17370）。此后任何**不传** `--targets` 的 build_output 调用都会探测命中它——而两个测试文件的合成章节（~1500 eff chars）会被真实目标全数拦截，~30 个既有测试红灯。**解法**：Task 3 与门同一提交里，给两个测试文件的 `run()` 助手注入 permissive targets（median 全 1 → 目标 <1 必过），3 处裸 subprocess 调用显式补 `--targets`。Task 4 落真实 targets 时测试已免疫。
3. **门层级**：L0 地板 `validate_depth`（≥3句/节、1000字/章）与 L1 结构门（toc 覆盖/章节卫生/槽位完整）**保留不动**；L2 是新增的最后一道，循环顺序：validate_chapter → validate_depth(L0) → validate_toc(L1) → inject → **validate_depth_target(L2)** → append。
4. **Phase 2 兼容**：calibrate 输出字段名第一天就叫 `median_*` 并按章聚合多份样例取中位数（Phase 1 每章 1 份，median=值本身）。
5. **测试跑法**（Windows host，backend 目录）：`PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py -v`。python 一律 `-X utf8`。
6. **红线**：提交全部 main-dev-fork、**严禁 `git add -A`**（~40 并发会话），永远 explicit pathspec；报告红线（数字不经 LLM/[待确认] 占位/崩溃即停/样例数值禁入正文）不受本计划影响；交付面（bug-2225 契约标记/manifest/present_files/artifacts 三门）零改动。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `skills/public/geological-report/scripts/build_output.py` | 改 | 抽 `effective_chars`；新增 `coverage_scale`/`validate_depth_target`/`load_targets`/`resolve_targets`；`--targets` 参数；assemble 接线 |
| `skills/public/geological-report/scripts/calibrate.py` | 新建 | 样例目录 → depth_targets.json（确定性幂等） |
| `skills/public/geological-report/references/depth_targets.json` | 新建(生成) | calibrate 对真实 10 章样例的产物 |
| `skills/public/geological-report/references/data_expectations.json` | 新建(手写) | 按章数据预告（族清单 + CSV 列样例） |
| `skills/public/geological-report/SKILL.md` | 改 | 步骤1 数据预告；步骤4 三处范式升级；命令速查 2 行 |
| `backend/tests/test_geological_report_v2_scripts.py` | 改 | effective_chars/calibrate/L2 门/data_expectations/真实 targets 结构测试；run() 注入 |
| `backend/tests/test_geological_report_bug2223.py` | 改 | run() 注入（防 L2 截胡既有负例） |
| `backend/tests/test_geological_report_skill.py` | 改 | SKILL.md presence 断言 |

---

### Task 1: 抽取 effective_chars（纯重构，零行为变化）

**Files:**
- Modify: `skills/public/geological-report/scripts/build_output.py:180-203`
- Test: `backend/tests/test_geological_report_v2_scripts.py`

- [ ] **Step 1.1: 写失败测试** — 在 `test_geological_report_v2_scripts.py` 的 `TestBuildOutput` 类之前插入：

```python
class TestEffectiveChars:
    """eff 口径单一来源：标题行/表格行/装饰符剔除（calibrate 与 L0/L2 门共用）。"""

    def test_excludes_headings_tables_and_decorations(self):
        import build_output

        text = "## 1 绪论\n\n正文第一句。正文第二句；正文第三句！\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- 要点：符号-与*#:{}剔除\n"
        # 18 = 三句正文（。；！ 保留）；8 = 「要点：符号与剔除」（全角：保留，ASCII - * # : { } 与空白剔除）
        assert build_output.effective_chars(text) == 26
```

- [ ] **Step 1.2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestEffectiveChars -v`
Expected: FAIL `AttributeError: module 'build_output' has no attribute 'effective_chars'`

- [ ] **Step 1.3: 实现** — `build_output.py` 中，在 `def validate_depth(...)`（L180）之前加模块级函数，并把 validate_depth 内 L201 的内联表达式改为调用它：

```python
def effective_chars(text: str) -> int:
    """有效字符数：排除空行/标题行/表格行，行内剔除空白与 |\\-*#:{} 装饰符。"""
    return sum(
        len(re.sub(r"[\s\|\-*#:{}]", "", line))
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("|") and not line.strip().startswith("#")
    )
```

L201 原：
```python
    eff = sum(len(re.sub(r"[\s\|\-*#:{}]", "", l)) for l in text.splitlines() if l.strip() and not l.strip().startswith("|") and not l.strip().startswith("#"))
```
改为：
```python
    eff = effective_chars(text)
```

- [ ] **Step 1.4: 跑新旧测试确认全绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_bug2223.py -v`
Expected: 全 PASS（既有 TestDepthGate 数字回归不变——同一表达式的机械搬移）

- [ ] **Step 1.5: Commit**

```bash
git add skills/public/geological-report/scripts/build_output.py backend/tests/test_geological_report_v2_scripts.py
git commit -m "refactor(geo-skill): 抽取 effective_chars 模块级函数——L0/L2 门与 calibrate 共用口径"
```

---

### Task 2: calibrate.py 校准脚本 + 测试

**Files:**
- Create: `skills/public/geological-report/scripts/calibrate.py`
- Test: `backend/tests/test_geological_report_v2_scripts.py`

- [ ] **Step 2.1: 写失败测试** — 在 v2_scripts 追加（本任务只测 mini fixture，真实 targets 由 Task 4 生成）：

```python
class TestCalibrate:
    """calibrate.py：样例 → depth_targets.json（确定性幂等；无节号样例 rc=1 拒产）。"""

    @staticmethod
    def _mini_samples(base):
        d = base / "samples"
        d.mkdir()
        (d / "ch1_sample.md").write_text(
            "## 1 绪论\n\n### 1.1 目的任务\n\n本次勘查目的明确。任务安排合理。经费保障到位。\n\n| 项目 | 数量 |\n|---|---|\n| 钻探 | 1000 |\n",
            encoding="utf-8",
        )
        (d / "ch2_sample.md").write_text("## 2 区域地质\n\n### 2.1 地层\n\n区域地层出露齐全。由老至新分述。各岩性组特征各异。\n", encoding="utf-8")
        (d / "source.md").write_text("来源说明，非样例，须被过滤。\n", encoding="utf-8")
        return d

    @staticmethod
    def _run(*argv):
        return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "calibrate.py"), *map(str, argv)], capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_mini_targets_deterministic(self, tmp_path):
        d = self._mini_samples(tmp_path)
        out1, out2 = tmp_path / "t1.json", tmp_path / "t2.json"
        for out in (out1, out2):
            r = self._run("--samples-dir", d, "--output", out)
            assert r.returncode == 0, r.stderr
        assert out1.read_bytes() == out2.read_bytes()
        doc = json.loads(out1.read_text(encoding="utf-8"))
        assert (doc["coefficient"], doc["scale_floor"], doc["per_signal_penalty"], doc["missing_table_weight"]) == (0.6, 0.25, 0.05, 8)
        assert set(doc["per_chapter"]) == {"ch1", "ch2"}  # source.md 被过滤
        assert doc["per_chapter"]["ch1"] == {"median_eff": 23, "median_table_rows": 2, "median_paragraphs": 1}
        assert doc["per_chapter"]["ch2"] == {"median_eff": 25, "median_table_rows": 0, "median_paragraphs": 1}

    def test_sample_without_numbered_headings_rc1(self, tmp_path):
        d = tmp_path / "samples"
        d.mkdir()
        (d / "ch1_sample.md").write_text("# 概述\n\n没有节号标题的文档。\n", encoding="utf-8")
        r = self._run("--samples-dir", d, "--output", tmp_path / "t.json")
        assert r.returncode == 1 and "ch1_sample.md" in r.stderr, r.stderr
        assert not (tmp_path / "t.json").exists()  # 绝不静默产出空 targets
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestCalibrate -v`
Expected: FAIL（`calibrate.py` 不存在，rc≠0 / FileNotFoundError）

- [ ] **Step 2.3: 实现 calibrate.py 全文**：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate.py — 从样例章节统计深度基线，生成 depth_targets.json（深度目标门的 targets）。

用法：
    python -X utf8 calibrate.py --samples-dir ../references/samples/exploration --output ../references/depth_targets.json

- 样例文件命名 chN*.md（同章多样例 chN_a.md/chN_b.md，按章聚中位数；Phase 1 每章 1 份）。
- 非 chN 开头的 .md（如 source.md）自动过滤。
- 输出确定性幂等：sort_keys、无时间戳——同输入必同字节。
- 样例缺节号标题 → rc=1 绝不静默产出空 targets（维护者脚本，崩溃即停）。
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from build_output import effective_chars

FNAME_RE = re.compile(r"^ch(\d+)")
SAMPLE_NO_RE = re.compile(r"^#{2,4}\s+\d+(?:\.\d+)*\s", re.MULTILINE)
SEPARATOR_RE = re.compile(r"^\|[\s\-|:]+\|?$")


def chapter_stats(text: str) -> dict:
    """单份样例统计：eff（与 build 门同口径）/ 表行数（separator 不计）/ 叙述段落数。"""
    lines = text.splitlines()
    table_rows = sum(1 for l in lines if l.strip().startswith("|") and not SEPARATOR_RE.match(l.strip()))
    paragraphs, in_para = 0, False
    for l in lines:
        s = l.strip()
        narrative = bool(s) and not s.startswith("#") and not s.startswith("|")
        if narrative and not in_para:
            paragraphs += 1
        in_para = narrative
    return {"eff": effective_chars(text), "table_rows": table_rows, "paragraphs": paragraphs}


def main() -> int:
    ap = argparse.ArgumentParser(description="样例章节 → depth_targets.json 深度基线")
    ap.add_argument("--samples-dir", required=True, help="样例目录（chN*.md）")
    ap.add_argument("--output", required=True, help="depth_targets.json 输出路径")
    args = ap.parse_args()

    samples_dir = Path(args.samples_dir)
    if not samples_dir.is_dir():
        print(f"[calibrate] 样例目录不存在：{samples_dir}", file=sys.stderr)
        return 1

    files = sorted(p for p in samples_dir.glob("*.md") if FNAME_RE.match(p.name))
    grouped = defaultdict(list)
    for p in files:
        text = p.read_text(encoding="utf-8")
        if not SAMPLE_NO_RE.search(text):
            print(f"[calibrate] {p.name} 无节号标题（需 `## N …` / `### N.M …` 形式）——拒绝生成空基线", file=sys.stderr)
            return 1
        grouped[f"ch{FNAME_RE.match(p.name).group(1)}"].append(chapter_stats(text))

    if not grouped:
        print(f"[calibrate] {samples_dir} 下无 chN*.md 样例", file=sys.stderr)
        return 1

    per_chapter = {
        ch_id: {
            "median_eff": int(statistics.median(s["eff"] for s in stats)),
            "median_table_rows": int(statistics.median(s["table_rows"] for s in stats)),
            "median_paragraphs": int(statistics.median(s["paragraphs"] for s in stats)),
        }
        for ch_id, stats in sorted(grouped.items())
    }
    doc = {
        "coefficient": 0.6,
        "scale_floor": 0.25,
        "per_signal_penalty": 0.05,
        "missing_table_weight": 8,
        "samples": [p.name for p in files],
        "per_chapter": per_chapter,
    }
    out = Path(args.output)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"CALIBRATED: {len(per_chapter)} chapters -> {out}")
    for ch_id, c in per_chapter.items():
        print(f"  {ch_id}: median_eff={c['median_eff']} tables={c['median_table_rows']} paras={c['median_paragraphs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

注：`from build_output import effective_chars` 依赖同目录 import（脚本 sys.path[0] = scripts/），与 v2_scripts `sys.path.insert(0, str(SCRIPTS))` 同理。

- [ ] **Step 2.4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestCalibrate -v`
Expected: 2 PASS

- [ ] **Step 2.5: Commit**

```bash
git add skills/public/geological-report/scripts/calibrate.py backend/tests/test_geological_report_v2_scripts.py
git commit -m "feat(geo-skill): calibrate.py 样例→深度基线（median_eff/表行/段落，确定性幂等，无节号 rc=1）"
```

---

### Task 3: L2 深度目标门 + --targets 参数 + 测试免疫注入

**Files:**
- Modify: `skills/public/geological-report/scripts/build_output.py`
- Modify: `backend/tests/test_geological_report_v2_scripts.py`（run() 注入 + 3 处裸 subprocess + 新门测试）
- Modify: `backend/tests/test_geological_report_bug2223.py`（run() 注入）

- [ ] **Step 3.1: 写失败测试** — v2_scripts 追加：

```python
class TestDepthTargetGate:
    """L2 深度目标门（spec 2026-08-25 §4）：eff ≥ median×0.6×覆盖缩放；缺 targets 回退地板门。"""

    @staticmethod
    def _targets(tmp_path, ch="ch2", median_eff=999999):
        p = tmp_path / "tg.json"
        p.write_text(
            json.dumps({"coefficient": 0.6, "scale_floor": 0.25, "per_signal_penalty": 0.05, "missing_table_weight": 8,
                        "per_chapter": {ch: {"median_eff": median_eff, "median_table_rows": 0, "median_paragraphs": 1}}}, ensure_ascii=False),
            encoding="utf-8",
        )
        return p

    @staticmethod
    def _build(ws, st, out, targets=None):
        argv = [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE),
                "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(out)]
        if targets is not None:
            argv += ["--targets", str(targets)]
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_thin_chapter_fail(self, ws, tmp_path):
        """数据齐全但薄：scale=1，eff < median×0.6 → FAIL，报错含公式因子与覆盖缩放。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 999999))
        assert r.returncode == 1 and "深度目标门" in r.stderr and "覆盖缩放" in r.stderr, r.stderr

    def test_met_target_pass(self, ws, tmp_path):
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 100))
        assert r.returncode == 0 and "BUILD_READY" in r.stdout, r.stderr

    def test_missing_targets_fallback_floor(self, ws, tmp_path):
        """--targets 指向不存在文件 → stderr 退回地板门，继续跑成功（spec §8）。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], tmp_path / "nope.json")
        assert r.returncode == 0 and "BUILD_READY" in r.stdout
        assert "退回地板门" in r.stderr, r.stderr

    def test_missing_data_signals_scale_down_pass(self, ws, tmp_path):
        """缺数章（E2E 防误拦）：40×[待确认]+1×数据未提供 → 48 signals → scale 触底 0.25 → 目标 8000×0.6×0.25=1200 < eff → 放行。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        raw = (st / "chapters" / "ch2.md").read_text(encoding="utf-8")
        raw += "\n\n补充说明 [待确认] " * 40 + "\n（某族: 数据未提供——[待确认] 槽位，缺参不编造）\n"
        (st / "chapters" / "ch2.md").write_text(raw, encoding="utf-8")
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 8000))
        assert r.returncode == 0 and "BUILD_READY" in r.stdout, r.stderr

    def test_coverage_scale_floor_unit(self):
        import build_output

        t = {"scale_floor": 0.25, "per_signal_penalty": 0.05, "missing_table_weight": 8}
        assert build_output.coverage_scale("[待确认]" * 100, t) == 0.25
        assert build_output.coverage_scale("全数据完整叙述。", t) == 1.0
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestDepthTargetGate -v`
Expected: FAIL（`coverage_scale` 不存在 / `--targets` unrecognized argument）

- [ ] **Step 3.3: 实现 build_output.py 四个函数** — 插在 `def validate_toc(...)`（L212）之后、`def assemble(...)`（L230）之前：

```python
def coverage_scale(text: str, targets: dict) -> float:
    """覆盖缩放：缺数信号越多目标越低，下限 scale_floor（缺数章防误拦）。"""
    signals = text.count("[待确认]") + targets.get("missing_table_weight", 8) * text.count("数据未提供")
    return max(targets.get("scale_floor", 0.25), 1 - targets.get("per_signal_penalty", 0.05) * signals)


def validate_depth_target(ch_id: str, text: str, targets: dict) -> None:
    """L2 深度目标门：inject 后文本 eff ≥ 样例 median × coefficient × 覆盖缩放。"""
    ch = targets.get("per_chapter", {}).get(ch_id)
    if not ch:
        return  # targets 未覆盖该章 → 不拦（样例库不全时不误伤）
    coeff = targets.get("coefficient", 0.6)
    scale = coverage_scale(text, targets)
    target_eff = ch.get("median_eff", 0) * coeff * scale
    eff = effective_chars(text)
    if eff < target_eff:
        raise ValueError(
            f"{ch_id}.md 深度目标门 FAIL：eff {eff} < 目标 {target_eff:.0f}"
            f"（样例 median {ch.get('median_eff')} × {coeff} × 覆盖缩放 {scale:.2f}）"
            f"——逐要素成段扩写（缺数写 [待确认] 不砍段，覆盖率不足时门自动放宽）；"
            f"表后五步解读（陈述→规律识别→成因解释→规范对比→勘查意义）；"
            f"范式参照 references/samples/exploration/{ch_id}_sample.md"
        )


def load_targets(path: Path) -> dict | None:
    """装载 depth_targets.json；缺失/损坏 → stderr 提示后退回地板门（不阻断，spec §8）。"""
    if not path.exists():
        print(f"[build] depth_targets 不存在（{path}）——退回地板门（L0 深度门继续生效）", file=sys.stderr)
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc.get("per_chapter"), dict):
            raise ValueError("per_chapter 缺失或非对象")
        return doc
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        print(f"[build] depth_targets 损坏（{path}: {e}）——退回地板门", file=sys.stderr)
        return None


def resolve_targets(args_targets: str | None, stage_path: Path) -> dict | None:
    """--targets 显式路径优先；缺省沿 stage 文件向上三级探测 depth_targets.json。"""
    if args_targets:
        return load_targets(Path(args_targets))
    for anc in (stage_path.parent, stage_path.parent.parent, stage_path.parent.parent.parent):
        cand = anc / "depth_targets.json"
        if cand.exists():
            return load_targets(cand)
    print("[build] 未找到 depth_targets.json——退回地板门（L0 深度门继续生效）", file=sys.stderr)
    return None
```

- [ ] **Step 3.4: assemble 接线** — 两处改动：

签名（L230）：
```python
def assemble(stage: dict, data_dir: Path, state_dir: Path) -> tuple[str, dict[str, dict]]:
```
改为：
```python
def assemble(stage: dict, data_dir: Path, state_dir: Path, targets: dict | None = None) -> tuple[str, dict[str, dict]]:
```

循环体（L268-270）：
```python
        validate_depth(ch_id, raw)
        toc_stats[ch_id] = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
        parts.append(inject(raw).rstrip() + "\n")
```
改为：
```python
        validate_depth(ch_id, raw)
        toc_stats[ch_id] = validate_toc(ch_id, raw, stage["chapters"][ch_id].get("toc", []))
        injected = inject(raw).rstrip() + "\n"
        if targets is not None:
            validate_depth_target(ch_id, injected, targets)
        parts.append(injected)
```

- [ ] **Step 3.5: main() 接线** — argparse（L295-298 区域）在 `--state-dir` 行后加：
```python
    p.add_argument("--targets", help="depth_targets.json 路径；缺省探测 stage 同目录/../ ../../")
```
在 `args = p.parse_args()` 之后的 stage 装载处（`Path(args.stage)` 首次解析点之后）加：
```python
    targets = resolve_targets(args.targets, Path(args.stage))
```
并把 main 内对 `assemble(` 的调用改为多传 `targets=targets`。

模块 docstring 的退出码说明行追加一句：`rc=1 门：未知槽位/目录覆盖门/深度目标门（L2；targets 缺失时自动跳过回退地板门）`（以现有 docstring 措辞风格并入）。

- [ ] **Step 3.6: 跑新门测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestDepthTargetGate -v`
Expected: 5 PASS

- [ ] **Step 3.7: 既有测试免疫注入** — 两个文件同样改法。

v2_scripts：文件头 import 区加 `import tempfile`；`run()`（L34-38）整体替换为：

```python
_FLOOR_TARGETS: Path | None = None


def _floor_targets() -> Path:
    """permissive targets（median 全 1 → L2 目标 <1 必过）：既有负例只测各自关心的门，不被 L2 截胡（真实 targets 于 Task 4 入库）。"""
    global _FLOOR_TARGETS
    if _FLOOR_TARGETS is None:
        d = Path(tempfile.mkdtemp(prefix="geo_floor_targets_"))
        _FLOOR_TARGETS = d / "floor.json"
        _FLOOR_TARGETS.write_text(
            json.dumps({"per_chapter": {f"ch{i}": {"median_eff": 1, "median_table_rows": 0, "median_paragraphs": 1} for i in range(1, 11)}}, ensure_ascii=False),
            encoding="utf-8",
        )
    return _FLOOR_TARGETS


def run(*args, expect=(0,)):
    """调真实 CLI；断言退出码 ∈ expect。返回 stdout。build_output 未显式传 --targets 时注入 permissive targets。"""
    argv = [str(SCRIPTS / args[0]), *map(str, args[1:])]
    if argv[0].endswith("build_output.py") and "--targets" not in argv:
        argv += ["--targets", str(_floor_targets())]
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-800:]}\n{r.stderr[:400]}"
    return r.stdout
```

v2_scripts 三处裸 subprocess（`test_missing_chapter_rc1` L607 / `test_front_matter_pollution_rc1` L629 / `test_chapter_bad_first_line_rc1` L642）的 argv 列表，在 `"--output", str(...)` 之后各插入一段：
```python
                "--targets", str(_floor_targets()),
```

bug2223：同样加 `import tempfile` 与 `_FLOOR_TARGETS`/`_floor_targets()` 助手（与上面逐字相同的两段），`run()`（L28-30）按同样方式改：在构造命令处注入。bug2223 的 run 当前形如：
```python
def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8")
```
改为：
```python
def run(*args, expect=(0,)):
    argv = [str(SCRIPTS / args[0]), *map(str, args[1:])]
    if argv[0].endswith("build_output.py") and "--targets" not in argv:
        argv += ["--targets", str(_floor_targets())]
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], capture_output=True, text=True, encoding="utf-8")
```
（保留该文件 run() 原有的返回值/断言语句不动——它返回完整 r；只改 argv 构造。）

- [ ] **Step 3.8: 全量回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_bug2223.py tests/test_geological_report_skill.py -v`
Expected: 全 PASS（此刻 references/ 还没有真实 depth_targets.json，探测不命中；免疫注入已就位为 Task 4 铺路）

- [ ] **Step 3.9: Commit**

```bash
git add skills/public/geological-report/scripts/build_output.py backend/tests/test_geological_report_v2_scripts.py backend/tests/test_geological_report_bug2223.py
git commit -m "feat(geo-skill): L2 深度目标门——validate_depth_target+覆盖缩放+--targets 探测回退；既有测试注入 permissive targets 防截胡"
```

---

### Task 4: 生成真实 depth_targets.json + 探测链路回归锚

**Files:**
- Create(生成): `skills/public/geological-report/references/depth_targets.json`
- Test: `backend/tests/test_geological_report_v2_scripts.py`

- [ ] **Step 4.1: 对真实样例跑 calibrate**

Run:
```bash
python -X utf8 skills/public/geological-report/scripts/calibrate.py --samples-dir skills/public/geological-report/references/samples/exploration --output skills/public/geological-report/references/depth_targets.json
```
Expected: `CALIBRATED: 10 chapters -> …`，ch1..ch10 各一行。核对量级与 spec §1 证据表一致：ch1≈7320、ch2≈9203、ch3≈3211、ch4≈8990、ch5≈3785、**ch6≈17370（最大）**、ch7≈7918、ch8≈7904、ch9≈3763、ch10≈2331。偏差 >20% 时停下核对样例文件是否被改动，勿盲目提交。

- [ ] **Step 4.2: 幂等复核** — 重跑同一命令后 `git diff` 应无变化（sort_keys 无时间戳）。

- [ ] **Step 4.3: 写结构回归锚 + 探测链路测试** — v2_scripts 追加：

```python
class TestDepthTargetsFile:
    """提交的 references/depth_targets.json：结构/量级锚（calibrate 产物回归）。"""

    def test_structure_and_magnitude(self):
        doc = json.loads((SKILL / "references" / "depth_targets.json").read_text(encoding="utf-8"))
        assert (doc["coefficient"], doc["scale_floor"]) == (0.6, 0.25)
        pc = doc["per_chapter"]
        assert set(pc) == {f"ch{i}" for i in range(1, 11)}
        assert all(c["median_eff"] > 1000 for c in pc.values())
        assert max(pc, key=lambda k: pc[k]["median_eff"]) == "ch6"  # 证据表：ch6 样例最厚
        assert pc["ch6"]["median_eff"] > 15000

    def test_probe_finds_real_targets(self, ws, tmp_path):
        """不传 --targets → 探测命中 references/depth_targets.json → 合成薄章节被真实目标拦截（探测链路端到端锚）。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE),
             "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"])],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 1 and "深度目标门" in r.stderr, r.stderr
```

- [ ] **Step 4.4: 全量回归（关键——真实 targets 已入库，免疫注入是否兜住全看这步）**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_bug2223.py tests/test_geological_report_skill.py -v`
Expected: 全 PASS。若有用例仍被「深度目标门」截胡 → 它绕过了 run() 注入（漏改的裸 subprocess），补 `--targets` 后重跑。

- [ ] **Step 4.5: Commit**

```bash
git add skills/public/geological-report/references/depth_targets.json backend/tests/test_geological_report_v2_scripts.py
git commit -m "feat(geo-skill): references/depth_targets.json 落地（10 章实测基线）+探测链路回归锚"
```

---

### Task 5: data_expectations.json 数据预告 + SKILL.md 步骤1 接入

**Files:**
- Create: `skills/public/geological-report/references/data_expectations.json`
- Modify: `skills/public/geological-report/SKILL.md:57-58`（步骤1 第1条尾部）
- Test: `backend/tests/test_geological_report_v2_scripts.py`、`backend/tests/test_geological_report_skill.py`

- [ ] **Step 5.1: 写失败测试** — v2_scripts 追加（族名对照 stage forms 校验，写错族名即红）：

```python
class TestDataExpectations:
    """按章数据预告：10 章全覆盖、族名必须是 stage forms 实有键、CSV 列样例在场。"""

    def test_covers_all_chapters_and_valid_families(self):
        doc = json.loads((SKILL / "references" / "data_expectations.json").read_text(encoding="utf-8"))
        pc = doc["per_chapter"]
        assert set(pc) == {f"ch{i}" for i in range(1, 11)}
        known = set(json.loads(STAGE.read_text(encoding="utf-8"))["forms"])
        for ch, entry in pc.items():
            assert set(entry["families"]) <= known, (ch, set(entry["families"]) - known)
        assert "样品编号" in doc["csv_columns"]["sample_assays"]
        assert "小体重" in doc["csv_columns"]["bulk_density"]
```

skill 测试文件追加（沿用该文件 presence 断言模式；若已有读取 SKILL.md 的 fixture/常量则复用，以下为自包含写法）：

```python
class TestDataExpectationPrompt:
    """SKILL.md 步骤1 数据预告 presence（spec 2026-08-25 §6）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (REPO_ROOT / "skills/public/geological-report/SKILL.md").read_text(encoding="utf-8")

    def test_data_expectation_present(self):
        assert "数据预告" in self.content
        assert "data_expectations.json" in self.content
```

（`REPO_ROOT` 若该文件已有同名常量则复用；没有则 `REPO_ROOT = Path(__file__).resolve().parents[2]`。）

- [ ] **Step 5.2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestDataExpectations tests/test_geological_report_skill.py -v`
Expected: FAIL（文件不存在 / 关键词缺失）

- [ ] **Step 5.3: 写 data_expectations.json 全文**（族名已对照 exploration.json forms 逐一核实：21 键）：

```json
{
  "_comment": "开题数据预告（手写静态文件，spec 2026-08-25）：按章列出所需数据族与 CSV 列样例，引导用户一次备齐。缺某族 → 相关小节落 [待确认]，缺数不编造。族名与 stages/exploration.json forms 键一致。",
  "csv_columns": {
    "sample_assays": ["样品编号", "工程编号", "矿体编号", "起止深度(m)", "样长(m)", "主元素品位(%)", "伴生元素品位(g/t)"],
    "bulk_density": ["样品编号", "矿体编号", "矿石类型", "小体重(t/m³)", "品位(%)", "湿度(%)"]
  },
  "per_chapter": {
    "ch1": {"families": ["project", "tenement", "prev_work", "mine_history"], "note": "绪论四件套：项目批文/矿权/以往工作/矿山沿革"},
    "ch2": {"families": ["regional_pack"], "note": "知识章：区域地质包由技能叙述，通常无需用户提供数据"},
    "ch3": {"families": ["geography", "orefield_geology"], "note": "交通地理 + 矿区地质"},
    "ch4": {"families": ["orebody_list"], "note": "矿体清单（编号/产状/规模/品位）；矿体数 >3 建议整表上传"},
    "ch5": {"families": ["sample_assays", "lab_assays", "beneficiation"], "note": "样品分析（sample_assays 为 CSV 族）+ 选冶试验"},
    "ch6": {"families": ["hydro_eng_env"], "note": "水文/工程/环境地质条件"},
    "ch7": {"families": ["workload", "exploration_qc", "bulk_density"], "note": "勘查工程量与质量评述（bulk_density 为 CSV 族）"},
    "ch8": {"families": ["industrial_params", "block_model", "verification", "prior_estimate"], "note": "资源量估算四件套：工业指标/块段/验证/既往估算；块段多建议整表上传"},
    "ch9": {"families": ["economics"], "note": "经济评价参数"},
    "ch10": {"families": [], "note": "结论：无新数据，要点由前九章投影"}
  }
}
```

- [ ] **Step 5.4: SKILL.md 步骤1 接入** — L57-58（第 1 条模板解析）的 blockquote 行 `> 知识工厂未命中模板…` 之后、`2. `ingest.py forms`…` 之前，插入一行：

```
   返回模板后（或声明兜底后）立即做**数据预告**：读 `references/data_expectations.json`，把按章数据清单（每章所需数据族 + CSV 列样例）一并向用户预告，引导一次备齐；用户明确缺的族照常落 `[待确认]`，缺数不编造。
```

- [ ] **Step 5.5: 跑测试确认通过 + Commit**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py::TestDataExpectations tests/test_geological_report_skill.py -v`
Expected: 全 PASS

```bash
git add skills/public/geological-report/references/data_expectations.json skills/public/geological-report/SKILL.md backend/tests/test_geological_report_v2_scripts.py backend/tests/test_geological_report_skill.py
git commit -m "feat(geo-skill): data_expectations.json 按章数据预告 + SKILL.md 步骤1 接入"
```

---

### Task 6: SKILL.md 步骤4 范式升级 + 命令速查 + presence 测试

**Files:**
- Modify: `skills/public/geological-report/SKILL.md:84-87,126-141`
- Test: `backend/tests/test_geological_report_skill.py`

- [ ] **Step 6.1: 写失败测试** — skill 测试文件追加（fixture 模式同 Task 5 的类，复用读取方式）：

```python
class TestDepthParadigm:
    """SKILL.md 步骤4 深度范式升级 presence（spec 2026-08-25 §6）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (REPO_ROOT / "skills/public/geological-report/SKILL.md").read_text(encoding="utf-8")

    def test_step4_depth_rules(self):
        for kw in ("逐要素成段", "五步解读", "动笔前读深度目标", "depth_targets.json", "深度目标门", "不砍段"):
            assert kw in self.content, kw

    def test_command_table(self):
        assert "calibrate.py" in self.content          # 速查表新增行
        assert "--targets" in self.content             # build_output 用法补可选参
```

- [ ] **Step 6.2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_skill.py -v`
Expected: FAIL（关键词缺失）

- [ ] **Step 6.3: SKILL.md 四处编辑**（均为「找原句→替换」，原文见 L84-87/L124-141）：

**① L84 骨架全覆盖 bullet**——原片段：
`全部二、三级节逐一落笔，**每节按其 `elements` 逐要素成句**（某要素缺数据写 `[待确认]` 占位句，如「矿体平均厚度：[待确认]」）；`
替换为：
`全部二、三级节逐一落笔，**每节按其 `elements` 逐要素成段**——要素链每个节点 ≥1 段完整专业叙述（定性描述+空间关系+工程意义），某要素缺数据写 `[待确认]` 占位句（如「矿体平均厚度：[待确认]」）但**不砍段**；`

**② L86 叙述深度下限 bullet**——原片段：
`每张表前有引入段、表后有解读段——禁「表后即下一节」`
替换为：
`每张表前有引入段、表后**五步解读**——陈述→规律识别→成因解释→规范对比→勘查意义（规范对比只引 standards_index 实有编号，禁凭记忆写条款号）——禁「表后即下一节」`

**③ L87 条目式叙述范式 bullet 之后新增一个 bullet**：
```
- **动笔前读深度目标（bug-2221 根治）**：写每章前读 `references/depth_targets.json` 该章 `median_eff`/`median_table_rows`/`median_paragraphs`，以此为篇幅下限自检；build_output **深度目标门**兜底（eff ≥ 样例 median × 0.6 × 覆盖缩放，FAIL exit 1），按 stderr 指引逐要素成段补写——缺数写 `[待确认]` 不砍段，数据覆盖不足时门自动放宽目标
```

**④ 命令速查表（L126-141）两行**——`build_output.py` 行改为：
```
| `build_output.py --stage S --data-dir D --state-dir T --output R [--targets P]` | 原子组装+槽位注入+深度目标门 | 0（BUILD_READY+MANIFEST_READY）/ 1 门拦（未知槽位/目录覆盖门/深度目标门） |
```
并在该行之前插入：
```
| `calibrate.py --samples-dir DIR --output T` | 样例→深度基线（维护者：样例变更后重跑生成 depth_targets.json） | 0/1 样例无节号拒产 |
```

- [ ] **Step 6.4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_skill.py -v`
Expected: 全 PASS（含既有 presence 类不回归）

- [ ] **Step 6.5: Commit**

```bash
git add skills/public/geological-report/SKILL.md backend/tests/test_geological_report_skill.py
git commit -m "docs(geo-skill): SKILL.md 步骤4 范式升级——逐要素成段/表后五步解读/动笔前读深度目标+命令速查补 calibrate"
```

---

### Task 7: 终验 + 部署

- [ ] **Step 7.1: 全量 geo 套件 + 交付门套件回归**

Run:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py tests/test_geological_report_bug2223.py tests/test_geological_report_skill.py tests/test_delivery_contract_gates.py -v
make lint
```
Expected: 全 PASS + lint 干净。若 `ruff format --check` 对触碰过的测试文件报红：`uv run ruff format tests/test_geological_report_v2_scripts.py tests/test_geological_report_bug2223.py tests/test_geological_report_skill.py` 后复查再提交（ruff 配置 line length 240）。

- [ ] **Step 7.2: calibrate 幂等终核** — 重跑 Step 4.1 命令，`git status` 应无 `depth_targets.json` 变更。

- [ ] **Step 7.3: 部署刷新** — `docker compose -p eai-docker restart gateway`（skills 投射到 gateway，references 新文件需重启生效）。

- [ ] **Step 7.4: 页面 E2E（部署后人工/agent 驱动，不阻塞本计划收尾）**——用 `backend/tests/fixtures/geological_report/e2e-full/` 数据包在线程里重跑全量生成，验收 spec §10：
  - 全量数据场景：各章 BUILD_READY，逐章 eff ≥ 样例 median × 0.6（ch6 正文 ≥ ~10,400 eff chars），报告总量 ≈ 43,000+ eff chars；
  - 缺数场景（只给部分族）：缺数章不被深度目标门误拦（覆盖缩放触底放行），正文落 `[待确认]` 占位且不砍段；
  - 故意交一版薄章节：build rc=1，stderr 含「深度目标门 FAIL…覆盖缩放」，agent 按 stderr 指引补写后过门。

---

## 自审记录（写计划时已核对）

- **Spec 覆盖**：§3 架构（Task 1/3）、§4 门公式与 FAIL 文案（Task 3）、§5 calibrate（Task 2/4）、§6 SKILL.md 三处（Task 5/6）、§8 错误处理表（load_targets/resolve_targets 三分支：缺失/损坏/探测不到 → 同一「退回地板门」stderr；calibrate 无节号 rc=1）、§9 测试策略（calibrate 2 例、effective_chars 回归、门 5 例、skill presence）、§10 验收（Task 4 量级锚 + Task 7.4 两场景）——全部有对应任务。
- **执行顺序依赖**：Task 3 的测试免疫注入**必须**先于（或同提交于）Task 4 真实 targets 入库，否则 ~30 既有测试被真实目标截胡——顺序已锁定。
- **红线**：零 harness/app 改动；data/ 与 formula_state.json 写者不变；交付面（bug-2225 三门）零触碰；数值仍只走 `{{SLOT:key}}`。
