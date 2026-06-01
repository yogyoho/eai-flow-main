# 项目工作流引擎 + AI 溯源 + 多人审核 设计方案

**日期**: 2026-05-29
**状态**: Draft
**前置**: 项目管理模块重设计（2026-05-24）、RBAC + 审核流程（2026-05-25）、文档协作编辑（2026-05-26）

## 1. 概述

在现有项目管理（固定 6 阶段、单链审批）基础上扩展三大能力：

1. **灵活工作流引擎** — 项目可配置多阶段工作流（串行/并行/条件/子流程），每阶段独立团队和审核，阶段间自动传递上下文。前端 React Flow 可视化编排，后端 Temporal.io 驱动执行。
2. **AI 内容溯源** — 段落级来源标注（类似 Wikipedia 脚注），追踪每段内容来自知识库 RAG、法规引用、AI 生成还是人工编写。
3. **多人分章节/维度混合审核** — 同一审核节点支持按章节分配审核人 + 按维度（技术/合规/语言）分工审核，并行处理。

**核心原则：** 灵活配置（可简单可复杂），基于现有实现扩展，不过度设计。

## 2. 架构设计

### 2.1 运行时拓扑

```
Browser
  ├── /api/extensions/workflow/*   ──→  Gateway FastAPI (port 8001)
  │   ├── Workflow routers              │
  │   └── Phase Review routers          │
  ├── /api/extensions/project/*    ──→  Gateway FastAPI (port 8001) [不变]
  ├── /api/collab/*                ──→  Hocuspocus WebSocket (port 8002) [不变]
  ├── /*                           ──→  Next.js Frontend (port 4000)
  │   ├── extensions/workflow/     [新增]
  │   ├── extensions/project/      [不变]
  │   └── extensions/collab/       [不变]
  │
  └── temporal:7233                 ──→  Temporal Server [新增，+1 容器]
                                        ↕ 连接 postgres-ext（复用现有 PG）
```

### 2.2 基础设施变更

**新增：+1 容器**

| 容器 | 镜像 | 说明 |
|------|------|------|
| temporal | temporalio/auto-setup:1.27.0 | 连接现有 postgres-ext，自动创建 temporal/temporal_visibility 库 |

**复用（不变）：**
- `postgres-ext` — 应用库 `agentflow` + Temporal 库 `temporal`/`temporal_visibility` 共享同一 PostgreSQL 实例
- `eai-flow-gateway` — 内嵌 Temporal Client + Worker（同进程，FastAPI lifespan 管理）
- `eai-flow-collab` — 不变
- `eai-flow-frontend` — 新增 `extensions/workflow/` 目录

**不再需要：**
- `temporal-postgresql` — 复用 postgres-ext
- `temporal-ui` — 监控面板融入前端 `WorkflowMonitor` 组件
- `temporal-admin-tools` — 可选

### 2.3 Gateway Temporal 集成

```python
# backend/app/extensions/workflow/temporal/client.py

from contextlib import asynccontextmanager
from temporalio.client import Client
from temporalio.worker import Worker

@asynccontextmanager
async def temporal_lifespan(app: FastAPI):
    """FastAPI lifespan: 启动 Temporal Client + 嵌入式 Worker"""
    client = await Client.connect("temporal:7233", namespace="default")
    worker = Worker(
        client,
        task_queue="project-workflow-queue",
        workflows=[DynamicGraphWorkflow],
        activities=[
            init_phase, gather_phase_context, advance_phase,
            start_ai_writing, parse_sources, store_sources,
            create_review_assignments, check_reviews_complete, handle_rejection,
            notify_phase_start, notify_review_pending, notify_workflow_complete,
        ],
    )
    worker_task = asyncio.create_task(worker.run())
    app.state.temporal_client = client
    yield
    worker_task.cancel()
```

### 2.4 设计原则

1. **DAG JSON 存应用库，Temporal 只管执行** — 用户编辑的是 DAG JSON，不是 Temporal 代码
2. **现有模型扩展而非替换** — `report_projects` 新增 `workflow_id` 等字段，无 `workflow_id` 的项目走旧逻辑
3. **所有副作用在 Activity 中** — Temporal Workflow 内不做 DB 操作
4. **渐进式部署** — Temporal 可独立启停，工作流定义存在应用库

## 3. 数据模型

