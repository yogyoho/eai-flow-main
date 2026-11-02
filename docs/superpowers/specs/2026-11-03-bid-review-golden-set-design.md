# bid-review 金标准评测集（golden set）设计 spec

日期：2026-11-03　分支：main-dev-fork
前置：L2-P1（附件清单核对）与 L2-P2（子件分组+跨层去重）已落地（`f165fdbe9..48afd2e95`）。

## 0. 范围

**做**：字段层声明式题库（34 条规则每条 ≥1 题 + L2 专项 strict 题 + 定向误报抑制题）、全管线冒烟 1-2 题（stub extract，钉接线不钉 LLM）、独立评测核（与生产同一分派逻辑）、pytest 回归门、CLI 成绩单（markdown+JSON）、半自动建库校准流程与记录。

**不做**（挂账）：gates 阈值红线（先观测拿基线，属后继阶段）｜规则效果页前端展示成绩单｜复核回流自动转正管道（先手工：feedback 导出→手工出题）｜真题录制/灌入工具｜字段级置信门禁｜真 LLM 冒烟进 CI（提供手工命令）。

## 1. 用户决策记录

| 决策点 | 定版 |
|---|---|
| 切入点 | 字段层为主 + 全管线冒烟（冒烟用 stub extract_fn 钉管线接线；LLM 抽取质量靠线上 metrics/复核回流观测，不进 CI 门） |
| 覆盖面 | 全 34 条规则每条 ≥1 题；L2 两条另加专项题（四态/子件分组/跨层去重/UNKNOWN→need_human） |
| 门槛形态 | pytest 回归门（不符即红）+ CLI 成绩单（信息型）；阈值红线后置 |
| 架构 | 声明式题库 + 独立评测器 + 双出口；复核回流作为灌题渠道二（手工） |

## 2. 现状工程事实（设计依据）

- 引擎已两层分离：文档 → `build_baseline(docs, extract_fn)`（LLM 抽取，可缺配 `ExtractNotConfigured`）→ `tender.*/bid.*` 字段 dict → 规则判定 → issues。
- 规则判定纯核已存在：`rule_runner.run_det_rule(rule, fields) -> list[dict]`（deterministic 纯函数）、`attach_evidence(issues, rule, provenance)`（provenance 可空）。
- 分派循环在 `worker._run_review_stage`：`det_fields = {k:v for k,v in fields.items() if v is not None}` → 逐 enabled 规则：`deterministic→attach_evidence(run_det_rule(...))`；`semantic|hybrid→run_sem_rule(rule, det_fields, materials, model_fn, docs_text)`；逐规则异常隔离→`_need_human(rule, "规则执行异常…")` 降级。循环体与 DB 写耦合。
- sem 规则可确定性评测：注入 scripted `model_fn`（按题给定模型应答），钉的是规则逻辑而非模型。
- rulepack：`engine/rulepacks/bid-review-core/1.0.0.yaml`，34 条（L1×20 + L2×2 + L3×16），rulepack 校验测试锁数量。
- 复核回流在线：`POST /issues/{id}/feedback`（confirm/false_positive/severity_change/need_human → ReviewFeedback + metrics 归因）。
- 既有测试：`backend/tests/test_bid_review_*.py` 23 个文件 258 用例。

## 3. 目录布局（全新独立模块）

```
backend/app/extensions/bid_review/golden/
├── __init__.py
├── __main__.py       # python -m app.extensions.bid_review.golden → CLI 成绩单
├── schema.py         # GoldenCase / Expectation / CaseResult / Report 契约
├── loader.py         # cases/*.yaml + smoke/*/case.yaml → GoldenCase（含校验）
├── runner.py         # run_case / run_all —— 共享分派核调用方
├── report.py         # Report → markdown + JSON
├── cases/            # 字段层题库（每题一个 YAML，按 {rule_id}-{slug}.yaml 命名）
├── smoke/            # 冒烟题：case.yaml + docs/{tender,bid}.md + extract_stub.yaml
└── CALIBRATION.md    # 建库校准记录（每处 diff 裁决：改标注 / 修 bug + buglog 编号）
tests/test_bid_review_golden.py    # pytest 回归门 + runner 自身单测
```

## 4. 共享分派核（唯一动现有代码的点）

从 `worker._run_review_stage` 提取纯函数：

```python
# app/extensions/bid_review/engine/eval_core.py（新文件）
def evaluate_fields(pack: RulePack, fields: dict, *,
                    model_fn=None, provenance: dict | None = None,
                    docs_text: str = "") -> list[dict]:
    """与 worker._run_review_stage 同一分派逻辑（det/sem 分派、det_fields 非空过滤、
    逐规则异常隔离→_need_human），无 DB、无状态。worker 循环改为消费本函数的
    issue dict 流，DB 写留在 worker。"""
```

- worker 改为调用 `evaluate_fields` 后逐条 `crud.add_issue`（行为不变，进度上报循环留在 worker）。
- 既有 258 个 bid_review 测试全程护住该重构；金标准尺子量的必须是生产同一段代码，禁止 runner 复制一份分派循环（复制=两把尺子，必然漂移说谎）。

## 5. 题目契约（case YAML schema）

