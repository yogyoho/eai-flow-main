# OntoStudio 动作层与实例级权限设计（P0-1 / P0-2）

> 状态：DESIGN APPROVED（2026-09-22 会话四问定案 + 三处确认）。
> 决策链：三轴完备性对照（国标 / Palantir / 业务闭环）→ 缺口清单 P0 五项 → 借鉴 `sharptoolbox/ontology-driven-dev` 的 M2 行为模型 → 四问定案。
> 前置讨论：`.wolf/tmp/ontostudio-completeness.html`（三轴对照表）、`docs/ontology/methodology.md` §4.4、`docs/superpowers/specs/2026-09-18-ontostudio-formal-kernel-design.md`（图原生内核）。
> 缺口出处：P0-1「实例级权限缺失」、P0-2「动作写回缺失」（`ontostudio` 只有 `merge_entities`/`unmerge` 一种窄写回）。

## 0. 需求画像（brainstorming 结论）

- **第一个动作**：审核动作（`review_entity.confirm` / `.reject`）。选它是因为它是唯一一个**已有半成品、有真实数据、有现成 UI 落点**的写回——`status ∈ {active, pending_review, merged}` 与 `ResolutionPanel` 已存在。链路先通，再换靶子。
- **真相源**：Postgres `dg_*` 是唯一真相源，内核图是**派生视图**。审核是业务事务，事务边界必须落在 Postgres；pyoxigraph 的写不参与 SQL 事务，双写要自己造补偿。
- **权限轴**：**域级授权为 P0，行级留扩展点**。本体表（`cpa_*` / `csp_*` / `dg_*`）**没有任何身份列**（无 `dept_id`/`user_id`/`created_by`），主平台的 `data_scopes` 模板在这些表上无法求值。硬做行级会产出 `allow_all` 兜底的**假过滤器**——比没有更危险。
- **Agent 面**：通用入口 + 具名薄包装，**共用同一执行体**。两套写路径并存即重演 P1-6（两套规则引擎）的亏。
- **借鉴边界**：拿 M2 行为模型的 `preconditions / postconditions / requiredPermissions / behaviorType` 骨架；**不拿** `syncTriggers`（同步跨聚合联动＝把耦合请回来，且本期无消费者）与 `appliedRules`（无独立规则求值器，前置条件已表达判断）。

## 1. 数据模型

### 1.1 注册表新增 `actions:` 段

`DomainFile` 顶层，与 `formal` 并列；声明落在 `app/ontology/schemas.py`。

```yaml
# app/ontology/registry/doc_graph.yaml
actions:
  - id: review_entity.confirm
    display_name: 确认实体
    description: 将待审抽取实体置为 active，同一事务内记审计
    domain: doc_graph
    target: graph_entity              # → ObjectType.api_name，解析到 dg_entities
    required_permissions: [ontology:action:review]
    preconditions:
      - { field: status, op: eq, value: pending_review }
    postconditions:
      - { field: status, set: active }
  - id: review_entity.reject
    display_name: 驳回实体
    description: 将待审抽取实体置为 rejected，同一事务内记审计
    domain: doc_graph
    target: graph_entity
    required_permissions: [ontology:action:review]
    preconditions:
      - { field: status, op: eq, value: pending_review }
    postconditions:
      - { field: status, set: rejected }
```

```python
class Precondition(BaseModel):
    """前置条件：只允许「列 op 字面量」——不做表达式求值（对标 M2 的谓词语法，收窄到可静态校验的子集）。"""
    model_config = ConfigDict(extra="forbid")
    field: str
    op: Literal["eq", "ne", "in", "not_in", "is_null", "not_null"]
    value: Any | None = None

class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    set: Any | None = None
    now: bool = False                     # set 与 now 互斥（模型校验器强制）

class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str                               # "<family>.<verb>"，如 review_entity.confirm
    display_name: str
    description: str
    domain: str
    target: str                           # ObjectType.api_name
    behavior_type: Literal["COMMAND"] = "COMMAND"   # 本期只做 COMMAND；QUERY 已有 engine.py，不重复
    required_permissions: list[str] = []
    preconditions: list[Precondition] = []
    postconditions: list[StateChange] = Field(min_length=1)
    version: int = 1
```

**实施补充（Task 2 质量审查引入，超出本节三类校验）**：`action.domain` 须与 `target` 所属对象类型的 `domain` 一致。理由是 `domain` 会写进 `dg_action_audit.domain`，而同一行的表名来自 target 对象——两者不一致会产出"domain 与表对不上"的审计行，而审计是这条写路径唯一的追溯凭据。校验位置必须在"target 存在性"检查**之后**（否则 target 不存在时取 `by_api_name[target]` 会 KeyError，掩盖真实的 `unknown action target` 错误）。

