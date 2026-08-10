# ABAC-lite 权限系统重构设计

> 日期：2026-07-30 | 状态：草稿

## 1. 动机与目标

### 痛点

| # | 问题 | 现状 |
|---|------|------|
| P1 | 新增模块手工加权限 | 每个 router 手动写 `require_permission("xxx:yyy")`，前端手写 `PERMISSION_CATEGORIES` |
| P2 | 操作权限 & 数据权限分离 | 操作权限走 `require_permission`，数据权限散落在各 service 层的 `WHERE dept_id=?` |
| P3 | 角色权限定死 | 角色-权限映射硬编码在 seed 脚本和 `_ROLE_DEFAULTS` 里 |
| P4 | 权限检查不统一 | 10 个模块路由无后端权限检查，部分用 `require_role`（硬编码 role_name） |
| P5 | 双轨 RBAC 互不通信 | `roles.permissions` 数组（系统级）和 `role_permissions` 表（项目级）各自独立 |
| P6 | 身份维度单一 | 只有 `role_id` + `dept_id`，无法应对标签、项目角色、自定义属性等复杂场景 |

### 目标

1. **配置驱动**：新模块声明权限点（YAML），引擎自动生效，无需改权限核心代码
2. **ABAC-lite**：基于属性的访问控制，身份 = 可解析属性集（角色/部门/项目角色/标签/自定义 KV）
3. **操作+数据统一**：一个引擎同时回答"能不能做这个操作"和"能看到哪些数据"
4. **全链路**：后端引擎 → 管理 UI → 前端按钮可见性

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    permissions.yaml                        │
│  modules:                                                 │
│    knowledge:    { permissions: [...], data_scopes: [...]}│
│    contract_price: { permissions: [...], data_scopes: [...]}│
│    ...                                                    │
│  roles:                                                   │
│    dept_head: { permissions: [...], data_scopes: [...]}   │
│    ...                                                    │
└──────────────┬───────────────────────────────────────────┘
               │ 启动加载
               ▼
┌──────────────────────────────┐  ┌────────────────────────┐
│    PermissionRegistry         │  │   IdentityProvider      │
│  • 模块权限点注册             │  │  • resolve(user_id)     │
│  • 权限点查询 API             │  │  • 返回 AttributeSet    │
│  • 变更热更新                 │  │  • 可插拔标签解析器     │
└──────────────┬───────────────┘  └───────────┬────────────┘
               │                              │
               └──────────┬───────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│                 UnifiedPermissionEngine                    │
│                                                           │
│  check(identity, permission) → bool                       │
│  get_data_scope(identity, resource_type) → FilterRule     │
│  list_permissions(identity) → PermissionSet               │
└──────────┬───────────────────────────────────────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐ ┌──────────────┐
│ Backend   │ │  Frontend     │
│ FastAPI   │ │  React        │
│ Depends() │ │  usePermission│
└──────────┘ └──────────────┘
```

核心原则：
- **Identity 是属性集**，不预设具体字段。role/dept/tags 都是属性的一个来源
- **权限点由模块声明**，引擎不内置任何模块权限
- **数据域是 FilterRule**，由引擎统一生成 SQL WHERE / 过滤条件

---

## 3. Identity Provider（身份属性解析器）

### 3.1 AttributeSet 数据结构

```python
@dataclass
class AttributeSet:
    user_id: str
    username: str

    # ── 固定属性 ──
    role_code: str | None          # 主角色 code（如 "dept_head"）
    role_level: int                # 主角色级别
    dept_id: str | None            # 主部门
    dept_ids: list[str]            # 所有部门

    # ── 动态属性（懒加载/外部解析）──
    member_projects: list[str]     # 参与的项目 ID 列表
    project_roles: dict[str, str]  # {project_id: role_code}

    # ── 可扩展属性 ──
    tags: list[str]                # 自定义标签（如 "external", "security_officer"）
    labels: dict[str, str]         # 任意 KV
    extra: dict[str, Any]          # 模块自定义扩展属性
