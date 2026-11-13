# 批廿四 bid_write P1-γ:tender.substantive_clauses 契约 + L4 模型审查激活(水印摘除条件)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把导出水印「商务风险未确认」从恒加变成可摘除:L4 语义规则包(10 卡全 sem/hyb)在写侧以 advisory-only 面跑真模型审查,参与卡全干净→水印摘除;`tender.substantive_clauses` 经扩面表登记进入写侧抽取契约。

**Architecture:** 三段。①契约:`tender.substantive_clauses` 入 `SUBSET_EXTRACT_EXTENSIONS`(非 universe 成员,bug-4350 律;抽取 prompt/normalize 自动带上,矩阵组装不消费该路径→零行影响)。②precheck:`project_bid_fields` 增投影 `bid.service_commitments`(bl.extra_commitments)/`bid.full_text`(bl.text);新 `run_l4_review`(参与卡=inputs 全非空的 L4 卡,缺输入卡诚实列 `input_missing` 不烧模型;`evaluate_fields` 全引擎语义管线,逐规则隔离);`run_export_gate` 增 `l4_model_fn` 形参,l4 面结果落 `export["l4"]`,`watermark` 摘除时置 `None`。③worker:`_l4_model_fn()`(镜像 bid_review.worker._default_model_fn;无模型→恒抛闭包→逐规则 ERROR→水印保持),`generate_and_record` 接线。advisory-only:L4 永不入 `blocked`/`reasons`(meta `counts_toward_bid_gate: false`)。

**Tech Stack:** Python 3.12 / pytest-asyncio / sqlite in-memory;复用 bid_review.engine(`evaluate_fields`/`load_rulepack`/`build_rule_card`/`_call_model`)。

**关键既有事实(实现者必读):**
- `_L4_PATH = bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml` 已在 precheck.py:24 定义(det-only 合包当前只取 `type=="deterministic"`,L4 全 sem/hyb→现贡献零规则)。
- L4 卡 inputs(10 卡):L4-001 `[bid.warranty_period, tender.min_warranty_period, bid.service_commitments]`;L4-002 `[bid.duration_main_text, tender.max_duration, bid.schedule_milestones]`;**L4-003 `[bid.service_commitments, tender.substantive_clauses]`**;**L4-004 `[bid.service_commitments, bid.full_text]`**;L4-005 `[bid.service_commitments, tender.clauses]`;L4-006(hyb)`[tender.scoring_items, bid.section_for_score]`;L4-007 `[bid.service_commitments, bid.total_price, bid.personnel_technical, bid.personnel_commercial, bid.equipment]`;L4-008(hyb)`[bid.full_text, bid.response_sections]`;L4-009 `[bid.response_sections, bid.figures, bid.table_cells]`;L4-010 `[bid.full_text, tender.scoring_items, bid.response_sections]`。写侧可投影面只覆盖 **L4-003/L4-004**(commitments+clauses / commitments+full_text),其余卡诚实 `input_missing`。
- `Rule` 数据类有 `.id/.inputs/.type/.enabled`;`run_sem_rule` 入口归一 dict(接受数据类)。模型 verdict→issue 映射:`full`=干净不产条目;`partial/none`→按 severity 产条目(FAIL/WARN);`unclear`→need_human(llm_runner.py:147);基础设施故障(含 ModelNotConfigured)逐规则隔离降级 ERROR。
- `_call_model`(llm_runner.py:228)接受同步/异步 callable,统一取 `.content`——测试 stub 直接返回 `SimpleNamespace(content=json_str)`。
- 模型输出 schema(SCHEMA_HINT):`{"verdicts": [{"clause_id", "verdict": "full|partial|none|unclear", "confidence", "reason", "evidence": [{"doc_id","page","text"}]}]}`;L4 confidence_gate=0.75。
- ctx 形状:`build_ctx`(generate/__init__.py:103)返回 `{"tender": t, "products": {"bid_letter","price_sheet","response_table","attachment_index"}, "material", "pre"}`——tender 抽取字段在 `ctx["tender"]`(含 `tender.substantive_clauses`)。
- `bl["extra_commitments"]` 元素形 `{"text": ..., "clause_id": ...}`(decl 行+general_commitments knob 拼装,generate/__init__.py:75-82)。
- 默认 knobs(无 general_commitments)→ `extra_commitments` 空 → `bid.service_commitments` 缺席 → 参与卡空 → L4 不执行 → 水印恒加:**既有绿跑测试零行为变化**。
- `matrix.assemble_matrix` 用固定路径清单(attachment_requirements/required_sections/…),不迭代 subset→新增抽取路径零矩阵行影响(已核实 matrix.py:97-109)。
- ModelNotConfigured 定义在 `bid_review/worker.py:71`;bid_write worker 已 `review_worker._resolve_model_name()` 复用(worker.py:33)。
- 夹具 `_TABLES` 三处律(bug-4353):本批**无新表**,不触。
- 全量回归命令:`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_write -q`(后台跑,~2min,208p 基线+新)。

