# 营销平台接入复刻版 Workflow 并下沉 Temporal 集成方案

- 文档日期：2026-10-24
- 适用范围：`business/sales-service`、`workflow/`、`docker/`
- 目标：营销平台调用复刻版 workflow 的**已发布工作流定义和表单**；复刻版 workflow 的运行时编排由 **Temporal** 承担；营销平台不再直接维护审批流程状态机。

---

## 1. 现状与问题

### 1.1 当前营销审批链路

```text
营销前端
  -> sales-backend /approvals
  -> sales DB: approval_requests + outbox_events
  -> sales-worker Outbox dispatcher
  -> Temporal: SalesApprovalWorkflow
  -> sales-approval-queue
  -> Activity 回写 sales DB
```

关键代码：

- `business/sales-service/backend/app/approval_service.py`
- `business/sales-service/backend/app/workflows/dispatcher.py`
- `business/sales-service/backend/app/workflows/workflow.py`
- `business/sales-service/backend/app/worker.py`

### 1.2 当前复刻版 workflow

```text
workflow-frontend (Next.js)
  -> workflow-backend FastAPI
  -> workflow DB (SQLite/PostgreSQL)
  -> engine/runtime.py 进程内状态机
```

关键代码：

- `workflow/backend/app/api/runtime.py`
- `workflow/backend/app/engine/runtime.py`
- `workflow/backend/app/models.py`
- `workflow/frontend/src/components/workflow/form-renderer.tsx`

### 1.3 当前缺口

1. 营销平台没有调用 `workflow/`，也没有 workflow 平台客户端。
2. `workflow/` 没有 Temporal 依赖、Client、Worker、Task Queue。
3. 两套系统各自维护审批状态，定义、表单、实例、任务没有统一来源。
4. 复刻版使用本地数据库事务直接推进流程，无法获得 Temporal 的持久化 Timer、Signal、Activity 重试、History Replay 和分布式 Worker 能力。

---

## 2. 目标架构

### 2.1 总体拓扑

```text
┌──────────────────────────────┐
│ 营销前端 Sales SPA           │
│  - 商机/审批列表             │
│  - 动态表单渲染              │
└──────────────┬───────────────┘
               │ /sales/api
┌──────────────▼───────────────┐
│ sales-backend (BFF)          │
│  - 商机、闸门、审批投影      │
│  - WorkflowPlatformClient    │
│  - 事件接收/对账              │
└───────┬──────────────┬───────┘
        │              │ HTTP
        │              ▼
        │   ┌──────────────────────────────┐
        │   │ workflow-backend             │
        │   │  - 定义/表单/实例/任务 API    │
        │   │  - 只写 intent/outbox         │
        │   │  - 查询读模型                 │
        │   └──────────┬───────────────────┘
        │              │ Outbox
        │   ┌──────────▼───────────────────┐
        │   │ workflow-worker              │
        │   │  - Temporal Worker           │
        │   │  - Dispatcher / Reconciler   │
        │   │  - Activities 写 workflow DB │
        │   └──────────┬───────────────────┘
        │              │
        │   ┌──────────▼───────────────────┐
        │   │ Temporal Server              │
        │   │  workflow-engine-queue       │
        │   └──────────────────────────────┘
        │
        └──> workflow DB / sales DB 逻辑隔离，不跨库写
```

### 2.2 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| 营销平台 | 商机、闸门、业务规则、销售权限、业务审计 | 流程节点推进、SLA Timer、审批任务状态机 |
| workflow 平台 | 定义、表单、实例、任务、审批历史、流程 API | 商机状态、销售金额、客户主数据 |
| Temporal | 执行历史、Timer、Signal、重试、Replay | 业务读模型、表单定义 |
| workflow DB | 定义/表单主数据 + 实例/任务读模型 | 作为流程推进的唯一事实来源 |
| sales DB | 商机 + 审批业务投影 | 保存完整 Temporal History |

### 2.3 核心原则

1. **workflow 平台是独立服务**，营销通过 HTTP 调用，不把 `workflow/backend` 当库导入。
2. **Temporal 是执行事实来源**，`flow_instance` / `flow_task` 是可重建投影。
3. **定义和表单版本化**，启动时冻结快照，运行中的实例不受后续编辑影响。
4. **营销只消费已发布版本**，不直接读写 `flow_definition` / `flow_form` 表。
5. **一个聚合只有一个写入方**：审批命令写 workflow 平台，商机状态写 sales 平台。
6. **所有跨服务写操作走 Outbox + 幂等键**。

---

## 3. 复刻版 workflow 改造

### 3.1 拆分现有 runtime

当前 `engine/runtime.py` 同时承担图计算、状态推进和数据库写入。改造后拆成三层：

