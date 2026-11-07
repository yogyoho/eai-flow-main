# P1-β批三 verdict 五值迁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** verdict 字段值域从历史混布三值(violation/need_human/unclear)迁到引擎五值域 FAIL/PASS/UNKNOWN/ERROR/SKIP,复核域 false_positive 保留 verdict 列原样(C-08 值域三拆终章;semantic_verdict/state/review_state 三面零改动)。

**Architecture:** 单一真相模块 `engine/verdicts.py`(域常量 + `normalize_verdict` 别名归一);引擎四生产者(rule_runner/llm_runner/eval_core 隔离/verify 写入点)直产新值;golden loader 加载期别名归一保 CALIBRATION 冻结面(先例=C-05/C-22 MATCHED→PRESENT);DB 存量走 database.py 幂等 UPDATE 先例块;前端仅 verdictPill 值域映射。**零规则变更**——包 50/det 44/宇宙 92/golden 73 题全部数字不变,五锁文件零触碰。

**Tech Stack:** Python 3.12 + SQLAlchemy async(PostgreSQL)、FastAPI、golden 离线评测器、Next.js 16 + rstest。

---

## 基线(2026-11-07,批二续收官 9433ec536)

| 项 | 值 | 批三约束 |
|---|---|---|
| family `pytest tests/ -k bid_review` | **679 passed / 6 skipped / 0 failed** | 收官须全绿(已知 flaky:feedback 共享 DB/claimer bug-4013/4122/scheduled-tasks dom 并发,单独重跑判定) |
| golden CLI | **73 题 0 失败** | 批次硬门,夹具(cases/cases-l4/extract_cases/smoke)**零 diff** |
| core 包 | 50(det 44/hyb 5/sem 1)+ L4 包 10 | 不变 |
| 宇宙 | 92(collect_field_paths 81) | 不变 |
| 五锁 | registry/rule_runner/golden/rule_families/extract | **零触碰**(无规则/路径变更) |

**已知 flaky(非本批造成,勿误判)**:test_bid_review_feedback(共享 DB)、test_claimer_loop(bug-4013/4122)、scheduled-tasks task-form-dialog dom(happy-dom 并发,单跑过)、pnpm test 2 timeouts。

**DNR(cerebrum)**:rstest `findAllByText` 必须 await(bug-4143);worker summarize 键集变化会破前端 toEqual(本批 summary 键零变化);golden 面 docs_text 恒空(本批不动折叠面);buglog.json 顶层是 `{"bugs": [...]}`(controller 记账用)。

## 裁决表 A-β3(controller 锁定;实现者不得更改,偏离=申报)

| # | 裁决 |
|---|---|
| ① | **值域映射(唯一真相=engine/verdicts.py)**:`violation→FAIL`;`unclear→UNKNOWN`;det 缺字段/求值缺失降级(`rule_runner._need_human` 默认)→`UNKNOWN`;**基础设施/模型侧故障**(eval_core 逐规则隔离异常含 ModelNotConfigured、llm_runner 模型确认失败两试降级)→`ERROR`;`pass→PASS`(别名);`PASS/SKIP`=合法枚举值但引擎当下不产 issue 行(遥测/未来面留位);`false_positive`=复核域第六值,**verdict 列保留原样**(A8),全部 FP 过滤点零改动。 |
| ② | **CALIBRATION 冻结面**:golden 夹具零改动;`golden/loader.py` 加载期对 expected verdict 过 `normalize_verdict`(单向别名归一,新值恒等);golden CLI 73 题 0 失败=批次硬门。 |
| ③ | **DB 存量**:`database.py` 既有幂等先例块追加 UPDATE remap(`violation→FAIL`;`need_human/unclear→UNKNOWN`);`false_positive` 行不动;`need_human` 布尔列不动。 |
| ④ | **need_human 旗标口径全面不动**:summarize_issues/unknown_ratio/GateMetricsRow/nav.ts/待人工格全走旗标,零改动;旗标语义=「需人工处理」不变。 |
| ⑤ | **verify.py 内部重算协议不动**:det 重算 "violation"/"pass" 注入契约(evaluator 可注入,测试 fake 依赖)原样保留;仅 issue 写入点(280-282)改写 FAIL。 |
| ⑥ | **semantic_verdict(raw 四值 full/partial/none/unclear)与 state(state_map 分层)两列零改动**(P1-α b08932b68 已落);`VERDICT_TO_ISSUE` 键(raw 域)不动只改值。 |
| ⑦ | **前端域拆分**:FeedbackAction(含 need_human 动作)与 review_state 域零改动;仅 verdictPill 值域映射 + types.ts 注释;ResultsView/DiffView 审计确认除 false_positive 外无引擎值比较。 |

