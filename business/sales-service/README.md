# Sales QW2 Service

营销/销售管理平台的 QW2 子系统：商机漏斗、统一待办、工作台与 Temporal 审批。

## 运行模型

```text
sales-backend  FastAPI，只负责鉴权、业务校验、创建审批单、写 Outbox、查询投影、发 Signal
sales-worker   Temporal Worker + Outbox dispatcher + Reconciler
Temporal       Workflow History、Timer、Signal、Activity 重试
sales DB       approval_requests / approval_steps / approval_assignments / approval_actions / todos 等业务投影
```

API 不直接启动 Workflow，也不直接扫描 Outbox。审批创建与 `outbox_events` 在同一事务提交，Worker 消费事件后启动 `SalesApprovalWorkflow`。这样 API 可以水平扩展，不会出现多个进程重复启动同一个审批。

### Workflow 平台审批（EAI-CUSTOM）

`WORKFLOW_PLATFORM_ENABLED=true` 时，新审批改由独立 workflow 平台编排：

```text
sales-backend → workflow-backend /instances
              → Temporal FlowInstanceWorkflow
              → workflow-worker 执行审批 Activity
              → sales 同步 tasks/history 到 approval_steps/approval_actions
```

- `approval_requests.engine=workflow_platform`，并记录 `platform_instance_id`。
- `approval_steps.platform_task_id` 关联 workflow 任务。
- BFF 调用使用 `X-Workflow-Internal-Token` + `X-User-*`。
- 旧审批仍保留 `sales_temporal` 链路。
- 集成测试：`tests/integration_workflow_platform.py`，
  用例说明：`docs/INTEGRATION_TEST_WORKFLOW_PLATFORM.md`。

页面层集成（EAI-CUSTOM）：

- 营销审批详情页保持业务页面不变，嵌入 `WorkflowApprovalPanel`。
- 面板已抽取为共享包 `packages/workflow-embed`（`@eai/workflow-embed`）；
  sales 前端只保留 BFF client 适配器，其他业务平台可直接复用该包。
- `sales-frontend` 镜像通过 Compose 的 `additional_contexts` 注入共享包；
  请使用 `docker compose ... build sales-frontend`，不要直接用前端目录作为构建上下文。
- 本地开发修改共享包后，先在 `packages/workflow-embed` 执行
  `pnpm install && pnpm build`；Docker 构建会自动重编译该包。
- BFF 聚合接口：`GET /api/v1/approvals/{id}/workflow`，返回
  `tasks/form/chart/history/capabilities`。
- 通过/驳回/退回申请人由组件调用 `POST /approvals/{id}/decision`，页面不维护
  workflow task id。
- “退回”不是终态：workflow 平台在同一实例中回到 `start`，为申请人创建待办；
  销售审批单状态为 `returned`，`completed_at` 为空，并保留原审批单号。
- 仅申请人本人可通过 `POST /approvals/{id}/resubmit` 修改原因/证据后重新提交；
  管理员不能代办。BFF 办理 `start` 任务，审批从第一步重新开始，不创建新审批单或新实例。
- “驳回”显式指向 `end`，仍为终态。
- 实时刷新：`GET /api/v1/approvals/stream` 与
  `GET /api/v1/approvals/{id}/stream`（SSE）；前端使用 fetch stream 同时支持
  bearer token 与 EAI Cookie，流不可用时自动降级为 8 秒轮询。
- 管理员侧边栏增加“流程管理”，跳转 `/workflow`，与 sales 共用 EAI SSO。

关键配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WORKFLOW_PLATFORM_ENABLED` | `false` | 新审批是否走 workflow 平台 |
| `WORKFLOW_PLATFORM_BASE_URL` | `http://workflow-backend:8020/api/workflow` | workflow API 地址 |
| `WORKFLOW_PLATFORM_INTERNAL_TOKEN` | 空 | 与 workflow 后端共享的内部令牌 |
| `WORKFLOW_PLATFORM_TIMEOUT_SECONDS` | `10` | 调用 workflow API 的超时 |

### 会签 / 或签

`approval_steps.mode` 支持：

- `sequential`：按 `step_no` 顺序，一人/一个角色池。
- `parallel_all`：同一步所有席位同意才通过；任一驳回立即结束；任一退回申请人则等待申请人修改后重提。
- `parallel_any`：任一席位同意即通过；全部驳回才驳回；任一退回申请人则等待申请人修改后重提。

