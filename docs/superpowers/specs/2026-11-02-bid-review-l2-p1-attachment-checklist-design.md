# bid-review L2 完整性层 P1：附件清单核对 设计 spec

日期：2026-11-02 ｜ 状态：待用户评审
素材：用户提供的 L2 设计（五类粒度/四态判定/附件清单核对表/26 条规则）＋ 全量 YAML 规则包
前置对账：L1/L3 canonical 规则包已存在（bid-review-core v1.0.0，32 条）；本 spec 只落 **P1**。

## 0. 范围（P1 先行，用户已批）

**做**：要求集抽取（进基准确认卡点）＋ 编号/规范化名称两级精确匹配 ＋ 份数计数 ＋ 2 条 det 规则（L2-020/L2-024）＋ 附件核对表投影端点与 UI。
**不做**（后续阶段）：类型指纹/语义兜底匹配（P3，semantic_confirm→待人工）、复合附件子件分组（P2）、跨层实体去重 L1>L2>L3（P2）、年份连续性判定（抽取捕获 `year_span` 但 P1 不判）、zip 解包、4 套项目类型 checklist 模板（P3，定位 `internal_template` 来源 minor 档）、L2 其余 24 条规则。

四态映射（对齐既有契约）：`PRESENT`→零渲染；`MISSING`/`PARTIAL`→issue（det）；`UNKNOWN`→`on_missing_input: need_human` 既有约定兜底；`EXTRA`→核对表 info 行提示，**不产 issue 不进问题数**。

## 1. 字段契约新增（三方同步：rulepack inputs / FIELD_DICTIONARY / 金标准 schema 注记）

```python
# extract.py FIELD_DICTIONARY += 
"tender.attachment_requirements"   # 招标侧要求集
"bid.attachment_index"             # 投标侧提供集
```

类型契约（FIELD_TYPE_CONTRACTS，同 deviation.items「原文只抄不编」口径）：

- `tender.attachment_requirements`：
  `[{no:"附件编号或空串", name:"附件名称", clause:"要求出处条款号", mandatory:"★|必需|建议", min_count:最少份数数字或null, year_span:年份数字或null}]`；
  只从招标「投标文件格式/组成」及资格审查条款逐条抄录，禁止编造；无编号填空串。
- `bid.attachment_index`：
  `[{no:"附件编号或空串", name:"附件名称", page:起始页码数字, pages:页数数字或null}]`；
  从投标文件附件清单/目录/附件标题逐条抄录，禁止编造。

## 2. 匹配器 `engine/attachments.py`（纯函数，pytest 全覆盖）

```
normalize_name(s)    # 全半角归一/去空白/剥「附件N」「附件N-M」序号前缀/去尾冒号
match_attachments(requirements, provided) ->
  per_req:   [{req, matched:[item...], found:n, status: MATCHED|PARTIAL|MISSING}]
  extra:     [item...]                      # 未被任何 req 匹配的提供项
匹配优先级：① no 精确（双方非空）② normalize_name 等值
```

- 状态：`found==0`→MISSING；`min_count` 且 `found<min_count`→PARTIAL；否则 MATCHED。P1 无子件核对，无 UNKNOWN 行（字段整体缺失→need_human 兜底）。
- 贪心一对一：一个提供项只归属一个 req（先编号后名称，防止「报价表」吞掉「分项报价表」——名称匹配要求归一后**全等**，非包含）。

## 3. 规则包 v1.1.0（+2 条 canonical，32→34）

```yaml
- id: L2-020
  name: 附件清单逐项对照
  layer: L2
  type: deterministic
  inputs: [tender.attachment_requirements, bid.attachment_index]
  check: {op: att_check}          # 新 op，镜像 set_eq 在 rule_runner 的专用分支先例
  severity: fatal
  evidence: [A-TENDER-NOTICE, A-BOQ]   # 占位；落地时挂附件要求出处锚
  message_tpl: "附件缺失：{missing}"
  fix_tpl: "补齐缺失附件并在附件清单中按编号顺序编排：{missing}"
- id: L2-024
  name: 附件份数达标
  layer: L2
  type: deterministic
  inputs: [tender.attachment_requirements, bid.attachment_index]
  check: {op: att_count}
  severity: major
  message_tpl: "附件份数不足：{insufficient}"
```

- `att_check`/`att_count` 分支（rule_runner，复用 `attachments.match_attachments`）：`att_check` 产 `{missing:[no+name]}`（只列 MISSING req）；`att_count` 产 `{insufficient:[no+name: required/found]}`（只列 PARTIAL req）。字段缺失 → 既有 `on_missing_input: need_human`。
- dedup 走既有 conventions 模板（`{rule_id}|{clause_id}|{evidence_keys}`），P1 不引入 `L2|ATT|<no>` 实体键。

## 4. 投影端点 `GET /tasks/{id}/attachment_checklist`

响应（先例 = /deviations /score_coverage 投影，从基线字段现算，不落库）：

```json
{"counts": {"required": 18, "matched": 15, "partial": 1, "missing": 2, "extra": 1},
 "items": [{"no": "ATT-E-008", "name": "类似业绩证明", "mandatory": "★",
            "min_count": 3, "found": 2, "status": "PARTIAL",
            "refs": [{"doc_id": "bid.pdf", "page": 118}], "clause": "第三章3.4"}],
 "extra_items": [{"name": "企业宣传册", "doc_id": "bid.pdf", "page": 310}]}
```

零投影（旧任务无 `tender.attachment_requirements` 字段）→ counts 全 0 + items `[]`，前端诚实空态「本任务抽取时未包含附件要求维度」（先例 = deviations）。

## 5. UI

1. **BaselineView**：tender 侧新增「附件要求」卡（no/名称/强制/份数 mini-table），裁决复用既有 adjudicate 通道（改错要求→409 前拦住，同字段卡）。bid 侧「附件清单」只读卡。
2. **ResultsView**：新卡「附件核对表」——五格 counts strip（EXTRA 灰档）＋ 明细表（序号/要求附件/强制/份数/提供情况页码 chip/状态 pill/缺项说明）＋ EXTRA 追加行（info 灰 pill，注「多余附件不判错」）＋ tbl-foot 口径注。状态 pill：MATCHED→pill-ok，PARTIAL→pill-warn，MISSING→pill-err。页码 chip 复用 DocLocate（role=bid 首文档）。
3. 侧栏/导航**不加**新页（P1 归宿在既有两页，核对表不是独立工作流）。

## 6. 测试（TDD 先红后绿）

- 后端：matcher 单测（归一/编号/名称全等防吞/一对一贪心/EXTRA/min_count PARTIAL）；`att_check`/`att_count` rule_runner 分支；checklist 端点投影＋零投影；字段缺失 need_human；rulepack 校验测试更新（34 条/L2 层出现）。
- 前端：BaselineView 附件要求卡 dom 测试；ResultsView 核对表卡 dom 测试（五格/pill 映射/EXTRA 行/零投影空态/页码 chip）。

## 7. 风险与非目标备注

- 抽取质量是 P1 唯一真风险：附件清单页在扫描件里 OCR 噪声大 → 基准确认卡点是兜底（人工校对后 requirement 才可信）。
- `covers(x,y)`=子串包含，语义不符，**不复用**；匹配器独立实现。
- P2/P3 挂账：子件分组（分组失败降 UNKNOWN，禁强行 PARTIAL）、类型指纹 sem 规则（semantic_confirm 强制人工）、跨层去重 keep most_severe+related_issues、4 套模板（internal_template minor 档）、gates 门禁（依赖金标准集，先在规则效果页观测）。
