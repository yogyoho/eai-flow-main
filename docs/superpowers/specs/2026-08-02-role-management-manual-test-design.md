# 角色管理全面页面测试方案（人工）

> 日期：2026-08-02 | 状态：待执行
> 前置设计：`docs/superpowers/specs/2026-08-01-role-management-yaml-driven-design.md`（yaml 驱动 RBAC + ABAC-lite）
> ABAC 现状结论：**功能级 ABAC 已生效**（`require_permission` → UnifiedPermissionEngine → DB policies 表被评估）；**数据级 ABAC（DataScope）仅 knowledge 一个模块接线**，contract_price/project 声明未接线（I4 延后，见 §1.3）。

---

## 0. 元信息

### 0.1 目标环境

- **URL**：`http://localhost:3000`（宿主机前端 dev，HMR 快）
- **启动**：`cd frontend && SKIP_ENV_VALIDATION=1 DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://localhost:2026 pnpm dev`
  - `next.config.js` 把 `/api/*` 代理到 nginx:2026 → gateway，浏览器同源 → 免 CORS，cookie/CSRF 正常
- **改动生效规则**：
  - 前端改动 → HMR 秒级生效（无需重启容器）
  - 后端 `.py` 改动 → `docker compose -p eai-docker restart gateway`
  - 仅改 `config/permissions.yaml` / `config/roles_custom.yaml` 授权 → **无需重启**（bind-mount + registry mtime 热重载，下一请求生效）
- **坑提醒**：`pnpm dev` 停止后可能残留孤儿 `next dev` 占 3000 → `Stop-Process -Id <PID> -Force` 后再启动
- **登录**：`admin@eai-flow.com` / `Admin@2026`（superadmin）

### 0.2 测试账号

- **测试员自备**。Phase 2 需要：superadmin（已有）+ 各角色账号（dept_head / project_manager / writer / reviewer / user）。
- 用 superadmin 登录 → `/admin/users` → 创建账号 → `/admin/roles` 分配角色。
- 每角色预期行为见 §4 矩阵。测完可删除（不影响生产数据）。

### 0.3 缺陷分级

| 级别 | 定义 |
|---|---|
| P0 | 阻塞：功能不可用 / 数据破坏 / 越权访问 |
| P1 | 严重：权限失效 / 核心交互错误 / 数据丢失风险 |
| P2 | 一般：UI 错乱 / 文案错误 / 边界情况 |
| P3 | 建议：体验优化 / 非关键 |

### 0.4 通过标准

1. Phase 1：所有页面 P0 检查项 PASS。
2. Phase 2：无 P0/P1 缺陷；P2 缺陷 ≤ 5（均记录）。
3. 已知预期失败项（§5.2）均确认为 confirmed-known（行为与描述一致即记为「确认，非新增」）。
4. 写操作（角色增删改）测后已恢复快照。

---

## 1. 范围

### 1.1 覆盖

- **Phase 1**：全系统业务页面遍历（§3，38 页）
- **Phase 2**：角色权限深度验证（§4）——RBAC 强制点 + ABAC 策略 + 前端按钮级 gate

### 1.2 排除

- `blog/` `docs/` `[lang]/docs/` 文档站
- `(auth)/login`、`(auth)/setup`、`(auth)/auth/callback`
- `/test-editor`（测试占位页）

### 1.3 已知基线（测试时勿当作新缺陷）

| 基线 | 说明 |
|---|---|
| 前端 127 pre-existing type errors | `pnpm typecheck` 既有基线，与本次改动无关 |
| 后端 420 pre-existing 测试失败 | 既有基线（`make test` 全量）；回归只跑增量相关用例 |
| **数据级 ABAC 未接线** | contract_price / project 的 `data_scopes` 在 yaml 已声明但查询未应用 → §4.5 标 N/A |
| `policy.grants.data_scope` 死字段 | 引擎只消费 `grants.permissions`，data_scope 维度被忽略 → §4.4 确认即可 |

---

## 2. Phase 0 前置修复（权限正确性 —— 必须先在代码上完成再测）

> 目的：把 dashboard/approval/law 三个 router 从 `system:access` 统一收口切换为模块级权限 + 读写拆权，迁移 workflow-admin 显示名判定。**本阶段是代码改动，测试员不参与；执行完并回归通过后再开始 Phase 1。**

### 2.0 前置

- 快照：`git status` 记录 `config/permissions.yaml`、`config/roles_custom.yaml`、`backend/app/extensions/{dashboard,approval,law}/routers.py` 当前状态。
- 改完重启：`docker compose -p eai-docker restart gateway`。

### 2.1 dashboard router → `dashboard:view`