```text
workflow/backend/app/
├── engine/
│   ├── definition.py      # 保留：定义 CRUD/发布
│   ├── graph.py           # 保留：图结构、拓扑、可达性
│   ├── expression.py      # 保留：条件表达式、handler 解析
│   ├── chart.py           # 保留：流程图
│   ├── projection.py      # 新增：实例/任务读模型写入
│   └── commands.py        # 新增：命令校验、命令去重
├── temporal/
│   ├── client.py          # Temporal Client
│   ├── worker.py          # Worker 入口
│   ├── workflow.py        # 通用 FlowInstanceWorkflow
│   ├── activities.py      # 所有副作用
│   ├── contracts.py       # 输入/信号/命令数据类
│   └── policies.py        # 重试、超时、并发策略
├── outbox.py              # 启动/命令/事件 Outbox
├── dispatcher.py          # Outbox -> Temporal
├── reconciler.py          # Temporal/DB 对账
└── auth.py                # EAI JWT / 本地模式
```

`api/runtime.py` 不再直接调用 `engine.runtime` 推进流程，只做：

```text
POST /instances          -> 创建 instance + outbox，返回 202
POST /tasks/{id}/...     -> 创建 command + outbox，返回 202
GET  /instances/{id}     -> 读 workflow DB 投影
GET  /tasks              -> 读 workflow DB 投影
```

### 3.2 数据模型调整

在现有 8 张 warm-flow 表上增量扩展，不推翻表结构。

#### `flow_definition`

新增/明确：

```sql
version           -- 已存在，发布时递增，例如 "3"
is_publish        -- 已存在
published_at      -- 新增
published_by      -- 新增
definition_hash   -- 新增，发布快照哈希
```

发布规则：

- 草稿可编辑。
- 发布后生成不可变快照。
- 运行中实例只引用快照，不引用最新定义。

#### `flow_instance`

新增：

```sql
instance_no              varchar(64) unique
business_type            varchar(64)   -- sales_opportunity_gate
business_key             varchar(128)  -- sales approval id
definition_version       varchar(32)
definition_snapshot_json text/json     -- 启动时冻结的 DefJson
temporal_workflow_id     varchar(160)
temporal_run_id          varchar(160)
status                   varchar(20)   -- pending_start/running/completed/terminated/failed
revision                 int           -- 每次状态变更 +1
started_at               timestamptz
completed_at             timestamptz
failure_reason           text
```

唯一约束：

```sql
unique (tenant_id, business_type, business_key, status)
-- 或使用部分唯一索引，只约束 active 状态
```

#### `flow_task`

新增：

```sql
task_key                 varchar(128)  -- 稳定任务键
assignees_json           text/json     -- 候选人/角色/用户
form_snapshot_json       text/json     -- 节点表单快照
sla_deadline             timestamptz
revision                 int
status                   varchar(20)   -- pending/active/completed/cancelled
```

#### `flow_his_task`

新增：

```sql
command_id               varchar(128) unique
actor_id                 varchar(64)
action                   varchar(32)   -- approve/reject/return/transfer/delegate/add_signature
payload_json             text/json
```

#### 新增表

```sql
flow_command (
  id bigserial primary key,
  instance_id bigint not null,
  task_id bigint,
  command_id varchar(128) unique not null,
  action varchar(32) not null,
  actor_id varchar(64) not null,
  payload_json text not null,
  status varchar(20) default 'pending',
  attempts int default 0,
  next_retry_at timestamptz,
  last_error text,
  created_at timestamptz,
  processed_at timestamptz
);

flow_outbox (
  id bigserial primary key,
  event_id varchar(128) unique not null,
  aggregate_type varchar(64) not null,
  aggregate_id bigint not null,
  event_type varchar(64) not null,
  payload_json text not null,
  status varchar(20) default 'pending',
  attempts int default 0,
  next_retry_at timestamptz,
  last_error text,
  created_at timestamptz,
  processed_at timestamptz
);
```

### 3.3 Temporal Workflow 设计

新增通用工作流，不为每个业务定义写一个 Temporal Workflow：

```python
@workflow.defn
class FlowInstanceWorkflow:
    @workflow.run
    async def run(self, input: FlowInstanceInput) -> FlowInstanceResult: ...

    @workflow.signal
    async def submit_command(self, command: TaskCommand) -> None: ...

    @workflow.signal
    async def cancel(self, command: CancelCommand) -> None: ...

    @workflow.query
    def state(self) -> dict: ...
```

`FlowInstanceInput` 包含：

```python
@dataclass
class FlowInstanceInput:
    instance_id: int
    tenant_id: str
    flow_code: str
    flow_version: str
    definition_snapshot: dict
    business_type: str
    business_key: str
    variables: dict
    starter: Actor
```

