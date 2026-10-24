# Sales QW2 Service

营销/销售管理平台的 QW2 子系统：商机漏斗、统一待办、工作台与 Temporal 审批。

## 运行模型

```text
sales-backend  FastAPI，只负责鉴权、业务校验、创建审批单、写 Outbox、查询投影、发 Signal
sales-worker   Temporal Worker + Outbox dispatcher + Reconciler
Temporal       Workflow History、Timer、Signal、Activity 重试
sales DB       approval_requests / approval_steps / approval_actions / todos 等业务投影
```

API 不直接启动 Workflow，也不直接扫描 Outbox。审批创建与 `outbox_events` 在同一事务提交，Worker 消费事件后启动 `SalesApprovalWorkflow`。这样 API 可以水平扩展，不会出现多个进程重复启动同一个审批。

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

离线测试覆盖契约序列化、整体过期、Outbox 退避、对账状态映射；带 Temporal 测试服务器的全链路用例见 `docs/designs/2026-10-23-sales-workflow-temporal-refactor.md`。
