# bid-review P1-α（底座+口径）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** P1 backlog 拆三批的第一批（α）：分片 JSON 解析加固（方差红旗）+ C-08 枚举三拆落库 + C-05 MATCHED→PRESENT 入库归一 + 记档回写。

**Architecture:** 全部落在 `app/extensions/bid_review/` 既有文件内，零新表、零配置改动。Task 1 抽共享 `_invoke_json` 核替换五段重复的两试循环；Task 2 在 sem/hyb issue 装配处携带 raw 语义四值与 state_map 派生业务态，落库走 `crud.add_issue` 显式 kwargs + `database.py` 幂等 ALTER 先例；Task 3 在 `_write_baselines` 入口对入库快照做单点归一（引擎内存态不动）。

**Tech Stack:** Python 3.12 / SQLAlchemy(async) / FastAPI / pytest；无新依赖。

---

## 0. 背景与铁律（每个 implementer 必读）

**来源**：规格 `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md` §3.3（C-05/C-08 裁决）+ §5 第 4 条（P1 前置）+ §6 P1；方差红旗来自 2026-11-06 活体方差回采（bug-4086 记档，tables 分片 4 调用 3 次双败、extract 大分片截断型双败，错误全部是 JSONDecodeError）。

**P1 全景拆批（本计划只做 α；β/γ 待 α 落地后另起 plan）**：
- **α（本计划）**：底座+口径——JSON 加固 / 枚举三拆 / MATCHED→PRESENT / 记档回写。
- **β（后续）**：规则扩包——L2 要件级/文件级扩展 + C-11 src→severity 覆盖 + L4 十条（C.2 YAML）+ 表达式引擎配套（乘法/regex/subset_of/level_ge/or/三值 UNKNOWN 传播/Decimal 精度）+ verdict 值域迁移 PASS/FAIL/UNKNOWN/ERROR/SKIP。
- **γ（后续）**：平台面——解析广度（xlsx/zip/章节兜底）、抽取器配置化+lint 端点、评测规模化（24 算子/ATT 组门禁/holdout）、漏报回流、错误码体系、MCP 三工具补齐。

