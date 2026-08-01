# 角色管理真相源统一 + 功能修复设计（yaml 驱动）

> 日期：2026-08-01 | 状态：草稿
> 基线：本文是 `2026-07-30-abac-rbac-redesign-design.md` 的**修订版**——该文档 §4.3 的真相源决策（"角色-权限映射存储在 DB `roles.permissions`，yaml 仅作 seed"）被推翻，改为 **permissions.yaml 驱动一切**。

## 1. 背景与现状

当前代码是 07-30 设计（PermissionRegistry + UnifiedPermissionEngine + IdentityProvider + FilterRule + policies 表 + 3-Tab 角色 UI）的部分落地。梳理发现实现存在系统性缺陷，核心是**真相源分裂**：

| 数据 | 声明处 | 执行处 | 是否一致 |
|---|---|---|---|
| 权限注册表 | `permissions.yaml` | `registry.py` | ✅ |
| 系统角色→权限 | `permissions.yaml` roles 节 | `require_permission` 读 **DB `roles.permissions`** | ❌ 漂移 |
| 角色 nav/pages | `permissions.yaml` + DB `role.nav` | `/me` 只读 yaml | ❌ DB 侧失效 |
| 角色 data_scopes | yaml roles 节 | `DataScopeEngine` 读 yaml，但 UI 保存进 no-op | ❌ 未落地 |
| 项目角色→权限 | DB `role_permissions` 表 + `DEFAULT_ROLE_PERMISSIONS` 常量 | `unified_permissions.py` | 🟡 与旧 `project_permissions.py` 并存 |
| 自定义角色默认权限 | 服务层 `BASE_PERMISSIONS` | `RoleService.create/update` | ❌ 第三套 |

具体问题清单见 §3。

## 2. 设计决策：yaml 驱动一切

### 2.1 数据 vs 定义分层

**用户的运行时增删、用户↔角色分配是"实例数据"，留在 DB，天然支持运行时 CRUD。角色的定义（有哪些角色、每个角色有哪些权限/nav/data_scopes）是"定义"，由 yaml 独占。**

| 类别 | 归属 | 运行时机制 |
|---|---|---|
| 用户实例 | DB `users` | 现有 CRUD，即时生效 |
| 用户↔角色分配 | DB `users.role_id` | 改外键，下一请求生效 |
| 角色定义（权限集/nav/data_scopes/继承） | `permissions.yaml` + `config/roles_custom.yaml` | UI 写透 overlay → 热重载 → 下一请求生效 |
| ABAC 动态策略 | DB `policies` 表 | 保留 DB（是动态数据，非定义） |

### 2.2 权威读取路径

授权（`require_permission` / `/me` / `DataScopeEngine`）一律从 **PermissionRegistry（yaml + overlay 合并，mtime 热重载）** 解析，不再读 DB `roles.permissions`。

DB `roles` 表降级为**物化镜像**：为 `users.role_id` 外键提供 `code → id` 映射，启动时从 registry 校准（name/permissions/nav/data_scopes/is_system/level）。镜像列的写入只发生在：启动校准、UI 写透后校准。运行时代码不得直接改镜像列。

### 2.3 overlay 文件

`config/roles_custom.yaml` 存放内置角色的覆盖和所有自定义角色：

```yaml
# 覆盖内置角色（同 code 整体覆盖 permissions.yaml 中的定义）
roles:
  dept_head:
    display_name: "部门负责人"
    level: 50
    permissions: ["#inherit:user", "kb:create", ...]
    nav: [...]
    data_scopes: [...]
# 禁用内置角色（删除=写 tombstone，不移除权限.yaml）
disabled_roles: []
```

合并规则：`permissions.yaml` 内置 → 叠加 overlay → 同 code 覆盖为 overlay 定义。自定义角色只存在于 overlay。删除内置角色 = 写入 `disabled_roles`；删除自定义角色 = 从 overlay 移除。

### 2.4 并发写

