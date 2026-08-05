# 角色管理 · 操作权限与数据访问权限深度审计 + 测试设计

> 日期：2026-08-05 | 状态：草稿 v1
> 父设计：
> - `2026-08-01-role-management-yaml-driven-design.md`（yaml 驱动真相源）
> - `2026-08-04-abac-deny-primitive-design.md`（数据访问控制统一 + ABAC deny 原语）
> 实施计划：`docs/superpowers/plans/2026-08-05-role-permission-deep-audit-test.md`（writing-plans 产出）

## 1. 背景与决策

用户要求梳理分析角色管理模块的操作权限 + 数据访问权限控制的设计完备性、实现落地性，尤其"个性化策略"的设计与实现，并做深度测试。

已与用户确认的决策：

| 决策点 | 选择 |
|---|---|
| 交付物形态 | **完整闭环**：审计 → 修关键缺口 → 深度测试 → 报告 |
| 个性化策略所指 | **ABAC 动态策略**（`policies` 表，条件→grant/deny）为主战场 |
| 测试覆盖层 | **A 后端集成（HTTP TestClient）+ B 浏览器 E2E + 安全对抗** 三层全上 |
| 实施方案 | **测试先行红→绿**：先写测试打当前状态（失败=审计证据），红项修复到全绿 |
| 分支 | 提交到 `main-dev-fork`（本仓库铁律，不提交 `main`） |

## 2. 审计结论（2026-08-05 HEAD 实机验证）

### 2.1 设计完备性 — ✅ 完备

- **操作权限**：yaml 驱动 RBAC（`permissions.yaml` + `roles_custom.yaml` overlay）+ `#inherit` 继承（环检测）+ 超管旁路 + deny 原语。设计自洽。
- **数据访问权限**：`DataScopeEngine` + `FilterRule`（`eq/in/and/or/overlap/not`）+ `with_data_scope` 统一 list/by-id + IDOR 闭合。两层正交模型（可见性 vs 权限）清晰。
- **个性化策略**：`policies` 表（`conditions` → `grants.{permissions, deny_permissions, deny_data_scopes}`），全局、动态、条件可空（=全员）。

### 2.2 实现落地性 — ✅ 绝大部分已落地，🔴 1 个 CRITICAL 数据 bug

**已落地（实机验证）：**
1. `require_permission` 从 PermissionRegistry 解析（`#inherit` 展开 + 环检测），不读 DB `roles.permissions`；S3 drift 守卫已删。
2. 超管旁路 `is_system OR "*"` 六处字节一致（`require_permission` / `require_super_admin` / `/me is_admin` / `admin.is_superadmin` / `with_data_scope` / `require_resource_permission`）。
3. deny 管线：`engine.check`（精确 + 模块通配 `prefix:*`）、`engine.list_permissions`（展开-减）、`/me` 走共享 `load_active_policies(db)`。
4. `evaluate_policy_conditions` 模块级共享（check/list_permissions/with_data_scope）；FilterRule `overlap`（PG `&&`，str→UUID 守卫）/`not` + 边界处理。
5. `with_data_scope`：超管 allow_all 内建旁路 + 策略 `deny_data_scopes` 收集 + `AND NOT deny` 组合。
6. knowledge 全量：list + by-id 统一走 scope（404 不泄露存在性）、`_can_access_kb` 删除、dept 共享靠 `allowed_depts OVERLAP` 生效、M1/M2/M3/M4/M5 全落。
7. project：L1（list 走 scope）已闭合（超出计划 known-limitations 声明的 defer）、L3（`system:access` 走引擎）已闭合、M6（get_project 404）已闭合、10 个 IDOR 端点全 gate。
8. docmgr：list + 主路由 by-id 走 scope（Task 13 完成）。
9. 写透：原子写 + `copy2` fallback（bind-mount 兼容）+ mtime 乐观锁 409 + registry reload + DB 镜像校准；`disabled_roles` tombstone + 删除守卫。
10. 前端：策略编辑器 deny 区（`deny_permissions`/`deny_data_scopes` 双向转换）、按钮级 `can()`（users/knowledge）、admin `is_admin` 权威、nav/pages 可见性消费与写回、角色级 DataScopePanel 存活。

