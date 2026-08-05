# 角色管理权限架构 · ABAC 定性 + 完备性评估报告

> 日期：2026-08-05 | 状态：完成（纯评估，不含实施）
> 依据：`2026-07-30-abac-rbac-redesign-design.md`（自标 ABAC-lite）、`2026-08-01-role-management-yaml-driven-design.md`、`2026-08-04-abac-deny-primitive-design.md`
> 评估对象：`backend/app/extensions/auth/`（engine/registry/identity/datascope/middleware/policy_loader/policy_routers）+ `config/permissions.yaml` + `roles_custom.yaml`
> 判定标准：**双标准** —— ① 对照设计自述目标（ABAC-lite）判实现完备性；② 对照完整 ABAC（NIST SP 800-162：subject/object/action/environment 四类属性 + 统一策略评估）给出演进差距

## 1. 结论摘要

- **ABAC 定性**：当前是**混合 RBAC + ABAC-lite** 架构，**不是完整 ABAC（NIST）**。
  - RBAC 核心：yaml 驱动角色 → 权限点，用户→角色分配，`require_permission` 查角色权限集。
  - ABAC-lite 层：`policies` 表的**属性条件策略**（条件只评估 subject 属性）+ `DataScopeEngine` 的**属性驱动行级数据域** + 可扩展 `AttributeSet` 身份属性集。
- **ABAC-lite 完备性**：**基本完备**，落地已验证（170 测试绿 + 浏览器 E2E）；剩余少量 UI 能力小缺口（P0）。
- **完整 ABAC 差距**：**缺 object/action/environment 三类属性**，且权限判定与数据域是**两套引擎**（无统一 subject×object×action×env 决策）。

## 2. ABAC 判定（四要素盘点）

| 层 | 机制 | 证据 | ABAC 定性 |
|---|---|---|---|
| 核心授权 | yaml 驱动角色 → 权限点；`require_permission` 从 PermissionRegistry 解析角色权限集（#inherit 展开 + 环检测），超管旁路 `is_system OR "*"` | `middleware.py:197-230`、`registry.py:261-281`、`config/permissions.yaml` | **RBAC**（经典角色授权） |
| 动态策略 | `policies` 表；`conditions`（属性条件树）→ grants `{permissions, deny_permissions, deny_data_scopes}`；条件只评估 **subject 属性** | `engine.py:142-180`（evaluate_policy_conditions）、`policy_loader.py`、`models.py` | **ABAC-lite**（subject 属性条件策略） |
| 数据访问 | `DataScopeEngine` + `FilterRule`（eq/in/and/or/overlap/not）行级过滤；rule_template 引用 **identity 属性 + 行字段** | `datascope.py:39-102`、`engine.py:25-130`、`config/permissions.yaml` data_scopes 节 | **ABAC-lite**（属性驱动数据域） |
| 身份属性 | `AttributeSet`：user_id/username/role_code/role_level/dept_id/dept_ids/member_projects/project_roles/tags/labels/extra | `identity.py:16-61` | **ABAC subject 属性集** |

**结论**：设计**自述 ABAC-lite**（`2026-07-30-abac-rbac-redesign-design.md` 标题即「ABAC-lite 权限系统重构设计」），实现具备 ABAC-lite 的三大特征；但策略条件仅面向 subject 属性，**缺 object/action/environment**，权限点与数据域两套引擎 —— 不构成完整 ABAC。

## 3. ABAC-lite 完备性（对照设计自述目标）

设计自述目标（2026-07-30 §2）：「身份 = 可解析属性集（角色/部门/项目角色/标签/自定义 KV）；策略 = 属性条件 → 授权；数据 = 按身份属性过滤行」。

