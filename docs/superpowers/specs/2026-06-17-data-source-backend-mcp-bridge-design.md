# 数据源后端 + MCP 桥 设计文档

- **日期**:2026-06-17
- **状态**:已确认范围(手动同步 / 明文 JSONB / Postgres 优先 + SQLAlchemy 通用),待评审
- **范围**:落地建议 ①(后端 CRUD/test/sync)+ ②(MCP 桥 + 注册)+ ③(先打通 database/api)。插件框架(建议④)不在本次范围。
- **目标**:把「基本设置 → 数据源」tab 从前端空壳变成 **AI Agent 可真实取数**的模块。

---

## 1. 背景与现状

- 「数据源」tab 前端已完整(`frontend/src/extensions/data-source/`:Manager / Form / Card / api / types),但后端 `backend/app/extensions/data_source/routers.py` 是**桩**——只有 `GET ""` 返回空列表,无 create/update/delete/test/sync,无数据模型。
- harness 层(Agent 运行处)被 `tests/test_harness_boundary.py` 强制禁止 `import app.*`,因此 Agent **无法直接读** DataSource 表。扩展模块对 Agent 暴露能力的唯一合法通道是 **MCP**。
- 现成范例:`app/extensions/project/mcp.py` —— 独立 stdio MCP server,通过 `extensions_config.json → mcpServers.project` 注册(enabled),Agent 已能用其 `read_chapter` / `write_chapter` 工具。本设计照搬该结构。

## 2. 非目标(本次不做)

- scheduled / event 同步(不引入调度器;字段保留,handler 标记 TODO)。
- connection_config 加密(明文 JSONB,标记 P1 后续 Fernet 加密)。
- 多数据库引擎全量适配(MySQL/Oracle/MSSQL 等专项优化)。
- 插件框架(Plugin/PluginInstance 后端、动态注册 MCP)。
- 用户级数据源隔离(MCP 工具全局可见,对齐 project/mcp.py;后续可加 user 过滤)。

## 3. 架构

```
浏览器「数据源」tab  ──REST──►  data_source/routers.py  ──►  DataSource 表 (extensions DB)
        (CRUD/test/sync)            (get_db + 当前用户)            │
                                                                  │ 同库
                                                                  ▼
                                          data_source/mcp.py  ◄── get_extensions_config().database.url
                                                │ (stdio MCP server)
                                                ▼
                                    extensions_config.json → mcpServers.data_sources
                                                │ langchain-mcp-adapters
                                                ▼
                                    Agent 工具集:list/get_schema/query/test_data_source
                                                │
                                                ▼
                                    Agent 写报告时自主取数 → 写入章节
```

### 关键架构约束
- **harness/app 边界**:MCP server 是独立进程,在 handler 内**懒加载** `import app.*`(与 project/mcp.py 一致),从而绕过边界。
- **同库原则**:DataSource 表由 startup `Base.metadata.create_all`(`database.py:206`)创建在 **extensions DB**(agentflow / `eai-flow-postgres-ext`)。MCP server 必须连**同一个库**。**禁止**照抄 `PROJECT_DB_URL`(那是独立的 `project-db` 库,与 DataSource 表无关)。

## 4. 数据模型

新增 `DataSource` 类,加入 `backend/app/extensions/models/__init__.py`(与 `User` 同文件、同 `Base`、同 SQLAlchemy 2.0 typed 风格),启动时自动建表。

```
DataSource
  ├── id            UUID pk, default uuid4
  ├── name          String(200), not null
  ├── type          String(20), not null            # database | api | file | gis
  ├── connection_config  JSONB, not null, default {} # {host,port,database,username,password,...} 按类型
  ├── auth_type     String(20), default "none"       # none | basic | oauth | api_key | certificate
  ├── sync_mode     String(20), default "manual"     # manual | scheduled | event
  ├── sync_config   JSONB, nullable                  # 预留,本次不消费
  ├── status        String(20), default "disconnected" # connected | error | disconnected | testing
  ├── last_sync_at  DateTime, nullable
  ├── created_by    UUID → users.id, nullable        # 创建者
  ├── created_at    DateTime, default now()
  └── updated_at    DateTime, default now(), onupdate now()
```
- 字段命名与前端 `data-source/types.ts` 严格对齐(前端零改动):前端发 `connection_config` / `auth_type` / `sync_mode`,后端存同名列。
- 唯一性:`(created_by, name)` 加唯一约束,避免同用户重名(可后置,实现时确认)。