- 文件：`backend/app/extensions/dashboard/routers.py`
- 现状：`DashboardUser = Annotated[CurrentUser, Depends(require_permission("system:access"))]`（整 router）
- 改：
  - 读端点（list/overview/summary/reminders 等）→ `require_permission("dashboard:view")`
  - 若存在写端点（create/update/delete/check-reminders 触发类）→ 拆为对应 `dashboard:*` 写权限点（先在 permissions.yaml 声明）
- 安全核对：所有角色均已持 `dashboard:view`（§4.1），无可见回归。
- 验证：① dept_head 登录访问 `/dashboard` 200；② 无 dashboard:view 的角色（如有自定义角色）403。

### 2.2 approval router → `approval:*`（读/写拆权）

- 文件：`backend/app/extensions/approval/routers.py`
- 现状：`CurrentUserWithAccess = require_permission("system:access")`
- 改（**逐端点列出读/写归属**）：
  - 读端点（list submissions / my approvals / 审批详情）→ gate = **`approval:view` OR `approval:review`（union）** ⚠️
  - 写端点：submit → `approval:submit`；review 操作 → `approval:review`；approve → `approval:approve`
- **⚠️ 风险（cerebrum 教训）**：`approval:view` 仅 dept_head 持有；**reviewer 只有 `approval:review` 无 `approval:view`**，writer 无任何 approval 权限。若读 gate 用单点 `approval:view`，reviewer 将看不到审批列表 → **读 gate 必须 union 或给 reviewer 补 `approval:view`**。改前先 grep `permissions.yaml` 核对目标角色权限（Do-Not-Repeat）。
- 验证：reviewer 能看到待我审批；dept_head 能看全部并可 approve；writer 提交 403（若无审批权限——需与产品确认 writer 是否应可 submit）。

### 2.3 law router → `kf:law:*`

- 文件：`backend/app/extensions/law/routers.py`
- 现状：`system:access`
- 改：读端点 → `kf:law:read`；写端点（create/update/delete）→ `kf:law:edit`
- 角色核对：dept_head 有 `kf:law:read` 无 `kf:law:edit` → 只读（产品意图确认）；project_manager 继承 read 但无 knowledge-factory 入口（观察点，非缺陷）。
- 验证：dept_head GET `/api/kf/laws*` 200；POST 403；superadmin 两者皆可。

### 2.4 `permissions.yaml` 补授权

- 按 §2.2/§2.3 决定是否补：`approval:view` 给 reviewer、`approval:submit` 给 writer（按产品意图）。
- 原则：**additive**（只加不删）；补完用 §4.1 矩阵核对一致性。

### 2.5 workflow-admin `is_admin` 迁移

- 文件：`frontend/src/app/workflow-admin/page.tsx`、`frontend/src/app/workflow-admin/components/TemplateEditorPage.tsx`
- 现状：两处 `role_name === "Super Admin"`（显示名硬编码，中文/英文都会漏判）
- 改：`usePermission().is_admin`（或 `/api/permissions/me` 的 `is_admin`）判定，覆盖改名但仍 `is_system` 的超管。
- ⚠️ 改后 HMR 即时生效（宿主机 :3000）。

### 2.6 回归

- 后端：`cd backend && PYTHONPATH=. uv run pytest tests/test_permission_registry.py tests/test_permission_engine.py tests/test_p0_permission_gates.py tests/test_unified_project_permissions.py -q`
- 前端：`cd frontend && pnpm typecheck`（仅确认本次改动文件无新增错误）
- 通过后才进入 Phase 1。

---

## 3. Phase 1 全系统页面遍历（superadmin）

### 3.0 操作指引

- superadmin 登录 `http://localhost:3000`。
- 每页执行 3.1 五项统一检查 + 页面特有检查（3.2）。
- F12 Console：记录所有 Error；对照 §1.3 已知基线，其余按 P0/P1/P2 分级进缺陷表（§5.1）。
- 结果标注：`✓` / `✗` / `N/A` + 备注。

### 3.1 统一检查项（每页必查）

| # | 检查项 | 预期 |
|---|--------|------|
| C1 | 页面可访问 | 非 404 / 500 / 白屏；HTTP 200 |
| C2 | 控制台无 Error | 无未捕获 Error（§1.3 基线项除外） |
| C3 | 导航显隐 | 侧栏该项显示；superadmin 应见全量 |
| C4 | 核心数据/列表加载 | 主列表/卡片正常渲染，无加载失败提示 |
| C5 | 渲染无警告 | 无 "Each child needs a unique key" 等 React 警告 |

### 3.2 页面清单（38 页）