```

### 3.2 解析流程

```
IdentityProvider.resolve(user_id)
  ├── 1. 加载 User + Role（DB 查询）
  ├── 2. 加载 UserDepartment[] → dept_ids
  ├── 3. 加载 ProjectMember[] → member_projects, project_roles
  ├── 4. 遍历 TagResolver 插件 → tags, labels
  │     • BuiltInTagResolver: 从 user.labels JSONB 解析
  │     • 自定义 TagResolver: 外部系统/业务逻辑
  └── 5. 缓存（请求级）
```

### 3.3 TagResolver 插件接口

```python
class TagResolver(Protocol):
    """解析用户的自定义标签和属性。每个模块可注册自己的 resolver。"""
    name: str

    async def resolve(self, user_id: str, db: AsyncSession) -> dict:
        """返回 {tags: [...], labels: {...}, extra: {...}}"""
        ...
```

示例：
```python
# 合同价格模块注册的 TagResolver
class ContractPriceTagResolver:
    name = "contract_price"

    async def resolve(self, user_id, db):
        # 如果用户在采购管理部 → 打标签
        dept = await db.get(Department, user.dept_id)
        tags = ["procurement"] if dept and "采购" in dept.name else []
        return {"tags": tags, "labels": {}, "extra": {}}
```

---

## 4. Permission Registry（权限注册中心）

### 4.1 配置文件格式（`permissions.yaml`）

```yaml
# 权限定义（模块声明）
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - id: kb:read
        display_name: "查看知识库"
        description: "浏览和搜索知识库内容"
      - id: kb:create
        display_name: "创建知识库"
        description: "创建新的知识库"
      - id: kb:update
        display_name: "编辑知识库"
      - id: kb:delete
        display_name: "删除知识库"
      - id: kb:upload
        display_name: "上传文档"
    data_scopes:
      - id: knowledge_owner
        display_name: "仅自己的知识库"
        rule_template: { owner_id: "$identity.user_id" }
      - id: knowledge_dept
        display_name: "本部门的知识库"
        rule_template:
          or:
            - { owner_id: "$identity.user_id" }
            - { dept_id IN: "$identity.dept_ids" }
      - id: knowledge_public
        display_name: "所有公开知识库"
        rule_template: { access_type: "public" }

  contract_price:
    display_name: "合同价格分析"
    permissions:
      - id: cpa:read
        display_name: "查看合同价格"
      - id: cpa:import
        display_name: "导入合同"
      - id: cpa:cluster
        display_name: "执行聚类分析"
      - id: cpa:export
        display_name: "导出分析结果"
    data_scopes:
      - id: cpa_all
        display_name: "全部合同数据"
        rule_template: {}
      - id: cpa_dept
        display_name: "本部门合同"
        rule_template: { dept_id IN: "$identity.dept_ids" }

  user_management:
    display_name: "用户管理"
    permissions:
      - id: user:read
        display_name: "查看用户"
      - id: user:create
        display_name: "创建用户"
      - id: user:update
        display_name: "编辑用户"
      - id: user:delete
        display_name: "删除用户"
    # 用户管理不需要数据域（全量或全无）

  role_management:
    display_name: "角色管理"
    permissions:
      - id: role:read
      - id: role:create
      - id: role:update
      - id: role:delete

  department:
    display_name: "部门管理"
    permissions:
      - id: department:create
      - id: department:update
      - id: department:delete

  project:
    display_name: "报告项目"
    permissions:
      - id: project:create
      - id: project:edit
      - id: project:delete
      - id: project:read
      - id: member:add
      - id: member:remove
      - id: chapter:write_own
      - id: chapter:write_any
      - id: chapter:review
      - id: chapter:review_any
      - id: approval:submit
      - id: approval:review
      - id: approval:approve
      - id: approval:view
      - id: ai:start_writing
      - id: outline:edit
      - id: settings:edit
      - id: export:generate
      - id: source:view
      - id: version:rollback
    data_scopes:
      - id: project_member
        display_name: "参与的项目"
        rule_template: { id IN: "$identity.member_projects" }
      - id: project_all
        display_name: "全部项目"
        rule_template: {}

  workflow:
    display_name: "工作流"
    permissions:
      - id: workflow:read
      - id: workflow:start
      - id: workflow:cancel
      - id: workflow:edit

  docmgr:
    display_name: "文档空间"
    permissions:
      - id: doc:read
      - id: doc:upload
      - id: doc:delete

  model_access:
    display_name: "模型访问"
    permissions:
      - id: model:read

  skills:
    display_name: "插件与工具"
    permissions:
      - id: skill:read
      - id: skill:install
      - id: skill:uninstall

  license:
    display_name: "许可证管理"
    permissions:
      - id: license:manage
        admin_only: true

  app_center:
    display_name: "应用中心管理"
    permissions:
      - id: app_center:manage
        admin_only: true

