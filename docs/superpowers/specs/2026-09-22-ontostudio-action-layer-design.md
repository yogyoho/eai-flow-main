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

`app/doc_graph/tables.py` 新增 `DgActionAudit`，随 `Base.metadata` 建表。

> **⚠️ 订正（2026-09-22 Task 3 规格审查实测）**：本设计初稿写的是"由 gateway 启动时的 `create_all` 建表——与现有 `dg_*` 同一机制"。**那是错的，且 `app/db.py:7` / `app/ontology/__init__.py:8` / `app/doc_graph/tables.py:86` 三处注释同样在说谎**：2026-09-17 独立服务搬迁把 `dg_*` 模型从 gateway 的 `Base` 摘到了本地 `app.db.Base`，而 **gateway 的 `Base.metadata` 里 `dg_*` 表为零**、ontostudio 全仓 `create_all` 只出现在注释里从未被调用。现存 4 张 `dg_*` 表是搬迁前建的。
>
> **实际建表路径**：由 **ontostudio 自身的 lifespan** 调 `Base.metadata.create_all`（`await conn.run_sync(...)`，用 `create_async_engine(_ext_url(), poolclass=NullPool)`，照 `app/doc_graph/ingest.py:40` 的既有模式）。这正是 `app/db.py:7` 预告过的"Task 3 起本服务接管"。
>
> **已知限制**：`create_all` **只建缺失的表，不做 schema 变更**——列增删改仍需人工迁移。这是本仓既有取向（gateway 同样如此），但必须写明，别让人以为有了自动迁移系统。

### 1.2.1 建表失败的降级契约（Task 3 质量审查裁定，**必读**）

**策略：非致命。** `ensure_tables()` 失败只留 WARNING，不阻断启动。

**为什么不是 fail-closed**：service 的 registry / kernel / MCP 读路径都不需要 DB。fail-closed 会用一个**功能级缺口**（审计写不进去）换**整服务不可用**，是错的轴；且会红掉 6 个进 lifespan 的测试。

**代价（必须知情，这是选择非致命换来的一侧）**：

- `/health` 是 DB 无关的，而两份 compose 的 healthcheck 都打它 → **无表实例报告健康**
- dev compose **没有 `postgres-ext` 的 `depends_on`**（offline 有）→ 竞态在 dev 是活的
- `create_all` **只在 lifespan 跑一次**，配 `restart: unless-stopped` 意味着**DB 恢复后不会自动补建，必须重启容器**
- 每个将来新增 `dg_*` 表的任务都会重掷同一次骰子

**配套要求**：

| 项 | 状态 |
|---|---|
| 生产引擎加 `connect_args={"timeout": 5}` | Task 3 落地。**没有它 warn-only 给不出保护**——实测黑洞地址下引擎 21.4s 才抛（Linux 可能约 2 分钟），这段窗口 uvicorn 根本不服务，异常路径压根走不到。**护栏的正确表述**：计时型上界测试只抓"超时被删掉/放大到同一量级以上"；`5→9s` 的漂移由一条捕获引擎实参的确定性测试钉住（`test_ensure_tables_bounds_connect_timeout`）。**不要声称上界测试能抓值漂移——经变异证伪** |
| `/health` 增加就绪字段（**不改状态码**） | Task 3 落地。把可观测性做出来；是否让 healthcheck 因此判不健康，是影响两份 compose 的运维决策，不由本任务单方面改 |
| 首次用 DB 时重试 / 懒建 | **Task 5 Step 6 落地**（写入方是它的建造者）：写路径遇 SQLSTATE 42P01 时调一次 `ensure_tables()` 并**在新事务里**重试一次；模块级 flag 保证每进程只尝试一次懒建（有界，不是重试循环），只对「表不存在」触发（宽 catch 会把连接失败/权限错误也吞进来），其余 DB 失败如实转 500。**已知限制**：`create_all` 只建缺失的表，不做 schema 变更——懒建解决不了「表在但列不全」 |

### 1.2.2 残余风险：**命令阶段无界**（Task 3 复审订正）

`connect_args={"timeout": 5}` **只界住握手**。TCP 建好之后，asyncpg 命令阶段默认 `command_timeout=None`，**是无界的**。两条真实路径：

1. **连接建立后链路被防火墙/NAT 静默掐断** → 只能等 TCP 自己发现（Windows 默认 keepalive 约 **2 小时**）。**这与原 I2 是同一个"启动楔死"失效模式，只是位置更靠后**——连接阶段超时修不掉它。
2. **`CREATE TABLE` 需要 ACCESS EXCLUSIVE 锁** → 撞上并发 DDL / 长事务会阻塞等待。

