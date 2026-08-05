# 角色管理 · 操作权限 + 数据访问权限 深度审计报告

> 日期：2026-08-05 | 状态：完成
> 依据设计：`2026-08-01-role-management-yaml-driven-design.md`、`2026-08-04-abac-deny-primitive-design.md`
> 计划：`2026-08-05-role-permission-deep-audit-test.md`；报告：本文件

## 1. 结论摘要

| 维度 | 结论 |
|---|---|
| 设计完备性 | ✅ **完备**：操作权限（yaml 驱动 RBAC + `#inherit` + deny 原语）与数据访问权限（`DataScopeEngine`+`FilterRule` scope 引擎统一 list/by-id）两层正交模型；个性化策略（ABAC `policies` 表）设计自洽 |
| 实现落地性 | ✅ **绝大部分落地**：deny 管线、`/me` 一致性、`overlap`/`not` 算子、`with_data_scope` 超管豁免 + AND NOT deny、knowledge/project/docmgr 三模块 scope 接线、IDOR 闭合、写透+乐观锁。**本轮修复 4 个缺口（F1-F4）** |
| 个性化策略实现 | ✅ **落地**：`policies` 表（`conditions` → `grants.{permissions, deny_permissions, deny_data_scopes}`）全链可用；`/me`/`require_permission`/`with_data_scope` 共享 `load_active_policies` 无漂移 |
| 深度测试 | ✅ **170 passed**（30 新 L1 + 140 法人域既有）+ 浏览器 E2E 实机验证 |

## 2. 设计完备性（对照 spec）

- **操作权限**：`permissions.yaml`（注册表/角色定义/project_roles）为权威，`roles_custom.yaml` overlay 覆盖，`#inherit` 继承（环检测），超管旁路 `is_system OR "*"`，deny-overrides（精确点 + 模块通配）。设计完备。
- **数据访问权限**：`DataScopeEngine`（allow OR-union + deny `AND NOT`）+ `FilterRule`（`eq/in/and/or/overlap/not`）统一 list/by-id；by-id 无权与不存在统一 404（不泄露存在性）；IDOR 端点成员资格 gate。设计完备。
- **个性化策略（ABAC）**：全局策略（非按角色挂载），`conditions` 空=全员，`priority` 排序，`deny_permissions`/`deny_data_scopes` 校验（未知 id 400）。设计完备。

## 3. 实现落地性 + 修复记录（红→绿）

### 3.1 已落地且验证（审计 + 测试确认）

1. `require_permission`/`require_super_admin`/`with_data_scope`/`/me`/`admin.is_superadmin`/`require_resource_permission` 全部从 PermissionRegistry 解析；超管旁路表达式六处**字节一致**。
2. deny 管线：`engine.check`（精确+通配 deny-overrides，超管豁免）、`engine.list_permissions`（展开具体点 − deny）、`/me` 走共享 `load_active_policies(db)`。
3. `FilterRule` `overlap`（PG `&&`，str→UUID 守卫）/`not` 算子 + 复合树可达；`with_data_scope` 超管 `allow_all` 内建 + deny 收集 + `AND NOT` 组合。
4. knowledge：list + 全 by-id 走 scope（404 统一），`_can_access_kb` 删除，dept 共享靠 `allowed_depts OVERLAP` 生效，M1/M2/M3/M4/M5 全落。
5. project：list 走 scope（L1）、`system:access` 走引擎（L3）、get_project 404（M6）、10 个 IDOR 端点 gate。
6. docmgr：list + 主路由 by-id 走 scope；写透（原子写 + copy2 fallback + mtime 乐观锁 409 + registry reload + DB 镜像校准）。
7. 前端：策略编辑器 deny 区（`deny_permissions`/`deny_data_scopes` 双向转换）、按钮级 `can()`（users/knowledge）、admin `is_admin` 权威、nav/pages 可见性消费与写回。

### 3.2 本轮修复（红→绿）

| # | 缺口 | 严重度 | 红项 | 修复 commit | 修复后验证 |
|---|---|---|---|---|---|
| **F1** | `roles_custom.yaml` 把 `dept_head.permissions` 清为 `[]`（overlay 整体替换）→ **0 权限，4 用户锁死** | 🔴 CRITICAL | `test_role_definition_f1.py`（resolve 0 权限） | `b5d79c42f`：`#inherit:user` + 16 部门扩展 = **21 权限**（含 `system:access`；`project_manager` 继承链恢复 = 30 权限） | resolve 21/True、30/True；UI 角色列表"部门负责人 4 用户 21 权限"；E2E：新 dept_head 用户登录 `/me` = 21 权限 + system:access + 完整 nav，knowledge 无 403 |
| **F2** | docmgr `collab_routers` by-id（批注/版本/评审）不走 scope（deny 不生效、超管非 owner 404） | 🟠 中高 | `test_docmgr_scopes.py::test_collab_by_id_scope_narrows`（SQL 无 deny） | `f1dad373f`：8 端点注入 `with_data_scope("docmgr")` + 换 `get_by_id_scoped` | SQL 含 `NOT IN`（deny 生效）；超管对齐主路由 |
| **F3** | docmgr `list_folders` 手写 `or_(own_docs, project_docs)` | 🟠 中 | `test_list_folders_scope_narrows`（SQL 无 deny） | `f1dad373f`：service 加 scope 分支 + `/folders` 注入 `with_data_scope` | SQL 含 `NOT IN`；`scope=None` 回退兼容 |
| **F4** | `workflow-admin` 硬编码 `role_name === "Super Admin"`（**中文名 admin 也被锁**） | 🟠 中 | —（前端无单测；实机验证旧 gate 锁 admin） | `6ec4e5bf3`：layout 改 AdminGate 模式 + page/TemplateEditorPage 改 `usePermission().is_admin` | tsc 全项目 0 错误；E2E：admin 可访问 /workflow-admin，dept_head 被重定向 /dashboard |

