# Warm-Flow → EAI-Flow 工作流子系统复刻设计

> 目标：在 `D:\eai\eai-flow-main\workflow` 下，用 **FastAPI + SQLAlchemy async + Pydantic** 和 **Next.js App Router + React 19 + TypeScript + Tailwind + shadcn + TanStack Query**，一比一复刻 `D:\eai\warm-flow-master` 的流程定义管理、经典设计器、流程图、表单与运行时审批语义。
>
> 本目录是**独立子系统**，与 `backend/app/extensions/workflow`（基于 Temporal 的 DAG 报告工作流）以及 `frontend/src/app/workflow-admin` **不共享数据模型、不复用表、不覆盖代码**。

---

## 1. 源系统盘点

### 1.1 模块清单

| 源模块 | 路径 | 职责 | 复刻位置 |
|---|---|---|---|
| Core | `warm-flow-core` | 引擎门面、实体、DTO、枚举、服务、条件/办理人/监听器策略、流程图元数据 | `backend/app/engine` |
| ORM | `warm-flow-orm` | MyBatis-Plus / JPA 等 DAO 适配 | `backend/app/models.py` + SQLAlchemy |
| Plugin UI | `warm-flow-plugin/warm-flow-plugin-ui` | 设计器与运行时 REST 控制器 | `backend/app/api/*` |
| Vue Designer | `warm-flow-vue-designer` | LogicFlow 画布、属性面板、经典节点 | `frontend/src/components/workflow/designer` |
| Demo | `warm-flow-designer-demo` | 集成示例、接口实现样例 | `frontend` 页面与演示数据 |
| SQL | `sql/mysql/warm-flow-all.sql` | 表结构 | `sql/001_workflow_mysql.sql` |

### 1.2 核心类映射

| Java | 说明 | Python |
|---|---|---|
| `FlowEngine` | 静态门面，持有各 Service 与策略 | `engine/definition.py` + `engine/runtime.py`（按领域拆分，无单例门面） |
| `DefService(Impl)` | 定义保存、发布、复制、导入导出、校验 | `engine/definition.py` |
| `InsService(Impl)` | 启动流程、实例挂起/激活、变量 | `engine/runtime.py::start_instance` |
| `TaskService(Impl)` | 通过/退回/撤销/终止/转办/委派/加减签/会签票签 | `engine/runtime.py::*` |
| `NodeService(Impl)` | 下一节点、网关判定、前驱/后继 | `engine/graph.py` |
| `ChartService(Impl)` | 流程图三原色与节点/边状态 | `engine/chart.py` |
| `HisTaskService` / `UserService` | 历史任务、办理人权限 | `engine/runtime.py` |
| `DefJson` / `NodeJson` / `SkipJson` | 设计器 JSON 契约 | `schemas.py` |
| `ExpressionUtil` + Condition/Handler 策略 | `eq@@flag|4`、`${handler}` | `engine/expression.py` |

### 1.3 设计器数据流（源系统）

```
Vue FlowDesigner
  ├─ queryDef(definitionId)                → GET  /warm-flow/query-def/{id}
  ├─ json2LogicFlowJson(DefJson)           → LogicFlow nodes/edges
  ├─ 拖拽/连线/属性面板修改
  ├─ logicFlowJsonToWarmFlow(graph)        → DefJson(JSON string)
  └─ saveJson(defJson, onlyNodeSkip)       → POST /warm-flow/save-json
```

- 节点坐标：`x,y|textX,textY`。
- 边坐标：`x1,y1;x2,y2|textX,textY`。
- 节点类型映射：`0=start, 1=between, 2=end, 3=serial, 4=parallel, 5=inclusive`。
- 边固定 `type=skip`，`sourceNodeId=nowNodeCode`，`targetNodeId=nextNodeCode`。
- `ext` 在存储层是 JSON 字符串（`[{code,value}]`），在 LogicFlow 中展开为 `properties.ext` 对象。
- `chartStatusColor` 为三原色数组：`[已办RGB, 待办RGB, 未办RGB]`。

