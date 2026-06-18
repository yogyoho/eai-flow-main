# 插件 → MCP 接线(type=tool)实现规格

- **日期**:2026-06-18
- **状态**:已批准设计,待评审
- **北极星(已采纳,本 spec 落地第一步)**:能力到达 Agent 只有 3 个原语(MCP 工具 / Skills / 子agent)。任何"管理/打包"层只有接线到原语之上才算数。数据源已是"受管 MCP 提供者"✓;**插件当前是孤岛——本 spec 把它接线到 MCP**,消除大杂烩。
- **目标**:`type=tool` 插件**启用**→把其 `entry_point` 注册成 `extensions_config.mcpServers` 里的一条 → Agent 经 function calling 立即获得其工具;**禁用/卸载**→摘掉。附 1 个 demo 模块端到端验证。

---

## 1. 背景与现状(有据)

- 插件 `plugin/` 目前**纯元数据**:安装/启用不碰 MCP/skills/子agent(`grep` 确认仅 `entry_point` 字段,无任何原语接线)。装了不动 = 孤岛,function calling 调不到。
- `Plugin` 模型已预留 `type`(data_connector/tool/output/custom)+ `entry_point`(模块路径)+ `config_schema`,设计上要指向原语,只是没接。
- `function calling` 已在用(LangGraph+LangChain,所有工具汇成 Tool)。所以接线终点 = `entry_point → MCP server → Tool → function calling 可达`,跟数据源同一条路。
- 写 `extensions_config.json` 的现成机制:`deerflow.config.extensions_config`(`get_extensions_config`/`reload_extensions_config`/`resolve_config_path`);gateway `routers/mcp.py` 已用"读 raw → 改 mcpServers → json.dump → reload"模式(本 spec 复用)。

## 2. 非目标(本期不做)

- 其它 type 的原语映射:`data_connector`→数据源模板、`output`→skill、`agent`→子agent。
- 插件沙箱 / 代码签名 / 权限审批(MVP 假定管理员可信插件,见 §6 安全)。
- 前端"工具已生效"的实时反馈(本期靠"启用后去对话里看 Agent 有没有新工具"人工确认)。
- Dataset 层(数据源子级,另一条线,符合北极星但独立)。

## 3. 设计

### 3.1 接线核心:`sync_mcp_registration(instance, plugin)`
新增于 `backend/app/extensions/plugin/service.py`(纯函数,不碰 DB):
- **mcpServers key** = `plugin_{plugin.id}`(UUID,稳定唯一;`description` 字段带人类名)。
- **if `instance.status == "active"` and `plugin.type == "tool"`**:写入/覆盖一条:
  ```json
  { "enabled": true, "type": "stdio",
    "command": "/app/backend/.venv/bin/python",
    "args": ["-m", "<plugin.entry_point>"],
    "env": <instance.config 中带 env 前缀的项,或整个 config;见 §3.2>,
    "cwd": "/app/backend", "url": null, "headers": {}, "oauth": null,
    "description": "<plugin.name>: <plugin.description>" }
  ```
- **else(非 active,或非 tool 类型)**:从 mcpServers 删除该 key(若存在)。
- 实现:读 raw `extensions_config.json`(保留所有其它顶层 key + skills)→ 改 `mcpServers` → `json.dump` 写回 → `reload_extensions_config()`(触发 harness mtime 热加载)。**幂等**:重复启用不产生重复条目。

### 3.2 env 传递
`PluginInstance.config`(按 `plugin.config_schema` 校验过的 JSON)→ 取出字符串值作为 MCP server 的 `env`(供 entry_point 进程读取,如 DB URL、token)。MVP:整个 config dict 平铺进 env(键须是合法环境变量名;非字符串值 `json.dumps`)。可后续细化。

### 3.3 钩子(在现有 service 方法里调用 sync)
- `create_instance`:创建后(状态默认 active)→ 若 type=tool → sync(注册)。
- `update_instance`:status 变更后 → sync(按新状态注册/摘除)。
- `delete_instance`:删除前 → sync(摘除)。
- 调用放 service 层(router commit 之后)。sync 本身不抛(写文件失败仅 log warning,不阻断业务——插件数据已存,只是没接上 MCP)。

### 3.4 demo 模块 + 预置插件
- 新增 `backend/app/extensions/plugin/builtin/demo_mcp.py`:极简 stdio MCP server(仿 `data_source/mcp.py` 结构),暴露 1 个工具 `demo_greet(name)` → 返回 `"你好,{name}"`。
- 在 `plugin/seed.py` 的 `BUILTIN_PLUGINS` 加 1 条:`{name:"示例工具(演示接线)", type:"tool", entry_point:"app.extensions.plugin.builtin.demo_mcp", description:"演示插件→MCP 接线:启用后 Agent 获得 demo_greet 工具", config_schema: {type:object}}`。幂等 upsert(已有 seed 机制)。

### 3.5 北极星文档
在 `CLAUDE.md` 架构段加一小节"扩展能力 3 层模型(北极星)":原语 / 受管提供者 / 打包层 + "不接原语不建"准则。

## 4. 数据流

```
插件市场→安装(type=tool)→ status=active
   │ service.create_instance → sync_mcp_registration
   ▼ 写 extensions_config.mcpServers["plugin_<id>"]
reload_extensions_config → harness MCP loader(mtime 热加载)
   ▼ langchain-mcp-adapters
Agent 工具集 += demo_greet(function calling 可调)
禁用/卸载 → sync 摘除条目 → reload → Agent 失去工具
```

## 5. 测试(TDD)

- `test_plugin_service.py`:`sync_mcp_registration`
  - active+tool → extensions_config(用临时文件/monkeypatch 路径)出现 `plugin_<id>` 条目,enabled=true,args=`["-m", entry_point]`。
  - 非active / 非 tool → 条目被删。
  - 幂等:连续两次 active 不重复、不报错。
  - 写文件失败不抛(monkeypatch open 抛 → 仅 warning)。
- `test_plugin_routers.py`:启用/禁用/卸载端点触发 sync(mock `sync_mcp_registration`,断言被调用/未调用)。
- demo 模块:`demo_mcp.py` 可 import、`TOOLS` 含 `demo_greet`。
- 北极星:无自动测试(文档)。

## 6. 安全

MVP:**管理员可信插件**。启用一个 type=tool 插件 = 在 gateway 容器里以 `python -m <entry_point>` 起一个进程(执行其代码)。风险=任意代码执行。本期假定插件来源可信(管理员手动 seed/安装)。**显式不做的**:沙箱隔离、代码签名、安装审批流、entry_point 白名单。文档与 UI 文案标注此假设;后续按需补沙箱/签名(P2)。

## 7. 验收标准

1. seed 的"示例工具"在插件市场可见;**安装 + 启用**后,`extensions_config.json` 出现 `plugin_<id>` 条目;在对话里 Agent **能用 `demo_greet`**(function calling 调到)。
2. **禁用**该实例 → 条目消失 → Agent 失去 `demo_greet`。
3. 卸载 → 条目消失。
4. 幂等:重复启用/禁用无副作用、无报错。
5. 北极星 3 层模型写进 CLAUDE.md。
