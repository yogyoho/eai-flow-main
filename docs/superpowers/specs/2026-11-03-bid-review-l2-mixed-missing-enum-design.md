# L2 混合态真缺失子件 issue 面枚举 设计

> 日期: 2026-11-03 ｜ 状态: 已落地(e671c9ba3..575be1f81 推送 origin/main-dev-fork)
> 前置: P3.2 已落地(本项是其 §8 挂账 :142 的兑付;L2-tuning/L2-synonyms 已落地)
> 范围: 后端 bid_review 扩展内,零上游/harness 改动

## 0. 背景与问题

P3.2 给复合子行 near_miss 加了逐子行 need_human(`rule_runner.py` `subs_nm` 分支),但该分支只遍历
`unknown_reason == "near_miss"` 的子件。混合成因父行(子 A near_miss + 子 B 真缺失)里,**真缺失
子件在 issue 面零可见**——近似子件有候选话术,真缺失子件什么都不发,只活在 checklist sub_results。
P3.2 质量审查 Minor-2 当时就此挂账(当时不动消息格式,scope 纪律);本切片兑付。

## 1. 机制(裁决1: 逐子行独立 need_human,不折进父消息)

`subs_nm` 分支内、近似子件循环之后追加真缺失子件循环:

```python
for s in (r.get("sub_results") or []):
    if s.get("status") != "MISSING":
        continue
    nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」缺失,需人工核对")
    nh["entity_keys"] = [_entity_key(s)]
    nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"
    issues.append(nh)
```

与 P3.2 逐子行点名哲学同构(近似子件点名候选、真缺失子件点名缺失);entity/dedup 按子行实体键
(同既有 :267-268 手法,同父两子不互吞)。**纯增量**:既有消息一字不改(平件/grouping/近似候选
措辞全保留,golden contains 回归面零动)。

## 2. 边界(裁决2/3)

- **miss 分支复合行不动**——「历来只点名父件」维持 P3.2 裁决(升级哲学+checklist 承载);
  改它 = 动规则模板 + golden contains 面,另一量级。
- **纯 grouping 父行(孤儿+真缺失子件)不枚举**——「无法自动分组」消息已让人逐子件重排,
  枚举无增量;循环放 `if subs_nm:` 内即天然满足。孤儿+近似+真缺失三因并存时枚举仍成立
  (同一循环同分支,三条真相各自成话)。

## 3. 零翻红论证

52 金标准题无一含「near_miss + MISSING 混合父行」(L2-020 三题其余子件全 MATCHED);
新 issue 只在混合态出现 → golden 不触发任何题,52/52 维持。

## 4. 测试

rule_runner +1(混合态枚举):混合父行 fixture(子 3.1 MATCHED / 3.2 near_miss sim≈0.83 /
3.3 真缺失)→ len==2;近似话术不变 + 真缺失子件独立 need_human 点名父件+子件(3.3 完税证明),
entity/dedup = `attachment:3.3`。
裁决偏差:设计表原列「纯 near_miss 父行不多发」+1 测——既有
`test_att_check_sub_near_miss_message_names_subitem` 已钉 len==1(同 fixture),重复,不新增。

## 5. 验收

1. `PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py` 全绿(预期 23+1=24);
2. bid_review 全家 pytest(预期 378+1=379/6);
3. golden CLI 52/52 exit 0;
4. ruff 触碰文件全绿;diff 仅 backend/app/extensions/bid_review/engine/rule_runner.py + backend/tests/test_bid_review_rule_runner.py + docs。

## 6. 执行方式(裁决5)与挂账

- 429 配额未重置 → 控制器 inline 执行(同 tuning/synonyms 切片),deviation 如实记录;
- :141 channels 位置元数据跳过(cosmetic,YAGNI);:143 时点性维持记录备查;
- 后续队列:指纹通道与 L0-L5 抽取管线(大件,单独立项设计讨论);
- 运行时生效仍需 gateway 重启(P3.2 起挂账,并发会话风险待用户)。