写透采用原子写（临时文件 + `os.replace`）+ 写前比对 `mtime`（乐观锁），冲突时返回 409 提示刷新。多人同时编辑同一角色是低频场景，接受"最后写者胜"。

## 3. 问题清单（本次修复范围）

### S 级 — 功能失效/数据破坏

- **S1 nav 开关不生效**：`/me` 只从 yaml `get_nav_ids_for_role(role_code)` 读，从不读 DB `role.nav`；自定义角色（yaml 无此 code）→ `nav=[]` → 全部导航消失。
- **S2 数据权限 tab 是 no-op**：`RoleUpdate` schema 无 `data_scopes` 字段，前端 `as unknown as` 强转被 Pydantic 丢弃；`DataScopeEngine` 只读 yaml。且 yaml 中 `dept_head/project_manager` 引用未定义的 `cpa_dept` scope。
- **S3 `user` 角色权限被自动重置**：`middleware._ensure_role` 的 drift 守卫把任何超出硬编码 `_ROLE_DEFAULTS["user"]` 的权限整组打回，管理员授予的额外权限每次登录被清空。
- **S4 角色继承不生效**：`engine.check` 只看 DB `roles.permissions` 数组，`parent_role_id` 不参与计算。yaml 的 `#inherit:` 语法在 `resolve_role_permissions` 已实现但未被强制路径使用。

### A 级 — 真相源分裂

- **A1 三套默认权限**：yaml roles 节 / DB roles 行 / 服务层 `BASE_PERMISSIONS` 互相漂移；`seed_db` 只创建 superadmin+user，yaml 的 dept_head/project_manager/writer/reviewer 在 DB 不存在。
- **A2 新旧项目权限并存**：`unified_permissions.py`（role_permissions 表）声明取代旧体系，但 `project/routers.py:304` 仍用 `project_permissions.py`（5 个 legacy 角色矩阵）。

### U 级 — 产品/UX

- **U1** 角色列表用户数显示 `-`（`/assignments` 端点未接入）。
- **U2** 权限执行覆盖不均：dashboard(1)/law(1)/approval(1)/knowledge_factory(1) 等几乎无 `require_permission`；前端 `can()` 仅 15 处。
- **U3** 策略 UI 误导：`PolicyCreate` 无 `role_id` 但前端按角色挂载；条件属性含 `email_domain`（`AttributeSet` 无此字段，恒失败）；grant 的 `data_scope` 被引擎忽略。
- **U4** 数据权限面板切换角色不重置选择、不加载当前角色的已配置 scopes。

## 4. 详细设计

### 4.1 后端强制路径改造

`require_permission`（middleware.py）：
1. `identity.role_code` 仍来自 DB `user.role_id → Role.code`（分配数据）。
2. `role_permissions` 字典改为 `{code: registry.resolve_role_permissions(code)}`，由 `get_permission_registry()` 提供（含 overlay 合并 + `#inherit` 展开 + 环检测）。
3. 删除 `select(Role)` 构建权限表 + 删除 `_ensure_role` 的 drift 重置（§4.3）。
4. 保留每请求 ContextVar 缓存（cache.py）不变；yaml/overlay mtime 变化时 registry 重载，下一请求生效。

`/api/permissions/me`（permission_routers.py）：
- nav/pages/data_scopes 全部改读 registry（yaml+overlay）：`get_nav_ids_for_role` / `get_page_ids_for_role` / 新增 `get_data_scopes_for_role`。
- `["*"]` 展开逻辑保留。
- 自定义角色（overlay 定义）不再出现 `nav=[]` 全消失（S1 修复）。

### 4.2 项目级权限统一（A2）

- `unified_permissions.py` 改为从 registry 读 `project_roles:` section（把 `DEFAULT_ROLE_PERMISSIONS` 从代码常量移入 yaml）：

```yaml
project_roles:
  owner:      [project:edit, project:delete, member:add, ...]
  phase_lead: [chapter:write_any, chapter:review_any, ai:start_writing, ...]
  writer:     [chapter:write_own, chapter:confirm]
  reviewer:   [chapter:review, approval:review]
  approver:   [approval:approve, approval:view]
```

