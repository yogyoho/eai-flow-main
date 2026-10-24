# 销售子系统 QW2 详细设计

**版本**：V1.1  
**日期**：2026-10-22  
**范围**：C1 商机漏斗 + A02 统一待办 + A01 我的工作台（本地底座）  
**落地工程**：`business/sales-service`  
**数据库**：`eai-flow-business-db` 中的 `sales` 库  
**审批工作流**：`eai-flow-temporal`（Temporal Server，`temporal:7233`）  
**上游依据**：`D:\eai\2026-10-21-tianma-sales-requirements-analysis.md` 第 5.1、5.2、5.5、6.2、7 章及第 14 章 QW2

> 本文是详细设计，不包含代码实现。目标是让 QW2 在 ERP/CRM/MES/MDM 接口未确定前，先以“本地主数据快照 + 平台自建商机/待办”的方式闭环，后续通过适配器替换数据来源，不推翻页面和流程。
>
> **实施补充（2026-10-23）**：审批工作流的生产级加固、Outbox/Reconciler、整体过期与 Worker 职责边界见 `2026-10-23-sales-workflow-temporal-refactor.md`。

---

## 1. 设计结论

### 1.1 QW2 是什么

QW2 是销售子系统的**执行底座**，先交付三个可真实使用的页面和一套规则引擎：

1. **C1 商机漏斗**：平台自己成为商机主系统，管理 S1–S9 九段状态机、阶段停留、双源赢单概率、R10 撞单、R4/R2/R6 闸门、失标原因和加权预测。
2. **A02 统一待办**：把规则事件、审批、仲裁、补录四类任务收口，支持优先级、SLA、超时升级、批量处理和审计。审批任务由 `eai-flow-temporal` 驱动，A02 只是审批待办的展示与入口。
3. **A01 我的工作台**：按角色聚合今日待办、待我审批、阻断项、超期商机、加权预测和漏斗健康度，并提供下钻和规则生成的今日摘要。

同时提供**最小主数据**（集团/客户/矿井/工作面/产品/联系人/示范面）的本地维护与 CSV / Excel 导入（支持拖拽），支撑 C1 运行。

### 1.2 QW2 不是什么

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| C2 招标雷达、资格自审、标书工厂 | 属于 QW1，依赖公开招标文件和证书/业绩库 | QW1 |
| B01 集团全景卡 | 依赖 MDM/售后/财务；QW2 只做最小主数据 | QW3/接口后 |
| D01 回款作战图 | 依赖合同/财务实收；QW2 不伪造应收 | 接口后 |
| E01 装机台账、R8 改造窗口 | 依赖售后/装机数据 | QW3 |
| F01 领导驾驶舱 | 数据不完整会误导 | QW1–QW3 稳定后 |
| F04/F05 智能问数、AI 自动简报 | QW2 先做规则摘要；LLM 后续接入 | 语义层稳定后 |
| ERP/CRM/MES/MDM 写回或实时同步 | 接口未定 | 接口契约确定后 |
| 完整合同、付款节点、开票、财务对账 | 账务权威在 ERP/财务 | C3/D01 |

> A01 中“本周开标”“本月回款到期”等依赖 C2/D01 的卡片，QW2 以 **“待接入”占位卡**呈现，不显示假数字；不把占位卡计入任何经营口径。

### 1.3 关键产品决策

1. **平台是商机和待办的主系统**：QW2 内新建的商机、阶段历史、概率修正、待办、审批、仲裁均以本服务为权威来源。
2. **客户/工作面是本地快照**：字段带 `source`、`source_id`、`data_as_of`、`completeness`；接口接入后由适配器同步，页面不直接依赖外部字段。
3. **不伪造实时**：导入数据显示“导入于 X 时间”；没有财务数据不显示“实收”；没有 APS 不显示“可承诺交期”。
4. **硬闸门必须可解释**：每次推进返回 `pass / warn / block / not_configured` 和证据；`block` 时 API 与页面同时拒绝，不能只靠前端置灰。
5. **审批用 Temporal，不自己写内存工作流**：R4 例外、R6 关联方、撞单合并等跨人、跨天、需重试的审批，统一由 `eai-flow-temporal` 编排；`sales` 库只保存审批投影和业务事实。
6. **规则配置化**：阶段概率、停留上限、降权幅度、SLA、升级节点、必填字段、审批模板均写配置表，不散落在代码和页面。
7. **所有写操作留痕**：阶段变更、概率修正、撞单裁决、待办处置、审批决定、导出、规则变更全部进审计。

---

## 2. 用户、角色与数据范围

### 2.1 角色

| 角色码 | 名称 | 数据范围 | 主要权限 |
| --- | --- | --- | --- |
| `sales_admin` | 销售系统管理员 | 全部 | 配置、主数据导入、规则、审计 |
| `sales_director` | 营销中心主任 | 全公司 | 查看全部、审批例外、规则配置 |
| `regional_manager` | 大区/服务区经理 | 本区域 | 查看本区域、处理升级、审批 |
| `sales_rep` | 客户经理/销售 | 本人 | 本人商机、待办、概率修正 |
| `data_steward` | 数据 Steward | 授权范围 | 主数据导入、补录、质量任务 |
| `compliance_officer` | 合规/关联方审批人 | 全公司 | 关联方审批；QW2 可由销售总监兼任 |
| `bid_manager` | 投标经理（QW2 只读） | 本区域 | 查看商机、接收待办（C2 在 QW1 完整启用） |

### 2.2 权限点

```text
sales.workbench.read
sales.opportunity.read
sales.opportunity.create
sales.opportunity.update
sales.opportunity.transition
sales.opportunity.rollback
sales.opportunity.probability_override
sales.opportunity.duplicate_resolve
sales.opportunity.export
sales.todo.read
sales.todo.assign
sales.todo.resolve
sales.todo.batch
sales.todo.export
sales.masterdata.read
sales.masterdata.import
sales.rule.read
sales.rule.manage
sales.approval.read
sales.approval.request
sales.approval.decide
sales.approval.cancel
sales.approval.manage
sales.audit.read
```

### 2.3 认证与身份映射

- 复用 Gateway 签发的 JWT，支持 `access_token` HttpOnly Cookie 与 `Authorization: Bearer` 两种方式。
- 共享 `JWT_SECRET_KEY`，与 procurement/asset/project 一致。
- JWT 中的 `sub`、`username` 映射到本服务 `user_profiles`；`role` 和 `permissions` 优先使用 JWT，缺失时回退到本地角色配置。
- 试点期允许本地 `user_profiles` 维护角色和数据范围；正式上线接 SSO/组织主数据。
- 管理员 `role=admin` 绕过权限点，但仍受审计。

### 2.4 数据范围强制

所有列表/详情/统计查询统一经过 `scope_filter(current_user)`：

| 数据范围 | 过滤 |
| --- | --- |
| `all` | 不过滤 |
| `region` | `region_code = current_user.region_code` |
| `self` | `owner_id = current_user.id OR created_by = current_user.id` |

前端只做展示，不作为权限边界；越权访问返回 403。

---

## 3. 核心用户旅程

### 3.1 C1 商机推进

```text
新建商机（S1 线索）
  → S2 初步接触（联系人、需求摘要）
  → S3 需求确认（需求文档、决策链）
  → S4 技术方案/示范（方案/示范面）
  → S5 投标立项（R4 示范面前置、资格预检）
  → S6 报价审批（R2 报价冲突、R6 关联方）
  → S7 投标（双审签、资格关闭）
  → S8 中标/失标（结果、C99 原因）
  → S9 合同生效（合同号、金额、生效日）
```

- 只允许相邻推进，不能跳段。
- 回退只能退到上一阶段，必须填写原因、影响、补救措施。
- 每次推进/回退/概率修正/撞单裁决都写历史，保留规则版本和操作人。
- 阶段超期自动降权，只影响预测，不改变阶段事实。
- 撞单未裁决时，相关商机不计入预测；不强制阻断阶段推进，但必须在 A02 生成仲裁待办。
- R4/R6 阻断可发起 Temporal 审批；审批通过只解除闸门，不自动推进，用户需重新提交 transition。

### 3.2 A02 待办处置

```text
规则/仲裁/补录产生待办
  → 按 severity 排序，计算 SLA
  → 责任人认领/开始处理
  → 处置（补字段/上传证据/裁决）
  → 关闭待办，写 todo_events
  → 超时则逐级升级并通知

审批类待办是 Temporal 工作流的投影：
  → 审批请求落库 + outbox
  → sales-worker 启动 Temporal ApprovalWorkflow
  → 工作流活动创建“待我审批”待办
  → 审批人提交信号 → 活动推进下一步/结束
  → 工作流结束时关闭审批待办并回写闸门证据
  → 审批 SLA/升级由 Temporal timer 驱动，A02 调度器不重复处理
```

### 3.3 A01 工作台

```text
登录 → 按角色加载卡片
  → 今日待办/待我审批/阻断项/超期商机/加权预测/漏斗健康
  → 点击数字下钻到 C1/A02（带筛选条件）
  → 今日摘要（规则生成，附来源和截至时间）
  → 只读汇总，处置动作跳转作业面
```

---

## 4. 总体架构

```mermaid
flowchart LR
  B[Browser /sales] --> N[Nginx]
  N --> FE[sales-frontend]
  N --> BE[sales-backend]
  BE --> DB[(business-db / sales)]
  BE --> JOB[内置调度器<br/>超期/规则扫描]
  BE -- outbox --> DB
  WK[sales-worker<br/>Temporal Worker] --> DB
  WK --> TMP[eai-flow-temporal<br/>temporal:7233]
  BE --> TMP
  TMP --> PEXT[(postgres-ext<br/>Temporal 持久化)]
  BE -. 后续 .-> OS[OntoStudio 本体/证据]
  BE -. 后续 .-> EXT[MDM/CRM/ERP]
```

- 前端：React 19 + Vite + TanStack Router/Table/Query + Tailwind/shadcn，复用 `business/procurement-service/frontend-shadcn` 的工程模式，base path `/sales/`。
- 后端：FastAPI + SQLAlchemy 2 async + asyncpg + Pydantic v2，端口 `3004`；只处理同步业务和审批请求，不在 API 进程内跑长审批。
- 审批工作流：`eai-flow-temporal` 容器（Compose 服务名 `temporal`，`TEMPORAL_URL=temporal:7233`），独立 `sales-worker` 消费 `sales-approval-queue`。
- 数据库：`business-db` 内独立 `sales` 库，保存业务事实和审批投影；Temporal 自身历史存 `postgres-ext`，两者职责分离。
- 调度：A02 规则/超期扫描在 `sales-backend` 或独立 `sales-scheduler` 中执行；多 worker 时用 PostgreSQL advisory lock 保证单实例。审批 SLA/升级由 Temporal timer 负责，不重复扫描。
- 外部系统：QW2 不调用。预留 `CustomerMasterPort`、`ContractPort`、`InstalledBasePort` 等适配器接口，默认 `LocalAdapter`。
- Temporal 不可用时：商机 CRUD、非审批规则、A01 仍可用；需要审批的闸门返回“审批引擎暂不可用”，请求保持 `pending_start`，不静默通过。

---

## 5. 工程结构