```yaml
case: L2-020-missing-attachment        # {rule_id}-{slug}，与文件名一致
desc: 投标缺 E-2 中标通知书 → L2-020 fatal 附件缺失
fields:                                # tender.*/bid.* 夹具
  tender.attachment_requirements:
    - {no: E-1, name: 业绩合同, min_count: 1}
    - {no: E-2, name: 中标通知书, min_count: 1}
  bid.attachment_index:
    - {no: E-1, name: 业绩合同, pages: [12, 18]}
expect_issues:                         # 应报：rule_id + severity + message 关键词
  - rule_id: L2-020
    severity: fatal
    contains: ["E-2", "中标通知书"]
expect_absent: [L1-005]                # 定向误报抑制：点名规则不得报
strict: false                          # 断言模式，见 §6
checklist:                             # 可选：L2 题附加核对表投影期望
  unknown_count: 0
```

- `fields` 校验：loader 校验顶层键 ⊆ rulepack 全部规则 `inputs` 并集 ∪ 投影端点已知路径（attachment_checklist / score_coverage / deviations 消费的字段）——拼错字段路径→加载报错，防"夹具拼错→规则零输入→永不触发"的假题。
- sem/hybrid 规则的题可带 `model_script:`（映射 `{<rule_id>: <应答JSON>}`，评测核按 rule_id 取用，构成确定性 scripted model_fn）；含 sem/hybrid 题而缺 script → loader 报错。
- message 断言用 `contains` 关键词而非全文等值（message_tpl 措辞允许演进；rule_id+severity+关键词已足够钉住语义）。

## 6. 断言模式（已批准的取舍）

- **默认 `strict: false`（宽松定向）**：断言 ①expect_issues 逐条命中（rule_id+severity+contains 全对才算命中）②expect_absent 零报。期望外 issue 忽略——一题字段喂全部 34 条规则，严格模式要求把顺带触发的问题全部标注，标注成本 ×34 题。
- **`strict: true`（L2 专项题用）**：任何期望外 issue 都算 diff。L2 题字段面小完全可控，配得起严格模式；L2 是去重/分组/四态机制的主战场，严格才有牙。
- 判定顺序：先按 rule_id 匹配 expect_issues（多对多：同 rule_id 多条 issue 时按 severity+contains 逐一消化），再查 expect_absent，最后 strict 模式数余量。

## 7. 评测核调用与双出口

- `runner.run_case(case, pack, model_fn=None)` → 组装 det_fields → `evaluate_fields` → checklist 投影（有 checklist 期望时调 `attachments.build_checklist` 同源函数）→ diff → `CaseResult`（结构化：missing[] / unexpected[] / severity_mismatch[] / contains_miss[] / checklist_diff）。
- **pytest 门**（`tests/test_bid_review_golden.py`）：`@pytest.mark.parametrize` 逐题断言 `CaseResult.diff == 空`；失败信息渲染结构化 diff。改规则/算子/rulepack 后跑金标准即回归。
- **CLI 成绩单**：`python -m app.extensions.bid_review.golden --report md [--out report.json]`。输出：每规则 TP/FP/FN/state 命中率 → 按层（L1/L2/L3）与严重度汇总 → 逐题 PASS/FAIL 明细（FAIL 带同款结构化 diff）。信息型，不进 CI 强制。

## 8. 全管线冒烟题

- 1-2 题：`smoke/smoke-1-basic/{case.yaml, docs/tender.md, docs/bid.md, extract_stub.yaml}`。文档夹具为小型 markdown（含全部关键章节词），`extract_stub.yaml` = 字段→值固定映射充当 `extract_fn`。
- 链路：读 docs → `build_baseline(docs, extract_fn=stub)` → fields → `evaluate_fields` → 同一断言。
- CI 门钉的是**管线接线**（分片→prompt 组装→normalize→fields→规则）。真 LLM 冒烟提供手工命令（`--live`，本地自担 token），不进 CI。

## 9. 建库校准流程（半自动，金标准的灵魂）

1. 落 schema + loader + runner + 1 道样例题，跑通双出口。
2. 逐规则起草题目：按该规则 `inputs` 构造最小触发字段 → 跑引擎 → 用现输出**起草** expected → 人工裁决每处 diff：引擎对→修标注；标注对→记 bug 修引擎（buglog 记录，CALIBRATION.md 记裁决结论）。
3. 全部入库后整库跑批必须全绿（=每题「引擎输出=标注」逐题成立）；此后任何 diff 即回归。
4. L2 专项题按 §6 strict 模式校准；误报抑制题（expect_absent）从现有已知误报场景反推。

## 10. 验收标准

- 34 条规则每条 ≥1 题入库且 pytest 绿；题库清单与 rulepack 34 条一一可对账（loader 提供覆盖率断言：任何 rule_id 无题→回归门红，防"新加规则没题"静默漏测）。
- L2 专项题 strict 全绿：L2-020/L2-024 × 四态、子件分组（含 UNKNOWN 降 need_human）、跨层去重 keep most_severe。
- 冒烟题绿；CLI 成绩单正确生成且数字与 pytest 结果一致。
- worker 重构后既有 258 测试全绿（行为不变证明）。
- runner diff 逻辑自身单测绿。

## 11. 错误处理

- loader：schema 不合法/字段路径越界/sem 题缺 model_script → 加载期报错（fail-fast，不带病进跑批）。
- runner：单题异常隔离——一道题的引擎异常按 worker 同款语义降级 `_need_human` 计入 diff（标注若期望正常报出则该题红），runner 自身不吞异常。
- CLI：题库加载失败/部分题失败 → exit code 非 0，成绩单仍完整输出（失败明细在内）。