### 1.4 运行时接口（源系统）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/warm-flow/save-json` | 设计器保存；Header `onlyNodeSkip` |
| GET | `/warm-flow/query-def/{id}` | 定义 + 节点 + 跳转 |
| GET | `/warm-flow/query-flow-chart/{id}` | 按实例渲染流程图 |
| GET | `/warm-flow/handler-type` | 办理人页签（用户/角色/部门） |
| GET | `/warm-flow/handler-result` | 办理人分页数据 |
| GET | `/warm-flow/handler-feedback` | 办理人名称回显 |
| GET | `/warm-flow/handler-dict` | 办理人字典 |
| GET | `/warm-flow/published-form` | 已发布表单 |
| GET/POST | `/warm-flow/form-content[/{id}]` | 读取/保存表单内容 |
| GET | `/warm-flow/execute/load/{taskId}` | 待办表单与数据 |
| GET | `/warm-flow/execute/hisLoad/{id}` | 已办表单与数据 |
| POST | `/warm-flow/execute/handle` | 通用审批 |
| GET | `/warm-flow/node-ext` | 节点扩展属性定义 |
| GET | `/warm-flow/listener-list` | 监听器列表 |

---

## 2. 数据模型

保留 warm-flow 的 8 张核心表，不做“现代化重命名”，以保证导入导出、设计器 JSON 和既有数据可直接迁移。

### 2.1 `flow_definition`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | 雪花 ID |
| flow_code | VARCHAR(40) | 流程编码，业务唯一键 |
| flow_name | VARCHAR(100) | 流程名称 |
| model_value | VARCHAR(40) | `CLASSICS` |
| category | VARCHAR(100) | 分类 |
| version | VARCHAR(20) | 同 code 递增版本 |
| is_publish | TINYINT | 0 未发布 / 1 已发布 / 9 失效 |
| form_custom | CHAR(1) | Y/N |
| form_path | VARCHAR(100) | 表单标识（如 `formCode:version`） |
| activity_status | TINYINT | 0 挂起 / 1 激活 |
| listener_type/path | VARCHAR | 全局监听器 |
| ext | VARCHAR(500) | 业务扩展 JSON |
| 审计/租户/删除 | | create_time/by、update_time/by、tenant_id、del_flag |

### 2.2 `flow_node`

`node_type`、`definition_id`、`node_code`、`node_name`、`permission_flag`、`node_ratio`、`coordinate`、`any_node_skip`、`listener_type/path`、`form_custom/path`、`ext`、`version`、审计字段。

- `permission_flag`：`@@` 分隔的办理人存储 ID（源系统由 `UserService` 拆分）。
- `node_ratio`：`0`=或签；`100`=会签；`(0,100)`=票签通过率；`passCount=N`、`rejectCount=N`、`default@@...`、`spel@@...`、`...@@sequence`。
- `any_node_skip`：退回时允许任意跳转的目标节点编码。

### 2.3 `flow_skip`

`definition_id`、`now_node_code`、`now_node_type`、`next_node_code`、`next_node_type`、`skip_name`、`skip_type`（PASS/REJECT/NONE）、`skip_condition`、`coordinate`。

### 2.4 `flow_instance`

`definition_id`、`business_id`、`node_type/code/name`、`variable`(JSON)、`flow_status`、`activity_status`、`def_json`（启动时快照）、`ext`。

> `def_json` 是流程图与运行中定义解耦的关键：除 `nodeList/skipList` 外，Phase 1
> 还在 `formSnapshot` 中冻结所有被引用表单的内容。任务加载、审批推进、撤销/终止
> 都从该快照读取，定义或表单后续修改不影响在途实例。

### 2.5 `flow_task`

`definition_id`、`instance_id`、`node_code/name/type`、`flow_status`、`form_custom/path`。

### 2.6 `flow_his_task`

