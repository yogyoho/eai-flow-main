# 知识库实例详情页 Tab 打磨（P1）设计

- 日期：2026-08-10
- 状态：设计已确认，待 spec 复核
- 涉及项目：eai-flow（`D:\eai\eai-flow-main`）
- 参考来源：pisuan / 语析 Yuxi（`D:\eai\pisuan`）知识库详情页右侧 tab

## 1. 背景与目标

eai-flow 知识库详情视图（`KnowledgeBaseDetail`，现挤在 `frontend/src/app/knowledge/page.tsx` 第 628–1652 行）已有「左右分栏 + 右侧 2 个手写 button tab（检索测试 / 检索配置）」的骨架，且检索测试已端到端打通：`kbApi.chat` → `POST /api/extensions/knowledge-bases/{id}/chat` → `RAGFlowClient.chat()` → RAGFlow `/api/v1/retrieval`，返回 answer + chunks + 相似度。

存在四个问题：

1. 详情靠组件 `selectedKb` state 切换，URL 不变 —— 无法深链接、刷新即丢、无法分享。
2. 检索配置（top_k / similarity_threshold / vector_similarity_weight）只在请求时传入、存在 React 临时 state，每次进页面重置 —— 配置形同虚设。
3. 整个列表 + 详情 + 多个内联组件挤在 2565 行单文件 `page.tsx`。
4. 用手写 `<button>` 当 tab，而项目已有现成 shadcn `Tabs` 组件（`frontend/src/components/ui/tabs.tsx`，支持 `line` 下划线样式）未被使用。

**目标**：对齐 pisuan 的 KB 详情 tab 体验中**可用且有价值**的子集（检索测试 + 检索配置），在不动 deerflow harness 核心、不新建检索引擎的前提下完成打磨。

> 参考：pisuan 详情右侧有 5 个 tab（知识图谱 / 检索测试 / 知识导图 / RAG评估 / 评估基准），其中图谱/导图/评估依赖 LightRAG / Milvus / Dify 后端能力。eai-flow 的知识库检索是**纯 RAGFlow**（向量 + 关键词），不具备这些能力，故本轮只移植**检索测试 + 检索配置**两个 tab，其余明确 defer。

## 2. 硬约束

- **不得修改 deerflow harness 核心代码**（`backend/packages/harness/deerflow/**`）。harness 跟踪 bytedance 上游，定制只在 app / extensions / 前端层。全部后端改动限于 `backend/app/extensions/knowledge/**`（app 层）与 `backend/app/extensions/{models,schemas}/**`。
- **不新建后端检索引擎**。检索一律走既有 RAGFlow。
- **不做需要从 extension 层调 LLM 的功能**（因此砍掉示例问题生成）。
- 遵循既有 ABAC 权限与「extensions 走 agentflow DB」架构。

## 3. 范围

### In scope
1. 详情页拆为独立路由 `/knowledge/[kbId]`，支持深链接 / 刷新 / 分享。
2. 右侧 tab 换用 shadcn `Tabs`（`line` 样式）。
3. 检索配置持久化到 KB 模型（新增 `retrieval_config` JSON 列）。
4. `POST /{kb_id}/chat` 在请求未传检索参数时，回退使用持久化的 `retrieval_config`。
5. 检索测试 UX 打磨：内联 top-k 覆盖、结果按相似度降序、点 source 看 chunk 原文（复用 `ChunkModal`）。

### Out of scope（明确 defer）
- 示例问题生成（本轮砍掉）。
- rerank 模型配置（RAGFlow `/retrieval` 不直接吃该参数，加它有风险）。
- 知识图谱、知识导图、RAG 评估 / 评估基准（需新后端引擎，纯 RAGFlow 不支持）。
- agent 侧 MCP 取 KB 检索（当前 plain knowledge 扩展无 MCP；knowledge_factory 的 MCP 与此无关）。
- 任何 deerflow harness 核心改动。

## 4. 架构

### 4.1 前端文件结构

Next.js app router。`_components` 下划线前缀目录不参与路由。