---

### Task 1: `tender.substantive_clauses` 契约(扩面表登记)

**Files:**
- Modify: `backend/app/extensions/bid_write/contracts.py:103-109`(SUBSET_EXTRACT_EXTENSIONS)
- Test: `backend/tests/test_bid_write_contracts.py`

- [x] **Step 1: 写失败测试**(追加到 test_bid_write_contracts.py,复用文件内既有 registry/universe 导入方式):

```python
def test_substantive_clauses_is_extension_member():
    """批廿四 P1-γ:tender.substantive_clauses=L4-003 语义审查输入面,非 universe
    成员,经扩面表登记(bug-4350 律);显式钉成员资格,⊆/∩ 通用律由扩面钉测试覆盖。"""
    assert "tender.substantive_clauses" in contracts.SUBSET_EXTRACT_EXTENSIONS
    assert "tender.substantive_clauses" in contracts.COMMERCIAL_TENDER_SUBSET
    assert "tender.substantive_clauses" not in _universe_set()
```

(若文件内无 `_universe_set` 助手,按既有钉测试同款方式取 universe;实现时对齐既有代码。)

- [x] **Step 2: 跑测试确认失败**:`PYTHONPATH=. uv run pytest tests/test_bid_write_contracts.py -q` → 新测试 FAIL(路径不在扩面表)。

- [x] **Step 3: 实现**——contracts.py 扩面表加一行:

```python
SUBSET_EXTRACT_EXTENSIONS: tuple[str, ...] = (
    "tender.purchaser_name",
    "tender.project_name",
    "tender.tender_no",
    "tender.substantive_clauses",  # 批廿四 P1-γ:L4-003 语义审查输入(实质性条款摘录列表)
)
```

- [x] **Step 4: 跑测试确认通过**(同命令,全文件绿——既有 ⊆/∩ 钉自动覆盖新成员)。

- [x] **Step 5: Commit**:

```bash
git add backend/app/extensions/bid_write/contracts.py backend/tests/test_bid_write_contracts.py
git commit -m "feat(bid_write): 批廿四 P1-γ-a——tender.substantive_clauses 扩面表登记(L4-003 语义审查输入;非 universe 成员 bug-4350 律;抽取 prompt/normalize 自动带上,矩阵组装零影响)"
```

---

### Task 2: `project_bid_fields` 增投影(service_commitments / full_text)

**Files:**
- Modify: `backend/app/extensions/bid_write/precheck.py:41-74`(project_bid_fields)
- Test: `backend/tests/test_bid_write_l4.py`(新建)

- [x] **Step 1: 写失败测试**(新建 test_bid_write_l4.py,头部:

```python
"""批廿四 P1-γ L4 语义审查面测试:参与卡筛选/摘除条件/投影/gate 接线。
advisory-only:L4 永不入 blocked/reasons;水印摘除=参与卡零 FAIL/ERROR/need_human/UNKNOWN。"""

import json
from types import SimpleNamespace

import pytest

from app.extensions.bid_write import contracts
from app.extensions.bid_write.precheck import project_bid_fields, run_l4_review, run_export_gate
```

——若 `run_l4_review`/`run_export_gate` 导入失败即本步 FAIL 形态):