`definition_id`、`instance_id`、`task_id`、`node_code/name/type`、`target_node_code/name`、`approver`、`cooperate_type`、`collaborator`、`skip_type`、`flow_status`、`message`、`variable`、`ext`、`form_custom/path`。

### 2.7 `flow_user`

`type`（1 审批人 / 2 转办人 / 3 委托人）、`processed_by`、`associated`（task id）。

### 2.8 `flow_form`

`form_code`、`form_name`、`version`、`is_publish`、`form_type`（0 内置 / 1 外挂）、`form_content`、`form_path`、`ext`。

### 2.9 `flow_command`

`instance_id`、`task_id`、`command_type`、`actor`、`payload`(JSON)、`claims`(JSON)、`status`、`idempotency_key`（唯一）、`workflow_id/run_id`、`attempts`、`available_at`、`error_code`、`result`。

状态：`PENDING → DISPATCHING → DISPATCHED → APPLIED`；失败为 `FAILED`，实例结束时未处理命令为 `CANCELLED`。

### 2.10 `flow_instance_runtime`

`instance_id`(PK)、`workflow_id`（唯一）、`run_id`、`engine`、`status`、`started_at`、`last_sync_at`、`completed_at`、`last_error`。

Workflow id 固定为 `flow-instance-{instance_id}`，便于 Dispatcher/Reconciler 幂等补启动。

### 2.11 `flow_outbox`

`instance_id`、`command_id`、`event_type`、`aggregate_type/id`、`payload`(JSON)、`status`、`dedupe_key`（唯一）、`attempts`、`available_at`、`delivered_at`。

状态：`PENDING → SENDING → SENT`；未配置 Webhook 时为 `SKIPPED`；重试耗尽为 `FAILED`。

---

## 3. 枚举与状态机

### 3.1 节点类型 `NodeType`

| key | value | 含义 |
|---|---|---|
| 0 | start | 开始节点 |
| 1 | between | 审批节点 |
| 2 | end | 结束节点 |
| 3 | serial | 互斥网关 |
| 4 | parallel | 并行网关 |
| 5 | inclusive | 包容网关 |

### 3.2 流程状态 `FlowStatus`

| key | 含义 | key | 含义 |
|---|---|---|---|
| 0 | 待提交 | 7 | 取回 |
| 1 | 审批中 | 8 | 已完成 |
| 2 | 审批通过 | 9 | 已退回 |
| 3 | 自动完成 | 10 | 失效 |
| 4 | 终止 | 11 | 拿回 |
| 5 | 作废 | 12 | 重启 |
| 6 | 撤销 | 13 | 暂存 |

实现中状态流转规则：

- 启动：实例 `0`（或调用方指定），首个任务 `1`。
- 通过到结束节点：实例、任务、历史任务均为 `8`。
- 退回申请人：实例 `9`，开始节点生成申请人任务 `1`，退回历史任务 `9`；原实例、原流程编号和定义快照均保留。
- 退回上一审批节点（`rejectLast`）：实例 `9`，目标任务 `1`，历史任务 `9`。
- 撤销：实例 `6`，清空待办并写历史。
- 终止：实例 `4`。
- 挂起：实例 `activity_status=0`；挂起时禁止审批。

### 3.3 发布状态 `PublishStatus`

`0` 未发布、`1` 已发布、`9` 已失效。

发布算法与源系统一致：

1. 同一 `flow_code` 只允许一个 `is_publish=1`。
2. 旧版本若已产生实例 → 置 `9`；未产生实例 → 置 `0`。
3. 无节点禁止发布。
4. 删除定义前检查实例；有实例禁止删除。
5. 取消发布仅允许在无实例时执行。

### 3.4 协作类型 `CooperateType`

`1` 审批、`2` 转办、`3` 委派、`4` 会签、`5` 票签、`6` 加签、`7` 减签。

### 3.5 流程图状态 `ChartStatus`

