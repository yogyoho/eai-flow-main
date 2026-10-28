# EAI Workflow · 工作流子系统

在 `D:\eai\eai-flow-main\workflow` 下，用 **FastAPI + SQLAlchemy async** 与
**Next.js App Router + React 19** 一比一复刻
[warm-flow](https://github.com/minflow/warm-flow) 的流程定义管理、双设计器、
流程图、表单与运行时审批语义。

> 本目录是**独立子系统**：它不读取、不写入、不复用
> `backend/app/extensions/workflow`（Temporal DAG）和
> `frontend/src/app/workflow-admin` 的任何模型或表结构。

---

## 1. 目录结构

```
workflow/
├── backend/                  # 独立 FastAPI 应用（默认 8020）
│   ├── alembic/              # PostgreSQL/Alembic 迁移
│   ├── app/
│   │   ├── api/              # definitions / designer / runtime / forms / meta
│   │   ├── engine/           # 定义、图、表达式、运行时、流程图
│   │   ├── models.py         # 8 张 warm-flow 核心表
│   │   ├── schemas.py        # Pydantic 请求/响应
│   │   ├── seed.py           # 三个演示流程 + 两个演示表单
│   │   └── main.py
│   └── tests/                # pytest（69 项）
├── frontend/                 # 独立 Next.js 应用（默认 3020，basePath=/workflow）
│   └── src/
│       ├── app/(workflow)/   # 定义、设计器、实例、待办、表单
│       ├── components/workflow/  # 设计器、表单渲染、审批弹窗、SVG 流程图
│       └── lib/              # API 客户端、类型、表单/会话工具
├── docs/DESIGN.md            # 源系统盘点与复刻契约
└── sql/001_workflow_mysql.sql
```

---

## 2. 快速启动

### 2.1 后端

```powershell
cd D:\eai\eai-flow-main\workflow\backend
python -m pip install -r requirements.txt
python -m alembic upgrade head      # PostgreSQL 生产库
python -m uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

- 生产库用 `alembic upgrade head` 建表；本地 SQLite 可保留
  `WORKFLOW_AUTO_CREATE_SCHEMA=1` 自动建表。
- 首次启动写入演示数据（`WORKFLOW_SEED_DEMO=1`）。
- 默认数据库：`backend/workflow.db`（SQLite）。
- 健康检查：`GET http://127.0.0.1:8020/health`，包含 `database.connected`
  与 `temporal.connected`。
- 交互文档：`http://127.0.0.1:8020/docs`。
- 认证：`WORKFLOW_AUTH_MODE=local` 信任 `X-User-*` 请求头；
  `WORKFLOW_AUTH_MODE=eai` 校验共享 JWT，并通过 Gateway
  `/api/permissions/me` 获取身份与权限。生产 Compose 默认 `eai`。
- Temporal Worker（独立进程）：

```powershell
$env:TEMPORAL_ENABLED="1"
$env:TEMPORAL_URL="127.0.0.1:7233"
$env:TEMPORAL_TASK_QUEUE="workflow-engine-queue"
python -m app.temporal.worker
```

切换到 PostgreSQL 只需设置环境变量（无需改代码）：

```powershell
$env:WORKFLOW_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/workflow"
$env:WORKFLOW_AUTO_CREATE_SCHEMA="0"
python -m alembic upgrade head
```

### 2.2 前端

```powershell
cd D:\eai\eai-flow-main\workflow\frontend
pnpm install
pnpm dev            # http://localhost:3020/workflow
```

> 设计器基于 LogicFlow，其 ESM 包存在循环依赖。Next 16 默认的 Turbopack 会在
> 设计器页抛出 `Cannot access '__TURBOPACK__default__export__' before initialization`，
> 因此 `dev` / `build` 脚本显式使用 `--webpack`。若要改回 Turbopack，请先验证
> `/workflow/design/[id]` 可正常装载。

可选环境变量（`frontend/.env.local`）：

```
NEXT_PUBLIC_WORKFLOW_API=http://127.0.0.1:8020/api/workflow
NEXT_PUBLIC_BASE_PATH=/workflow
```

Docker/Nginx 部署时改为同源 `NEXT_PUBLIC_WORKFLOW_API=/workflow/api`，
页面、RSC 与 `/_next` 资源统一由 `basePath=/workflow` 提供。

### 2.3 校验

```powershell
cd workflow\backend  ; python -m pytest -q
cd workflow\frontend ; pnpm typecheck ; pnpm build
```

### 2.4 Docker

```powershell
docker build -t eai-workflow-backend  workflow/backend
docker build -t eai-workflow-frontend `
  --build-arg NEXT_PUBLIC_WORKFLOW_API=http://127.0.0.1:8020/api/workflow `
  workflow/frontend

docker run --rm -p 8020:8020 `
  -e TEMPORAL_ENABLED=1 `
  -e TEMPORAL_URL=host.docker.internal:7233 `
  eai-workflow-backend

docker run --rm -p 3020:3020 eai-workflow-frontend
```

统一栈（业务库 + Temporal + workflow）：

```powershell
docker compose `
  -f docker/docker-compose-dev.yaml `
  -f docker/docker-compose.extensions.yaml `
  -f docker/docker-compose.business.yaml `
  -f docker/docker-compose.temporal.yaml `
  -f docker/docker-compose.workflow.yaml up -d
```

`docker-compose.workflow.yaml` 已通过 `include` 接入
`docker-compose.business.yaml`，因此常规业务栈启动时会自动创建 workflow 服务；
单独传入该 overlay 也仍然有效。该覆盖文件会创建 `workflow` 数据库、执行
`alembic upgrade head`，并启动 `workflow-backend`、`workflow-worker`、
`workflow-dispatcher`、`workflow-frontend`。nginx 入口：

- 页面：`http://localhost:2026/workflow`
- API：`http://localhost:2026/workflow/api/*` → `workflow-backend:8020/api/workflow/*`
- 调试端口：`127.0.0.1:8020`、`127.0.0.1:3020`

生产必须提供 `JWT_SECRET_KEY`，并保持 `WORKFLOW_AUTH_MODE=eai`；
首次启动是否写入演示数据由 `WORKFLOW_SEED_DEMO=1` 控制。若只做本地联调，可设置
`WORKFLOW_AUTH_MODE=local` 与 `WORKFLOW_SEED_DEMO=1`，保留演示身份切换器。

---

## 3. 演示账号与流程

`local` 模式下请求身份通过请求头注入，前端在左下角切换；`eai` 模式使用
真实 EAI 身份并隐藏切换器。演示账号：

| 用户 | 姓名 | 部门 | 角色 |
|---|---|---|---|
| `u1001` | 张三 | d01 研发部 | manager / employee |
| `u1002` | 李四 | d02 总经办 | director |
| `u1003` | 王五 | d03 财务部 | finance |
| `u1004` | 赵六 | d01 研发部 | employee |

请求头：`X-User-Id`、`X-User-Roles`（逗号分隔）、`X-User-Dept`、
`X-Tenant-Id`。用户名只在浏览器侧映射，不放进请求头（HTTP 头必须 ASCII）。

内置流程：

| 编码 | 名称 | 说明 |
|---|---|---|
| `leave` | 员工请假流程 | 部门负责人 → 分管领导；部门负责人用 `role:manager@@u1001` 双通道 |
| `expense` | 费用报销流程 | 互斥网关按金额分流（≤5000 财务，>5000 总监后财务） |
| `purchase` | 采购申请流程 | 会签节点 `review`，3 人 100% 通过后进入财务 |

演示表单：`leave_form:1`、`expense_form:1`。

---

## 4. 数据模型

保留 warm-flow 的 8 张核心表（`sql/001_workflow_mysql.sql` 提供 MySQL DDL）：

| 表 | 作用 |
|---|---|
| `flow_definition` | 流程定义、版本、发布/挂起、监听器、表单绑定 |
| `flow_node` | 节点、坐标、权限标识、会签比例、节点表单 |
| `flow_skip` | 跳转、条件表达式、跳转类型（PASS/REJECT）、边坐标 |
| `flow_instance` | 实例、当前节点、流程状态、变量快照、DefJson 快照 |
| `flow_task` | 待办任务（当前节点 + 办理人） |
| `flow_his_task` | 审批历史（通过、退回、转办、委派、加签、会签票） |
| `flow_user` | 任务办理人（审批/转办/委派/加签） |
| `flow_form` | 业务表单定义（`form_content` 字段 schema） |

节点类型与 warm-flow 保持一致：
`0=start, 1=between, 2=end, 3=serial, 4=parallel, 5=inclusive`。

流程状态沿用 warm-flow 编码：`0 待提交 / 1 审批中 / 2 审批通过 /
4 已终止 / 5 已作废 / 6 已撤销 / 8 已完成 / 9 已退回`。
实例启动后为 `0`（待提交），首个审批通过后进入 `1`，这是源系统原生语义，
实例列表用「待提交」标签单独展示。

---

## 5. 设计器契约

前端使用 LogicFlow（`@logicflow/core` + `@logicflow/extension`）直接承载画布：

- 经典模式（`CLASSICS`）：节点语义色 + 自由布局，是唯一保留的设计器模式。
- 节点坐标 `x,y|textX,textY`；边坐标 `x1,y1;x2,y2|textX,textY`。
- 节点标签固定在节点形状内部；加载定义时会把 `textX,textY` 归一化到节点中心。
- 加载历史边坐标时会校验首尾点是否靠近源/目标节点；异常坐标回退为自动路由，
  避免旧数据把所有连线画到同一个位置。销售审批 seed 会在启动时自动修复旧布局。
- `save-json` 请求头 `onlyNodeSkip` 支持仅保存节点与跳转。
- 保存校验：恰好一个开始节点、允许多个结束节点、禁止跳转到开始节点。
- 设计器接口沿用 warm-flow 路径：

```
POST /api/workflow/designer/save-json
GET  /api/workflow/designer/query-def/{id}
GET  /api/workflow/designer/query-flow-chart/{instanceId}
GET  /api/workflow/designer/execute/load/{taskId}
GET  /api/workflow/designer/execute/hisLoad/{hisTaskId}
POST /api/workflow/designer/execute/handle
GET  /api/workflow/designer/published-form
GET  /api/workflow/designer/form-content/{formId}
POST /api/workflow/designer/form-content
GET  /api/workflow/designer/handler-type|handler-result|handler-feedback|handler-dict
GET  /api/workflow/designer/node-ext|listener-list
```

运行时 REST（实例/待办/历史/表单/元数据）：

```
POST /api/workflow/instances
GET  /api/workflow/instances
GET  /api/workflow/instances/{id}
POST /api/workflow/instances/{id}/revoke|terminate|suspend|activate
GET  /api/workflow/tasks?assignee=u1001&instanceId=...
POST /api/workflow/tasks/{id}/approve|reject|reject-last
POST /api/workflow/tasks/{id}/transfer|depute|add-signature|reduce-signature
GET  /api/workflow/history?handler=u1001&instanceId=...
GET/POST/PUT/DELETE /api/workflow/forms
POST /api/workflow/forms/{id}/publish
GET  /api/workflow/meta/{enums,stats,users,handlers}
```

`designer/execute/load` 会返回任务、实例、节点、变量、表单 schema、
`task.chart`（实例 DefJson 快照）与 `task.assignees`，供审批弹窗直接渲染。

所有写接口（启动、审批、退回、撤销、终止、转办、加签）支持
`Idempotency-Key` 请求头；相同键与相同载荷重复提交只产生一条命令。

---

## 6. 条件表达式与办理人

条件（`skip_condition`）：

```
eq@@amount|5000      ne@@type|A
gt@@amount|5000      ge@@amount|5000
lt@@days|3           le@@days|3
like@@title|采购     notLike@@title|测试
default@@            spel@@amount > 1000 and level == "A"
```

- `default@@` 为兜底分支。
- `spel@@` 仅支持安全表达式子集（Python `ast` 白名单，禁止任意代码）。
- 办理人支持 `u1001@@u1002`、`role:manager`、`dept:d01` 与 `${变量}` 占位。
- 未配置办理人时回退给发起人 / 当前处理人。

---

## 7. 已知差异与约定

1. `flow_his_task.flow_status` 在历史行上使用更直观的
   `2=通过 / 9=退回 / 8=完成`，与实例状态机同源；源系统的部分历史状态码
   （如 `3/7`）未在历史行复用。
2. 保存定义时**允许多个结束节点**（并行/包容分支需要），只校验恰好一个开始节点。
3. `reject-last` 只回退到历史中的审批节点（跳过开始节点与网关）；
   首个审批节点无法退回时会返回明确错误。
4. 运行态流程图使用轻量自绘 SVG（非 LogicFlow），以获得更清晰的只读展示；
   设计器仍使用 LogicFlow。
5. 前端演示身份切换只在 `WORKFLOW_AUTH_MODE=local` 下可用；`eai` 模式
   使用 HttpOnly Cookie/JWT 的真实身份并隐藏切换器。
6. 表单删除为软删除；被已发布流程引用时后端返回 `409` 并拒绝删除。

---

## 8. 演示数据说明

`backend/workflow.db` 为本地演示库（已被 `.gitignore` 忽略）。运行时会产生
形如 `SMOKE-LEAVE-*`、`SMOKE-EXPENSE-*` 的验证实例；如需干净环境，
停止后端后删除该文件并重启即可自动重建演示数据。

---

## 9. Phase 1 实施记录

- **数据库迁移**：新增 `alembic.ini` 与初始迁移；生产
  `WORKFLOW_AUTO_CREATE_SCHEMA=0` + `alembic upgrade head`，SQLite 演示仍可自动建表。
- **EAI 认证**：`WORKFLOW_AUTH_MODE=eai` 校验共享 JWT，调用 Gateway
  `/api/permissions/me`，按 60 秒 TTL 缓存身份与权限；`/api/workflow/meta/me`
  返回当前主体。管理员权限 `*` 可办理任意待办。
- **实例快照**：启动时把定义图与所有被引用表单写入 `flow_instance.def_json`
  （`nodeList/skipList/formSnapshot`）。任务加载、审批推进、撤销/终止和流程图
  都从快照读取，后续编辑定义或表单不会影响运行中的实例。
- **统一入口**：前端页面迁到根路由组并设置 `basePath=/workflow`；nginx
  `/workflow/` 代理页面与静态资源，`/workflow/api/` 转发到后端固定前缀。
- **Compose**：`docker/docker-compose.workflow.yaml` 提供数据库初始化、
  Alembic、API、Temporal Worker、Dispatcher 与前端服务。

---

## 10. Phase 2：Temporal 真实编排

### 10.1 数据流

```
营销 BFF / 前端
   │ POST /instances 或 /tasks/{id}/approve...
   ▼
workflow-backend
   ├─ 写 flow_command（PENDING，Idempotency-Key 唯一）
   ├─ 快速路径 signal FlowInstanceWorkflow
   └─ 等待命令 APPLIED / FAILED（超时返回当前投影）
   ▼
workflow-dispatcher
   ├─ 扫描 PENDING 命令 → signal Temporal
   ├─ 扫描 flow_outbox → POST 营销回调（HMAC 签名）
   └─ 定时 reconcile 卡住的命令 / 运行时 / Outbox
   ▼
workflow-worker
   └─ FlowInstanceWorkflow → apply_command_activity
        └─ 单事务：runtime 变更 + command=APPLIED + outbox 事件
```

- 每个实例一个长期运行 Workflow：`flow-instance-{instance_id}`。
- 与审批有关的变更全部走命令表；`TEMPORAL_ENABLED=0` 时命令在 API 进程内同步执行，便于本地演示和测试。
- `START` 仍同步创建实例和首个任务（保证 API 立即返回实例 ID），随后启动 Workflow；若启动失败，由 Reconciler 从 `flow_instance_runtime` 补启动。
- `flow_command.idempotency_key` 唯一；Activity 重试或重复 signal 不会重复审批。
- `flow_outbox` 与领域变更同事务提交；Webhook 失败按指数退避重试，达到上限后标记 `FAILED`。
- 未配置 `WORKFLOW_EVENT_WEBHOOK_URL` 时事件标记为 `SKIPPED`，不会无限重试。

### 10.2 新增表

| 表 | 作用 |
|---|---|
| `flow_command` | 幂等命令收件箱；状态 `PENDING/DISPATCHING/DISPATCHED/APPLIED/FAILED/CANCELLED` |
| `flow_instance_runtime` | 实例与 Temporal Workflow 的绑定、`run_id`、同步状态和错误 |
| `flow_outbox` | 事务性领域事件、投递状态、重试次数与去重键 |

### 10.3 事件与幂等

- 事件类型：`workflow.instance.started`、`workflow.instance.updated`、
  `workflow.instance.completed`。
- 事件载荷包含实例、当前任务、办理人、业务 ID、流程变量和触发命令。
- Webhook 请求头：`X-Workflow-Event`、`X-Workflow-Delivery`、
  `X-Workflow-Timestamp`、`X-Workflow-Signature: sha256=...`；
  签名原文为 `timestamp + "." + body`。
- 写命令接口支持标准 `Idempotency-Key` 请求头；重复提交同一键且载荷一致时返回同一结果。

### 10.4 运行进程

```powershell
python -m app.temporal.worker       # Workflow + Activity
python -m app.temporal.dispatcher   # command signal + outbox + reconcile
```

Dispatcher 的关键配置：

```env
WORKFLOW_COMMAND_WAIT_TIMEOUT_SECONDS=5
WORKFLOW_COMMAND_DISPATCH_INTERVAL_SECONDS=2
WORKFLOW_COMMAND_MAX_ATTEMPTS=10
WORKFLOW_COMMAND_STALE_SECONDS=120
WORKFLOW_EVENT_WEBHOOK_URL=
WORKFLOW_EVENT_WEBHOOK_SECRET=
WORKFLOW_OUTBOX_MAX_ATTEMPTS=10
WORKFLOW_RECONCILE_INTERVAL_SECONDS=300
WORKFLOW_RECONCILE_STALE_SECONDS=120
```

真实链路已在本地 Temporal + PostgreSQL 上验证：启动实例、两次审批、命令 `APPLIED`、
Outbox 事件写入与 Workflow 终态回填均正常。

### 10.5 营销平台接入

- 启动时 `WORKFLOW_SEED_SALES_APPROVALS=1` 会幂等预置：
  - `sales_approval_form:1`
  - `sales_r4_exception`（区域经理 → 销售总监）
  - `sales_r6_related_party`（区域经理 → 销售总监 → 合规官）
  - `sales_duplicate_merge`（区域经理）
- sales-service 通过 `X-Workflow-Internal-Token` + `X-User-*` 调用 workflow API；
  workflow 后端需配置相同的 `WORKFLOW_INTERNAL_TOKEN`。
- sales 审批详情会把 workflow 实例的 `tasks/history` 同步回
  `approval_steps/approval_actions`，原营销审批页面无需改接口。
- 集成测试用例与执行脚本：
  `business/sales-service/docs/INTEGRATION_TEST_WORKFLOW_PLATFORM.md`
  和 `business/sales-service/tests/integration_workflow_platform.py`。
- 页面层：营销审批详情嵌入 `WorkflowApprovalPanel`，通过 sales BFF
  `/approvals/{id}/workflow` 获取表单快照、流程图、历史和操作能力；
  面板实现位于共享包 `packages/workflow-embed`（`@eai/workflow-embed`），
  其他业务平台通过注入自己的 BFF client 复用；
  `/workflow` 继续作为独立设计器/管理工作台，管理员从营销侧边栏进入。
- 实时刷新：sales BFF 提供 `/approvals/stream` 和
  `/approvals/{id}/stream` SSE，前端使用 fetch stream（可带本地 token 或 EAI
  Cookie），流不可用时自动降级为轮询。
