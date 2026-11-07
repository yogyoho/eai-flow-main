# P1-β批五(gate_status 四态判定式 + tender 差表落账)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 规格 §5.7.2 门禁四态判定式落地(SUBMITTABLE/CONDITIONAL/NOT_SUBMITTABLE/PENDING_HUMAN,现仓库仅二值 fatal_hits);tender 33 字段权威差表落账(字段实补挂批六)。

**Architecture:** `compute_gate_status(issues)` 单点落 worker.py(`_issue_get` 双形态),`summarize_issues` additive 键 `gate_status`(双 API 面共享);双渲染器报告文案四态化(「命中 N 项」计数保持 `_fatal_hits` 现口径);前端 GateMetricsRow 四态 pill。零 DB 列(派生值)、零规则变更、零宇宙变化。

**Tech Stack:** Python 3.12/pytest;前端 rstest(非 vitest,tests/unit/extensions/ 平铺,findAllByText 须 await——bug-4143)。

---

## 裁决表(controller-locked,实现者不得改动;偏差按裁决精神处理并声明)

| # | 裁决 |
|---|---|
| A-β5-① | 判定口径=规格 §5.7.2 逐字:存在 fatal FAIL→NOT_SUBMITTABLE;elif fatal UNKNOWN→PENDING_HUMAN;elif major FAIL 或 L3 major INCONSISTENT→CONDITIONAL;else SUBMITTABLE。判定只读**值域/状态域**(verdict/state),need_human 旗标不参与 gate 判定(旗标口径本身零改动,批三裁决④精神);false_positive(复核域)自然不计(verdict 非 FAIL/UNKNOWN)。 |
| A-β5-② | NOT_SUBMITTABLE 子件用纯值域判定(fatal+FAIL),**不**复用 routers `_fatal_hits`(其含旗标排除且在 routers 层,worker 不得反向 import——层级纪律)。`_fatal_hits` 函数逐字不动,继续供「命中 N 项」计数。实践上 fatal+FAIL+need_human 行不可达(det 违规 flag=False),理论分歧采规格字面,记档即可。 |
| A-β5-③ | 隔离四条照规格:L4 任何结论不参与(layer==L4 跳过,counts_toward_bid_gate 同构);EXTRA/false_positive 不计;UNKNOWN 不得当 PASS;L3 只影响 CONDITIONAL(且仅 severity=major + state=INCONSISTENT)。 |
| A-β5-④ | gate_status=派生值不落库:summarize_issues 增 additive 键 `summary["gate_status"]`(worker 落 progress.summary 与 issues API 共用);报告 html/md 双渲染器文案四态化(NOT_SUBMITTABLE 保留「命中致命红线 N 项,建议整改后重新审查。」原文含计数,其余三态用规格 §3.2.7 报告文案逐字:SUBMITTABLE=未发现否决性风险,可按流程提交。/CONDITIONAL=存在需整改项,建议整改后提交。/PENDING_HUMAN=关键项无法自动判定,必须人工确认。)。 |
| A-β5-⑤ | 数字锁:包 50(det 44)/宇宙 92/golden 73/0 不变(零规则变更批);family 因新测试增长**允许**(测试增长不属规则变更)。 |
| A-β5-⑥ | 前端:GateMetricsRow(primitives.tsx)增 gate_status 四态 pill;既有待人工格等 flag 口径展示零改动;Summary 类型 additive 可选键。 |
| A-β5-⑦ | tender 33 字段:**批五只落权威差表进 spec**(逐字段 verdict=已映射(仓库别名)/缺(候选+消费规则)/双向无消费),**字段实补挂批六**——须与消费规则同批落(3-layer 规则:无消费字段=silo),universe bump 批六显式解锁。 |
| A-β5-⑧ | 实现者禁区照旧:`.wolf/`、`docs/superpowers/`、golden 面、五锁文件结构、config.yaml。控制器包办台账。 |

## 实态勘误(实现者先验证再动手)

