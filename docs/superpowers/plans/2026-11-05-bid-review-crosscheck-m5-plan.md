# B立项 M5 交叉自检+质量门禁(§八三检 + §十指标)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯服务端零 LLM 交叉自检(`payload["crosscheck"]`:声明↔实体双向 / 页码偏移>5 降置信 / 正副本一致性 / 核心字段成功率)+ §十指标投影(`unknown_ratio`/`rules_total` 入 summary,`GET /metrics/extraction` 聚合端点)+ 负证据覆盖 100% 测试门禁。**B立项收官段。**

**Architecture:** 完全复用 M4 clusters.py 先例——纯函数模块(crosscheck.py,difflib 不需要,纯集合/比较),worker perf 段后无条件跑(零配额),产出落 `payload["crosscheck"]`(**非字段路径**→registry/universe/M0/golden 零触碰);summary 新键 additive。§八/§十原文未入库(spec 只有两行索引),语义为本计划显式裁决并逐条挂账原文复核。

**Tech Stack:** Python 3.12(stdlib 集合比较), pytest, ruff;全部在 `backend/`。

**Spec:** `docs/superpowers/specs/2026-11-04-bid-review-extract-engine-b-design.md` §5 M5 行(线 42)+ 线 67 明细 + 线 73(抽取分只升不降)。

---

## 七裁决(2026-11-05,取证后定案)

1. **交叉自检纯服务端零 LLM**(裁决基座):新模块 `engine/crosscheck.py::run_crosscheck(fields, candidates) -> dict`,纯函数零 LLM 零配额。产出落 `payload["crosscheck"]` 键(baselines 行持久化),**不进 fields**——universe 77 逐位不动,materials_hash 不含 crosscheck(其只是 fields 的派生报告,重算无意义),M0 26/26 与 golden 55 全不翻。worker 在 M4 perf 段之后**无条件跑**(无门控——免费),失败隔离(except→warning,无 crosscheck 键,基线照常交付)。
2. **声明↔实体双向**(§八1):`declarations = {missing, extra}`。**missing** = `tender.required_declarations` 编码不在 `bid.declaration_letter_codes`(声明有实体无→强 MISSING 方向;L1-021 规则已有裁决面,crosscheck 是交叉报告面,零规则改动);**extra** = bid 编码不在 tender 清单(实体有清单无→**提示补清单,不判 MISSING**——与 L1-021 `all` 而非 `set_eq` 语义对齐:清单外自附不算违规)。
3. **页码偏移>5 降置信**(§八2,消费 M2 形态):`page_offset = {flag, max_abs_offset, affected_codes}` 从 `bid.section_tree` 行的 `offset_flag`(M2 已算,注释明言「消费在 M5 交叉自检」)归并。降置信落**注记形态**:flag 命中时 worker 对 provenance page 非 null 的 paths 在 `fields_conf[path]` 增 `"page_offset": true` 键(**不覆盖** conf/verified——模型自报与服务端核验信号不污染);verify 第4道 gate/规则链自动消费(页偏移→need_human)挂账 R2+(动规则语义翻 golden,零规则语义改动铁律)。
4. **正副本一致性=candidates 跨文档同字段多值检测**:`copy_conflicts = [{path, values, doc_ids}]`——同一字段路径在 ≥2 个 doc_id 观察到 ≥2 个归一(str.strip)不同非空值→advisory 报告,**不判违规**(哪份是正本无法从数据判定)。§八原文未入库,此语义为本计划自定,显式挂账原文复核。
5. **§十指标三分落位**:
   - (a) `core_success_rate`(抽取时):CORE_FIELDS 8 条 bid 商业关键路径(`bid.total_price`/`bid.total_price_words`/`bid.validity_days`/`bid.warranty_period`/`bid.deposit_amount`/`bid.commitment_completion_date`/`bid.bid_letter_signatory`/`bid.authorization_letter_present`)非 null 占比(4 位小数),入 crosscheck。§十原文未入库,清单自定挂账复核。
   - (b) `unknown_ratio`+`rules_total`(审查时):`summarize_issues(issues, rules_total=None)` 扩签名(routers 既有调用零改动,新键 additive,rules_total=None 时 ratio=None 伪零纪律);`_run_review_stage` 返回 `(written, len(pack.rules))`(现两调用点均弃返回值,改绑安全),done 帧 summary 携带。
   - (c) **负证据覆盖 100% 本轮=测试门禁**(§十 pytest 套件成员):断言 attachments 平件 MISSING、复合父行真 MISSING、复合子行真 MISSING 一律带非 null `negative_evidence`(M1 门禁实现已在,本轮补回归锁);issue 级结构化负证据上浮(端点可算)挂账 R2+(动 issue 契约)。