**未落地 / 缺口（详见 §3）：**
- 🔴 **CRITICAL（实机确认）**：`config/roles_custom.yaml` 工作树把 `dept_head.permissions` 改为 `[]` 且无 `#inherit`。overlay 合并是**整体替换**（`registry.py:291-302`，as-designed），→ `dept_head` 解析为 **0 权限**，无 `system:access`。4 个在册 dept_head 用户（zhangsan/yang/huangwt/yangxf）**全部被 403 锁死**。`project_manager` 的 `#inherit:dept_head` 也因此继承到空集。
- 🟠 F2：docmgr `collab_routers` by-id（批注/版本/评审接口）仍走 legacy `get_by_id` → deny_data_scopes 不生效、超管非 owner 得 404（与主路由行为分歧）。
- 🟠 F3：docmgr `list_folders` 手写 `or_(own_docs, project_docs)`，未接 scope 引擎。
- 🟠 F4：`workflow-admin` 用硬编码 `user.role_name === "Super Admin"` 门（绕过权限系统）。
- 🟡 F5：roles 页 / admin 子导航未消费 `role:*`/`dept:*`/`user:*` 权限点（运行时被 AdminGate(is_admin) 兜住）——**记录不修**。

### 2.3 测试现状 — 引擎层强、HTTP 集成层系统性缺失

- **已覆盖**（17 个测试文件，单元/引擎/SQL 组合层）：overlay 合并、写透原子性 + mtime、校准、`check`/`list_permissions` deny、`DataScopeEngine` deny 组合、knowledge M5 可见性矩阵、docmgr scope、策略 grant 校验、`require_project_member` 依赖、overlap/not 基础算子。
- **系统性缺口**（深度测试主战场）：`/api/permissions/me` 端点 **0 覆盖**；deny→端点 403 无 HTTP 测试；数据 deny 到 knowledge 列表 e2e 无测试；`with_data_scope` 中间件无直测；6 个 IDOR 端点未 HTTP 驱动；knowledge by-id 404 / dept-list 翻转无端点断言；`#inherit` 环检测零覆盖；`not`-over-`allow_all`/`none_allow` 未测；overlap 空列未测；`knowledge_law_all` 未断言。
- **前端**：仅 `policyConverters`（不含 deny 转换器）与 `dataScope` 两个测试；`usePermission`/`PermissionProvider`/`pageVisibility` 无测试。
- 无死测试/骨架测试（唯一两处 `pass` 是合法 fake class body）。

## 3. 差距清单（处置表）

| # | 差距 | 严重度 | 处置 |
|---|---|---|---|
| F1 | `dept_head` overlay `permissions: []` → 0 权限，4 用户锁死 | 🔴 CRITICAL | **本轮修复** |
| F2 | docmgr `collab_routers` by-id 不走 scope（deny 不生效/超管分歧） | 🟠 中高 | **本轮修复** |
| F3 | docmgr `list_folders` 手写可见性 | 🟠 中 | **本轮修复** |
| F4 | `workflow-admin` 硬编码 `role_name === "Super Admin"` | 🟠 中 | **本轮修复** |
| F5 | roles 页/admin 子导航细粒度权限点未消费 | 🟡 低 | **记录不修**（运行时被 is_admin 兜住） |
| — | `require_role` 显示名判定（08-01 §4.8 计划逐步替换） | RISK | 记录 |
| — | `bare-*` deny 在 `check` 与 `list_permissions` 不对称（写入口已拒） | RISK | 记录 |
| — | `knowledge_dept` 模板是 spec §4.3 的超集（当前绑定等价） | RISK | 记录 |
| — | `PolicyGrant.data_scope` 残留字段（引擎不消费） | RISK | 记录 |
| — | 页面可见性无前端深链守卫（canPage 只作用于导航项） | RISK | 记录 |
| — | `DEFAULT_ROLE_PERMISSIONS` 死常量未删/未标废弃 | DEFERRED | 记录 |