## 映射总表(实现者速查)

| 旧值 | 新值 | 语义 |
|---|---|---|
| `violation` | `FAIL` | 引擎确定性违规(det 判定失败/sem partial·none) |
| `pass` | `PASS` | 通过(别名兼容;issue 行当下不产) |
| `need_human` | `UNKNOWN` | 缺字段/材料无法判定(旗标 need_human=True 保持) |
| `unclear` | `UNKNOWN` | 模型判不清(旗标 need_human=True 保持) |
| (新) | `ERROR` | 基础设施/模型侧故障降级(逐规则隔离/确认失败;旗标 need_human=True 保持) |
| (新) | `SKIP` | 跳过(合法枚举,当下不产 issue 行) |
| `false_positive` | `false_positive` | **复核域,原样保留**,非引擎产出 |

---

### Task 1: 引擎五值域落地(verdicts.py + 四生产者 + golden 别名面)

**Files:**
- Create: `backend/app/extensions/bid_review/engine/verdicts.py`
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(:183,:200,:169 注释,:250 docstring)
- Modify: `backend/app/extensions/bid_review/engine/llm_runner.py`(:45-47,:137,:206,:50 注释,:201 docstring)
- Modify: `backend/app/extensions/bid_review/engine/eval_core.py`(:66,:84,:101,:107,:151)
- Modify: `backend/app/extensions/bid_review/engine/verify.py`(:280-282)
- Modify: `backend/app/extensions/bid_review/golden/loader.py`(:62)、`golden/schema.py`(:14)、`golden/runner.py`(:95,:99)
- Test: `backend/tests/test_bid_review_rule_runner.py`、`test_bid_review_llm_verify.py`、`test_bid_review_eval_core.py`、`test_bid_review_expr_operators2.py`、`test_bid_review_score_coverage.py`、`test_bid_review_r2_rule_families.py`、`test_bid_review_golden.py`、其余 grep 命中 engine 面断言的 test_bid_review_*.py

**禁区(整个批次有效)**:`.wolf/`、`docs/superpowers/specs/`、`golden/CALIBRATION.md`、golden 夹具四目录(cases/cases-l4/extract_cases/smoke)、五锁文件(test_bid_review_registry.py/test_bid_review_rule_runner.py 的 EXPECTED_V1_IDS+det 计数锁/test_bid_review_golden.py 的 EXPECTED_COVERAGE/test_bid_review_rule_families.py 的宇宙锁/test_bid_review_extract.py 形状测试——本批无规则变更,这些文件**不该有任何改动**;若测试断言旧 verdict 值,只改断言字符串,不动锁结构)。

- [ ] **Step 1: 创建 engine/verdicts.py(唯一真相)**

