# bid-review 金标准评测集（golden set）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 bid-review 规则引擎建人工标注题库（34 规则全覆盖+L2 专项 strict+全管线冒烟），以 pytest 回归门 + CLI 成绩单双出口生效。

**Architecture:** 从 `worker._run_review_stage` 提取共享分派核 `eval_core.evaluate_fields`（worker 与评测器共用同一段分派逻辑，禁复制）；`golden/` 新模块承载 schema/loader/runner/report/CLI；题库为每题一个 YAML（字段夹具+人工标注期望），sem/hyb 规则经 `model_script` 确定性脚本应答评测。

**Tech Stack:** Python 3.12 / pytest / PyYAML（repo 既有）。纯后端，零前端改动。Spec: `docs/superpowers/specs/2026-11-03-bid-review-golden-set-design.md`。

---

## 全局约束（每个任务的实现者都必须遵守）

- 分支 `main-dev-fork`，**只提交到该分支，禁 push**（controller 收尾统一推）。禁 `git add -A`/`git add .`，只 add 本任务列出的显式路径。
- **不动他任务 WIP**：`backend/app/extensions/contract_price/service.py`、`backend/app/extensions/settings/routers.py`、`frontend/src/app/bid-review/bid-review.css`、`frontend/src/extensions/bid-review/components/TaskStepper.tsx`、`TaskTitleTag.tsx`、`frontend/tests/unit/extensions/bid-review-review-queue.dom.test.tsx`、`.wolf/*` 内容（controller 专属协议追加除外）、其余 git status 里既有脏文件。
- 后端测试命令：`cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/ -k "bid_review" -q --ignore=test_dept_fix.py --ignore=test_full_pipeline.py`（当前基线 **258 passed, 6 skipped**——任何任务完成后此数只增不减）。单文件：`PYTHONPATH=. uv run pytest tests/test_<file>.py -v`。
- lint：`cd /d/eai/eai-flow-main/backend && uv run ruff check app/extensions/bid_review tests/test_bid_review_golden.py tests/test_bid_review_eval_core.py && uv run ruff format --check <同列表>`（只管自己的文件；全树 format 债务不动）。
- 行宽 240；导入排序 E/F/I；`EAI-CUSTOM` 注释按三重规范（本计划全部新模块在模块 docstring 首行声明即可，改动上游文件需 START/END 包裹——本计划只动 `worker.py` 一处，见 Task 1）。
- 已知 flaky 勿再报：`test_model_crash_isolated*` 时序、`review_state_projection`、worker_prod_model 环境依赖（若全量套件偶红，单跑复验后注记）。
- 新 YAML 一律 UTF-8 无 BOM；中文直接写。
- 评测器与生产代码共享分派核是本计划的铁律：**任何在 runner 里重写分派循环的写法都是错误实现**。

## 现状工程事实（实现者必读）

- 分派循环现位：`backend/app/extensions/bid_review/worker.py:346-389`（`_run_review_stage` 内）。逻辑：`det_fields = 非None 过滤` → 逐 enabled 规则：`deterministic → attach_evidence(run_det_rule(rule, det_fields), rule, provenance)`；`semantic|hybrid → await run_sem_rule(rule, det_fields, materials, model_fn, docs_text)`；异常 → `_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 need_human)")`；逐条 `crud.add_issue`。
- 纯函数已存在：`engine/rule_runner.py` 的 `run_det_rule(rule, fields) -> list[dict]`、`attach_evidence(issues, rule, provenance)`、`_need_human(rule, msg)`、`Rule`/`RulePack`/`load_rulepack(path)`。issue dict 形状：`{rule_id, layer, severity, verdict: violation|need_human|unclear, need_human, matched_expected, message, fix, evidence, entity_keys, source, dedup_key}`。
- `run_sem_rule(rule, fields, materials, model_fn, docs_text, model_name="sem-default")`（async，`engine/llm_runner.py:207`）；`model_fn` 是**已包装**形态：`async def wrapped(messages) -> SimpleNamespace(content=str)`；scripted stub 直接回 str 即可（`getattr(response, "content", response)` 兜住）。模型应答 JSON 契约（`engine/verify.py check_schema`）：`{"verdicts": [{"clause_id": str, "verdict": <∈规则 check.verdict_set 或默认集>, "confidence": 0-1, "reason": 非空str, "evidence": [{"doc_id": 非空str, "page": 正int, "text": str?}], "severity"?: str}]}`（非空 verdicts 列表）。
- `worker._wrap_model_fn`（:77-89）与 `_content_to_str`（:60-74）将被移入 eval_core（worker 保别名兼容）。
- `build_baseline(docs, extract_fn)`（`engine/extract.py:394`）：`extract_fn(docs, field_paths)` 同步 callable，返回 `{path: value}` 平 dict 或 `{"fields": ..., "provenance": ...}`；docs 形状 `[{"doc_id": "b.pdf", "role": "bid", "text": "..."}]`（先例 `tests/test_bid_review_worker_sem.py:102 _DOCS`）。
- rulepack：`engine/rulepacks/bid-review-core/1.0.0.yaml`，34 条 = 29 deterministic + 4 hybrid（L1-003/L1-007/L3-004/L3-008）+ 1 semantic（L1-013）。hyb 铁律：det 零命中→零模型调用直接 `[]`；候选（violation）交模型确认，`full`=驳回候选不产条目、`partial/none`=产条目、`unclear`=need_human 存活；缺字段 need_human 直接透传。
- 既有脚本化模型先例：`tests/test_bid_review_worker_sem.py` 的 `_fake_model(responses, calls)`（按规则卡「规则:<id>」路由）与 `_vd(*entries)`。
- `build_checklist(requirements, provided, bid_doc_id=None) -> dict`（`engine/attachments.py:159`）。

## File Structure（职责锁定）

```
backend/app/extensions/bid_review/engine/eval_core.py   # 共享分派核（wrap_model_fn + evaluate_fields）——新
backend/app/extensions/bid_review/golden/__init__.py    # 包标记——新
backend/app/extensions/bid_review/golden/schema.py      # GoldenCase/Expectation/ChecklistExpect/CaseResult 数据类——新
backend/app/extensions/bid_review/golden/loader.py      # YAML 载入+校验（allowlist/sem-script 依赖/命名）——新
backend/app/extensions/bid_review/golden/runner.py      # run_case/run_smoke_dir（diff 引擎）——新
backend/app/extensions/bid_review/golden/report.py      # Report 聚合 + markdown/JSON 渲染——新
backend/app/extensions/bid_review/golden/__main__.py    # CLI 入口——新
backend/app/extensions/bid_review/golden/cases/*.yaml   # 字段层题库（34+）——新
backend/app/extensions/bid_review/golden/smoke/smoke-1-basic/*  # 冒烟题——新
backend/app/extensions/bid_review/golden/CALIBRATION.md # 校准裁决记录——新
backend/app/extensions/bid_review/worker.py             # _run_review_stage 改为消费 evaluate_fields——唯一改动现有文件
backend/tests/test_bid_review_eval_core.py              # 分派核单测——新
backend/tests/test_bid_review_golden.py                 # 回归门（参数化逐题+覆盖率）+ loader/runner/report 单测——新
```

---

### Task 1: 共享分派核 `eval_core.py` 提取 + worker 改接

**Files:**
- Create: `backend/app/extensions/bid_review/engine/eval_core.py`
- Modify: `backend/app/extensions/bid_review/worker.py`（`_run_review_stage` :346-368 一段 + `_wrap_model_fn`/`_content_to_str` 移走留别名）
- Test: `backend/tests/test_bid_review_eval_core.py`（新）

- [ ] **Step 1: 写分派核失败测试** `backend/tests/test_bid_review_eval_core.py`：

