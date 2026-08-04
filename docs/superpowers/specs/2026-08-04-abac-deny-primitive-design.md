# 数据访问控制统一 + ABAC deny 原语设计（scope 引擎主轴）

> 日期：2026-08-04 | 状态：草稿 v3（数据访问控制升为主轴）
> 父设计：`2026-08-01-role-management-yaml-driven-design.md`
> 演进：本稿由 "abac-deny-primitive" 初稿扩展——调研发现 **scope 引擎连 allow 侧都表达不全**(缺数组重叠算子),且真实数据隔离靠各模块手写、带 IDOR 洞。故把**数据访问控制统一**升为本次重构主轴,deny 原语降为配套章节。

## 负责人决策（累计拍板）

| 决策点 | 选择 |
|---|---|
| 数据可见性架构 | **路线 A：统一到 scope 引擎**(list + by-id 都走 `with_data_scope`,消灭手写平行实现) |
| 重构模块范围 | **知识库 + 项目 + 文档空间** 三个着重;**排除 contract_price**(客户定制扩展,非平台基础模块) |
| 知识库"各类子库"精准控制 | **(a) 按 access_type 三档精准执行**(private/public/dept);kb_type 分类型差异化 deferred(语法已就绪,见 §8) |
| deny 范围 | 权限点 deny + 数据范围 deny |
| deny 匹配粒度 | 精确权限点 + 模块通配(`deny kb:*`) |
| 超管 vs deny | 超管豁免,deny 对 `is_system`/`*` 无效(权限+数据双豁免) |
| 前端防误操作 | 仅警示色 + 审计日志,不强制二次确认 |
| 合并算法 | deny-overrides |

## 1. 目标

1. **统一可见性层**:知识库/项目/文档空间的"能看到哪些行"全部由 `DataScopeEngine` + `FilterRule` 决定,消灭每模块各自手写的 `owner OR member` 过滤。
2. **闭合 IDOR**:list 过滤了、by-id 却不复查的端点全部改为"同一条 scope 规则复用"。
3. **补齐 scope 表达力**:给 `FilterRule` 加**数组重叠**算子(知识库 `allowed_depts`),让 dept 共享真正生效。
4. **知识库可见性精准化**:把 private/public/dept 三档做对(核心是修复 dept 共享的数组重叠算子),让 `knowledge_dept` 真正生效。kb_type 分类型差异化本期不做(语法已就绪,见 §8)。
5. **deny 原语**:权限点(精确+通配)+ 数据范围(`AND NOT`)两层 deny,deny-overrides;并修 `/me` 策略一致性 bug。
6. **超管双豁免**:`is_system`/`*` 对权限 deny 与数据 deny 都免疫,内建到引擎/依赖。

## 2. 非目标

- **不动 contract_price**:客户定制扩展,自有共享语义,不套平台隔离。
- knowledge_factory / data_source / output 等配置/目录类模块**本期不铺数据 scope**(可后续)。
- 不引入 permit-overrides / 逐策略 override / priority 驱动合并(Option 2 范围)。
- 数据 deny 不支持任意 SQL 谓词,只能引用 registry 已注册 scope 的 `rule_template`;未知 scope id 写入拒绝。
- 项目内**分角色操作权限**(写/审/批)继续走 `unified_permissions`(`project_roles`),不并入 scope 引擎——它是"权限层",不是"可见性层"(§4.1)。

## 3. 现状（三模块数据访问实测）

### 3.1 三种访问模式（全仓现状）

| 模式 | 机制 | 现状 |
|---|---|---|
| scope 引擎 | `DataScopeEngine`+`with_data_scope`+`FilterRule` | 设计完整,但**全仓仅 1 处消费**(`knowledge/routers.py:84`) |
| 手写成员过滤 | service 层 `owner OR ProjectMember` | project/docmgr/workspace 真实隔离靠它,**互不一致、带 IDOR** |
| 无过滤 | 全局共享 | contract_price/knowledge_factory/data_source(本期除 contract_price 外不处理) |

### 3.2 知识库模型 + 三个实锤缺陷

`KnowledgeBase`(`models/__init__.py:140-168`):`owner_id`、`access_type`(private/public/dept)、`kb_type`(ragflow/law)、`allowed_depts`(**PG ARRAY(UUID)**)。**无 `dept_id` 列。**