# ── 角色-权限映射（默认值，运行时 DB 覆盖）──
roles:
  superadmin:
    display_name: "超级管理员"
    is_system: true
    level: 100
    permissions: ["*"]  # 通配符 = 所有权限
    data_scopes: ["project_all", "cpa_all", "knowledge_public"]

  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    permissions:
      - kb:read
      - kb:create
      - doc:read
      - doc:upload
      - project:create
      - project:read
      - model:read
      - system:access
      - workflow:read
      - cpa:read
      - cpa:import
      - approval:approve
      - approval:submit
      - approval:view
      - chapter:review
      - source:view
    data_scopes:
      - knowledge_dept
      - cpa_dept
      - project_member

  project_manager:
    display_name: "项目经理"
    is_system: false
    level: 60
    permissions:
      - "#inherit:dept_head"     # 继承部门负责人的所有权限
      - project:edit
      - member:add
      - member:remove
      - chapter:write_any
      - ai:start_writing
      - outline:edit
      - settings:edit
      - export:generate
      - approval:submit
      - approval:review
      - workflow:start
      - workflow:cancel
    data_scopes:
      - project_member
      - knowledge_dept
      - cpa_dept

  writer:
    display_name: "撰写人"
    is_system: false
    level: 10
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
      - chapter:write_own
      - chapter:review
      - ai:start_writing
      - source:view
      - workflow:read
    data_scopes:
      - project_member
      - knowledge_dept

  reviewer:
    display_name: "审核员"
    is_system: false
    level: 20
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
      - chapter:review
      - approval:review
      - source:view
      - workflow:read
    data_scopes:
      - project_member
      - knowledge_dept

  user:
    display_name: "普通用户"
    is_system: false
    level: 1
    permissions:
      - kb:read
      - doc:read
      - model:read
      - system:access
    data_scopes:
      - knowledge_public
      - project_member
```

### 4.2 权限继承语法

```yaml
permissions:
  - "#inherit:dept_head"       # 继承 dept_head 的全部权限（可叠多个 #inherit）
  - project:edit               # 额外权限
  - "!chapter:write_any"       # 显式排除某项（可选语法）
```

### 4.3 热更新

- 文件变更 → 引擎自动 reload
- `/api/permissions/registry` 返回当前生效的权限注册表
- 角色-权限映射仍然存储在 DB 的 `roles.permissions` 列，`permissions.yaml` 中的 `roles` 节仅作为 seed 数据
- `with_data_scope(resource_type)` 不强制要求 `{resource_type}:read` 权限——数据域是独立维度的过滤规则，即使角色没有显式的 read 权限点，只要有数据域配置就能在允许的范围内查询
- 没有配置 `data_scopes` 的模块（如 user_management）默认 `NONE_ALLOW`（拒绝一切），需显式配置 `{}`（空模板 = 全量）才允许全量访问

---

## 5. UnifiedPermissionEngine（统一权限引擎）

### 5.1 核心 API

```python
class UnifiedPermissionEngine:
    """ABAC-lite 权限引擎。"""

    @staticmethod
    async def check(
        identity: AttributeSet,
        permission: str,
        resource: dict | None = None,   # 可选：具体资源属性
    ) -> bool:
        """
        检查用户是否有某操作权限。

        1. 如果 identity.role_code 对应角色有 "*" → True
        2. 如果 permission 在 identity 的有效权限列表中 → True
        3. 如果 resource 不为 None → 额外检查数据域规则
        """
        ...

    @staticmethod
    async def get_data_scope(
        identity: AttributeSet,
        resource_type: str,
    ) -> FilterRule:
        """
        返回用户对某类资源的数据过滤规则。

        返回值可直接转换为 SQLAlchemy filter 表达式。
        """
        ...

    @staticmethod
    async def list_permissions(
        identity: AttributeSet,
    ) -> list[str]:
        """列出身份持有的所有有效权限点（用于前端渲染）。"""
        ...