```python
"""共享分派核单测(金标准 spec §4):det/sem 分派、None 剥离、逐规则隔离、进度回调。
金标准尺子量生产同一段代码——本文件锁 eval_core 行为契约。"""
import json
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.rule_runner import load_rulepack

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")


def _quiet_model(responses: dict | None = None):
    """scripted model_fn:按规则卡「规则:<id>」路由;缺省回安静 full 应答(零条目)。"""
    table = responses or {}

    def model(messages):
        card = messages[0]["content"] if isinstance(messages, list) else str(messages)
        for rid, resp in table.items():
            if f"规则:{rid}" in card:
                return resp
        return json.dumps({"verdicts": [{"clause_id": "g", "verdict": "full", "confidence": 1.0, "reason": "quiet", "evidence": [{"doc_id": "g.pdf", "page": 1}]}]}, ensure_ascii=False)

    return model


@pytest.mark.asyncio
async def test_det_violation_and_need_human_dispatch():
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    by_rule = {}
    for i in issues:
        by_rule.setdefault(i["rule_id"], []).append(i)
    assert any(i["verdict"] == "violation" and i["severity"] == "fatal" for i in by_rule["L1-009"])
    # L1-005 输入缺失 → need_human(缺字段约定)
    assert any(i["verdict"] == "need_human" for i in by_rule["L1-005"])


@pytest.mark.asyncio
async def test_none_fields_stripped_before_eval():
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": None}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    l9 = [i for i in issues if i["rule_id"] == "L1-009"]
    assert all(i["verdict"] == "need_human" for i in l9)  # None 字段=缺字段,不判违规


@pytest.mark.asyncio
async def test_rule_crash_isolated_to_need_human(monkeypatch):
    from app.extensions.bid_review.engine import eval_core
    pack = load_rulepack(PACK)

    def boom(rule, fields):
        if rule.id == "L1-009":
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(eval_core, "run_det_rule", boom)
    issues = await evaluate_fields(pack, {}, model_fn=wrap_model_fn(_quiet_model()))
    l9 = [i for i in issues if i["rule_id"] == "L1-009"]
    assert len(l9) == 1 and l9[0]["verdict"] == "need_human" and "boom" in l9[0]["message"]


@pytest.mark.asyncio
async def test_on_progress_reports_each_rule():
    pack = load_rulepack(PACK)
    seen = []

    async def cb(i, total, rule):
        seen.append((i, total, rule.id))

    await evaluate_fields(pack, {}, model_fn=wrap_model_fn(_quiet_model()), on_progress=cb)
    ids = [r for _, _, r in seen]
    assert len(seen) == sum(1 for r in pack.rules if r.enabled)
    assert ids[0] and ids[-1]  # 逐规则推进
```

注意：repo 若无 `pytest.mark.asyncio` 的 asyncio_mode 配置，先查 `backend/tests/` 既有 async 测试的写法（`test_bid_review_worker_sem.py` 用 `async def test_...` + `pytest.ini`/`pyproject` 里 `asyncio_mode = auto` 或显式 marker——**照抄既有写法**，以上 `@pytest.mark.asyncio` 以仓库实际形态为准）。

- [ ] **Step 2: 跑失败** — `PYTHONPATH=. uv run pytest tests/test_bid_review_eval_core.py -v` → 预期 `ModuleNotFoundError: eval_core`。

- [ ] **Step 3: 建 `engine/eval_core.py`**（worker.py 的 `_content_to_str` :60-74 与 `_wrap_model_fn` :77-89 原文搬入，实现照抄不得改语义）：

```python
"""共享规则分派核(金标准评测集 spec §4,EAI-CUSTOM 2026-11-03):
worker._run_review_stage 与 golden 评测器共用同一段分派逻辑——det/sem 分派、
None 字段剥离、逐规则异常隔离降级 need_human。金标准尺子量的必须是生产同一段
代码,评测器禁复制分派循环(复制=两把尺子,必然漂移说谎)。bug 编号:无;
升级注意:改分派语义须同步跑 tests/test_bid_review_eval_core.py 与金标准全库。"""
import inspect
from types import SimpleNamespace
from typing import Awaitable, Callable

from app.extensions.bid_review.engine.llm_runner import run_sem_rule
from app.extensions.bid_review.engine.rule_runner import Rule, RulePack, _need_human, attach_evidence, run_det_rule

ProgressCB = Callable[[int, int, Rule], Awaitable[None]]


def _content_to_str(content) -> str:
    # ↑ 从 worker.py:60-74 原文搬入(LangChain 分块 list 归一 str),逐字保留
    ...

def wrap_model_fn(model_fn):
    # ↑ 从 worker.py:77-89 原文搬入(调 raw model_fn,归一 content 为 str 后以
    # 带 .content 的轻量响应对象回交),逐字保留
    ...

async def evaluate_fields(
    pack: RulePack,
    fields: dict,
    *,
    model_fn,
    materials: str = "",
    docs_text: str = "",
    provenance: dict | None = None,
    on_progress: ProgressCB | None = None,
) -> list[dict]:
    """字段 → issues(无 DB、无状态)。model_fn 为已包装形态(wrap_model_fn 产物)。
    与 worker._run_review_stage 分派语义逐字一致(None 剥离/类型分派/逐规则隔离)。"""
    det_fields = {k: v for k, v in fields.items() if v is not None}
    rules = [r for r in pack.rules if r.enabled]
    total = max(len(rules), 1)
    out: list[dict] = []
    for i, rule in enumerate(rules, start=1):
        if on_progress is not None:
            await on_progress(i, total, rule)
        try:
            if rule.type == "deterministic":
                issues = attach_evidence(run_det_rule(rule, det_fields), rule, provenance)
            else:  # semantic|hybrid
                issues = await run_sem_rule(rule, det_fields, materials, model_fn, docs_text)
        except Exception as exc:  # noqa: BLE001
            issues = [_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 need_human)")]
        out.extend(issues)
    return out
```

- [ ] **Step 4: worker 改接** —— `worker.py`：
  1. 删除本模块 `_content_to_str`/`_wrap_model_fn` 函数体，替换为别名（保测试/外部引用兼容）：
     ```python
     from app.extensions.bid_review.engine.eval_core import _content_to_str, evaluate_fields, wrap_model_fn
     _wrap_model_fn = wrap_model_fn  # 兼容别名(金标准重构,原实现移 eval_core)
     ```
  2. `_run_review_stage` :346-368 段替换为：
     ```python
     pack = load_rulepack(RULEPACK_PATH)
     det_fields = {k: v for k, v in fields.items() if v is not None}
     wrapped_model = _wrap_model_fn(model_fn or _default_model_fn())
     docs = _load_docs(task)
     materials = _collect_materials(docs)
     docs_text = _collect_docs_text(docs)

     async def _progress(i: int, total: int, rule) -> None:
         await crud.set_status(db, task, "running", progress={"stage": "review", "pct": int(i * 100 / total), "msg": f"{rule.id}({i}/{total})"})

     issues = await evaluate_fields(pack, det_fields, model_fn=wrapped_model, materials=materials, docs_text=docs_text, provenance=provenance, on_progress=_progress)
     written = 0
     ```
     其后 `for issue in issues: row = await crud.add_issue(...)` 段**一字不动**保留。docstring 补一行：「分派逻辑移 eval_core 共享核(金标准 spec §4,worker/评测器同源)。」日志差异注记：隔离 warning 从 worker logger 移到 eval_core（含 rule.id 与 exc，无 task id）——查无测试断言该日志文本。

- [ ] **Step 5: 全绿** — `PYTHONPATH=. uv run pytest tests/test_bid_review_eval_core.py tests/test_bid_review_worker.py tests/test_bid_review_worker_sem.py tests/test_bid_review_worker_prod_model.py -v` 全过；再跑全局 `-k "bid_review"` ≥ 258+4。

- [ ] **Step 6: ruff** — `uv run ruff check app/extensions/bid_review/engine/eval_core.py app/extensions/bid_review/worker.py && uv run ruff format app/extensions/bid_review/engine/eval_core.py`

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/bid_review/engine/eval_core.py backend/app/extensions/bid_review/worker.py backend/tests/test_bid_review_eval_core.py
git commit -m "refactor(bid-review): 分派逻辑提取共享核 eval_core.evaluate_fields——worker/golden 同源(金标准 spec §4),worker 保别名兼容"
```

---

### Task 2: golden 包骨架 + schema.py + loader.py + 样例题

**Files:**
- Create: `backend/app/extensions/bid_review/golden/__init__.py`、`schema.py`、`loader.py`
- Create: `backend/app/extensions/bid_review/golden/cases/L1-009-over-max-price.yaml`（首道样例题）
- Test: `backend/tests/test_bid_review_golden.py`（先只含 loader 测试段）

- [ ] **Step 1: 写 loader 失败测试**（`backend/tests/test_bid_review_golden.py` 开头段）：

```python
"""金标准回归门(金标准 spec §7)+loader/runner/report 单测。题库=人工标注答案,
diff 即回归;快照式自动生成被 spec 明确否决(把 bug 固化成标准)。"""
import json
from pathlib import Path