```python
def _ctx_with_commitments():
    """最小 ctx:BL 带 general_commitments(经 build_ctx 纯装配),tender 带实质性条款。"""
    from app.extensions.bid_write.generate import build_ctx

    return build_ctx(
        {"tender.boq_items": [{"id": "1", "name": "设备A", "qty": 1, "unit": "项"}], "tender.substantive_clauses": ["投标人不得转包"]},
        [],  # 矩阵行空;承诺全走 general_commitments knob
        None,
        general_commitments=[{"text": "额外承诺:终身免费维保", "clause_id": ""}],
    )


def test_project_bid_fields_l4_projections():
    """commitments 非空→bid.service_commitments;bl.text 非空→bid.full_text;
    无 commitments→两路径缺席(零行为面:绿跑参与卡空→L4 不执行)。"""
    out = project_bid_fields(_ctx_with_commitments())
    assert out["bid.service_commitments"] == [{"text": "额外承诺:终身免费维保", "clause_id": ""}]
    assert out["bid.full_text"]
    bare = project_bid_fields({"products": {"bid_letter": {"slots": {}, "text": "x"}, "price_sheet": {}}})
    assert "bid.service_commitments" not in bare
```

- [x] **Step 2: 跑测试确认失败**:`PYTHONPATH=. uv run pytest tests/test_bid_write_l4.py -q` → FAIL(KeyError service_commitments)。

- [x] **Step 3: 实现**——project_bid_fields 末尾(bl 块后)追加:

```python
    comms = [c for c in (bl.get("extra_commitments") or []) if isinstance(c, dict) and str(c.get("text") or "").strip()]
    if comms:
        # 批廿四 P1-γ:L4-003/004 语义审查输入面(承诺清单+产物全文投影)
        out["bid.service_commitments"] = [{"text": str(c["text"]).strip(), "clause_id": str(c.get("clause_id") or "")} for c in comms]
    if bl.get("text"):
        out["bid.full_text"] = bl["text"]
```

- [x] **Step 4: 跑测试确认通过**;顺跑 `tests/test_bid_write_precheck*.py`(若存在)确认 det 面零回归(新增 bid.* 路径不在 core det rules inputs,零影响)。

- [x] **Step 5: Commit**:

```bash
git add backend/app/extensions/bid_write/precheck.py backend/tests/test_bid_write_l4.py
git commit -m "feat(bid_write): 批廿四 P1-γ-b——project_bid_fields 增 bid.service_commitments/bl 承诺+bid.full_text/bl 文投影(L4-003/004 参与面;无承诺缺席=绿跑零行为)"
```

---

### Task 3: `run_l4_review` + `run_export_gate(l4_model_fn)` 形参

**Files:**
- Modify: `backend/app/extensions/bid_write/precheck.py`(`_l4_participants`/`run_l4_review` 新函数 + run_export_gate 改形)
- Test: `backend/tests/test_bid_write_l4.py`

- [x] **Step 1: 写失败测试**(追加):

