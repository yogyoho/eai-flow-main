# 数据源 Tier 1:Agent 感知 实现规格

- **日期**:2026-06-18
- **状态**:已批准设计,待评审
- **范围**:让 Agent 写报告时**主动**使用用户已连的数据源(Option A:静态指令 + description 字段)。
- **目标**:用户配了数据源后,Agent 不再"等点名"——自己 list→按描述选源→只读取数→写进报告并标注来源。
- **机制选择**:静态系统提示指令(**不跨 harness/app 边界**,不破坏 prefix-cache)。否决了 callback/runtime-config 注入(跨边界、每run取数、复杂度高、收益边际)。

---

## 1. 背景

数据源后端 + 只读 MCP 桥已落地(Agent 有 `list_data_sources`/`get_data_source_schema`/`query_data_source`/`test_data_source`)。缺口:写报告的系统提示**没告诉 Agent 这些工具存在、该用**。用户配完只看到"已连接",数据不自动进报告。草稿:`docs/superpowers/specs/2026-06-18-data-source-agent-awareness-tier1-draft.md`。

## 2. 非目标(本期不做)

- 跨边界注入真实数据源列表到提示(callback / runtime config —— Tier 1+ 的强化版)。
- 章节-数据绑定 UI(Tier 2)。
- 活数据/刷新/图表/逐点溯源(Tier 3)。
- 连接器市场、统一插件 tab(Tier 4)。

## 3. 改动总览(3 处)

| # | 改动 | 层 |
|---|---|---|
| A | `DataSource.description` 字段 | model + migrate_db + schema + 前端 |
| B | `list_data_sources` / `get_data_source_schema` 输出带 description | MCP |
| C | 系统提示加静态"数据源工具使用"指令 | harness prompt |

## 4. A — `DataSource.description` 字段

### 4.1 模型(`backend/app/extensions/models/__init__.py` 的 `DataSource`)
- 加 `description: Mapped[str | None] = mapped_column(Text, nullable=True)`。
- `Text` 已在文件顶部导入。

### 4.2 迁移(`backend/app/extensions/database.py` `migrate_db()`)
- 加 `ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS description TEXT`(幂等)。
- **必须用 ALTER**:既有 `data_sources` 表已存在,`create_all` 不会给既有表加列(bug-152 教训)。挂在 migrate_db 里,启动即升级。

### 4.3 Schemas(`backend/app/extensions/data_source/schemas.py`)
- `DataSourceCreate`:加 `description: str | None = None`。
- `DataSourceUpdate`:加 `description: str | None = None`。
- `DataSourceResponse`:加 `description: str | None = None`。

### 4.4 前端(`frontend/src/extensions/data_source/`)
- `types.ts`:`DataSource` 与 `CreateDataSourceRequest` 加 `description?: string | null`(对齐 camelCase;`api.ts` 的 transform 已处理 snake↔camel,确认 `description` 单字直通)。
- `DataSourceForm.tsx`:表单加一个 textarea「描述(给 AI:这个数据源里是什么,例如"厂界噪声 2024 年监测值")」,在「名称」下方。`initialData` 回填;提交时带上。
- `DataSourceCard.tsx`(可选):卡片显示 description 一行(让用户也看见)。

## 5. B — MCP 输出带 description

### 5.1 `list_data_sources`(`backend/app/extensions/data_source/mcp.py`)
- `_handle_list_data_sources` 每条返回的 dict 加 `"description": r.description`(null 安全)。

### 5.2 `get_data_source_schema`(同文件)
- 非 database 分支的返回里加 `"description": src.description`(database 分支已有 name/type,顺手补 description)。

## 6. C — 系统提示静态指令(harness)

### 6.1 位置(`backend/packages/harness/deerflow/agents/lead_agent/prompt.py`)
- 在 `SYSTEM_PROMPT_TEMPLATE` 中新增一段静态文本(或在 `apply_prompt_template` 拼一个 `data_sources_section` 占位填入)。**纯静态、无 per-user 数据**,不破坏 prefix-cache。
- 与现有 skills 段、deferred-tools 段并列。

### 6.2 指令内容(中文,与系统提示语言一致)
```
## 外部数据源(可选)
如果当前任务(尤其是写报告、回答涉及真实数据)需要真实数据,你可以查询用户已配置的外部数据源:
- 先调 list_data_sources 查看有哪些数据源(注意每个源的 description,据此选择最相关的)。
- 用 get_data_source_schema 了解其表/字段或接口结构。
- 用 query_data_source 取数(database 为只读 SQL,强制 SELECT/WITH、自动 LIMIT 200;api 为 GET)。
- 把取到的真实数据写进报告/回答,并标注来源(数据源名称 + 查询时间)。
若这些工具未直接可见,用 tool_search 检索。没有相关数据源时忽略本段。
```

## 7. 数据流

```
用户在「数据源」表单填描述 → DataSource.description(经 ALTER 加列后落库)
                                                           │
Agent 写报告 ← 系统提示静态指令(知道有这些工具、何时用)   │
   │                                                       │
   ▼ list_data_sources ← 返回 name + description ──────────┘
   │ Agent 按 description 选源
   ▼ query_data_source(只读守卫已落地)
   │ 真实数据
   ▼ 写进章节 + 标注来源
```

## 8. 测试(TDD)

- **A 模型/schema**:model 默认 None;router 创建带 description → 201 且响应含 description;PATCH 改 description。
- **A 迁移**:不写自动迁移测试(人工/启动验证);确认 `ALTER ... ADD COLUMN IF NOT EXISTS` 幂等(重启不报错)。
- **B MCP**:`_handle_list_data_sources` 返回项含 description;`get_data_source_schema` 含 description。
- **C prompt**:`apply_prompt_template(...)` 渲染结果包含"外部数据源"指令关键句(如"list_data_sources"),断言字符串存在。

## 9. 验收标准

1. 数据源表单能填描述;创建/编辑/列表/卡片均显示。
2. `list_data_sources` 返回的每项含 description。
3. 渲染的系统提示包含数据源使用指令。
4. 端到端(人工):连一个带描述的源 → 在报告对话里要一个用数据的章节 → Agent **未被点名**,凭 list 的描述选中源、查出真实数据、写进报告并标注来源。

## 10. 风险

| 风险 | 缓解 |
|---|---|
| 既有表加列失败 | 用 `ADD COLUMN IF NOT EXISTS`(幂等);启动 migrate_db 执行(已修通,见 bug-152) |
| 静态指令在数据源工具未启用时冗余 | 指令自带"没有相关数据源时忽略";工具未加载则 Agent 调不到,无副作用 |
| deferred 工具导致 Agent 看不到 | 指令提示用 tool_search;deferred-tools 段已有该机制 |
| 前端 camelCase 映射 | `description` 单字无 snake/camel 差异,直通;api.ts transform 已覆盖 |
| 系统提示变长影响 cache | 该段静态且短;整段 prompt 仍跨用户一致,prefix-cache 复用不变 |