- `role_permissions` 表停用（不再 seed/读取；数据保留不删，避免破坏历史）。`DEFAULT_ROLE_PERMISSIONS` 常量删除。
- `project/routers.py:304` 的 `get_my_permissions` 与 `require_resource_permission` 改用 `unified_permissions`；删除 `project/permissions.py` + `project/project_permissions.py` 的依赖。
- `identity.project_roles`（ProjectMember.role）与 `ProjectRole` 枚举的映射保持不变。

### 4.3 启动校准（init_db）

在 `init_db`/`seed_db` 新增角色校准步骤：
1. 从 registry（yaml+overlay+`#inherit` 展开后）得到每个角色的最终定义。
2. 遍历角色 code：DB 无此 code → 创建行（含 FK 需要的 id）；已有 → 校准 name/permissions/nav/data_scopes/is_system/level。
3. `disabled_roles` 中的内置角色：DB 行保留但标记禁用（或删除，若无非默认用户引用则删除；有引用则保留并阻止 UI 分配）。
4. 删除 `_ROLE_DEFAULTS` 硬编码（middleware 与 seed_db 同步清理），user/superadmin 定义统一收敛到 yaml。
5. `seed_db` 中 `user` 角色的硬编码权限数组（`["kb:read","kb:create","kb:upload"]`）移除，改从 yaml 取。

### 4.4 S3 修复：删除 drift 守卫

`middleware._ensure_role` 的"非系统角色权限超默认即重置"逻辑删除。yaml 是权威，授权路径已改为读 registry，不再需要防 DB 漂移的自动重置；管理员在 UI 授予的权限经写透落 overlay，长期有效。

### 4.5 S4 修复：继承生效

继承在 registry 层统一展开（`resolve_role_permissions` 已支持 `#inherit:`，含环检测）。强制路径与 `/me` 都用展开结果。DB `parent_role_id` 列保留但不参与计算（或作为 UI 展示用的"基于…创建"标签）。

### 4.6 写透（角色管理 UI）

`RoleService.create/update/delete/copy` 改为写透 overlay：
- **update**：解析请求 → 合并到 overlay roles（内置角色覆盖、自定义角色新建）→ 原子写 + mtime 乐观锁 → 触 registry 重载 → 校准 DB 镜像行 → 返回合并后结果。
- **create/copy**：code 去重（含内置）→ 追加 overlay → 同上。
- **delete**：内置角色 → 写入 `disabled_roles`；自定义角色 → 从 overlay 移除；有已分配用户 → 409 阻止（沿用现有 `get_role_user_count` 守卫）。
- `RoleResponse` 的 nav/data_scopes/permissions 合并展示（DB 镜像 + registry）。

### 4.7 前端修复

- **U1** 角色列表接 `GET /api/extensions/roles/assignments` 显示用户数（替代硬编码 `-`）。
- **U3 策略 UI**：去掉条件属性里的 `email_domain`；去掉 grant 的 data_scope 下拉（引擎不消费，保留会误导）；策略列表明示"全局策略，作用于所有角色"；`handlePolicySave` 不再传 `role_id`。
- **U4 数据权限面板**：`handleSelectRole` 时从角色数据加载已配置 scopes 作为初始选择（来自 registry `get_data_scopes_for_role`）；切换角色重置选择。
- **U2 前端按钮级 can()**：优先覆盖 admin/users 页操作、knowledge 页、project 页操作按钮（按模块分批）。
- **A3 附修**：`admin/layout.tsx` 的 `isAdmin` 从 `role_name === "Super Admin"` 改为 `is_system`/`can("system:access")`（或 `/me` 返回 `is_admin` 标志），消除显示名硬编码。

### 4.8 后端权限点补强（U2 后端侧）