执行模型：

```text
启动
  -> Activity mark_instance_running
  -> 解析 start 节点
  -> 按 skip 激活下一个节点
  -> 审批节点：Activity activate_task（解析 handler、创建 task、计算 SLA）
  -> wait_condition 等待 submit_command / timer
  -> Activity apply_task_command（幂等写 task/history/outbox）
  -> 根据 action 推进、退回、转办、加签或结束
  -> Activity finalize_instance
```

关键约束：

- Workflow 内**禁止** DB、HTTP、随机数、`datetime.now()`。
- 所有 ID、时间、handler 解析、数据库写入都在 Activity 或启动参数中完成。
- 定义快照随启动输入传递；超过 Temporal payload 限制时改为 DB 快照 ID + 启动 Activity 加载，并在启动时校验大小。
- 使用 `workflow.now()`、`workflow.uuid4()`。
- 长流程使用 `workflow.continue_as_new(state)`，阈值例如 2,000 个事件或 30 天。
- 使用 `workflow.patched` 做工作流代码版本兼容。
- Workflow ID：`flow-{tenant_id}-{instance_id}`。
- 启动策略：`WorkflowIDReusePolicy.REJECT_DUPLICATE`。
- Task Queue：`workflow-engine-queue`，与 `sales-approval-queue`、`project-workflow-queue` 分离。

### 3.4 审批语义映射

| warm-flow 语义 | Temporal 实现 |
|---|---|
| 串行审批 | 激活一个 task，`wait_condition` 等命令 |
| 并行审批 | 激活多个分支/task，按 `parallel_all` / `parallel_any` 条件等待 |
| 会签 | 一个 task 多个 assignment，按 `node_ratio` 计算完成条件 |
| 或签 | 任一 assignment 通过即节点完成 |
| 驳回 | 按 `REJECT` skip 跳转；无目标则结束 |
| 驳回上一节点 | 从 workflow state 的审批历史栈找上一个审批节点 |
| 转办 | 更新 task assignees，记录 history，重新等待 |
| 委派 | 增加/替换 assignment，保留原审批人审计 |
| 加签/减签 | 更新 assignment 集合，重新计算会签条件 |
| 撤回 | `cancel` signal，关闭活跃 task，标记 terminated |
| SLA 超时 | `workflow.wait_condition(timeout=...)` + `escalate_task` Activity |
| 定时提醒 | Temporal Timer，不依赖数据库扫描 |
| 过期 | 超时 Activity 标记 expired/升级，**不自动通过** |

### 3.5 Activity 清单

```text
mark_instance_running(instance_id, workflow_id, run_id)
activate_node(instance_id, node_code, variables, revision)
activate_task(instance_id, node_code, assignees, form_snapshot, sla_deadline)
apply_task_command(instance_id, task_id, command)
resolve_handlers(instance_id, node_code, variables)
evaluate_skips(instance_id, node_code, variables)
record_history(instance_id, task_id, command)
escalate_task(instance_id, task_id, reason)
finalize_instance(instance_id, result)
cancel_instance(instance_id, reason)
emit_event(instance_id, event_type, payload)
```

Activity 要求：

- 全部幂等，使用 `command_id` / `event_id` / `task_id + revision` 做唯一键。
- 每个 Activity 在自己的事务里更新投影并写 outbox。
- 配置重试策略：数据库瞬时错误有限重试；业务校验错误不重试。
- Activity 超时和心跳用于长任务。

### 3.6 命令与 Signal

外部 API 不直接推进流程，而是写 `flow_command`：

```text
POST /tasks/{task_id}/approve
  -> 校验操作者、任务状态、表单
  -> 插入 flow_command(command_id 唯一)
  -> 返回 202 {command_id, status:"accepted"}
  -> dispatcher 发送 Temporal signal submit_command
  -> Activity apply_task_command 幂等处理
```

Signal 载荷：

```json
{
  "command_id": "cmd-uuid",
  "instance_id": 123,
  "task_id": 456,
  "task_revision": 7,
  "actor": {
    "user_id": "u1001",
    "roles": ["sales_manager"],
    "dept_id": "d01",
    "tenant_id": "000000"
  },
  "action": "approve",
  "comment": "同意",
  "form_data": {
    "decision_reason": "客户资质已核验"
  },
  "target_node_code": null
}
```

并发控制：

- Workflow 检查 `task_revision`，过期命令拒绝并记录 `stale_command`。
- 同一 `command_id` 重复投递只处理一次。
- API 层也做乐观锁，避免重复点击。

### 3.7 事件回调

平台通过 `flow_outbox` 发送事件到 sales：