```text
business/sales-service/
├── README.md
├── .env.sales.example
├── backend/
│   ├── app/
│   │   ├── app.py                  # FastAPI 工厂/lifespan
│   │   ├── main.py                 # uv 入口
│   │   ├── config.py               # 环境配置
│   │   ├── database.py             # async engine/session
│   │   ├── auth.py                 # JWT + 权限
│   │   ├── models.py               # SQLAlchemy 模型
│   │   ├── schemas.py              # Pydantic 模型
│   │   ├── enums.py                # 阶段/状态/严重度/规则码
│   │   ├── errors.py               # 统一错误码
│   │   ├── routers/
│   │   │   ├── workbench.py
│   │   │   ├── opportunities.py
│   │   │   ├── todos.py
│   │   │   ├── master_data.py
│   │   │   ├── rules.py
│   │   │   ├── approvals.py
│   │   │   ├── notifications.py
│   │   │   └── health.py
│   │   ├── services/
│   │   │   ├── opportunity_service.py
│   │   │   ├── stage_machine.py
│   │   │   ├── rule_engine.py
│   │   │   ├── probability_service.py
│   │   │   ├── duplicate_service.py
│   │   │   ├── todo_service.py
│   │   │   ├── escalation_service.py
│   │   │   ├── workbench_service.py
│   │   │   ├── scope_service.py
│   │   │   ├── audit_service.py
│   │   │   ├── import_service.py
│   │   │   ├── approval_service.py     # 审批请求/投影/API 侧
│   │   │   └── outbox_service.py       # 事务外盒：可靠启动工作流
│   │   ├── workflows/
│   │   │   ├── __init__.py
│   │   │   ├── approval_workflow.py    # ApprovalWorkflow（只依赖 temporalio/数据类）
│   │   │   ├── approval_activities.py  # DB/通知/审计/闸门回写
│   │   │   ├── approval_models.py      # 工作流输入/信号/结果 DTO
│   │   │   ├── constants.py            # task queue / signal / workflow ID
│   │   │   ├── worker.py               # Temporal Worker 入口
│   │   │   └── outbox_dispatcher.py    # 启动/重试工作流
│   │   ├── jobs/
│   │   │   └── scheduler.py            # 仅规则/超期/仲裁，不含审批
│   │   └── seed/
│   │       ├── demo.py
│   │       ├── lost_reasons.py
│   │       ├── rules.py
│   │       └── approval_definitions.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── workflow/                   # Temporal time-skipping/replay
│   │   └── conftest.py
│   ├── alembic/                    # Sprint 1 结束前补 baseline
│   ├── pyproject.toml
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── components/layout/      # 复用 procurement shell
    │   ├── components/sales/       # PageHead/MetricStrip/Panel/StageRail...
    │   ├── features/sales/
    │   │   ├── workbench/
    │   │   ├── opportunities/
    │   │   ├── todos/
    │   │   ├── approvals/          # 审批抽屉/步骤时间线/决定表单
    │   │   └── master-data/
    │   ├── lib/api/sales.ts
    │   ├── routes/_authenticated/sales/
    │   │   ├── route.tsx
    │   │   ├── index.tsx           # A01
    │   │   ├── opportunities.tsx   # C1
    │   │   ├── todos.tsx           # A02
    │   │   └── master-data.tsx
    │   ├── main.tsx
    │   └── styles/
    ├── vite.config.ts
    ├── package.json
    ├── nginx.conf
    └── Dockerfile
```

---

## 6. 数据模型

### 6.1 建模约定

- 库：`sales`；schema：`public`（与现有 business 服务一致）。
- 主键：`uuid`（`gen_random_uuid()` 或应用生成）。
- 时间：`timestamptz`，存 UTC；展示按 `Asia/Shanghai`。
- 金额：`numeric(18,2)`，默认人民币；页面统一“元/万元/亿元”格式化，入库始终为元。
- 枚举：数据库用 `varchar` + 应用枚举校验，便于演进；状态变更必须走服务层。
- 软删除：业务表不物理删除，用 `status` 或 `is_active`；审计不可删。
- 并发：`opportunities.version` 整数，更新使用 `WHERE version = :expected`，冲突返回 409。
- 来源：`source`（`manual/import/demo/external`）、`source_system`、`source_id`、`data_as_of`、`confidence`。
- 审计：所有写操作记录 `audit_events` 前后快照。
- 审批双写边界：`sales` 库是**审批投影和业务事实**的权威；Temporal 是**流程编排和定时器**的权威。工作流活动必须幂等写投影，不能出现“Temporal 已通过、页面还显示审批中”。
- 可靠启动：审批请求与 `outbox_events` 在同一数据库事务内提交；`outbox_dispatcher` 负责启动 Temporal，失败重试，避免“DB 成功、工作流丢失”。

### 6.2 核心 ER

```mermaid
erDiagram
  ORG_UNITS ||--o{ USER_PROFILES : has
  CUSTOMER_GROUPS ||--o{ CUSTOMERS : contains
  CUSTOMERS ||--o{ MINES : owns
  MINES ||--o{ WORKFACES : contains
  CUSTOMERS ||--o{ OPPORTUNITIES : owns
  WORKFACES ||--o{ OPPORTUNITIES : relates
  CUSTOMER_GROUPS ||--o{ PILOT_PROJECTS : has
  OPPORTUNITIES ||--o{ OPPORTUNITY_STAGE_HISTORY : changes
  OPPORTUNITIES ||--o{ OPPORTUNITY_PROBABILITY_HISTORY : adjusts
  OPPORTUNITIES ||--o{ OPPORTUNITY_GATE_CHECKS : checks
  OPPORTUNITIES ||--o{ OPPORTUNITY_DUPLICATES : duplicate
  OPPORTUNITIES ||--o{ TODOS : generates
  TODOS ||--o{ TODO_EVENTS : logs
  TODOS ||--o{ TODO_ESCALATIONS : escalates
  APPROVAL_DEFINITIONS ||--o{ APPROVAL_REQUESTS : instantiates
  APPROVAL_REQUESTS ||--o{ APPROVAL_STEPS : has
  APPROVAL_REQUESTS ||--o{ APPROVAL_ACTIONS : records
  OPPORTUNITIES ||--o{ APPROVAL_REQUESTS : needs
  APPROVAL_REQUESTS ||--o{ TODOS : projects
```

### 6.3 表设计

#### 6.3.1 组织与用户

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `org_units` | `id, code, name, type, parent_id, region_code, is_active` | 公司/大区/服务区/团队 |
| `user_profiles` | `id, username, display_name, role_code, org_id, region_code, data_scope, is_active, last_login_at` | `id` 对齐 JWT `sub` |

#### 6.3.2 最小主数据

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `customer_groups` | `id, name, credit_code, parent_id, region_code, is_new_customer, source, source_id, data_as_of, completeness` | 集团/子集团；`is_new_customer` 供 R4 |
| `customers` | `id, group_id, name, credit_code, region_code, service_org_id, address, related_party_status, source, source_id, data_as_of, completeness` | `related_party_status`: `unknown/no/yes` |
| `mines` | `id, customer_id, group_id, name, region_code, capacity, status, source, source_id, data_as_of` | 矿井 |
| `workfaces` | `id, mine_id, name, mining_height_m, conditions, status, source, source_id, data_as_of` | 工作面，最小经营单元 |
| `products` | `id, product_line, model, name, is_active, source, source_id` | 产品线/型号 |
| `contacts` | `id, customer_id, name, title, role, influence, stance, phone, email, source, data_as_of` | 关键人/决策链 |
| `opportunity_contacts` | `opportunity_id, contact_id, role, is_primary` | 商机关联联系人 |
| `pilot_projects` | `id, customer_group_id, workface_id, name, completed_at, effect, evidence_url, source, data_as_of` | R4 示范面 |

#### 6.3.3 商机

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 主键 |
| `opportunity_no` | varchar(32) unique | `OPP-YYYYMM-####` |
| `name` | varchar(200) | 商机名称 |
| `customer_id` | uuid FK | 必填 |
| `mine_id` | uuid FK nullable | 可空 |
| `workface_id` | uuid FK nullable | 可空；R10 匹配键之一 |
| `product_line` | varchar(80) | 必填；R10 匹配键之一 |
| `amount` | numeric(18,2) | 预计金额，元 |
| `currency` | varchar(8) | 默认 CNY |
| `stage` | varchar(4) | `S1`–`S9` |
| `status` | varchar(16) | `active/won/lost/closed` |
| `result` | varchar(8) nullable | `won/lost`，S8 回填 |
| `stage_entered_at` | timestamptz | 进入当前阶段时间 |
| `stage_due_at` | timestamptz nullable | 阶段停留上限 |
| `expected_close_date` | date | 预计成交日 |
| `owner_id` | uuid FK | 负责人 |
| `owner_org_id` | uuid FK | 归属组织 |
| `region_code` | varchar(32) | 数据范围 |
| `source` | varchar(16) | `manual/import/demo/external` |
| `source_id` | varchar(128) nullable | 外部 ID |
| `rule_probability` | numeric(5,2) | 规则概率，0–100 |
| `manual_probability` | numeric(5,2) nullable | 人工修正值 |
| `manual_reason` | text nullable | 偏差 >15pct 必填 |
| `effective_probability` | numeric(5,2) | 生效概率 |
| `probability_source` | varchar(8) | `rule/manual` |
| `forecast_excluded` | boolean | 撞单/关闭/异常时排除预测 |
| `duplicate_of_id` | uuid nullable | 被合并到的主商机 |
| `lost_reason_code` | varchar(8) nullable | C01–C99 |
| `lost_reason_note` | text nullable | C99 必填 |
| `contract_no` | varchar(64) nullable | S9 必填 |
| `contract_amount` | numeric(18,2) nullable | S9 必填 |
| `contract_effective_date` | date nullable | S9 必填 |
| `version` | int | 乐观锁 |
| `created_by/at, updated_by/at` | | 审计字段 |

索引：

```text
(stage, status)
(owner_id, status)
(customer_id, workface_id, product_line)
(region_code, product_line, expected_close_date)
(expected_close_date)
```

#### 6.3.4 历史与规则结果

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `opportunity_stage_history` | `id, opportunity_id, from_stage, to_stage, action, reason, impact, remedy, rule_version, operator_id, created_at` | 推进/回退全历史 |
| `opportunity_probability_history` | `id, opportunity_id, rule_probability, manual_probability, manual_reason, effective_probability, changed_by, created_at` | 概率修正历史 |
| `opportunity_gate_checks` | `id, opportunity_id, gate_code, status, message, evidence_json, rule_version, checked_by, checked_at` | 每次闸门结果 |
| `opportunity_duplicates` | `id, opportunity_id, duplicate_opportunity_id, match_keys, status, resolution, primary_opportunity_id, resolved_by, resolved_at, reason` | R10 撞单案件 |
| `quote_conflicts` | `id, opportunity_id, status, description, resolution, resolved_by, resolved_at` | R2 最小记录 |
| `approval_definitions` | `id, code, name, version, mode, steps_json, is_active, effective_from, effective_to` | 审批模板，按版本冻结 |
| `approval_requests` | `id, request_no, definition_code, definition_version, opportunity_id, gate_code, status, current_step, reason, evidence_json, payload_json, requested_by, requested_at, workflow_id, workflow_run_id, started_at, completed_at, expires_at, failure_reason, version` | 审批请求 + Temporal 句柄 |
| `approval_steps` | `id, request_id, step_no, mode, approver_role, approver_id, status, decision, comment, sla_due_at, decided_at, escalated_at, escalation_level, idempotency_key` | 审批步骤投影；并行步骤共用一条步骤记录 |
| `approval_assignments` | `id, step_id, request_id, step_no, assignment_key, approver_role, approver_id, status, decision, comment, decided_at, delegated_from, idempotency_key` | 并行步骤的席位投影；`assignment_key` 唯一 |
| `approval_actions` | `id, request_id, step_no, assignment_key, action, actor_id, actor_role, comment, idempotency_key unique, created_at` | 审批动作幂等记录；并行步骤记录具体席位 |
| `outbox_events` | `id, aggregate_type, aggregate_id, event_type, payload_json, status, attempts, next_retry_at, last_error, created_at, processed_at` | 可靠启动/重试工作流 |