`DomainFile` 增 `actions: list[ActionSpec] = []`。**校验以 `@model_validator(mode="after")` 挂载、随 `model_validate` 自动跑**（不采用"须显式调用的公开方法"——本仓既有模式是前者，见 `app/doc_graph/schemas.py:154`；后者无先例且会被本计划后续 Task 的代码绕过）。`registry.py` 加载时做**交叉引用校验**：`target` 必须解析到本域已声明的 `ObjectType`；`preconditions[].field` 与 `postconditions[].field` 必须是该对象类型的已声明属性；`required_permissions` 非空。任一不满足 → **fail-closed 拒绝加载**（与现有 registry 一致）。

### 1.2 审计表

`app/doc_graph/tables.py` 新增 `DgActionAudit`，随 `Base.metadata` 由 **gateway 启动时的 `create_all`** 建表——与现有 `dg_*` 同一机制，**无需迁移脚本**。

```
dg_action_audit
  id            uuid   PK  default gen_random_uuid()
  action_id     text        NOT NULL
  domain        text        NOT NULL
  target_table  text        NOT NULL
  target_pk     uuid        NOT NULL
  actor_id      uuid        NOT NULL          -- CurrentUser.id
  actor_role    text
  params        jsonb       NOT NULL DEFAULT '{}'
  before        jsonb                          -- 变更前列值（仅受影响列）
  after         jsonb                          -- 变更后列值
  source        text        NOT NULL DEFAULT 'api'   -- api | mcp
  created_at    timestamptz NOT NULL DEFAULT now()
  INDEX (target_pk, created_at DESC)
  INDEX (actor_id, created_at DESC)
```

**`MergeAudit` 图节点降级为该表的投影**——**属 §4 折叠步（第 2 步）的范围，不在本 spec 实现范围内**；本 spec 只建表、只写行，不动 `MergeAudit`。物理三元组仍永不删（保留合并/撤销语义）。

### 1.3 必须一并改的涟漪：`status` 枚举加 `rejected`

三处不同步则 SHACL 当场判违规：

| 位置 | 现值 | 改为 |
|---|---|---|
| `app/ontology/kernel/validate.py:58` | `Literal(v) for v in ("active","pending_review","merged")` | 追加 `"rejected"` |
| `app/ontology/kernel/validate.py:61` | `"status 必须是 active/pending_review/merged 之一"` | 同步文案 |
| `app/ontology/registry/doc_graph.yaml` | `status` 的 `enum` | 追加 `rejected` |

选 `rejected` 而非删除行：删除会丢审计链，与"物理记录永不删"的既有取向冲突。

## 2. 执行模型

`invoke_action(action_id, params)` 单条管线。**服务端永不信任调用方给出的表名或列名。**

```
1 解析 ActionSpec              → 未声明即拒（fail-closed）
2 权限校验 required_permissions → 复用现有 _gateway_authorizes 通道（30s 缓存）
3 取数据范围 FilterRule         → §3；编译为 WHERE 片段
4 事务（create_async_engine + NullPool + async with engine.begin()，照 app/doc_graph/ingest.py:40-44）
   a. SELECT ... WHERE <pk> = :pk AND (<scope>) FOR UPDATE
      └ 行不存在 **或** 不在可见范围 → 404（不区分二者，避免存在性泄漏）
   b. 前置条件对**锁定后的行**求值 → 不满足 → 409 + 中文提示
   c. UPDATE <registry 声明的表> SET <postconditions> WHERE <pk> = :pk
      └ 表名/列名**只能来自解析后的 ActionSpec**，值一律命名参数绑定
   d. INSERT dg_action_audit（before / after / params / actor / source）
5 提交后：受影响行**增量重投影**进内核图
   └ 失败不回滚业务状态，记入 errors 并可重放（与 kernel/infer.py 现有降级处理一致）
```

返回：`{action_id, target, pk, before, after, audit_id, projected: bool}`。

**写守卫是新增的、与读守卫分开。** 现有 `sqlguard.assert_readonly_select` 按设计只放 SELECT，不能复用。新增 `actions/sql_write.py`：

- 表名、列名只能来自解析后的 `ActionSpec`（内部经 registry 白名单），**调用方的 `params` 只允许出现在值位置**
- 值一律命名参数绑定；标识符加引号
- 前置条件的 `value` 若来自 `params`，类型必须与属性声明一致，否则 400

## 3. 权限接线（域级为 P0，行级为扩展点）