### 3.1 新增表

#### `workflow_definitions`

存储 React Flow 生成的 DAG 工作流定义，可复用为模板。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `name` | VARCHAR(200) | 工作流名称，如 "环评报告流程" |
| `report_type` | VARCHAR(50) | 可选绑定的报告类型 |
| `graph_json` | JSONB | DAG 节点和边的完整定义 |
| `is_template` | BOOLEAN DEFAULT false | 是否为预设模板 |
| `created_by` | UUID FK→users | 创建人 |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `phase_reviews`

阶段审核分配，支持按章节和按维度两种模式。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK→report_projects | 所属项目 |
| `phase_node` | VARCHAR(50) | DAG 节点 ID |
| `chapter_id` | UUID FK→project_chapters | 可 NULL（按维度审核时为 NULL） |
| `reviewer_id` | UUID FK→users | 审核人 |
| `review_type` | VARCHAR(20) | `chapter` 或 `dimension` |
| `dimension` | VARCHAR(50) | 维度名称（技术/合规/语言等），按章节审核时为 NULL |
| `status` | VARCHAR(20) DEFAULT 'pending' | pending / approved / rejected |
| `comment` | TEXT | 审核意见 |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `content_sources`

AI 内容溯源，段落级来源标注。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `chapter_id` | UUID FK→project_chapters | 所属章节 |
| `block_index` | INTEGER | BlockNote 块索引 |
| `source_type` | VARCHAR(30) | `knowledge_base` / `rag_retrieval` / `ai_generated` / `human_written` / `template` / `external_data` |
| `source_ref` | VARCHAR(500) | 来源标识（知识库文档路径、法规编号等） |
| `snippet` | TEXT | 被引用的原文片段 |
| `confidence` | FLOAT | 置信度 0-1 |
| `metadata` | JSONB | 扩展信息（页码、检索分数等） |
| `created_at` | TIMESTAMP | |

### 3.2 工作流执行状态

工作流实例状态不单独建表。Temporal 自身持久化工作流执行历史。应用侧通过 `report_projects.temporal_workflow_id` 查询 Temporal API 获取实时状态。

需要应用侧持久化的状态（审核记录、溯源标注）分别在 `phase_reviews` 和 `content_sources` 表中。

### 3.3 现有模型扩展

**`report_projects` 新增字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `workflow_id` | UUID FK→workflow_definitions | 关联的工作流定义，NULL 则走旧 6 阶段逻辑 |
| `temporal_workflow_id` | VARCHAR(100) | Temporal 工作流实例 ID |
| `current_phase_node` | VARCHAR(50) | 当前执行的 DAG 节点 ID |

**现有表不变：** `project_chapters`, `project_members`, `approval_workflows`, `approval_records`, `collab_documents`, `collab_updates`, `collab_versions`, `collab_comments`。

### 3.4 Alembic 迁移


```python
def upgrade():
    # 1. 新增 workflow_definitions 表
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('report_type', sa.String(50), nullable=True),
        sa.Column('graph_json', sa.JSON(), nullable=False),
        sa.Column('is_template', sa.Boolean(), default=False),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # 2. 新增 content_sources 表
    op.create_table(
        'content_sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('chapter_id', sa.UUID(), sa.ForeignKey('project_chapters.id'), nullable=False),
        sa.Column('block_index', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(30), nullable=False),
        sa.Column('source_ref', sa.String(500), nullable=True),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_content_sources_chapter', 'content_sources', ['chapter_id', 'block_index'])

    # 3. 新增 phase_reviews 表
    op.create_table(
        'phase_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), sa.ForeignKey('report_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phase_node', sa.String(50), nullable=False),
        sa.Column('chapter_id', sa.UUID(), sa.ForeignKey('project_chapters.id'), nullable=True),
        sa.Column('reviewer_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('review_type', sa.String(20), nullable=False),
        sa.Column('dimension', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_phase_reviews_project_phase', 'phase_reviews', ['project_id', 'phase_node'])

    # 4. report_projects 新增字段
    op.add_column('report_projects', sa.Column('workflow_id', sa.UUID(), sa.ForeignKey('workflow_definitions.id'), nullable=True))
    op.add_column('report_projects', sa.Column('temporal_workflow_id', sa.String(100), nullable=True))
    op.add_column('report_projects', sa.Column('current_phase_node', sa.String(50), nullable=True))
```