并行模板步骤使用 `approvers`，每个席位有稳定 `assignment_key`：

```json
{
  "step_no": 1,
  "mode": "parallel_all",
  "sla_hours": 24,
  "approvers": [
    {"role": "regional_manager"},
    {"user_id": "demo-director"},
    {"key": "finance-check", "role": "finance"}
  ]
}
```

决策 API 对并行步骤必须传 `assignment_key`；每个席位有独立待办、状态和转办记录。转办不消耗席位，角色席位转办后收窄为明确用户。取消/过期/失败时未决席位标记 `skipped`，不会自动通过。并行步骤共享一个 SLA 时钟，升级只影响仍未决定的席位。

### 主数据导入

销售主数据页的「数据导入」支持拖拽或点击选择文件：

- Excel：`.xlsx`、`.xlsm`（首个工作表、首行为表头、公式读取缓存值）。
- CSV：UTF-8 BOM 或 GBK，首行为表头。
- 单个文件最大 10MB；支持中文表头别名；可先勾选“仅校验”试跑。
- CSV 模板可直接下载；旧版 `.xls` 需另存为 `.xlsx`。

### 表单控件

商机漏斗与主数据新增/导入对话框中的下拉框、日期框使用统一的自定义控件，不依赖浏览器原生 `<select>` / `<input type="date">` 外观。下拉菜单通过 Portal 定位，避免被弹窗或滚动容器裁切。

## 本地启动

Temporal Server、PostgreSQL、MinIO 由 Docker Compose 提供。仅启动 API 不足以处理审批，必须同时启动 Worker（或设置 `SALES_EMBEDDED_WORKER=true`）。

```bash
# 后端依赖
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# 本地联调：API + 内置 Worker（不要在生产使用）
set SALES_EMBEDDED_WORKER=true
set TEMPORAL_URL=127.0.0.1:7233
python -m uvicorn app.main:app --host 127.0.0.1 --port 3004

# 或分离启动
python -m uvicorn app.main:app --host 127.0.0.1 --port 3004
python -m app.worker
```

## 关键环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TEMPORAL_ENABLED` | `true` | 关闭后审批发起返回 503，已有 Workflow 不丢失 |
| `TEMPORAL_URL` | `temporal:7233` | Temporal Frontend |
| `TEMPORAL_NAMESPACE` | `default` | 命名空间 |
| `TEMPORAL_TASK_QUEUE` | `sales-approval-queue` | Worker 任务队列 |
| `TEMPORAL_RPC_TIMEOUT_SECONDS` | `5` | 启动/Signal/Describe 的硬超时，防止断连挂死 dispatcher |
| `SALES_EMBEDDED_WORKER` | `false` | 本地联调可置 true；生产保持 false |
| `OUTBOX_MAX_ATTEMPTS` | `10` | 启动事件最大重试次数，超过后审批置 failed |
| `TEMPORAL_RECONCILE_INTERVAL_SECONDS` | `300` | 投影对账周期 |
| `TEMPORAL_RECONCILE_STALE_SECONDS` | `120` | 超过该时长未更新的审批参与对账 |

## 健康检查

- `GET /health`：数据库、对象存储、Temporal 实际连接探测。
- `GET /ready`：只检查数据库，供容器就绪探针使用。
- Temporal 不可达时 API 仍可读历史投影；新审批进入 `pending_start`，由 Outbox 重试。

## 测试

```bash
cd backend
python -m pytest -q
python -m ruff check app tests
```

离线测试覆盖契约序列化、并行席位聚合、整体过期、Outbox 退避、对账状态映射。当前 43 个离线测试通过；另有 7 个时间跳跃用例默认跳过。

时间跳跃用例需要 Temporal Test Server（Docker 中的生产 Temporal 不支持时间跳跃）：

```powershell
$env:TEMPORAL_TEST_SERVER = "C:\path\to\temporal-test-server.exe"
python -m pytest tests/test_workflow_time_skipping.py -q
# 7 passed
python -m pytest -q
# 50 passed
```

覆盖顺序/并行 24h SLA 升级、升级后 4h 过期、整体 1h 优先、整体 7 天过期、并行转办后 24h 重置。测试服务器不提交到仓库；未设置 `TEMPORAL_TEST_SERVER` 且 `PATH` 中也没有时自动跳过。完整验收记录见 `docs/designs/2026-10-23-sales-workflow-temporal-refactor.md`。