- `summarize_issues` worker.py:211-245(`_issue_get` 双形态 helper :208);`_fatal_hits` routers.py:588-593;报告 html 渲染 gate_txt :633、`_render_report_md` 同口径(R4)——grep「命中致命红线」定位两处。
- state 域:llm_runner.py:54-56 state_map,L3 `{partial|none|inconsistent→INCONSISTENT}`;issue 的 state 键双形态经 `_issue_get`。
- verdict 域=批三五值(FAIL/PASS/UNKNOWN/ERROR/SKIP;false_positive 复核域)。L4 行 gate 跳过层=routers:591-593 同构。
- 前端:GateMetricsRow 在 `frontend/src/extensions/bid-review/components/primitives.tsx`(与 verdictPill 同文件;verdictPill 零调用点勿动)。Summary 类型在 `frontend/src/extensions/bid-review/types.ts`。
- 后端 family gate=`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(平铺;**勿**用 tests/unit/extensions/,那是前端 rstest 布局)。
- summarize 钉面:test_bid_review_worker.py / _routers.py / _worker_sem.py(无 exact-dict 断言,additive 键安全——实现者跑门确认)。

---

### Task 1: gate_status 四态(后端:worker + 双渲染器 + 测试)

**Files:**
- Modify: `backend/app/extensions/bid_review/worker.py`(常量 + compute_gate_status + summarize_issues additive)
- Modify: `backend/app/extensions/bid_review/routers.py`(双渲染器 gate_txt 四态)
- Test: `backend/tests/test_bid_review_worker.py`(新 test class + summarize 键钉)

- [ ] **Step 1: 写失败测试**(test_bid_review_worker.py 尾部追加;文件既有风格先看——dict/ORM 双形态测法照既有)

```python
class TestGateStatus:
    """批五 gate_status 四态判定(A-β5-①②③,规格 §5.7.2 逐字)。"""

    @staticmethod
    def _mk(sev, verdict, layer="L1", state=None, need_human=False):
        return {"severity": sev, "verdict": verdict, "layer": layer, "state": state, "need_human": need_human}

    def test_submittable_when_clean(self):
        assert compute_gate_status([self._mk("major", "PASS"), self._mk("minor", "UNKNOWN", layer="L3")]) == "SUBMITTABLE"

    def test_not_submittable_on_fatal_fail(self):
        issues = [self._mk("major", "FAIL"), self._mk("fatal", "FAIL", layer="L2")]
        assert compute_gate_status(issues) == "NOT_SUBMITTABLE"

    def test_pending_human_on_fatal_unknown(self):
        # fatal UNKNOWN(含 need_human 旗标行——旗标不参与判定,A-β5-①)
        issues = [self._mk("major", "FAIL"), self._mk("fatal", "UNKNOWN", need_human=True)]
        assert compute_gate_status(issues) == "PENDING_HUMAN"

    def test_conditional_on_major_fail(self):
        assert compute_gate_status([self._mk("major", "FAIL", layer="L2")]) == "CONDITIONAL"

    def test_conditional_on_l3_major_inconsistent(self):
        issues = [self._mk("major", "PASS", layer="L3", state="INCONSISTENT")]
        assert compute_gate_status(issues) == "CONDITIONAL"

    def test_l3_non_major_inconsistent_not_conditional(self):
        issues = [self._mk("minor", "PASS", layer="L3", state="INCONSISTENT")]
        assert compute_gate_status(issues) == "SUBMITTABLE"

    def test_l4_excluded_entirely(self):
        issues = [self._mk("fatal", "FAIL", layer="L4"), self._mk("fatal", "UNKNOWN", layer="L4")]
        assert compute_gate_status(issues) == "SUBMITTABLE"

    def test_false_positive_and_error_not_counted(self):
        issues = [self._mk("fatal", "false_positive"), self._mk("major", "ERROR")]
        assert compute_gate_status(issues) == "SUBMITTABLE"

    def test_fatal_fail_wins_over_fatal_unknown(self):
        issues = [self._mk("fatal", "UNKNOWN"), self._mk("fatal", "FAIL")]
        assert compute_gate_status(issues) == "NOT_SUBMITTABLE"

    def test_empty_and_none(self):
        assert compute_gate_status([]) == "SUBMITTABLE"
        assert compute_gate_status(None) == "SUBMITTABLE"

    def test_summarize_adds_gate_status(self):
        issues = [self._mk("fatal", "FAIL", layer="L2")]
        summary = summarize_issues(issues, rules_total=10)
        assert summary["gate_status"] == "NOT_SUBMITTABLE"