| 文件 | 职责 | 说明 |
|---|---|---|
| `frontend/src/app/knowledge/page.tsx` | **只留列表**（`KnowledgeBaseManagement`） | 卡片点击由 `setSelectedKb` 改为 `router.push('/knowledge/{id}')`；原 2565 行大幅瘦身 |
| `frontend/src/app/knowledge/[kbId]/page.tsx` | **新详情路由（薄）** | 读 `params.kbId` → TanStack Query 取 KB（响应内含 retrieval-config） → 渲染 `<KnowledgeBaseDetail>` |
| `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx` | 从原文件抽出的详情组件 | 左右分栏 + shadcn `<Tabs>` |
| `frontend/src/app/knowledge/_components/{CustomSelect,DocStatusBadge,ChunkModal}.tsx` | 原内联小件抽出 | 列表 / 详情共用 |

API 层扩充位置：`frontend/src/extensions/api/index.ts` 的 `kbApi`。

### 4.2 后端

全部位于 `backend/app/extensions/knowledge/`（app 层），检索走既有 `RAGFlowClient`（`client.py`）。无新引擎、无 harness 改动。

## 5. 组件设计（右侧 Tabs）

shadcn `<Tabs defaultValue="test">`，两个 `<TabsContent>`：

### 5.1 检索测试 tab（`test`，默认）
- 查询 `<Textarea>` + `[格式化 / 原始]` 切换（保留既有）。
- **内联 top-k 数字框**：默认值取自已加载的 `retrieval_config.top_k`，可临时覆盖本次查询。
- 搜索按钮 → `kbApi.chat(kbId, { question, top_k, similarity_threshold, vector_similarity_weight })`（threshold / weight 取自配置）。
- 结果区：
  - `answer`（若有）。
  - `sources[]` **按相似度降序**，每条显示相似度 % + 分块内容预览；点击条目复用 `ChunkModal` 展示分块全文。
  - RAGFlow 失败时在结果区显错（沿用 chat 既有错误处理）。

### 5.2 检索配置 tab（`config`）
- 三个滑块，双向绑定 `retrieval_config`：
  - Top-K（整数，如 1–50）
  - 相似度阈值 similarity_threshold（0–1）
  - 向量权重 vector_similarity_weight（0–1）
- `[保存]` → `kbApi.updateRetrievalConfig(kbId, cfg)` → invalidate 配置 query + toast；`[重置]` → 回退未保存改动。
- 保留既有：只读「知识库信息」网格 + 数据授权面板（owner / admin 可见）。

> 注：字段为**静态渲染**（3 个已知字段），不做 pisuan 式后端 schema 驱动动态渲染（YAGNI）。

## 6. 数据模型

`backend/app/extensions/models/__init__.py` 的 `KnowledgeBase` 新增一列：

```python
retrieval_config = Column(JSON, nullable=True)
# 形如 {"top_k": 8, "similarity_threshold": 0.2, "vector_similarity_weight": 0.3}
```

- null 表示未配置，全部回退到请求默认值 / RAGFlow 数据集默认值。
- 配套 Alembic 迁移（或项目既有的扩展表建表机制 —— 实现期确认 eai-flow 扩展表的迁移工具链；若扩展表是启动自动建表，则补相应机制）。

`backend/app/extensions/schemas.py`：新增 `RetrievalConfig` Pydantic 模型；KB 响应模型带上 `retrieval_config`。

**默认值**（服务端常量，GET 时与存储值合并返回）：
```python
RETRIEVAL_CONFIG_DEFAULTS = {"top_k": 8, "similarity_threshold": 0.2, "vector_similarity_weight": 0.3}
```
> 若现有前端 React state 默认值与此不同，实现期沿用前端既有默认值，保持行为一致。

## 7. 后端契约

路由前缀 `/api/extensions/knowledge-bases`，文件 `backend/app/extensions/knowledge/routers.py`。

