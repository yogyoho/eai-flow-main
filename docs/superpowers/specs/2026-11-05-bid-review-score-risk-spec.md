# bid-review 评分涉险面(score 预估)Spec(2026-11-05)

> 挂账兑付:对齐审计裁决②「若产品侧真要预估,另立 spec——显式拒绝编造」。
> 同 slice 完成 spec + 实施(零配额纯后端,零新端点零迁移)。

## 背景

`score_coverage`(B4)= 评分办法项 × 规则 inputs **机械求交的覆盖度审计面**——它回答
「多少评分项被规则看管着」,不回答「能得多少分」。对齐审计②补过 `covered_max_score`
事实键并明示「非得分预估」。本 spec 定义真正的预估面,**边界一句话:引擎不知评分
细则的裁量矩阵,任何「预计扣 N 分」都是编造;可诚实给出的是涉险上界**。

## 裁决

1. **R1 涉险上界,拒绝预测得分**。新增三个事实键,全部由既有数据机械派生:
   - `at_risk_max_score`(float|None):涉险项 max_score 可数值化合计——「这些分处于
     风险中」是上限事实,不是预计扣分;
   - `at_risk_item_names`(list[str]):涉险项名(审计锚);
   - `unresolved_item_names`(list[str]):unclear/待人工规则命中项——**不可估面**,
     显式列出,不凑数不编造。
   措辞纪律:一切消费方(docstring/MCP/前端)必须表述为「涉险/风险上限」,禁用
   「预计得分/预估扣分」。
2. **R2 归因链可审计,与 coverage 同源**。violation issue.rule_id ∩ item.covered_by_rules
   非空 → 该项涉险(交集机制,不靠语义猜);一条违规命中多项 → 全计(保守上界);
   false_positive 不进(引擎已翻清白);unclear/need_human → unresolved。
3. **R3 真零/伪零纪律**。无涉险项 → `at_risk_max_score = 0.0`(真零事实:无活跃违规
   威胁任何评分项);有涉险项且可数值化 → 合计;有涉险项但 max_score 全不可数值化
   → `None`(诚实不可估,不凑 0,与 covered_max_score 同型)。
4. **R4 接线零面变化**。派生在 `GET /tasks/{id}/score_coverage` 端点层(现算不落库
   先例):`compute_score_coverage` 本体**零改动**;空评分项短路响应**字节不变**
   (`{"total":0,"covered":0,"items":[]}`,前端回落口径不动);MCP `bid_review_score_coverage`
   `**out` 透传自动浮出新键,handler 零改动。报告 md/html 本 slice 不加节(YAGNI,
   MCP+API 是 agent/UI 通道;产品要报告呈现再立项)。
5. **R5 断言面(bug-4018 纪律)**。既有三处精确锁全部保持:
   - `compute_score_coverage([],[])` 全等锁(:59)→ 本体不改,安全;
   - items 逐项全等锁(:54)→ 不加逐项键,涉险聚合在顶层,安全;
   - 端点空短路全等锁(:139)→ R4 字节不变,安全。

## 纯函数契约

`derive_score_risk(coverage_out, violation_rule_ids, unresolved_rule_ids) -> dict`
(engine/extract.py,与 compute_score_coverage 同文件;违规集由端点从
`crud.list_issues` 派生:active = `verdict=="violation" and not need_human`;
unresolved = 非 false_positive 且 (`need_human or verdict=="unclear"`)):

- 逐 item:`covered_by_rules ∩ violation_rule_ids` 非空 → 涉险;否则 ∩ unresolved
  非空 → unresolved(互斥,violation 优先);
- 数值化:`float(max_score)` 失败跳过数值不炸整体(名字仍列);
- 返回三键(R1)。

## 验收(测试即契约)

- 纯函数:数值合计+名字;真零 0.0;unresolved 列名不进合计;违规规则未覆盖任何项
  → 0.0 空名;涉险全不可数值化 → None;
- 端点:带基线评分项 + 三种 verdict 的 issues → 响应含三键且值正确;空评分项任务
  → 旧形状全等不变;md/html 报告与 MCP 既有断言零翻红。

## Out of scope

- 扣分矩阵/裁量校准(需产品+历史复核数据,另行立项);
- 报告呈现节、前端 meter 改造(消费方后续 slice);
- score_coverage 落库(现算先例保持)。