审批状态：`pending_start`、`running`、`approved`、`rejected`、`returned`、`cancelled`、`expired`、`failed`。  
审批动作：`approve`、`reject`、`return`、`cancel`、`delegate`（`delegate` QW2 可选）。

#### 6.3.5 待办

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 主键 |
| `todo_no` | varchar(32) unique | `TODO-YYYYMM-####` |
| `type` | varchar(20) | `rule_event/approval/arbitration/data_fix` |
| `severity` | varchar(10) | `blocker/high/medium/low` |
| `title` | varchar(200) | 标题 |
| `description` | text | 说明 |
| `object_type` | varchar(32) | `opportunity/approval/duplicate/...` |
| `object_id` | uuid | 关联对象 |
| `source_rule` | varchar(16) nullable | R2/R4/R6/R9/R10/STAGE |
| `assignee_id` | uuid nullable | 责任人 |
| `assignee_role` | varchar(32) nullable | 角色池 |
| `status` | varchar(16) | `open/in_progress/resolved/cancelled` |
| `due_at` | timestamptz | SLA 截止 |
| `sla_minutes` | int | SLA 时长 |
| `escalation_level` | int | 0–3 |
| `dedupe_key` | varchar(200) | 去重键 |
| `resolution` | text nullable | 处置说明 |
| `resolved_at` | timestamptz nullable | 完成时间 |
| `created_by/at, updated_by/at` | | 审计字段 |

索引/约束：

```text
(assignee_id, status, due_at)
(type, severity, status)
(object_type, object_id)
UNIQUE (dedupe_key) WHERE status IN ('open','in_progress')
```

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `todo_events` | `id, todo_id, event_type, from_status, to_status, operator_id, note, created_at` | 处置历史 |
| `todo_escalations` | `id, todo_id, level, from_assignee, to_assignee, reason, created_at` | 升级历史 |
| `role_load_limits` | `role_code, max_open, updated_at` | 角色负载上限 |

#### 6.3.6 配置、通知、审计

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `rule_configs` | `id, rule_code, version, enabled, config_json, effective_from, effective_to, created_by, created_at` | 规则版本 |
| `lost_reason_codes` | `code, label, requires_note, is_active, sort_order` | C01–C99 码表 |
| `workbench_card_configs` | `role_code, card_code, sort_order, enabled` | 角色卡片 |
| `notifications` | `id, user_id, type, title, body, link, read_at, created_at` | 站内信 |
| `audit_events` | `id, actor_type, actor_id, action, object_type, object_id, before_json, after_json, request_id, created_at` | 不可篡改审计 |
| `number_sequences` | `prefix, period, next_value` | 单号生成 |
| `import_jobs` | `id, type, file_name, total, success, failed, status, created_by, created_at` | CSV / Excel 导入批次 |
| `saved_views` | `id, user_id, page, name, filters_json, is_default` | 可选，P1 |

### 6.4 状态枚举

| 枚举 | 值 |
| --- | --- |
| 商机阶段 | `S1` 线索、`S2` 初步接触、`S3` 需求确认、`S4` 技术方案/示范、`S5` 投标立项、`S6` 报价审批、`S7` 投标、`S8` 中标/失标、`S9` 合同生效 |
| 商机状态 | `active`、`won`、`lost`、`closed` |
| 待办类型 | `rule_event`、`approval`、`arbitration`、`data_fix` |
| 严重度 | `blocker`、`high`、`medium`、`low` |
| 待办状态 | `open`、`in_progress`、`resolved`、`cancelled` |
| 闸门结果 | `pass`、`warn`、`block`、`not_configured` |
| 关联方状态 | `unknown`、`no`、`yes` |
| 概率来源 | `rule`、`manual` |
| 审批状态 | `pending_start`、`running`、`approved`、`rejected`、`returned`、`cancelled`、`expired`、`failed` |
| 审批动作 | `approve`、`reject`、`return`、`cancel`、`delegate` |
| 审批步骤模式 | `sequential`、`parallel_all`、`parallel_any` |
| 审批步骤状态 | `pending`、`active`、`approved`、`rejected`、`returned`、`escalated`、`expired` |
| Outbox 状态 | `pending`、`processing`、`processed`、`failed`、`dead` |

---

## 7. 商机状态机

### 7.1 阶段定义

| 阶段 | 名称 | 进入必填 | 推进闸门 | 停留上限 | 可回退 |
| --- | --- | --- | --- | --- | --- |
| S1 | 线索 | 来源、客户/工作面、产品线、金额、预计成交日、负责人 | 来源可追溯 | 不限 | 否 |
| S2 | 初步接触 | 联系人、需求摘要 | 联系人已关联 | 30 天 | 到 S1 |
| S3 | 需求确认 | 需求文档/链接、决策链 | 决策链至少 1 人 | 30 天 | 到 S2 |
| S4 | 技术方案/示范 | 方案/示范面安排 | 方案已启动 | 35 天 | 到 S3 |
| S5 | 投标立项 | Go/No-Go 结论、投标策略 | R4 示范面（新客户集团） | 15 天 | 到 S4 |
| S6 | 报价审批 | 报价版本/金额 | R2 报价冲突、R6 关联方 | 10 天 | 到 S5 |
| S7 | 投标 | 标书提交/待开标 | 资格关闭、双审签（QW1 接入后） | 15 天 | 到 S6 |
| S8 | 中标/失标 | 结果、合同/失标原因 | R9 失标原因 | 不限 | 到 S7（管理员） |
| S9 | 合同生效 | 合同号、合同金额、生效日 | 合同字段完整 | 不限 | 否 |

### 7.2 推进校验顺序

`POST /opportunities/{id}/transition` 按以下顺序执行，任一步失败即返回，不写业务状态：

1. 认证、权限、数据范围。
2. 读取商机并校验 `version`（乐观锁）。
3. 校验目标阶段是否相邻；S8 需带 `result`。
4. 校验当前阶段必填字段。
5. 执行闸门规则，汇总 `pass/warn/block/not_configured`。
6. 有 `block` 则返回 422，附带 `gate_results` 和处理入口；若该闸门支持例外审批，额外返回 `approval_required=true`、`approval_template`、`approval_request_id`（已发起时）。
7. 审批通过只解除闸门，**不自动推进阶段**；用户必须再次提交 transition，重新执行全部校验，避免绕过阶段必填和并发检查。
8. 更新阶段、`stage_entered_at`、`stage_due_at`、概率；写阶段历史、闸门结果。
9. 关闭已解决的阶段待办；为新的 `warn/block` 生成待办（幂等）。
10. 写审计事件，返回详情 + 闸门结果 + 新待办 + 审批状态（如有）。

### 7.3 回退

- 只允许 `S2→S1`、`S3→S2`、`S4→S3`、`S5→S4`、`S6→S5`、`S7→S6`。
- 必填：`reason`（原因）、`impact`（影响）、`remedy`（补救措施）。
- 回退后阶段停留重新计时；概率按新阶段重算；历史保留。
- `S8` 结果纠错仅管理员可操作，必须写原因，不删历史。

### 7.4 S8/S9 规则

- `S8` 必须回填 `result=won/lost`。
- `lost`：`lost_reason_code` 必填；`C99` 必须写 `lost_reason_note`；状态置 `lost`，退出预测。
- `won`：可停留在 S8“中标待签”；进入 S9 必须补 `contract_no`、`contract_amount`、`contract_effective_date`。
- `S9`：状态 `won`，`forecast_excluded=true`，不再计入在途商机。

---

## 8. 概率与预测

### 8.1 双源概率

```text
rule_probability = stage_base_probability
                 - overdue_penalty_pp
                 + signal_adjustment_pp   # QW2 暂为 0，预留 R12
                 （下限 5，上限 100）

effective_probability = manual_probability if not null else rule_probability
probability_source   = manual if manual_probability is not null else rule

deviation_pp = manual_probability - rule_probability
if abs(deviation_pp) > 15 and manual_reason is empty -> 422
```

### 8.2 阶段基准概率（联调种子值，业务确认后改配置）

| 阶段 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 基准概率 | 10% | 20% | 35% | 50% | 60% | 70% | 80% | 90% | 100% |

> 这些数值只用于联调和演示，不作为经营承诺；正式值由业务在 `rule_configs` 中确认并版本化。

### 8.3 超期降权

- 阶段上限：S2 30 天、S3 30 天、S4 35 天、S5 15 天、S6 10 天、S7 15 天。
- 超过上限后，`overdue_penalty_pp` 默认 15pp，最高 20pp；可按阶段配置。
- 降权只影响 `rule_probability`，不改变阶段事实，也不覆盖人工值。
- 前端同时展示“规则值 / 人工值 / 生效值”，超期标记与降权原因可解释。

### 8.4 加权预测

```text
weighted_forecast = Σ(amount × effective_probability / 100)
```

- 范围：`status=active`，`forecast_excluded=false`，`stage in S1..S8`。
- 排除：`S9`、`lost`、`closed`、撞单未裁决、`forecast_excluded=true`。
- 维度：区域、产品线、负责人、阶段。
- 页面必须标注“预测非承诺值”和“数据截至时间”。

### 8.5 阶段统计

| 指标 | 口径 |
| --- | --- |
| 在途商机金额 | `stage in S1..S8 AND status=active AND forecast_excluded=false` 的金额合计 |
| 阶段数量/金额 | 按 `stage` 聚合 |
| 阶段转化率 | 进入下一阶段商机数 ÷ 上一阶段有效商机数；回退计入回退后阶段 |
| 平均停留 | `now - stage_entered_at` 的平均天数 |
| 超期商机 | `stage_due_at < now` 且 `status=active` |
| 撞单预警 | `opportunity_duplicates.status=pending` 的数量 |

---

## 9. 规则与闸门

### 9.1 QW2 规则清单

| 规则 | 触发 | 结果 | QW2 实现 |
| --- | --- | --- | --- |
| R4 示范面前置 | `S4→S5` 且客户集团 `is_new_customer=true` | 无关联示范面则 `block`，可申请例外审批 | 查 `pilot_projects`；例外走 Temporal `R4_EXCEPTION` |
| R2 报价冲突 | `S5→S6` | 存在未裁决冲突则 `block` | 查 `quote_conflicts`；冲突由本地记录/后续 C3 接入；裁决后可重试 |
| R6 关联方审批 | `S6→S7` | 关联方且无专用审批则 `block`，可走关联方审批 | 查 `customers.related_party_status` + Temporal `R6_RELATED_PARTY` |
| R9 失标原因 | S8 回填失标 | 缺原因/ C99 无说明则 `block` | 码表 `lost_reason_codes` |
| R10 撞单 | 新建/编辑/推进 | 命中则 `warn` + 预测排除 + 仲裁待办 | 同客户 + 同工作面 + 同产品线，排除自身/已关闭 |
| STAGE_FIELDS | 每次推进 | 缺必填则 `block` | 阶段必填字段表 |
| STAGE_OVERDUE | 定时扫描 | `warn` + 降权 + 待办 | 调度器扫描 |
| R12 资本开支信号 | 后续 | 调整概率 | QW2 预留，`signal_adjustment_pp=0` |
| R8 改造窗口 | 后续 | 生成线索 | 不在 QW2 |

> R6 的 `related_party_status=unknown` 不直接发起审批，先阻断并生成 `data_fix` 待办，由数据 Steward 确认 `no`/`yes`；确认 `yes` 后再走 `R6_RELATED_PARTY`，确认 `no` 直接通过。

### 9.2 闸门返回结构

```json
{
  "code": "R4",
  "status": "block",
  "message": "新客户集团投标立项前须有关联示范面",
  "evidence_required": true,
  "action": "link_pilot_project_or_request_exception",
  "approval_template": "R4_EXCEPTION",
  "approval_request_id": null,
  "details": {"customer_group_id": "...", "pilot_count": 0}
}
```