## 4. 修复设计

### F1 — `dept_head` 权限被清空（CRITICAL，实机已确认）

**根因**：工作树 `config/roles_custom.yaml` 未提交改动把 `dept_head.permissions` 清为 `[]`；`PermissionRegistry._apply_overlay`（`registry.py:291-302`）整体替换 base 定义 → `resolve_role_permissions('dept_head')` = 空集。base `permissions.yaml` 的 dept_head 17 条权限不存活。

**修复**（只改 `roles_custom.yaml` 的 `dept_head.permissions` 键，保留工作树的 nav/pages/data_scopes 微调）：

```yaml
dept_head:
  permissions:
    - "#inherit:user"   # → dashboard:view, kb:read, doc:read, model:read, system:access
    - department:create
    - department:update
    - department:delete
    - kb:create
    - kb:upload
    - kb:update
    - kb:delete
    - doc:upload
    - doc:delete
    - project:create
    - project:read
    - approval:approve
    - approval:submit
    - approval:view
    - chapter:review
    - workflow:read
```

= `user`(5) + 16 扩展 = **21 权限**，等于 base `dept_head`(17) + `department:*`(3) + `doc:delete`。**不含**提交版 53 条里的 `user:*`/`role:*`/`license:manage`/`workflow:edit/start/cancel`（接近超管，疑似过度授权）。`project_manager` 的 `#inherit:dept_head` 继承链随之恢复。

**回归测试（红→绿）**：
- `resolve_role_permissions('dept_head')` ⊇ `{system:access, department:create, kb:delete, approval:approve}`；`project_manager` 因 `#inherit:dept_head` 也含 `system:access`。
- dept_head 用户 `GET /api/extensions/knowledge/knowledge-bases` → 200（修前 403）。

### F2 — docmgr `collab_routers` by-id 接 scope 引擎

**文件**：`backend/app/extensions/docmgr/collab_routers.py`、`service.py`。

**做法**：批注/版本/评审相关 by-id 端点注入 `scope: FilterRule = Depends(with_data_scope("docmgr"))`，把 `get_by_id(db, doc_id, user_id)`（legacy，service.py:128-141）换成主路由同款 `get_by_id_scoped(scope, doc_id)`（service.py:143-173，404 合并无权/不存在）。超管经 `with_data_scope` 内建 allow_all 自然放行（对齐主路由行为）。

**回归测试**：`deny_data_scopes` 策略能窄化 collab by-id；超管非 owner 可取（修前 404）；IDOR 保持闭合（非成员/非 owner 非 project 成员 → 404）。

### F3 — docmgr `list_folders` 接 scope 引擎

**文件**：`backend/app/extensions/docmgr/service.py`（`list_folders`，246-263）、`routers.py`（/folders 端点，435-443）。

**做法**：`/folders` 端点注入 `with_data_scope("docmgr")`，把手写 `or_(own_docs, project_docs)` 换成 `scope.to_sqlalchemy(Folder, {"owner_id": Folder.owner_id, "project_id": Folder.project_id})` 叠加基础条件；`scope=None` 回退保留原手写分支（内部调用/测试兼容）。

**回归测试**：`list_folders` 行为与手写等价（我+项目成员的文件夹）；`deny_data_scopes` 生效；超管全见。

### F4 — `workflow-admin` 硬编码角色名门

**文件**：`frontend/src/app/workflow-admin/layout.tsx`（10-22）、`page.tsx`（41/184/190/208/214）、`components/TemplateEditorPage.tsx`（32/151/255-256）。

**做法**：全部 `role_name === "Super Admin"` / `isSuperAdmin` 判定改为 `usePermission().is_admin`（来自 `/api/permissions/me`，后端 `is_system OR "*"` 权威）。非超管仍重定向 `/dashboard`。