| 目标 | 状态 | 证据 |
|---|---|---|
| 身份 = 可解析属性集 | ✅ | `AttributeSet` 10 属性 + `extra` 扩展点；`IdentityProvider.resolve` 从 DB 解析 |
| 属性条件 → 授权（grant/deny） | ✅ | `evaluate_policy_conditions` 10 算子（eq/neq/gt/gte/lt/lte/contains/not_contains/in/not_in）+ and/or + 空=全员；deny 精确/模块通配 + deny-overrides + 超管豁免 |
| 数据按身份属性过滤行 | ✅ | `FilterRule` 6 算子；list/by-id 统一 scope（404 不泄露）；超管 allow_all |
| 落地与测试 | ✅ | 深度审计 170 测试绿 + 浏览器 E2E（角色/策略/数据域/IDOR/deny 全链验证） |

**ABAC-lite 范围内剩余小缺口（P0，低风险）**：
- ⚠️ UI 条件属性白名单 `ATTR_OPTIONS` 已补 `role_code`/`username`（commit `897a3ec8f`），但仍缺 `dept_ids`/`member_projects`/`labels.*`（引擎支持、API 可用，UI 不能选）。
- ⚠️ `or` 树条件 UI 不可表达（`toUIConditions` 退空条件并 warn）。
- ⚠️ 策略粒度固定为「全局或 subject 条件」（无按资源/对象挂载）—— 设计如此，非缺陷。
- ⚠️ `data_scopes`（可见性）与项目角色权限（`unified_permissions`）分属两套机制 —— spec 已划界（08-04 §4.1），边界明确非缺陷。

## 4. 完整 ABAC（NIST SP 800-162）差距

NIST ABAC：授权决策基于 **subject × object × action × environment** 四类属性的**组合策略**，单一决策点。

| NIST 要素 | 现状 | 差距 |
|---|---|---|
| **Subject 属性** | ✅ 全（10 属性 + extra 扩展） | — |
| **Object（资源）属性** | ⚠️ 仅作 scope 模板**固定列**（knowledge: owner_id/access_type/allowed_depts；project: id/created_by；docmgr: user_id/project_id） | ❌ 不能入策略条件：`check(identity, permission)` 无资源上下文，无法表达「仅当对象敏感级别/归属条件 X 才 deny/grant」 |
| **Action（动作）属性** | ⚠️ `permission` 是字符串点（如 `kb:delete`），非属性化 | ❌ 无动作元数据（无法「仅工作时间可写」等 action 条件） |
| **Environment（环境）属性** | ❌ 无（时间/IP/设备/地点等） | ❌ 完全缺失 |
| **统一评估** | 权限引擎（`UnifiedPermissionEngine`）+ 数据域引擎（`DataScopeEngine`）**两套**，策略只能影响权限点与 `deny_data_scopes` 钩子 | ❌ 无单次 subject×object×action×env 统一决策 |

**结论**：完整 ABAC 差距 = **object/action/environment 三类属性缺失 + 无统一策略评估**。现有 ABAC-lite 是「subject 属性 → 权限点/数据域」的偏侧实现。

## 5. 差距清单与优先级

| 优先级 | 差距 | 说明 | 性质 |
|---|---|---|---|
| **P0** | UI 补 `dept_ids`/`member_projects`；`or` 树只读展示防丢条件 | ABAC-lite 范围内 UI 能力补全 | 可实施（低风险） |
| **P1** | **object 属性入策略条件** | 需把资源上下文传入策略评估（scope 行属性 / 请求资源元数据），使 `check` 能基于对象属性出决策 | 架构演进 |
| **P2** | **action/environment 属性** | permission 属性化（模块:操作 → 动作元数据）+ 环境属性（时间/IP/设备） | 架构演进 |
| **P3** | **统一评估** | 单一决策点合并权限点 + 数据域，subject×object×action×env 一次出决策 | 架构演进 |

## 6. 边界

- **本报告为纯评估**，不含实施。P0-P3 仅作差距记录与演进方向，是否实施另行决策。
- 评估基于 2026-08-05 HEAD + 工作树（含本轮 role_code/username 修复）。`roles_custom.yaml`/ATTR_OPTIONS 等已落地改动按现状计。
- 完整 ABAC（NIST）是「能力对齐」参照，不是必须达标 —— 是否演进到 P1-P3 取决于业务对 object/action/environment 属性授权的真实需求（YAGNI）。