为缺失 `require_permission` 的路由补强制点：dashboard、law、approval、knowledge_factory、settings 等。新增权限点先声明到 `permissions.yaml` 再挂载。`require_role`（按显示名）逐步替换为 `require_permission`。

## 5. 兼容性与迁移

1. **数据不迁移**：users/roles/project_members 表结构不变；`roles.permissions/nav` 列保留作镜像。`role_permissions` 表停用不删。只新增 `config/roles_custom.yaml`（初始可为空）。
2. **DB 校准幂等**：启动重复执行安全（upsert by code）。
3. **行为变化**：a) 授权从"DB roles.permissions"切到"registry（yaml+overlay）"——现状 yaml 与 DB 已漂移，切换后以 yaml 为准；b) user 角色不再被自动重置；c) 项目权限以 yaml `project_roles` 为准。发布前需人工核对 yaml roles 节与当前 DB roles 的差异，确保切换后权限不意外扩大/缩小（上线前跑一遍 diff 脚本输出）。
4. **回滚**：镜像列 + registry 双读切换点集中，可回退到 DB 读路径。

## 6. 测试

- 单元：registry 合并（overlay 覆盖/继承展开/环检测）、写透原子性、`require_permission` 从 registry 解析、`DataScopeEngine` 从 registry 解析、项目权限 yaml 读取。
- 迁移：`init_db` 校准幂等（重复跑不产生脏数据）。
- 回归：S1（自定义角色 nav 不消失）、S3（user 角色授予额外权限后不被重置）、S4（`#inherit` 角色权限生效）、现有 `tests/test_*` 全绿。
- 前端：U1 用户数显示、U3 策略 UI 修正、U4 面板状态。

## 7. 文件清单

| 文件 | 改动 |
|---|---|
| `config/permissions.yaml` | roles 节对齐 DB 现状、补 `cpa_dept` scope、新增 `project_roles:` section、补缺权限点 |
| `config/roles_custom.yaml` | 新增（overlay，初始空/示例） |
| `backend/app/extensions/auth/registry.py` | 加载 overlay、合并、`get_data_scopes_for_role`、暴露 `list_role_codes` |
| `backend/app/extensions/auth/middleware.py` | `require_permission` 读 registry；删 `_ROLE_DEFAULTS` drift 守卫 |
| `backend/app/extensions/auth/permission_routers.py` | `/me` 读 registry（nav/pages/data_scopes） |
| `backend/app/extensions/auth/identity.py` | （如需）`email_domain` 属性或从 UI 条件选项移除 |
| `backend/app/extensions/auth/datascope.py` | `from_registry` 读 overlay 合并结果 |
| `backend/app/extensions/role/service.py` | 写透 overlay + 校准 DB + 原子写/乐观锁 |
| `backend/app/extensions/role/routers.py` | 角色响应合并、删除走 disabled_roles |
| `backend/app/extensions/database.py` | `init_db` 角色校准、删硬编码 seed |
| `backend/app/extensions/auth/unified_permissions.py` | 读 yaml `project_roles` |
| `backend/app/extensions/project/routers.py` | 切到 unified_permissions；删旧 `project_permissions.py` 依赖 |
| `backend/app/extensions/models/role_permission.py` | 删 `DEFAULT_ROLE_PERMISSIONS` 常量（或标记废弃） |
| `frontend/src/app/admin/roles/page.tsx` | U1/U3/U4 修复 |
| `frontend/src/app/admin/layout.tsx` | A3 is_admin 判定 |
| 前端各页 | U2 按钮级 can()（分批） |

## 8. 风险与未决

- **行为翻转风险**：授权从 DB 切到 yaml，现有 yaml 与 DB 漂移意味着上线即改变部分角色实际权限。缓解：上线前 diff 脚本 + 人工核对（§5.3）。
- **overlay 并发写**：接受"最后写者胜"，乐观锁防覆盖提示。
- **未决**：`role_permissions` 表是保留停用还是彻底删除；`disabled_roles` 语义是否需要 UI 展示。默认：保留停用、UI 暂不展示禁用态。
