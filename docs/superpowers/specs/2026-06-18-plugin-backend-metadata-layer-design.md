# 插件 tab 后端(元数据层)设计文档

- **日期**:2026-06-18
- **状态**:已确认范围(元数据层 / API Key 只发吊销),待评审
- **范围**:补齐「设置 → 插件」tab 的后端 —— 注册目录 + 实例装机 + API Key,**纯元数据,不执行代码、不接 MCP**。执行期(插件即 MCP 动态注册)留作下一期。
- **目标**:让插件 tab 的 3 个前端子 tab(市场/已安装/API密钥)从全 404 变为全部可用;与已落地的 data_source 后端保持一致的架构纪律。

---

## 1. 背景与现状

- 插件 tab 前端完整(`frontend/src/extensions/plugin/`:Marketplace + api + types + 3 组件),但后端**完全不存在** —— 前端调 `/api/extensions/plugins/{registry,instances,api-keys}` 全部 404。
- 对照:data_source tab 已用同一套模式建好后端(model + CRUD + MCP 桥,已落地、51 测试通过)。本设计**镜像 data_source**,但**不含 MCP**(插件本期不执行)。
- spec 原型见 `docs/superpowers/specs/2026-05-21-report-platform-feature-design.md` §4(Plugin/PluginInstance/ApiKey 模型 + 功能清单 + 预置插件)。

## 2. 非目标(本期不做)

- 插件执行 / entry_point 调用 / 沙箱(不做;纯元数据)。
- 插件即 MCP 动态注册(不做;data_source 已覆盖"Agent 取数据")。
- API Key 鉴权中间件(只发/吊销,不接入任何端点校验)。
- Webhook 订阅(spec P2,不做)。
- 管理员上传/注册插件端点(本期靠预置;YAGNI)。
- 项目级实例隔离(本期恒全局,`project_id` 存 null)。
- 前端改动(6 文件已完整,字段与本设计一致)。

## 3. 架构

```
浏览器「插件」tab  ──REST──►  plugin/routers.py  ──►  Plugin / PluginInstance / ApiKey 表 (extensions DB)
   (registry/instances/api-keys)   (get_db + get_current_user)            │
                                                                         │ startup seed_db()
                                                                         ▼
                                                          plugin/seed.py::seed_builtin_plugins()
                                                          (预置 4 个内置插件 → 市场)
```

- 模型加进 `backend/app/extensions/models/__init__.py`(与 User/DataSource 同 Base、同风格),startup `Base.metadata.create_all` 自动建表。
- 路由 prefix `/api/extensions/plugins`,在 `gateway/app.py` 注册。
- 鉴权/DB:复用 `get_current_user` + `get_db`(同 data_source)。
- config 校验:`jsonschema` 库(已确认在依赖中)按 `plugin.config_schema` 校验实例 config。

## 4. 数据模型(3 张表,加进 `models/__init__.py`)

### Plugin(注册目录)
```
id(UUID pk) · name(str 200) · type(str 20: data_connector|tool|output|custom)
version(str 50) · author(str 200, nullable) · description(text, nullable)
config_schema(JSONB nullable, JSON Schema 驱动前端表单) · entry_point(str 500 nullable, 留给未来执行期)
icon(str 100 nullable) · permissions(JSONB default []) · status(str 20 default "registered")
created_at · updated_at
```
- 唯一约束:`(name, version)`。

### PluginInstance(已安装实例)
```
id(UUID pk) · plugin_id(FK plugins) · plugin_name(str 200 冗余) · plugin_type(str 20 冗余)
project_id(UUID FK projects nullable, 本期恒 null) · config(JSONB default {})
status(str 20 default "disabled": active|error|disabled) · last_sync_at(DateTime nullable)
created_by(FK users nullable) · created_at · updated_at
```
- 冗余 `plugin_name`/`plugin_type`:前端列表直接展示,免 join(对齐前端 `PluginInstance` 类型)。

### ApiKey
```
id(UUID pk) · name(str 200) · key_prefix(str 16 展示用) · key_hash(str 128 只存哈希)
scope(JSONB default []) · project_id(UUID nullable) · created_by(FK users nullable)
expires_at(DateTime nullable) · last_used_at(DateTime nullable) · created_at
```
- 明文 key **仅创建时返回一次**,DB 只存 `key_hash`(sha256)与 `key_prefix`(前 8 位,展示用 `xxxx` 形式)。