**回归测试**：改名但 `is_system` 的超管可访问（修前被锁）；非超管重定向。类型检查 `pnpm typecheck`。

## 5. 深度测试矩阵

### L1 — 后端集成（HTTP TestClient，ABAC 策略为核心，新增测试文件）

运行机制：`docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -m pytest tests/<file>.py -v'`（backend 整目录 bind-mount，`.venv` 为 named volume）。用 FastAPI `dependency_overrides` 覆盖 `get_current_user`/`get_db`，复用仓库既有 async db fixture 模式（参考 `test_role_calibration.py` 的 `conn` fixture）；策略行用测试库 seed。

| 测试文件 | 覆盖 | 断言要点 |
|---|---|---|
| `test_permissions_me_endpoint.py` | `/me` 端点（现 0 覆盖） | 超管全集+`is_admin`；策略 grant 出现在 permissions；策略 deny 后不出现；`/me` 与 `require_permission` 对同一策略一致 |
| `test_policy_deny_endpoint.py` | deny→端点 | 策略 `deny_permissions=[kb:read]` → 需该权限端点 Y=403/Z=200；模块通配 `kb:*`；空条件=全员；超管豁免 |
| `test_data_deny_e2e.py` | 数据 deny e2e | `deny_data_scopes=[knowledge_public]` → public KB 从真实列表查询排除；超管全见 |
| `test_with_data_scope_middleware.py` | 中间件依赖 | 策略加载、deny_ids 累积、超管 allow_all 旁路、`AND NOT deny` 组成 |
| `test_project_idor_http.py` | IDOR 端点 HTTP | 非成员调 doc-status/finalize/merge/activities/stats/board → 403；成员 200；超管 200；get_project 非成员 404（M6） |
| `test_knowledge_flip.py` | knowledge 翻转 | dept 角色看到 dept 共享库（修前不可见→修后可见）；by-id 无权 404 非 403；超管全见 |
| `test_docmgr_scopes.py` | F2/F3 | collab by-id deny 窄化 + 超管非 owner 可取；list_folders deny 生效 + 行为等价 |
| `test_rbac_edge.py` | 引擎边界 | `#inherit` 环检测；`not`-over-`allow_all`/`none_allow`；overlap 空 allowed_depts 列；`knowledge_law_all` 存在；`bare-*` deny 写入口 400 |

### L2 — 浏览器 E2E（真实 Docker 环境，多角色登录）

| 场景 | 步骤 | 预期 |
|---|---|---|
| 策略编辑器 deny 区 | admin 登录 → 角色管理 → 策略 → 新建含 deny_permissions + deny_data_scopes → 保存 → 重载 | 保存成功、字段往返、策略行显示"拒绝权限/拒绝范围" |
| dept_head 修复后全流程 | dept_head 用户登录 → 知识库/项目/文档空间 | 无 403；能建库/看项目 |
| workflow-admin 门（F4） | 非超管访问 `/workflow-admin` | 重定向 `/dashboard`；超管可进 |
| 按钮级 can() | user 角色进 knowledge 页 | 新建/上传/删除按钮按权限显隐 |
| 页面可见性 | 不同角色看 knowledge-factory（9 tab）/ contract-price（6 路由） | 未授权 tab 不渲染 |
| roles 页 | admin 编辑角色权限/nav/pages → 保存 | overlay 写透生效、DB 镜像校准 |

### L3 — 安全对抗（越权/存在性/豁免/绕过）

| 探测 | 预期 |
|---|---|
| IDOR：非成员直接改他人项目文档 status/finalize/merge | 403 |
| 存在性泄露：by-id 无权 vs 不存在 | 统一 404（不泄露） |
| 超管双豁免：deny_permissions + deny_data_scopes 对超管无效 | 全见全放行 |
| deny 绕过：精确点 vs 通配 vs 嵌套条件 vs 空条件 | 全部按 deny-overrides 拒绝 |
| 边界：畸形 dept_ids（str→UUID 失败）、空 allowed_depts | 失败闭合（none_allow），不 500 |
| `bare-*` deny 写入 | 400 拒绝 |
| deep-link 直达隐藏子页 | 记录（前端无守卫，已知项） |