`0` 未办、`1` 待办、`2` 已办。三原色按经典模式色板取色。未办节点与连线统一显示为灰色；已实际走过的退回/驳回连线也记为已办，并以红色虚线展示。销售审批流程从每个审批节点分出两条 `REJECT` 边：`step_n → end` 表示终态“驳回”，`step_n → start` 表示“退回申请人修改”。两条边在未走过时均为灰色，只有实际走过的边变红。旧实例快照中退回连线仍为 `0` 时，构建流程图会按 `flow_his_task` 的 `REJECT` 目标节点回填对应边的已办状态，避免历史实例把已走过的退回路径画成灰色。

---

## 4. 运行时算法

### 4.1 启动 `start`

```
校验 flowCode / businessId / 已发布定义 / 激活状态 / 开始节点
→ 取 start 的 PASS 后继（自动穿透网关）
→ 创建 instance（node=首个目标节点，def_json=全图 + 表单快照）
→ 首节点写历史（approver=发起人，skip=PASS，status=0/1/8）
→ 为目标节点创建 task
→ 解析 permission_flag → 写入 flow_user（type=1）
```

### 4.2 审批 `skip / pass / reject`

```
锁定 task → 校验实例激活、任务归属、办理人权限
→ 合并流程变量
→ 会签/票签判定（未达成则只写当前人历史并删其权限，返回）
→ 计算下一节点（PASS/REJECT；指定 node_code；any_node_skip）
→ 网关递归展开（互斥/并行/包容）
→ 当前 task 转历史
→ 新 task + flow_user
→ 更新实例位置与状态；结束节点则完成
→ 撤回/退回时重置流程图状态
```

### 4.2.1 退回申请人 `returnToApplicant`

```
锁定 task → 校验实例激活、任务归属、办理人权限 → 合并流程变量
→ 当前节点必须不是 start/end
→ 在实例冻结快照中查找或补写 step_n → start 的 REJECT 边（上方回路）
→ 标记当前节点未办、退回边已办、start 待办
→ 当前 task 转历史（target=start，flow_status=9）
→ 移除同实例其他待办并写失效历史
→ 在 start 节点创建申请人任务（assignee=instance.create_by，flow_status=0）
→ 实例 node=start，flow_status=9
```

申请人办理该 start 任务（`approve`）时复用同一实例，`handle_task` 从 start 的 PASS 后继重新路由到第一步，sales 审批单号不变。只有 `REJECT` 边允许指向开始节点；普通 PASS/网关跳转仍禁止回到 start。

### 4.3 网关

- **互斥网关**：按跳转顺序取第一条条件成立的分支；无条件分支作为默认。
- **并行网关**：所有无条件分支都走。
- **包容网关**：条件成立的分支 + 无条件分支。
- 条件表达式：
  - `eq@@flag|4`、`ne@@`、`gt@@`、`ge@@`、`lt@@`、`le@@`、`like@@`、`notLike@@`
  - `spel@@#{...}`：本复刻使用受限表达式求值，仅支持变量比较/布尔组合，禁止任意代码执行。
  - `default@@...`：无条件命中。

### 4.4 或签 / 会签 / 票签

- `node_ratio=0`：或签，一人通过即流转，其余待办权限删除。
- `node_ratio=100`：会签，全部办理人通过才流转；任一驳回按策略立即退回（可配置）。
- `0<ratio<100`：票签通过率。
- `passCount=N` / `rejectCount=N`：固定人数。
- `@@sequence`：顺签，只给第一个办理人生成待办。

### 4.5 其他动作

| 动作 | 语义 |
|---|---|
| 撤销 revoke | 发起人撤回审批中的实例，回到开始节点，状态 6 |
| 终止 terminate | 强制结束实例，状态 4 |
| 转办 transfer | 当前办理人把任务转给他人，原权限删除，type=2 |
| 委派 depute | 委托他人处理，处理后回到委托人，type=3 |
| 加签 addSignature | 增加审批人，type=1 |
| 减签 reduceSignature | 移除审批人（至少保留一人） |
| 退回申请人 returnToApplicant | 同一实例退回到 start，创建申请人任务；申请人重新提交后从第一步重新审批 |
| 退回 rejectLast | 退回到上一个审批节点 |
| 拿回 taskBack | 从历史中拿回自己最近一次已办 |