#### A. 工作区（7）
| 页面 | 特有检查项 | 预期 |
|---|---|---|
| `/workspace` | 会话列表加载；新建会话 | 列表正常；新建成功跳转 |
| `/workspace/chats` | 会话列表 + 搜索 | 列表正常 |
| `/workspace/chats/[thread_id]` | 发消息流式回复；历史加载 | 首条回复正常；无白屏 |
| `/workspace/agents` | 自定义 agent 列表 | 列表正常 |
| `/workspace/agents/new` | 创建 agent 表单 | 可提交 |
| `/workspace/agents/[agent_name]/chats/[thread_id]` | agent 会话 | 正常 |
| `/workspace/scheduled-tasks` | 定时任务列表 | 正常或空态 |

#### B. 管理后台（5）
| 页面 | 特有检查项 | 预期 |
|---|---|---|
| `/admin` | 总览/入口 | 正常 |
| `/admin/users` | 用户列表；新建/编辑/删除按钮显隐 | 列表正常；按钮显示（superadmin） |
| `/admin/roles` | 角色列表（含用户数）；3-Tab（权限/nav/策略/数据权限）；编辑写透 | U1 用户数显示真实数字；编辑角色 → toast 成功 → overlay 更新 |
| `/admin/departments` | 部门树 CRUD | 正常 |
| `/admin/app-center` | 应用管理 | 正常 |

#### C. 业务模块（22）
| 页面 | 特有检查项 | 预期 |
|---|---|---|
| `/dashboard` | 工作台聚合卡片加载 | 项目/审批/提醒正常 |
| `/projects` | 项目列表 | 正常 |
| `/projects/new` | 创建表单 | 可提交 |
| `/projects/[id]` | 项目详情各 tab（大纲/章节/成员/审批/工作流） | 各 tab 可切换、加载正常 |
| `/projects/[id]/scifi` | sci-fi 视图 | 正常 |
| `/knowledge` | 知识库列表；上传/删除按钮（kb:* gate） | 列表正常；按钮按权限显隐 |
| `/knowledge-factory` | 9 tab（样例/抽取/模板/法规/合规/版本/质量/爬取/字典）逐个切换 | 每 tab 加载正常 |
| `/contract-price` | 总览仪表盘 | 正常 |
| `/contract-price/contracts` | 合同解析列表 + 导入按钮 | 正常 |
| `/contract-price/items` | 分项校验 | 正常 |
| `/contract-price/clusters` | 分组审核 | 正常 |
| `/contract-price/tasks` | 任务中心 | 正常 |
| `/contract-price/settings` | 配置 | 正常 |
| `/docmgr` | 文档树/文件夹 | 正常 |
| `/writing` | AI 对话写作 | 正常 |
| `/output` | 报告输出 | 正常 |
| `/data-sources` | 数据源管理 | 正常 |
| `/plugins` | 插件列表 | 正常（后端可能部分 stub → 404 记录为已知？见 §1.3） |
| `/workflow-admin` | 模板列表；发布按钮 is_admin gate | 正常 |
| `/workflow-admin/new` | 新建流程模板 | 可提交 |
| `/workflow-admin/[templateId]` | 模板编辑器 | 编辑器加载 |
| `/app-center` | 应用中心 | 正常 |

#### D. 其他（4）
| 页面 | 特有检查项 | 预期 |
|---|---|---|
| `/agentspace` | AgentSpace 列表 | 正常 |
| `/agentspace/[id]` | 详情 | 正常 |
| `/cad-design` | CAD 设计 | 正常 |
| `/settings` | 各设置页签 | 正常 |

---

## 4. Phase 2 角色权限深度验证

### 4.0 前置

- superadmin 在 `/admin/users` 创建测试账号：dept_head / project_manager / writer / reviewer / user 各一。
- **写操作前快照**：`copy config/roles_custom.yaml config/roles_custom.yaml.bak`；测后 `git checkout -- config/roles_custom.yaml` 恢复（§4.6）。

### 4.1 角色 → 权限矩阵（来源：`config/permissions.yaml`）