### 3.3 测试基线与回归

- **L1 新增 9 文件 / 30 用例全绿**：`/me` 端点（3）、deny→HTTP 403（6）、with_data_scope 直调（3）、数据 deny 到 SQL（2）、knowledge overlap/by-id（2）、IDOR HTTP（3）、rbac 边界（6）、docmgr scopes（2）、F1 回归（3）。
- **法人域既有 13 文件 / 140 用例全绿**（无回归）。
- 合计 **170 passed**；`ruff` 全过（测试 import 排序已修）。

## 4. 浏览器 E2E 实机验证（Docker :2026，多角色）

| 场景 | 结果 |
|---|---|
| admin 登录 → 角色列表 | ✅ "部门负责人 **4 用户 21 权限**"、"项目经理 30 权限"（F1 实时反映） |
| admin → 自定义策略 → 添加策略 | ✅ deny 区完整渲染：「拒绝权限」输入（支持 `kb:delete`/`kb:*`）+「拒绝数据范围」四模块勾选（报告项目/文档空间/知识库/合同价格分析）+「命中即拒绝」提示 |
| admin → /workflow-admin | ✅ 可访问（旧 gate 因 role_name="超级管理员"≠"Super Admin" 曾锁住 admin——F4 修复） |
| 新建 dept_head 测试用户 → 登录 | ✅ `/me`：`is_admin:false, role_code:dept_head, 21 权限, system:access:true, 完整 nav`；`/knowledge` 无 403；「新建知识库」按钮可见（can() 生效） |
| dept_head → /workflow-admin | ✅ 重定向 `/dashboard`（F4 非超管拦截） |
| 清理 | ✅ 测试用户已删除 |

## 5. 已知项与后续建议（记录不修）

| 项 | 影响 | 建议 |
|---|---|---|
| **F5**：roles 页 / admin 子导航未消费 `role:*`/`dept:*`/`user:*` 细粒度权限点 | 运行时被 AdminGate(is_admin) 兜住，低 | 后续补按钮级 `can()` + 子导航 `canNav` |
| `require_role` 仍按显示名判定（08-01 §4.8 计划替换） | 用了它的路由基于名字 | 逐步替换为 `require_permission`/is_admin |
| `bare-*` deny 在 `check` 与 `list_permissions` 不对称 | 写入口 `_validate_grants` 已拒绝 `*`；仅存量 DB 行可能触发 | 存量核对 |
| `knowledge_dept` 模板是 spec §4.3 超集（`owner_id` OR） | 当前绑定等价（dept_head 等角色同时绑 knowledge_owner） | 未来若单绑 knowledge_dept 需复核 |
| `PolicyGrant.data_scope` 残留字段 | 引擎不消费，UI 不再设置 | 可清理 |
| 页面可见性无前端深链守卫 | `canPage` 只作用于导航项，URL 直达可加载 | 后端已 403/404 兜底；前端路由守卫可选 |
| `knowledge_law_all` scope 未声明 | spec §6 矩阵残留名；`kb_type`(law) 分类型差异化已按 08-04 §2 deferred | 不为此造数据 |
| docmgr `collab_routers`/`list_folders` 修复后 `scope=None` 回退分支 | 仅测试/内部调用用 | 保留 |
| `DEFAULT_ROLE_PERMISSIONS` 死常量 | 未删/未标废弃 | 清理 |

## 6. 风险与边界

- **行为翻转预告**：F1 修复后 dept_head 权限集合 = 21（`#inherit:user` + 部门扩展），与提交版 53 条不同（收敛了 `user:*`/`role:*`/`license:manage`/`workflow:edit/start/cancel` 等近超管授权）。若业务上 dept_head 确需这些，需在 UI 里补勾选。
- **测试隔离**：L1 全部走 mock DB + 真实 registry（仓库无 live-PG 基建，共享 dev DB 不做破坏性写入）；浏览器 E2E 创建了临时 dept_head 用户并已删除。
- **EAI-CUSTOM**：docmgr 两处 + workflow-admin 三处改动均带 `EAI-CUSTOM (F4/F2/F3)` 注释；未触碰 harness。
- **全量回归基线**：本 fork 后端全量 pytest 仍有 ~420 失败/79 collection 错误（**既有基线**，非法人域）；前端 tsc 本次实测 **0 错误**（此前 127 基线已被并发工作清除）。法人域 170 用例全绿。