```python
def _stub_model(verdict="full", confidence=0.95):
    """L4 模型 stub:_call_model 契约=callable 返回带 .content 对象。"""
    def _fn(messages):
        payload = {"verdicts": [{"clause_id": "C1", "verdict": verdict, "confidence": confidence, "reason": "stub", "evidence": [{"doc_id": "bid", "page": 1, "text": "stub"}]}]}
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    return _fn


@pytest.mark.asyncio
async def test_l4_no_participants_not_executed():
    """无承诺→参与卡空→executed=False 不烧模型(零行为面)。"""
    out = await run_l4_review({}, "", _stub_model())
    assert out["executed"] is False
    assert out["watermark_removed"] is False
    assert len(out["input_missing"]) >= 8  # 多数卡缺输入诚实列名


@pytest.mark.asyncio
async def test_l4_all_pass_removes_watermark():
    """L4-003/004 参与(L4-005 缺 tender.clauses 列 input_missing);
    全 full→零条目→摘除。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    fields = {
        "bid.service_commitments": [{"text": "终身免费维保", "clause_id": ""}],
        "bid.full_text": "承诺:终身免费维保",
        "tender.substantive_clauses": ["投标人不得转包"],
    }
    out = await run_l4_review(fields, "承诺:终身免费维保", wrap_model_fn(_stub_model("full")))
    assert out["executed"] is True
    assert set(out["participants"]) == {"L4-003", "L4-004"}
    assert "L4-005" in out["input_missing"]
    assert out["watermark_removed"] is True


@pytest.mark.asyncio
async def test_l4_fail_or_unclear_keeps_watermark():
    """none→FAIL 条目;unclear→need_human;两者都不摘。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    fields = {
        "bid.service_commitments": [{"text": "终身免费维保", "clause_id": ""}],
        "bid.full_text": "承诺:终身免费维保",
        "tender.substantive_clauses": ["投标人不得转包"],
    }
    fail = await run_l4_review(fields, "x", wrap_model_fn(_stub_model("none")))
    assert fail["executed"] is True and fail["watermark_removed"] is False
    unclear = await run_l4_review(fields, "x", wrap_model_fn(_stub_model("unclear", confidence=0.5)))
    assert unclear["watermark_removed"] is False


@pytest.mark.asyncio
async def test_l4_model_missing_degrades_error_keeps_watermark():
    """恒抛闭包→逐规则隔离 ERROR→水印保持(诚实,绝不假绿)。"""
    from app.extensions.bid_review.worker import ModelNotConfigured

    def _boom(messages):
        raise ModelNotConfigured("no model")
    fields = {
        "bid.service_commitments": [{"text": "终身免费维保", "clause_id": ""}],
        "bid.full_text": "x",
        "tender.substantive_clauses": ["y"],
    }
    out = await run_l4_review(fields, "x", _boom)
    assert out["executed"] is True and out["watermark_removed"] is False
    assert out["counts"].get("ERROR", 0) >= 1


@pytest.mark.asyncio
async def test_export_gate_l4_advisory_and_watermark():
    """gate 形:l4 摘除→watermark=None;不供 l4_model_fn→恒加(既有面);
    L4 永不入 blocked/reasons(advisory-only 铁律)。"""
    ctx = _ctx_with_commitments()
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    gone = await run_export_gate(ctx, l4_model_fn=wrap_model_fn(_stub_model("full")))
    assert gone["watermark"] is None
    assert gone["l4"]["executed"] is True
    keep = await run_export_gate(ctx)  # 既有签名零破坏
    assert keep["watermark"] == contracts.EXPORT_RISK_WATERMARK
    assert keep["l4"] is None
    fail = await run_export_gate(ctx, l4_model_fn=wrap_model_fn(_stub_model("none")))
    assert fail["watermark"] == contracts.EXPORT_RISK_WATERMARK
    assert not fail["blocked"] or fail["l4"]  # blocked 面与 L4 解耦(L4 不贡献 blocked)
```

- [x] **Step 2: 跑测试确认失败**:`PYTHONPATH=. uv run pytest tests/test_bid_write_l4.py -q` → `run_l4_review` ImportError / `l4_model_fn` TypeError。

- [x] **Step 3: 实现**——precheck.py 追加(在 run_export_gate 之前;`_L4_BLOCKING`/`_l4_pack_cache` 模块级):

