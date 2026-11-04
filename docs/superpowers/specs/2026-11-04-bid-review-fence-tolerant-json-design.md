# 围栏容错 JSON 解析(fence-tolerant check_schema) 设计

> 日期: 2026-11-04 ｜ 状态: 已落地(本切片全量,含实现+活体回采)
> 前置: 真实数据走查(任务 5318d0d9,2026-11-04)发现 P0——生产模型确认面 0% 存活
> 范围: engine/verify.py `check_schema` 单点 + llm_verify +2;规则包/前端零改

## 0. 发现(真实数据走查战报)

走查任务 `5318d0d9`(数据中心 L2 件,agnes-2.5-Flash,quick 全管线 94s,35 规则):

**活体验证通过**:L2-020 MISSING→fatal(entity ✓)/近似行 need_human(相似度0.7,entity ✓)/
L2-021 det 候选真实生成(bug-3965 门修复活体生效,`hyb_prefilter.hit n=1`)/降级路径实体存活
(`attachment:2`)/L2-024 份数 violation/429 免费档单规则隔离降级不炸任务。

**P0**:agnes-2.5-Flash 每回包 `\n\n```json … ``` 围栏包壳 → check_schema 裸 json.loads
于 char 2 全灭(每次调用每次重试同一位置)→ L1-003/L1-013/L2-021 全部 schema_discard→
候选降级 need_human。**生产模型确认层 0% 存活**;echo 遵从率/entity join 确认路径被遮蔽。
det 层不受影响(走查 5 条 L2 issue 全对),死的只是模型确认段。

## 1. 修复

`check_schema` raw 层三级降级(单点,sem/hyb 全路径共用此咽喉):

```
1) 直接 json.loads(现状零改,纯 JSON/dict 输入零影响)
2) 失败 → 剥 ``` 围栏(正则 ```(?:json)?\s*(.*?)\s*``` DOTALL 取第一块)再 loads
3) 再失败 → 首 { 末 } 切片再 loads(宽容 prose 包裹)
4) 全败 → not_json(现状错误路径不变)
```

六裁决:①单点 check_schema(不散修调用侧);②三级降级如上(逐级宽容,全败才报错);
③零翻红=既有测试全传纯 JSON/dict 不受影响,golden script 纯 JSON 不变,新增围栏/prose
2 测;④429 免费档限流不改码(隔离按设计工作),换主模型/升 plan 是运维决定不属本切片;
⑤修复后用 `/tasks/{id}/retry` 重跑走查补采 echo 遵从率+entity join 确认路径活体证据;
⑥bug-3971 随修复入账。

## 2. 验收(落地实测)

1. llm_verify **46** 全绿(44+2;围栏/prose 先红后绿);
2. bid_review 全家 pytest **398 passed / 0 failed** exit 0;
3. golden CLI **55/55** exit 0;
4. **活体回采**(R2 任务 7c6aec02,版本链挂 5318d0d9,gateway 重启后):围栏容错生效
   ——schema 报错从 `not_json: Expecting value…char 2` 前进到内容级
   (`evidence[0].page 必须为正整数`);L1-003 出现 `(C1: …)` 候选 id 回显确认条目
   =**echo 遵从率首证 >0**;done,fatal 1/major 2/need_human 27(R1 为 31);
5. ruff 触碰文件绿(impl commit 见 push 批次)。

## 4. 回采新发现(剥壳后暴露的第二层,入队列非本切片)

- **P1 evidence.page 契约 vs text-kind 文档**:模型对 .md(无页码)回不出正整数页,
  L2-021/L1-003/L1-013 确认段死在 `page 必须为正整数` 重试循环——模型确认层复活的
  最后一块拦路石(下一切片首推);
- **P1 重复执行/双快照重复条目**:同规则两行(两份字段快照,如 L2-020 fatal×2),
  dedup_key 因 clause/evidence 差异未合并;summary fatal=1 与 DB fatal violation=2 口径
  不一致——需 worker 取证;
- **P2 抽取形状契约**:L1-016/L3-018 crash `'int' object is not iterable`、L1-003
  prefilter skip `object of type 'int' has no len()`——抽取回标量而规则吃列表;
- **观测**:entity join 确认路径仍未观测到(L2-021 确认死在 page 契约,非 join 问题);
  L1-003 回显条目 verdict=violation+need_human=t(confidence 门槛按设计转待人工)。

## 3. 挂账

- agnes-2.5-Flash 免费档 429 限流(约 15 次调用后触发)——换主模型/升 Token Plan,运维决定;
- echo 遵从率长期观测机制(修复后仅单次采样)。