```python
# EAI-CUSTOM(P1-β批三 2026-11-07,C-08 值域三拆终章):verdict 引擎五值域。
# 引擎判定域 = FAIL|PASS|UNKNOWN|ERROR|SKIP;false_positive = 复核域值(A8),
# 仍落 verdict 列但非引擎产出;历史三值 violation/need_human/unclear 经
# normalize_verdict 单向归一(golden loader/DB remap/评测读面共用;先例 =
# C-05/C-22 MATCHED→PRESENT 别名归一,夹具与存量裁决记录零改动)。
VERDICT_FAIL = "FAIL"
VERDICT_PASS = "PASS"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_ERROR = "ERROR"
VERDICT_SKIP = "SKIP"
VERDICT_DOMAIN = (VERDICT_FAIL, VERDICT_PASS, VERDICT_UNKNOWN, VERDICT_ERROR, VERDICT_SKIP)

# 旧值→新值(单向;新值与复核域 false_positive 恒等透传;未知串原样返回=防御)
_VERDICT_ALIASES = {
    "violation": VERDICT_FAIL,
    "pass": VERDICT_PASS,
    "need_human": VERDICT_UNKNOWN,
    "unclear": VERDICT_UNKNOWN,
}


def normalize_verdict(v: str | None) -> str:
    """旧三值→引擎五值;新五值/false_positive/未知串恒等返回。"""
    s = str(v or "")
    return _VERDICT_ALIASES.get(s, s)
```

- [ ] **Step 2: 写 verdicts.py 单测(先失败)**

在 `backend/tests/test_bid_review_eval_core.py` 末尾追加(该文件已 import 引擎面,归属合适):

```python
# ── P1-β批三:verdict 五值域与别名归一(C-08 终章)───────────────────────────────


def test_normalize_verdict_aliases():
    from app.extensions.bid_review.engine.verdicts import (
        VERDICT_DOMAIN,
        normalize_verdict,
    )

    assert normalize_verdict("violation") == "FAIL"
    assert normalize_verdict("need_human") == "UNKNOWN"
    assert normalize_verdict("unclear") == "UNKNOWN"
    assert normalize_verdict("pass") == "PASS"
    for v in VERDICT_DOMAIN:  # 新值恒等
        assert normalize_verdict(v) == v
    assert normalize_verdict("false_positive") == "false_positive"  # 复核域透传
    assert normalize_verdict("") == ""  # 空/未知串防御性原样
    assert normalize_verdict(None) == ""
```

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_eval_core.py::test_normalize_verdict_aliases -v`
Expected: FAIL `ModuleNotFoundError: ... verdicts`(Step 1 已建文件则直接 PASS;若 Step 1 先行,本步作锚固)。

- [ ] **Step 3: rule_runner.py 生产者迁移**

3a. 文件头 import 区加:`from app.extensions.bid_review.engine.verdicts import VERDICT_FAIL, VERDICT_UNKNOWN`

3b. `_issue`(:183 附近)verdict 值替换:

```python
        "verdict": VERDICT_FAIL,
        "need_human": False,