**为什么不阻塞本轮**：已文档化的失效模式在连接阶段（21s→5s 是本轮的真收益），验收点是"启动不被黑洞地址吊死"。

**为什么这个理由必须写准**：Task 3 的初版理由是"DDL 时长本就有界"——**那是错的**，会让人把"命令阶段无界"读成"不存在风险"。同理，"加 command_timeout 只会引入新的误杀面"也比实情弱：引擎是 NullPool 且在同一次调用内 `dispose()`，command_timeout 只影响**这一次** `create_all`，而它的失败已被设计成非致命（WARNING + `tables_ready=False`）——**误杀代价≈一条 WARNING**。

**已收口（Task 5 Step 6，2026-09-23）**：取 `connect_args={"timeout": 5, "command_timeout": 30}`——上面「误杀代价≈一条 WARNING」的取舍成立，故取 30 而非 60，倾向早失败。
**写路径的两个超时必须拆开裁决**（Task 5 规格审查订正——把两者捆成一句"都没传"会弱化握手那一半）：

| | 连接阶段（握手） | 命令阶段 |
|---|---|---|
| 有无"合法的长等待" | **无** | 有——`FOR UPDATE` 撞上并发长事务时可以合法地等很久 |
| 无超时的后果 | **请求永久挂起**，占住 ASGI 任务（本机实测 21.5s，Linux 可到分钟级） | 同上，但那个等待可能是正当的 |
| 误杀面 | **不存在** | 真实存在——30s 会把"等到后成功"变成**用户可见的 500** |
| 结论 | **已补**：`connect_args={"timeout": 5}`，与 `ensure_tables` 同值 | **已收口（Task 7, 2026-09-23）**：`command_timeout=60`（`executor.py::_WRITE_COMMAND_TIMEOUT_S`）——**故意不等于**建表路径的 30，见下 |

> **命令阶段的裁决（Task 7，`77c7bbceb` 之后）**：本表此前写「留 Task 6/7 裁决」，Task 6 是 gateway 侧没做，而 Task 7 节原本也没提它——**本计划第六次"凡写下'那是 X 的范围'却没同时改 X 的步骤"**。Task 7 裁定收口并实装：
>
> - **为什么不能继续留 `None`**：写引擎的每条 `FOR UPDATE` / `UPDATE` 都跑在**与读端点共用的事件循环 worker** 上，而 `/actions/invoke`（本任务新开）让这条路径可被用户直接触发。无界意味着链路被静默掐断时请求挂到 TCP keepalive（Windows ≈ 2 小时）为止，**期间占住整个 worker**——比 500 严重得多。
> - **为什么取 60 而非 30**：本表把两条路径的误杀面分开了——建表那边误杀 ≈ 一条 WARNING，写路径是**用户可见的 500**；而唯一合法的长等待是 `FOR UPDATE` 撞并发写同一行，单行审核动作的竞争写者应为毫秒级。60s 已比"排队"宽两个数量级，再大就是拿"worker 被占住的时长"换裕度。
> - **实现与守卫**：常量连同理由落在 `executor.py` 顶部；Task 5 那条「断言 `command_timeout` **缺席**（有意留空）」的测试**翻转**成正向断言，并加一条 `!= db._COMMAND_TIMEOUT_S` 的反向断言挡住"顺手统一成同源"。顺带修 `str(TimeoutError())` 是空串导致 detail 变成 `"写事务失败: "` 的问题（收口后这条路径设计上可达），新增 1 条测试钉住。

关键区别是**取舍轴不同**：握手阶段不存在"合法的长等待"，所以那个超时**没有可比的误杀面**——它与 `command_timeout` 不是同一类决策，不能因为后者有争议就一起不加。**一个请求永久挂死，比一个 5 秒失败严重得多，而前者没有任何正当理由。**

替代方案 `server_settings={'lock_timeout': …, 'statement_timeout': …}` 未采用。

> **本节是这条取舍的正典（canon）**（Task 5 质量审查 M-5）。同一取舍目前有 4 份副本——`app/db.py`、`executor.py`、`spec`（本节）、以及一条测试 docstring。**四处全文重述会漂移**；代码与测试处**只保留够用的短注释并指向本节**，需要完整论证时看这里。

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

三处**都要改**，但强度不同（Task 3 审查实测订正）：