- `pass`：可继续。
- `warn`：可继续，但生成待办/提示。
- `block`：不可继续；API 返回 422，页面按钮不可用并给出处理入口。
- `not_configured`：依赖模块未接入；页面明确显示“未配置”，不得静默当作通过。QW2 中 R2/R6 通过本地记录实现，不使用该状态；后续 C3 接入时可切换。
- `action=link_pilot_project_or_request_exception`：允许关联示范面，或发起 `R4_EXCEPTION` 审批。
- `action=request_related_party_approval`：发起 `R6_RELATED_PARTY` 审批。
- 审批通过后，闸门读取 `approval_requests.status=approved` 且 `gate_code` 匹配；过期/取消/退回的审批不算通过。每次通过都记录 `approval_request_id` 到 `opportunity_gate_checks.evidence_json`。

### 9.3 规则版本

- `rule_configs` 每次修改生成新 `version`，旧版本 `effective_to` 关闭。
- 阶段历史记录 `rule_version`；历史判定按当时版本复算，不用最新规则改写历史。
- 规则变更需 `sales.rule.manage` 权限，写审计。

### 9.4 审批工作流（Temporal / eai-flow-temporal）

#### 9.4.1 为什么用 Temporal

审批不是一次 HTTP 调用，而是跨人、跨天、可能退回、可能超时、必须可恢复的流程。如果放在 `sales-backend` 的内存或数据库轮询里，会面临：

- 服务重启后审批状态丢失或重复推进；
- 多副本时重复发待办、重复升级；
- 超时升级靠扫描，时间精度差；
- 审批历史与业务状态容易不一致。

因此 QW2 的审批统一交给已有的 **`eai-flow-temporal`** 容器：

- Compose 服务名：`temporal`
- 容器名：`eai-flow-temporal`
- 地址：`temporal:7233`（本机调试可用 `localhost:7233`）
- Namespace：`default`
- Task Queue：`sales-approval-queue`
- Workflow ID：`sales-approval-{approval_request_id}`

Temporal 负责“流程走到哪、下一步是谁、什么时候升级”；`sales` 库负责“审批单是什么、谁批了什么、闸门是否解除”。两者通过幂等活动同步。

#### 9.4.2 运行拓扑

```text
sales-backend
  ├─ 创建 approval_request（pending_start）
  ├─ 同事务写 outbox_events（approval.start）
  └─ 提供审批查询/决定 API（只写 DB + 发信号）

sales-worker（独立容器，同一后端镜像）
  ├─ outbox_dispatcher：读 outbox，启动 Temporal Workflow
  ├─ Temporal Worker：消费 sales-approval-queue
  ├─ activities：写 DB、发通知、写审计、回写闸门
  └─ reconciler：对账 running 审批与 Temporal 状态

eai-flow-temporal
  ├─ Workflow history / timers
  └─ 持久化在 postgres-ext
```

- 生产默认 **API 与 Worker 分离**；`sales-backend` 不跑 Temporal Worker，避免 API 重启影响审批。
- 本地开发可设 `SALES_EMBEDDED_WORKER=true`，在 `sales-backend` lifespan 内启动 Worker + outbox dispatcher，减少容器数量。
- Temporal 只在内网暴露；浏览器不直接连接 Temporal，所有审批动作经 `sales-backend` 鉴权后发信号。

#### 9.4.3 审批模板

`approval_definitions` 存模板，`steps_json` 在发起时**快照**进工作流输入。运行中的审批不受模板后续修改影响。

| 模板 | 用途 | 步骤（初始建议） |
| --- | --- | --- |
| `R4_EXCEPTION` | 新客户集团无示范面，申请投标立项例外 | 大区经理 24h → 销售总监 24h |
| `R6_RELATED_PARTY` | 关联方交易专用审批 | 大区经理 24h → 销售总监 24h → 合规审批人 48h |
| `DUPLICATE_MERGE` | 跨区域/跨负责人撞单合并 | 大区经理 24h；跨区域再加销售总监 24h |
| `PROBABILITY_OVERRIDE` | 预留；QW2 概率偏差只要求理由，不走审批 | 暂不启用 |
| `QUOTE_DISCOUNT` | 预留，C3 报价审批接入 | 暂不启用 |

步骤模式：

- `sequential`：按 step_no 顺序，一步一人/一个角色池，沿用 `approver_role` / `approver_id`。
- `parallel_all`（会签）：同一步多个席位全部同意才通过；任一席位驳回/退回，步骤立即结束。
- `parallel_any`（或签）：同一步任一席位同意即通过；全部席位驳回才驳回；任一席位退回，步骤立即结束。

并行步骤使用 `approvers` 列表声明席位：

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

- 席位键 `assignment_key` 必须稳定且在同一步内唯一：缺省为 `role:<role>` 或 `user:<user_id>`，也可由模板显式提供 `key`。
- 每个席位独立投影到 `approval_assignments`，独立待办、独立决策、独立转办；决策 API 必须携带 `assignment_key`。
- 转办只改变席位当前处理人，不消耗席位最终结论；角色席位转办后收窄为明确用户席位，仅受转办人或管理员可操作。
- 并行步骤共用一个步骤 SLA 时钟；任一转办会把步骤时钟重置为 24 小时，升级只影响仍未决定的席位。
- 升级/过期/取消/失败时未决席位标记 `skipped`，绝不自动通过。

QW2 种子模板仍使用 `sequential`；`parallel_all/parallel_any` 已由 Temporal 工作流与投影层实现，供后续报价/合同审批直接复用。

#### 9.4.4 工作流状态与信号

审批状态：

```text
pending_start → running → approved
                    ├── rejected
                    ├── returned
                    ├── cancelled
                    ├── expired
                    └── failed
```

- `pending_start`：DB 已落库，Temporal 尚未启动；由 outbox 重试。
- `running`：工作流已启动，等待当前步骤决定。
- `approved/rejected/returned`：终态；`returned` 表示退回申请人补充，需新建请求重新提交。
- `cancelled`：申请人/管理员撤回。
- `expired`：超过最大审批时限，未自动通过。
- `failed`：工作流启动失败或不可恢复错误，需管理员处理。

信号：

| 信号 | 参数 | 说明 |
| --- | --- | --- |
| `decision` | `step_no, assignment_key?, action, actor_id, actor_role, comment, idempotency_key, delegate_to?` | 同意/驳回/退回/转办；并行步骤必须带席位键 |
| `cancel` | `reason, actor_id` | 撤回 |

查询：

| 查询 | 返回 |
| --- | --- |
| `get_state` | 当前步骤、步骤状态、已做决定、是否终态 |

> 页面不依赖 Temporal Query 渲染；页面读 `sales` 库投影。Query 只用于运维/对账。

#### 9.4.5 工作流主循环（伪代码）

```python
@workflow.defn(name="SalesApprovalWorkflow")
class SalesApprovalWorkflow:
    @workflow.run
    async def run(self, req: ApprovalInput) -> ApprovalResult:
        await workflow.execute_activity(mark_running, req, ...)
        for step in req.steps:
            await workflow.execute_activity(activate_step, ActivateStep(req, step), ...)
            try:
                await workflow.wait_condition(
                    lambda: self._decision_for(step.step_no) is not None,
                    timeout=timedelta(hours=step.sla_hours),
                )
            except asyncio.TimeoutError:
                await workflow.execute_activity(escalate_step, EscalateStep(req, step), ...)
                try:
                    await workflow.wait_condition(
                        lambda: self._decision_for(step.step_no) is not None,
                        timeout=timedelta(hours=step.escalation_hours),
                    )
                except asyncio.TimeoutError:
                    await workflow.execute_activity(finalize_expired, req, ...)
                    return ApprovalResult(status="expired")
            decision = self._decision_for(step.step_no)
            if decision.action == "reject":
                await workflow.execute_activity(finalize_rejected, RejectInput(req, step, decision), ...)
                return ApprovalResult(status="rejected")
            if decision.action == "return":
                await workflow.execute_activity(finalize_returned, ReturnInput(req, step, decision), ...)
                return ApprovalResult(status="returned")
            # approve：推进下一步
        await workflow.execute_activity(finalize_approved, req, ...)
        return ApprovalResult(status="approved")
```

约束：

- 工作流代码只 import `temporalio` 和 DTO，不 import FastAPI/SQLAlchemy，使用默认 sandbox。
- 所有时间用 `workflow.now()`；不在工作流里读数据库、发 HTTP、生成随机数。
- 所有 DB 写入、通知、审计都在 activity 中完成。
- 审批通过/拒绝/退回后，由 activity 写投影；工作流返回值只作对账依据。

#### 9.4.6 活动与幂等

| 活动 | 作用 | 幂等策略 |
| --- | --- | --- |
| `mark_running` | 请求状态改 `running`，记录 workflow/run id | 状态已是 `running` 直接返回 |
| `activate_step` | 当前步骤置 `active`，创建/更新审批待办、发通知 | `dedupe_key=approval:{request_id}:{step_no}` |
| `record_decision` | 写 `approval_actions`，更新 `approval_steps` | `idempotency_key` 唯一；`ON CONFLICT DO NOTHING` |
| `escalate_step` | 升级步骤责任人/角色，更新待办 severity、发通知 | `step_no + escalation_level` 唯一 |
| `finalize_approved` | 请求 `approved`，关闭审批待办，回写闸门证据 | 已终态则 no-op |
| `finalize_rejected` | 请求 `rejected`，关闭待办，写审计 | 已终态则 no-op |
| `finalize_returned` | 请求 `returned`，关闭待办，通知申请人 | 已终态则 no-op |
| `finalize_expired` | 请求 `expired`，关闭待办，通知管理员 | 已终态则 no-op |
| `mark_failed` | 请求 `failed`，记录错误，通知管理员 | 仅非终态可写 |
| `write_audit` | 审计事件 | `request_id + action + step_no` 幂等 |
| `notify` | 站内信 | `notification_key` 唯一 |

活动重试策略（初始）：

```text
ScheduleToStart: 5 minutes
StartToClose:    30 seconds
ScheduleToClose: 1 hour
Retry:           maximum_attempts=5, initial_interval=2s, backoff=2.0
```

- 活动抛业务异常（如“步骤已决定”）用 `ApplicationError(non_retryable=True)`，避免无意义重试。
- 活动写 DB 必须短事务；通知失败不回滚审批事实，进入通知重试。
- 所有活动参数带 `approval_request_id`，日志用 `workflow_id/run_id/step_no` 关联。

#### 9.4.7 可靠启动：Outbox

不允许“先写 DB，再直接 `start_workflow`”的双写：

1. `POST /opportunities/{id}/approvals` 在**一个事务**内写 `approval_requests(status=pending_start)` 和 `outbox_events(event_type=approval.start)`。
2. `outbox_dispatcher` 用 `SELECT ... FOR UPDATE SKIP LOCKED` 取事件，启动工作流。
3. 启动成功：更新请求 `status=running`、`workflow_id`、`workflow_run_id`，outbox `processed`。
4. 启动失败：`attempts++`、`next_retry_at` 指数退避（1m/5m/15m/1h/6h），超过 10 次置 `failed` 并通知管理员。
5. 重复启动：`workflow_id` 固定为 `sales-approval-{approval_request_id}`，使用 `ALLOW_DUPLICATE_FAILED_ONLY`；若已存在，读取 handle，视为成功。

这样即使 API 返回成功、Temporal 暂时不可用，审批也不会丢；页面显示“等待审批引擎”，outbox 自动补发。

#### 9.4.8 SLA、升级与超时