by-id 真相源 = 手写 `_can_access_kb`(`routers.py:57-64`):owner ∨ public ∨ (dept ∧ `user.dept_id ∈ kb.allowed_depts`)。
list 真相源 = `with_data_scope("knowledge")`,column_map `{owner_id, access_type}`(`routers.py:99-105`)。

- **缺陷 1(list/by-id 不一致且漏 dept 共享)**:`knowledge_dept` scope 模板 `{or:[{owner_id},{dept_id IN dept_ids}]}` 引用的 `dept_id` 列**不存在** → `to_sqlalchemy` 对未知列返回 `false`(`engine.py:94`)→ dept 分支恒假 → list 里"本部门"角色**只看到自己的库**;而真实 dept 共享是 `allowed_depts` 数组重叠,FilterRule **当前语法表达不了**。
- **缺陷 2**:`knowledge_dept` scope 实际坏掉(被 dept_head/project_manager 等角色引用却无效)。
- **缺陷 3**:admin 旁路用字符串 `role_name in ["超级管理员","admin"]`(`routers.py:163,178`),与全局 `is_superadmin` 漂移。

### 3.3 项目模型 + IDOR

`ReportProject`(`models/__init__.py:589-630`):`id`、`created_by`、`archived_at`、`status`;成员经 `ProjectMember` 联结(`710`)。

- list 可见性手写:`archived_at IS NULL AND (created_by==user OR ProjectMember 存在)`(`project/service.py:160-172`),**不走 scope 引擎**。
- **IDOR(权限层洞)**:`/documents/{doc_id}/status`(`routers.py:1000`)、`/finalize-doc`(`1185`)、`/merge-docs`(`1029`)只验 `system:access`、不复查成员资格;`/activities`(`735`)、`/stats`(`1101`)、`/files`(`300`)同样。任何登录用户凭 project_id+doc_id 可改他人项目。
- `project_member` scope(`permissions.yaml:60`,`{id IN member_projects}`)已声明且等价于手写过滤,但**未被消费**。

### 3.4 文档空间模型

`AIDocument`(`models/__init__.py:202-236`):`user_id`(owner)、`project_id`(nullable FK)、`folder_id`;`Folder`(`239`):`owner_id`、`project_id`。
可见性手写:`user_id==caller OR project_id IN member_projects`(`docmgr/service.py:48-54`),by-id **处处复查**(`get_by_id(user_id)`,`104-111`)→ **IDOR 已闭合**。但 **docmgr 模块一条 data_scope 都没声明**,完全没接 scope 引擎。

### 3.5 scope 引擎 / FilterRule 现状

- `FilterRule`(`engine.py:16-111`)算子:`none_allow/allow_all/eq/in/and/or`;`to_sqlalchemy` 齐全。**缺 `not`(deny 用)与数组重叠(allowed_depts 用)**。
- `DataScopeEngine.get_data_scope`(`datascope.py:39-63`):仅 role scope 的 OR-union,无 deny 入口、不接受策略。
- `with_data_scope`(`middleware.py:339-362`):不加载策略、不做超管旁路(超管旁路现由各调用点自判)。
- **bug**:`/me`(`permission_routers.py:79-82`)构造引擎**不传 policies** → 漏算策略授权(将来也漏算 deny)。

## 4. 设计

### 4.1 两层正交模型（划界）

| 层 | 问题 | 机制 | 本设计 |
|---|---|---|---|
| **可见性** | 能看到哪些行 | `DataScopeEngine`+`FilterRule`(行级过滤) | **统一**,本期重点 |
| **权限** | 对看到的行能做什么 | 权限点 `require_permission`;项目内角色走 `unified_permissions` | 权限点补 deny;项目角色不动 |

可见性与权限**叠加生效**(see-it AND can-do-it)。项目内"我在项目 X 是审阅者"属权限层,留 `unified_permissions`,不强行塞 scope 引擎。

### 4.2 FilterRule 算子扩展（核心）

**(a) 数组重叠 `overlap`**——让知识库 dept 共享生效:

```yaml
# scope 模板语法
{ allowed_depts OVERLAP: "$identity.dept_ids" }
```
```python
# from_template 解析:key 含 " OVERLAP" → operator="overlap", field, value=identity.dept_ids
# to_sqlalchemy(PG ARRAY):
if self.operator == "overlap":
    col = column_map.get(self.field) or getattr(model, self.field)
    return col.overlap(self.value)   # PG &&；value 需为同元素类型数组(UUID)
```

**(b) 逻辑非 `not`**——数据 deny 用:
```python
if self.operator == "not" and self.children:
    return not_(self.children[0].to_sqlalchemy(model, column_map))
```