**铁律（违者打回）**：
1. 分支 `main-dev-fork`；`git add` 只用 pathspec，**禁 `-A`/`.`**（工作区有并发会话改动）。
2. 测试口径：`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q` 全绿（当前基线 588 passed / 6 skipped，只增不减）；每任务提交前跑；全部任务收尾后跑全量 `uv run pytest tests/ -q` + 离线金标准 `PYTHONPATH=. uv run python -m app.extensions.bid_review.golden.extract`（无 --live）须 26/26。
3. **冻结面不可动**：golden/cases/*.yaml 题面与断言、CALIBRATION.md 既有行、基线快照地板 1.0、universe 78、请求面 71。
4. EAI-CUSTOM 注释规范：上游文件改动须 `# EAI-CUSTOM(...)` 行注；本项目自有文件（app/extensions/bid_review/** 全部）注明裁决来源与日期即可。
5. `.wolf/` 目录 implementer 禁入（controller 专属）；不 restart docker（宿主 pytest 足够）；不开 worktree。
6. `docs/superpowers/` 在 .gitignore，本计划的后续文档改动提交须 `git add -f docs/superpowers/plans/<本文件>`。

---

### Task 1: 分片 JSON 解析加固（_parse_json_object 宽松修复 + _invoke_json 三试纠错共享核）

**Files:**
- Modify: `backend/app/extensions/bid_review/worker.py:115-128`（_parse_json_object）、`:260-271`（extract 循环）、`:319-331`（attachments）、`:350-362`（sections）、`:381-393`（tables）、`:412-424`（performance）、`:243-244`（docstring 两试→三试）
- Test: `backend/tests/test_bid_review_invoke_json.py`（新建）

**依据**：活体方差回采 2026-11-06：tables 分片 4 调用 3 次双败（`Expecting property name enclosed in double quotes`，char 69-86 小输出=尾逗号特征）；extract 大分片 2 次双败（`Expecting ',' delimiter` char 12k-17k=截断特征）。现状五段各有一份 `for attempt in (1, 2)` 盲重试，模型看不到自己上轮的坏输出。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_bid_review_invoke_json.py`：

```python
"""_parse_json_object 尾逗号宽松修复 + _invoke_json 三试纠错共享核。

bug-4086 血亲(2026-11-06 活体方差回采):tables 分片小输出尾逗号是高频死因;
extract 大分片截断型双败。三试 + 第 2/3 试回灌 assistant 原文 + 纠错 user 轮
(模型可见自己的错误,修复率高于盲目重掷)。
"""

import pytest

from app.extensions.bid_review import worker


class _FakeModel:
    """按脚本回放 content 的假模型;记录每次收到的 messages。"""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls: list[list[dict]] = []

    def invoke(self, messages):
        self.calls.append([dict(m) for m in messages])

        class _R:
            pass

        r = _R()
        r.content = self.scripts.pop(0)
        return r


def test_parse_json_object_repairs_trailing_comma():
    assert worker._parse_json_object('{"a": [1, 2,], "b": "x",}') == {"a": [1, 2], "b": "x"}


def test_parse_json_object_strict_error_still_raised():
    with pytest.raises(ValueError):
        worker._parse_json_object('{"a": "未闭合')


def test_invoke_json_recovers_by_third_attempt():
    m = _FakeModel(["完全不是JSON", '{"a": [1, 2]}}', '{"a": 1}'])
    out = worker._invoke_json(m, "P", "表格提取")
    assert out == {"a": 1}
    assert len(m.calls) == 3
    # 第 2 试起:assistant 原文回灌 + 纠错 user 轮(模型可见自己上轮输出)
    assert m.calls[1][-2]["role"] == "assistant"
    assert m.calls[1][-1]["role"] == "user"
    assert "JSON" in m.calls[1][-1]["content"]


def test_invoke_json_exhausts_with_noun_label():
    m = _FakeModel(["x", "y", "z"])
    with pytest.raises(RuntimeError, match="表格提取三试未获有效 JSON"):
        worker._invoke_json(m, "P", "表格提取")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_invoke_json.py -v`
Expected: FAIL（`_invoke_json` 不存在 → AttributeError；尾逗号用例 JSONDecodeError）

- [ ] **Step 3: 实现**

`worker.py` 模块级新增（放 `_parse_json_object` 上方）：

```python
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
```

`_parse_json_object` 整体替换为：

```python
def _parse_json_object(text: str) -> dict:
    """模型输出 → JSON dict(容 ```json 围栏与前后杂文:取首 { 至末 } 切片);
    尾逗号宽松修复一次(活体方差观测 2026-11-06:tables 分片小输出尾部逗号是
    高频死因,bug-4086 血亲);仍失败或非 dict 抛 ValueError(调用方重试)。"""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"模型输出不含 JSON 对象: {text[:120]!r}")
    snippet = s[start : end + 1]
    try:
        payload = json.loads(snippet)
    except json.JSONDecodeError:
        payload = json.loads(_TRAILING_COMMA_RE.sub(r"\1", snippet))  # 尾逗号修复,再炸照抛
    if not isinstance(payload, dict):
        raise ValueError(f"模型输出 JSON 非对象: {type(payload).__name__}")
    return payload
```

新增共享核（放 `_parse_json_object` 之后）：

```python
def _invoke_json(model, prompt: str, noun: str) -> dict:
    """分片 prompt → JSON dict 共享调用核(五段 DRY,替换各自的两试循环):
    三试解析;第 2/3 试回灌上轮原始输出(assistant 轮)+ 纠错 user 轮;输出未以
    } 收尾时记疑似截断(bug-4086 活体:大分片 char 12k+ 截断型双败)。仍失败抛
    RuntimeError({noun}三试未获有效 JSON)。"""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    last_err: Exception | None = None
    for attempt in (1, 2, 3):
        response = model.invoke(messages)
        raw = _content_to_str(getattr(response, "content", ""))
        if not raw.rstrip().endswith("}"):
            logger.warning("bid_review %s output looks truncated(len=%d)", noun, len(raw))
        try:
            return _parse_json_object(raw)
        except ValueError as exc:
            last_err = exc
            logger.warning("bid_review %s parse retry attempt=%d err=%s", noun, attempt, exc)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "上一次输出不是合法 JSON。请重新输出完整、合法的 JSON 对象：不要任何解释文字，不要截断，所有键用双引号，不要尾逗号。"},
            ]
    raise RuntimeError(f"{noun}三试未获有效 JSON({last_err})") from last_err
```

五处调用点替换（保留各自外层函数签名与 docstring 的测试 seam，只换循环体）：

extract（原 `:260-271`）：
```python
    def _invoke_shard(prompt: str) -> dict:
        return _invoke_json(model, prompt, "基准提取")
```

attachments `_fn` 体（原 `:319-331`）：
```python
    def _fn(docs, requirements, index_rows, fp_hints) -> dict:
        prompt = build_attachments_prompt(docs, requirements, index_rows, fp_hints)
        return _invoke_json(model, prompt, "附件实体提取")
```

sections `_fn` 体（原 `:350-362`）：
```python
    def _fn(docs, toc_codes, required_sections) -> dict:
        prompt = build_sections_prompt(docs, toc_codes, required_sections)
        return _invoke_json(model, prompt, "章节提取")
```

tables `_fn` 体（原 `:381-393`）：
```python
    def _fn(docs, tender_rows) -> dict:
        prompt = build_tables_prompt(docs, tender_rows)
        return _invoke_json(model, prompt, "表格提取")
```

performance `_fn` 体（原 `:412-424`）：
```python
    def _fn(docs) -> dict:
        prompt = build_performance_prompt(docs)
        return _invoke_json(model, prompt, "业绩提取")
```

`_default_extract_fn` docstring 中「坏输出重试 1 次」改为「坏输出纠错重试至多 2 次（_invoke_json 三试共享核，bug-4086 加固）」。

- [ ] **Step 4: 跑测试确认通过 + 家族回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_invoke_json.py tests/ -k "bid_review and (worker or sem or extract)" -v`
Expected: PASS（新 4 题绿 + 既有 worker/sem/extract 家族零翻红；若既有用例显式钉「两试」文案，据新契约「三试」同刻更新该用例并在 commit message 注明）

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/bid_review/worker.py backend/tests/test_bid_review_invoke_json.py
git commit -m "fix(bid-review): 分片JSON解析加固——_parse_json_object尾逗号宽松修复+_invoke_json三试纠错共享核(五段DRY,assistant回灌+纠错轮+截断遥测);bug-4086活体方差红旗兑付"
```

---

### Task 2: C-08 枚举三拆——semantic_verdict/state 落库（加列不加值裁决）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/llm_runner.py`（_verdict_to_issue + _STATE_MAP）、`models.py:69` 附近（两列 + 注释）、`crud.py:118-181`（add_issue kwargs + 构造）、`worker.py:529-544`（call site）、`database.py:955-966` 附近（幂等 ALTER）、`schemas.py:52-76`（IssueOut）
- Test: `backend/tests/test_bid_review_llm_verify.py`、`backend/tests/test_bid_review_crud.py`、`backend/tests/test_bid_review_schemas.py`

**裁决记录（本任务的边界）**：C-08 全量 = verdict 值域迁 `PASS/FAIL/UNKNOWN/ERROR/SKIP`（整合版枚举 :2008）+ state 分层 + semantic_verdict。**本批只落 semantic_verdict/state 两字段；verdict 值域迁移挂 P1-β**（会破 CALIBRATION 59 题冻结面与 golden schema `verdict: violation|need_human|unclear` 契约，须随 β 规则扩包同批重标定）。现有 verdict 收敛映射 `VERDICT_TO_ISSUE`（partial/none→violation）**不动**。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_bid_review_llm_verify.py` 追加（沿用文件既有 import；若 `llm_runner` 未导入则补 `from app.extensions.bid_review.engine import llm_runner`）：

```python
def test_sem_issue_carries_raw_semantic_verdict_and_state():
    """C-08 三拆(EAI-CUSTOM 2026-11-06):模型 raw 四值原样落 semantic_verdict,
    state 按 state_map 分层枚举派生;verdict 收敛值不破 CALIBRATION。"""
    from app.extensions.bid_review.engine import llm_runner

    rule = {"id": "L1-003", "layer": "L1", "severity": "major", "type": "semantic", "message_tpl": "{clause_id}:{reason}", "check": {}}
    issue = llm_runner._verdict_to_issue(rule, {"clause_id": "C-1", "verdict": "partial", "reason": "部分响应", "evidence": []})
    assert issue["semantic_verdict"] == "partial"
    assert issue["state"] == "PARTIAL"  # L1 state_map: partial→PARTIAL
    assert issue["verdict"] == "violation"  # 收敛映射不动(CALIBRATION 冻结面)

    rule_l2 = {"id": "L2-025", "layer": "L2", "severity": "major", "type": "semantic", "message_tpl": "{clause_id}:{reason}", "check": {}}
    issue_l2 = llm_runner._verdict_to_issue(rule_l2, {"clause_id": "C-2", "verdict": "unclear", "reason": "材料不足", "evidence": []})
    assert issue_l2["semantic_verdict"] == "unclear"
    assert issue_l2["state"] == "UNKNOWN"
    assert issue_l2["need_human"] is True

    rule_x = {"id": "X-1", "layer": "L9", "severity": "minor", "type": "semantic", "message_tpl": "{clause_id}:{reason}", "check": {}}
    assert llm_runner._verdict_to_issue(rule_x, {"clause_id": "c", "verdict": "full", "reason": "", "evidence": []})["state"] is None
```

`backend/tests/test_bid_review_crud.py` 追加（文件已有 sqlite 内存 engine 夹具，镜像同文件既有 add_issue 用例的夹具用法）：

```python
@pytest.mark.asyncio
async def test_add_issue_persists_semantic_verdict_and_state(db):
    """C-08 三拆落库:semantic_verdict/state 两列显式 kwargs 透传 crud.add_issue。"""
    t = await crud.create_task(db, owner_id="u1")
    row = await crud.add_issue(
        db, task_id=t.id, owner_id="u1", rule_id="L2-025", layer="L2", severity="major",
        verdict="unclear", message="复合附件分组失败", dedup_key="L2-025|-|k1",
        semantic_verdict="unclear", state="UNKNOWN",
    )
    await db.refresh(row)
    assert row.semantic_verdict == "unclear"
    assert row.state == "UNKNOWN"
```

`backend/tests/test_bid_review_schemas.py` 追加：

```python
def test_issue_out_exposes_semantic_verdict_and_state():
    from app.extensions.bid_review.schemas import IssueOut

    assert "semantic_verdict" in IssueOut.model_fields
    assert "state" in IssueOut.model_fields
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_llm_verify.py tests/test_bid_review_crud.py tests/test_bid_review_schemas.py -v -k "semantic or issue_out"`
Expected: FAIL（KeyError 'semantic_verdict' / TypeError unexpected kwarg / KeyError）

- [ ] **Step 3: 实现**

**(a) `llm_runner.py`** 模块级（`VERDICT_TO_ISSUE` 定义 :45 之后）新增：

```python
# C-08 枚举三拆(EAI-CUSTOM 2026-11-06,整合版规格 §3.3 裁决):模型只输出 raw 语义值,
# state 由 state_map 后处理派生(模型禁编业务态);七键全表=与规格 semantic_verdict 枚举
# [full, partial, none, unclear, consistent, inconsistent, not_applicable] 对齐,v1 模型
# 只产前四值。verdict 值域迁 PASS/FAIL/... = P1-β 挂账(破 CALIBRATION 冻结面)。
_STATE_MAP: dict[str, dict[str, str]] = {
    "L1": {"full": "MATCHED", "partial": "PARTIAL", "none": "MISSING", "unclear": "UNKNOWN",
           "consistent": "MATCHED", "inconsistent": "PARTIAL", "not_applicable": "MATCHED"},
    "L2": {"full": "PRESENT", "partial": "PARTIAL", "none": "MISSING", "unclear": "UNKNOWN",
           "consistent": "PRESENT", "inconsistent": "PARTIAL", "not_applicable": "PRESENT"},
    "L3": {"full": "CONSISTENT", "partial": "INCONSISTENT", "none": "INCONSISTENT", "unclear": "UNKNOWN",
           "consistent": "CONSISTENT", "inconsistent": "INCONSISTENT", "not_applicable": "CONSISTENT"},
    "L4": {"full": "NONE", "partial": "RISK", "none": "RISK", "unclear": "UNKNOWN",
           "consistent": "NONE", "inconsistent": "RISK", "not_applicable": "NONE"},
}
```

`_verdict_to_issue` 返回 dict（:121-136）在 `"verdict": VERDICT_TO_ISSUE.get(verdict, "unclear"),` 之后插入两行：

```python
        "semantic_verdict": verdict,  # C-08:raw 四值原样留痕(收敛映射另见上键)
        "state": _STATE_MAP.get(str(rule.get("layer") or ""), {}).get(verdict),  # 分层业务态,v1 det 规则不产本键
```

**(b) `models.py`**（ReviewIssue 类，`verdict` 列 :69 之后）追加两列并把 :69 注释补一句：

```python
    verdict: Mapped[str] = mapped_column(String(20))  # violation|need_human|unclear;人工复核回写(false_positive 等,A8)也落本列;值域迁 PASS/FAIL/UNKNOWN/ERROR/SKIP=P1-β 挂账(C-08)
    # C-08 枚举三拆(EAI-CUSTOM 2026-11-06):引擎 raw 语义四值 full|partial|none|unclear
    # (sem/hyb 专属,det 规则 NULL)与 state_map 分层业务态(L1 MATCHED…/L2 PRESENT…);
    # 模型禁编业务态,state 恒由后处理派生。
    semantic_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    state: Mapped[str | None] = mapped_column(String(24), nullable=True)
```

**(c) `database.py`**（migrate_db 内既有 bid-review 幂等补列块 :955-966 旁，照同款先例）追加：

```python
        # EAI-CUSTOM (bid-review C-08 枚举三拆,2026-11-06): 语义四值/分层业务态两列
        # (create_all 不 ALTER 已有表,幂等补列;先例=同文件 L2 P2 entity_keys 块)
        for _stmt in (
            "ALTER TABLE bid_review_issues ADD COLUMN IF NOT EXISTS semantic_verdict VARCHAR(16)",
            "ALTER TABLE bid_review_issues ADD COLUMN IF NOT EXISTS state VARCHAR(24)",
        ):
            await conn.execute(text(_stmt))
```

（注记：`variable` 名与同块既有循环变量避让；tests 走 create_all 新表自带 ORM 列，此块只服务存量库。）

**(d) `crud.py`** `add_issue` 签名 keyword-only 段（:129-134）追加两参，`ReviewIssue(...)` 构造（:163-177）追加两 kwargs：

```python
    entity_keys: list | None = None,
    semantic_verdict: str | None = None,
    state: str | None = None,
) -> ReviewIssue | None:
```

```python
        entity_keys=list(entity_keys or []),
        semantic_verdict=semantic_verdict,
        state=state,
    )
```

**(e) `worker.py`** `_run_review_stage` 落库循环（:529-544）`entity_keys=...` 之后追加：

```python
            semantic_verdict=_issue_get(issue, "semantic_verdict"),
            state=_issue_get(issue, "state"),
```

**(f) `schemas.py`** IssueOut（:68 entity_keys 之后、grouped_into 之前）追加：

```python
    # EAI-CUSTOM(C-08 枚举三拆 2026-11-06):引擎 raw 语义四值+分层业务态;det/旧网关=None
    semantic_verdict: str | None = None
    state: str | None = None
```

- [ ] **Step 4: 跑测试确认通过 + 家族回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_llm_verify.py tests/test_bid_review_crud.py tests/test_bid_review_schemas.py -v && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`
Expected: PASS 全绿（golden 评分器不消费新键——issues dict 多键无害；快照 26/26 不动）

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/bid_review/engine/llm_runner.py backend/app/extensions/bid_review/models.py backend/app/extensions/bid_review/crud.py backend/app/extensions/bid_review/worker.py backend/app/extensions/database.py backend/app/extensions/bid_review/schemas.py backend/tests/test_bid_review_llm_verify.py backend/tests/test_bid_review_crud.py backend/tests/test_bid_review_schemas.py
git commit -m "feat(bid-review): C-08枚举三拆落库——semantic_verdict(raw四值)+state(state_map派生)两列贯穿llm_runner/crud/worker/IssueOut;verdict值域迁移挂P1-β;幂等ALTER先例块"
```

---

### Task 3: C-05 MATCHED→PRESENT 入库归一（单点边界，引擎内存态不动）

**Files:**
- Modify: `backend/app/extensions/bid_review/worker.py`（`_write_baselines` :446-456 入口 + 新 helper）
- Test: `backend/tests/test_bid_review_worker.py`

**安全性论证（implementer 须复核）**：引擎判定（`attachments.py` 三通道匹配、`rule_runner` per_req 状态、`build_checklist`）只消费**实体身份**（no/name 归一）与引擎自产状态，从不读入库行 `status` 字段——故入库快照改 PRESENT 对 review 段与 `resume_confirmed` 复跑零影响。MATCHED 保留为清单视图别名（`build_checklist`/golden scorer 不动，fixtures 冻结面不动）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_bid_review_worker.py` 追加（文件已有 sqlite 夹具，用最小直调 `_write_baselines`）：

```python
@pytest.mark.asyncio
async def test_write_baselines_normalizes_matched_to_present(db):
    """C-05(EAI-CUSTOM 2026-11-06):入库快照 bid.attachments/attachment_index 的
    MATCHED → PRESENT;引擎内存态(fields 原对象)不得被改。"""
    from app.extensions.bid_review import worker

    t = await crud.create_task(db, owner_id="u1")
    fields = {
        "bid.attachments": [{"no": "1", "name": "营业执照", "status": "MATCHED"}],
        "bid.attachment_index": [{"no": "1", "name": "营业执照", "status": "MATCHED"}],
        "tender.attachment_requirements": [{"no": "1", "name": "营业执照", "mandatory": "★"}],
    }
    snapshot = fields["bid.attachments"][0]
    await worker._write_baselines(db, t.id, [{"doc_id": "bid.pdf", "role": "bid"}], fields, "h" * 16)
    rows = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    stored = rows[0].payload["fields"]
    assert stored["bid.attachments"][0]["status"] == "PRESENT"
    assert stored["bid.attachment_index"][0]["status"] == "PRESENT"
    assert stored["tender.attachment_requirements"][0].get("status") is None  # 只动两容器
    assert snapshot["status"] == "MATCHED"  # 调用方内存对象不被改(引用同一 dict)
```

（夹具名按目标文件既有约定对齐：`db`/owner 名与同文件相邻用例一致；先建 task 行保证 `list_baselines` owner 过滤命中。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_worker.py -v -k "normalizes_matched"`
Expected: FAIL（stored status 仍为 MATCHED）

- [ ] **Step 3: 实现**

`worker.py` 新增 helper（放 `_write_baselines` 定义 :446 之前）：

```python
def _normalize_attachment_status(fields: dict) -> dict:
    """C-05 入库归一(EAI-CUSTOM 2026-11-06,整合版规格 §3.3 裁决):入库快照的
    bid.attachments[].status 与 bid.attachment_index[].status MATCHED → PRESENT
    (规格 L2 枚举);引擎内存态不改——浅拷贝顶层+重建两列表,调用方 fields 原对象
    不被改(review 段照旧)。MATCHED 保留为清单视图别名(build_checklist/golden
    scorer/fixtures 不动,CALIBRATION 注记);引擎判定只认实体身份不认行 status,
    resume 复跑安全。"""
    out = dict(fields)
    for key in ("bid.attachments", "bid.attachment_index"):
        rows = out.get(key)
        if isinstance(rows, list):
            out[key] = [
                {**r, "status": "PRESENT"} if isinstance(r, dict) and r.get("status") == "MATCHED" else r
                for r in rows
            ]
    return out
```

`_write_baselines` 体首行（docstring 之后、`delete` 语句之前）插入：

```python
    fields = _normalize_attachment_status(fields)  # C-05 入库归一:入库快照 PRESENT,内存态不动
```

- [ ] **Step 4: 跑测试确认通过 + 家族回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_worker.py -v && PYTHONPATH=. uv run pytest tests/ -k bid_review -q && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden.extract`
Expected: PASS 全绿 + 金标准离线快照 26/26（fixtures 冻结面用 MATCHED，scorer 未动）

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/bid_review/worker.py backend/tests/test_bid_review_worker.py
git commit -m "feat(bid-review): C-05入库归一——bid.attachments/attachment_index快照MATCHED→PRESENT单点边界(_write_baselines入口);引擎内存态/清单视图别名/golden冻结面不动"
```

---

### Task 4: 记档回写（CALIBRATION + 对齐规格书）

**Files:**
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`（文末新增一节）
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`（§3.3 两行 + §5 第 4 条 + §6 P1 行）
- Test: 无（docs-only）

- [ ] **Step 1: CALIBRATION.md 文末追加**

```markdown
## C-05/C-08 口径注记（2026-11-06，P1-α 落地）

- **C-05**：入库快照 `bid.attachments[].status`/`bid.attachment_index[].status` 的 `MATCHED` 已归一为 **PRESENT**（规格 L2 枚举；`worker._normalize_attachment_status` 单点边界）。引擎内存态与判定不变；**MATCHED 保留为清单视图别名**——golden fixtures 的 `status_by_no` 钉值与 `build_checklist` 产出口径**不动**，本表既有行继续有效。
- **C-08**：`bid_review_issues` 新增 `semantic_verdict`（引擎 raw 四值 full|partial|none|unclear，sem/hyb 专属）与 `state`（state_map 分层业务态）两列；`verdict` 收敛值（violation|need_human|unclear）与四态判定表**不变**。verdict 值域迁 PASS/FAIL/UNKNOWN/ERROR/SKIP 挂 P1-β（届时随规则扩包同批重标定本表）。
```

- [ ] **Step 2: 对齐规格书三处回写（本任务提交后回填 commit hash）**

`docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`：

1. §3.3 表 C-05/C-08 行的「处置」列尾追加：`→ 已兑付（2026-11-06 P1-α：<commit-hash>；入库 PRESENT+清单别名 / semantic_verdict+state 落库，verdict 值域迁 P1-β）`。
2. §5 第 4 条改为：`4. ~~（P1 前置）枚举三拆 alias、MATCHED→PRESENT 归一、CALIBRATION 裁决表回写整合版侧~~ → 已兑付（2026-11-06 P1-α，Task 2/3/4；verdict 值域迁移部分挂 P1-β）`。
3. §6 P1 行中「枚举三拆」移除，行尾追加：`（枚举三拆已于 2026-11-06 P1-α 兑付，verdict 值域迁 P1-β）`。

- [ ] **Step 3: 提交（docs/superpowers 须 -f）**

```bash
git add backend/app/extensions/bid_review/golden/CALIBRATION.md
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): C-05/C-08口径注记回写——CALIBRATION新增节+对齐规格书§3.3/§5/§6已兑付标注(P1-α收官)"
```

---

## 收尾验收（controller 执行，implementer 不做）

1. `cd backend && uv run pytest tests/ -q` 全绿（588+ 基线只增不减，6 skipped 持平）。
2. 离线金标准 26/26；`git log --oneline -4` 四 commit 各自独立可回滚。
3. wolf 记档（controller 侧）：memory 行 + buglog 无新账（Task 1 属 bug-4086 兑付，复用原条目 occurrences+1）。
4. 后续：活体复跑不进本批（烧配额须用户点头）；P1-β plan 待用户裁决后另起。