```json
{
  "event_id": "evt-uuid",
  "event_type": "instance.changed",
  "instance_id": 123,
  "revision": 8,
  "business_type": "sales_opportunity_gate",
  "business_key": "approval-uuid",
  "occurred_at": "2026-10-24T10:00:00Z",
  "payload": {
    "status": "running",
    "current_nodes": ["manager_approve"]
  }
}
```

约定：

- 事件只做“变更通知”，不承载完整业务快照。
- sales 收到事件后调用 `GET /instances/{id}?view=sales_projection` 拉取归一化快照。
- 事件按 `event_id` 去重，按 `revision` 忽略旧事件。
- 平台 Outbox 至少一次投递；sales 事件表幂等。
- sales 定时对账兜底，修复漏事件。

---

## 4. 营销平台改造

### 4.1 数据模型

`approval_requests` 新增：

```sql
engine                    varchar(32) default 'legacy_temporal'
                          -- legacy_temporal / workflow_platform
platform_instance_id      bigint
platform_definition_code  varchar(64)
platform_definition_version varchar(32)
platform_status           varchar(20)
projection_revision       int default 0
last_event_at             timestamptz
```

保留 `workflow_id` / `workflow_run_id` 仅用于 legacy Temporal 实例，避免语义混淆。

新增绑定表：

```sql
approval_definition_bindings (
  gate_code varchar(16) primary key,
  flow_code varchar(64) not null,
  flow_version varchar(32),          -- null = 最新已发布
  engine varchar(32) not null default 'workflow_platform',
  is_active boolean not null default true,
  created_at timestamptz,
  updated_at timestamptz
);
```

规则：

- 新审批启动时按 `gate_code` 查绑定。
- 找不到绑定则 fail closed，返回明确配置错误。
- 旧 `approval_definitions.steps_json` 只服务 legacy 路径，不再作为新流程事实来源。
- 运行中的 legacy 实例继续用旧表跑完，不做中途迁移。

`approval_steps` / `approval_assignments` 新增：

```sql
platform_task_id   bigint
node_code          varchar(100)
platform_revision  int
```

作为平台任务的销售侧读模型。

新增事件收件箱：

```sql
workflow_event_inbox (
  event_id varchar(128) primary key,
  event_type varchar(64),
  payload_json jsonb,
  received_at timestamptz,
  processed_at timestamptz,
  last_error text
);
```

### 4.2 启动链路

```text
营销前端发起 R4/R6/撞单审批
  -> sales-backend create_approval
  -> 查 approval_definition_bindings
  -> 创建 approval_request(status=pending_start, engine=workflow_platform)
  -> 同一事务写 outbox_events(approval.start)
  -> sales-worker dispatcher 调 workflow 平台
```

请求示例：

```http
POST /api/workflow/instances
Authorization: Bearer <user-jwt>
Idempotency-Key: approval:<approval_id>
Content-Type: application/json

{
  "flow_code": "sales.gate.r4",
  "flow_version": null,
  "business_type": "sales_opportunity_gate",
  "business_key": "<approval_id>",
  "tenant_id": "000000",
  "starter": {
    "user_id": "u1001",
    "roles": ["sales_rep"],
    "dept_id": "d01"
  },
  "variables": {
    "opportunity": {
      "id": "...",
      "opportunity_no": "OPP-2026-0001",
      "name": "...",
      "amount": 1200000,
      "stage": "S3",
      "region_code": "CN-E"
    },
    "gate": {
      "code": "R4",
      "reason": "新客户首单",
      "evidence": {}
    },
    "formData": {}
  },
  "callback_url": "http://sales-backend:3004/api/v1/integrations/workflow/events"
}
```

响应：

```json
{
  "instance_id": 123,
  "instance_no": "WF-2026-000123",
  "temporal_workflow_id": "flow-000000-123",
  "status": "pending_start",
  "definition_version": "3"
}
```

sales 侧保存 `platform_instance_id`、`platform_definition_version`，等待 `instance.changed` 事件。

幂等：

- `Idempotency-Key` = `approval:<approval_id>`。
- 平台重复请求返回同一 instance。
- Temporal 启动重复请求按 `AlreadyStarted` 处理为成功。

### 4.3 决策链路

```text
营销审批抽屉提交
  -> sales-backend /approvals/{id}/decision
  -> 校验销售权限 + 当前用户是否任务候选人
  -> 调 workflow 平台 command API
  -> 平台写 flow_command + 返回 202
  -> platform dispatcher signal Temporal
  -> workflow Activity 更新 task/history
  -> platform outbox 发 instance.changed
  -> sales 更新审批投影
```

请求示例：

```http
POST /api/workflow/tasks/456/commands
Authorization: Bearer <user-jwt>
Idempotency-Key: decision:<approval_id>:<task_id>:<uuid>

{
  "command_id": "cmd-uuid",
  "action": "approve",
  "comment": "同意",
  "form_data": {
    "decision_reason": "客户资质已核验"
  },
  "task_revision": 7,
  "target_node_code": null
}
```

