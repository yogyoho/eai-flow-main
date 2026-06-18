# 数据源 → Agent 感知(Tier 1)产品 spec 草稿

- **日期**:2026-06-18
- **状态**:草稿(产品分析存档,尚未进入 brainstorm→实现流程)
- **来源**:`/plan-ceo-review` 产物。方向已选定 = Tier 1(Agent 感知);本次范围 = 仅分析。
- **目的**:把"数据源接通之后给用户什么"的产品决策与实现思路固化,下次开干时直接 brainstorm→spec→plan→实现。

---

## 1. 背景:为什么需要这一层

数据源后端 + 只读 MCP 桥已落地:用户能配 DB/API/file/GIS 源,Agent 有 `list_data_sources`/`get_data_source_schema`/`query_data_source`/`test_data_source` 四个工具。

**缺口**:Agent **有**工具,但写报告时**没人提示它"你有这些数据源、该用"**。用户配完只看到绿色"已连接"徽章,数据不会自动进报告。**联通是管道,不是产品**——水没流到任何地方。

## 2. 目标(产品,非技术)

让 Agent 在写报告(或任何取数任务)时,**主动**识别并使用用户已连的数据源,把真实数据填进报告并标注来源。用户的体感从"我配了个源,然后没然后"变成"我配了源,数据自己进了报告"。

## 3. 解决方案(机制)

把"可用数据源摘要"注入 Agent 系统提示,与现有 skills/memory/MCP 注入同路径(`apply_prompt_template`)。run 开始时读当前用户已连的源,拼一段塞进提示:

```
## 可用数据源(可用 query_data_source 只读查询,自动 LIMIT 200,只读)
- 监测平台(API):厂界噪声/地下水 2024 年监测值
- 地质钻孔库(database, 表:钻孔/地层/取芯):本场地勘察数据
```

注入粒度三选(推荐第3种):
1. 静态全量 schema —— token 贵,源多即爆。
2. 纯懒加载(只给工具,靠 tool_search) —— Agent 不知道要搜,≈没有。
3. **摘要注入(推荐)**:name + type + 一句话描述 + 顶层表名(来自 `get_data_source_schema`,可缓存)。要细节再调 schema 工具。

## 4. 杀手级小细节:数据源加 `description` 字段

全层性价比最高的一行改动。现 `DataSource` 只有 `name`(如"测试数据库"),Agent 看名字无法判断里面是监测还是地质数据。加 `description`/`purpose`(用户写"厂界噪声 2024"),Agent 就能**按意图匹配到对的源**。无此字段,Agent 只能瞎猜或要求用户点名,第1层效果打折一半。模型加列 + 前端表单加输入框。

## 5. 用户体验("啊哈"时刻)

1. 用户连"监测平台",填描述。
2. 报告对话:"写第三章 地下水现状评价"。
3. Agent **未被点名**,凭描述认出该用"监测平台",查真实数据,写进章节,标注"数据来源:监测平台,查询于…"。
4. "已连接"徽章第一次意味着:数据自己进了报告。

## 6. 设计岔路(开干时定)

| 岔路 | 建议 | 理由 |
|---|---|---|
| 摘要新鲜度 | 每次 run 开始现读,不跨 run 缓存 | 源会增删改名,陈旧摘要=查错库 |
| 注入哪些源 | 当前用户的 + 全局 | 与数据源 ownership 一致 |
| 主动 vs 被动 | 按 `description` 匹配决定查不查,不每次都探 | 过度探查=慢+吵;描述匹配最准 |
| 溯源 | 第1层就带("数据来源:X,查询于…") | 一开始建信任,直接铺路 Tier 3 |
| 连接成本 | 每次查询开新引擎(NullPool),先这样 | MVP 够用;规模化再池化 |
| 安全 | 不改变威胁模型 | 查询仍走 `assert_readonly_select` 只读守卫;感知只是"知道存在",不提权 |

## 7. 验收标准

- 用户连一个**带描述**的源。
- 开报告对话,要一个用数据的章节。
- Agent **未被点名**,凭描述认对源、查真实数据、写进去并标注来源。
- 这条 demo 跑通 = 数据源功能"值回票价"。

## 8. 范围外(本层不做,Tier 2/3/4)

- Tier 2:章节-数据绑定 UI(选源/表绑到章节)。
- Tier 3:活数据(刷新/"数据截至"/图表/过期提醒/逐点溯源)。
- Tier 4:连接器市场(装连接器→得数据源,统一插件 tab 与数据源 tab)。
- 本层是 Tier 2/3 的地基:Agent 得先知道源存在,才能绑定。

## 9. 与现有架构的接口点(实现时的抓手)

- 注入位置:`packages/harness/deerflow/agents/lead_agent/agent.py` 系统提示组装(`apply_prompt_template`),与 skills/memory 同段。
- 取数:复用 extensions DB(查当前用户 `DataSource`),经现有 MCP/服务路径读 name/type/description/顶层表。
- 描述字段:`DataSource` 模型加 `description: str | None`;前端 `DataSourceForm` 加输入框。
- 只读安全:复用已落地的 `assert_readonly_select`。

## 10. 下一步

进入 `superpowers:brainstorming` 把本草稿转成正式 spec(澄清:摘要注入的精确格式、description 是否必填、全局源可见性、token 上限),再 writing-plans→实现。