### 3.5 DAG JSON 结构（React Flow 输出）

```json
{
  "nodes": [
    {
      "id": "phase-a",
      "type": "phase",
      "data": {
        "label": "现状调查",
        "team": "group-a",
        "chapter_range": [1, 3],
        "ai_assist": true,
        "input_from": []
      }
    },
    {
      "id": "review-1",
      "type": "review",
      "data": {
        "label": "分章节审核",
        "mode": "mixed",
        "chapter_assignments": [{"chapters": [1,2,3], "reviewer_id": "..."}],
        "dimension_assignments": [{"dimension": "技术", "reviewer_id": "..."}]
      }
    },
    {
      "id": "condition-1",
      "type": "condition",
      "data": {
        "label": "环评类型?",
        "expression": "report.subtype"
      }
    },
    {
      "id": "merge-1",
      "type": "merge",
      "data": { "label": "汇聚" }
    }
  ],
  "edges": [
    { "source": "phase-a", "target": "phase-b" },
    { "source": "phase-b", "target": "phase-c" },
    { "source": "phase-b", "target": "phase-d" },
    { "source": "phase-c", "target": "merge-1" },
    { "source": "phase-d", "target": "merge-1" },
    { "source": "merge-1", "target": "review-1" },
    { "source": "review-1", "target": "phase-e", "label": "approved" },
    { "source": "review-1", "target": "merge-1", "label": "rejected" }
  ]
}
```

## 4. 工作流执行引擎

### 4.1 DAG 节点类型 → Temporal 行为映射

| 节点类型 | Temporal 行为 | 信号/等待机制 |
|----------|--------------|--------------|
| `phase` | 执行阶段 Activity（初始化子项目、分配团队、AI 撰写） | `wait_condition` 等待 `phase:complete` 信号 |
| `review` | 创建审核分配（phase_reviews），等待所有人完成 | `wait_condition` 等待 `review:complete` 信号；rejected 回退 |
| `condition` | 评估表达式，选择分支 | 无等待，立即路由 |
| `ai_generate` | 调用 DeerFlow Agent 撰写章节 | `wait_condition` 等待 `ai:complete` 信号 |
| `merge` | 汇聚并行分支的输出，作为下游上下文 | `wait_condition` 等待所有上游分支完成 |

### 4.2 DynamicGraphWorkflow