6. **metrics 端点** `GET /metrics/extraction`(治理域口径同 `/rulepacks` 与既有两 metrics 端点:全库聚合,owner 仅作鉴权):每任务取**最新**基线行(order_by asc 后写覆盖=最新),聚合 `core_success_rate` 均值 / `page_offset_tasks` / `copy_conflict_total` / `declarations_missing_total` / `declarations_extra_total`。伪零纪律:无任务计数 0、均值 None。
7. **M0 不扩+零规则语义改动**:零新字段路径(71 首段逐位不动,universe 77 不动);golden 55 零翻红(golden 走 rule_runner 直喂,不经 worker/payload);summary 新键 additive 前端容忍。

---

### Task 1: 计划预提交

- [x] **Step 1:** `git add -f docs/superpowers/plans/2026-11-05-bid-review-crosscheck-m5-plan.md && git commit -m "docs(bid-review): B立项M5交叉自检计划——纯服务端三检+§十指标投影+负证据门禁七裁决"`

### Task 2: crosscheck.py 纯函数 + 契约测试

**Files:** engine/crosscheck.py(新建);tests/test_bid_review_crosscheck.py(新建)

- [x] **Step 1: 失败测试**

```python
# tests/test_bid_review_crosscheck.py
from app.extensions.bid_review.engine.crosscheck import (
    CORE_FIELDS, annotate_page_offset, run_crosscheck,
)

class TestDeclarations:
    def test_missing_and_extra_bidirectional(self):
        cc = run_crosscheck(
            {"tender.required_declarations": ["A-DECL-1", "A-DECL-2"], "bid.declaration_letter_codes": ["A-DECL-1", "A-DECL-X"]},
        )
        assert cc["declarations"]["missing"] == ["A-DECL-2"]  # 强 MISSING 方向
        assert cc["declarations"]["extra"] == ["A-DECL-X"]  # 提示补清单,不判 MISSING

    def test_both_empty(self):
        assert run_crosscheck({})["declarations"] == {"missing": [], "extra": []}

class TestPageOffset:
    def test_flag_from_section_tree(self):
        rows = [{"code": "1", "offset": 7, "offset_flag": True}, {"code": "2", "offset": -2, "offset_flag": False}]
        cc = run_crosscheck({"bid.section_tree": rows})
        assert cc["page_offset"] == {"flag": True, "max_abs_offset": 7, "affected_codes": ["1"]}

    def test_no_offset(self):
        assert run_crosscheck({"bid.section_tree": [{"code": "1", "offset": None, "offset_flag": None}]})["page_offset"]["flag"] is False
        assert run_crosscheck({})["page_offset"]["max_abs_offset"] is None

class TestCopyConflicts:
    def test_cross_doc_distinct_values(self):
        cands = {"bid.total_price": [
            {"value": "1000", "doc_id": "a.pdf"}, {"value": "1200", "doc_id": "b.pdf"},
        ]}
        cc = run_crosscheck({}, cands)
        assert cc["copy_conflicts"] == [{"path": "bid.total_price", "values": ["1000", "1200"], "doc_ids": ["a.pdf", "b.pdf"]}]

    def test_same_value_or_single_doc_no_conflict(self):
        same = {"p": [{"value": "1000", "doc_id": "a"}, {"value": "1000", "doc_id": "b"}]}
        one_doc = {"p": [{"value": "1", "doc_id": "a"}, {"value": "2", "doc_id": "a"}]}
        assert run_crosscheck({}, same)["copy_conflicts"] == []
        assert run_crosscheck({}, one_doc)["copy_conflicts"] == []

class TestCoreSuccessRate:
    def test_ratio_and_empty(self):
        fields = {p: ("x" if i < 6 else None) for i, p in enumerate(CORE_FIELDS)}
        assert run_crosscheck(fields)["core_success_rate"] == 0.75
        assert run_crosscheck({})["core_success_rate"] == 0.0
        assert len(CORE_FIELDS) == 8

class TestAnnotatePageOffset:
    def test_annotates_page_bearing_paths_only_when_flag(self):
        fc = {"a": {"conf": 0.9, "verified": True}, "b": {"conf": None, "verified": False}}
        prov = {"a": {"page": 3}, "b": {"page": None}}
        off = {"flag": True, "max_abs_offset": 7, "affected_codes": ["1"]}
        out = annotate_page_offset(fc, prov, off)
        assert out["a"] == {"conf": 0.9, "verified": True, "page_offset": True}
        assert "page_offset" not in out["b"]  # page null 不注记

    def test_no_flag_no_mutation(self):
        fc = {"a": {"conf": 0.9, "verified": True}}
        assert annotate_page_offset(fc, {"a": {"page": 3}}, {"flag": False}) == fc
        assert annotate_page_offset(None, None, None) in (None, {})
```