import pytest

from app.extensions.bid_review.golden import loader
from app.extensions.bid_review.engine.rule_runner import load_rulepack

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")
CASES_DIR = Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "golden" / "cases"


def test_load_sample_case():
    c = loader.load_case(CASES_DIR / "L1-009-over-max-price.yaml")
    assert c.case == "L1-009-over-max-price"
    assert c.expect_issues[0].rule_id == "L1-009" and c.expect_issues[0].severity == "fatal"
    assert c.strict is False


def test_unknown_field_path_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "case: bad\ndesc: x\nfields:\n  tender.nonexistent.path: 1\nexpect_issues: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="未知字段路径"):
        loader.load_case(p)


def test_sem_expect_requires_model_script(tmp_path):
    p = tmp_path / "bad2.yaml"
    p.write_text(
        "case: bad2\ndesc: x\nfields: {}\nexpect_issues:\n- {rule_id: L1-013, severity: major, contains: [x]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="model_script"):
        loader.load_case(p)


def test_case_filename_must_match_case_id(tmp_path):
    p = tmp_path / "mismatch.yaml"
    p.write_text("case: other-name\ndesc: x\nfields: {}\nexpect_issues: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case 与文件名"):
        loader.load_case(p)
```

- [ ] **Step 2: 跑失败**（ModuleNotFoundError: golden）。

- [ ] **Step 3: 实现 schema.py + loader.py + 样例题**：

`schema.py`：

```python
"""金标准题库契约(EAI-CUSTOM 2026-11-03,spec §5/§6)。Expectation.verdict 缺省
violation:need_human 类断言须显式 verdict: need_human——漏报判定按 verdict 分桶,
引擎降级链(need_human)不冒充命中。strict 的「期望外」只数 verdict=violation
(need_human 是引擎主动声明无法判定,不是错判;其断言走 expect_issues 显式期待)。"""
from dataclasses import dataclass, field


@dataclass
class Expectation:
    rule_id: str
    severity: str
    contains: list[str] = field(default_factory=list)
    verdict: str = "violation"  # violation | need_human | unclear
    entity: str = ""            # 实体消歧子串(对 entity_keys+message;L2 逐实体多条时必带,spec §1.5)
    acceptable_rule_ids: list[str] = field(default_factory=list)  # 等价规则集:任一命中算 TP(不计覆盖率地板,spec §1.5)


@dataclass
class ChecklistExpect:
    unknown_count: int = 0
    status_by_no: dict[str, str] = field(default_factory=dict)  # {no: MATCHED|PARTIAL|MISSING|UNKNOWN}


@dataclass
class GoldenCase:
    case: str
    desc: str
    fields: dict
    expect_issues: list[Expectation]
    expect_absent: list[str]
    strict: bool = False
    checklist: ChecklistExpect | None = None
    model_script: dict[str, str] = field(default_factory=dict)  # {rule_id: verdicts JSON}
    source_path: str = ""


@dataclass
class CaseResult:
    case: str
    desc: str
    strict: bool
    ok: bool
    missing: list[str]           # 期望未命中渲染
    unexpected: list[str]        # strict 下期望外 violation
    absent_violations: list[str] # expect_absent 违例
    checklist_diff: list[str]
    hits: dict[str, int] = field(default_factory=dict)  # {rule_id: 命中数}(成绩单 tp 来源)
    n_issues: int = 0

    @property
    def diff_lines(self) -> list[str]:
        return [*self.missing, *self.unexpected, *self.absent_violations, *self.checklist_diff]
```

`loader.py`：

```python
"""题库 YAML 载入+校验(EAI-CUSTOM 2026-11-03)。fail-fast:schema 不合法/字段越界/
sem 断言缺 script 一律加载期报错,不带病进跑批(spec §11)。"""
import re
from pathlib import Path

import yaml

from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden.schema import ChecklistExpect, Expectation, GoldenCase

RULEPACK_PATH = str(Path(__file__).resolve().parent.parent / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")
# 投影端点消费但非规则 inputs 的字段(spec §5 白名单并集)
PROJECTION_PATHS = {"tender.attachment_requirements", "bid.attachment_index", "tender.scoring_items"}

_NAME_RE = re.compile(r"^[A-Z0-9]+-[0-9]+-[a-z0-9-]+$")


def known_field_paths(pack=None) -> set[str]:
    pack = pack or load_rulepack(RULEPACK_PATH)
    paths: set[str] = set(PROJECTION_PATHS)
    for r in pack.rules:
        paths.update(r.inputs or [])
    return paths


def load_case(path: str | Path, pack=None) -> GoldenCase:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    case = str(data.get("case") or "")
    if not _NAME_RE.match(case) or case != Path(path).stem:
        raise ValueError(f"case 与文件名不一致或命名非法: {case} vs {Path(path).stem}(规则 {{rule_id}}-{{slug}})")
    pack = pack or load_rulepack(RULEPACK_PATH)
    types = {r.id: r.type for r in pack.rules}
    allowed = known_field_paths(pack)
    bad = [k for k in (data.get("fields") or {}) if k not in allowed]
    if bad:
        raise ValueError(f"未知字段路径(rulepack inputs ∪ 投影路径之外): {bad}")
    expects = [
        Expectation(
            rule_id=str(e["rule_id"]),
            severity=str(e.get("severity") or ""),
            contains=[str(x) for x in (e.get("contains") or [])],
            verdict=str(e.get("verdict") or "violation"),
            entity=str(e.get("entity") or ""),
            acceptable_rule_ids=[str(x) for x in (e.get("acceptable_rule_ids") or [])],
        )
        for e in (data.get("expect_issues") or [])
    ]
    script = {str(k): str(v) for k, v in (data.get("model_script") or {}).items()}
    for e in expects:
        rid_type = types.get(e.rule_id)
        if rid_type in ("semantic", "hybrid") and e.verdict != "full" and e.rule_id not in script:
            raise ValueError(f"expect_issues 引用 sem/hyb 规则 {e.rule_id} 但缺 model_script(默认安静应答只会回 full)")
    cl = data.get("checklist")
    return GoldenCase(
        case=case,
        desc=str(data.get("desc") or ""),
        fields=dict(data.get("fields") or {}),
        expect_issues=expects,
        expect_absent=[str(x) for x in (data.get("expect_absent") or [])],
        strict=bool(data.get("strict") or False),
        checklist=ChecklistExpect(**cl) if cl else None,
        model_script=script,
        source_path=str(path),
    )


def load_cases(directory: str | Path = None) -> list[GoldenCase]:
    directory = Path(directory) if directory else Path(__file__).resolve().parent / "cases"
    return [load_case(p) for p in sorted(directory.glob("*.yaml"))]
```

样例题 `golden/cases/L1-009-over-max-price.yaml`（字段取自既有测试 `test_run_l1_009_violation_and_need_human` 的实连线）：

```yaml
case: L1-009-over-max-price
desc: 投标总价超最高限价 1 元 → L1-009 fatal
fields:
  bid.total_price: 1000001.0
  tender.max_price: 1000000.0
  bid.price_includes_tax: true
  tender.price_includes_tax: true
expect_issues:
  - rule_id: L1-009
    severity: fatal
    contains: ["1,000,001"]
expect_absent: []
strict: false
```

- [ ] **Step 4: 跑 loader 测试绿** — `PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py -v` 4 过。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/golden/__init__.py backend/app/extensions/bid_review/golden/schema.py backend/app/extensions/bid_review/golden/loader.py backend/app/extensions/bid_review/golden/cases/L1-009-over-max-price.yaml backend/tests/test_bid_review_golden.py
git commit -m "feat(bid-review): golden 包骨架——schema/loader 契约+样例题 L1-009(spec §5;fields 白名单+sem script 依赖 fail-fast)"
```

---

### Task 3: runner.py diff 引擎

**Files:**
- Create: `backend/app/extensions/bid_review/golden/runner.py`
- Test: `backend/tests/test_bid_review_golden.py`（追加 runner 测试段）

- [ ] **Step 1: 追加 runner 失败测试**：

```python
# ---- runner diff 引擎 ----
from app.extensions.bid_review.golden.loader import load_case
from app.extensions.bid_review.golden.runner import run_case

CASES = Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "golden"


@pytest.mark.asyncio
async def test_sample_case_passes():
    pack = load_rulepack(PACK)
    c = load_case(CASES / "cases" / "L1-009-over-max-price.yaml", pack)
    res = await run_case(c, pack)
    assert res.ok, res.diff_lines


@pytest.mark.asyncio
async def test_missing_expectation_detected():
    pack = load_rulepack(PACK)
    c = load_case(CASES / "cases" / "L1-009-over-max-price.yaml", pack)
    c.expect_issues[0].contains = ["不存在的关键词XYZ"]
    res = await run_case(c, pack)
    assert not res.ok and any("L1-009" in m and "未命中" in m for m in res.diff_lines)


@pytest.mark.asyncio
async def test_strict_flags_unexpected_violation_but_tolerates_need_human():
    pack = load_rulepack(PACK)
    c = load_case(CASES / "cases" / "L1-009-over-max-price.yaml", pack)
    c.strict = True
    # 只给 4 个字段:其余规则缺字段→need_human(不进 strict 余量);L1-009 违规=期望内
    res = await run_case(c, pack)
    assert res.ok, res.diff_lines
    # 再塞一个期望外 violation 触发源 → strict 红
    c.fields["tender.max_price"] = 999999.0  # 另造 L1-014 违规(duration 缺失→need_human,此行仅示意)
    c.fields["bid.duration_main_text"] = 999  # L1-014: lte 违规且输入齐备
    res2 = await run_case(c, pack)
    assert not res2.ok and any("期望外" in m for m in res2.diff_lines)


@pytest.mark.asyncio
async def test_expect_absent_and_severity_mismatch():
    pack = load_rulepack(PACK)
    c = load_case(CASES / "cases" / "L1-009-over-max-price.yaml", pack)
    c.expect_absent = ["L1-009"]  # 必然违例(该题 L1-009 必报)
    res = await run_case(c, pack)
    assert any("L1-009" in m and "不应报" in m for m in res.diff_lines)
    c2 = load_case(CASES / "cases" / "L1-009-over-max-price.yaml", pack)
    c2.expect_issues[0].severity = "minor"  # 实际 fatal
    res2 = await run_case(c2, pack)
    assert any("severity" in m for m in res2.diff_lines)


@pytest.mark.asyncio
async def test_acceptable_rule_ids_any_hit_counts():
    """等价规则集(spec §1.5):主 id 无触发、等价 id 命中 → 算 TP。"""
    from app.extensions.bid_review.golden.schema import Expectation, GoldenCase
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
    c = GoldenCase(case="mech-acceptable", desc="", fields=fields,
                   expect_issues=[Expectation(rule_id="L2-024", severity="fatal", contains=["1,000,001"], acceptable_rule_ids=["L1-009"])],
                   expect_absent=[], strict=False)
    res = await run_case(c, pack)
    assert res.ok and res.hits.get("L2-024") == 1, res.diff_lines


@pytest.mark.asyncio
async def test_entity_disambiguation_filters_per_entity_issues():
    """实体消歧(spec §1.5):entity 子串不匹配的条目不能顶替命中。"""
    from app.extensions.bid_review.golden.schema import Expectation, GoldenCase
    pack = load_rulepack(PACK)
    fields = {
        "tender.attachment_requirements": [
            {"no": "E-1", "name": "业绩合同", "min_count": 1},
            {"no": "E-2", "name": "中标通知书", "min_count": 1},
        ],
        "bid.attachment_index": [{"no": "E-1", "name": "业绩合同", "pages": [1, 2]}],
    }
    c = GoldenCase(case="mech-entity", desc="", fields=fields,
                   expect_issues=[Expectation(rule_id="L2-020", severity="fatal", contains=["E-2"], entity="E-2")],
                   expect_absent=[], strict=False)
    res = await run_case(c, pack)
    assert res.ok, res.diff_lines
    c2 = GoldenCase(case="mech-entity2", desc="", fields=fields,
                    expect_issues=[Expectation(rule_id="L2-020", severity="fatal", contains=["E-2"], entity="E-9")],
                    expect_absent=[], strict=False)
    res2 = await run_case(c2, pack)
    assert not res2.ok  # E-9 条目不存在 → 期望必须 miss(entity 过滤生效)
```

- [ ] **Step 2: 跑失败**（ModuleNotFoundError: runner）。

- [ ] **Step 3: 实现 runner.py**：

```python
"""金标准评测核(EAI-CUSTOM 2026-11-03,spec §6/§7):case → evaluate_fields(共享
分派核,禁复制循环)→ 期望对表 → CaseResult。判定顺序:expect_issues 按 rule_id
分桶逐条消化(verdict 分桶,severity+contains 全对才算命中)→ expect_absent 查违例
→ strict 只数期望外 verdict=violation。scripted model_fn:按规则卡「规则:<id>」
路由 model_script;缺省回安静 full 应答(零条目;hyb 候选被 full 驳回→零产出)。"""
import json

from app.extensions.bid_review.engine.attachments import build_checklist
from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.rule_runner import RulePack, load_rulepack
from app.extensions.bid_review.golden.loader import RULEPACK_PATH
from app.extensions.bid_review.golden.schema import CaseResult, GoldenCase

_QUIET = json.dumps(
    {"verdicts": [{"clause_id": "golden-quiet", "verdict": "full", "confidence": 1.0, "reason": "golden 默认安静应答", "evidence": [{"doc_id": "golden", "page": 1}]}]},
    ensure_ascii=False,
)


def _scripted_model(case: GoldenCase):
    table = case.model_script

    def model(messages):
        card = messages[0]["content"] if isinstance(messages, list) else str(messages)
        for rid, resp in table.items():
            if f"规则:{rid}" in card:
                return resp
        return _QUIET

    return model


def _rule_pool(expect, issues: list[dict]) -> list[dict]:
    ids = {expect.rule_id, *expect.acceptable_rule_ids}
    return [i for i in issues if i["rule_id"] in ids]


def _issue_matches(expect, i: dict) -> bool:
    """entity(子串对 entity_keys+message) + severity + contains 全对才算命中(spec §1.5)。"""
    if expect.entity and expect.entity not in " ".join([*(i.get("entity_keys") or []), str(i.get("message") or "")]):
        return False
    if expect.severity and i.get("severity") != expect.severity:
        return False
    return all(kw in str(i.get("message") or "") for kw in expect.contains)


def _status_for(expect, issues: list[dict]) -> str:
    """命中 | verdict | severity | contains | missing——判定梯度:每级只差一个维度,
    diff 行直接指出错的是哪个维度(verdict 不符=state mismatch 单列可见,spec §1.5)。"""
    pool = _rule_pool(expect, issues)
    ok = [i for i in pool if i.get("verdict") == expect.verdict]
    if any(_issue_matches(expect, i) for i in ok):
        return "命中"
    if any(_issue_matches(expect, i) for i in pool):
        return "verdict"  # 规则/实体/关键词全对但态判错(state mismatch)
    if any(i.get("verdict") == expect.verdict and expect.severity and i.get("severity") == expect.severity for i in pool):
        return "contains"
    if any(i.get("verdict") == expect.verdict for i in pool):
        return "severity"
    return "missing"


async def run_case(case: GoldenCase, pack: RulePack | None = None) -> CaseResult:
    pack = pack or load_rulepack(RULEPACK_PATH)
    issues = await evaluate_fields(pack, case.fields, model_fn=wrap_model_fn(_scripted_model(case)))
    missing: list[str] = []
    consumed: set[int] = set()
    hits: dict[str, int] = {}
    for e in case.expect_issues:
        st = _status_for(e, issues)
        if st == "命中":
            for idx, i in enumerate(issues):
                if idx not in consumed and i["rule_id"] in {e.rule_id, *e.acceptable_rule_ids} and _issue_matches(e, i) and i.get("verdict") == e.verdict:
                    consumed.add(idx)
                    hits[e.rule_id] = hits.get(e.rule_id, 0) + 1
                    break
            continue
        tag = {"missing": "未命中", "verdict": "verdict 不符(state mismatch)", "severity": "severity 不符", "contains": "关键词未命中"}[st]
        missing.append(f"期望未命中[{e.rule_id} {e.severity} {e.verdict}] {tag}: contains={e.contains}")
    absent = [f"不应报而报[{rid}](expect_absent): {next((i['message'][:60] for i in issues if i['rule_id'] == rid), '')}" for rid in case.expect_absent if any(i["rule_id"] == rid and i.get("verdict") == "violation" for i in issues)]
    unexpected: list[str] = []
    if case.strict:
        for idx, i in enumerate(issues):
            if idx in consumed or i.get("verdict") != "violation":
                continue
            unexpected.append(f"期望外 violation[{i['rule_id']} {i['severity']}]: {str(i.get('message'))[:80]}")
    cl_diff: list[str] = []
    if case.checklist is not None:
        cl = build_checklist(case.fields.get("tender.attachment_requirements"), case.fields.get("bid.attachment_index"))
        got_unknown = int((cl.get("counts") or {}).get("unknown") or 0)
        if got_unknown != case.checklist.unknown_count:
            cl_diff.append(f"checklist.counts.unknown 实际 {got_unknown} ≠ 期望 {case.checklist.unknown_count}")
        for no, want in case.checklist.status_by_no.items():
            got = next((r.get("status") for r in cl.get("items") or [] if str((r.get("req") or {}).get("no")) == no), None)
            if got != want:
                cl_diff.append(f"checklist[{no}].status 实际 {got} ≠ 期望 {want}")
    ok = not (missing or unexpected or absent or cl_diff)
    return CaseResult(case=case.case, desc=case.desc, strict=case.strict, ok=ok, missing=missing, unexpected=unexpected, absent_violations=absent, checklist_diff=cl_diff, hits=hits, n_issues=len(issues))


async def run_all(cases: list[GoldenCase], pack: RulePack | None = None) -> list[CaseResult]:
    pack = pack or load_rulepack(RULEPACK_PATH)
    return [await run_case(c, pack) for c in cases]
```

实现注记：命中语义 =「规则 ∈ 主 id ∪ acceptable_rule_ids + verdict + entity + severity + contains 全对」；`_status_for`/消化循环若与测试断言冲突，以此语义为准调实现，**不得放松测试**。

- [ ] **Step 4: runner 测试绿**（4 过）+ loader 测试仍绿。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/golden/runner.py backend/tests/test_bid_review_golden.py
git commit -m "feat(bid-review): golden runner diff 引擎——verdict 分桶消化+expect_absent+strict(仅数期望外 violation)+checklist 期望(spec §6/§7)"
```

---

### Task 4: pytest 回归门 + 覆盖率地板

**Files:**
- Test: `backend/tests/test_bid_review_golden.py`（追加回归门段）

- [ ] **Step 1: 追加回归门**（此时题库仅 1 题——覆盖率地板从 {L1-009} 起步，后续批次任务扩表）：

```python
# ---- 回归门:逐题参数化 + 覆盖率地板 ----
EXPECTED_COVERAGE = {"L1-009"}  # 每批次任务扩此表;收尾任务改为 == 全 34 条(pack ids 精确相等)


@pytest.mark.parametrize("path", sorted(CASES.glob("cases/*.yaml")), ids=lambda p: p.stem)
async def test_golden_case(path):
    pack = load_rulepack(PACK)
    res = await run_case(loader.load_case(path, pack), pack)
    assert res.ok, "\n".join(res.diff_lines)


def test_rule_coverage_floor():
    pack = load_rulepack(PACK)
    # 只数主 rule_id;acceptable_rule_ids 是等价别名,不计地板(防靠别名凑覆盖,spec §1.5)
    covered = {e.rule_id for c in loader.load_cases() for e in c.expect_issues}
    pack_ids = {r.id for r in pack.rules}
    missing_floor = EXPECTED_COVERAGE - covered
    assert not missing_floor, f"覆盖率地板未达成: {sorted(missing_floor)}"
    unknown = covered - pack_ids
    assert not unknown, f"题库引用了不存在的规则: {sorted(unknown)}"


def test_coverage_complete_marker():
    """收尾后(EXPECTED_COVERAGE == pack 全集)此测试钉死精确相等;现阶段跳过。"""
    pack = load_rulepack(PACK)
    if EXPECTED_COVERAGE != {r.id for r in pack.rules}:
        pytest.skip("题库未收满,精确相等断言待收尾任务启用")
    covered = {e.rule_id for c in loader.load_cases() for e in c.expect_issues}
    assert covered == {r.id for r in pack.rules}
```

asyncio 参数化标记与文件内既有 async 测试写法一致（repo asyncio_mode 形态）。回归门此刻应全绿（样例题 ok + 地板 {L1-009} 达成）。

- [ ] **Step 2: 全绿** + **Step 3: Commit**

```bash
git add backend/tests/test_bid_review_golden.py
git commit -m "test(bid-review): 金标准回归门——逐题参数化+覆盖率地板 EXPECTED_COVERAGE(收尾任务翻全集精确相等)"
```

---

### Task 5: report.py + CLI（`__main__.py`）

**Files:**
- Create: `backend/app/extensions/bid_review/golden/report.py`、`backend/app/extensions/bid_review/golden/__main__.py`
- Test: `backend/tests/test_bid_review_golden.py`（追加 report/CLI 段）

- [ ] **Step 1: 追加失败测试**：

```python
# ---- report + CLI ----
from app.extensions.bid_review.golden.report import build_report, render_markdown


def test_report_counts_and_markdown():
    from app.extensions.bid_review.golden.schema import CaseResult
    results = [
        CaseResult(case="a", desc="", strict=False, ok=True, missing=[], unexpected=[], absent_violations=[], checklist_diff=[], hits={"L1-009": 1}),
        CaseResult(case="b", desc="", strict=False, ok=False, missing=["期望未命中[L1-009 fatal violation] 未命中: contains=['x']"], unexpected=[], absent_violations=["不应报而报[L1-011]"], checklist_diff=[]),
    ]
    rep = build_report(results)
    assert rep["total"] == 2 and rep["failed"] == 1
    assert rep["per_rule"]["L1-009"]["tp"] == 1 and rep["per_rule"]["L1-009"]["fn"] == 1
    assert rep["per_rule"]["L1-011"]["absent_fp"] == 1
    md = render_markdown(rep)
    assert "| 规则 | TP | FN | 误报(absent) |" in md and "L1-009" in md and "FAIL" in md


def test_report_zero_hit_flag():
    """有题引用但四类计数全 0 → zero_hit 死规则告警(spec §1.5)。"""
    from app.extensions.bid_review.golden.schema import CaseResult, Expectation, GoldenCase
    res = CaseResult(case="a", desc="", strict=False, ok=True, missing=[], unexpected=[], absent_violations=[], checklist_diff=[])
    c = GoldenCase(case="a", desc="", fields={}, expect_issues=[Expectation(rule_id="L1-001", severity="fatal")], expect_absent=[])
    rep = build_report([res], [c])
    assert rep["per_rule"]["L1-001"]["zero_hit"] is True


def test_cli_main_exit_codes(tmp_path, capsys):
    from app.extensions.bid_review.golden.__main__ import main
    out = tmp_path / "rep.json"
    rc = main(["--report", "md", "--out", str(out)])
    assert rc == 0 and out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] >= 1
```

- [ ] **Step 2: 跑失败 → Step 3: 实现**：

`report.py`：

```python
"""成绩单聚合与渲染(EAI-CUSTOM 2026-11-03,spec §7):信息型,不进 CI 强制。
per_rule 键:tp=期望命中题数/fn=期望未命中/absent_fp=expect_absent 违例/
unexpected=strict 期望外。"""
from app.extensions.bid_review.golden.schema import CaseResult


def build_report(results: list[CaseResult], cases: list[GoldenCase] | None = None) -> dict:
    per: dict[str, dict] = {}
    for r in results:
        for rid, n in (r.hits or {}).items():  # tp 来自 runner 消化命中计数
            per.setdefault(rid, {"tp": 0, "fn": 0, "absent_fp": 0, "unexpected": 0})["tp"] += n
        for line in r.missing:
            rid = line.split("[", 1)[1].split("]", 1)[0].split()[0]
            per.setdefault(rid, {"tp": 0, "fn": 0, "absent_fp": 0, "unexpected": 0})["fn"] += 1
        for line in r.absent_violations:
            rid = line.split("[", 1)[1].split("]", 1)[0]
            per.setdefault(rid, {"tp": 0, "fn": 0, "absent_fp": 0, "unexpected": 0})["absent_fp"] += 1
        for line in r.unexpected:
            rid = line.split("[", 1)[1].split("]", 1)[0].split()[0]
            per.setdefault(rid, {"tp": 0, "fn": 0, "absent_fp": 0, "unexpected": 0})["unexpected"] += 1
    referenced: set[str] = set()
    for c in cases or []:
        referenced.update(e.rule_id for e in c.expect_issues)
        referenced.update(c.expect_absent)
    for rid in referenced:
        m = per.setdefault(rid, {"tp": 0, "fn": 0, "absent_fp": 0, "unexpected": 0})
        m["zero_hit"] = (m["tp"] + m["fn"] + m["absent_fp"] + m["unexpected"]) == 0  # 死规则/题失效告警(spec §1.5 采纳)
    return {"total": len(results), "failed": sum(1 for r in results if not r.ok), "per_rule": per, "results": [r.__dict__ for r in results]}


def render_markdown(rep: dict) -> str:
    lines = ["# 金标准成绩单", "", f"题数 {rep['total']} | 失败 {rep['failed']}", "", "| 规则 | TP | FN | 误报(absent) | 期望外(strict) | zero_hit |", "|---|---|---|---|---|---|"]
    for rid in sorted(rep["per_rule"]):
        m = rep["per_rule"][rid]
        lines.append(f"| {rid} | {m['tp']} | {m['fn']} | {m['absent_fp']} | {m['unexpected']} | {m.get('zero_hit', '')} |")
    lines.append("")
    for r in rep["results"]:
        mark = "PASS" if r["ok"] else "FAIL"
        lines.append(f"- {mark} {r['case']}" + ("" if r["ok"] else "：" + "；".join(r["missing"] + r["unexpected"] + r["absent_violations"] + r["checklist_diff"])))
    return "\n".join(lines) + "\n"
```

tp 来源：`CaseResult.hits`（Task 2 schema 已定义，Task 3 run_case 消化命中时累计）在 build_report 开头并入 `tp`；`zero_hit` 需要 cases 里的引用关系（expect_issues ∪ expect_absent），故 CLI 传 `build_report(results, cases)`。

`__main__.py`：

```python
"""CLI 成绩单入口(EAI-CUSTOM 2026-11-03):python -m app.extensions.bid_review.golden
--report md [--out report.json]。加载失败/有题失败 → exit 1,成绩单仍完整输出(spec §11)。"""
import argparse
import asyncio
import sys

from app.extensions.bid_review.golden.loader import load_cases
from app.extensions.bid_review.golden.report import build_report, render_markdown
from app.extensions.bid_review.golden.runner import run_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="golden")
    ap.add_argument("--report", default="md", choices=["md"])
    ap.add_argument("--out", default=None, help="JSON 落盘路径")
    args = ap.parse_args(argv)
    try:
        cases = load_cases()
    except Exception as exc:  # noqa: BLE001
        print(f"题库加载失败: {exc}", file=sys.stderr)
        return 1
    results = asyncio.run(run_all(cases))
    rep = build_report(results, cases)
    print(render_markdown(rep))
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(__import__("json").dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 全绿（此时题库 1 题全过 → CLI rc=0）→ Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/golden/report.py backend/app/extensions/bid_review/golden/__main__.py backend/app/extensions/bid_review/golden/schema.py backend/app/extensions/bid_review/golden/runner.py backend/tests/test_bid_review_golden.py
git commit -m "feat(bid-review): golden 成绩单聚合+CLI——per_rule tp/fn/absent_fp/unexpected,markdown+JSON,exit code 语义(spec §7/§11)"
```

---

### Task 6: 全管线冒烟 runner + smoke-1-basic 题

**Files:**
- Modify: `backend/app/extensions/bid_review/golden/runner.py`（追加 `run_smoke_dir`）
- Create: `backend/app/extensions/bid_review/golden/smoke/smoke-1-basic/{case.yaml, extract_stub.yaml, docs/tender.md, docs/bid.md}`
- Test: `backend/tests/test_bid_review_golden.py`（追加 smoke 段）

- [ ] **Step 1: 失败测试**：

```python
# ---- 全管线冒烟(spec §8):钉接线,不钉 LLM ----
from app.extensions.bid_review.engine.extract import build_baseline
from app.extensions.bid_review.golden.runner import run_smoke_dir

SMOKE = CASES / "smoke"


def test_smoke_docs_fixture_and_stub_extract():
    fields = run_smoke_dir._fields_from_stub(SMOKE / "smoke-1-basic")
    assert fields.get("bid.total_price") == 1000001.0


@pytest.mark.asyncio
async def test_smoke_pipeline_end_to_end():
    pack = load_rulepack(PACK)
    res = await run_smoke_dir(SMOKE / "smoke-1-basic", pack)
    assert res.ok, res.diff_lines
```

- [ ] **Step 2: 失败 → Step 3: runner 追加**：

```python
def _fields_from_stub(smoke_dir):
    """冒烟题字段构造:docs 目录 md 文件 → docs 列表;extract_stub.yaml 平映射充当
    extract_fn(docs, field_paths)(spec §8:钉管线接线,LLM 不进 CI 门)。"""
    from app.extensions.bid_review.engine.extract import build_baseline
    d = Path(smoke_dir)
    docs = []
    for name, role in (("tender.md", "tender"), ("bid.md", "bid")):
        p = d / "docs" / name
        if p.exists():
            docs.append({"doc_id": name, "role": role, "text": p.read_text(encoding="utf-8")})
    stub = yaml.safe_load((d / "extract_stub.yaml").read_text(encoding="utf-8"))
    payload = build_baseline(docs, lambda _docs, _paths: {k: v for k, v in stub.items() if k in set(_paths)})
    return payload["fields"]


async def run_smoke_dir(smoke_dir, pack: RulePack | None = None) -> CaseResult:
    """冒烟题 = build_baseline(extract_stub) 产字段 → 复用 run_case 同一断言核。"""
    from app.extensions.bid_review.golden.loader import load_case
    pack = pack or load_rulepack(RULEPACK_PATH)
    case = load_case(Path(smoke_dir) / "case.yaml", pack)
    case.fields = _fields_from_stub(smoke_dir)
    return await run_case(case, pack)
```

（文件顶部补 `from pathlib import Path` 与 `import yaml`。）

- [ ] **Step 4: 冒烟夹具**：

`smoke/smoke-1-basic/docs/tender.md`：

```markdown
# 招标文件（金标准冒烟夹具）
## 投标人须知
投标报价不得高于最高限价人民币 1,000,000 元。
## 附件清单
应提供：E-1 业绩合同（1 份）；E-2 中标通知书（1 份）。
```

`smoke/smoke-1-basic/docs/bid.md`：

```markdown
# 投标文件（金标准冒烟夹具）
## 报价
投标总价：1,000,001 元（含税）。
## 附件清单
E-1 业绩合同（见第 12-18 页）。
```

`smoke/smoke-1-basic/extract_stub.yaml`（平映射；模拟「抽取层把原文变成字段」）：

```yaml
bid.total_price: 1000001.0
tender.max_price: 1000000.0
bid.price_includes_tax: true
tender.price_includes_tax: true
tender.attachment_requirements:
  - {no: E-1, name: 业绩合同, min_count: 1}
  - {no: E-2, name: 中标通知书, min_count: 1}
bid.attachment_index:
  - {no: E-1, name: 业绩合同, pages: [12, 18]}
```

`smoke/smoke-1-basic/case.yaml`（字段键留空——由 stub 产出；断言同字段层题）：

```yaml
case: L1-009-smoke-basic
desc: 全管线冒烟:docs→stub 抽取→规则→L1-009 fatal + L2-020 附件缺失 E-2
fields: {}
expect_issues:
  - {rule_id: L1-009, severity: fatal, contains: ["1,000,001"]}
  - {rule_id: L2-020, severity: fatal, contains: ["E-2"]}
expect_absent: []
strict: false
```

- [ ] **Step 5: smoke 测试绿 → Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/golden/runner.py backend/app/extensions/bid_review/golden/smoke backend/tests/test_bid_review_golden.py
git commit -m "feat(bid-review): 全管线冒烟 smoke-1-basic——docs 夹具+extract_stub 钉接线(build_baseline→evaluate_fields 同核断言,spec §8)"
```

---

### Task 7: 建库批 A —— L1 层 20 题（含 sem/hyb 3 题 model_script）

**Files:**
- Create: `golden/cases/L1-*.yaml` ×20
- Modify: `backend/tests/test_bid_review_golden.py`（`EXPECTED_COVERAGE` 加 L1 全部 20 id）
- Modify: `golden/CALIBRATION.md`（新建，记每题裁决）

- [ ] **Step 0: 校准流程声明（写入 CALIBRATION.md 头部）**：

```markdown
# 建库校准记录

流程(spec §9):每题①按 trigger 表构造最小字段 → ②跑引擎取现输出起草 expect_issues →
③逐处 diff 裁决:引擎对→修标注 / 标注对→修引擎 bug(buglog 记录,此处记编号与结论) →
④入库后该题必须绿。裁决格式:`| case | 裁决 | 结论/bug编号 |`

## 四态判定决策表(L2 专项题裁决依据,口径唯一,spec §1.5 采纳)

| 事实 | 金标准态 |
|---|---|
| 检索过且确认不存在 | MISSING |
| 存在但子件/份数不足 | PARTIAL |
| 存在且齐备 | MATCHED(PRESENT) |
| 解析失败/分组失败/语义低置信 | UNKNOWN(引擎侧=need_human) |
| 抽取失败被误判为缺失 | 标注错误示范,不入库(记录进培训集) |
```

- [ ] **Step 1: 逐题建 YAML**。完整样例两道（其余按表+同构）：

det 例（`L1-002-qual-level-low.yaml`）：

```yaml
case: L1-002-qual-level-low
desc: 投标资质等级低于要求 → L1-002 violation
fields:
  bid.qual_levels: ["资质等级三级"]
  tender.required_qual_level: "资质等级一级"
expect_issues:
  - {rule_id: L1-002, severity: fatal, contains: ["资质等级"]}
expect_absent: []
strict: false
```

sem 例（`L1-013-substantive-clause.yaml`，model_script 按规则卡路由；script JSON 必须过 check_schema——verdict∈该规则 verdict_set，evidence.page 正整数）：

```yaml
case: L1-013-substantive-clause
desc: 实质性条款响应偏离 → L1-013 semantic violation(scripted model 应答 partial)
fields:
  tender.substantive_clauses:
    - {id: "★1", text: "工期不得超过 180 日历天"}
    - {id: "★2", text: "须为原厂投标"}
model_script:
  L1-013: '{"verdicts": [{"clause_id": "★1", "verdict": "partial", "confidence": 0.9, "reason": "响应偏离", "evidence": [{"doc_id": "bid.pdf", "page": 3, "text": "工期 200 日历天"}]}]}'
expect_issues:
  - {rule_id: L1-013, severity: major, contains: ["★1"]}
expect_absent: []
strict: false
```

severity 以该规则 yaml 实际 `severity` 为准（起草时从 rulepack 读，勿臆造）。

**L1 层 20 题 trigger 表**（fields 构造要点；inputs 照抄 rulepack，构造=使 inputs 齐备且判定 FAIL；`？`=起草时从 rulepack 对应规则 yaml 读 check 表达式确认触发条件）：

| rule_id | type | inputs | 触发构造要点 |
|---|---|---|---|
| L1-001 | det | license_valid_until/bid_deadline/business_scope/bid_scope | 执照有效期早于投标截止；scope 词集不交 |
| L1-002 | det | qual_levels/required_qual_level | 等级低于要求（样例已给） |
| L1-003 | hyb | similar_performances/min_similar_performance_count | 业绩数 < 要求 → 候选；script=partial 确认 |
| L1-005 | det | validity_days/required_validity_days | 有效期天数 < 要求 |
| L1-006 | det | deposit_amount/deposit_required | 金额不等 |
| L1-007 | hyb | missing_signature_pages | 非空 → 候选；script=partial |
| L1-008 | det | authorization_letter_present/authorization_signatory/bid_letter_signatory | 授权签署人与投标函不一致 |
| L1-009 | det | （样例题已有） | — |
| L1-010 | det | detail_rows/subtotal/total_price/total_price_words | 明细合计≠总价（大写不一致可选触发） |
| L1-011 | det | boq_items(tender/bid) | set_eq：bid 缺 tender 某清单项 |
| L1-012 | det | tax_rate_occurrences/tax_rate | 出现处含≠要求税率 |
| L1-013 | sem | substantive_clauses | script=partial（样例已给） |
| L1-014 | det | duration_main_text/max_duration | 工期 > 上限 |
| L1-015 | det | warranty_period/min_warranty_period | 质保 < 下限 |
| L1-016 | det | entity_name_occurrences/license_name | 出现名称含非执照名项 |
| L1-019 | det | alternative_price_offers | 非空备选报价 |
| L1-021 | det | required_declarations/declaration_letter_codes | 必备声明函缺一项 |
| L1-003/L1-007/L1-013 | （上三行已含） | | |

（表计 17 行 + L1-009 样例 = 18……实现者注意：L1 全集 = 上表并集去重共 **20 个 id**，缺漏以 rulepack 实际 L1 id 清单为准——`{r.id for r in pack.rules if r.layer=="L1"}`，逐个建题，禁漏。）

**A 家族干净基线 ×3**（`A-clean-l1-price.yaml` / `A-clean-l1-qual.yaml` / `A-clean-l1-mixed.yaml`；`strict: true` + `expect_issues: []` → 任何 violation 即红，need_human 不计余量，sem/hyb 默认安静应答天然零产出——FP 探针，spec §1.5/§5.5）。样例：

```yaml
case: A-clean-l1-price
desc: 干净基线——价格族全达标,期望零 violation(A 家族 FP 探针)
fields:
  bid.total_price: 980000.0
  tender.max_price: 1000000.0
  bid.price_includes_tax: true
  tender.price_includes_tax: true
  bid.detail_rows:
    - {name: 设备A, qty: 2, price: 400000.0, total: 800000.0}
    - {name: 设备B, qty: 1, price: 180000.0, total: 180000.0}
  bid.subtotal: 980000.0
  bid.total_price_words: "玖拾捌万元整"
expect_issues: []
expect_absent: []
strict: true
```

（steps 表达式以 rulepack check 为准起草；校准时 A 题若红，逐条裁决是引擎误报还是字段夹具不达标——这正是 A 族的价值。）

- [ ] **Step 2: 校准循环** —— 每题：`PYTHONPATH=. uv run python -c "import asyncio,json;from app.extensions.bid_review.golden.loader import load_case;from app.extensions.bid_review.golden.runner import run_case;from app.extensions.bid_review.engine.rule_runner import load_rulepack;print(json.dumps([i for i in asyncio.run(run_case(load_case('<path>'),load_rulepack()) and [] ) ] ))"` 不可用时直接写临时脚本跑 `evaluate_fields` 打印 issues → 起草 expect → 裁决 → 改 YAML。裁决逐题记入 CALIBRATION.md；真 bug 走 buglog 并在题库外修（不得为过题改生产代码——**金标准独立性铁律**：只有"标注错"才改 YAML，"引擎错"须先修引擎再让题绿）。
- [ ] **Step 3: EXPECTED_COVERAGE 扩表** —— 测试文件里并入 L1 全 20 id；`pytest tests/test_bid_review_golden.py` 全绿。
- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/bid_review/golden/cases backend/app/extensions/bid_review/golden/CALIBRATION.md backend/tests/test_bid_review_golden.py
git commit -m "test(bid-review): 金标准批A——L1 层 20 题入库校准(含 sem/hyb 3 题 model_script),覆盖率地板扩至 L1 全集"
```

---

### Task 8: 建库批 B —— L3 层 16 题（含 hybrid L3-004/L3-008 script）

同 Task 7 流程与铁律。L3 id 全集以 `{r.id for r in pack.rules if r.layer=="L3"}` 为准（16 个）。trigger 要点（inputs 照 rulepack）：

| rule_id | type | 触发构造要点 |
|---|---|---|
| L3-001 | det | 投标页眉页脚项目名/编号 ≠ tender.project_identity |
| L3-002 | det | tenderee_name_mentions 含不一致项（all 量词：任一行≠招标人名） |
| L3-003 | det | license_name ≠ bid_letter 署名 或 白名单外 |
| L3-004 | hyb | old_project_mentions 白名单外 → 候选；script=partial |
| L3-005 | det | 三处工期文本不一致 |
| L3-006 | det | amount_occurrences 含≠总价项 |
| L3-007 | det | 商务/技术人员 set_eq 差集 |
| L3-008 | hyb | device_model_mismatches 非空 → 候选；script=partial |
| L3-009 | det | schedule 起止 vs commitment 完成日冲突 |
| L3-010 | det | boq_unit_checks 含失败行 |
| L3-012 | det | appendix_references 缺引用 |
| L3-013 | det | required_sections 编码不在 toc_section_codes |
| L3-014 | det | 函件日期晚于 bid_deadline 等 steps 违反 |
| L3-016 | det | version_tag_occurrences 含≠document_version |
| L3-018 | det | currency_occurrences 含≠tender.currency |

EXPECTED_COVERAGE 并入 L3 全 16 id；全绿；Commit：

```bash
git add backend/app/extensions/bid_review/golden/cases backend/app/extensions/bid_review/golden/CALIBRATION.md backend/tests/test_bid_review_golden.py
git commit -m "test(bid-review): 金标准批B——L3 层 16 题入库校准(含 hybrid 2 题 script),覆盖率地板扩至 L1+L3"
```

---

### Task 9: 建库批 C —— L2 专项 strict 题 + E 族达标负例（×6）

**Files:**
- Create: `golden/cases/L2-*.yaml`（≥8）+ `golden/cases/FP-suppress-*.yaml`（≥2）
- Modify: 测试文件 `EXPECTED_COVERAGE`（L2-020/L2-024 并入；此处改**精确相等**断言启用：删 `test_coverage_complete_marker` 的 skip 分支，直接断言 `covered == pack_ids`）

L2 专项题清单（全部 `strict: true`；strict 断言=期望内消化后**零期望外 violation**；need_human 不进余量）：

1. `L2-020-missing-attachment`（spec §5 原题）——缺 E-2 → fatal MISSING，contains ["E-2"]
2. `L2-020-matched-clean.yaml` —— E-1/E-2 全命中 → 零 L2 条目；checklist: {unknown_count: 0, status_by_no: {E-1: MATCHED, E-2: MATCHED}}
3. `L2-020-unknown-group-failure.yaml` —— 复合件孤儿（req 带 sub_items 而 bid 侧零引用）→ expect verdict=need_human contains ["无法自动分组"]；checklist unknown_count ≥1
4. `L2-020-subitems-three-channel.yaml` —— 编号精确/编号模糊/名称归一 三子件各一（复用 P2 语义）
5. `L2-024-count-insufficient.yaml` —— min_count 2 实供 1 → major 份数不足
6. `L2-024-count-unknown-clamp.yaml` —— UNKNOWN 不计份数（att_count 钳位）
7. `L2-cross-dedup-keep-most-severe.yaml` —— 同一附件实体同触 L2-020(fatal) 与 L2-024(major)：expect_issues 断 L2-020 fatal 命中；list 端点投影的 related_issues 不在 runner 断言面（纯函数面），checklist 断言 unknown_count=0
8. `L2-020-flat-no-subnote.yaml` —— 平件（无 sub_items）无 UNKNOWN、无子件注（P2 回归）

E 族达标负例 ×6（非 strict；expect_issues 尽量空、expect_absent 点名——「近似但不该报」；E 与 B 等量级才不虚高精确率，spec §1.5/§5.5）：

9. `E-l1-005-validity-satisfied.yaml` —— validity=要求 → expect_absent: [L1-005]
10. `E-l1-009-within-max.yaml` —— 总价=限价 → expect_absent: [L1-009]
11. `E-l1-015-warranty-equal.yaml` —— 质保=下限 → expect_absent: [L1-015]
12. `E-l1-019-no-alternative.yaml` —— 备选报价为空 → expect_absent: [L1-019]
13. `E-l3-016-version-consistent.yaml` —— 版本出现处全一致 → expect_absent: [L3-016]
14. `E-l2-020-all-matched.yaml` —— 附件全齐备 → expect_absent: [L2-020, L2-024]

（P2 语义细节以 `backend/tests/test_bid_review_attachments.py`/`test_bid_review_grouping.py` 既有断言为连线事实；sub_items 字段形状照抄该处夹具。）

全绿（此时 `EXPECTED_COVERAGE == pack ids` 精确相等生效）→ Commit：

```bash
git add backend/app/extensions/bid_review/golden/cases backend/app/extensions/bid_review/golden/CALIBRATION.md backend/tests/test_bid_review_golden.py
git commit -m "test(bid-review): 金标准批C——L2 专项 strict 题(四态/子件三通道/去重 keep most_severe/钳位)+E 族达标负例×6,覆盖率翻全集精确相等"
```

---

### Task 10: 收尾（controller 执行，不派实现者）

- [ ] 全量：`PYTHONPATH=. uv run pytest tests/ -k "bid_review" -q --ignore=test_dept_fix.py --ignore=test_full_pipeline.py` 全绿（基线 258+6 skip + 新增）；ruff 全域自扫清零。
- [ ] CLI 实跑一次：`PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md` → 34 规则每行可见、`failed 0`、exit 0；`--out $CLAUDE_JOB_DIR/tmp/golden-report.json` 留档。
- [ ] CALIBRATION.md 裁决表完整（每题一行）；真 bug 已走 buglog。
- [ ] wolf 记账（memory/anatomy 新文件条目）；controller push：`until git push origin main-dev-fork 2>&1; do sleep 15; done` → `git rev-list --left-right --count origin/main-dev-fork...main-dev-fork` 必须输出 `0\t0`。
- [ ] 终审（superpowers:code-reviewer）范围 = 金标准计划基点 commit → HEAD；后走 finishing-a-development-branch（直接落 main-dev-fork 已推 = 等效 Option 3）。

## Self-Review 结论（已跑）

1. **Spec 覆盖**：§3 目录→File Structure；§4→T1；§5→T2；§6→T3（verdict 分桶/strict 只数 violation = spec §6 歧关裁定）；§7→T3/T4/T5；§8→T6；§9→T7-9 Step 0/2；§10→T4 地板+T9 精确相等+T10；§11→loader fail-fast/runner 隔离透传/CLI exit；§1.5 对照采纳→T2(entity/acceptable/hits 字段)+T3(梯度判定+两机制测试)+T5(zero_hit)+T7(A 族×3+CALIBRATION 四态决策表)+T9(E 族×6)——全覆盖。
2. **占位符扫描**：T1 Step 3 两处「原文搬入」是既有代码的移动而非新写占位（源行号已给）；T7 表 `？` 项为"起草时从 rulepack 读"的显式指令而非 TBD；其余步骤均含完整内容。
3. **类型一致性**：`CaseResult.hits` 已在 T2 schema 定义、T3 run_case 累计、T5 build_report 消费（无回改点）；`_rule_pool`/`_issue_matches`/`_status_for` 命名前后一致；`run_smoke_dir`/`_fields_from_stub` 命名前后一致；`build_report(results, cases)` 签名与 `__main__` 调用一致；`EXPECTED_COVERAGE` 生命周期（T4 地板→T7/8/9 扩表→T9 翻精确）闭环；覆盖率地板只数主 rule_id（acceptable_rule_ids 不计——schema 注释+T4 注释+spec §5.5 三处一致）。