| 方法 路径 | 说明 | 权限 | 备注 |
|---|---|---|---|
| `GET /{kb_id}`（**改**） | 既有 KB 详情响应**带上 `retrieval_config`**（已与默认值合并：`{...DEFAULTS, ...(stored or {})}`） | `kb:read` | 既有接口的小改；前端无需单独取配置 |
| `PUT /{kb_id}/retrieval-config` | 校验 + 持久化 `retrieval_config` | `kb:update` | 新增；越界 422 |
| `POST /{kb_id}/chat`（**改**） | 请求未传 top_k / threshold / weight 时，回退用 `kb.retrieval_config` | 不变 | 既有接口的小改 |

`/chat` 回退语义（伪码）：
```python
cfg = kb.retrieval_config or {}
top_k = body.top_k if body.top_k is not None else cfg.get("top_k")
similarity_threshold = body.similarity_threshold if body.similarity_threshold is not None else cfg.get("similarity_threshold")
vector_similarity_weight = body.vector_similarity_weight if body.vector_similarity_weight is not None else cfg.get("vector_similarity_weight")
# 三者仍可能为 None → RAGFlowClient 透传 None → RAGFlow 用数据集默认
```

## 8. 数据流

1. 进 `/knowledge/{kbId}` → `kbApi.get(kbId)`（TanStack Query；响应内含合并后的 `retrieval_config`）→ 渲染。
2. 检索测试默认 top-k 来自已取 config；搜索时三参数随请求带上。
3. 配置保存 → `kbApi.updateRetrievalConfig(kbId, cfg)` → invalidate KB query（刷新配置）→ toast → 下次检索测试自动用新配置。
4. 列表卡片点击 → `router.push('/knowledge/{id}')`，不再用 state 切换。

## 9. 错误处理

- 检索测试 RAGFlow 失败 → 结果区显错（沿用 chat 既有处理）。
- 配置保存越界（top_k 超范围等）→ 前端滑块约束 + 后端 Pydantic 校验 422。
- KB 不存在 / 无权 → ABAC 已返回 403 / 404，详情页显示 not-found 状态。
- **空库**（无文档）→ 检索测试提示「请先上传文档」，搜索按钮置灰。

## 10. 测试

### 后端（pytest，Docker 内 `api-dev`）
- `test_retrieval_config_put_and_read`：`PUT` 持久化 → `GET /{kb_id}` 响应内带回（与默认值合并）；未配置时返回默认值。
- `test_chat_falls_back_to_persisted_config`：请求不传参数时用 KB 配置。
- 权限：非 owner `PUT /retrieval-config` → 403；普通读者 `GET /{kb_id}` 仍能看到配置（读权限即可）。

### 前端（Vitest）
- 两 tab 渲染、配置保存流（保存 → invalidate → toast）、检索测试结果按相似度排序、点 source 打开 `ChunkModal`。

## 11. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| （原）从 extension 层调 LLM 的路径不明 | ~~中~~ → **已消除** | 砍掉示例问题后，P1 不再需要任何 LLM 调用 |
| 抽离详情组件时打断列表页对共用小件的依赖 | 低 | 共用件（CustomSelect / DocStatusBadge / ChunkModal）一并抽到 `_components/`，两边 import |
| 扩展表迁移机制（Alembic vs 自动建表）未确认 | 低 | 实现期第一步确认；与既有扩展表保持一致 |
| `/chat` 回退语义改变现有调用方行为 | 低 | 仅在请求参数为 None 时回退；显式传参行为不变 |

## 12. 验收标准

1. 访问 `/knowledge/{某KB id}` 能直接进详情页；刷新仍在该页；列表卡片点击跳转到该 URL。
2. 右侧为 shadcn 下划线样式 2 tab。
3. 在检索配置 tab 改 top_k 并保存 → 切到检索测试 tab 搜索 → 结果条数受新 top_k 影响（验证回退生效）。
4. 检索测试结果按相似度降序，可点开 chunk 原文。
5. 后端单测 + 前端组件测通过；`make lint` / `pnpm typecheck` 通过。
6. `backend/packages/harness/deerflow/**` 零改动（git diff 可验）。