| 层 | 落点 | 内容 |
|---|---|---|
| 策略真相源 ①：操作权限 | `config/permissions.yaml`（+ `deploy/offline/config/permissions.yaml`） | `ontology` 模块（L259）的 page 下新增 operation `ontology:action:review`。模块与 `nav_id: nav:ontology` 已存在，仅追加 operation |
| 策略真相源 ②：数据范围 | 同上 | **`ontology` 模块现为 `data_scopes: []`——必须新增**：`ontology_all`（`rule_template: {}`，空模板＝全量，比照既有的 `cpa_all`/`csp_all`/`bpp_all`），并把 `graph_entity` / `graph_relation` 的 `scope_resource` 绑到 `ontology`。**漏掉这一步则 `scope_resource` 恒解析为 `none_allow`，动作永远 404** |
| 资源 key 命名 | 同一份 yaml | `scope_resource` 的值就是 `DataScopeEngine` 的 `resource_type`，即 permissions.yaml 的**模块 key**（`ontology` / `contract_price` / `spare_parts` / `bid_quote`…），非 scope id |
| 规则求值 | gateway `backend/app/extensions/auth/`（**extensions 层，不动 harness 核心**） | **新增只读端点** `GET /api/permissions/scope?resource=<key>` → 序列化 `FilterRule`（即 `DataScopeEngine.get_data_scope()` 的结果）。需带 EAI-CUSTOM 标注 |
| 物理绑定 | registry `ObjectType.scope_resource` + 可选 `scope_bindings` | `scope_resource` 声明该对象类型归属哪个权限资源 key；`scope_bindings: {模板字段: 本表列名}` 在两者不一致时覆盖，缺省恒等映射 |
| 编译 | ontostudio `app/ontology/scope.py` | vendor `FilterRule` 数据类（约 10 行，纯数据，注释注明来源与同步方式）+ `rule_to_sql(rule, bindings) -> (fragment, params)`：`allow_all→TRUE`、`none_allow→FALSE`、`and/or/not`、`eq→col = :p`、`in→col = ANY(:p)`、`overlap→col && :p` |
| 静态校验 | `scripts/ontology_lint.py` | 每个可能生效的 scope 模板字段，必须能解析到该对象类型的已声明属性或 `scope_bindings`；否则 lint 失败 |

**今日实际形态（写明以免误解）**：本体表无身份列，因此带 `ontology_all`（空模板）的角色解析为 `allow_all`，不带者为 `none_allow`——二者之间**没有中间态**。**这就是域级授权**：能看/不能看整个域。通道是真的：等哪天补上归属列，填 `scope_bindings` 即可开出真行级，不改架构。

`FilterRule` 走 wire 时用其字段的 JSON 形态（`operator` / `field` / `value` / `children`），两侧各自持有数据类，**不共享代码**——OntoStudio 是独立服务，无法 import `app.*`。

## 4. Agent 面

| 工具 | 形态 | 说明 |
|---|---|---|
| `invoke_action` | 通用，MCP（`/mcp/ontology`） | 参数 `action_id` + `params`。`action_id` 由 registry 生成枚举；`describe_ontology` 一并返回可用动作清单（`id` / `display_name` / `description` / 参数） |
| `review_entity` | 具名薄包装 | 高频路径。内部调**同一条** executor，不复制逻辑 |
| `merge_entities` / `unmerge` | **折叠为 action**（`review_entity.merge` / `.unmerge`） | 排期见下 |

**为什么通用 + 具名并存**：通用入口好扩展，但具名工具对 LLM 更友好（枚举型 `action_id` 易选错，且 harness 有 `tool_search` 延迟加载，工具越碎发现成本越高）。故取中间：**长尾走 `invoke_action`，高频走具名包装，同一个执行体**。

**折叠排期（不可颠倒）**：框架不存在时无法折叠。

1. 建框架，`review_entity` 走通（本 spec 的实现范围）
2. 把 `merge_entities` / `unmerge` 机械移植到同一执行体——两侧测试同时绿
3. 删旧实现；**验收以"旧实现文件已删除、MCP 上只剩一条写路径"为准**

中间态两套并存是**过渡**，不是终态。

## 5. 文件落点

