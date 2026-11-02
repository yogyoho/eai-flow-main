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

## 批A(L1×17 + A族×3)裁决表

rulepack 实有 L1=17 条(计划表估 20 与文件不符,以文件为准;L1-004/017/018/020 不存在)。
L1-009 复用既有 L1-009-over-max-price.yaml,未新建。除下表「标注对」两行外,
各题均为「引擎对」:期望按引擎现输出起草,逐处 diff 后与 rulepack 触发语义逐字核对一致。

| case | 裁决 | 结论/bug编号 |
|---|---|---|
| L1-001-license-scope | 引擎对 | 执照有效期 "2026-01-01" < 截止 "2026-06-30"(ISO 串词法比较,日期值一律 YAML 加引号防 PyYAML 转 date);covers 子串包含达标,单因触发 |
| L1-002-qual-level-low | 引擎对 | covers 串包含判定(无序数比较器,v2);消息含要求等级与投标列表原文 |
| L1-003-performance-short | 引擎对 | hyb 粗筛 count<min 产候选 → scripted partial → violation(major=rulepack);message 占位符剥离为 _render_message 既定行为,尾缀 "(clause_id: reason)" 上下文摘要入 contains 钉 |
| L1-005-validity-short | 引擎对 | 60<90 gte 违例,消息含两值 |
| L1-006-deposit-mismatch | 引擎对 | eq 违例;:money 渲染 ¥50,000.00/¥100,000.00 入 contains 钉语义 |
| L1-007-signature-missing | 引擎对 | hyb 粗筛非空产候选 → scripted partial → violation(fatal=rulepack);同 L1-003 占位符剥离钉法 |
| L1-008-signatory-mismatch | 引擎对 | steps 双条件;授权书存在性达标、签用人不一致单因触发 |
| L1-009-over-max-price | (既有) | T1 期已入库,本批未动 |
| L1-010-price-sum-mismatch | 标注对 | 计划草样 detail_rows 行键用 total,rulepack 契约读 `[*].amount`(DEMO-001 field_snapshot 同证)→ 夹具改 amount;引擎求和/渲染均正确 |
| L1-011-boq-missing-item | 标注对→引擎bug已修 | 见下「引擎修复 #1」;修复后 漏项=tender−bid、增项=bid−tender 与规则名/fix_tpl 语义一致 |
| L1-012-tax-rate-mismatch | 引擎对 | op:all 逐出现值;0.09≠0.13,消息含出现处 where |
| L1-013-substantive-clause | 引擎对 | 计划草样 severity=major 与 rulepack fatal 不符,以 rulepack 为准(标注修正);scripted partial → violation(fatal),message="实质性条款 ★1 响应为 partial:响应偏离" |
| L1-014-duration-over | 引擎对 | 原始数值按 normalize_unit 天口径;200>180 |
| L1-015-warranty-short | 引擎对 | {value,unit} 结构月×30(360<720);_fmt 渲染 "12个月"/"24个月" 入 contains 钉 |
| L1-016-entity-name-mismatch | 引擎对 | op:all 逐处;出现值与执照名差「制造」二字,消息含 (where) |
| L1-019-alternative-offer | 引擎对 | count≠0 即违例;消息含替代方案描述串 |
| L1-021-declaration-missing | 引擎对 | all-in 差集(清单外自附不算违规);缺 DECL-INT 单条 |
| A-1-clean-price | 引擎对 | 价格族全达标零 violation;detail_rows 行键同 L1-010 改 amount(strict=True,need_human 全数容忍) |
| A-2-clean-qual | 引擎对 | 资质族(L1-001/002)全达标零 violation;日期串加引号 |
| A-3-clean-mixed | 引擎对 | 有效期/质保/保证金/声明函族全达标零 violation;bid 自附额外声明函 DECL-EXTRA 不触发=all-in 语义 FP 探针 |

## 引擎修复 #1(批A唯一)

- **位置**:`backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml` L1-011 check(L58-60 → EAI-CUSTOM 注释块)
- **现象**:招标清单有 BM-003、投标清单缺之(典型漏项),引擎消息渲染为「清单不一致:漏项  ,增项 BM-003」——漏项/增项与事实互换。
- **根因**:rule_runner set_eq 渲染契约为恒等式 `{missing}`=right−left、`{extra}`=left−right(L3-007「仅技术标出现 {missing}」实测同款,求值器与该契约自洽);L1-011 却声明 left=tender/right=bid,使真漏项(tender−bid)落 {extra}、投标自附项(bid−tender)落 {missing}。声明侧转置,非求值器缺陷。
- **红先证据**:L1-011-boq-missing-item.yaml 按正确标注(contains "漏项 BM-003")跑出 RED(关键词未命中,引擎现输出为「增项 BM-003」);修复后 GREEN。
- **修法**:L1-011 left/right 对调为 `left: "codes(bid.boq_items)"` / `right: "codes(tender.boq_items)"`。备选方案(求值器统一反转 miss/extra)否决——会破坏 L3-007 消息契约。
- **为什么标注对**:规则名「清单无漏项、无擅自增项」+ fix_tpl「删除擅自新增项或补充漏报项」语义唯一:漏项=tender 要求而 bid 未报。若按现输出钉 contains,即把 bug 固化成标准(spec §9 明否)。
- **buglog**:由 controller 落账;后续挂账:同源 M1 副本 `skills/public/bid-proposal-review/references/rules-det-subset.yaml`(L52-53)载同一转置声明,属技能分发件(bid_review/ 之外),批A未动,须另行对账。

## 批A运行时行为备忘(建库时实测,T2+ 建库者直接受益)

1. **sem/hyb script 三道闸**:evidence 在 docs_text=""(golden runner 缺省)下必走「证据未对齐」降级 → issue.need_human=True 但 verdict=violation 不变;期望匹配不理 need_human 旗标,严格度不受影响。confidence 须 ≥ rulepack confidence_gate(0.75)否则 gate_confidence 转 need_human(verdict 变 need_human → 期望失配)。reason/fix/evidence 文本过 injection_guard(勿含「忽略…要求」「请你扮演」等句式)。
2. **hyb 消息形态**:llm_runner._render_message 对含字段占位符的 message_tpl(如 L1-003/L1-007)剥占位符并尾缀 " ({clause_id}: {reason})";contains 钉「规则关键词 + scripted reason 子串」最稳。L1-013 的 tpl 占位符全由 ctx 供给,消息为纯渲染无尾缀。
3. **det 消息直接可钉**:message_tpl 占位符由 fields+extra 渲染(:money 千分位、list 顿号连接、{value,unit} 中文单位),contains 从现输出照抄即可。
4. **日期值一律加引号**:PyYAML 把裸 `2026-01-01` 转 datetime.date,与 str 混比会 TypeError→逐规则隔离降级 need_human(假阴性)。
5. **A 族 strict 语义实测**:未供 inputs 的规则全部落 need_human(not counted),供齐且 PASS 也不产出——A 族只需保证「供齐的族全 PASS、供不齐的族宁缺勿错」。
6. **命名字**:loader `_NAME_RE` 要求 `^[A-Z0-9]+-[0-9]+-[a-z0-9-]+$`,A 族计划草名 A-clean-l1-* 不合法(第二段须数字),本批落地为 A-1/A-2/A-3-。