```

import 行补 `compute_gate_status`(该文件已 import summarize_issues)。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_worker.py::TestGateStatus -v
```
预期:FAIL(ImportError 或 KeyError)。

- [ ] **Step 3: 实现 worker.py**

`summarize_issues` 紧上方新增(SEVERITY_ORDER 附近):

```python
GATE_SUBMITTABLE = "SUBMITTABLE"
GATE_CONDITIONAL = "CONDITIONAL"
GATE_NOT_SUBMITTABLE = "NOT_SUBMITTABLE"
GATE_PENDING_HUMAN = "PENDING_HUMAN"


def compute_gate_status(issues) -> str:
    """门禁四态判定(批五,规格 §5.7.2 逐字;A-β5-①②③):fatal FAIL→NOT_SUBMITTABLE,
    elif fatal UNKNOWN→PENDING_HUMAN,elif major FAIL 或 L3 major INCONSISTENT→CONDITIONAL,
    else SUBMITTABLE。只读值域/状态域(verdict/state),need_human 旗标不参与(旗标口径零改动);
    L4 任何结论不参与(counts_toward_bid_gate 同构);false_positive 复核域不计;UNKNOWN 不得当 PASS。
    派生值不落库(routers._fatal_hits 逐字不动,继续供「命中 N 项」计数——A-β5-②)。"""
    fatal_fail = fatal_unknown = major_fail = l3_inconsistent = False
    for issue in issues or []:
        layer = str(_issue_get(issue, "layer") or "")
        if layer == "L4":
            continue
        sev = str(_issue_get(issue, "severity") or "")
        verdict = str(_issue_get(issue, "verdict") or "")
        if sev == "fatal":
            if verdict == "FAIL":
                fatal_fail = True
            elif verdict == "UNKNOWN":
                fatal_unknown = True
        elif sev == "major" and verdict == "FAIL":
            major_fail = True
        if layer == "L3" and sev == "major" and str(_issue_get(issue, "state") or "") == "INCONSISTENT":
            l3_inconsistent = True
    if fatal_fail:
        return GATE_NOT_SUBMITTABLE
    if fatal_unknown:
        return GATE_PENDING_HUMAN
    if major_fail or l3_inconsistent:
        return GATE_CONDITIONAL
    return GATE_SUBMITTABLE
```

`summarize_issues` 尾部(`advisory` 行后、`return summary` 前)加一行,docstring 末尾补一行:
`批五(A-β5-④):增 gate_status 四态派生键(compute_gate_status,双 API 面共享)。`

```python
    summary["gate_status"] = compute_gate_status(issues)
```

- [ ] **Step 4: 双渲染器四态文案(routers.py)**

grep「命中致命红线」定位 html/md 两处。每处改为(gate_txt 行替换,`_GATE_TXT` 模块级常量放 `_fatal_hits` 附近):

```python
_GATE_TXT = {
    "NOT_SUBMITTABLE": "存在否决性风险,不建议提交。",
    "PENDING_HUMAN": "关键项无法自动判定,必须人工确认。",
    "CONDITIONAL": "存在需整改项,建议整改后提交。",
    "SUBMITTABLE": "未发现否决性风险,可按流程提交。",
}
```

```python
    gate_status = worker.compute_gate_status(issues)
    if gate_status == "NOT_SUBMITTABLE":
        gate_txt = f"命中致命红线 {len(fatal_hits)} 项,建议整改后重新审查。"
    else:
        gate_txt = _GATE_TXT.get(gate_status, _GATE_TXT["SUBMITTABLE"])
```