响应：

```json
{
  "command_id": "cmd-uuid",
  "status": "accepted"
}
```

sales 侧：

- 不直接改 `approval_requests.status`。
- 返回 202，前端提示“已提交，等待流程引擎确认”。
- 收到事件后刷新详情。
- 平台返回 409（任务已处理/版本过期）时，前端刷新并提示。

### 4.4 表单接入

平台负责：

- 表单定义、版本、发布。
- 节点绑定 `form_path`。
- 启动时冻结表单快照。
- 任务详情返回 `form.schema`。
- 服务端校验必填、类型、选项。

营销负责：

- 从 sales API 获取当前任务表单 schema。
- 使用销售侧 `WorkflowFormRenderer` 渲染。
- 提交 `form_data`。
- 只读历史任务展示快照。

表单契约：

```json
{
  "version": "1",
  "fields": [
    {
      "key": "decision_reason",
      "label": "审批意见",
      "type": "textarea",
      "required": true,
      "placeholder": "请说明判断依据"
    },
    {
      "key": "risk_level",
      "label": "风险等级",
      "type": "select",
      "required": true,
      "options": ["低", "中", "高"]
    }
  ]
}
```

字段类型 MVP：

```text
text / textarea / number / select / date / switch
```

实现建议：

- 销售前端已有 React 19，与 workflow 前端一致。
- 不直接复用 Next.js 页面；把 `FormRenderer` 的 schema 解析和 6 种字段渲染移植到 `business/sales-service/frontend/src/components/workflow/`。
- 使用销售现有 `components/controls.tsx` 的控件样式，保持 UI 一致。
- 后续若字段类型增多，再抽 `shared/workflow-form` 包。
- 平台和销售共用契约测试，防止 schema 漂移。
- 文件上传 MVP 不走平台：销售仍上传 MinIO，表单值里保存 `attachment_ids`。

### 4.5 事件接收与投影

新增 sales 接口：

```http
POST /api/v1/integrations/workflow/events
X-Workflow-Event-Id: evt-uuid
X-Workflow-Timestamp: 1760000000
X-Workflow-Signature: sha256=...
```

处理：

```text
验证 HMAC + 时间窗
  -> insert workflow_event_inbox(event_id)（冲突则直接 200）
  -> 如果是 instance.changed：
       GET platform /instances/{id}?view=sales_projection&revision=...
       映射到 approval_requests / approval_steps / assignments
       更新 projection_revision
  -> 标记 processed
```

投影映射：

- `flow_node.ext` 可带销售扩展：

```json
{
  "sales": {
    "step_no": 1,
    "role": "sales_manager"
  }
}
```

- `approval_steps.step_no` 取 `ext.sales.step_no`，否则按节点拓扑顺序。
- `approver_role` 取 `ext.sales.role` 或平台 handler 角色。
- `platform_task_id` 保存平台 task id。
- `approval_assignments` 从平台 task assignments 映射。

对账：

- 每 5 分钟扫描 `status=running` 且 `last_event_at` 超过阈值的审批。
- 调用平台 instance detail，比较 `projection_revision`，修复漏事件。
- 对账只修读模型，不直接推进流程。

### 4.6 权限与身份

当前 `workflow/backend/app/deps.py` 使用 `X-User-Id` / `X-User-Roles` 演示头，不能上生产。

改造：

- `workflow-backend` 增加 `AUTH_MODE=eai|local`。
- `eai` 模式验证 EAI JWT（Authorization Bearer），从 token 取 `sub`、roles、dept、tenant。
- sales 调平台时转发当前用户 JWT；后台任务使用服务账号 token。
- 平台侧校验：
  - 启动：`workflow.instance.start`
  - 读取：`workflow.instance.read`
  - 决策：`workflow.task.decide`
  - 定义/表单管理：`workflow.definition.manage`
- 租户从 token 取，不能信任请求体里的 `tenant_id`。
- 回调使用 HMAC，不使用用户 JWT。

---

## 5. API 契约

建议保留复刻版现有 API 兼容，同时新增集成 API：

```text
POST /api/workflow/instances
GET  /api/workflow/instances/{id}
GET  /api/workflow/instances/{id}/tasks
GET  /api/workflow/tasks/{id}?view=approval
POST /api/workflow/tasks/{id}/commands
POST /api/workflow/instances/{id}/cancel
GET  /api/workflow/definitions/published?flow_code=...
GET  /api/workflow/forms/published?form_code=...
GET  /api/workflow/health
```

`GET /tasks/{id}?view=approval` 返回：