| 权限 | superadmin | dept_head | project_manager¹ | writer | reviewer | user |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `dashboard:view` | `*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `kb:read` | `*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `kb:create/upload/update/delete` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `doc:read` | `*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `doc:upload` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `project:create/read` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `project:edit/member:*` | `*` | ✗ | ✓ | ✗ | ✗ | ✗ |
| `chapter:write_own` | `*` | ✗ | ✗ | ✓ | ✗ | ✗ |
| `chapter:write_any` | `*` | ✗ | ✓ | ✗ | ✗ | ✗ |
| `chapter:review` | `*` | ✓ | ✓ | ✓ | ✓ | ✗ |
| `ai:start_writing` | `*` | ✗ | ✓ | ✓ | ✗ | ✗ |
| `approval:submit` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `approval:review` | `*` | ✗ | ✓ | ✗ | ✓ | ✗ |
| `approval:approve` | `*` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `approval:view` | `*` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `model:read` | `*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `workflow:read` | `*` | ✓ | ✓ | ✓ | ✓ | ✗ |
| `cpa:read/import` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `kf:read / kf:law:read / kf:scrape:read` | `*` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `kf:law:edit / kf:template:*` | `*` | ✗ | ✗ | ✗ | ✗ | ✗ |
| `system:access` | `*` | ✓ | ✓ | ✓ | ✓ | ✓ |

¹ project_manager = `#inherit:dept_head` + 附加，故拥有 dept_head 全部权限；**但 nav 不含 knowledge-factory / contract-price**（观察点）。

**nav 对比**：

| 角色 | dashboard | writing | projects | docmgr | knowledge | knowledge-factory | contract-price | output | app-center |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| dept_head | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| project_manager | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ |
| writer | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ |
| reviewer | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ |
| user | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ |

### 4.2 后端强制点验证（逐端点 HTTP 状态）

> 端点来自实际 router 定义（已核对）。`*` = 依 Phase 0 §2.2/§2.4 最终授权决定；若补了 `approval:view` 给 reviewer、`approval:submit` 给 writer，按补后预期调整。

**dashboard**（`/api/extensions/dashboard`）——读 + 用户自操作端点保持 `dashboard:view`（my-calendar/notification 属用户自助，非特权写，无需拆）：

| 端点 | 权限点 | dept_head | reviewer | writer | user |
|---|---|:---:|:---:|:---:|:---:|
| `GET /my-tasks` `/my-projects` `/my-stats` `/my-calendar` `/notifications` | `dashboard:view` | 200 | 200 | 200 | 200 |
| `POST /my-calendar` `POST /notifications/read-all` `PATCH /notifications/{id}/read` `PUT /notification-preferences` `POST /check-reminders` | `dashboard:view`（用户自助） | 200 | 200 | 200 | 200 |

**approval**（`/api/extensions/approval`）——读/写拆权：

| 端点 | 权限点 | dept_head | reviewer | writer | user |
|---|---|:---:|:---:|:---:|:---:|
| `GET /workflows/default` `GET /records` | `approval:view`∪`approval:review` | 200 | 200 | 403* | 403 |
| `POST /submissions` | `approval:submit` | 200 | 403 | 403* | 403 |
| `POST /actions`（review 动作） | `approval:review` | 403* | 200 | 403 | 403 |
| `POST /actions`（approve 动作） | `approval:approve` | 200 | 403 | 403 | 403 |

**law**（`/api/kf/laws`）——读/写拆权：

| 端点 | 权限点 | dept_head | reviewer | writer | user |
|---|---|:---:|:---:|:---:|:---:|
| `GET ""` `GET /statistics` `GET /ragflow-status` `GET /{law_id}` `GET /{law_id}/templates` `GET /templates/{template_id}/laws` | `kf:law:read` | 200 | 403 | 403 | 403 |
| `POST ""` `POST /init-ragflow` `POST /sync-all` `POST /parse-file` `POST /import-with-file` `PUT /{law_id}` `DELETE /{law_id}` `POST /{law_id}/sync` `POST /{law_id}/templates` `DELETE /{law_id}/templates/{template_id}` | `kf:law:edit` | 403 | 403 | 403 | 403 |

**管理端点**（不变，仅 superadmin / 授权角色）：

| 端点 | 权限点 | dept_head | reviewer | writer | user |
|---|---|:---:|:---:|:---:|:---:|
| `GET /api/extensions/roles` `/api/policies` | `role:read` | 403 | 403 | 403 | 403 |
| `GET/POST/PUT/DELETE /api/extensions/users` | `user:*` | 403 | 403 | 403 | 403 |
| `GET /api/permissions/me` | 登录即可 | 200 | 200 | 200 | 200 |

### 4.3 前端按钮级 gate（`can()` / `canPage()`）