```python
# backend/app/extensions/workflow/temporal/workflows.py

@workflow.defn
class DynamicGraphWorkflow:
    def __init__(self):
        self.phase_contexts: dict[str, dict] = {}
        self.review_results: dict[str, str] = {}
        self.ai_results: dict[str, dict] = {}

    @workflow.run
    async def run(self, params: dict) -> dict:
        definition = params["graph_json"]
        project_id = params["project_id"]
        nodes = {n["id"]: n for n in definition["nodes"]}
        edges = definition["edges"]

        # 拓扑排序
        topo_order = topological_sort(nodes, edges)

        # 找到所有 start 节点（无入边）
        current_nodes = find_start_nodes(edges)

        completed = set()
        results = {}

        while current_nodes:
            next_nodes = set()
            for node_id in current_nodes:
                node = nodes[node_id]
                node_type = node["type"]

                if node_type == "phase":
                    await workflow.execute_activity(
                        init_phase, {"node": node, "project_id": project_id, "input_contexts": ...},
                        start_to_close_timeout=timedelta(minutes=5),
                    )
                    # 等待外部 phase_complete 信号
                    await workflow.wait_condition(
                        lambda: node_id in self.phase_contexts,
                        timeout=timedelta(days=30),
                    )
                    results[node_id] = self.phase_contexts[node_id]

                elif node_type == "review":
                    await workflow.execute_activity(
                        create_review_assignments, {"node": node, "project_id": project_id},
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    # 等待所有审核完成
                    await workflow.wait_condition(
                        lambda: self._all_reviews_done(node_id, node),
                        timeout=timedelta(days=30),
                    )
                    if self._has_rejection(node_id, node):
                        # 退回：回退到配置的目标节点
                        target = self._get_rejection_target(node_id, edges)
                        current_nodes = {target}
                        continue

                elif node_type == "condition":
                    value = await workflow.execute_activity(
                        evaluate_condition, node["data"]["expression"],
                        start_to_close_timeout=timedelta(seconds=5),
                    )
                    # 路由到匹配的分支
                    matched_edges = [e for e in edges if e["source"] == node_id and e.get("label") == str(value)]
                    for edge in matched_edges:
                        next_nodes.add(edge["target"])
                    completed.add(node_id)
                    continue

                elif node_type == "merge":
                    # 等待所有上游完成
                    upstream = [e["source"] for e in edges if e["target"] == node_id]
                    await workflow.wait_condition(
                        lambda: all(u in completed for u in upstream),
                    )
                    merged_context = {u: results.get(u, {}) for u in upstream}
                    results[node_id] = merged_context

                elif node_type == "ai_generate":
                    await workflow.execute_activity(
                        start_ai_writing, {"node": node, "project_id": project_id},
                        start_to_close_timeout=timedelta(minutes=10),
                    )
                    await workflow.wait_condition(
                        lambda: node_id in self.ai_results,
                        timeout=timedelta(hours=2),
                    )
                    await workflow.execute_activity(
                        parse_and_store_sources,
                        {"chapter_id": node["data"]["chapter_id"], "content": self.ai_results[node_id]},
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    results[node_id] = self.ai_results[node_id]

                completed.add(node_id)

                # 找下游节点
                for edge in edges:
                    if edge["source"] == node_id and edge["target"] not in completed:
                        # 检查下游节点的所有上游是否都完成
                        downstream_upstream = [e["source"] for e in edges if e["target"] == edge["target"]]
                        if all(u in completed for u in downstream_upstream):
                            next_nodes.add(edge["target"])

            current_nodes = next_nodes

        return {"status": "completed", "results": results}

    # --- Signals ---

    @workflow.signal
    async def phase_complete(self, phase_node: str, context: dict):
        self.phase_contexts[phase_node] = context

    @workflow.signal
    async def review_action(self, review_id: str, action: str):
        self.review_results[review_id] = action

    @workflow.signal
    async def ai_complete(self, chapter_id: str, result: dict):
        self.ai_results[chapter_id] = result
```

### 4.3 上下文传递机制

- 每个阶段完成时，`phase_complete` Signal 携带阶段产物（章节内容摘要、关键结论、数据指标）
- Workflow 将上下文存在 `results` 字典中
- 下游阶段启动时，Activity 从 `results` 中提取上游上下文作为输入
- 并行汇聚时，merge 节点合并所有上游 `results` 为字典数组

### 4.4 Activities 列表

**阶段管理：**
- `init_phase(params)` — 初始化阶段（创建/分配章节、设置团队）
- `gather_phase_context(params)` — 收集阶段产物
- `advance_phase(params)` — 更新 `report_project.current_phase_node`

**AI 生成：**
- `start_ai_writing(params)` — 调用 DeerFlow Agent 撰写章节
- `parse_sources(params)` — 解析 AI 输出中的 `[source:type:id]` 标记
- `store_sources(params)` — 批量写入 `content_sources` 表

**审核：**
- `create_review_assignments(params)` — 从 DAG review 节点配置创建 `phase_reviews` 记录
- `check_reviews_complete(params)` — 查询是否所有审核已完成
- `handle_rejection(params)` — 处理退回，回退工作流

**通知：**
- `notify_phase_start(params)` — 通知团队阶段启动
- `notify_review_pending(params)` — 通知审核人有待审核
- `notify_workflow_complete(params)` — 通知经理工作流完成

## 5. AI 内容溯源

### 5.1 溯源采集流程

1. **Agent 生成内容时**：report-write Skill 要求 AI 在输出中标注 `[source:type:id]` 标记
2. **写入章节时**：MCP `write_chapter` Activity 调用 `traceability.parse_and_store_sources()` 解析标记，提取到 `content_sources` 表
3. **编辑器展示时**：BlockNote 自定义扩展渲染溯源标注（类似 Wikipedia 脚注）
4. **人工编辑时**：编辑器扩展自动将人工修改的块标记为 `human_written` 类型

### 5.2 标注格式

AI 生成内容中的溯源标记格式：

```
该区域 SO₂ 日均浓度为 0.045mg/m³[1]，低于国家标准限值 0.15mg/m³[2]。

[1] source:rag_retrieval:知识库「监测数据库」→「2024年度监测报告」p.23
[2] source:regulation:GB 3095-2012《环境空气质量标准》表2
```