## 5. REST 端点(替换 `data_source/routers.py` 的桩)

前缀沿用 `/api/extensions/data-sources`(已在 `gateway/app.py:481` 注册 router)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `` | 列表(按当前用户过滤,或全量——实现时对齐 docmgr 权限) |
| POST | `` | 创建,返回 {id},前端再 GET 详情(对齐前端 `dataSourceApi.create` 逻辑) |
| GET | `/{id}` | 详情 |
| PATCH | `/{id}` | 更新;若 body 带 `status` 也允许更新状态 |
| DELETE | `/{id}` | 删除 |
| POST | `/{id}/test` | 测连接 → `{success, message, metadata?}` |
| POST | `/{id}/sync` | 触发手动同步 → 更新 `last_sync_at` + `status` |

- **认证**:复用扩展模块现有鉴权依赖(当前用户),实现时参照 `docmgr/routers.py` 或 `project/routers.py` 的 `Depends(...)` 写法。
- **DB**:`Depends(get_db)`。
- **请求/响应 Pydantic 模型**:对齐前端 `CreateDataSourceRequest` / `TestConnectionResult`。
- test 前把 `status` 置 `testing`,完成后置 `connected` / `error`。

## 6. test 连接实现(按 `type` 分发)

- **database**:由 `connection_config`({host,port,database,username,password} 可选 `driver`/`schema`)拼 SQLAlchemy URL,默认 `postgresql+asyncpg://...`(Postgres 优先);如 config 显式带 `driver`(如 `mysql+aiomysql`、`sqlite+aiosqlite`)则用之(SQLAlchemy 通用回退,缺驱动则报清晰错误)。执行 `SELECT 1`,成功 → connected。
- **api**:`httpx.AsyncClient` GET `connection_config.url`(可带 `headers` / `params` / auth 头),2xx → connected,4xx/5xx → error 并带回状态码。
- **file**:`Path(connection_config.path).exists()`。
- **gis**:检查 `connection_config.file_name` 非空(本次不做真实上传落盘校验,P1 补)。
- 所有分支:异常 → `success=False, message=str(e)`,不让请求 500。

## 7. 同步实现(MVP 手动)

- `POST /{id}/sync`:根据 type 做一次轻量"抽样"并更新 `last_sync_at`:
  - database:`SELECT count(*) FROM <第一张表/或 information_schema 统计>`,回填 `metadata.table_count` 之类(实现时定)。
  - api:GET 一次,记录响应大小。
  - file / gis:记录文件大小 / 存在性。
- `sync_mode = scheduled/event` 时:handler 记录"未实现"日志并正常返回(status 不变),不报错。前端已有 lastSyncAt 展示。

## 8. MCP 桥 — 新增 `app/extensions/data_source/mcp.py`

照搬 `project/mcp.py` 结构(`Server` + `stdio_server` + `list_tools` + `call_tool`,handler 内懒加载 `import app.*`,返回 `TextContent(json)`)。

### 暴露工具
| 工具 | 入参 | 作用 |
|---|---|---|
| `list_data_sources` | — | 列出所有数据源: id/name/type/status/last_sync_at |
| `get_data_source_schema` | `name` | database:返回库内表/字段概览(information_schema,限行);api:返回 url 与示例;file/gis:返回路径/文件名 |
| `query_data_source` | `name`, `params` | database:`params.sql` 执行**只读**查询(强制 SELECT,限 200 行);api:`params` 作为 query/headers 发 GET |
| `test_data_source` | `name` | 复用 §6 逻辑 |

### DB 连接(关键)
- handler 内 `from app.extensions.config import get_extensions_config`,用 `get_extensions_config().database.url` 建 short-lived engine + session(参考 project/mcp.py 的 `_run_in_db`,**但用 extensions 库 URL**)。
- 可选覆盖:若环境变量 `DATA_SOURCE_DB_URL` 存在则优先使用(预留显式注入位,默认不设)。
- **绝不用 `PROJECT_DB_URL`**。

