# L2 候选→确认条目 entity 继承(join key) 设计

> 日期: 2026-11-04 ｜ 状态: 已批准(六裁决,会话 2026-11-04)
> 前置: L2-指纹通道已落地(其 §6 挂账首位=本切片;bug-3966)
> 范围: llm_runner.py 为主 + golden case 1 回填 + llm_verify +2;规则包/规则引擎/前端零改

## 0. 问题

hyb det 候选经模型确认后实体丢失:`build_rule_card` 候选段只给模型 `{verdict, message}`(无 id),
模型回条与 det 候选无 join key → `_verdict_to_issue` 产物零 entity_keys → L2-021 确认条目进不了
跨层重复投影(routers 同实体跨 ≥2 层)与 crud 持久化合并。降级(schema 弃→need_human)与
passthrough(缺字段)路径走 det 原始 dict,实体本就带——**只有模型确认路径丢**。

## 1. 机制

```
候选注入:  candidates 附加稳定 id "C1"/"C2"…(注入时枚举,不污染 det 原始 dict)
           候选段 JSON 每条带 "id";指令追加「回显 clause_id 用候选 id」
模型回显:  entry.clause_id == "C1" → cand_map 查回候选
继承:      _verdict_to_issue 后、七道前:issue["entity_keys"] = 候选 entity_keys(unclear 同继)
降级:      模型自造 clause_id 查不回 → 无 entity(=现状,弱而非坏)
```

六裁决:①join key=候选 id 注入+模型回显(位置对齐脆弃/message 匹配不可靠弃);②继承时机=
条目成型后、七道前(entity 不参与七道,时机统一);③PROMPT_VERSION 升版 2026-10-29→2026-11-04
(候选段契约变更,溯源诚实);④golden case 1 恢复 entity 钉+script clause_id 改 C1,既有 4 条 hyb
金题 script 不动(按 rule_id 路由无视 prompt,存量零翻红);⑤SCHEMA_HINT 不动(候选回显语义只属
hyb 候选段指令,不污染全局模板);⑥llm_verify +2(回显继承/自造 id 零 entity)。

## 2. 零翻红论证

- 既有 hyb 金题(L1-003/007,L3-004/008)script 按 rule_id 路由、内容无视 prompt → 候选段格式
  变更零影响;其 det 候选 entity_keys 恒 [](数字/计数类 det issue)→ 继承恒 no-op;
- llm_verify 既有候选段断言字符串("det 粗筛候选"/"驳回候选"/"unclear")指令改写中保留;
- prompt_version 断言仅存在性,升版零翻红。

## 3. 验收

1. llm_verify 42→44 全绿;
2. bid_review 全家 pytest **394/6**(392+2);
3. golden CLI **55/55** exit 0(case 1 entity 钉恢复=端到端验证);
4. ruff 触碰文件全绿;diff 仅 llm_runner+golden case 1+llm_verify+docs。

## 4. 挂账

- 真实模型对「回显候选 id」遵从率——观测(不回显=丢实体=现状,无回归);
- gateway 重启总挂账不变。
