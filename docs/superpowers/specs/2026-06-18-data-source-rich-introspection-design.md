# 数据源富内省(列画像)设计规格

- **日期**:2026-06-18
- **状态**:设计明确(单函数增强),直接实现(TDD,不单列 plan)
- **目标**:Agent 自动探索数据源表时**看到列**,从而可靠地把"厂界噪声"对到正确的表,而非盲猜表名。
- **北极星**:数据源 = 受管 MCP 提供者;富内省是其"自动画像"能力(仍是 MCP 工具路径)。

## 改动(后端,1 个新方法 + 2 处接线)

### 1. `DataSourceService.profile_tables(source)`(新,`data_source/service.py`)
连**源库**(`_build_db_url`),**一条** `information_schema.columns` 查询(public schema),按表分组,返回:
```python
[{"name": "<table>", "columns": [{"name": "<col>", "type": "<data_type>"}, ...]}, ...]  # 上限 50 表
```
- 一次查询(cheap),不分表 count/sample(性能;列名已足以让 Agent 选对表)。
- 复用 `create_async_engine` + `NullPool`(同 `list_tables`/`run_readonly_query`)。

### 2. `get_data_source_schema` 数据库分支(`data_source/mcp.py`)
由 `list_tables`(只表名)改为 `profile_tables` → `tables` 字段返回 `[{name, columns}]`。

### 3. `list_datasets` D 兜底(`data_source/mcp.py`)
由 `list_tables` 改为 `profile_tables` → 无标注时返回的自动数据集带 `columns`(label/table_name/columns)。

### 保留 `list_tables`
不删(避免动其它引用);`profile_tables` 是新增。两个调用点切换到 `profile_tables`。

## 测试(TDD,`test_data_source_datasets.py` 追加)
- `profile_tables`:mock `create_async_engine`,返回 information_schema 行 → 断言按表分组、列名/类型正确、上限 50。
- `list_datasets` D 兜底:把现有 `test_list_datasets_fallback_when_none` 的 mock 从 `list_tables` 改为 `profile_tables`,断言输出 dataset 含 `columns`。

## 验收
1. 给一个源 `get_data_source_schema` → 返回每表含列。
2. 无标注源 `list_datasets` → 自动列出的数据集带列。
3. 现有数据源/数据集测试仍全绿(更新 D 兜底测试)。

## 范围外
- 行数/样例行(perf;列已够。后续可选)。
- 数据集标注 UI(下一步)。