### 🔒 只读安全约束(query_data_source)
- database 分支:对 `params.sql` 做保护——trim、转大写前缀必须是 `SELECT` 或 `WITH`;拒绝 `;` 后跟写操作;包 `LIMIT`(无则自动追加 `LIMIT 200`);使用只读事务 / 回滚。任何不满足 → 返回错误,不执行。
- api 分支:仅允许 GET。
- 失败/超时统一返回结构化错误,不抛崩 MCP 进程。

## 9. 注册

### `extensions_config.json` — `mcpServers` 增
```json
"data_sources": {
  "enabled": true,
  "type": "stdio",
  "command": "/app/backend/.venv/bin/python",
  "args": ["-m", "app.extensions.data_source.mcp"],
  "env": {},
  "cwd": "/app/backend",
  "url": null, "headers": {}, "oauth": null,
  "description": "External data source query tools for report writing agent"
}
```
- `env` 默认空:依赖 MCP 子进程继承 gateway 容器环境的 `EXTENSIONS_DB_*`(get_extensions_config 自动解析)。如继承失效再显式注入 `DATA_SOURCE_DB_URL`。

### 部署
- Docker 热重载:`docker compose -p eai-docker restart gateway` 后,新模型 create_all + 新 MCP server 生效。
- extensions_config.json 改动会被 mtime 热加载,无需额外动作。

## 10. 测试(TDD — 项目硬性要求)

`backend/tests/` 新增(参照现有 test 命名与 fixtures):
- `test_data_source_models.py` — 模型字段/默认值/JSONB 序列化。
- `test_data_source_routers.py` — CRUD 全流程 + test 连接各 type 分发(mock httpx/连接) + sync 更新 last_sync_at。用 ASGI/依赖覆盖 + 内存或事务回滚 DB。
- `test_data_source_mcp.py` — 4 个工具的返回结构 + **只读约束**(注入写 SQL 必须被拒、自动 LIMIT、非 SELECT 拒绝)。

## 11. 变更清单(预估)

新增:
- `backend/app/extensions/data_source/{service.py, mcp.py, schemas.py}`(routers.py 重写)
- `backend/tests/test_data_source_{models,routers,mcp}.py`

修改:
- `backend/app/extensions/models/__init__.py` — 加 `DataSource`
- `backend/app/extensions/data_source/routers.py` — 桩 → 完整实现
- `extensions_config.json` — 加 `data_sources` MCP server

不动:前端(已与字段对齐)。

## 12. 风险

| 风险 | 缓解 |
|---|---|
| MCP 连错库(误用 project-db) | 强制走 `get_extensions_config().database.url`;测试断言连到 agentflow 库 |
| Agent 经 query 误写/拖垮生产库 | §8 只读约束 + 自动 LIMIT + 只读事务 |
| 明文密码落库 | 本次接受(内部平台 + 鉴权),P1 加 Fernet |
| asyncpg 对非 postgres 引擎缺失 | SQLAlchemy 回退 + 缺驱动报清晰提示 |

---

## 13. 实现过程中的偏离(评审后调整)

1. **只读守卫增强(超出原 §8 描述,安全加固)**:实现评审发现 PostgreSQL 允许 data-modifying CTE(`WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d`),原"首词 SELECT/WITH + 禁 INTO + 禁多语句"无法拦截。故在 `assert_readonly_select` 增加整词写操作关键字扫描(`\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL)\b`);整词匹配避免对 `update_time`/`deleted_logs` 等标识符误报。已加 5 个回归测试(CTE 拦截 + 无误报)。
2. **查询执行加只读事务(defense-in-depth)**:`query_data_source` database 分支执行用户 SQL 前尝试 `SET TRANSACTION READ ONLY`(best-effort,失败回退到关键字守卫)。补齐 §8 "只读事务" 防御纵深。
3. **API 连接测试成功判定收窄为 2xx**:按 §6 "2xx → connected" 将 `200 <= status < 400` 收紧为 `< 300`。
4. **移除 `_run_in_db_probe` 死别名**:`get_data_source_schema` 直接复用 `_run_in_db`。