```

3c. `_need_human`(:195 附近)**加 verdict 形参**(默认 UNKNOWN;eval_core 隔离面传 ERROR,见 Step 5):

```python
def _need_human(rule: Rule, msg: str, verdict: str = VERDICT_UNKNOWN) -> dict:
```

函数体内 `"verdict": "need_human",` → `"verdict": verdict,`(need_human 旗标 True 行不动)。

3d. 注释同步::169 附近「_need_human 非正式违规不带键」段与 :250 docstring「缺字段 → need_human,precondition 不成立 → [],判定失败 → violation」→「缺字段 → UNKNOWN,precondition 不成立 → [],判定失败 → FAIL(P1-β批三 五值域)」。

- [ ] **Step 4: llm_runner.py sem/hyb 面迁移**

4a. import 区加 `from app.extensions.bid_review.engine.verdicts import VERDICT_ERROR, VERDICT_FAIL, VERDICT_UNKNOWN`。

4b. :45-47(注意 :44 行注释「full=干净条款不产问题」保留):

```python
# 模型 verdict → 引擎 issue verdict(§4.6 语义映射;full=干净条款不产问题;P1-β批三 五值域)
VERDICT_TO_ISSUE = {"partial": VERDICT_FAIL, "none": VERDICT_FAIL, "unclear": VERDICT_UNKNOWN}
```

键(raw 四值域,C-08 裁决⑥)不动,只改值。

4c. :137 `"verdict": VERDICT_TO_ISSUE.get(verdict, "unclear"),` → `.get(verdict, VERDICT_UNKNOWN)`;:145 `"need_human": verdict == "unclear",` **不动**(旗标,raw 域判断)。

4d. `_degrade_candidate_to_need_human`(:198-213):docstring「verdict 翻为 need_human」→「verdict 翻为 ERROR(模型侧故障,五值域 P1-β批三)」;`"verdict": "need_human",` → `"verdict": VERDICT_ERROR,`(need_human: True / numeric_expr None / dedup_key 全不动)。

4e. :50 注释「verdict 值域迁 PASS/FAIL/... = P1-β 挂账(破 CALIBRATION 冻结面)」→「verdict 值域五值迁已兑付(P1-β批三;CALIBRATION 冻结面经 loader normalize_verdict 别名保住,夹具零改动)」。

- [ ] **Step 5: eval_core.py 折叠/隔离面迁移**

import 区加 `from app.extensions.bid_review.engine.verdicts import VERDICT_ERROR, VERDICT_FAIL`。

5 处值替换(上下文照旧,只换字符串):

- :66 `i.get("verdict") == "violation"` → `== VERDICT_FAIL`(L2-021 抑制)
- :84 同上(L3-012 抑制)
- :101 `_fold_issues_by_primary` primary 判定 `== "violation"` → `== VERDICT_FAIL`
- :107 folded 判定同上
- :147-151 逐规则隔离 except 块:

```python
        except Exception as exc:  # noqa: BLE001
            # 求值意外与模型侧故障(含 ModelNotConfigured)在此统一降级 ERROR
            # (引擎五值域:基础设施故障≠数据不可判;缺字段类 UNKNOWN 走
            # rule_runner._need_human 默认,P1-β批三),不外溢单规则异常。
            issues = [_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 ERROR)", verdict=VERDICT_ERROR)]
```

(`_need_human` 已在 eval_core import 面中——确认 import 行含之,若只 import 了别的名字则补。)

- [ ] **Step 6: verify.py 写入点迁移(协议不动)**

:280-282:

```python
    if det == "violation" and issue.get("verdict") != VERDICT_FAIL:
        # 引擎五值域(P1-β批三):重算坐实违规 → 翻 FAIL;内部重算协议
        # ("violation"/"pass" 注入契约)本身不动(裁决⑤)。
        issue["verdict"] = VERDICT_FAIL
```

import 区加 `VERDICT_FAIL`。:168/184 docstring 内「"violation"/"pass"」协议描述**保留**(内部协议未变)。

- [ ] **Step 7: golden 别名面(夹具零改动)**

7a. `golden/loader.py` import 区加 `from app.extensions.bid_review.engine.verdicts import normalize_verdict`;:62:

```python
            verdict=normalize_verdict(str(e.get("verdict") or "violation")),
```

(默认值仍 "violation",经归一即 FAIL——单点归一覆盖 cases/cases-l4/extract_cases 全部加载面。)

7b. `golden/schema.py` :14 注释更新(默认值不动):

```python
    verdict: str = "violation"  # 引擎五值 FAIL|PASS|UNKNOWN|ERROR|SKIP(批三);历史三值由 loader normalize_verdict 归一,夹具零改动(CALIBRATION 冻结面)