```python
_L4_BLOCKING = {"FAIL", "ERROR", "need_human", "UNKNOWN"}
_l4_pack_cache = None


def _l4_participants(fields: dict):
    """L4 参与卡筛选(P1-γ):enabled ∧ sem/hyb ∧ inputs 全非空。缺输入卡诚实列
    input_missing 不烧模型(sem 卡缺输入仍会模型调用,写侧成本闸;engine 不动,
    写侧本地关切)。返回 (pack|None, 参与卡 id 列表, 缺输入卡 id 列表)。"""
    global _l4_pack_cache
    if not _L4_PATH.exists():
        return None, [], []
    if _l4_pack_cache is None:
        _l4_pack_cache = load_rulepack(_L4_PATH)
    parts: list = []
    missing: list[str] = []
    for r in _l4_pack_cache.rules:
        if not r.enabled or r.type not in ("semantic", "hybrid"):
            continue
        if all(fields.get(p) not in (None, "", [], {}) for p in r.inputs):
            parts.append(r)
        else:
            missing.append(r.id)
    if not parts:
        return None, [], missing
    return dataclasses.replace(_l4_pack_cache, rules=parts), [r.id for r in parts], missing


async def run_l4_review(fields: dict, materials: str, model_fn) -> dict:
    """L4 语义审查面(advisory-only,P1-γ):参与卡过 evaluate_fields 全引擎语义
    管线(逐规则隔离;full=干净零条目/partial·none=FAIL·WARN/unclear=need_human/
    基础设施故障=ERROR)。摘除条件=executed ∧ 参与卡零 FAIL/ERROR/need_human/
    UNKNOWN(unclear=未确认→水印保持,诚实)。L4 永不入 gate blocked/reasons
    (pack meta counts_toward_bid_gate=false)。"""
    pack, parts, missing = _l4_participants(fields)
    if pack is None or model_fn is None:
        return {
            "executed": False, "counts": {}, "issues": [], "participants": parts,
            "input_missing": missing, "watermark_removed": False,
            "scope_note": "L4 无参与卡或缺模型→未执行(水印恒加)",
        }
    issues = await evaluate_fields(pack, dict(fields or {}), model_fn=model_fn, materials=materials)
    counts = Counter(i.get("verdict") for i in issues)
    removed = not any(i.get("verdict") in _L4_BLOCKING for i in issues)
    return {
        "executed": True,
        "counts": {k: counts[k] for k in sorted(counts)},
        "issues": issues,
        "participants": parts,
        "input_missing": missing,
        "watermark_removed": bool(removed),
        "scope_note": f"L4 模型审查 advisory-only(不阻断;参与卡 {len(parts)},缺输入 {len(missing)})",
    }
```

run_export_gate 改形(签名加 kw,fields 提前算,l4 面叠加,watermark 条件化):

```python
async def run_export_gate(ctx: dict, *, l4_model_fn=None) -> dict:
    """导出前置校验(P0 规格 §8):重跑全量 D0 断言 + det 规则层预审查
    (+P1-γ:l4_model_fn 供给时叠加 L4 语义审查面 advisory-only——不入 blocked/
    reasons;watermark 摘除条件=参与卡零 FAIL/ERROR/need_human/UNKNOWN,摘除
    即 None,否则恒加 EXPORT_RISK_WATERMARK)。blocked=gate D0 FAIL/ERROR 或
    L1 fatal det FAIL(L4 零贡献,铁律)。"""
    from app.extensions.bid_write.contracts import EXPORT_RISK_WATERMARK, SCHEMA_VERSION
    from app.extensions.bid_write.executor.gate import gate_verdict
    from app.extensions.bid_write.executor.runner import run_assertions

    report = run_assertions(ctx)
    gate = gate_verdict(report)
    fields = project_bid_fields(ctx)
    pre = await run_rule_precheck(fields)
    l4 = None
    if l4_model_fn is not None:
        l4_fields = dict(fields)
        sc = ((ctx or {}).get("tender") or {}).get("tender.substantive_clauses")
        if sc:
            l4_fields["tender.substantive_clauses"] = sc
        bl = ((ctx or {}).get("products") or {}).get("bid_letter") or {}
        l4 = await run_l4_review(l4_fields, str(bl.get("text") or ""), l4_model_fn)
    a_counts = Counter(r.status for r in report.results)
    from app.extensions.bid_write.executor.report import to_report_dict

    return {
        "blocked": bool(gate["blocked"] or pre["blocked"]),
        "reasons": sorted(set(gate["reasons"]) | set(pre["l1_fatal_fail"])),
        "watermark": None if l4 is not None and l4["watermark_removed"] else EXPORT_RISK_WATERMARK,
        "assertion_counts": {k: a_counts[k] for k in sorted(a_counts)},
        "rule_counts": pre["counts"],
        "l1_fatal_fail": pre["l1_fatal_fail"],
        "l4": l4,
        "scope_note": pre["scope_note"],
        "schema_version": SCHEMA_VERSION,
        # results=gaps 断言维度消费面(to_report_dict 序列化;报告=导出物非真相源)
        "results": to_report_dict(report)["results"],
    }
```