### 5.3 source_type 枚举

| 类型 | 说明 | source_ref 示例 |
|------|------|----------------|
| `knowledge_base` | 知识库文档引用 | `kb:uuid/doc:uuid` |
| `rag_retrieval` | RAG 检索片段 | `kb:uuid/doc:uuid#chunk:5` |
| `ai_generated` | AI 模型生成 | `model:gpt-4o/thread:uuid` |
| `human_written` | 人工编写 | `user:uuid` |
| `template` | 模板预置内容 | `template:uuid/section:概述` |
| `external_data` | 外部数据源 | `api:监测站点/sensor:PM25` |

### 5.4 溯源缺失检测

后端提供 API 检测哪些段落/数据没有溯源标注，返回缺失列表和预警信息，前端在编辑器中高亮提示。

## 6. 多人分章节/维度混合审核

### 6.1 审核模式

| 模式 | review_type | 分配方式 | 说明 |
|------|-------------|---------|------|
| 按章节 | `chapter` | 指定章节 + 审核人 | 每人审核自己负责的章节 |
| 按维度 | `dimension` | 指定维度 + 审核人 | 每人审阅全部章节，但只关注特定维度 |
| 混合 | 两者并存 | 同一 review 节点内同时配置 | 既有章节分配，也有维度分工 |

### 6.2 审核执行流程

1. Workflow 到达 review 节点 → `create_review_assignments` Activity 从 DAG 配置创建 `phase_reviews` 记录
2. `notify_review_pending` Activity 通知各审核人
3. Workflow `wait_condition` 等待所有 `phase_reviews` 状态变为 `approved` 或 `rejected`
4. 审核人通过前端 `POST /phase-reviews/{id}/action` 提交审核结果 → 后端更新 `phase_reviews` 记录 + 发送 `review_action` Signal
5. 全部 approved → Workflow 推进到下游节点
6. 任一 rejected → Workflow 回退到 DAG 配置的目标节点（退回编辑）

### 6.3 审核维度预设

系统预设常见审核维度，经理也可自定义：

| 维度 | 说明 |
|------|------|
| `technical` | 技术准确性、数据合理性 |
| `compliance` | 法规合规性、标准符合度 |
| `language` | 语言表述、术语一致性 |
| `completeness` | 内容完整性、要素覆盖 |
| `format` | 格式规范、编号一致性 |

## 7. 前端组件

### 7.1 目录结构

```
src/extensions/workflow/
├── api.ts                          # Workflow API 客户端
├── types.ts                        # DAG 节点/边/实例类型
├── transforms.ts                   # snake/camel 转换
│
├── WorkflowEditor.tsx               # React Flow 工作流编排器
│   ├── nodes/
│   │   ├── PhaseNode.tsx            # 阶段节点
│   │   ├── ReviewNode.tsx           # 审核节点
│   │   ├── ConditionNode.tsx        # 条件分支节点
│   │   ├── AIGenerateNode.tsx       # AI 生成节点
│   │   └── MergeNode.tsx            # 汇聚节点
│   ├── edges/
│   │   └── ConditionEdge.tsx        # 条件边
│   ├── panels/
│   │   ├── PhaseConfigPanel.tsx     # 阶段属性配置侧边栏
│   │   ├── ReviewConfigPanel.tsx    # 审核分配配置
│   │   └── NodePalette.tsx          # 左侧节点拖拽面板
│   └── hooks/
│       ├── useWorkflowDAG.ts        # DAG 操作 hook
│       └── useValidation.ts         # DAG 校验（环检测、孤立节点）
│
├── WorkflowMonitor.tsx              # 工作流执行监控面板
│   ├── PhaseStatusCard.tsx          # 阶段状态卡片
│   ├── TimelineView.tsx             # 时间线视图
│   └── useWorkflowStatus.ts         # 轮询工作流状态 hook
│
├── TraceabilityPanel.tsx            # AI 溯源面板
│   ├── SourceAnnotation.tsx         # 段落溯源标注组件
│   └── SourceFootnote.tsx           # 脚注列表
│
└── PhaseReviewPanel.tsx             # 阶段审核工作台
    ├── ChapterReviewCard.tsx        # 章节审核卡片
    ├── DimensionReviewCard.tsx      # 维度审核卡片
    └── ReviewAssignmentDialog.tsx   # 经理分配审核对话框
```