| 位置 | 按钮/入口 | 权限点 | 预期 |
|---|---|---|---|
| `/knowledge` | 上传文档 / 删除 | `kb:upload` / `kb:delete` | dept_head 可见；writer/user 隐藏 |
| `/admin/users` | 新建/编辑/删除 | `user:*` | 仅 superadmin 可见 |
| `/projects` | 新建项目 | `project:create` | dept_head/project_manager 可见；writer/user 隐藏 |
| `/projects/[id]` | 成员管理 / 编辑 | `member:*` / `project:edit` | 仅 project_manager |
| `/contract-price/contracts` | 导入 | `cpa:import` | dept_head/project_manager 可见；其余隐藏 |
| `/knowledge-factory` 9 tab | 子页签显隐 | `canPage("kf:page:law")` 等 | 按 roles.pages 过滤 |
| `/workflow-admin` | 发布按钮 | `is_admin` | 仅 superadmin |

### 4.4 ABAC 专项（策略）

1. **策略 CRUD**：`/admin/roles` 策略 tab 或直接 `GET/POST /api/policies`（需 `role:read/create`）——新建/编辑/禁用/删除策略正常。
2. **条件策略生效**：建一条 `conditions: {attr: "role_level", op: "gte", value: 50}` 授予某权限（如 `kf:scrape:execute`）→ 期望 dept_head(50) 得、writer(10) 不得；验证对应端点。
3. **data_scope 死字段确认**：建 `grants: {data_scope: [...], permissions: [...]}` 策略 → 确认引擎只消费 permissions（文档结论，**非缺陷**，记录即可）。
4. **全局性确认**：策略无 role_id，作用于所有角色（满足条件者）。

### 4.5 数据权限（N/A 与已接线项）

- **N/A（I4 未接线，本轮不测）**：contract_price `cpa_dept/cpa_all`、project `project_member/project_all` 数据范围 —— 查询未应用 FilterRule，行为等价全量。**留待接线后补测**。
- **已接线可测**：`/knowledge`（`with_data_scope("knowledge")` 已应用）。
  - 用例：dept_head 建一个私有知识库 → 用 user 登录 → `/knowledge` 应看不到该库（user 仅 `knowledge_public`）→ 验证行级过滤。

### 4.6 角色管理 UI 写操作（破坏性，测后恢复）

| 用例 | 操作 | 预期 | 恢复 |
|---|---|---|---|
| 创建自定义角色 | 新建 role「测试角色」赋 2-3 权限 | 写透 `roles_custom.yaml`；重新登录/刷新后权限生效 | 删除该角色 |
| 覆盖内置角色 | 给 dept_head 加一个权限保存 | overlay 覆盖生效；刷新后 nav/权限更新 | `git checkout -- config/roles_custom.yaml` |
| 删除内置角色 | 删除 dept_head | 写 `disabled_roles` tombstone；有用户引用 → 409 | 恢复快照 |
| 乐观锁 | 两窗口同时编辑同一角色 | 后写者 409「冲突，请刷新」 | — |

**写操作全程**：保持 `roles_custom.yaml.bak` 快照；测完 `git checkout -- config/roles_custom.yaml`（或恢复 bak），确认 `git status` 干净。

---

## 5. 缺陷清单与验收

### 5.1 缺陷表（测试员填写）

| 缺陷ID | 页面/端点 | 操作步骤 | 实际行为 | 预期 | 分级 | 已知? | 状态 |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

### 5.2 已知预期失败/观察项（预填，行为一致即 confirmed-known）

| # | 描述 | 状态 |
|---|---|---|
| K1 | 数据级 ABAC：contract_price/project data_scopes 未接线（§1.3）→ §4.5 N/A | 确认即通过 |
| K2 | `policy.grants.data_scope` 死字段 | 确认即通过 |
| K3 | project_manager 有 kf/cpa 权限但 nav 无知识工厂/合同价格入口 | 记录，待产品定夺 |
| K4 | 前端 127 type errors / 后端 420 失败为既有基线 | 忽略 |
| K5 | 数据源/插件后端部分 stub（如返回 404/空） | 记录为已知 |

### 5.3 验收结论

```
测试日期：____ / 测试员：____ / 环境：localhost:3000
Phase 1 结果：P0 PASS ___ / 失败 ___（列缺陷ID）
Phase 2 结果：P0/P1 缺陷 ___（列缺陷ID）；P2 缺陷 ___
已知项 confirmed-known：___ / ___
总体结论：□ 通过  □ 有条件通过（列遗留）  □ 不通过
签名：____
```

---

## 附录 A：参考

- 设计：`docs/superpowers/specs/2026-08-01-role-management-yaml-driven-design.md`
- 实施计划（含执行结果/延后）：`docs/superpowers/plans/2026-08-01-role-management-yaml-driven.md`
- 权限定义：`config/permissions.yaml`（roles / project_roles / modules）
- Overlay：`config/roles_custom.yaml`
- ABAC 引擎：`backend/app/extensions/auth/{engine,identity,datascope,policy_routers,middleware}.py`