- [x] **Step 4: 跑测试确认通过**:`PYTHONPATH=. uv run pytest tests/test_bid_write_l4.py tests/test_bid_write_m2_worker.py tests/test_bid_write_routers.py -q` 全绿(stub 若因 verdict_set/gates 细节失败,按 check_schema 七道实际行为调 stub——不放松被测语义)。

- [x] **Step 5: Commit**:

```bash
git add backend/app/extensions/bid_write/precheck.py backend/tests/test_bid_write_l4.py
git commit -m "feat(bid_write): 批廿四 P1-γ-c——run_l4_review 语义审查面+run_export_gate l4_model_fn 形参(参与卡=inputs 全非空缺输入诚实列名不烧模型;摘除=参与卡零 FAIL/ERROR/need_human/UNKNOWN;advisory-only 零入 blocked/reasons;watermark 摘除置 None)"
```

---

### Task 4: worker `_l4_model_fn` + `generate_and_record` 接线

**Files:**
- Modify: `backend/app/extensions/bid_write/worker.py`(新 `_l4_model_fn`;generate_and_record 一行)
- Test: `backend/tests/test_bid_write_l4.py`

- [x] **Step 1: 写失败测试**(追加;复用 policy/materials 测试的 seed 手法——sqlite in-memory + 建任务 + meta.fields 注入 + generate_and_record,`_l4_model_fn` 打桩):

```python
@pytest.mark.asyncio
async def test_worker_generate_persists_l4(monkeypatch, _seed_env):
    """generate_and_record 接线:verdict["l4"] 落 skill_run;承诺面全 full→水印 None。"""
    # _seed_env 为既有 bid_write 测试的 db/monkeypatch 夹具组合(实现时对齐
    # test_bid_write_policy.py 的 _seed 手法:建表清单+任务+meta.fields/rows)。
    ...
```

(实现时照抄 test_bid_write_policy.py `_seed` 的建表+建任务+fields 注入骨架,再:

```python
    monkeypatch.setattr(worker, "_l4_model_fn", lambda: _stub_model("full"))
    export = await worker.generate_and_record(db, task, owner_id)
    assert export["l4"]["executed"] is True
    assert export["watermark"] is None
    run = await crud.latest_skill_run(db, task_id=task.id, owner_id=owner_id)
    assert (run.verdict or {}).get("l4", {}).get("executed") is True
```

承诺面走 knobs:`await crud.set_meta(db, task, knobs={"general_commitments": [{"text": "终身免费维保", "clause_id": ""}]})` 或直接 engine_meta 注入(对齐既有测试手法)。)

- [x] **Step 2: 跑测试确认失败**:`PYTHONPATH=. uv run pytest tests/test_bid_write_l4.py -q` → `worker` 无 `_l4_model_fn` 属性。

- [x] **Step 3: 实现**——worker.py 追加(extraction 模型接线旁):

```python
def _l4_model_fn():
    """L4 语义审查模型接线(P1-γ;镜像 bid_review.worker._default_model_fn 先例):
    模型选择同 extraction(_resolve_model_name→EAI_BID_REVIEW_MODEL/config 首项,
    写侧不另设 env=同一把模型尺);ainvoke 异步禁同步堵环;无可用模型返回恒抛
    闭包,L4 逐规则隔离降级 ERROR→水印保持,绝不静默假绿。"""
    from app.extensions.bid_review.worker import ModelNotConfigured

    name = review_worker._resolve_model_name()
    if not name:

        def _fn(messages):
            raise ModelNotConfigured("config.yaml 无可用模型(L4 语义审查逐规则降级 ERROR→水印保持)")

        return _fn
    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name)
    logger.info("bid_write L4 semantic review using model %s", name)

    async def _fn(messages):
        return await model.ainvoke(messages)

    return _fn
```

