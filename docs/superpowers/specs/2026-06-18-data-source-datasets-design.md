# 数据源数据集层(DataSourceDataset)Phase 1 实现规格

- **日期**:2026-06-18
- **状态**:已选模型(B+D:实例+数据集+自动兜底),待评审
- **北极星**:数据源 = 受管的 MCP 提供者。**Dataset 是其上的"业务表标注层"**——把"实例里有哪些业务表、各叫什么"显式化,让 Agent 按业务名直查,而非盲翻全库。符合 3 层模型(仍是 MCP 工具)。
- **范围(Phase 1,纯后端)**:`DataSourceDataset` 模型 + CRUD 端点 + `list_datasets`/`query_dataset` 两个 MCP 工具(无标注时自动兜底发现)。
- **Phase 2(不做)**:前端标注 UI;富内省(列/行数/样例)。

---

## 1. 背景与目标

数据源只到"实例"级;一个实例有多张业务表(噪声/地下水/废气…),Agent 现在靠 `get_data_source_schema` 列全部表再猜。**目标**:让用户给关键业务表**打标签**(label+description),Agent 按标签直查。没标注的源 → 自动兜底(列表明表名)。

## 2. 非目标(本期)

- 前端标注 UI(Phase 2;本期靠 API/SQL 标注)。
- 富内省(列/行数/样例,Phase 2 的 `get_data_source_schema` 升级)。
- `default_query` 的复杂解析(本期支持存,查询时当只读 SQL 走守卫;不做变量替换)。

## 3. 数据模型(新表,create_all 自动建)

`DataSourceDataset`(`backend/app/extensions/models/__init__.py`):
```
id(UUID pk) · source_id(UUID FK→data_sources, ON DELETE CASCADE, not null, index)
table_name(str 200, not null)        # 技术锚点
label(str 200, not null)             # 业务名,如"厂界噪声"
description(text, nullable)          # 给 AI
key_columns(JSONB, nullable)         # 如 ["点位","Leq","时间"]
default_query(text, nullable)        # 可选保存的只读 SQL
created_at · updated_at
__table_args__ = UniqueConstraint(source_id, table_name)
```
- 新表 → `create_all` 建表(**不需要** ALTER;非 bug-152 场景)。
- 级联删:数据源删 → 其数据集自动删(`ON DELETE CASCADE`)。

## 4. Schemas(`data_source/schemas.py`)
- `DatasetCreate`: `table_name`(必填)、`label`(必填)、`description?`、`key_columns?`、`default_query?`。
- `DatasetUpdate`: 全可选。
- `DatasetResponse`: 全字段(from_attributes)。
- `DatasetListResponse`: `{items: [DatasetResponse]}`。

## 5. Service(`data_source/service.py`,`DataSourceService` 加静态方法)
- `list_datasets(db, source_id) -> [DataSourceDataset]`
- `get_dataset(db, dataset_id)`
- `create_dataset(db, source_id, req) -> DataSourceDataset`(校验 source 存在;唯一约束冲突→400)
- `update_dataset(db, dataset_id, req)`
- `delete_dataset(db, dataset_id) -> bool`
- `resolve_dataset(db, source_id, label) -> DataSourceDataset | None`(按 label 找;Phase 1 query_dataset 用)

## 6. REST 端点(嵌在数据源下,prefix `/api/extensions/data-sources`)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/{source_id}/datasets` | 列该源数据集 |
| POST | `/{source_id}/datasets` | 创建(table_name+label) |
| PATCH | `/datasets/{dataset_id}` | 改 |
| DELETE | `/datasets/{dataset_id}` | 删 |
全部 `Depends(get_current_user)`。

## 7. MCP 工具(`data_source/mcp.py`)
### `list_datasets(source_name)`
- 经 `_run_in_db` 取 source + 其数据集。
- **有标注数据集**:返回 `[{label, table_name, description, key_columns}]`。
- **无标注(D 兜底)**:调 `DataSourceService.list_tables(source)`(已有,连源库)返回 `[{"label": table, "table_name": table, "auto": true}]`,并附 `"note": "未标注,自动列出表名"`.
- source 不存在 → `{success:false}`。

### `query_dataset(source_name, label, params?)`
- `resolve_dataset` 按 label 找数据集。
- 找到 → 用 `default_query`(若有)或无(报"该数据集未配 default_query,用 query_data_source 写 SQL")。**有 default_query** → 经 `assert_readonly_select` + `run_readonly_query(source, sql)` 执行(复用只读通道)。
- 找不到 label → `{success:false, message:"数据集不存在:label;可用 list_datasets 查看"}`。
- Phase 1 简化:`query_dataset` 只跑 `default_query`(若配了);没配则提示用 `query_data_source`。避免 Phase 1 引入 params→SQL 模板的复杂度。

## 8. 数据流
```
用户标注:数据源X→数据集「厂界噪声」(table=noise_monitor, default_query="SELECT ... LIMIT 200")
Agent 写报告:list_data_sources → list_datasets(X) → 看到「厂界噪声」→ query_dataset(X,"厂界噪声")
   → resolve → default_query → assert_readonly_select → run_readonly_query(连源库) → 真实数据
未标注源:list_datasets 自动列表明表(D 兜底)→ Agent 看到表名
```

## 9. 测试(TDD)
- **model**:DataSourceDataset 默认值、表名、唯一约束。
- **service**:create(校验 source / 唯一冲突)、list、update、delete、resolve。
- **router**:GET/POST/PATCH/DELETE(dependency_overrides + mock service)。
- **mcp**:list_datasets(有标注→返回;无标注→调 list_tables 兜底)、query_dataset(找到+default_query→跑;找到无 default_query→提示;找不到→404)。

## 10. 验收标准
1. 能经 API 给一个数据源加数据集(table+label+description+default_query)。
2. `list_datasets` 返回标注数据集;无标注时返回自动列出的表名。
3. `query_dataset` 对配了 default_query 的数据集返回真实数据(只读)。
4. 删数据源 → 其数据集级联删除。

## 11. 风险
| 风险 | 缓解 |
|---|---|
| default_query 是用户写的 SQL | 经 `assert_readonly_select` 只读守卫(已落地);失败回错不执行 |
| 无标注源兜底连源库慢 | 复用 `list_tables`(已有,Limit 50);Phase 2 富内省时加缓存 |
| label 重名 | Phase 1 按 label 取第一个(resolve_dataset);唯一约束在 (source_id, table_name) 不在 label,label 重名允许多个(取首个) |