---

## 5. 目标 API 契约

统一前缀：**`/api/workflow`**。响应直接返回资源对象，错误使用 `{"detail": "..."}`（与 eai-flow 一致）。

### 5.1 定义管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/definitions` | 分页：`page,size,flowCode,flowName,category,isPublish` |
| POST | `/definitions` | 新建定义（仅元数据） |
| GET | `/definitions/{id}` | 详情（含节点/跳转） |
| PUT | `/definitions/{id}` | 更新元数据 |
| DELETE | `/definitions/{id}` | 删除（有实例则 409） |
| POST | `/definitions/{id}/publish` | 发布 |
| POST | `/definitions/{id}/unpublish` | 取消发布 |
| POST | `/definitions/{id}/copy` | 复制新版本 |
| POST | `/definitions/{id}/activate` | 激活 |
| POST | `/definitions/{id}/suspend` | 挂起 |
| GET | `/definitions/{id}/export` | 导出 DefJson |
| POST | `/definitions/import` | 导入 DefJson |

### 5.2 设计器兼容接口

保持与 warm-flow 控制器同名，前端移植成本最低：

```
POST /designer/save-json              Header: onlyNodeSkip
GET  /designer/query-def[/{id}]
GET  /designer/query-flow-chart/{instanceId}
GET  /designer/handler-type
GET  /designer/handler-result
GET  /designer/handler-feedback
GET  /designer/handler-dict
GET  /designer/published-form
GET  /designer/form-content/{id}
POST /designer/form-content
GET  /designer/execute/load/{taskId}
GET  /designer/execute/hisLoad/{hisTaskId}
POST /designer/execute/handle
GET  /designer/node-ext
GET  /designer/listener-list
```

### 5.3 运行时

```
POST /instances                       启动
GET  /instances                       分页查询
GET  /instances/{id}                  实例详情 + 流程图
POST /instances/{id}/revoke           撤销
POST /instances/{id}/terminate        终止
GET  /tasks                           待办（assignee/instanceId）
GET  /tasks/{id}                      待办详情 + 表单
POST /tasks/{id}/approve              通过（start 任务上表示申请人重新提交）
POST /tasks/{id}/reject               驳回（可显式指定目标节点）
POST /tasks/{id}/return-to-applicant  退回申请人（同一实例）
POST /tasks/{id}/reject-last          退回上一个审批节点
POST /tasks/{id}/transfer             转办
POST /tasks/{id}/depute               委派
POST /tasks/{id}/add-signature        加签
POST /tasks/{id}/reduce-signature     减签
GET  /history                         已办
```

### 5.4 表单与元数据

```
GET/POST      /forms
GET/PUT/DELETE/forms/{id}
POST          /forms/{id}/publish
GET           /meta/enums            枚举、状态色、节点尺寸
GET           /health
```

---

## 6. 前端设计

### 6.1 路由

| 路由 | 页面 |
|---|---|
| `/workflow` | 定义列表、发布/复制/删除/导入导出 |
| `/workflow/design/[id]` | 经典流程设计器（新建用 `new`） |
| `/workflow/tasks` | 我的待办 + 审批弹窗 |
| `/workflow/instances` | 实例列表 |
| `/workflow/instances/[id]` | 实例详情 + 流程图 + 历史 |
| `/workflow/forms` | 表单管理 |

### 6.2 设计器组件

```
components/workflow/designer/
  FlowDesigner.tsx        画布容器、LogicFlow 生命周期、保存
  DesignerToolbar.tsx     缩放、撤销、保存、导出
  DesignerSidebar.tsx     经典模式节点面板
  NodePropertyPanel.tsx   节点/边属性抽屉
  HandlerPicker.tsx       办理人选择（用户/角色/部门）
  FormPicker.tsx          表单选择
  graph.ts                DefJson ⇄ LogicFlow 转换
  nodeRegistry.ts         节点样式与默认属性
  types.ts
```