> **`doc_graph.yaml` 的 status `enum` 并不参与 SHACL**——`kernel/compile.py:65,73,103` 只读 `etype`/`predicate` 的 enum；YAML 的 enum 仅经 `mcp.py:134` 的属性 dump 对 agent 可见。所以初稿「三处不同步则 SHACL 当场判违规」对 YAML 那一处**表述不准**。真正会让 SHACL 判违规的是 `validate.py` 的两处。YAML 那处仍要改（否则 agent 看到的枚举与校验器不一致）。

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
- ~~前置条件的 `value` 若来自 `params`，类型必须与属性声明一致，否则 400~~
  **【订正 2026-09-22 Task 4 复审】本行是悬空承诺——已删除。** 本设计**不存在**"前置条件的 value 来自调用方 params"的机制：全库无 `$params` 之类替换，且计划里 executor 把调用方 `params` **只写进审计行**（`CAST(:params AS jsonb)`），**从不进 SQL 值位置**。因此：
  - 前置条件的 `value` **只能来自 registry 字面量**（YAML 是热加载的，故它是"作者笔误"的输入面，不是"不可信调用方输入"）
  - 由此，`sql_write` 的形状守卫（拒 str/int/dict 等）拦的是**作者笔误**，Task 9 的 lint 才是它更该在的层（见计划 Task 9）
  - 若将来真的要开"参数化前置条件"，那是**新机制**，须重新设计并回答"值从哪来、如何校验"，不要在实现时顺手加上

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

### 3.1 `/scope` 不是平台数据范围判定的忠实投影（Task 6 规格审查 F2——**本节的缺口**）

本节原话只说「返回 `DataScopeEngine.get_data_scope()` 的结果」。而平台正典 `with_data_scope`（`backend/app/extensions/auth/middleware.py:350-388`）在那之上还有两步，**`/scope` 两步都没做**，且**方向相反**：

| 缺的那一步 | 正典行为 | `/scope` 当前 | 方向 |
|---|---|---|---|
| **超管旁路**（`middleware.py:380`：`is_system` 或 `permissions` 含 `"*"` → `allow_all`） | 直接放行 | 不认 | **比平台更严** → 会 404 掉本该允许的动作 |
| **ABAC `deny_data_scopes` 扣减**（`middleware.py:385`；`get_data_scope` 本身**支持** `deny_scope_ids`） | 在 allow 上扣 deny | **不传** `deny_scope_ids` | **比平台更松 = fail-open** → 一条 `deny_data_scopes: [ontology_all]` 的策略会被动作层忽略 |

**今日无实害**（Task 6 质量审查独立确认两条路径）：`policies` 表 **0 行**（连一条 deny 策略都不存在）；唯一持有 `ontology_all` 的角色是 superadmin，而超管旁路在 deny 循环**之前就 return `allow_all`**，故即便造出 deny 策略，平台侧对唯一持有者也免疫。超管旁路那一半另被 superadmin 的 `data_scopes: [ontology_all]` 授权**掩盖**住了。

> **⚠️ 时间性事实（改变了这条缺口的可触发性，勿按旧文理解为"纯理论"）**：`policy_routers.py:47-50` 校验 `deny_data_scopes` 的每个 id **必须在 registry 中已声明**——而 **`bc4609635` 之前，`ontology_all` 在 `permissions.yaml` 里出现 0 次**。也就是说，**是那次提交本身第一次让"deny 掉 `ontology_all`"成为一条可被管理员创建的策略**。缺口从"理论上"变成"一次管理操作即可触发"。
>
> **最坏情形具体化**：`{conditions: {}, grants: {deny_data_scopes: [ontology_all]}}` 在平台侧是**全域读封锁**（空模板 deny ⇒ `get_data_scope` 返回 `none_allow`），而 OntoStudio 的读路径与动作层**完全无视它**。

**但这是设计缺口，不是实现缺口**——实现严格符合本节字面。**收敛动作已立为 Task 7 节首的硬性验收项**（此前这里写"见 Task 7 接线清单"，而 Task 7 并无该步骤——**那是本计划第五次"凡写下'那是 X 的范围'却没同时改 X 的步骤"**，已修）。

