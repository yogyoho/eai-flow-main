# 围栏容错 JSON 解析(fence-tolerant check_schema) 设计

> 日期: 2026-11-04 ｜ 状态: 设计定版(实施中)
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

## 2. 验收

1. llm_verify 新 2 测先红后绿(围栏/prose 包裹均过 schema);
2. bid_review 全家 pytest 精确计数(基线 396+2=398 口径);
3. golden CLI 55/55 exit 0(scripted 纯 JSON,确认非依赖);
4. retry 走查任务:L2-021 模型确认段活体观测(echo 遵从/entity 继承/partial 别名路径);
5. ruff 触碰文件绿。

## 3. 挂账

- agnes-2.5-Flash 免费档 429 限流(约 15 次调用后触发)——换主模型/升 Token Plan,运维决定;
- echo 遵从率长期观测机制(修复后仅单次采样)。