```json
{
  "task": {
    "id": 456,
    "instance_id": 123,
    "node_code": "manager_approve",
    "node_name": "销售经理审批",
    "status": "active",
    "revision": 7,
    "sla_deadline": "2026-10-25T10:00:00Z"
  },
  "instance": {
    "id": 123,
    "instance_no": "WF-2026-000123",
    "status": "running",
    "business_type": "sales_opportunity_gate",
    "business_key": "approval-uuid",
    "definition_version": "3"
  },
  "form": {
    "code": "sales_gate_approval",
    "version": "1",
    "schema": {
      "version": "1",
      "fields": []
    }
  },
  "variables": {},
  "history": []
}
```

兼容策略：

- 现有 `/tasks/{id}/approve` 等接口保留，内部改为写 `flow_command`，返回 202。
- 复刻版前端改为提交后 invalidate query / 轮询，不再假设同步完成。
- 新集成统一使用 `/commands`，减少接口碎片。

---

## 6. 部署方案

### 6.1 服务清单

新增：

```text
workflow-backend     FastAPI，内部端口 8020
workflow-worker      Temporal Worker + Dispatcher/Reconciler
workflow-frontend    Next.js，内部端口 3020
workflow-db          PostgreSQL database: workflow（复用 business-db 实例）
```

不要使用 8010：当前 8010 是 OCR 容器端口。

### 6.2 Compose 关键配置

```yaml
workflow-backend:
  build: ../workflow/backend
  environment:
    - WORKFLOW_DATABASE_URL=postgresql+asyncpg://business:business123@business-db:5432/workflow
    - WORKFLOW_AUTH_MODE=eai
    - TEMPORAL_ENABLED=true
    - TEMPORAL_URL=temporal:7233
    - TEMPORAL_NAMESPACE=default
    - TEMPORAL_TASK_QUEUE=workflow-engine-queue
    - WORKFLOW_PUBLIC_BASE_URL=http://localhost:2026/workflow
  depends_on:
    business-db:
      condition: service_healthy
    temporal:
      condition: service_started

workflow-worker:
  build: ../workflow/backend
  command: python -m app.worker
  environment:
    - WORKFLOW_DATABASE_URL=postgresql+asyncpg://business:business123@business-db:5432/workflow
    - TEMPORAL_ENABLED=true
    - TEMPORAL_URL=temporal:7233
    - TEMPORAL_NAMESPACE=default
    - TEMPORAL_TASK_QUEUE=workflow-engine-queue

workflow-frontend:
  build: ../workflow/frontend
  environment:
    - NEXT_PUBLIC_WORKFLOW_API=/workflow/api
```

### 6.3 Nginx