### 4.3 知识库：按 kb_type × access_type 的 scope 体系 + list/by-id 统一

**重写 knowledge 模块的 data_scopes**(`permissions.yaml`):

```yaml
knowledge:
  data_scopes:
    - { id: "knowledge_owner",  rule_template: { owner_id: "$identity.user_id" } }
    - { id: "knowledge_public", rule_template: { access_type: "public" } }
    - { id: "knowledge_dept",   rule_template: { and: [ { access_type: "dept" }, { allowed_depts OVERLAP: "$identity.dept_ids" } ] } }
```

- 角色按需绑定多个 scope,引擎 OR-union → 等价于 `_can_access_kb` 的 owner∨public∨dept,且**首次正确覆盖 dept 共享**。
- **kb_type 差异化(本期不做)**:`kb_type` 是普通列,届时用现有 eq/and 加 scope(如 `{kb_type:"law"}`)即可,无需新算子;留待按需扩展。
- **column_map 扩充**(`routers.py:99`):`{owner_id, access_type, allowed_depts}`(allowed_depts 走 overlap 算子,不走常规列解析)。

**list/by-id 统一(§4.6 通用原则)**:by-id 改为
```python
scope = await dep_with_data_scope("knowledge")(...)  # 复用同一条规则
row = (await db.execute(select(KB).where(KB.id==kid).where(scope.to_sqlalchemy(KB, colmap)))).scalar_one_or_none()
if not row: raise 404  # 既"不存在"也"无权见"都归 404,不泄露存在性
```
→ 删除 `_can_access_kb` 手写平行实现(缺陷 1 闭合)。admin 旁路统一走 `with_data_scope` 内建超管分支(缺陷 3 闭合)。

### 4.4 项目：list 改用 scope + 闭合 IDOR

**list 可见性**改用 `with_data_scope("projects")`:
```yaml
projects:
  data_scopes:
    - { id: "project_member", rule_template: { or: [ { id IN: "$identity.member_projects" }, { created_by: "$identity.user_id" } ] } }
    - { id: "project_all",    rule_template: {} }
```
(`project_member` 已声明,补上 `created_by` 并接线;`archived_at IS NULL` 仍作基础查询条件,不进 scope。)

**IDOR 闭合(权限层)**:下列端点把 `CurrentUserWithAccess`(=`system:access`)换为成员资格复查——优先复用 `require_resource_permission(...)` 或新增 `require_project_member`:
- `/documents/{doc_id}/status`(`1000`)、`/finalize-doc`(`1185`)、`/merge-docs`(`1029`)
- `/activities`(`735`)、`/stats`(`1101`)、`/files`(`300`)、phase board/readiness(`599,613`)、`/phase-status`(`911`)

### 4.5 文档空间：声明 scope + 接线

**新增 docmgr 模块 data_scopes**(`permissions.yaml`,当前为空):
```yaml
docmgr:
  data_scopes:
    - { id: "doc_owner",          rule_template: { user_id: "$identity.user_id" } }
    - { id: "doc_project_member", rule_template: { project_id IN: "$identity.member_projects" } }
    - { id: "doc_all",            rule_template: {} }
```
- `list_docs`(`docmgr/service.py:48`)改为接受 `with_data_scope("docmgr")` 产出的 FilterRule(或 service 内部按同一规则构造),`get_by_id` 复用同规则(§4.6)。
- docmgr 现 IDOR 已闭合,本节主要是**机制统一**(从手写迁到 scope 引擎),行为不变。

### 4.6 by-id 统一原则（消灭 list/by-id 分叉的通用规则）

**每个资源的 get/update/delete by-id 必须复用与 list 完全相同的 scope FilterRule**(以 `where(scope.to_sqlalchemy(model, colmap))` 叠加 id 条件),不得另写 `_can_access_*` 手写判定。"无权"与"不存在"统一返回 404,避免存在性泄露。这是 §3 全部 list/by-id 不一致缺陷的根治模板。

### 4.7 数据范围 deny（AND NOT，挂载于统一可见层）