```

### 5.2 FastAPI 集成

```python
# 新式用法：依赖注入
def require_permission(permission: str):
    """替代旧 middleware 中同名函数的依赖工厂。"""
    async def checker(
        current_user = Depends(get_current_user),
        db = Depends(get_db),
        engine: UnifiedPermissionEngine = Depends(get_permission_engine),
    ) -> AttributeSet:
        identity = await IdentityProvider.resolve(current_user.id, db)
        if not await engine.check(identity, permission):
            raise HTTPException(403, f"Permission denied: {permission}")
        return identity   # 返回 identity 供下游使用
    return checker


def with_data_scope(resource_type: str):
    """注入数据域过滤器。"""
    async def scope(
        identity: AttributeSet = Depends(require_permission(f"{resource_type}:read")),
        engine: UnifiedPermissionEngine = Depends(get_permission_engine),
    ) -> FilterRule:
        return await engine.get_data_scope(identity, resource_type)
    return scope


# 使用示例
@router.get("/knowledge-bases")
async def list_kbs(
    db = Depends(get_db),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    query = select(KnowledgeBase).where(scope.to_sqlalchemy())
    ...
```

### 5.3 FilterRule 表达式与变量解析

YAML 中的 `rule_template` 使用 `$identity.xxx` 语法引用用户属性，运行时由引擎替换：

```
{ owner_id: "$identity.user_id" }          → 简单字段替换
{ dept_id IN: "$identity.dept_ids" }       → IN 子句展开
{ id IN: "$identity.member_projects" }    → 列表值 IN
```

```python
@dataclass
class FilterRule:
    """可序列化的过滤规则，支持 AND/OR/IN/EQ/NONE_ALLOW（空=全拒绝）。"""
    operator: str   # "eq" | "in" | "and" | "or" | "none_allow"
    field: str | None = None
    value: Any = None
    children: list["FilterRule"] | None = None

    @classmethod
    def from_template(cls, template: dict, identity: AttributeSet) -> "FilterRule":
        """将 YAML rule_template + identity 解析为具体 FilterRule。"""
        ...

    def to_sqlalchemy(self, model, column_map: dict[str, Column]) -> BinaryExpression:
        """
        转换为 SQLAlchemy WHERE 表达式。
        column_map 映射字段名到模型列：{"owner_id": Model.owner_id, "dept_id": Model.dept_id, ...}
        """
        ...

    def to_dict(self) -> dict:
        """序列化为 JSON（供前端使用）。"""
        ...
```

### 5.4 `admin_only` 权限

`admin_only: true` 标记的权限（如 `license:manage`、`app_center:manage`）**仅对 `is_system=true` 的角色生效**。不允许在 UI 中分配给非系统角色。

---

## 6. 前端——全链路权限控制

### 6.1 权限 API

| 端点 | 用途 |
|------|------|
| `GET /api/permissions/registry` | 全部权限点定义（模块列表、权限 ID、显示名） |
| `GET /api/permissions/me` | 当前用户的有效权限列表 + 身份属性 |
| `GET /api/permissions/roles/{code}` | 某角色的权限配置 |

### 6.2 React 权限 Hook

```typescript
// 使用示例
function KnowledgeBasePage() {
  const { can, identity } = usePermission();

  return (
    <div>
      {can("kb:create") && (
        <Button onClick={handleCreate}>新建知识库</Button>
      )}
      {/* data_scope 控制筛选条件 */}
      <Select
        options={identity.dept_ids.map(...)}
        value={filterDept}
      />
    </div>
  );
}
```

### 6.3 角色管理 UI 升级（三 Tab 分级配置）

管理员打开 `/admin/roles/{code}`，三个 Tab 按复杂度分级：

**Tab 1：操作权限**（日常管理）

按 `permissions.yaml` 的 `modules` 动态渲染，每行一个模块，每列一个权限点，勾选即生效。

- 模块列表和权限点**完全来自注册表**，新增模块自动出现
- 支持"全选模块"/"全选全部"批量操作
- `admin_only: true` 的权限只对系统角色可见
- `is_system=true` 的角色只读

**Tab 2：数据权限**（日常管理）

每个资源类型选择预置的数据范围模板（来自模块 YAML 声明的 `data_scopes`）：

| 资源类型 | 可选数据范围 |
|---------|------------|
| 知识库 | ◉ 仅自己的 ○ 本部门 ○ 全部公开 |
| 合同价格 | ○ 全部数据 ◉ 本部门 |
| 报告项目 | ◉ 参与的项目 ○ 全部项目 |

数据范围为空的模块（如用户管理）不显示在此 Tab。

**Tab 3：自定义策略**（高级管理员）

基于任意身份属性编写条件规则，类似 IAM 策略编辑器：

```
┌───────────────────────────────────────────────────────┐
│ + 新增策略                                             │
│                                                       │
│ 策略名称: [采购部可导入合同___________]                  │
│                                                       │
│ 条件:                                                  │
│ ┌──────────────────┬──────────┬────────────────────┐  │
│ │ tags             │ contains │ [procurement]      │  │
│ ├──────────────────┼──────────┼────────────────────┤  │
│ │ role_level       │ >=       │ [50]               │  │
│ └──────────────────┴──────────┴────────────────────┘  │
│ [+ 添加条件]                                           │
│                                                       │
│ 满足 [全部条件 ▾] 时：                                  │
│   操作权限: [cpa:import _______________] [+ 添加]       │
│   数据范围: [本部门 ▾]                                  │
│                                                       │
│ [取消]  [保存策略]                                     │
└───────────────────────────────────────────────────────┘
```

已有策略列表（支持启用/禁用/编辑/删除）：

```
策略名称              │ 条件                         │ 效果
──────────────────────┼─────────────────────────────┼────────────────
采购部可导入合同       │ tags ∋ procurement          │ cpa:import
                      │ AND role_level ≥ 50          │ 数据: 本部门
外部顾问只读           │ tags ∋ external              │ kb:read
                      │                             │ 数据: 仅自己的
```

**可用属性列表**（来自 `AttributeSet` + 所有 `TagResolver` 注册的属性）：

| 属性 | 类型 | 来源 |
|------|------|------|
| `role_code` | string | 用户角色 code |
| `role_level` | int | 角色等级 |
| `dept_id` | string | 主部门 UUID |
| `dept_ids` | list | 所有部门 |
| `member_projects` | list | 参与的项目 |
| `tags` | list | 自定义标签 |
| `labels.*` | string | 自定义 KV |

**可用运算符**：`=`, `!=`, `>`, `>=`, `<`, `<=`, `contains`（包含）, `not_contains`, `in`（列表中）, `not_in`


---

## 7. ABAC 策略引擎

### 7.1 策略存储

策略存储在 DB 的 `policies` 表中（新建），同时 `permissions.yaml` 可提供 seed 策略：

```sql
CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INT NOT NULL DEFAULT 0,
    conditions JSONB NOT NULL,
    grants JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

对应的 YAML seed 格式：

```yaml
policies:
  - name: "采购部可导入合同"
    priority: 10
    conditions:
      and:
        - { attr: "tags", op: "contains", value: "procurement" }
        - { attr: "role_level", op: "gte", value: 50 }
    grants:
      permissions: ["cpa:import"]
      data_scope: "cpa_dept"
```

### 7.2 策略评估

`UnifiedPermissionEngine.check()` 的完整评估流程：

```
check(identity, permission, resource?)
  │
  ├── 1. 角色通配符检查
  │      "*" 在角色权限中？→ True
  │
  ├── 2. 角色直接权限检查
  │      permission 在 roles.permissions 中？→ True
  │
  ├── 3. ABAC 策略评估（按 priority 升序）
  │      遍历每条 enabled 策略:
  │        evaluate(条件, identity) → True
  │        且 permission 在策略.grants 中
  │        → 如果 resource 不为 None → 额外检查 data_scope
  │        → True
  │
  └── 4. 默认拒绝 → False
```

策略之间是 **OR 关系**——任意一条匹配即通过。低 priority 值优先评估；两条策略给同一用户授予不同 data_scope 时，取 priority 更小的那条。

### 7.3 条件表达式求值

```python
class ConditionEvaluator:
    OPERATORS = {
        "eq": lambda attr, val: attr == val,
        "neq": lambda attr, val: attr != val,
        "gt": lambda attr, val: attr > val,
        "gte": lambda attr, val: attr >= val,
        "lt": lambda attr, val: attr < val,
        "lte": lambda attr, val: attr <= val,
        "contains": lambda attr, val: val in attr if isinstance(attr, list) else False,
        "not_contains": lambda attr, val: val not in attr if isinstance(attr, list) else True,
        "in": lambda attr, val: attr in val,
        "not_in": lambda attr, val: attr not in val,
    }

    @classmethod
    def evaluate(cls, conditions: dict, identity: AttributeSet) -> bool:
        """递归评估条件树。and/or 节点递归求值，叶子节点调用运算符。"""
        ...
```

---

## 8. 迁移计划

### Phase 1：引擎 + 注册中心（向后兼容）

1. 新增 `permissions.yaml`，迁移现有所有权限点
2. 实现 `PermissionRegistry` + `UnifiedPermissionEngine`
3. 新增 `IdentityProvider`（基础版：role + dept + project_members）
4. 旧版 `require_permission` 内部改为调用 `UnifiedPermissionEngine.check()`
5. 现有 API 行为不变，回归测试通过

### Phase 2：数据域引擎

1. 实现 `FilterRule` 表达式 + `DataScopeEngine`
2. 新增 `with_data_scope()` 依赖注入
3. 逐一迁移各模块的 `WHERE dept_id=?` 为 `scope.to_sqlalchemy()`
4. 首批：knowledge、project、contract_price

### Phase 3：前端全链路

1. 新增权限 API 端点
2. 实现 `usePermission` Hook
3. 升级角色管理 UI（动态权限列表）
4. 各页面按钮级 `can()` 控制（按模块分批做）

### Phase 4：清理

1. 删除废弃的 `project/permissions.py`（`PERMISSION_MATRIX`）
2. 统一 `role_permissions` 表和 `roles.permissions` 列（合并为统一存储）
3. 删除硬编码的 `_ROLE_DEFAULTS`
4. 10 个未保护模块全部接入权限检查

---

## 9. 文件清单

| 文件 | 用途 |
|------|------|
| `config/permissions.yaml` | 模块权限声明 + 角色默认映射 + seed 策略 |
| `backend/app/extensions/auth/identity.py` | `IdentityProvider` + `AttributeSet` + `ConditionEvaluator` |
| `backend/app/extensions/auth/engine.py` | `UnifiedPermissionEngine` + `FilterRule` |
| `backend/app/extensions/auth/registry.py` | `PermissionRegistry`（YAML 加载 + 热更新） |
| `backend/app/extensions/auth/middleware.py` | 改造：`require_permission` / `with_data_scope` |
| `backend/app/extensions/auth/routers.py` | 新增：`/api/permissions/*` + `/api/policies/*` 端点 |
| `backend/app/extensions/auth/models.py` | 新增：`Policy` 模型 |
| `backend/app/extensions/auth/tag_resolvers/` | 可插拔 TagResolver 目录 |
| `frontend/src/core/permissions/` | `usePermission` Hook + 权限上下文 |
| `frontend/src/app/admin/roles/` | 升级：三 Tab 权限配置（操作/数据/策略） |
| `docs/superpowers/specs/2026-07-30-abac-rbac-redesign-design.md` | 本设计文档 |