```
新增  ontostudio/backend/app/ontology/actions/__init__.py
新增  ontostudio/backend/app/ontology/actions/executor.py      # §2 管线
新增  ontostudio/backend/app/ontology/actions/sql_write.py     # 写守卫 + UPDATE 构造
新增  ontostudio/backend/app/ontology/scope.py                 # FilterRule + rule_to_sql
改    ontostudio/backend/app/ontology/schemas.py               # ActionSpec/Precondition/StateChange + DomainFile.actions
改    ontostudio/backend/app/ontology/registry.py              # 加载 actions 段 + 交叉引用校验
改    ontostudio/backend/app/ontology/registry/doc_graph.yaml  # 声明 review_entity.*
改    ontostudio/backend/app/ontology/routers.py               # POST /actions/invoke
改    ontostudio/backend/app/ontology/mcp.py                   # invoke_action / review_entity
改    ontostudio/backend/app/ontology/kernel/validate.py       # status 枚举加 rejected（L58/L61）
改    ontostudio/backend/app/doc_graph/tables.py               # DgActionAudit
改    ontostudio/backend/scripts/ontology_lint.py              # scope 绑定校验
改    backend/app/extensions/auth/routers.py   # gateway 侧 GET /api/permissions/scope（与 /me 同文件同 router，L253 旁）
改    backend/app/extensions/auth/datascope.py  # 如需暴露 resource→FilterRule 的便捷入口（现有 get_data_scope 已够，预期不改）
改    config/permissions.yaml                 # ontology 模块：operation ontology:action:review + data_scopes 新增 ontology_all
改    deploy/offline/config/permissions.yaml   # 同上（离线模板必须同步，否则离线部署恒 404）
```

## 6. 测试策略（TDD：先红后绿）

| 文件 | 覆盖 |
|---|---|
| `ontostudio/backend/tests/test_actions_schema.py` | 合法 YAML 解析通过；未知 `target`、空 `postconditions`、非法 `op`、`set`+`now` 并存 均拒绝 |
| `ontostudio/backend/tests/test_scope_rule_to_sql.py` | 8 个 operator 各自编译正确；**参数绑定而非字符串拼接**（含注入用例）；`scope_bindings` 覆盖生效 |
| `ontostudio/backend/tests/test_actions_executor.py` | happy path；前置不满足→409；行不在范围→404；无权限→403；审计行落库且 before/after 正确；**投影失败不回滚** |
| `ontostudio/backend/tests/test_actions_mcp.py` | 两工具注册、鉴权、`action_id` 枚举与 registry 一致 |
| `backend/tests/test_permissions_scope_endpoint.py` | `/api/permissions/scope` 返回序列化 FilterRule；无角色→`none_allow`；`*_all`→`allow_all` |

## 7. 验收（端到端为主判据）

1. `pending_review` 实体 → `review_entity(confirm)` → `status=active`；`dg_action_audit` 有对应行；图重投影后 SHACL 无违规
2. 同一动作作用于非 `pending_review` 行 → 409 + 中文提示
3. 无 `ontology:action:review` 的用户 → 403
4. **有操作权限但角色不带 `ontology_all`** → **404**（数据范围拒绝用 404 而非 403：存在性不外泄）。这条同时是 §3 那句"漏掉 `data_scopes` 则恒 404"的反向验证
5. 注入投影失败 → 业务状态**已提交**、`errors` 有记录、可重放
6. `ontology_lint.py` 对"模板字段无绑定"报错

## 8. 明确不做（YAGNI）

- `syncTriggers` / 跨聚合同步联动——本期无消费者，且是耦合来源
- `appliedRules` 独立规则求值器——前置条件已表达判断
- `triggerType`（USER_ACTION / SYSTEM）——本期动作只有人触发
- 行级权限本体实现——**待数据具备归属轴**（见 §3 今日形态）
- 动作的撤销 / 回滚（`undo`）——审计已留 `before`，可据此手写补偿；产品化另议
- `QUERY` 型动作——`engine.py` 已覆盖查询面

## 9. 风险与后置

| 风险 | 处置 |
|---|---|
| 写路径是新的攻击面 | §2 写守卫：表/列只来自声明，值一律参数绑定；专门的注入测试 |
| `rejected` 引入后旧数据/旧查询不认 | SHACL 与 registry 三处同步改；`enum` 是追加不是替换，向后兼容 |
| gateway 端点改动影响主平台 | 只读端点、不改既有路由；`DataScopeEngine` 已有单测覆盖，新增端点走同一引擎 |
| 折叠 merge/unmerge 时功能回归 | 分三步走，第 2 步两侧测试同时绿才进第 3 步 |
| `FilterRule` 两边各自持有会漂移 | 在 `scope.py` 注释注明来源文件；wire 形态变更时两侧同步；纳入 lint 检查 |
| **`not_in` 空集是 fail-open**（Task 1 实测发现） | `NOT (col = ANY(ARRAY[]))` ≡ `TRUE` ≡ 放行全部。这是 `NOT IN` 的标准语义，但方向与 `in`（空集＝拒绝）相反。**今日无暴露路径**：参考实现 `engine.py::from_template` 目前不产出 `ne/not_in/not`。**修复位置在 gateway 侧解析层**（`_resolve` 返回 None 时应 fail-closed 为 `none_allow`，与既有 `IN` 分支同向），**不要在 `scope.py` 加空集守卫**——那会把语义判断塞进纯编译器。若将来 gateway 开始下发 `not_in`，必须先补这条 |