`get_data_scope(identity, resource_type, deny_scope_ids)`(`datascope.py`):
```python
allow_rule = build_scope_union(identity, resource_type, role_scope_ids)
deny_rule  = build_scope_union(identity, resource_type, deny_scope_ids)
if deny_rule.operator == "none_allow":  return allow_rule            # 无适用 deny
if deny_rule.operator == "allow_all":   return FilterRule("none_allow")  # deny 空模板=全否
return FilterRule("and", children=[allow_rule, FilterRule("not", children=[deny_rule])])
```
- 策略 `grants.deny_data_scopes: [scope_id,...]` → `with_data_scope` 从激活策略按 identity 条件收集 deny_scope_ids 后传入(§4.10)。
- 表达力边界:deny 只能"按已声明 scope 打洞"(如 deny `knowledge_public`)。要"排除机密分类"须先声明对应 scope 且表有列/标签。

### 4.8 权限点 deny + /me 一致性（前稿保留）

- `engine.check`(精确 + 模块通配):allow 集合(角色∪策略 allow)后,任一匹配策略 `deny_permissions` 含精确点或 `prefix:*` → 拒绝。
- `engine.list_permissions`:**全量展开**为具体权限点(靠 `_all_permission_ids`,支持 `*`/`prefix:*`),再 `− deny`。输出始终具体点(与现 `/me` 一致)。
- **`/me` 修复**:`permission_routers.py:79` 改用共享 `load_active_policies(db)` 构造引擎(与 `require_permission` 同源),消除漂移。
- 提取模块级 `evaluate_policy_conditions(conditions, identity)`(`engine.py`),供 check/list_permissions/DataScopeEngine/with_data_scope 共用。

### 4.9 超管双豁免

- 权限侧:`require_permission` 在 `engine.check` 前 `is_system or "*" in resolved` 旁路(`middleware.py:240-245` 已然)。
- 数据侧:**`with_data_scope` 内建超管检测**,超管直接 `allow_all`,不经 deny 计算(不再靠各调用点自判;`knowledge/routers.py:90` 手写分支可简化为始终套用 scope)。

### 4.10 with_data_scope 改造（数据 deny + 超管 + 统一注入）

```python
async def _scope(current_user, db) -> FilterRule:
    identity = await get_identity_provider().resolve(current_user.id, db)
    reg = get_permission_registry()
    defaults = reg.get_role_defaults(identity.role_code)
    if (defaults and defaults.get("is_system")) or "*" in reg.resolve_role_permissions(identity.role_code or ""):
        return FilterRule("allow_all")              # 超管双豁免
    deny_ids = set()
    for p in await load_active_policies(db):
        if evaluate_policy_conditions(p.conditions, identity):
            deny_ids.update(p.grants.get("deny_data_scopes") or [])
    return DataScopeEngine.from_registry().get_data_scope(identity, resource_type, deny_ids)
```

### 4.11 其它（priority / 空条件 / 审计 / 前端）

- **priority**:deny-overrides 并集下对决策无影响,保留预留、文档化。
- **空条件**:策略 `conditions={}` → 全员(非超管)生效。权限 kill-switch / 数据全员排除。UI 提示。
- **审计**:`check` deny 命中 → 403 日志补 `denied by policy <name>`;数据 deny 致空集 → best-effort 日志。
- **前端策略编辑器**(`page.tsx`):新增"拒绝权限(精确+通配)""拒绝数据范围"两栏(警示色,不二次确认);`toEngineGrants`/`toGrantArray` deny 对偶;删 `grant.data_scope` 残留展示;空条件文案。

## 5. 兼容性

1. 表结构不变(`KnowledgeBase.allowed_depts` 已存在;`ReportProject.created_by`/`ProjectMember` 已存在;`AIDocument.user_id/project_id` 已存在)。**无 schema 迁移**。
2. `policies.grants` JSON dict 加 `deny_permissions`/`deny_data_scopes`,老策略 `or []` 兜底,行为同今天。
3. scope 模板重写(knowledge_dept 修正、docmgr 新增):**切换后以 yaml 为准**,上线前需 diff 现有角色 data_scopes 绑定,确认可见性不意外扩大/缩小(尤其修好的 knowledge_dept 会让"本部门"角色新看到 dept 共享库——正确收敛,但需预告)。
4. `/me` 修复会让前端多显示被漏算的策略授权按钮(向"后端允许"对齐,正确)。
5. by-id 统一为 404:"无权"与"不存在"合并,前端依赖 403 区分的需适配。
6. 回滚:可见性统一(scope 重写+with_data_scope 改造)、权限 deny、数据 deny、`/me` 修复各自独立可回退。

## 6. 测试

**FilterRule 算子**
- `overlap`:`allowed_depts.overlap(dept_ids)` 产正确 `&&`;空 dept_ids/空 allowed_depts 行为。
- `not`:`NOT (...)` 正确;`not allow_all`=全否、`not none_allow`=全真组合。