html 渲染的 class 行(`"hit" if fatal_hits else "ok"`)同步改:`"hit" if gate_status == "NOT_SUBMITTABLE" else ("warn" if gate_status in ("PENDING_HUMAN", "CONDITIONAL") else "ok")`(md 渲染无 class 逻辑则只改文案)。`fatal_hits = _fatal_hits(issues)` 行**保留不动**(计数继续)。若 md/html 渲染器不 import worker,确认 routers 已有 `worker` import(_l4_advisory_cap 在用,应有)。

- [ ] **Step 5: 跑测试确认通过 + 回归门**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_worker.py tests/test_bid_review_routers.py -v
PYTHONPATH=. uv run pytest tests/ -k bid_review -q
PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_golden_extract.py -q
PYTHONPATH=. uv run python -c "from app.extensions.bid_review.engine.registry import universe; print(len(universe()))"
```
预期:新测试全绿;family 全绿(既有数 684p/6s+新);golden **113p/73 题**;universe **92**(A-β5-⑤)。

- [ ] **Step 6: lint + commit**

```bash
cd D:/eai/eai-flow-main/backend && uv run ruff check app/extensions/bid_review/worker.py app/extensions/bid_review/routers.py tests/test_bid_review_worker.py
cd D:/eai/eai-flow-main
git add backend/app/extensions/bid_review/worker.py backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_worker.py
git commit -m "feat(bid-review): 批五T1——gate_status四态判定式落地:worker.compute_gate_status(规格§5.7.2逐字,fatal FAIL→NOT_SUBMITTABLE/fatal UNKNOWN→PENDING_HUMAN/major FAIL或L3 major INCONSISTENT→CONDITIONAL/else SUBMITTABLE;值域状态域判定,旗标不参与,L4隔离,false_positive不计,A-β5-①②③)+summarize_issues additive键(双API面共享,A-β5-④)+双渲染器四态文案(命中N项计数保持_fatal_hits现口径逐字不动,A-β5-②);零规则变更数字锁92/73不变(A-β5-⑤)"
```

**Review 分工:** gate 语义属判定核 → agent reviewer。

### Task 2: 前端 GateMetricsRow 四态 pill

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/primitives.tsx`(GateMetricsRow 增 pill)
- Modify: `frontend/src/extensions/bid-review/types.ts`(Summary additive)
- Test: `frontend/tests/unit/extensions/` 下既有 bid-review GateMetricsRow/summary 相关 rstest 文件(实态定位,命名随既有)

- [ ] **Step 1: 实态定位**:读 primitives.tsx 的 GateMetricsRow 现形与 types.ts Summary 类型;找 tests/unit/extensions/ 下既有相关 rstest。

- [ ] **Step 2: 写失败测试**(随既有文件风格):summary 带 gate_status="NOT_SUBMITTABLE" 渲染含「不建议提交」类文案/pill;SUBMITTABLE 渲染「可按流程提交」;gate_status 缺席(旧 summary)不炸、渲染零回归。

- [ ] **Step 3: 实现**:types.ts Summary 增 `gate_status?: string;`(注释:批五,规格 §5.7.2 四态派生键)。GateMetricsRow 增四态 pill(NOT_SUBMITTABLE/PENDING_HUMAN=error 红、CONDITIONAL=warning 黄、SUBMITTABLE=success 绿;四态中文文案与后端 _GATE_TXT 逐字同源)。既有待人工格等展示零改动(A-β5-⑥)。

- [ ] **Step 4: 跑 rstest + typecheck + lint**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm rstest --run tests/unit/extensions 2>/dev/null || pnpm test -- run tests/unit/extensions
pnpm typecheck && pnpm lint
```
预期:新测试绿;零 NEW 失败(HEAD 既有红线允许,批 gate=零新增失败)。

- [ ] **Step 5: commit**

```bash
cd D:/eai/eai-flow-main
git add frontend/src/extensions/bid-review/components/primitives.tsx frontend/src/extensions/bid-review/types.ts frontend/tests/unit/extensions/
git commit -m "feat(bid-review): 批五T2——前端gate_status四态pill:GateMetricsRow增判定展示(四态文案与后端_GATE_TXT同源,红/黄/绿分级),既有待人工格flag口径零改动(A-β5-⑥);Summary类型additive可选键"
```

**Review 分工:** 小面机械 diff → controller inline review。

### Task 3: tender 33 权威差表 + gate_status 行 + 批五兑付段(controller 直办)

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`