### 6.3 设计器策略

- **CLASSICS**：LogicFlow 自由画布，拖拽矩形节点，正交/折线连接，完整属性面板。保留源系统的节点语义色、状态色、坐标格式。
- 仿钉钉（`MIMIC`）模式已移除，系统只保留经典画布；历史 `MIMIC` 定义在迁移时归一为 `CLASSICS`，并按已保存坐标直接打开。

### 6.4 状态与请求

- TanStack Query 管理服务端状态：`['definitions']`、`['definition', id]`、`['tasks']`、`['instances']`。
- 设计器本地状态用 `useReducer`，保存时统一序列化。
- 所有请求通过 `lib/api.ts`，`NEXT_PUBLIC_WORKFLOW_API` 可指向独立后端。
- 表单使用受控 JSON Schema 渲染器（内置字段：input/textarea/number/select/date/switch），外挂表单仅存路径。

---

## 7. 鉴权、租户与隔离

- `WORKFLOW_AUTH_MODE=local`：信任 `X-User-Id`、`X-User-Name`、`X-User-Roles`、
  `X-User-Dept` 请求头，用于演示与测试。
- `WORKFLOW_AUTH_MODE=eai`：从 `Authorization: Bearer` 或 `access_token` Cookie
  校验共享 JWT，再以该 token 调用 Gateway `/api/permissions/me`，得到权威
  `user_id/role_code/dept/permissions/is_admin`；身份与权限按 60 秒 TTL 缓存。
- `RequestContext.claims` 同时包含角色、权限与部门；管理员获得 `*`，可办理任意待办。
- `GET /api/workflow/meta/me` 返回当前主体，前端据此隐藏演示身份切换器。
- 所有表保留 `tenant_id`，查询默认按租户过滤。
- `del_flag='0'` 软删除。
- **隔离边界**：
  - 不复用 `app.extensions.workflow` 的 `workflow_*` 表。
  - 不复用 `workflow-admin` 的 DAG 节点/边模型。
  - 新表统一 `flow_*` 前缀，与 warm-flow 原表一致，可直接迁移。
  - 独立 FastAPI 应用，可单独部署，也可在主网关以 `include_router` 挂载。

---

## 8. 迁移与实施阶段

### Phase 0（已完成）
- 目录骨架、设计文档、SQL、后端引擎与 API、前端页面与设计器、pytest、README。

### Phase 1（已完成）
- Alembic 初始迁移；生产 `WORKFLOW_AUTO_CREATE_SCHEMA=0`，SQLite 演示保留自动建表。
- EAI JWT/权限认证与 `meta/me`；前端同源 Cookie 请求。
- 实例启动时冻结定义图与表单内容；运行态全部读取快照。
- 前端迁到根路由组 + `basePath=/workflow`；nginx 统一 `/workflow/` 与
  `/workflow/api/`；Compose 覆盖文件接入 PostgreSQL/Temporal/Worker。

### Phase 2（本次交付）
- 通用 `FlowInstanceWorkflow`：每实例一个长期 Workflow，命令通过 signal 进入。
- `flow_command` 幂等命令收件箱；`flow_instance_runtime` 绑定 Temporal；
  `flow_outbox` 与领域变更同事务提交。
- `apply_command_activity` 在一个事务内完成 runtime 变更 + 命令 APPLIED +
  Outbox 事件；Activity/信号重试幂等。
- 独立 `workflow-dispatcher`：信号投递、Webhook Outbox 投递、定时对账。
- Reconciler 修复卡住的 DISPATCHING/DISPATCHED 命令、缺失 Workflow、
  Temporal 终态与 Outbox SENDING 状态。
- 本地 Temporal + PostgreSQL 完成启动 → 两级审批 → 完成链路验证。