- [x] **Step 2: 红** → **Step 3: 实现**(crosscheck.py:run_crosscheck 分派四私有函数+annotate_page_offset+CORE_FIELDS 常量;声明比较 str.strip 归一)→ **Step 4: 绿** → **Step 5: commit**(`feat(bid-review): B立项M5交叉自检——crosscheck.py纯函数(声明双向/页偏移/正副本candidates/核心字段成功率)+fields_conf页偏移注记`)

### Task 3: worker crosscheck 段 + baselines 持久化

**Files:** worker.py;tests/test_bid_review_worker.py

- [x] **Step 1: 失败测试**(镜像 M3/M4 段测试:merged(payload["crosscheck"] 四键齐+materials_hash 不变——crosscheck 不进 fields;页偏移 fixture(section_tree offset_flag=True+provenance page 3)→fields_conf 注记 page_offset:true;失败隔离(crosscheck_fn 注入 raise→无键);零字段→crosscheck 空壳键照落)

```python
async def test_m5_crosscheck_landed_and_hash_untouched(...):
    await advance_task(db, t.id, owner_id="u1", docs=docs, extract_fn=_m5_extract(offset=True), wait_confirm=True)
    payload = await _first_payload(db, t.id)
    cc = payload["crosscheck"]
    assert set(cc) == {"declarations", "page_offset", "copy_conflicts", "core_success_rate"}
    assert cc["page_offset"]["flag"] is True
    # fields_conf 注记:provenance page 非 null 路径
    assert any(v.get("page_offset") is True for v in (payload["fields_conf"] or {}).values())
    assert payload["materials_hash"] == materials_hash(payload["fields"])  # crosscheck 不进 fields
```

- [x] **Step 2: 红** → **Step 3: 实现**:worker perf 段后加 crosscheck 段(try/except 隔离;`run_crosscheck(fields, payload.get("candidates"))`→`payload={**payload,"crosscheck":...}`;flag 命中→`annotate_page_offset(payload.get("fields_conf"), payload.get("provenance"), ...)`);`_write_baselines` 增 `crosscheck: dict | None = None` 参数,payload dict 增 `"crosscheck": crosscheck or {}`,advance_task 调用传 `payload.get("crosscheck")` → **Step 4: 绿** → **Step 5: commit**(`feat(bid-review): B立项M5 worker交叉自检段——payload.crosscheck落库+fields_conf页偏移注记+hash不触及`)

### Task 4: summary §十指标(unknown_ratio+rules_total)

**Files:** worker.py;tests/test_bid_review_worker.py

- [x] **Step 1: 失败测试**

```python
def test_summary_unknown_ratio():
    issues = [{"severity": "fatal", "need_human": False}, {"severity": "info", "need_human": True}]
    s = summarize_issues(issues, rules_total=8)
    assert s["rules_total"] == 8 and s["unknown_ratio"] == 0.125
    s2 = summarize_issues(issues)  # routers 既有调用零改动
    assert s2["unknown_ratio"] is None and s2["rules_total"] is None
    assert summarize_issues(issues, rules_total=0)["unknown_ratio"] is None  # 伪零纪律
```

- [x] **Step 2: 红** → **Step 3: 实现**:summarize_issues 加 `rules_total=None` 参数+两新键;`_run_review_stage` 返回 `(written, len(pack.rules))`;advance_task/resume_confirmed 两调用点改绑 `written, rules_total = ...` 并把 rules_total 传 summarize_issues → **Step 4: 绿** → **Step 5: commit**(`feat(bid-review): B立项M5 §十指标——summary.unknown_ratio+rules_total(伪零纪律;routers调用零改动)`)

### Task 5: GET /metrics/extraction 聚合端点

**Files:** routers.py;tests/test_bid_review_metrics.py

- [x] **Step 1: 失败测试**

```python
async def test_metrics_extraction_aggregates_latest(...):
    # 同任务两行基线(先旧后新),取新行 crosscheck;另一任务无 crosscheck 键不计
    ...插入 BaselinePackage(payload={"crosscheck": {"core_success_rate": 0.75, "page_offset": {"flag": True}, "copy_conflicts": [1], "declarations": {"missing": ["x"], "extra": []}}})...
    r = await client.get("/metrics/extraction")
    body = r.json()
    assert body["tasks"] == 1 and body["core_success_rate_avg"] == 0.75
    assert body["page_offset_tasks"] == 1 and body["copy_conflict_total"] == 1
    assert body["declarations_missing_total"] == 1 and body["declarations_extra_total"] == 0

async def test_metrics_extraction_empty(...):
    body = (await client.get("/metrics/extraction")).json()
    assert body["tasks"] == 0 and body["core_success_rate_avg"] is None
```

- [x] **Step 2: 红** → **Step 3: 实现**(select(BaselinePackage) 全库 order_by created_at asc;dict 按 task_id 后写覆盖=最新;五聚合;口径注释同 fail_attribution「全库聚合,owner 仅作鉴权」)→ **Step 4: 绿** → **Step 5: commit**(`feat(bid-review): B立项M5 GET /metrics/extraction——最新基线crosscheck五聚合(伪零纪律)`)

### Task 6: 负证据覆盖门禁 + 全量验证

**Files:** tests/test_bid_review_crosscheck.py(追加)

- [x] **Step 1: 门禁测试**(§十 pytest 套件成员——负证据覆盖 100% 回归锁;夹具经 attachments.att_check 全链路,逐行断言三种 MISSING 形态都带非 null negative_evidence)

```python
class TestNegativeEvidenceCoverageGate:
    """§十指标「负证据覆盖 100%」测试门禁(裁决⑤c):M1 门禁实现已在,本锁防回归。
    平件 MISSING/复合父行真 MISSING/复合子行真 MISSING 一律带非 null negative_evidence。"""

    def test_flat_and_composite_missing_carry_negative_evidence(self):
        # 复用既有 attachments 夹具形态构造:平件要求缺失→per_req MISSING 行 negative_evidence 非 None;
        # 复合父行真缺失→parent_negative_evidence 非 None;子行 MISSING→negative_evidence 非 None
        ...
```

(实现时按 test_bid_review_attachments.py 既有夹具同构落;断言点:①平件 per_req MISSING 行 ②`_composite` 返回 parent_negative_evidence ③子行 sub_results MISSING。若既有测试已全覆盖三形态,本 Task 收缩为一条汇总断言并注明。)

- [x] **Step 2: 绿** → **Step 3: 全量验证** `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(后台;期望全绿,预计 ~546);golden 55+M0 26/26 含在全家(零翻红);71 首段锁+universe 77 不动(registry 测试锁);ruff check --fix + format 改动文件→重跑受影响测试

### Task 7: 收官

- [x] **Step 1:** push 重试至 `0\t0`
- [x] **Step 2:** wolf(memory;buglog 若 bug)+ anatomy(crosscheck.py/新测试/routers/worker 条目)+ plan 勾选 docs commit(`git add -f`)
- [x] **Step 3:** auto-memory `bid-review-extract-engine-m5-landed.md` + MEMORY.md 索引;终报 = **B立项五段全收官总结**+队列下一项(挂账池:活体回采/R2+ 规则族/§八§十原文复核)+「继续」收尾

### 挂账(显式)

- §八/§十原文到位→复核裁决2/3/4/5a 语义(当前两行索引,盲设计显式标注)
- 页偏移注记进 verify 第4道 gate→need_human 自动降级(R2+;动规则语义翻 golden)
- issue 级结构化负证据上浮→metrics 端点可算负证据覆盖率(R2+;动 issue 契约)
- CORE_FIELDS 清单以 spec §十原文校准(R2+)
- [x] 活体回采(**2026-11-05 已兑付**:walkthrough 双文档经 worker.advance_task 生产管线全链路单跑(scripts/bid_review_live_full.py),抽取分 **21/26=0.8077 > 0.7308** 只升不降达成;crosscheck 四指标活体值:declarations missing/extra=[]、page_offset flag=false、copy_conflicts=[]、core_success_rate=0.25;第二段门信号本轮未触发=诚实缺席;详见 annotations meta.live_run;plan docs/superpowers/plans/2026-11-05-bid-review-live-recapture-plan.md)