## 5. REST 端点(prefix `/api/extensions/plugins`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/registry` | 目录列表(市场)。响应 `{items:[Plugin...]}` |
| GET | `/registry/{id}` | 详情(含 config_schema) |
| GET | `/instances?project_id=` | 已安装实例列表。响应 `{items:[PluginInstance...]}` |
| POST | `/instances` | 安装:body `{plugin_id, project_id?, config}`;config 按 `plugin.config_schema` 校验;冗余写 name/type;实例 `status="active"`(装即启用);返回实例 |
| PATCH | `/instances/{id}` | 改 `config` 和/或 `status`(启用/禁用)。body 部分字段 |
| DELETE | `/instances/{id}` | 卸载 |
| GET | `/api-keys` | 列表(只回 prefix/scope/时间,**不回明文**)。响应 `{items:[ApiKey...]}` |
| POST | `/api-keys` | 创建:body `{name, scope?, project_id?, expires_at?}` → 返回 `{id, key}`(明文仅此一次) |
| DELETE | `/api-keys/{id}` | 吊销 |

- 全部端点 `Depends(get_current_user)`(已登录即可,不做细粒度权限,对齐 data_source)。
- 字段命名 snake_case,与前端 `api.ts` 映射一致(前端已做 snake↔camel)。

## 6. config 校验

- `PluginService.validate_config(plugin, config)`:若 `plugin.config_schema` 非空,用 `jsonschema.validate(config, schema)`;失败抛 `HTTPException(400, detail=错误信息)`。
- 无 schema → 不校验,直接存。
- 前端 `PluginConfigForm` 已据 schema 渲染表单,服务端校验是第二道防线。

## 7. 预置插件(seed)

- 新增 `app/extensions/plugin/seed.py::seed_builtin_plugins(db)`,在 `database.py::seed_db()` 内调用(参照 `output.seed.seed_builtin_templates` 的挂法,line ~1327)。
- 预置 4 个(spec §4.3),`status="registered"`:
  | name | type | 说明 | config_schema |
  |---|---|---|---|
  | 地质数据连接器 | data_connector | 对接地质钻孔数据库,拉取地层信息 | {host,port,database} |
  | 环境监测连接器 | data_connector | 对接在线监测平台,获取实时数据 | {url} |
  | CAD 文件预览 | tool | 解析 DWG/DXF,生成预览图和元数据 | {file_path} |
  | GIS 数据可视化 | tool | 加载 Shapefile/GeoJSON,嵌入地图 | {layer_url} |
- 幂等:按 `(name, version)` upsert,重启不重复。

## 8. API Key 哈希

- 创建:`secrets.token_urlsafe(32)` 生成明文 key;`key_prefix = key[:8]`;`key_hash = sha256(key).hexdigest()`;只存 hash+prefix,返回明文一次。
- 列表/展示只用 `key_prefix`(如 `aB3k…`)。
- 本期无任何端点校验 key(纯发放);校验中间件留作下一期。

## 9. 文件结构

新增:
- `backend/app/extensions/plugin/{__init__,schemas,service,routers,seed}.py`
- `backend/tests/test_plugin_{models,service,routers}.py`

修改:
- `backend/app/extensions/models/__init__.py` — 加 `Plugin`/`PluginInstance`/`ApiKey`
- `backend/app/extensions/database.py` — `seed_db()` 内加 `seed_builtin_plugins(session)` 调用
- `backend/app/gateway/app.py` — 注册 plugin router

不动:前端 6 文件。

## 10. 测试(TDD)

- `test_plugin_models.py` — 3 模型默认值/字段/表名(纯单元)。
- `test_plugin_service.py` — config 校验(有 schema 通过/失败、无 schema 放行)、安装(name/type 冗余)、API Key 哈希(明文不存、prefix、hash 可校验)、seed 幂等。
- `test_plugin_routers.py` — 端点 via dependency_overrides + AsyncClient(对齐 data_source 路由测试):registry 列表、install 201 + config 校验 400、PATCH 启停、api-key 创建返回明文一次 + 列表不含明文 + 吊销。

## 11. 风险

| 风险 | 缓解 |
|---|---|
| 预置插件无执行能力,装机后"什么都不发生" | 本期即设计如此(元数据层);UI 状态/配置真实可用,执行期留下一期。文档说明 |
| API Key 发了但没人校验 | 本期即设计如此;明文仅创建时返回、只存 hash,安全基线达标;校验中间件下一期 |
| seed 与 create_all 顺序 | seed 在 `seed_db()` 内、建表之后执行(参照 output seed 挂法);幂等 upsert |
| jsonschema 校验过严拒合法 config | 只在 plugin 自带 config_schema 时校验;错误信息回传前端 |