### Phase 3
- 营销 BFF 从现有 sales Temporal 审批链路切换到 workflow 平台。
- 监听器 SPI（HTTP/MQ/脚本）；SpEL 子集完善。
- 移动端适配；表单设计器拖拽。
- 并行网关汇聚计数持久化、分布式锁、事件溯源、性能压测。

### 数据迁移
1. 导出 warm-flow `flow_*` 8 表。
2. 保持字段名与类型，直接导入本系统。
3. 校验 `flow_definition.version` 与 `flow_node.version` 一致。
4. 用 `designer/query-def` 抽样比对 JSON。

---

## 9. 测试计划

| 层级 | 内容 |
|---|---|
| 单元 | 条件表达式、坐标转换、版本号、网关分支 |
| 服务 | 保存/发布/失效/复制/删除保护 |
| 运行时 | 启动、通过、退回、或签、会签、票签、撤销、终止、转办 |
| API | 设计器 save-json 幂等、onlyNodeSkip、流程图状态 |
| 迁移 | Alembic 在 SQLite/PostgreSQL 建表，`alembic check` 无差异 |
| 认证 | `local` 头身份、EAI JWT、权限缓存、全局路由保护 |
| 快照 | 定义/表单修改不影响在途任务、审批路径与历史表单 |
| 命令 | `Idempotency-Key` 重复提交不重复审批；失败命令记录错误码 |
| Outbox | 同事务事件、注入 sender 投递、失败退避、终态 SENT/SKIPPED |
| Dispatcher | signal 成功/失败、stale 命令重新入队、终态命令取消 |
| E2E | 新建→设计→发布→启动→审批→完成→流程图；nginx 页面/API/静态资源 |
| Temporal E2E | 真实 Temporal：启动→两级审批→Workflow 终态→Reconciler 回填 |

---

## 10. 验收标准

1. 8 张表字段与 warm-flow DDL 对齐，可直接导入导出。
2. `save-json` 能完整往返 `DefJson`，节点/边坐标不丢失。
3. 发布规则、版本递增、失效规则与源系统一致。
4. 只保留经典设计器，DefJson 节点/边坐标可完整往返。
5. 或签/会签/票签/退回/撤销/转办行为可复现。
6. 流程图按实例展示已办/待办/未办三态。
7. 独立启动：`uvicorn app.main:app` + `pnpm dev`，不依赖主站即可演示。

---

## 11. 已知差异（有意为之）

| 项 | 源系统 | 本复刻 | 原因 |
|---|---|---|---|
| SpEL | Spring EL 全量 | 安全子集 | 避免任意代码执行 |
| 监听器 | Java SPI/Spring Bean | HTTP Webhook + 注册表 | 跨语言 |
| 表单设计器 | 内置拖拽设计器 | JSON Schema 编辑器 + 预览 | 一期聚焦流程 |
| 租户 | 插件注入 | 请求头/中间件 | 独立部署 |

---

## 12. 目录说明

```
workflow/
├─ backend/
│  ├─ alembic/           # 初始迁移与 alembic.ini
│  ├─ app/
│  │  ├─ api/            # definitions / designer / runtime / forms / meta
│  │  ├─ engine/         # enums / expression / graph / definition / runtime / chart / commands
│  │  ├─ temporal/       # FlowInstanceWorkflow / activities / dispatcher / reconciler
│  │  ├─ models.py       # 8 张 warm-flow 表 + command/runtime/outbox
│  │  ├─ schemas.py      # Pydantic（camelCase 别名）
│  │  ├─ database.py     # async engine / session / init / health
│  │  ├─ config.py
│  │  ├─ deps.py         # local / EAI JWT 身份
│  │  └─ main.py
│  └─ tests/
├─ frontend/
│  └─ src/
│     ├─ app/(workflow)/ # 列表、设计器、待办、实例、表单（basePath=/workflow）
│     ├─ components/     # ui + designer
│     └─ lib/            # api / types / utils
├─ sql/
└─ docs/
```