- 每个步骤有 `sla_hours` 和 `escalation_hours`，由模板配置。
- 到 `sla_hours`：Temporal timer 触发 `escalate_step`，待办升级到上一级角色，`escalation_level++`，通知。
- 到 `escalation_hours`：再次升级或置 `expired`。
- `expired` **不自动通过**；闸门保持阻断，需重新发起审批。
- 最大审批时限 `expires_at`（默认 7 天）写入工作流输入；超时由工作流 timer 结束为 `expired`。
- 审批 SLA 由 Temporal 负责；A02 调度器**跳过** `type=approval`，避免双升级。

#### 9.4.9 失败、对账与降级

| 场景 | 行为 |
| --- | --- |
| Temporal 未启用（`TEMPORAL_ENABLED=false`） | 审批 API 返回 503；不创建无法执行的审批 |
| Temporal 暂时不可达 | 审批请求可落 `pending_start`，outbox 重试；页面显示“等待审批引擎” |
| Worker 重启 | Temporal 保留 history；Worker 恢复后继续；活动幂等 |
| API 重启 | 不影响工作流；页面从 DB 读投影 |
| 工作流完成但 DB 未终态 | `reconciler` 每 5 分钟对账，调用 `describe/result` 后补写终态 |
| DB 显示 running 但工作流不存在 | 标记 `failed`，通知管理员；不自动通过 |
| 重复点击审批 | `idempotency_key` 去重；返回已有结果，不重复推进 |

对账任务只处理 `running` 且超过 2 分钟未更新的请求，避免与正常活动竞争；补写终态走同一组幂等活动。

#### 9.4.10 版本与兼容

- 审批模板版本：`approval_definitions.version`；发起时快照，运行中不变。
- 工作流代码变更：使用 `workflow.patched("sales-approval-vX")`；删除旧分支前确保无运行中 history。
- 信号名、参数结构只增不改；新增字段给默认值。
- CI 增加 workflow replay 测试；用历史样本回放，防止非确定性代码。
- 禁止在 workflow 中读取当前时间、随机数、环境变量、数据库；全部通过输入或 activity。

#### 9.4.11 安全与审计

- 只有 `sales-backend` 能连接 Temporal；Temporal 不暴露公网。
- 审批决定 API 校验：登录、`sales.approval.decide`、数据范围、当前步骤、角色匹配、是否本人申请（默认禁止自批）。
- `idempotency_key` 由前端每次点击生成（`crypto.randomUUID()`），服务端唯一约束。
- 每次发起/决定/升级/撤回/终态都写 `audit_events` 和 `approval_actions`。
- 审批意见、拒绝理由、退回说明必填规则：
  - `reject`：comment 必填；
  - `return`：comment 必填；
  - `approve`：comment 可选。
- 审批历史不可删除；`cancelled/returned` 也保留。

#### 9.4.12 与闸门、A02、A01 的边界

- **闸门**：审批通过只写 `opportunity_gate_checks` 的例外证据；不自动推进阶段。
- **A02**：审批待办是投影；不能手工 `resolve`，只能跳转审批抽屉做决定。
- **A01**：新增“待我审批”卡，统计当前用户/角色待处理步骤；点击进入 A02 审批筛选。
- **C1**：推进被 R4/R6 阻断时，弹窗提供“申请例外审批/关联方审批”；审批中显示状态；通过后“重新校验并推进”。

