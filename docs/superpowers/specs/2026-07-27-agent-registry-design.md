# Agent 注册表（数字员工看板）设计

- **日期**: 2026-07-27
- **状态**: Draft（待评审）
- **分支**: `main-dev-fork`
- **范围**: 大重构「泛化为 AgentSpace 式人+agent 协作 workspace」的 **子项目 #1（地基）**
- **参照**: [HKUDS/AgentSpace](https://github.com/HKUDS/AgentSpace) — `apps/web/features/agents/`（Digital Employee Board）
- **样式**: 复用本系统 `frontend/src/extensions/dashboard/` 的视觉风格

---

## 1. 背景与目标

### 1.1 上层目标（本 spec 的母体）
借鉴 AgentSpace 的功能设计思路，把本系统的「项目管理 + 工作台」从**人驱动的报告生产工作流**演进为**人 + agent 协作的通用 workspace**，agent 成为项目/任务的一等参与者。

该跨度太大，无法用单个 spec 承载，已拆为 6 个独立子项目（见 §11）。**本 spec 只覆盖子项目 #1：Agent 注册表（数字员工看板）**——它是其余所有子项目的地基（没有一等 agent 实体，就无法把 agent 指派到任务/项目）。

### 1.2 现状（必须先理解的起点）
- **custom-agent = `lead_agent` 的运行时配置**，以 `agent_name` 字符串为身份；后端 `AgentConfig` = `{name, description, model, model_settings, thinking_enabled, reasoning_effort, tool_groups, skills, soul, github}`，前端只看到一半。
- **持久化双后端**（`deerflow.persistence.agents`）：file（默认，`users/{user_id}/agents/{name}/`）或 db（`agents` 表：id/user_id/name/config JSON/soul）。经 `get_agent_store()` 派发。
- **严格 per-user 隔离**：A 的 agent 对 B 不可见不可改（上游 deer-flow 设计）。
- **缺口**：无 `owner_id`、无 `status`/`readiness`、无 `role`/`avatar`、无 `org`/`visibility`、无 per-agent MCP 绑定（MCP 全局）、无稳定代理主键（FE 拿 name 当主键）、无 Edit UI（存在一个 dead 的 `AgentSettingsDialog` 可复活）、无 search/filter。
- **agent 参与项目极浅**：仅靠 ① 项目 MCP server（`project/mcp.py`）② Temporal DAG 的 `ai_generate` 节点 ③ 每成员一个 DeerFlow thread。数据模型里没有任何 `agent_id`/指派 agent 的字段。
- Built-in（`lead_agent`、subagent `general-purpose`/`bash`）是**另一套**（harness 代码常量），不在 custom-agents 体系内。

### 1.3 本子项目目标
把现有 custom-agents **升级为一等组织资源**（AgentSpace Digital Employee Board），交付：
1. **注册表元数据层**（owner/status/readiness/role/avatar/稳定 ID/per-agent MCP 绑定声明）。
2. **组织级看板**（双栏列表+详情、搜索筛选、画廊模式）。
3. **真正的编辑 UI**（含 harness 配置编辑，复活 dead dialog）。
4. **Built-in agent 只读露出**。

### 1.4 关键决策（brainstorm 已确认）
| 决策 | 选择 | 理由 |
|---|---|---|
| 重构方向 | 泛化为通用协作 workspace | 用户选择 |
| 首个子项目 | Agent 注册表 | 地基、纯新增、零存量风险 |
| 可见性模型 | **组织级可见** | 贴 AgentSpace「数字员工」本质 |
| 范围档位 | **MVP：注册表 + 看板 + 编辑** | 借用/转移/导出/审批留后续 |
| 架构方案 | **方案 1：app 层投影 + write-through + 懒同步** | 唯一不动 harness 且真交付 MVP 的路径 |
| 模块形态 | **全新独立模块**，不改现有 dashboard/project/project-detail | 用户明确要求降风险 |
| UI 参照 | AgentSpace 页面布局/操作 | 用户明确要求 |
| UI 样式 | 完全采用 dashboard 风格 | 用户明确要求 |

---

## 2. 非目标（明确排除 / 留到后续子项目）

- ❌ 修改现有 `extensions/dashboard`、`extensions/project`、`extensions/approval`、`extensions/shell`（除 Sidebar 加一行导航，见 §6.2）的任何业务代码。
- ❌ 修改 deer-flow harness 核心（`backend/packages/harness/deerflow/`）。只通过其公开 API 调用。
- ❌ per-agent MCP **运行时强制执行**（harness 全局加载 MCP，短期无法按 agent 过滤）。MVP 只存**声明性元数据**。
- ❌ 借用/请求流、跨 owner 转移、persona 导出、owner 审计/吊销队列（→ 后续「治理/借用」子项目）。
- ❌ 把 agent 指派到任务/章节、多 agent 协作、agent 任务执行桥（→ 子项目 #2/#3）。
- ❌ 通用 Project 抽象、工作台重做、治理整合（→ 子项目 #4/#5/#6）。
- ❌ 多租户 `org_id` 的实际使用（字段预留，值恒 NULL）。

---

## 3. 设计护栏（硬约束）

1. **不动 harness 核心**：所有新代码在 `backend/app/extensions/agent_registry/` + `frontend/src/extensions/agent_registry/` + config。harness 只被其公开 API 调用（`get_agent_store()`、`list_all()`、`load_agent_config/load_agent_soul`）。
2. **不改现有模块**：dashboard/project/approval 业务代码零改动；样式通过 **import 现有 `dashboard.css`** 复用（dashboard 改了我们联动）。
3. **EAI 定制注释**：所有新增的对 deer-flow 上游行为的定制/覆盖加 `EAI-CUSTOM` 注释。
4. **提交到 `main-dev-fork`**（不提交 `main`）。
5. **harness/app 边界**：保持 `tests/test_harness_boundary.py` 绿（app import deerflow，反向禁止）。

---

## 4. 架构（方案 1：app 层投影）

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: extensions/agent_registry（新模块，dashboard 风格）   │
│    看板(列表+详情) · 画廊 · 创建/编辑                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ /api/extensions/agent-registry (cookie-JWT)
┌──────────────────────────┴──────────────────────────────────────┐
│  Backend: app/extensions/agent_registry（新）                    │
│    routers · service · schemas · models(AgentRegistry)           │
│                                                                   │
│    ┌─ agent_registry 表 (PostgreSQL agentflow) ─┐                │
│    │  组织级元数据投影（owner/status/readiness…）│                │
│    └─────────────────────────────────────────────┘                │
│         │ write-through + 懒 reconcile                            │
│         ▼  (公开 API: get_agent_store / list_all)                 │
└─────────┬─────────────────────────────────────────────────────────┘
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Harness: deerflow.persistence.agents（不动）                     │
│    file 后端 / db 后端  ←  config(model/tool_groups/skills/…)     │
│                            + SOUL.md  （运行时真源）              │
│                                                                   │
│  lead_agent 运行时：照旧从 harness store 加载，零改动             │
└─────────────────────────────────────────────────────────────────┘
```

**核心思想**：harness agent store 是 config/SOUL 的运行时真源（`lead_agent` 零改动加载）；`agent_registry` 是一张 app 层投影表，只存「看板能独立渲染 + 组织元数据」。两者通过 `(source_user_id, agent_name)` 关联。

---

## 5. 数据模型

### 5.1 新表 `agent_registry`
落 `backend/app/extensions/models/__init__.py`，并在 `backend/app/extensions/database.py::migrate_db()` 加 `CREATE TABLE IF NOT EXISTS`（沿用项目「无 Alembic」约定）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID pk | **稳定代理主键**（补 FE 拿 name 当主键的痛点） |
| `agent_name` | str, idx | harness 身份键（lowercase `[a-z0-9-]+`） |
| `source_user_id` | str, idx | harness per-user 桶（config/SOUL 物理归属） |
| `owner_id` | str, idx | 注册表管理者（创建时 = `source_user_id`；分开存为未来 transfer 留口） |
| `org_id` | str, null | 多租户预留；现在恒 NULL |
| `display_name` | str, null | 人读名（与 slug 解耦） |
| `role` | str, null | 如「环评撰写员/审核员/通用助手」 |
| `summary` | str, null | 看板一句话 |
| `avatar` | str, null | 头像 URL/emoji |
| `status` | str, default `active` | `active\|idle\|busy\|error\|disabled\|orphaned` |
| `readiness` | str, default `ready` | `draft\|ready\|prod` |
| `visibility` | str, default `org` | `org`(全员可见看板) \| `private`(仅 owner) |
| `skills_snapshot` | str[], null | 缓存 `AgentConfig.skills`，看板筛选用（避免每行回 harness） |
| `mcp_servers` | str[], null | **声明性** MCP 绑定（MVP 仅展示，运行时仍全局，强制留后续） |
| `tags` | str[], null | 自由标签 |
| `last_synced_at` | datetime, null | 上次与 harness reconcile 时间 |
| `created_at` / `updated_at` | datetime | — |

约束：`UniqueConstraint(source_user_id, agent_name, name="uq_agent_registry_source_name")`。

**刻意不放进本表**：`model / tool_groups / model_settings / soul / thinking_enabled / reasoning_effort` —— 留在 harness store（运行时真源）。详情页按需回 harness 取（仅 owner 取全量）。

### 5.2 与 harness 的关系
```
agent_registry 行 ──(source_user_id, agent_name)──> harness AgentStore
                                                         ├─ config (model/tool_groups/skills/model_settings…)
                                                         └─ SOUL.md
```
- 看板列表：只读 `agent_registry`（快、可查、组织级）。
- 运行：`lead_agent` 照旧从 harness store 加载，零改动。
- 详情/编辑：owner 走 harness 公开 API 读写 config/SOUL；registry 行同步元数据。

### 5.3 Built-in agent（只读，不入表）
看板合并 `agent_registry` 行（可编辑）+ 内存枚举的 built-in（`lead_agent`、subagent `general-purpose`/`bash`，经 `subagents/registry.py` 只读列出）。后者打「系统」徽标、不可编辑/删除。`GET /builtins` 请求时现读，新加 subagent 自动反映。无 harness 改动。

### 5.4 可见性 / SOUL 访问规则（MVP）
- **看板列表**（任一登录用户）：所有 `visibility='org'` 行的**公开元数据**（display_name/role/owner 用户名/status/readiness/skills_snapshot/mcp_servers/tags）+ 自己的 `private` 行。**不暴露 SOUL / 系统提示词 / model_settings。**
- **详情**：**owner** 看全量（含 harness config + SOUL）；**非 owner** 只看公开元数据。
- **编辑/删除**：仅 `owner_id == effective_user_id`。

### 5.5 迁移默认（首启懒同步）
用 harness `list_all()` 扫出所有 `(user_id, agent_name)`，逐个建 registry 行：`owner_id=source_user_id=user_id`、`visibility='org'`（贴合组织级可见）、`status='active'`、`readiness='ready'`、`skills_snapshot` 从 harness config 回填。**SOUL 永不进 registry、永不向非 owner 暴露**。

### 5.6 关键简化（避免跨用户 harness 加载）
- 看板列表只读 `agent_registry` 表（org 级投影，天然跨用户）。
- owner 查自己详情 = `effective_user_id == source_user_id`，自然命中 harness。
- 非 owner **只看 registry 元数据，从不碰 harness** → MVP 无需跨用户加载 config。唯一系统级枚举是 `list_all()`（GitHub 注册表有先例）。

---

## 6. 前端 / UI

### 6.1 样式地基（零改 dashboard）
- 新模块 **import** `extensions/dashboard/dashboard.css`（保证风格联动）。
- 页面根容器套 `.dashboard-shell.cyber-grid`，复用 `db-card` / `glow-cyan|purple|green|red` / `font-cyber` / 双语标签（中文 + 大写英文 cyber tag）/ 暗色模式 token。
- 12 栏网格 + Header + MetricsRow + footer 与 dashboard 同款。

### 6.2 路由与导航
- 新路由 `/workspace/agent-board`；模式走 query：默认 `agent`（双栏），`?view=showcase`（画廊）。
- 导航：`extensions/shell/Sidebar.tsx` 加一项「数字员工 `DIGITAL EMPLOYEES`」——**唯一轻微触点**（一行）。若要完全隔离，改为模块自注册导航（二选一，见 §10 开放问题）。

### 6.3 看板主视图（`agent` 模式）— 参照 AgentSpace 左列表+右详情
```
┌─ dashboard-shell cyber-grid ──────────────────────────────────────┐
│ HEADER  数字员工看板 · DIGITAL EMPLOYEES        [画廊] [+ 新建]    │
│ MetricsRow  总数·在线·生产就绪·按角色分布(迷你卡)                  │
├──────────────────────┬────────────────────────────────────────────┤
│ LEFT 列表面板 db-card │ RIGHT 详情面板 db-card  (flex-1, 可拖动分隔)│
│  🔍 搜索  ⬇筛选       │ ┌ 头部 band ─────────────────────────────┐ │
│  全部员工 (12)        │ │ [avatar] display_name   角色徽          │ │
│ ─ 系统 SYSTEM ─       │ │ owner · status●(glow) · readiness       │ │
│   lead_agent    🔒    │ │ [对话] [编辑] [删除]                    │ │
│   general-purpose🔒   │ └─────────────────────────────────────────┘ │
│ ─ 我的 MINE ─         │ Tabs: 概览 | 配置*(owner) | 活动           │
│   环评撰写员-A   ●    │ ┌ 概览 ─────────────────────────────────┐ │
│   审核员-B       ●    │ │ summary · skills chips · mcp chips     │ │
│ ─ 团队 TEAM ─         │ │ tags · runtime: model/tool_groups      │ │
│   通用助手-C     ○    │ │ *(owner 看全量; 非owner 仅公开元数据)   │ │
└──────────────────────┴────────────────────────────────────────────┘
```
- **左列表**（参照 AgentSpace，增强为 org 看板）：搜索 + 筛选（status/readiness/role/owner）；分组默认「系统 / 我的 / 团队」（比 AgentSpace 的 Bound/Unbound 更贴组织场景）；每行 = avatar + display_name + role + status 圆点（glow 配色）。窄屏塌缩为单栏 + 返回栏（AgentSpace 同款）。
- **右详情**（= AgentSpace `AgentDetail`）：头部 band + 三 Tab。「对话」深链到现有 `/workspace/agents/[name]`（不改那模块）；「编辑/删除」仅 owner。

### 6.4 Tab 内容
| Tab | 内容 | 可见性 |
|---|---|---|
| **概览 Overview** | summary、skills chips、mcp_servers chips、tags、runtime 摘要(model/tool_groups) | 所有人（非 owner 只看公开元数据，无 SOUL/无 model_settings） |
| **配置 Config** | display_name/role/summary/avatar/status/readiness/visibility + harness 配置(model、model_settings/thinking/reasoning（复活 dead `AgentSettingsDialog` helpers）、tool_groups、skills 选器、mcp_servers 选器、SOUL 编辑框)。保存 = write-through | **仅 owner** |
| **活动 Activity** | 最近运行/同步时间(`last_synced_at`)，MVP 轻量 | owner（非 owner 可看摘要） |

### 6.5 创建 / 编辑
- **新建弹窗**（参照 AgentSpace `CreateAgentModal`，dashboard 风）：`agent_name`(slug，复用现有 `/api/agents/check` 查重) + display_name + role + summary + status/readiness/visibility + model + skills 选器 + mcp_servers 选器(从 `extensions_config` 列) + SOUL。提交 → registry API write-through → 跳进详情。
- **编辑** = 详情页「配置」Tab inline 编辑（非单独弹窗），owner 专属。

### 6.6 画廊模式（`?view=showcase`）— 参照 AgentSpace `DigitalEmployeeShowcase`
全宽大卡片网格（`visibility=org`）：avatar + 名 + 角色 + owner + readiness + skills + `[对话/查看]`。**MVP 不做** access-request（approve/reject/request-copy）——留到「借用/请求」子项目。

### 6.7 与 AgentSpace 的偏离（明确标出）
| 点 | AgentSpace | 我们 | 原因 |
|---|---|---|---|
| 列表分组 | Bound/Unbound（按 runtime 绑定） | 系统/我的/团队（按 owner） | 我们都跑在 lead_agent 上，Bound 概念不成立 |
| 搜索/筛选 | 无 | 有（status/readiness/role/owner） | org 级 agent 多，必须能筛 |
| 执行引擎/容器面板 | `container` 模式 + daemon 管理 | 不做 | DeerFlow 自带 runtime |
| Google Workspace / Feishu / fork 邀请 | 有 | 不做 | 超出 MVP |

---

## 7. 同步策略

### 7.1 Write-through（registry API = 管理入口）
- **创建**：registry service 调 harness `get_agent_store()` 写 config/SOUL → 插 registry 行。
- **编辑**：harness 配置字段 + registry 元数据字段 一次逻辑事务同更新。
- **删除**：harness agent + registry 行同删。

### 7.2 懒 reconcile（兜底带外写入）
- **触发**：`LIST`（看板拉取）时 + 可选定时清扫。
- **机制**：harness `AgentStore.list_all()` → 对每个 `(user_id, agent_name)` upsert registry 行（缺则按默认建；刷新 `skills_snapshot`、`last_synced_at`）。
- **孤儿**：registry 行的 `(source_user_id, agent_name)` 已不在 `list_all()`（被旧 `/api/agents` 或 chat 工具删了）→ 标 `status='orphaned'`，**不自动硬删**，露给 owner 清理。
- **chat 工具直写**（`setup_agent`/`update_agent`，harness 不动）：靠下一次 LIST 的懒 reconcile 兜回。可接受的短窗。

### 7.3 并发
reconcile 幂等（`UniqueConstraint` → `ON CONFLICT DO UPDATE`）；write-through 按 id 行级更新。

---

## 8. API 接口

路由前缀 `/api/extensions/agent-registry`，注册到 `backend/app/gateway/app.py`，走现有 cookie-JWT 鉴权。

| Method | Path | 说明 |
|---|---|---|
| GET | `/agents?q=&status=&readiness=&role=&owner_id=&group_by=` | 看板列表（先 reconcile 再返回）；公开元数据 + 自己的 private |
| GET | `/agents/{id}` | 单行；owner 可 `?full=true` 带 harness 配置 |
| GET | `/agents/{id}/config` | **owner only** harness 全量 config + SOUL；非 owner → 403 |
| POST | `/agents` | 创建（write-through） |
| PATCH | `/agents/{id}` | 更新元数据 + (owner) harness 配置；非 owner → 403 |
| DELETE | `/agents/{id}` | **owner only** 删 harness + registry；非 owner → 403 |
| GET | `/builtins` | 只读枚举 lead_agent + subagents |
| GET | `/meta/filters` | 角色/owner/tag 去重列表（筛选用） |
| POST | `/reconcile` | 强制清扫（admin/owner） |

**访问控制（服务端强约束）**：list 看 `org` 行 + 自己 `private`；config/edit/delete 仅 `owner_id == effective_user_id`。**SOUL/系统提示词/model_settings 永不跨 owner 返回**（写测试盯死）。

---

## 9. 边界 / 错误 / 测试 / 上线

### 9.1 边界 & 错误
- **双写半失败**：harness 成功 + registry 失败 → 重试 registry upsert；harness 失败 → 报错不建行。恢复 = 下次 reconcile（harness 是真源）。
- **重命名**：harness 里 name 是不可变自然键 → 无重命名漂移。`display_name` 可改。
- **规模**：`list_all()` 在 agent 极多时可能慢 → registry 列表分页 + reconcile 批处理（先这样，不够再优化）。
- **泄漏防线**：服务端强制 + 测试验证非 owner 拿不到 SOUL。
- **鉴权/参数/未找到**：401/403/422/404，沿用 gateway 既有中间件。

### 9.2 功能开关
新增 `agent_registry.enabled`（默认 off），独立于现有 `agents_api.enabled`。可暗发布。

### 9.3 测试
- **后端 pytest**（`make test`）：write-through 一致性、reconcile（带外建 agent → 出现行 + snapshot 刷新 + 孤儿标记）、访问控制（非 owner GET config→403、GET detail 无 SOUL）、builtins。
- **前端**：board 列表/详情渲染、筛选逻辑、owner vs 非 owner UI 门控的单测；create→edit→delete 的 Playwright e2e。
- **harness 边界测试** `tests/test_harness_boundary.py` 保持绿。

### 9.4 上线（全增量、可暗发布、零改既有模块）
1. 后端：建表 + reconcile + API（flag=off）→ 跑一次 reconcile 回填存量。
2. 前端：看板只读（list + 详情，无编辑）验证投影。
3. 开创建/编辑/删除（write-through）。
4. 导航对全员可见。

### 9.5 文件清单
- **后端**：`agent_registry/{__init__,models,schemas,service,routers}.py` + `models/__init__.py` 加 `AgentRegistry` + `database.py::migrate_db` 加建表 + `gateway/app.py` 注册路由 + config 加 flag。
- **前端**：`extensions/agent_registry/{types,api,hooks,index}` + `components/`(BoardList/AgentDetail/AgentCard/ConfigTab/CreateAgentModal/SkillPicker) + `app/workspace/agent-board/page.tsx`(+`?view=showcase`) + Sidebar 一行 + import `dashboard.css`。
- 全程 `EAI-CUSTOM` 注释；提交 `main-dev-fork`。

---

## 10. 开放问题

1. **导航接入方式**：`shell/Sidebar.tsx` 加一行（最简，但触现有文件） vs 模块自注册导航（完全隔离，需看 shell 是否有注册机制）。→ 实施时定，倾向自注册若可行。
2. **样式复用方式**：直接 import `dashboard.css`（联动） vs 抽公共 token 文件。→ 倾向直接 import（YAGNI）。
3. **status `orphaned` 的清理 UX**：owner 看到孤儿行后是「一键清理」还是「恢复」？→ 实施时定，倾向先只读展示 + 手动删。

---

## 11. 后续子项目（母体重构全景，供上下文）

| # | 子项目 | 依赖 | 备注 |
|---|---|---|---|
| **1** | **Agent 注册表 / 数字员工看板**（本 spec） | 无 | 地基 |
| 2 | 通用 Task + 指派（人/agent） | 1 | 统一任务板，喂工作台 |
| 3 | Agent 任务执行桥 | 1+2 | 派 agent 跑任务、产出回写 |
| 4 | 通用 Project 抽象（ReportProject→Project(kind)） | 可与 2 并行 | 报告流变模块，迁数据 |
| 5 | 治理整合（合并 3 套审批 + agent 行为门 + 审计） | 1 | 清技术债 |
| 6 | 工作台重做（AgentSpace 式总览） | 1,2 | 最后整合 |

> 每个子项目各自走 spec → plan → implement。本 spec 仅授权 #1。

---

## 12. 决策日志

- **2026-07-27** 重构方向定为「泛化为通用协作 workspace」，拆 6 子项目，首做 #1 Agent 注册表。（用户确认）
- **2026-07-27** 可见性选「组织级可见」；架构选「方案 1 app 层投影」；范围选「MVP 注册表+看板+编辑」。（用户确认）
- **2026-07-27** 用户要求：新功能做成**全新独立模块**，不改现有 dashboard/project/project-detail（风险太高）。
- **2026-07-27** 用户要求：UI 全面参照 AgentSpace 页面，样式完全采用 dashboard 风格。