**知识库（核心）**
- list:`knowledge_dept` 角色 now 能看到 dept 共享库(access_type=dept ∧ allowed_depts∋本部门);修复前看不到。
- list:`knowledge_owner`/`knowledge_public`/`knowledge_law_all` 各自正确。
- by-id:同 list 规则复用;无权→404(不泄露存在性);超管全见。
- 回归:`_can_access_kb` 删除后所有 KB 端点行为等价。

**项目**
- list:`with_data_scope("projects")` 与原手写 `created_by OR member` 等价。
- IDOR:非成员调 `/documents/{doc_id}/status`、`/finalize-doc`、`/merge-docs`、`/activities`、`/stats` → 403。

**文档空间**
- list/by-id:`doc_owner`∨`doc_project_member` 与原手写等价;IDOR 保持闭合。

**deny**
- 权限:deny 精确/通配压过角色与 allow;超管豁免;空条件全局;`list_permissions` 展开+减。
- 数据:`deny_data_scopes` 在 knowledge 产 `allow AND NOT deny`;超管全见。
- `/me` 一致性:策略授予/拒绝在 `/me` 与 `require_permission` 一致。

**回归**:`test_datascope.py`、`test_authorization_provider.py`、角色校准测试全绿。

## 7. 文件清单

| 文件 | 改动 |
|---|---|
| `config/permissions.yaml` | knowledge data_scopes 重写(overlap+kb_type);docmgr 新增 data_scopes;project_member 补 created_by;project_roles 不变 |
| `backend/app/extensions/auth/engine.py` | FilterRule 加 `overlap`/`not` 算子 + to_sqlalchemy;提取 `evaluate_policy_conditions`;check/list_permissions 加 deny(§4.8) |
| `backend/app/extensions/auth/policy_loader.py` | **新增** `load_active_policies(db)` |
| `backend/app/extensions/auth/datascope.py` | `get_data_scope` 加 `deny_scope_ids` + `AND NOT deny`;抽 `build_scope_union` |
| `backend/app/extensions/auth/middleware.py` | `with_data_scope` 改造(§4.10);`require_permission` 用共享 loader + deny 日志 |
| `backend/app/extensions/auth/permission_routers.py` | `/me` 传 `load_active_policies(db)`(修一致性 bug) |
| `backend/app/extensions/auth/policy_routers.py` | 校验 `deny_permissions`/`deny_data_scopes`(scope id 必须存在于 registry) |
| `backend/app/extensions/knowledge/routers.py` | column_map 扩 allowed_depts/kb_type;by-id 改用 scope 复用;删 `_can_access_kb`;admin 旁路走 with_data_scope 内建 |
| `backend/app/extensions/project/routers.py` | list 改 `with_data_scope("projects")`;闭合 IDOR 端点(§4.4 清单) |
| `backend/app/extensions/docmgr/service.py`+`routers.py` | list/by-id 接 `with_data_scope("docmgr")`(行为不变) |
| `frontend/src/app/admin/roles/page.tsx` | 策略编辑器 deny 两栏 + 警示色;删 grant.data_scope 展示 |
| `backend/tests/` | §6 各项(FilteRule 算子、三模块可见性、IDOR、deny、`/me` 一致性) |

## 8. 风险与未决

- **知识库范围 = (a) 已确认**:本期只做 access_type 三档精准(owner/public/dept via overlap)。kb_type 分类型差异化 deferred——`kb_type` 是普通列,届时用 eq/and 加 scope 即可,无需新算子。
- **behavior flip 风险**:修好 `knowledge_dept` 后,"本部门"角色会**新看到**此前看不到的 dept 共享库——正确收敛,但上线前需预告并 diff 现有绑定。
- **by-id 统一为 404**:前端若依赖 403 区分"无权"需适配。
- **overlap 算子的类型对齐**:`allowed_depts` 是 UUID 数组,`identity.dept_ids` 是 str 列表 → `to_sqlalchemy` 需 cast 为同元素类型数组,实现时验证。
- **项目 list 改 scope 的等价性**:须保证 `archived_at IS NULL` 仍作基础条件叠加,不被 scope 吞掉。
- **未决**:kb_type 差异化是否需要在角色 UI 里显式按子库类型勾选 scope,还是仅靠 yaml 默认绑定(本期默认 yaml 绑定,UI 后续)。