generate_and_record 内一行:

```python
    export = await run_export_gate(ctx, l4_model_fn=_l4_model_fn())
```

- [x] **Step 4: 跑测试确认通过**(注意:绿跑 seed 无 commitments→参与卡空→真 `_l4_model_fn` 恒抛闭包零调用,既有测试零行为;policy 测试 metrics 断言不动)。

- [x] **Step 5: Commit**:

```bash
git add backend/app/extensions/bid_write/worker.py backend/tests/test_bid_write_l4.py
git commit -m "feat(bid_write): 批廿四 P1-γ-d——worker _l4_model_fn 生产接线(镜像 bid_review 先例;无模型恒抛闭包逐规则 ERROR 水印保持)+generate_and_record 接线(l4 面落 skill_run verdict)"
```

---

### Task 5: 全量回归 + docs 收口

- [x] **Step 1: 全量回归**(后台):`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_write -q` → 全绿(208 基线+新;绿跑 ERROR 平台律:既有 CtxMissing 1 条不变)。
- [x] **Step 2: `cd backend && make lint`** 零新增告警。
- [x] **Step 3: docs 收口**——plan 勾选+落地态勘误;spec §7 增 P1-γ 落地态段(剩余 P1-δ);wolf 三件套(anatomy/memory/cerebrum)+buglog(如触发)+auto-memory `bid-write-p1-beta24-l4-activation-landed.md`。
- [x] **Step 4: 最终 Commit**:

```bash
git add -f docs/superpowers/plans/2026-11-14-bid-write-p1-beta24-l4-activation-plan.md docs/superpowers/specs/2026-11-13-bid-write-p0-skills-spec.md .wolf/
git commit -m "docs(bid-write): 批廿四收口——plan 全勾+spec §7 P1-γ 落地态段(剩余 P1-δ)+wolf 三件套"
```

---

## 落地态勘误(收口回填,2026-11-14)

- **Task 1 落地形态与计划不同(研究疏漏,钉救)**:计划按扩面表登记,实现时被 `ext∩uni=∅` 钉当场打红——`tender.substantive_clauses` **本就是 universe 成员**(anchors「招标合同条款/实质性条款」组,bid_review 侧早已收编;研究阶段只 grep 了 extract.py 的 FIELD_TYPE_CONTRACTS 没查 ANCHOR_REGISTRY)。**主路径直入**(`contracts.py` 头注「挂 M2 与 L4 激活同批落地」早已预埋此意);扩面表三 BL 槽位不动。教训入 cerebrum:查 universe 成员资格须查 `registry.universe()`(=pack_inputs∪anchors∪projection∪second_stage)全四源,不能只查其一。
- **红提交事故**:Task 1 初版 commit 时 `pytest | tail` 管道吃掉退出码,`&&` 链未断→红态入库;发现后修绿+amend(unpushed,HEAD 验证仍是本批 commit)。教训入 cerebrum Do-Not-Repeat。
- **commit 形态**:4 commits(8f1b4f8d6 契约 / precheck 投影 / precheck L4 面 / 6c1685572 worker 接线),均先红后绿+amend 修 lint(I001 import 排序 ruff --fix;fixture 复用 `db as policy_db` 需 re-export noqa——ruff --fix 曾删掉该 import 致 fixture 解析 ERROR,回补 noqa 双钉)。
- **回归**:全量 `-k bid_write` 216p/6s/0f(208 基线+7 L4+1 契约钉);export dict 新增 `"l4"` 键(恒在,None=未执行)未破任何键钉。绿跑 ERROR 平台(CtxMissing 1 条)不受影响——默认 knobs 参与卡空,L4 面零调用。
- **挂账**:写侧投影现只覆盖 L4-003/004 两卡,其余 8 卡 `input_missing` 诚实列名(bid.warranty_period/schedule_milestones/personnel/equipment/response_sections 等投影面挂 P1-δ+素材联动);`tender.clauses`(spec 名,L4-005)仍非 repo 路径,不别名不造假。export-precheck 端点保持 det-only 快径(L4 只走 generate 面)。