#### 9.4.13 审批 API 补充

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/opportunities/{id}/approvals` | 发起审批（gate_code、template_code、reason、evidence） |
| GET | `/approvals` | 列表；`status=pending_my_action` 支持待我审批 |
| GET | `/approvals/{id}` | 审批详情 + 步骤 + 动作历史 |
| GET | `/approvals/{id}/timeline` | 审批时间线 |
| POST | `/approvals/{id}/decision` | `{step_no, assignment_key?, action, comment, idempotency_key, delegate_to?}` |
| POST | `/approvals/{id}/cancel` | 撤回（申请人/管理员） |
| POST | `/approvals/{id}/retry-start` | 管理员手动补发 outbox |
| GET | `/approvals/pending-count` | A01 卡片计数 |

---

## 10. A02 统一待办详细设计

### 10.1 待办来源

| 类型 | 来源 | 示例 | 可批量 |
| --- | --- | --- | --- |
| `rule_event` | 规则引擎/扫描器 | R4 示范面缺失、R10 撞单、阶段超期、字段缺失 | 仅批量指派，不可批量关闭阻断 |
| `approval` | Temporal 审批工作流投影 | R4 例外、关联方审批、撞单合并审批 | 否；不可手工关闭 |
| `arbitration` | 撞单/主数据冲突 | R10 归属裁决 | 否 |
| `data_fix` | 数据质量 | 缺联系人、缺预计金额、缺合同号 | 可批量指派/关闭非阻断 |

### 10.2 严重度与 SLA（建议初始值）

| 严重度 | 默认 SLA | 升级 |
| --- | --- | --- |
| `blocker` | 4 小时 | 4h → 大区经理；24h → 中心主任；连续两周 → 经营例会 |
| `high` | 24 小时 | 24h → 大区经理；48h → 中心主任 |
| `medium` | 3 天 | 3 天 → 大区经理 |
| `low` | 7 天 | 7 天 → 责任人提醒 |

- 具体 SLA 可按 `rule_code`/审批模板覆盖；以配置为准。
- 阻断项无“跳过”按钮；只能处置/关闭或走例外审批。
- 审批类待办保留原审批链，A02 只做入口，不改变审批步骤。
- 审批类待办的 `due_at` 来自当前 `approval_steps.sla_due_at`；升级由 Temporal 驱动，A02 调度器不处理。

### 10.3 去重

- `dedupe_key = "{source_rule}:{object_type}:{object_id}:{bucket}"`。
- `bucket` 默认按天（同一实体同类事件 24h 去重）；阶段超期按阶段进入日。
- 部分唯一索引保证同一 `dedupe_key` 只存在一个 `open/in_progress` 待办。
- 已关闭后再次命中可重新生成，但保留历史。

### 10.4 状态流转

```text
open → in_progress → resolved
open → cancelled（仅允许取消非阻断、非审批类）
in_progress → open（退回）
```

- 关闭必须填 `resolution`；阻断项关闭需 `sales.todo.resolve` + 关联对象已满足条件。
- 审批类待办状态跟随 `approval_steps`：
  - `pending` → `open`；
  - `active` → `in_progress`；
  - `approved/rejected/returned/expired` → `resolved/cancelled`；
  - 审批类不允许手工 `resolve`，只能走 `/approvals/{id}/decisions`。
- 仲裁撤销不回删原记录，保留撤销原因。

### 10.5 升级任务

- 调度器每 5 分钟扫描 `due_at < now AND status in (open,in_progress) AND type <> 'approval'`。
- 按 `escalation_level` 找下一级角色/人员；写 `todo_escalations`、通知、审计。
- 若找不到上级，升级到 `sales_admin` 并标记异常。
- 多 worker 用 `pg_try_advisory_lock` 保证只有一个调度器执行。
- 审批类由 Temporal timer 升级；A02 只展示 `escalation_level` 和当前审批人。

### 10.6 统计

| 指标 | 口径 |
| --- | --- |
| 全部待办 | 当前筛选范围 |
| 今日到期 | `due_at` 在今日（Asia/Shanghai） |
| 已超时 | `due_at < now` 且未关闭 |
| ERROR 阻断 | `severity=blocker` 且未关闭 |
| 平均处理时长 | `resolved_at - created_at` 的平均值，排除取消 |

### 10.7 角色负载

- `role_load_limits` 配置每个角色在办上限。
- A02 右侧展示“在办/上限”，超限提示调剂；不自动改派，避免抢单。

---

## 11. A01 工作台详细设计

### 11.1 卡片

| 卡片 | 数据来源 | QW2 状态 |
| --- | --- | --- |
| 今日待办 | `todos` 本人/范围 | 可用 |
| 待我审批 | 顺序步看 `approval_steps`；并行步看 `approval_assignments` 中当前用户的活跃席位 | 可用 |
| 阻断项 | `todos severity=blocker` | 可用 |
| 超期商机 | `opportunities stage_due_at < now` | 可用 |
| 加权预测 | `opportunities` 本地 | 可用 |
| 漏斗健康 | 阶段数量/金额/停留 | 可用 |
| 本周开标 | C2 | 占位“待接入 C2” |
| 本月回款到期 | D01 | 占位“待接入 D01” |
| 资格缺口 | C2 | 占位“待接入 C2” |

- 卡片配置表 `workbench_card_configs`：按角色启用/排序；占位卡可隐藏。
- 数字点击下钻：`/sales/opportunities?stage=S5&overdue=1`、`/sales/todos?severity=blocker`。
- 所有数字带 `data_as_of`；导入数据带来源标识。

### 11.2 今日摘要（QW2 规则版）

不调用 LLM，按模板生成 3–5 条：

1. 今日阻断项数量 + 最近到期项。
2. 待我审批数量 + 最久等待项。
3. 超期阶段 Top 3 + 影响金额。
4. 加权预测 + 与上周变化（有快照才显示）。
5. 撞单待裁决数量 / 数据缺失提醒。

每条包含 `source_type`、`source_id`、`link`、`as_of`；生成动作写审计。后续可替换为 `BriefProvider`（LLM + 证据），页面结构不变。

### 11.3 只读边界

- 工作台不直接改商机/待办；所有处置跳转 C1/A02。
- 刷新不丢失筛选/滚动上下文；失败可重试。
- 首屏 P95 ≤ 2 秒；无权限数据不出现。

---

## 12. API 设计

### 12.1 约定

- 基础路径：`/api/v1`；Nginx 对外 `/sales/api/*`。
- 认证：Cookie/Bearer；写操作校验 CSRF（如 Gateway 已提供 `csrf_token`）。
- 分页：`skip`、`limit`（默认 20，最大 100）；列表返回 `{items,total,skip,limit}`。
- 错误：`{"detail": "...", "code": "SALES-...", "context": {...}}`。
- 时间：ISO 8601 UTC；页面本地化。
- 导出：CSV，带当前筛选、口径、时间、操作人。

### 12.2 工作台

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workbench/summary` | 当前用户角色/范围、卡片数据、`data_as_of` |
| GET | `/workbench/brief` | 规则摘要条目（含来源链接） |
| GET | `/workbench/quick-entries` | 角色快捷入口 |
| GET | `/workbench/cards` | 当前角色卡片配置 |
| PUT | `/workbench/cards` | 管理员配置角色卡片 |

### 12.3 商机

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/opportunities` | 列表/筛选/排序/分页 |
| POST | `/opportunities` | 新建（默认 S1） |
| GET | `/opportunities/{id}` | 详情：主数据、概率、闸门、历史、待办、撞单 |
| PATCH | `/opportunities/{id}` | 编辑允许字段；需 `version` |
| POST | `/opportunities/{id}/transition` | 推进/回退统一入口（或拆分） |
| POST | `/opportunities/{id}/rollback` | 回退（也可合并到 transition） |
| POST | `/opportunities/{id}/probability` | 人工概率修正 |
| GET | `/opportunities/{id}/timeline` | 阶段/概率/待办/审计时间线 |
| POST | `/opportunities/{id}/duplicates/check` | 手动触发 R10 |
| POST | `/opportunities/{id}/duplicates/{case_id}/resolve` | 撞单裁决 |
| GET | `/opportunities/funnel` | 九段数量/金额/转化/停留 |
| GET | `/opportunities/forecast` | 加权预测汇总 |
| GET | `/opportunities/export` | CSV 导出 |

#### 推进请求示例

```json
POST /api/v1/opportunities/{id}/transition
{
  "to_stage": "S5",
  "version": 7,
  "reason": "完成技术方案并安排示范面",
  "go_no_go": "go",
  "bid_strategy": "high_match",
  "evidence": [{"type": "pilot_project", "id": "..."}]
}
```

响应（通过）：

```json
{
  "opportunity": {"id": "...", "stage": "S5", "version": 8},
  "gate_results": [
    {"code": "R4", "status": "pass", "message": "已关联示范面"}
  ],
  "todos": [{"id": "...", "type": "data_fix", "title": "补充投标策略附件"}]
}
```

响应（阻断且可申请审批）：

```json
{
  "detail": "新客户集团投标立项前须有关联示范面",
  "code": "SALES-422-GATE_BLOCKED",
  "context": {
    "opportunity_id": "...",
    "gate_results": [{
      "code": "R4",
      "status": "block",
      "action": "link_pilot_project_or_request_exception",
      "approval_template": "R4_EXCEPTION",
      "approval_request_id": null
    }]
  }
}
```

- 前端根据 `approval_template` 显示“申请例外审批”；审批通过后重新提交 transition。
- 如果同一闸门已有审批中请求，返回 `approval_request_id`，避免重复发起。

#### 概率修正

```json
POST /api/v1/opportunities/{id}/probability
{
  "manual_probability": 72,
  "reason": "客户已明确预算，竞争格局有利",
  "version": 8
}
```

- 偏差 ≤15pct：`reason` 可选。
- 偏差 >15pct：`reason` 必填，否则 422。

### 12.4 待办

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/todos` | 筛选：type/severity/status/assignee/object/overdue/keyword |
| GET | `/todos/stats` | 统计卡 |
| GET | `/todos/{id}` | 详情 + 事件 |
| POST | `/todos/{id}/claim` | 认领 |
| POST | `/todos/{id}/assign` | 指派（需权限） |
| POST | `/todos/{id}/start` | 开始处理 |
| POST | `/todos/{id}/resolve` | 处置完成；`type=approval` 返回 409，必须走审批决定 |
| POST | `/todos/{id}/cancel` | 取消（限制；审批类不可） |
| POST | `/todos/batch` | 批量指派/关闭（按类型限制；审批类不可） |
| GET | `/todos/export` | CSV |

### 12.5 主数据与规则

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/master-data/customer-groups` | 集团列表/搜索 |
| GET | `/master-data/customers` | 客户列表 |
| GET | `/master-data/mines` | 矿井 |
| GET | `/master-data/workfaces` | 工作面 |
| GET | `/master-data/products` | 产品线/型号 |
| GET | `/master-data/contacts` | 联系人 |
| GET | `/master-data/pilot-projects` | 示范面 |
| POST | `/master-data/import/upload` | CSV / Excel 导入（type + file，可 dry_run） |
| GET | `/rules` | 规则列表/版本 |
| PUT | `/rules/{code}` | 新版本 |
| GET | `/lost-reason-codes` | 失标码表 |
| GET | `/notifications` | 站内信 |
| POST | `/notifications/{id}/read` | 已读 |

### 12.6 审批

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/opportunities/{id}/approvals` | 发起审批；返回 202 + `approval_request_id` |
| GET | `/approvals` | 列表；支持 `status=pending_my_action`、`gate_code`、`opportunity_id` |
| GET | `/approvals/{id}` | 详情 + 步骤 + 动作历史 + 工作流状态 |
| GET | `/approvals/{id}/timeline` | 审批时间线 |
| POST | `/approvals/{id}/decision` | 提交决定：`step_no/assignment_key?/action/comment/idempotency_key/delegate_to?` |
| POST | `/approvals/{id}/cancel` | 撤回（申请人/管理员） |
| POST | `/approvals/{id}/retry-start` | 管理员手动补发 outbox |
| GET | `/approvals/pending-count` | 待我审批计数 |

#### 审批决定示例

```json
POST /api/v1/approvals/{id}/decisions
{
  "step_no": 1,
  "action": "approve",
  "comment": "已核实示范面材料，同意立项",
  "idempotency_key": "c1f0d7a2-..."
}
```

- 返回 202：`{"status":"accepted","approval_id":"...","step_no":1}`。
- 重复 `idempotency_key` 返回 200 + 已接受结果，不重复推进。
- 当前步骤不匹配、非当前审批人、自批未开启：409/403。
- Temporal 未连接但请求已落库：202 + `status=pending_start`；页面显示“等待审批引擎”。

#### 审批状态查询

```json
{
  "id": "...",
  "status": "running",
  "current_step": 1,
  "workflow_id": "sales-approval-...",
  "workflow_run_id": "...",
  "steps": [
    {"step_no": 1, "approver_role": "regional_manager", "status": "active", "sla_due_at": "..."},
    {"step_no": 2, "approver_role": "sales_director", "status": "pending"}
  ]
}
```

### 12.7 错误码

| 错误码 | HTTP | 场景 |
| --- | --- | --- |
| `SALES-400-INVALID_TRANSITION` | 400 | 跳段/非法回退 |
| `SALES-400-MISSING_FIELDS` | 400 | 阶段必填缺失 |
| `SALES-403-SCOPE_DENIED` | 403 | 数据范围/权限不足 |
| `SALES-404-NOT_FOUND` | 404 | 对象不存在 |
| `SALES-409-VERSION_CONFLICT` | 409 | 乐观锁冲突 |
| `SALES-409-DUPLICATE` | 409 | 撞单未裁决 |
| `SALES-409-TODO_STATE` | 409 | 待办状态不允许操作 |
| `SALES-409-APPROVAL_STATE` | 409 | 审批步骤已决定/已终态 |
| `SALES-409-DUPLICATE_DECISION` | 409 | 同一步骤已由他人决定；相同 `idempotency_key` 重试返回 200 原结果 |
| `SALES-422-GATE_BLOCKED` | 422 | 闸门阻断 |
| `SALES-422-PROBABILITY_REASON` | 422 | 偏差 >15 无依据 |
| `SALES-422-SELF_APPROVAL` | 422 | 默认禁止自批 |
| `SALES-503-TEMPORAL_UNAVAILABLE` | 503 | 审批引擎未启用/不可达 |
| `SALES-500-INTERNAL` | 500 | 未预期错误 |

---

## 13. 前端页面设计

### 13.1 视觉与组件

- 复用 procurement 的 shadcn 主题、侧边栏、Header、Main、ProfileDropdown、ThemeSwitch。
- 新增销售组件：
  - `SalesPageHead`：kicker、标题、说明、角色/数据范围/截至时间、操作。
  - `MetricStrip`：5 格指标，支持 danger/warn/accent。
  - `Panel`：标题、副标题、右侧操作、内容、脚注。
  - `StageRail`：九段，数量、金额、进度条、当前阶段。
  - `ProbabilityCell`：规则值/人工值/生效值三列或两行。
  - `SlaCell`：倒计时/逾期/升级级别。
  - `StatusPill`、`SeverityDot`、`GateBadge`。
  - `ApprovalTimeline`：步骤、决定、时间、意见、升级记录。
  - `ApprovalDecisionForm`：同意/拒绝/退回 + 意见 + 幂等提交。
  - `PendingApprovalCard`：A01 待我审批。
  - `EmptyState`、`ErrorState`、`TableSkeleton`。
- 字号：页头标题 20–24px，卡片标题 14px，表格头 12px，表格单元 13px，辅助 12px；数字强调 22px。
- 颜色：沿用主题；阻断红、预警橙、通过绿、未知灰；不要用颜色作为唯一信息载体（同时给文字/图标）。

### 13.2 A01 我的工作台 `/sales/`

布局（≥1280px）：

```text
PageHead（角色/范围/截至时间/刷新/生成摘要）
MetricStrip（今日待办｜待我审批｜阻断项｜加权预测｜超期商机）
Hero 摘要（3–5 条，来源链接）
左 2/3：待办与预警 Top 5 + 待我审批 Top 3 + 漏斗快照
右 1/3：阶段健康 / 快捷入口 / 待接入卡片
脚注：只读汇总、数据来源、口径
```

- 1024–1279px：Hero 全宽，左右改上下。
- ≤900px：卡片纵向堆叠；表格改列表；无横向滚动。
- 占位卡显示“待接入 C2/D01”，禁用点击，不显示数字。
- 加载：首次无缓存显示 skeleton；缓存刷新保留旧数据 + 顶部进度，不闪骨架。

### 13.3 C1 商机漏斗 `/sales/opportunities`

```text
PageHead（全部/我的/超期｜导出｜新建）
MetricStrip（在途金额｜加权预测｜平均停留｜超期｜撞单）
StageRail（S1–S9，可点击筛选）
左：阶段转化；右：阶段健康度
Panel：在途商机表
  - 商机/工作面
  - 产品线
  - 阶段
  - 预计金额
  - 双源概率（规则/人工/生效）
  - 阶段停留
  - 负责人
  - 操作（推进/查看）
```

- 行点击打开右侧详情抽屉（≥1280px 可固定 380–420px；以下为全屏抽屉/页面）。
- 详情：头部（名称/客户/工作面/负责人）、阶段进度、闸门结果、概率、联系人/决策链、时间线、撞单、待办、审批、操作。
- 新建/编辑：客户→矿井→工作面级联；金额、预计成交日、产品线、负责人、来源；S1 必填校验。
- 推进弹窗：显示目标阶段、必填项、闸门预检、证据、原因；阻断时给处理入口。
- 闸门阻断且可审批时：
  - 显示“申请例外审批/关联方审批”按钮；
  - 已有审批中请求显示“审批中（当前步骤/审批人/截止）”，按钮改为“查看审批”；
  - 审批通过后显示“已通过，重新校验并推进”；不自动推进。
- 概率编辑：双列显示，偏差 >15 时强制填写依据。
- 空/错/无权限：明确文案 + 重试/返回。
- 移动端：StageRail 横向滚动；表格变卡片；关键操作吸底；不出现页面级横向滚动。

### 13.4 A02 统一待办 `/sales/todos`

```text
PageHead（导出｜批量处理）
MetricStrip（全部｜今日到期｜已超时｜阻断｜平均处理时长）
FilterRow（类型 chips｜优先级｜责任人｜状态｜搜索）
Table
  - 级别
  - 待办事项（标题 + 说明）
  - 类型/规则
  - 关联对象
  - SLA
  - 责任人
  - 操作
下：升级与 SLA 规则｜角色负载
```

- 阻断行置顶，红色左边框；无“跳过”。
- 批量选择只对允许类型启用；不可批量项置灰并说明；审批类永远不可批量。
- 审批类行显示“步骤 1/2”、当前审批人/角色、SLA；点击打开审批抽屉，不跳原审批单（QW2 没有独立审批系统）。
- 审批抽屉：申请信息、关联商机、闸门、步骤时间线、升级记录、意见、同意/拒绝/退回；提交中禁用按钮；成功后刷新列表和 A01 计数。
- 审批类 `resolve/cancel` 按钮不出现；手工调用 API 返回 409。
- 仲裁类跳转裁决抽屉；补录类跳转对象表单。
- 详情抽屉含事件时间线、升级记录、关联对象摘要。
- 移动端：卡片列表，SLA/严重度/操作在卡片内；批量栏吸底。

### 13.5 主数据 `/sales/master-data`（管理员/Steward）

- Tab：集团/客户/矿井/工作面/产品/联系人/示范面。
- 列表 + 搜索 + 导入 CSV / Excel（拖拽或点选）+ 失败行下载。
- 显示来源、更新时间、完整度；不提供“假实时”。
- 导入采用“预校验→确认导入→结果”三步，失败不落库。

### 13.6 路由与导航

```text
/sales/                     A01 我的工作台
/sales/opportunities        C1 商机漏斗
/sales/opportunities/:id    商机详情（可选独立页）
/sales/todos                A02 统一待办
/sales/master-data          最小主数据（管理员）
```

侧边栏新增“销售管理”组：我的工作台、商机漏斗、统一待办、主数据。C2/D01 等未实现页面不放入导航，避免空链接。

### 13.7 状态与缓存

- TanStack Query：列表 `staleTime=15s`；详情 `staleTime=5s`；写操作后精确失效。
- 刷新保留筛选；分页/排序同步 URL search params，支持深链。
- 错误：401 跳登录；403 显示无权限；409 提示版本冲突/审批已处理并刷新；422 展示闸门/字段/自批限制；503 显示“审批引擎暂不可用，请稍后重试”。
- 审批提交使用幂等键；双击/重试不重复推进。
- 骨架仅首次加载；缓存刷新不闪。

---

## 14. 非功能设计

| 项 | 要求 |
| --- | --- |
| 性能 | A01 首屏 P95 ≤ 2s；列表 P95 ≤ 1.5s；详情 ≤ 1s（本地库，1 万商机/10 万待办量级） |
| 并发 | 写操作乐观锁；待办处置幂等；调度器 advisory lock；审批决定 `idempotency_key` |
| 可用性 | 外部系统不可用不影响 QW2 核心流程；Temporal 不可用时审批请求排队，非审批流程继续 |
| 审批可靠性 | Temporal 持久化 history；活动至少一次 + 幂等；outbox 补发；工作流/DB 对账 |
| 安全 | JWT、RBAC、数据范围、CSRF、输入校验、导出审计；Temporal 仅内网 |
| 审计 | 登录、查询导出、阶段/概率/撞单/待办/规则/审批变更全记录 |
| 隐私 | 联系人手机/邮箱脱敏展示；导出需权限 |
| 可观测 | `/health`（含 Temporal 连接状态）、结构化日志、request_id、慢查询日志；审批启动/完成/失败/超时指标 |
| 备份 | 随 business-db 统一备份；sales 库独立恢复演练；Temporal history 由 postgres-ext 备份 |
| 时区 | 存 UTC，展示 Asia/Shanghai；SLA 按自然日/小时计算 |
| 浏览器 | Chrome/Edge 最近两个大版本；1440/1024/390 三档验收 |

---

## 15. 测试策略

### 15.1 后端

- 单元测试：
  - 状态机：合法/非法推进、回退、S8 结果、S9 合同字段。
  - 概率：规则值、超期降权、人工偏差、上下限。
  - R10：同客户/工作面/产品线匹配、排除自身、预测排除、裁决。
  - R4/R2/R6/R9：pass/warn/block。
  - 待办：去重、SLA、升级、批量限制、审批不可手工关闭。
  - 审批：模板快照、顺序/并行通过、拒绝/退回、自批限制、步骤越权、重复信号。
  - 数据范围：all/region/self。
- 集成测试：
  - 使用独立测试库（事务回滚或临时 schema）。
  - API 全链路：创建→推进→闸门→待办→裁决→预测。
  - 审批全链路：阻断→发起审批→outbox→工作流→活动→待办→决定→闸门解除→重试推进。
  - 并发：两个请求同时推进，只有一个成功；两个相同审批信号只生效一次。
  - 调度器：冻结时间，验证超期/升级幂等；审批类不被 A02 调度器处理。
  - Temporal 不可达：请求 `pending_start`，outbox 重试，恢复后启动。
- 工作流测试：
  - `WorkflowEnvironment.start_time_skipping()` + 内存/测试活动：通过、拒绝、退回、超时升级、过期、撤回。
  - `WorkflowReplayer` 回放历史，防止非确定性。
  - 活动失败重试、`non_retryable`、幂等。
- 契约：OpenAPI 快照；前端类型与后端 schema 对齐。

### 15.2 前端

- 组件测试：MetricStrip、StageRail、ProbabilityCell、SlaCell、GateBadge、空/错/骨架。
- 页面测试：A01/A02/C1 的筛选、分页、抽屉、表单校验、阻断提示。
- E2E（Playwright）：
  1. 新建商机 → S1→S2→S3→S4；R4 阻断 → 关联示范面 → S5。
  2. R10 撞单 → 仲裁待办 → 裁决 → 预测恢复。
  3. 人工概率偏差 >15 无依据被拒；填写依据后保存。
  4. 阶段超期 → 降权 + 待办 → 升级。
  5. 失标 C99 无说明被拒；填写后关闭。
  6. 待办批量限制；阻断不可批量；审批类不可批量/手工关闭。
  7. R4 阻断 → 申请例外审批 → 大区经理通过 → 销售总监通过 → 重新校验并推进。
  8. 审批拒绝/退回 → 闸门保持阻断 → 申请人补充后重新发起。
  9. 审批超时 → 升级 → 待办责任人变化；不自动通过。
  10. 角色/数据范围：销售只看自己，区域经理看区域；非当前审批人不能操作。
  11. 390px 无横向滚动。

### 15.3 验收数据

- 1 个集团、2 个客户、3 个矿井、6 个工作面、3 条产品线。
- 12 个商机覆盖 S1–S9、超期、撞单、失标。
- 20 条待办覆盖四类/四级严重度/超时/升级。
- 证书/业绩不需要（QW2 不纳入 C2）。
- 所有演示数据标记 `source=demo`，页面显示“演示数据”。

---

## 16. 部署设计

### 16.1 数据库

`docker/postgres-init/init-business-dbs.sh` 增加：

```sql
CREATE DATABASE sales;
GRANT ALL PRIVILEGES ON DATABASE sales TO $POSTGRES_USER;
```

已有 `business-db-data` 卷不会重跑 init，需要手工执行：

```sql
CREATE DATABASE sales;
GRANT ALL PRIVILEGES ON DATABASE sales TO business;
```

### 16.2 Compose

`docker/docker-compose.business.yaml` 增加 API、Worker、前端：

```yaml
sales-backend:
  build:
    context: ../business/sales-service/backend
  container_name: eai-flow-sales-backend
  command: uv run uvicorn app.main:app --host 0.0.0.0 --port 3004 --workers 2
  environment:
    - DATABASE_URL=${SALES_DATABASE_URL:-postgresql+asyncpg://${BUSINESS_DB_USER:-business}:${BUSINESS_DB_PASSWORD:-business123}@business-db:5432/sales}
    - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    - JWT_ALGORITHM=HS256
    - API_PREFIX=/api/v1
    - SCHEDULER_ENABLED=true
    - TEMPORAL_ENABLED=true
    - TEMPORAL_URL=temporal:7233
    - TEMPORAL_NAMESPACE=default
    - TEMPORAL_TASK_QUEUE=sales-approval-queue
    - TZ=Asia/Shanghai
  env_file:
    - ../.env
  depends_on:
    business-db:
      condition: service_healthy
  networks:
    - eai-flow-net
  restart: unless-stopped

sales-worker:
  build:
    context: ../business/sales-service/backend
  container_name: eai-flow-sales-worker
  command: uv run python -m app.workflows.worker
  environment:
    - DATABASE_URL=${SALES_DATABASE_URL:-postgresql+asyncpg://${BUSINESS_DB_USER:-business}:${BUSINESS_DB_PASSWORD:-business123}@business-db:5432/sales}
    - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    - TEMPORAL_ENABLED=true
    - TEMPORAL_URL=temporal:7233
    - TEMPORAL_NAMESPACE=default
    - TEMPORAL_TASK_QUEUE=sales-approval-queue
    - TZ=Asia/Shanghai
  env_file:
    - ../.env
  depends_on:
    business-db:
      condition: service_healthy
  networks:
    - eai-flow-net
  restart: unless-stopped

sales-frontend:
  build:
    context: ../business/sales-service/frontend
  container_name: eai-flow-sales-frontend
  networks:
    - eai-flow-net
  restart: unless-stopped
```

启动顺序：

```bash
# 已有 extensions 提供 postgres-ext；temporal 依赖它
docker compose \
  -f docker-compose.yaml \
  -f docker-compose.extensions.yaml \
  -f docker-compose.business.yaml \
  -f docker-compose.temporal.yaml \
  up -d
```

- `docker/docker-compose.temporal.yaml` 已存在，服务名 `temporal`、容器名 `eai-flow-temporal`，端口 `7233`。
- Temporal 使用 `postgres-ext`，不是 `business-db`；首次部署若 `postgres-ext` 数据卷非空，需按现有部署手册创建 `temporal` 角色/库。
- `sales-worker` 依赖 Temporal 的 DNS/网络，不依赖其 healthcheck；Temporal 未就绪时 Worker 连接失败并重试，不应导致 API 启动失败。
- 可选：加 `temporalio/ui` 容器供运维查看工作流，不暴露给业务用户。

### 16.3 Nginx

在业务 Nginx 配置（`nginx.full.conf` / `nginx.external.conf`，以及实际部署使用的模板）增加：

```nginx
upstream sales-frontend { server sales-frontend:3000; }
upstream sales-backend  { server sales-backend:3004; }

location /sales/ {
    rewrite ^/sales/(.*) /$1 break;
    proxy_pass http://sales-frontend;
    ...
}

location /sales/api/ {
    rewrite ^/sales/api/(.*) /api/v1/$1 break;
    proxy_pass http://sales-backend;
    ...
}
```

> 注意：当前主 `docker/nginx/nginx.conf` 只包含 Gateway/Frontend/OntoStudio 路由，不包含 procurement/asset/project。QW2 部署前必须确认业务路由实际由哪个 Nginx 模板承载；不能只改一个未生效的文件。

### 16.4 前端

- Vite `base: '/sales/'`。
- TanStack Router `basepath: '/sales'`。
- API base：`/sales/api`。
- 静态资源、favicon、深链刷新由 Nginx `try_files` 回退 `index.html`。
- 构建产物独立镜像，不复用 procurement 镜像。

### 16.5 环境变量

```env
DATABASE_URL=postgresql+asyncpg://business:business123@localhost:5433/sales
JWT_SECRET_KEY=CHANGE_ME_USE_SAME_SECRET_AS_EAIFLOW
JWT_ALGORITHM=HS256
API_PREFIX=/api/v1
HOST=0.0.0.0
PORT=3004
LOG_LEVEL=INFO
SCHEDULER_ENABLED=true

# Temporal / eai-flow-temporal
TEMPORAL_ENABLED=true
TEMPORAL_URL=temporal:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=sales-approval-queue
# 本地单进程调试可开；生产用独立 sales-worker
SALES_EMBEDDED_WORKER=false

TZ=Asia/Shanghai
```

### 16.6 依赖、迁移与种子

- 后端依赖增加 `temporalio[pydantic]>=1.27.0`（与现有 `backend/pyproject.toml` 一致）。
- Worker 入口：`uv run python -m app.workflows.worker`；生产独立容器，`SALES_EMBEDDED_WORKER=false`。
- 本地调试：`SALES_EMBEDDED_WORKER=true` 可在 API 进程内跑 Worker + outbox，但多副本时必须关闭。
- Sprint 0：`create_all` 快速起步；Sprint 1 结束前补 Alembic baseline，之后所有变更走 migration。
- 种子命令：`uv run python -m app.seed.demo`，写入 `source=demo`，可重复执行（幂等）；同时写入 `approval_definitions` 种子。
- 生产禁止自动跑 demo seed；通过 `SEED_DEMO=false` 控制。

---

## 17. 迭代计划

按 1 名后端、1 名前端、0.5 名 QA 估算：

| 迭代 | 周期 | 交付 | 退出标准 |
| --- | --- | --- | --- |
| Sprint 0 | 4–5 天 | 工程骨架、DB、JWT、Shell、主数据表/导入、审计、Temporal Client/Worker 骨架 | 可登录，可导入客户/工作面；Temporal 连接/健康状态可见 |
| Sprint 1 | 1 周 | C1 列表/新建/详情/编辑、S1–S4 状态机、阶段历史 | 非法跳段被拒；必填校验生效 |
| Sprint 2 | 1 周 | S5–S9、R4/R2/R6/R9、R10、双源概率、预测、漏斗统计 | 六条闸门用例通过；预测可复算 |
| Sprint 3 | 1.5 周 | A02 四类待办、去重、SLA、升级、批量；Temporal 审批工作流、outbox、审批待办投影 | 通过/拒绝/退回/超时升级可模拟；审批类不可批量/手工关闭 |
| Sprint 4 | 1 周 | A01 卡片（含待我审批）、摘要、下钻、快捷入口、角色配置 | 数字与 C1/A02 一致；占位卡不显示假数 |
| Sprint 5 | 3–5 天 | 响应式、性能、权限矩阵、E2E、部署、演示数据 | 三档分辨率通过；E2E 全绿；可试点 |

总计 **5–6 周** 可演示；加业务 UAT/数据准备约 **6–7 周**。Temporal 审批是本次新增的关键路径，Sprint 3 需要后端和前端联调，不能压缩到 1 周内同时完成 A02 全部功能。

---

## 18. 验收清单

### 18.1 商机

- [ ] 新建商机默认 S1，必填校验生效。
- [ ] S1→S9 只能相邻推进；跳段被 API 拒绝。
- [ ] 回退必须填原因/影响/补救，历史可查。
- [ ] R4 新客户集团无示范面阻断 S5，关联后通过。
- [ ] R2 未裁决报价冲突阻断 S6。
- [ ] R6 关联方无专用审批阻断 S7。
- [ ] R9 失标无 C01–C99 阻断；C99 无说明阻断。
- [ ] R10 同客户/工作面/产品线撞单生成仲裁待办，未裁决不计预测。
- [ ] 概率双源展示；偏差 >15 无依据保存被拒。
- [ ] 超期自动降权 10–20%，阶段事实不变。
- [ ] 加权预测可复算，S9/失标/撞单排除。
- [ ] S9 合同号/金额/生效日必填。
- [ ] 版本冲突返回 409，不覆盖他人修改。

### 18.2 待办

- [ ] 四类待办统一列表、筛选、搜索、分页。
- [ ] 阻断置顶，无跳过；不可批量关闭。
- [ ] SLA 倒计时/逾期准确；升级链路可模拟。
- [ ] 同一实体同类事件 24h 去重。
- [ ] 审批类待办是 Temporal 投影；步骤/审批人/SLA 与审批单一致。
- [ ] 审批类不可批量、不可手工关闭；`resolve` 返回 409。
- [ ] 审批通过/拒绝/退回后，待办自动关闭/切换，A01 计数同步。
- [ ] 审批超时升级由 Temporal 驱动；A02 调度器不重复升级。
- [ ] 重复点击审批只生效一次；`idempotency_key` 冲突返回已有结果。
- [ ] 仲裁撤销不回删原记录。
- [ ] 批量操作逐条留痕。
- [ ] 统计与列表口径一致；导出含操作人/时间。

### 18.3 工作台

- [ ] 不同角色看到不同卡片/范围。
- [ ] 今日待办、阻断、超期、预测、漏斗与源页面一致。
- [ ] 点击数字下钻携带筛选。
- [ ] 摘要每条有来源和截至时间。
- [ ] 占位卡不显示假数字。
- [ ] 刷新保留上下文；失败可重试。
- [ ] 首屏 P95 ≤ 2s；390px 无横向滚动。

### 18.4 审批

- [ ] R4/R6 阻断页面能发起对应审批，不能绕过。
- [ ] 审批请求与 outbox 同事务；Temporal 不可用时显示“等待审批引擎”，恢复后自动启动。
- [ ] 审批按模板步骤顺序执行；当前步骤角色/用户才能操作。
- [ ] 默认禁止自批；拒绝/退回必须填意见。
- [ ] 审批通过后闸门解除，但不自动推进；重新提交 transition 才推进。
- [ ] 审批拒绝/退回/过期后闸门保持阻断，历史可查。
- [ ] 审批超时按 timer 升级；过期不自动通过。
- [ ] Worker 重启、API 重启后审批继续；活动幂等、不重复发待办。
- [ ] 工作流与 DB 对账可修复“Temporal 已完成、DB running”。
- [ ] 审批历史可回放；工作流代码变更未破坏运行中实例。

### 18.5 通用

- [ ] 越权数据不可见/不可操作。
- [ ] 所有写操作有审计。
- [ ] 导入失败可下载修正；重复导入不重复。
- [ ] 外部系统不可用时核心流程不阻塞。
- [ ] 前端/后端/DB 可一键本地启动。
- [ ] Demo 数据有明确标识。

---

## 19. 风险与待确认

| # | 事项 | 影响 | 建议 |
| --- | --- | --- | --- |
| 1 | Gateway JWT 的 role/permissions 是否包含销售角色 | 权限映射失败 | QW2 用 `user_profiles` 本地映射兜底，接口保留 |
| 2 | 客户/矿井/工作面种子数据谁提供 | C1 无法真实演示 | 业务 1 周内给 CSV；否则用 `source=demo` 并标识 |
| 3 | 阶段基准概率/降权幅度未确认 | 预测口径不可验收 | 先配置化 + demo 值，业务确认后版本化 |
| 4 | C01–C99 码表未定 | 失标归因不可比 | 先给最小示例码，业务确认后替换；保留 C99 |
| 5 | R2/R6 在 QW2 只有最小记录 | 可能被误解为完整报价/关联方管理 | 页面标注“本地记录/待接入”；C3/关联方系统接入后替换 |
| 6 | 附件二进制存储未定 | 证据只能存 URL | QW2 先存 URL/对象键；后续接对象存储 |
| 7 | 审批角色矩阵未定 | 审批链不合规 | QW2 先按 `R4_EXCEPTION`/`R6_RELATED_PARTY` 建议模板，业务确认后改配置；`compliance_officer` 可先由销售总监兼 |
| 8 | 多 worker 调度器 | 重复生成/升级 | advisory lock + 幂等键；审批 SLA 交给 Temporal，不上双保险 |
| 9 | A01 占位卡 | 用户误以为功能缺失 | 明确“待接入 C2/D01”，可配置隐藏 |
| 10 | 撞单合并策略 | 合并后历史/预测口径 | 默认“保留主商机、非主商机关闭并记 `duplicate_of_id`”，合并前双签/审批 |
| 11 | 组织/区域编码 | 数据范围错 | 先用最小 `org_units`，接口后映射 HR/MDM |
| 12 | S9 合同字段与 C3 边界 | 重复建设 | QW2 只存合同号/金额/生效日；付款节点/交付由 C3 负责 |
| 13 | Temporal 未启动/`postgres-ext` 缺 temporal 角色 | 审批不可用 | 部署前检查 `eai-flow-temporal` 和 `postgres-ext`；API 不因 Temporal 失败而启动失败 |
| 14 | Worker 多副本 | 同一 workflow task 不会并发投递给多个 Worker，但活动仍可能重试 | 活动必须幂等；Worker 可水平扩展，不需要 advisory lock |
| 15 | 工作流代码非确定性 | 历史回放失败，运行中审批卡住 | 禁止 workflow 内读时钟/随机/DB；CI 回放；用 `workflow.patched` |
| 16 | Outbox 积压 | 审批延迟 | 监控 outbox 待处理数/最老事件；退避重试；管理员手动 `retry-start` |
| 17 | 审批与闸门双写不一致 | 页面显示通过但闸门仍阻断 | 以 `approval_requests.status` + `opportunity_gate_checks` 同事务活动为准；对账任务修复 |

### 需要拍板

1. QW2 页面范围是否就按 A01 + C1 + A02 + 最小主数据，C2/D01 卡片占位？
2. R2/R6 是否接受“本地最小记录 + 明确标注”，还是要等报价/关联方系统？
3. 阶段概率/降权/SLA 的初始值由谁确认？是否先用 demo 值开发？
4. C01–C99 先给最小示例码是否可接受？
5. 试点角色/区域/团队是谁？种子数据谁给？
6. 附件是否 QW2 只存 URL，还是本期就接对象存储？
7. 审批模板步骤/角色是否按 `R4_EXCEPTION`、`R6_RELATED_PARTY` 建议执行？`compliance_officer` 由谁担任？
8. 审批 SLA/升级/过期时限是否按 24h/24h/7 天？是否允许自批/转办？
9. 生产是否接受独立 `sales-worker` 容器？本地开发是否允许 `SALES_EMBEDDED_WORKER=true`？
10. 是否需要在 QW2 就接 Temporal UI，还是只用 API/日志运维？

---

## 20. 附录：初始种子建议

### 20.1 失标原因最小码表（示例，待业务确认）

| 码 | 名称 | 需说明 |
| --- | --- | --- |
| C01 | 价格高于对手 | 否 |
| C02 | 技术方案不满足 | 否 |
| C03 | 同类业绩不足 | 否 |
| C04 | 交货期不满足 | 否 |
| C05 | 客户关系/决策链不足 | 否 |
| C06 | 资质/证书不满足 | 否 |
| C07 | 废标/形式审查不通过 | 否 |
| C08 | 竞争性谈判/策略放弃 | 否 |
| C99 | 其他 | 是 |

### 20.2 规则配置初始键

```json
{
  "stage_probability": {"S1": 10, "S2": 20, "S3": 35, "S4": 50, "S5": 60, "S6": 70, "S7": 80, "S8": 90, "S9": 100},
  "stage_sla_days": {"S1": null, "S2": 30, "S3": 30, "S4": 35, "S5": 15, "S6": 10, "S7": 15, "S8": null, "S9": null},
  "overdue_penalty_pp": 15,
  "overdue_penalty_max_pp": 20,
  "manual_deviation_threshold_pp": 15,
  "probability_floor": 5,
  "duplicate_match": ["customer_id", "workface_id", "product_line"],
  "todo_dedupe_hours": 24,
  "sla_hours": {"blocker": 4, "high": 24, "medium": 72, "low": 168},
  "escalation_hours": [4, 24, 336]
}
```

### 20.3 审批模板种子

```json
[
  {
    "code": "R4_EXCEPTION",
    "name": "R4 示范面例外审批",
    "version": 1,
    "mode": "sequential",
    "steps": [
      {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24, "escalation_hours": 24},
      {"step_no": 2, "approver_role": "sales_director", "sla_hours": 24, "escalation_hours": 24}
    ]
  },
  {
    "code": "R6_RELATED_PARTY",
    "name": "关联方交易审批",
    "version": 1,
    "mode": "sequential",
    "steps": [
      {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24, "escalation_hours": 24},
      {"step_no": 2, "approver_role": "sales_director", "sla_hours": 24, "escalation_hours": 24},
      {"step_no": 3, "approver_role": "compliance_officer", "sla_hours": 48, "escalation_hours": 24}
    ]
  },
  {
    "code": "DUPLICATE_MERGE",
    "name": "撞单合并审批",
    "version": 1,
    "mode": "sequential",
    "steps": [
      {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24, "escalation_hours": 24}
    ]
  }
]
```

### 20.4 Temporal 配置

```env
TEMPORAL_ENABLED=true
TEMPORAL_URL=temporal:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=sales-approval-queue
TEMPORAL_WORKFLOW_ID_PREFIX=sales-approval
TEMPORAL_MAX_CONCURRENT_ACTIVITIES=20
TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS=20
```

### 20.5 Demo 数据规模

- 1 个集团、2 个客户、3 个矿井、6 个工作面、3 条产品线。
- 12 个商机：S1–S9 覆盖、2 个超期、1 组撞单、1 个失标、1 个 S9。
- 20 条待办：四类、四级、2 条超时、1 条升级中。
- 3 个审批：1 个 `R4_EXCEPTION` 运行中、1 个 `R6_RELATED_PARTY` 已通过、1 个 `DUPLICATE_MERGE` 已拒绝。
- 所有 demo 数据 `source=demo`，页面顶部显示“演示数据，仅用于联调”。