```

7c. `golden/runner.py` :95 与 :99 的 `i.get("verdict") == "violation"` / `!= "violation"` → `== "FAIL"` / `!= "FAIL"`(比较的是**产出** issue,批三后已出新值;直接写常量字符串即可,或 import VERDICT_FAIL,二选一,文件内一致)。:95/:99 附近 expect_absent/严格匹配注释若提「violation」措辞同步。

- [ ] **Step 8: 引擎面测试清扫(机械映射,禁区甄别)**

对 Step Files 的 Test 列表逐文件:先 `grep -n '"violation"\|'"'"'violation'"'"'\|need_human\|unclear' <file>` 盘点,再按映射总表替换 **issue-verdict 断言/构造**:

- `verdict == "violation"` / `"verdict": "violation"` / `verdict="violation"` → FAIL
- `"verdict": "need_human"` / `verdict="need_human"`(issue 构造/crud 调用)→ UNKNOWN
- `"verdict": "unclear"` → UNKNOWN

**不碰**(甄别清单,机械替换前逐处过目):
1. `test_bid_review_llm_verify.py` 中 **evaluator fake 的返回串** `"violation"`/`"pass"`(verify 内部协议注入契约,裁决⑤);
2. FeedbackAction 域 `"need_human"`/`"false_positive"`(feedback/routers 类测试,routers 面在 Task 2 才迁——**本 Task 不改 feedback/routers/worker 测试**,它们 interim 红,Task 2 收);
3. `semantic_verdict` 的 raw 四值(full/partial/none/unclear)——零改动;
4. severity/review_state 值。

- [ ] **Step 9: 跑引擎+golden 面测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_eval_core.py tests/test_bid_review_rule_runner.py tests/test_bid_review_llm_verify.py tests/test_bid_review_golden.py tests/test_bid_review_expr_operators2.py tests/test_bid_review_score_coverage.py tests/test_bid_review_r2_rule_families.py -v`
Expected: 全 PASS(routers/worker/feedback/metrics/diff/grouping/l4_activation/mcp/crud/schemas/c11 等**服务端消费面测试 interim 红,Task 2 收复——申报即可,不算失败**)。

- [ ] **Step 10: golden CLI 硬门 + 夹具零 diff 验证**

Run: `cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden`
Expected: `题数 73 | 失败 0`。
Run: `git status --short -- backend/app/extensions/bid_review/golden/cases backend/app/extensions/bid_review/golden/cases-l4 backend/app/extensions/bid_review/golden/extract_cases backend/app/extensions/bid_review/golden/smoke backend/app/extensions/bid_review/golden/CALIBRATION.md`
Expected: **空输出**(冻结面零 diff;CALIBRATION.md 不许动)。

- [ ] **Step 11: Commit**

```bash
git add backend/app/extensions/bid_review/engine/verdicts.py backend/app/extensions/bid_review/engine/rule_runner.py backend/app/extensions/bid_review/engine/llm_runner.py backend/app/extensions/bid_review/engine/eval_core.py backend/app/extensions/bid_review/engine/verify.py backend/app/extensions/bid_review/golden/loader.py backend/app/extensions/bid_review/golden/schema.py backend/app/extensions/bid_review/golden/runner.py backend/tests/
git commit -m "feat(bid-review): 批三T1——verdict五值域落地:engine/verdicts.py唯一真相(FAIL/PASS/UNKNOWN/ERROR/SKIP+normalize_verdict别名);四生产者直产新值(det FAIL/缺字段UNKNOWN/模型确认失败与逐规则隔离ERROR);eval_core折叠/抑制五点+verify写入点(内部协议不动裁决⑤);golden loader加载期归一保CALIBRATION冻结面(夹具零改动裁决②,C-08值域三拆终章,A-β3-①)"
```

(只 add 本批文件;git status 里**其他会话的未提交改动一律排除**。)

---

### Task 2: 服务端消费面(DB 幂等 remap + routers 回写点 + 注释)

