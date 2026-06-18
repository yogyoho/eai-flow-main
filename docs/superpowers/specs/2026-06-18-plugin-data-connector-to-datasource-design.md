# data_connector 插件 → 数据源模板 实现规格

- **日期**:2026-06-18
- **状态**:语义已定(b:连接器=数据源模板),直接实现
- **目标**:装一个 `type=data_connector` 插件 → 自动建/更新一个 **DataSource**(`type`=插件的 ds 类型、`connection_config`=实例 config);禁用/卸载 → 删该 DataSource。Agent 用**通用**数据源工具(`list_datasets`/`query_dataset`)+ 数据集 UI + 只读守卫操作它。**插件 tab 与数据源 tab 合流。**
- **北极星**:data_connector 插件 = 打包层,映射到"受管 MCP 提供者(数据源)"——不造新原语,复用已建的数据源全套。

## 非目标
- 连接器自动 seed 数据集(连接器建出 DataSource 后,用户用数据集 UI 标注,或 Agent 走富内省兜底)。
- DataSource↔plugin 的强关联字段(name-based 关联,MVP;碰撞=管理边界)。
- entry_point 当 MCP server 的 (a) 语义(已否决)。

## 设计

### 1. `sync_data_source_registration(db, instance, plugin, *, remove=False)`(plugin/service.py)
与 `sync_mcp_registration` 并列的静态方法(async,用传入的 db):
- `should = (not remove) and instance.status=="active" and plugin.type=="data_connector" and plugin.entry_point in ("database","api","file","gis")`
- 查 `DataSource` by `name == plugin.name`(name-based 关联)。
- **should**:无则建(`name=plugin.name, type=plugin.entry_point, connection_config=instance.config or {}, description=plugin.description, auth_type="none", sync_mode="manual"`);有则更新 type/connection_config/description。
- **not should**:有则删。
- `await db.flush()`。**不抛**(失败由调用方事务回滚;与 sync_mcp_registration 的"不阻断业务"一致——但这个走 db,异常会冒泡到 hook→router 事务,可接受;或 try/except 仅 warning)。MVP:不额外 try/except(走正常事务)。

### 2. 钩子(plugin/service.py create/update/delete_instance)
在现有 `sync_mcp_registration(...)` 调用旁,加 `await PluginService.sync_data_source_registration(db, inst, plugin, ...)`:
- create(创建后,active):`await ...sync_data_source_registration(db, inst, plugin)`
- update(status 变更后):`await ...sync_data_source_registration(db, inst, plugin)`
- delete(remove=True):`await ...sync_data_source_registration(db, inst, plugin, remove=True)`
(均在 `await db.flush()` 之后;delete 在 `db.delete(inst)` 之前取 plugin、之后调 sync。)

### 3. demo:给 2 个 data_connector seed 设 entry_point(plugin/seed.py)
现有 seed 的"地质数据连接器"/"环境监测连接器"是 `type=data_connector` 但 `entry_point` 未设。给它们设:
- 地质数据连接器:`entry_point="database"`(config_schema 已是 host/port/database)
- 环境监测连接器:`entry_point="api"`(config_schema 已是 url)
(seed 的 `Plugin(...)` 构造已传 `entry_point=p.get("entry_point")`,只需在 BUILTIN_PLUGINS 这两条加 `"entry_point": "..."`。)

### 4. 数据流
```
插件市场→安装"地质数据连接器"(type=data_connector, entry_point=database, config={host,port,db,user,pwd})
   │ create_instance → sync_data_source_registration
   ▼ upsert DataSource(name="地质数据连接器", type=database, connection_config=config)
Agent: list_data_sources 看到"地质数据连接器" → list_datasets(数据集UI标注 or 富内省兜底) → query_dataset/query_data_source 取数
禁用/卸载 → 删该 DataSource
```

## 测试(TDD, test_plugin_mcp_wiring.py 追加 或 新建 test_plugin_datasource_wiring.py)
- `sync_data_source_registration`:
  - active+data_connector+valid entry_point → upsert(无则建,有则更新);mock db。
  - 非 active / 非 data_connector / 无效 entry_point → 删 existing(若有)。
  - remove=True → 删。
- 钩子:create/update/delete 调它(mock,断言被调)。
- seed:2 个 data_connector 有 entry_point。

## 验收
1. 安装"地质数据连接器"(填 host/port/db/user/pwd)→ `data_sources` 表出现"地质数据连接器"(type=database, connection_config=填的值)。
2. `list_data_sources` 看到 it;Agent 能 query 它。
3. 禁用/卸载 → 该 DataSource 消失。
4. 现有插件/数据源测试全绿。

## 风险
| 风险 | 缓解 |
|---|---|
| name-based 关联碰撞(用户手建同名 DataSource) | MVP 接受(管理员 curated);文档说明。后续可加 `plugin_id` 列强关联 |
| sync 走 db,异常冒泡到事务 | 可接受(与 sync_mcp_registration 的"不阻断"略不同,但 DB 操作本就在事务里) |
| entry_point 语义因 type 而异(tool=MCP模块, data_connector=ds类型) | 文档明示;两种 type 各自清晰 |