```nginx
location /workflow/api/ {
    set $workflow_backend_upstream workflow-backend:8020;
    rewrite ^/workflow/api/(.*)$ /api/workflow/$1 break;
    proxy_pass http://$workflow_backend_upstream;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
}

location = /workflow {
    return 301 /workflow/;
}

location /workflow/ {
    set $workflow_frontend_upstream workflow-frontend:3020;
    proxy_pass http://$workflow_frontend_upstream;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

当前前端页面路由本身已经是 `/workflow/*`，Phase 0 的 standalone 容器可直接访问
`http://localhost:3020/workflow`，此时 `basePath` 必须保持为空；否则会变成
`/workflow/workflow`。

Phase 1 若要通过统一 nginx 的 `/workflow/` 暴露，需要先把 Next 页面迁到根路由
（例如 `app/(workflow)/...`），再启用 `basePath: "/workflow"`，让 `/_next/*`
静态资源也落到 `/workflow/_next/*`；否则 `/_next/*` 会与主站冲突。该迁移与
nginx 路由一起做，不在 Phase 0 强行启用。

### 6.4 数据库与迁移

- 生产禁用 SQLite，统一 PostgreSQL。
- 引入 Alembic，禁止生产 `create_all`。
- 初始化 `workflow` database（`docker/postgres-init` 或运维脚本）。
- 迁移顺序：定义/表单表 -> 实例/任务扩展 -> command/outbox -> 索引/约束。
- `workflow/backend/workflow.db` 只保留本地演示，不提交。

### 6.5 可观测性

`/health` 返回：

```json
{
  "status": "ok",
  "database": "ok",
  "temporal": {
    "enabled": true,
    "connected": true,
    "namespace": "default",
    "task_queue": "workflow-engine-queue"
  },
  "outbox": {
    "pending": 0
  }
}
```

指标：

- `workflow_instances_total{status}`
- `workflow_tasks_active`
- `workflow_task_age_seconds`
- `workflow_outbox_pending`
- `workflow_temporal_rpc_errors_total`
- `workflow_commands_stale_total`

日志字段：

```text
instance_id, workflow_id, task_id, command_id, event_id, tenant_id
```

---

## 7. 迁移与上线

### Phase 0：平台骨架与连通性（已完成，2026-10-24）

- `workflow/` 已补齐 `.gitignore`、`.dockerignore`、后端/前端 Dockerfile。
- 后端加入 `temporalio`，新增 `app/temporal/client.py`、`worker.py`、`workflow.py`、`activities.py`。
- 配置新增 `TEMPORAL_ENABLED`、`TEMPORAL_URL`、`TEMPORAL_NAMESPACE`、`TEMPORAL_TASK_QUEUE`、并发与超时参数。
- `GET /health` 与 `GET /api/workflow/health` 返回 `temporal.connected`，探测有硬超时，Temporal 不可用时不拖垮 API。
- 独立 Worker 入口：`python -m app.temporal.worker`；Task Queue：`workflow-engine-queue`。
- 端口调整：`workflow-backend` 8020，`workflow-frontend` 3020，避开 OCR 8010 与 OntoStudio 3010。
- 验证通过：后端 51 项测试、前端 `pnpm typecheck` / `pnpm build`、两个 Docker 镜像构建、容器内 Worker 执行 `TemporalProbeWorkflow` 成功。
- 待办（Phase 1）：纳入 Git 跟踪、PostgreSQL + Alembic、EAI 认证、Compose/Nginx、表单/定义快照发布。
- 待办（Phase 2）：用真正的 `FlowInstanceWorkflow` 替换探测工作流，迁移串行/并行/会签/驳回/转办语义。

### Phase 1：平台生产化（4-6 天）

- PostgreSQL + Alembic。
- EAI 认证与权限。
- 定义/表单版本发布和快照。
- Dockerfile、Compose、Nginx、健康检查。
- 现有 workflow 前端改为走 `/workflow/api`；若走统一 nginx，先迁移到根路由并启用 `basePath=/workflow`。

### Phase 2：Temporal 运行时（6-8 天）

- 新增 `FlowInstanceWorkflow`、Activities、Worker。
- 新增 `flow_command` / `flow_outbox` / Dispatcher / Reconciler。
- 移植 `engine/runtime.py` 的图计算、会签、并行、驳回、转办语义。
- 把复刻版原有 48 个测试迁移为：
  - 纯图/表达式单元测试。
  - Temporal time-skipping 工作流测试。
  - Replay 测试。
- 验证 Worker 重启、Temporal 重启、重复 Signal、超时升级。

### Phase 3：营销接入（5-7 天）

- sales `WorkflowPlatformClient`。
- `approval_definition_bindings` 和配置迁移。
- 启动 Outbox 分支：legacy vs workflow_platform。
- 决策代理、事件收件箱、投影、对账。
- 销售前端动态表单渲染。
- 保留 legacy Temporal 路径，feature flag 控制。

### Phase 4：灰度切换（3-5 天）

- 先切 R4 单闸门。
- 观察：
  - 启动成功率
  - 任务到达率
  - 决策延迟
  - Outbox 积压
  - 投影一致性
- 再切 R6、撞单。
- 旧 `SalesApprovalWorkflow` 只处理存量，不接新单。

### Phase 5：清理（2-3 天）

- 移除 sales 直接启动 `SalesApprovalWorkflow` 的新单路径。
- 保留只读兼容和 reconciler。
- 归档旧审批模板。
- 更新 README、设计文档、运维手册。

粗估：1 名后端 + 1 名前端，约 4-6 周。最大工作量在 Temporal 审批语义迁移和测试，不在 CRUD。

---

## 8. 验收标准

### 功能

- 营销发起 R4 审批，平台创建实例，Temporal 出现 `FlowInstanceWorkflow`。
- 审批任务出现在销售待办，表单按平台 schema 渲染。
- 通过/驳回/退回/转办/加签均能推进，销售投影同步。
- 审批完成后商机闸门状态正确，审计记录完整。
- 重复点击、重复事件、重复启动均不产生重复实例/任务。

### 一致性

- Temporal 不可用时，启动进入 Outbox 重试，不丢单。
- Worker 重启后，运行中实例继续。
- 平台事件丢失时，销售对账能修复。
- 修改定义/表单不影响运行中实例。
- 旧 `approval_requests` 历史仍可查看。

### 安全

- 未授权用户不能查看/决策他人任务。
- 租户隔离生效。
- 回调签名校验和重放保护生效。
- 平台演示头在 `AUTH_MODE=eai` 下不可用。

### 性能

- 单实例启动 P95 < 1s（不含 Temporal 调度）。
- 任务列表查询 P95 < 300ms。
- 100 并发审批不出现重复任务/丢 Signal。
- Outbox 积压可观测、可重试。

---

## 9. 主要风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| warm-flow 语义与 Temporal 状态机不一致 | 审批走错分支 | 建 conformance 测试，逐条覆盖会签/并行/驳回/转办 |
| 双写导致状态分叉 | 销售与平台状态不一致 | 单写入方；销售只做投影；事件 + 对账 |
| 定义编辑影响运行中实例 | 流程漂移 | 启动冻结 `definition_snapshot` / `form_snapshot` |
| 事件丢失 | 销售状态停滞 | Outbox + inbox 去重 + 定时对账 |
| Command 重复/乱序 | 重复审批 | `command_id` 唯一 + `task_revision` 乐观锁 |
| 长流程 History 膨胀 | 工作流失败 | `continue_as_new` + 状态快照 |
| Temporal payload 超限 | 启动失败 | 定义大小限制；大快照存 DB，传引用 |
| 表单 schema 漂移 | 前端渲染错误 | 共享契约 + 契约测试；未知字段降级只读 |
| 演示认证头上生产 | 越权 | 强制 EAI JWT，禁用 local 模式 |
| 端口冲突 | 部署失败 | 使用 8020/3020，避开 OCR 8010 |
| 存量审批迁移 | 流程中断 | 不迁移运行中实例，存量跑完，新单走新链路 |

---

## 10. 代码改造清单

### workflow 平台

```text
workflow/backend/pyproject.toml                 + temporalio, alembic
workflow/backend/app/config.py                  + TEMPORAL_*, AUTH_MODE, WORKFLOW_PUBLIC_BASE_URL
workflow/backend/app/models.py                  + instance/task/command/outbox 字段
workflow/backend/app/auth.py                    + EAI JWT
workflow/backend/app/temporal/client.py         + Client / 健康探测（Phase 0 已完成）
workflow/backend/app/temporal/worker.py         + Worker（Phase 0 已完成）
workflow/backend/app/temporal/workflow.py       + TemporalProbeWorkflow（Phase 0）/ FlowInstanceWorkflow（Phase 2）
workflow/backend/app/temporal/activities.py     + 探测 Activity（Phase 0）/ 幂等 Activities（Phase 2）
workflow/backend/app/temporal/contracts.py      + 输入/信号/命令
workflow/backend/app/outbox.py                  + 事务 Outbox
workflow/backend/app/dispatcher.py              + Temporal signal/start
workflow/backend/app/reconciler.py              + 对账
workflow/backend/app/api/runtime.py             改为命令/投影模式
workflow/backend/app/engine/projection.py       新增读模型写入
workflow/backend/alembic/                       新增迁移
workflow/backend/Dockerfile                     新增
workflow/frontend/Dockerfile                    新增
workflow/frontend/next.config.*                 basePath 保持空；现有页面已自带 /workflow 前缀
workflow/frontend/src/lib/api.ts                本地 8020；统一入口构建参数改为 /workflow/api
```

### 营销平台

```text
business/sales-service/backend/app/integrations/workflow_platform.py  新增客户端
business/sales-service/backend/app/models.py                           + engine/platform_* / inbox
business/sales-service/backend/app/approval_service.py                 启动/决策分支
business/sales-service/backend/app/workflows/dispatcher.py             provider 分支
business/sales-service/backend/app/routers/approvals.py                决策代理 + 事件接口
business/sales-service/backend/app/config.py                           + WORKFLOW_PLATFORM_*
business/sales-service/frontend/src/components/workflow/FormRenderer.tsx  新增
business/sales-service/frontend/src/pages/Approvals.tsx                动态表单
business/sales-service/frontend/src/api.ts                             类型扩展
```

### 部署

```text
docker/docker-compose.business.yaml        + workflow-backend/worker/frontend
docker/docker-compose.temporal.yaml        + workflow-engine-queue 说明
docker/nginx/nginx.conf                    + /workflow/、/workflow/api/
docker/postgres-init/                      + workflow database
```

---

## 11. 建议的 MVP 闭环

先只做 R4 一个闸门，打通下面这条最小链路：

```text
营销发起 R4
  -> sales outbox
  -> workflow 平台创建实例
  -> Temporal 启动 FlowInstanceWorkflow
  -> 生成销售经理任务
  -> 销售审批抽屉渲染平台表单
  -> 提交通过
  -> Temporal Activity 更新任务
  -> 平台事件回传 sales
  -> 商机 R4 闸门解除
```

MVP 不包含：

- 并行会签/或签的高级比例策略（可先支持串行 + 全部会签）。
- 加签/减签。
- 复杂退回路径。
- 文件字段。
- 平台内置销售专用报表。

MVP 验收通过后，再补全会签、并行、转办、SLA 升级和 R6/撞单。