- [ ] **Step 1: 权威差表落 §5**(底稿如下,逐行 grep 证据核验后落账;证据=universe 实跑清单已核(28 tender 路径)+FIELd contracts+rulepack inputs):

| 规格字段(C-09/C-18 canonical) | 仓库路径(universe 实跑) | verdict |
|---|---|---|
| project_identity | tender.project_identity.{name,code,lot_section} | ✅ |
| deadline(C-16) | tender.bid_deadline | ✅ 别名 |
| validity_days | tender.required_validity_days | ✅ 别名 |
| max_price | tender.max_price | ✅ |
| price_includes_tax | tender.price_includes_tax | ✅ |
| tax_requirement | tender.tax_rate | ✅ 别名(语义核:T3 验) |
| duration_required(duration_req alias) | tender.max_duration | ✅ 别名 |
| warranty_required(warranty_req alias) | tender.min_warranty_period | ✅ 别名 |
| qualification_req(required_qualifications) | tender.required_qual_level | ✅ 别名(语义核) |
| performance_req(reference_requirement) | tender.min_similar_performance_count | ⚠️ 窄化别名(T3 验:规格是要求描述还是标量) |
| pm_req(pm_requirement) | — | ❌ 候选缺 |
| deposit | tender.deposit_required | ⚠️ 窄化别名(T3 验) |
| consortium_allowed | — | ❌ 候选缺 |
| subcontract_limit | — | ❌ 候选缺 |
| required_signatures | tender.signature_slots(邻接) | ⚠️ 语义核 |
| mandatory_declarations(C-18) | tender.required_declarations | ✅ 别名 |
| clauses | tender.substantive_clauses | ✅ |
| boq_items | tender.boq_items | ✅ |
| format_requirements | — | ❌ 候选缺(规格消费 L1-026) |
| file_composition | tender.file_composition | ✅ |
| volume_specs | tender.volume_specs | ✅ |
| electronic_files | tender.electronic_files | ✅ |
| required_sections | tender.required_sections | ✅ |
| tech_sections_required | — | ❌ 候选缺 |
| commitment_sections | — | ❌ 候选缺 |
| scoring_items | tender.scoring_items(B4 投影+抽取) | ✅ |
| required_figures | — | ❌ 候选缺 |
| attachment_requirements | tender.attachment_requirements | ✅ |
| attachment_count_reqs | — | ❌ 候选缺(邻接挂账 L2-002 逐册份数) |
| signature_slots | tender.signature_slots | ✅ |
| required_tables | — | ❌ 候选缺(规格消费 L2-040) |
| required_fields | tender.required_fields | ✅ |
| sample_required | — | ❌ 候选缺 |

T3 动作:⚠️ 行逐个 grep 规格 §6.2 该字段行+仓库对应路径 shape 对比,定 ✅/❌;❌ 行补「消费规则=规格卡号(仓库未覆盖规则则注)」;终表写进 spec §5 行下(细化为差表小节),批六挂账字段清单收口。

- [ ] **Step 2: §5 gate_status ❌→✅**(引批五 T1/T2 hash+规格 §5.7.2 判定式)+ 批五兑付段(段式同批四:A-β5-①..⑧ 兑付、数字锁实跑数、挂账:批六 tender 字段实补清单、gate_status 前端活体走查并批二续、PENDING_HUMAN live 无 fatal UNKNOWN 数据集留 live 批验证)。

- [ ] **Step 3: 全量门 + 台账**(family/golden/universe 实跑数写台账;`.wolf/` 三件+buglog 如有;plan 勾选;最终报告)。

**Review 分工:** docs → controller inline。