### 7.2 WorkflowEditor

基于 React Flow 的可视化工作流编排器：
- **左侧** NodePalette：5 种节点类型可拖拽
- **中间** React Flow 画布：节点连线、状态可视化（已完成/进行中/待启动）
- **右侧** ConfigPanel：选中节点的属性配置（阶段名、团队、章节范围、审核分配等）
- **工具栏**：校验、存为模板、保存、加载模板

### 7.3 TraceabilityPanel

集成在 BlockNote 编辑器中：
- **编辑器内**：段落级溯源标注渲染，不同来源类型用不同颜色底纹 + 上标编号
- **编辑器下方**：脚注列表，展示每个标注的完整来源信息（知识库名/文档名/页码/置信度）
- **右侧面板**：本章溯源统计（按类型计数）+ 缺失预警

### 7.4 PhaseReviewPanel

审核工作台：
- **经理视图**：配置审核分配（左侧按章节分配审核人，右侧按维度分工）
- **审核人视图**：待审核章节列表 / 全文档按维度审阅，通过/退回按钮 + 意见输入
- **进度可视化**：审核进度条，显示各审核人的完成状态

## 8. 后端 API

### 8.1 新增端点

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/workflow/definitions` | 工作流模板列表 | project:list |
| POST | `/workflow/definitions` | 创建/保存工作流定义 | project:create |
| GET | `/workflow/definitions/{id}` | 获取 DAG JSON | project:read |
| POST | `/workflow/definitions/{id}/validate` | 校验 DAG | project:read |
| POST | `/projects/{id}/start-workflow` | 启动 Temporal 工作流 | project:advance |
| GET | `/projects/{id}/workflow-status` | 查询工作流状态 | project:read |
| POST | `/projects/{id}/workflow-signal` | 发送信号 | 视信号类型 |
| GET | `/projects/{id}/chapters/{ch_id}/sources` | 获取章节溯源 | chapter:view_all |
| POST | `/projects/{id}/phase-reviews/assign` | 分配审核人 | approval:submit |
| POST | `/projects/{id}/phase-reviews/{rev_id}/action` | 审核动作 | approval:review/approve |
| GET | `/projects/{id}/phase-reviews` | 审核状态 | approval:view |

### 8.2 现有 API 不变

所有现有 project/docmgr/collab API 保持不变。新功能通过新端点扩展。

### 8.3 后端目录结构

```
backend/app/extensions/workflow/
├── __init__.py
├── routers.py           # API 端点
├── schemas.py           # Pydantic models
├── service.py           # 业务逻辑（DAG 校验、状态管理）
├── permissions.py       # 工作流权限（复用 project permissions）
├── models.py            # SQLAlchemy models（4 新表）
├── temporal/
│   ├── __init__.py
│   ├── client.py        # Temporal Client 管理器
│   ├── workflows.py     # DynamicGraphWorkflow
│   ├── activities.py    # 全部 Activity 实现
│   └── signals.py       # Signal 定义
├── traceability.py      # 溯源解析服务
└── review.py            # 阶段审核服务
```

## 9. 分阶段交付

### Phase 1: 工作流引擎 + React Flow 编辑器 (~3 周)

**后端：**
- Docker 新增 temporal-auto-setup 容器
- FastAPI lifespan 集成 Temporal Client + Worker
- `workflow_definitions` 模型 + CRUD API
- `DynamicGraphWorkflow` 解释器
- Phase/Review/Merge Activity 实现
- DAG 校验服务（环检测、孤立节点）
- Signal 处理（phase_complete, review_action）

**前端：**
- React Flow 编辑器（5 种节点类型）
- NodePalette 拖拽面板
- PhaseConfigPanel / ReviewConfigPanel
- DAG 校验反馈 UI
- 存为模板 / 加载模板

**交付价值：** 项目经理可以可视化编排工作流，系统按 DAG 自动推进阶段。替代原有固定 6 阶段。

### Phase 2: AI 内容溯源 ✅ 已实现 (2026-05-30)

**后端：**
- ✅ `content_sources` 模型 + API
- ✅ 溯源解析服务（解析 [source] 标记）(traceability.py)
- ✅ MCP `write_chapter` Activity 集成溯源解析 — `update_chapter` 自动触发 `_auto_parse_sources`
- ✅ `start_ai_writing` Activity 实际调用 LLM 生成带来源标记的章节内容 (activities.py)
- ✅ 溯源缺失检测 API (`/chapters/{id}/sources/missing`)
- ✅ 手动解析端点 (`POST /chapters/{id}/sources/parse`)

**前端：**
- ✅ TraceabilityPanel 溯源面板 (TraceabilityPanel.tsx)
- ✅ SourceFootnote 脚注列表组件 (SourceFootnote.tsx)
- ✅ SourceAnnotation 标注组件 (SourceAnnotation.tsx)
- ⏳ BlockNote 自定义扩展：编辑器内溯源标注渲染 — 需 follow-up
- ⏳ 溯源统计面板（按类型计数）— 需 follow-up

**测试：** 12/12 tests passing (test_traceability.py)

**交付价值：** AI 生成内容自动标注来源、自动解析并持久化到数据库，手动解析端点可用。编辑器内渲染待完善。

### Phase 3: 多人分章节/维度混合审核 ✅ 已实现 (2026-05-30)

**后端：**
- ✅ `phase_reviews` 模型 + migration (models.py, database.py)
- ✅ 4 个审核 API 端点: assign, action, status, my-reviews (routers.py)
- ✅ Real activity implementations: init_phase, advance_phase, create_review_assignments, check_reviews_complete, handle_rejection, gather_phase_context, evaluate_condition (activities.py)
- ✅ Signal helper: send_signal for review completion → Temporal workflow (client.py)
- ✅ Application-side rejection rollback: apply_rejection_rollback (review.py)
- ✅ 审核维度预设 (technical/compliance/language/completeness/format)

**前端：**
- ✅ PhaseReviewPanel 审核工作台 (PhaseReviewPanel.tsx)
- ✅ ReviewAssignmentDialog 分配对话框 (ReviewAssignmentDialog.tsx)
- ✅ ChapterReviewCard / DimensionReviewCard (ChapterReviewCard.tsx, DimensionReviewCard.tsx)
- ✅ 审核进度可视化 (progress bar + status counts)

**测试：** 19/19 tests passing (test_phase_review.py + test_review_rollback.py)

### Phase 4: 工作流监控 + 条件分支 ✅ 已实现 (2026-05-30)

**后端：**
- ✅ Condition Activity 评估表达式路由 (evaluate_condition with report.* field lookup)
- ✅ 工作流状态查询 API: GET workflow-status, POST start-workflow, POST workflow-cancel
- ✅ POST workflow-signal 端点: 发送任意信号到运行中的工作流 (routers.py)
- ✅ Temporal client helpers: get_workflow_status, cancel_workflow, start_workflow, send_signal
- ⏳ Child Workflow 支持（子项目作为子工作流）— 延后，需 follow-up

**前端：**
- ✅ WorkflowMonitor 执行监控面板 (WorkflowMonitor.tsx)
- ✅ PhaseStatusCard 节点状态卡片 (PhaseStatusCard.tsx)
- ✅ TimelineView 时间线视图 (TimelineView.tsx)
- ✅ useWorkflowStatus 轮询 hook (hooks/useWorkflowStatus.ts)
- ✅ 启动/取消工作流按钮

**测试：** 3/3 tests passing (test_workflow_signal.py)

**交付价值：** 实时监控、条件分支支持差异化流程、信号发送端点。子工作流延后实现。

## 10. 向后兼容

- 无 `workflow_id` 的项目继续走原有固定 6 阶段逻辑，零迁移成本
- 新项目可选择使用工作流模式或传统模式
- `current_stage` 字段保留，工作流模式下从 `current_phase_node` 推导
- 所有现有 API、前端组件、MCP 工具保持不变

## 11. 技术选型

| 组件 | 选型 | 版本 |
|------|------|------|
| 工作流引擎 | Temporal.io | Server 1.27.0, Python SDK 1.27.0 |
| 前端流程编辑器 | React Flow | @xyflow/react latest |
| 溯源存储 | PostgreSQL JSONB | 复用 postgres-ext |
| 编辑器扩展 | BlockNote 自定义扩展 | @blocknote/react |
| 依赖管理 | uv (backend), pnpm (frontend) | 现有工具链 |