**Files:**
- Modify: `backend/app/extensions/database.py`(幂等先例块,~:231-248 区段)
- Modify: `backend/app/extensions/bid_review/models.py`(:69 注释)
- Modify: `backend/app/extensions/bid_review/schemas.py`(:58 注释)
- Modify: `backend/app/extensions/bid_review/routers.py`(:453,:537,:593,:939,:940 + 既有注释措辞 :162/:394/:590/:709)
- Test: `test_bid_review_routers.py`、`test_bid_review_feedback.py`、`test_bid_review_worker.py`、`test_bid_review_worker_sem.py`、`test_bid_review_crud.py`、`test_bid_review_metrics.py`、`test_bid_review_diff.py`、`test_bid_review_grouping.py`、`test_bid_review_l4_activation.py`、`test_bid_review_mcp.py`、`test_bid_review_schemas.py`、`test_bid_review_c11_severity.py`

**前置确认**:models.py ReviewIssue 的 `__tablename__`(预期 `review_issues`——grep 确认,若不同以实际为准)。mcp.py 只做字段透传(:262/:294),grep 确认无 verdict 比较→**零改动**。worker.py :569 透传→零改动。

- [ ] **Step 1: database.py 幂等 remap(裁决③)**

在既有幂等 ALTER 先例块(`await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone ..."))` 等之后、同函数内)追加:

```python
        # C-08 verdict 值域迁(P1-β批三 2026-11-07,幂等 UPDATE,先例同上块):
        # 历史三值→引擎五值;false_positive 复核域行不动(A8);need_human 布尔列不动。
        await conn.execute(text("UPDATE review_issues SET verdict='FAIL' WHERE verdict='violation'"))
        await conn.execute(text("UPDATE review_issues SET verdict='UNKNOWN' WHERE verdict IN ('need_human','unclear')"))
```

(表名以前置确认结果为准。)

- [ ] **Step 2: models/schemas 注释**

models.py :69 整行注释替换:

```python
    verdict: Mapped[str] = mapped_column(String(20))  # 引擎五值 FAIL|PASS|UNKNOWN|ERROR|SKIP(P1-β批三 C-08 迁毕);false_positive=复核域回写值(A8)仍落本列;存量历史三值经 database.py 幂等 UPDATE remap
```

schemas.py :58 `verdict: str  # emission-only(A8)` → `verdict: str  # emission-only(A8);值域=引擎五值+复核域 false_positive(P1-β批三)`

- [ ] **Step 3: routers.py 迁移(FP 点零触碰)**

5 处引擎值替换:

- :453 `getattr(i, "verdict", "") != "violation"` → `!= "FAIL"`(分组归并)
- :537 `issue.verdict = "need_human"` → `issue.verdict = "UNKNOWN"` 并把该行尾注释改为 `# 反馈转待人工:UNKNOWN+旗标(引擎五值域;不计规则包统计口径不变)`
- :593 `i.verdict == "violation"` → `== "FAIL"`(_fatal_hits;该行其余 fatal/need_human/layer 条件不动)
- :939 `i.verdict == "violation"` → `== "FAIL"`
- :940 `i.verdict == "unclear"` → `== "UNKNOWN"`

**零触碰**::172/:174/:398/:622/:714/:830 全部 `false_positive` 比较;:524 action 白名单;:421-427 review_state 派生注释(本就写明 verdict 不参与)。:162/:394/:590/:709 注释里「verdict=violation」措辞同步为 FAIL(纯注释,语义不变)。

- [ ] **Step 4: 服务端测试清扫**

对 Test 列表逐文件 grep 盘点后按映射总表替换 issue-verdict 断言(禁区同 Task 1 Step 8 清单——evaluator fake 串、FeedbackAction 串、semantic_verdict raw 值、severity/review_state)。**特别注意** `test_bid_review_feedback.py`:action="need_human" 的**请求体**字符串不动;断言落库 `verdict` 的地方由 `"need_human"` → `"UNKNOWN"`(:537 已改)。

