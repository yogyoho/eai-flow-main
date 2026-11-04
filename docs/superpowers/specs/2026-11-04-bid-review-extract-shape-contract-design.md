# 抽取形状契约(occurrence/count 列表字段) 设计

> 日期: 2026-11-04 ｜ 状态: 设计定稿(六裁决已批)
> 前置: R4 活体取证(baselines 实读 + R2/R4 issue 症状对照)
> 范围: extract.py 出口归一 + 提示契约扩容;eval/rule_runner/规则包零改

## 0. 根因(R4 实锤)

1. occurrence 型字段规则预期 `[{value, where}]` 对象列表,抽取实际回**纯值列表**
   (R4 实测:`bid.currency_occurrences=["人民币"]`、`bid.entity_name_occurrences=
   ["某某科技有限公司"]`、`bid.amount_occurrences=[980000]`)→ `op: all` 迭代字符串项
   求值期缺 `c.value/e.value` → 哑 need_human(L3-018 现症;R2 症状为标量 crash 同族)。
2. count() 型字段(`bid.similar_performances` 等)R2 症状=标量 int 进 count → `has no
   len()` crash;R4=模型整体漏抽 → 缺字段 need_human。
3. 波及面:`op: all` 10 条 + `count()` 5 条规则全在裸奔;引擎逐规则隔离正确工作,
   **白丢召回**(R4 "人民币==人民币" 本可干净 pass)。
4. 机制现状:extract.py 已有 `FIELD_TYPE_CONTRACTS` 先例(工期 {value,unit},fix-round
   同款问题同款修法),occurrence/count 型字段零契约零出口闸;prompt 只报字段名不报形状。

## 1. 修复(双层,页码契约先例)

- **出口归一闸**(`normalize_fields` 单点):`OCCURRENCE_PATHS`(10)+`LIST_PATHS`(5)
  注册表;归一语义三条,零编造——①标量→`[标量]`(bool 视垃圾置 None);②occurrence
  路径纯值项→`{value: 项, where: null}` 包装(dict 项原样保留;bool/list/None 项丢弃,
  空结果置 None);③其余垃圾(dict 形状不符等)→None 走字段缺失 need_human。where=null
  由页码契约切片(bug-3972)的对齐层 null 容忍兜底。
- **提示契约扩容**:15 路径入 `FIELD_TYPE_CONTRACTS`(occurrence 契约「对象列表,禁止
  纯值列表」+ count 契约「字符串列表,禁止标量」),:369 现有渲染机制自动进 prompt,
  零额外接线。
- golden 不经 normalize_fields(直喂 rule_runner)——golden 正确形状零影响。

## 2. 六裁决(已批,2026-11-04)

1. 架构 A(出口闸+提示契约同片双层),eval 侧零改;否决求值侧容忍(伪数据=静默采信);
2. 归一语义三条无损/降级规则(见 §1);
3. 手转录 15 路径注册表(与 FIELD_DICTIONARY 同风格三处同步),不做 rulepack 自动推导;
4. 违例消息 `{where}=None` 渲染不动;
5. R5 活体走查(小配额 ~96s):断言 L3-018 翻干净 pass + op:all 家族不再形状炸;
6. bug-3981 入账(入账前查 auto-hook 占号)。

## 3. 验收口径

1. extract 套件 +6 回归门先红后绿(包装/listify/dict 保留/垃圾 None/prompt 契约覆盖);
2. bid_review 全家 pytest 精确计数全绿;golden 55/55 零翻红;ruff 触碰文件绿;
3. gateway 重启后 R5 活体:currency_occurrences 形状正确或经闸归一,L3-018 不再
   「求值期字段缺失」。

## 4. 挂账

- boq_items/detail_rows/scoring_items 等复杂行结构字段只有提示契约无出口闸(形状
  多态,闸会误杀合法行),留观察;
- R5 若 L3-018 仍哑 → 闸语义有漏,回炉。