### L4 — 修复回归

F1-F4 每项一个回归测试文件/用例，随修复红→绿（见 §4 各节）。

## 6. 执行顺序（red→green）

- **Cycle 0 — F1 dept_head 抢救**：写 F1 回归测试（红）→ 修 `roles_custom.yaml`（绿）→ 容器内跑测试 + `resolve_role_permissions` 验证 → 确认 4 用户解锁。
- **Cycle 1 — L1 集成套件红→绿**：写全部 L1 测试文件打当前状态 → 记录红项（含尚未修好的 F2/F3 暴露的 bug）→ 修 F2/F3/F4 → 全绿。每项修复带回归。
- **Cycle 2 — L2 浏览器 E2E**：真实 Docker 多角色登录实测。
- **Cycle 3 — L3 安全对抗**：越权/存在性/豁免/绕过探测。
- **Cycle 4 — 审计报告**：设计完备性 + 落地性 + 测试结论（红→绿逐项）+ 已知项，汇总为报告（本 spec 的 §7 + 实施结果）。

## 7. 报告产出

审计报告作为实施计划的收尾产物，包含：
1. 设计完备性结论（§2.1）。
2. 实现落地性结论 + 修复记录（§2.2 + Cycle 0/1 的 commit 清单）。
3. 深度测试结论：L1/L2/L3 每项通过/失败明细（红→绿转表）。
4. 已知项（§3 记录不修 + RISK 清单）+ 后续建议（如 `require_role` 替换、roles 页细粒度、deep-link 守卫）。

## 8. 风险与边界

- **行为翻转**：修好 `knowledge_dept` 后 dept 角色会**新看到**此前看不到的 dept 共享库（正确收敛，需在报告中预告）；F1 修复后 dept_head 权限集合与提交版 53 条不同（21 条，收敛过度授权）——发布前核对。
- **测试隔离**：L1 用依赖覆盖 + 测试 DB，**不**在真实业务库跑破坏性测试；L3 破坏性探测全部走测试 DB；L2 在真实环境做只读/可回滚操作。
- **EAI-CUSTOM 规则**：改 `app/` EAI 定制代码无需三重规范（非 harness 上游）；若触碰 harness 文件必须三重标注 + 征询用户。改上游维护文件（如 roles_custom.yaml 无此问题）需 `// EAI-CUSTOM` 注释。
- **不引入新依赖**：FilterRule/引擎已具备全部算子；测试用 stdlib pytest + 现有 fixture。
- **全量回归基线**：本 fork 后端全量 pytest 有 420 失败/79 collection 错误为**既有基线**（判别"新失败"只看法人域测试文件）；前端 typecheck 127 错误为既有基线。不修基线。

## 9. 文件清单

**修复：**
- `config/roles_custom.yaml` — F1 dept_head permissions（`#inherit:user` + 16 扩展）。
- `backend/app/extensions/docmgr/collab_routers.py` + `service.py` — F2 换 `get_by_id_scoped` + 注入 `with_data_scope("docmgr")`。
- `backend/app/extensions/docmgr/service.py` + `routers.py` — F3 `list_folders` 接 scope。
- `frontend/src/app/workflow-admin/layout.tsx` + `page.tsx` + `components/TemplateEditorPage.tsx` — F4 `is_admin` 门。

**测试（新增，backend/tests/）：**
- `test_permissions_me_endpoint.py`、`test_policy_deny_endpoint.py`、`test_data_deny_e2e.py`、`test_with_data_scope_middleware.py`、`test_project_idor_http.py`、`test_knowledge_flip.py`、`test_docmgr_scopes.py`、`test_rbac_edge.py`。

**文档：**
- 本 spec + `docs/superpowers/plans/2026-08-05-role-permission-deep-audit-test.md`（实施计划）。