- [ ] **Step 5: 跑服务端面测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_routers.py tests/test_bid_review_feedback.py tests/test_bid_review_worker.py tests/test_bid_review_worker_sem.py tests/test_bid_review_crud.py tests/test_bid_review_metrics.py tests/test_bid_review_diff.py tests/test_bid_review_grouping.py tests/test_bid_review_l4_activation.py tests/test_bid_review_mcp.py tests/test_bid_review_schemas.py tests/test_bid_review_c11_severity.py -v`
Expected: 全 PASS(feedback 文件若因共享 DB flaky,单独重跑判定)。

- [ ] **Step 6: DB remap 冒烟(容器内验证幂等)**

Run: `docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT verdict, count(*) FROM review_issues GROUP BY verdict ORDER BY 1"`
Expected: 输出中无 `violation/need_human/unclear` 行(若有旧值,说明该库未跑新启动路径——测试库走 SQLite/内存面时本步只验 dev PG;把现状如实申报,不阻塞)。

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/database.py backend/app/extensions/bid_review/models.py backend/app/extensions/bid_review/schemas.py backend/app/extensions/bid_review/routers.py backend/tests/
git commit -m "feat(bid-review): 批三T2——服务端消费面迁移:database.py幂等UPDATE remap(历史三值→FAIL/UNKNOWN,false_positive行不动,裁决③);routers五点引擎值(分组FAIL/反馈转待人工UNKNOWN/_fatal_hits FAIL/规则归并FAIL+UNKNOWN)+FP过滤点零触碰(A8复核域);models/schemas值域注释;need_human旗标口径全面不动(裁决④)"
```

---

### Task 3: 前端判定码

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/primitives.tsx`(:88-101 verdictPill)
- Modify: `frontend/src/extensions/bid-review/types.ts`(:50 注释)
- Audit(预期零改动,grep 确认):`components/ResultsView.tsx`、`components/DiffView.tsx`、`api.ts`、`hooks.ts`、`nav.ts`
- Test: `frontend/tests/unit/extensions/bid-review/`(grep 命中 pill label/verdict 断言的文件)

- [ ] **Step 1: verdictPill 值域映射(裁决⑦)**

primitives.tsx switch 整体替换(既有 tone/label 语义逐 case 保留映射):

```tsx
  switch (verdict) {
    case "FAIL":
      return { tone: "error", label: "违规" };
    case "PASS":
      return { tone: "success", label: "通过" };
    case "UNKNOWN":
      return { tone: "gray", label: "待人工" };
    case "ERROR":
      return { tone: "error", label: "执行异常" };
    case "SKIP":
      return { tone: "gray", label: "跳过" };
    case "false_positive":
      return { tone: "gray", label: "误报" };
    default:
      return { tone: "gray", label: verdict || "未知" };
  }
```

:21 注释同步(「verdict violation→error / pass→success / need_human→muted」→「verdict FAIL→error / PASS→success / UNKNOWN·SKIP·false_positive→gray / ERROR→error」)。

- [ ] **Step 2: types.ts 注释**

:50 `verdict: string;` 上方加 doc 注释:

```ts
  /** 引擎五值 FAIL|PASS|UNKNOWN|ERROR|SKIP(后端 P1-β批三 C-08)+ 复核域 false_positive。 */
  verdict: string;
```

- [ ] **Step 3: 消费面审计(grep 出证)**

Run: `grep -rn 'verdict ===\|verdict !==\|verdict ==' frontend/src/extensions/bid-review/`
Expected 命中且**全部保留不动**:ResultsView `!== "false_positive"`(:261)/`=== "false_positive"`(:470);其余命中若是引擎值比较则按映射改并申报。DiffView(:25)present-based 审计确认。FeedbackAction(`api.ts` :57 `"need_human"`)不动。

- [ ] **Step 4: rstest 清扫 + 跑测**