> **✅ 已闭合（Task 7，2026-09-23，`31e5af471`）**：`/scope` 不再自建判定——`middleware.resolve_data_scope` 成为数据范围判定的**唯一**实现，`with_data_scope` 与 `/api/permissions/scope` 两侧共用同一条路径（超管旁路 + `deny_data_scopes` 扣减 + registry 范围并集）。上表两行**同时**不再适用。
>
> **验收方式（实测，`backend/tests/test_permissions_scope_endpoint.py` 4 条两侧一致性用例）**：用 overlay 造一个**非超管**且持 `ontology_all` 的角色（仓里没有任何这种角色——`ontology_all` 只授给了 superadmin，而超管在两侧都走旁路，用超管测不到扣减那一步），配一条 `{conditions: {}, grants: {deny_data_scopes: [ontology_all]}}` 策略 → 两侧同为 `none_allow` 且**逐字相等**；同角色去掉该策略（**对照态**）→ 两侧同为 `allow_all`（没有这条，一个恒 `none_allow` 的实现也能过上一条）；超管 + 同策略 → 两侧同为 `allow_all`；`docmgr` 的非退化复合树（`or`/`eq`/`in`）→ 两侧相等。
>
> **两类断言的判别力经变异实测校准，别只留一类**：`== platform.to_wire()` 抓**两处漂移**（把 `/scope` 改回自建判定 → 红）；**绝对值**断言抓**共用的那一条判定本身错了**（删掉旁路、或删掉 deny 扣减 → 相等断言**仍然全绿**，只有绝对值红）。
>
> **一处有意的行为变更**：**超管 + 未知 resource** 由 `none_allow` 变 `allow_all`。判据是 `with_data_scope("no_such_module")` 对超管同样返回 `allow_all`（旁路排在 `get_data_scope` **之前**，资源存不存在根本到不了那一步）——"两侧一致"优先于更早那句「未知资源一律 none_allow」。非超管那一支行为不变（仍 fail-closed）。
>
> 下面「今日无实害」一段现在只是**当时的历史快照**：别再拿它当"所以不用修"的依据（它描述的正是缺口未修时为何没被触发）。

### 3.2 已知减损：`/scope` 的 4xx 映射只兜竞态窗口（Task 6 实现者披露，未修）

`/scope` 现在经 `require_permission("system:access")` 门禁，而 **`require_permission` 内部自己就 resolve 一次**（`middleware.py:224-225`，同请求缓存）。于是"**用户行已删**"这个情形在**依赖层**就抛 `ValueError` → **500**；端点里加的 `except ValueError → 403` 只兜得住两次 resolve 之间的竞态窗口。

**之所以留着不修**：实现者写不出会让它变红的测试（映射在依赖层之上，测不到），故它**既没声称判别力、也没在注释里把它写成有效护栏**——代码注释明写了这一点。把映射上移到依赖层会**同时影响 `/me` 与 `with_data_scope`**，属独立决策，不该在 `scope` 一个端点上擅自挪。

**这是"知道但不修"的正当形态**：有记录、有理由、有归属边界、且实现者没有把它伪装成已解决。**记录在此，供将来做统一错误映射时一并处理。**

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

### 4.1 MCP 通道的授权模型（**Task 8 实现者提出，协调者裁定 2026-09-24**）

**现状（Task 8 实测）**：`run_action_for_mcp` **不校验动作权限**——`required_permissions`（`ontology:action:review`）**只在 REST 侧逐条校验**；数据范围恒 `allow_all`。这是由于 MCP 走**共享头鉴权、没有可判定的调用者身份**，无法按用户授权。

> **本节的漏项**：本节初版只裁定过**数据范围**那一半（"域级二态下没有可区分的维度"，记为已知天花板），**权限那一半当时没写**。而工具描述原本还宣称「权限与数据范围**在服务端强制**」——**一句不成立的安全承诺，而且是写给 agent 看的**。Task 8 已订正描述为事实版（"写路径在服务端（事务/审计/身份标注）；本通道的授权在 MCP 配置层，不逐条校验动作声明的 `required_permissions`"）。

**裁定：接受「MCP server 注册即授权」，但附一条硬触发条件。**

- **为什么这是真授权门**：在 `extensions_config.json` 里 enable `ontology` server 需要**改配置文件并重启服务**，**不是 agent 自己能做的事**——能被 agent 调用，即管理员已同意该 agent 使用本体写路径。这与"逐条校验 `required_permissions`"是两个层级，但都不是空的。
- **为什么不做动作级授权**：MCP 侧**目前没有调用者身份**，做不了；那要先设计一套 MCP 身份机制（per-agent token 或等价物），是**新机制**而非接线。
- **为什么不做"只暴露具名工具"**：会与本节「通用入口 + 具名薄包装**共用执行体**」冲突，且**挡不住任何事**——具名包装同样能写。

> **⚠️ 触发条件（必须遵守，不得默认沿用）**：**当前唯一动作是审核**（`review_entity.confirm` / `.reject`）——**可逆、爆炸半径小、且审计留痕**，这是接受上述裁定的前提。**一旦加入爆炸半径更大的动作（批量改价、删除、跨域写），必须先落地 MCP 侧的身份与动作级授权，再上那个动作。** 这条不是建议，是前提。
>
> **可选的廉价加固（未做，供将来）**：在 MCP server 的配置里加 `action_id` 白名单，让部署能限制该通道可调用的动作集合。成本低，但它**不替代**上面的触发条件——白名单管的是"哪些动作"，触发条件管的是"谁能调"。

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