grep `frontend/tests/unit/extensions/bid-review/` 中 `"violation"/"need_human"/"unclear"` 断言(区分 FeedbackAction 串),机械替换;`findAllByText` 一律 await(DNR bug-4143)。
Run: `cd frontend && pnpm test -- tests/unit/extensions/bid-review`
Expected: 全 PASS(既有 2 timeouts flaky 单独判定)。

- [ ] **Step 5: lint/typecheck(零新增红线门)**

Run: `cd frontend && pnpm lint && pnpm typecheck`
Expected: 允许 HEAD 既有红线(批二续已证 6 处 ResultsView eslint 在旧 hunks);**本批触碰文件零新增**。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/bid-review/components/primitives.tsx frontend/src/extensions/bid-review/types.ts frontend/tests/unit/extensions/bid-review/
git commit -m "feat(bid-review): 批三T3——前端判定码:verdictPill五值域映射(FAIL违规/PASS通过/UNKNOWN待人工/ERROR执行异常/SKIP跳过/false_positive误报)+types值域注释;FeedbackAction与review_state域零改动(裁决⑦);ResultsView/DiffView审计FP域零触碰"
```

---

### Task 4: 台账对账 + 全量验收

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`(:82 C-08 行 + :108 批次段)

- [ ] **Step 1: 全量验收四门(controller 会复核;实现者先跑)**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q   # 预期 679+/6 skipped/0 failed(新增 normalizer 测试 +1)
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden   # 预期 题数 73 | 失败 0
cd backend && PYTHONPATH=. uv run python -c "from app.extensions.bid_review.engine.registry import universe; print('universe', len(universe()))"   # 预期 universe 92
git status --short -- backend/app/extensions/bid_review/golden/cases backend/app/extensions/bid_review/golden/cases-l4 backend/app/extensions/bid_review/golden/extract_cases backend/app/extensions/bid_review/golden/smoke backend/app/extensions/bid_review/golden/CALIBRATION.md   # 预期 空
```

- [ ] **Step 2: spec 对账两处**

:82 C-08 行处置列追加:「;verdict 值域五值迁已兑付(2026-11-07 P1-β批三:T1 <hash> 引擎+golden别名面/T2 <hash> DB remap+消费面/T3 <hash> 前端;夹具零改动,73/0 保持)」(hash 由 T1-T3 commit 实际值填)。:108 批次段「批三=verdict 值域五值迁(NEXT)」后追加批三兑付句(同格式:数字不变注记——包 50/det 44/宇宙 92/golden 73 题全保持;挂账:PASS/SKIP 引擎 issue 行遥测面留位、ERROR 仅基础设施降级路径产出)。

- [ ] **Step 3: Commit**

```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): 批三T4——台账对账:C-08值域迁兑付注记+批三收官段(包50/宇宙92/golden73全数字不变;挂账PASS/SKIP遥测留位)"
```

---

## Self-Review 记录(controller 已跑)

1. **Spec 覆盖**:C-08 值域迁=Task 1(引擎+golden)+Task 2(DB/消费面)+Task 3(前端)+Task 4(台账);裁决①..⑦ 全落任务。无缺口。
2. **占位符扫描**:无 TBD/TODO;全部代码块完整;行号引用为批二续收官态(9433ec536)实测。
3. **类型一致性**:`normalize_verdict(v: str | None) -> str` 单一签名;`_need_human(rule, msg, verdict=VERDICT_UNKNOWN)` 仅 eval_core:151 传参;golden loader 与 DB remap 共用别名表。前端仅 verdictPill switch。一致。

## 里程碑语义(验收口径)

- **T1 后**:引擎/golden 面全绿 + golden CLI 73/0;服务端消费面测试 interim 红(已申报清单)。
- **T2 后**:family 全绿(除已知 flaky)。
- **T3 后**:前端 bid-review rstest 全绿;lint/typecheck 零新增。
- **T4 后**:四门全过 + 台账收官;controller 做 .wolf 记账(cerebrum/anatomy/buglog/memory——实现者禁触)。
