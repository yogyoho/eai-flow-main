# OntoStudio 动作层与域级实例权限 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 OntoStudio 加一条受治理的写路径——动作在 registry 里声明、经权限与数据范围校验、在 Postgres 事务内落库并记审计，同时经 MCP 暴露给 agent。

**Architecture:** 声明式动作（`registry/*.yaml` 的 `actions:` 段）→ 单条执行管线（解析 → 权限 → 数据范围 → `FOR UPDATE` 锁定 → 前置校验 → UPDATE → 审计行）→ 提交后增量重投影进内核图。Postgres `dg_*` 是唯一真相源，图是派生视图。权限的**策略**在 `config/permissions.yaml`（gateway 为真相源，经 `/api/permissions/scope` 下发序列化 `FilterRule`），**物理绑定**在 registry（`scope_resource` + 可选 `scope_bindings`）。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async + asyncpg（NullPool）/ pydantic v2（`extra="forbid"`）/ pyoxigraph / pytest + pytest-asyncio / httpx

**Spec:** `docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md`

**工作目录约定**：除非另注，所有命令在 `D:\eai\eai-flow-main\ontostudio\backend` 下执行；gateway 侧改动在 `D:\eai\eai-flow-main\backend` 下执行。测试统一 `PYTHONPATH=. uv run pytest <path> -v`（若 `uv run` 在该环境不工作，用 `PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest <path> -v`——Task 1/2 实测可用）。

### ⚠️ 每个 Task 开工前必须跑一次「归属语句」检查（Task 1–7 的教训，**六次复发**）

**这不是提示，是一条命令。** 本计划已**六次**出现"凡写下『那是 X 的范围』/『留给 X』/『随 X 落地』，却没同时改 X 的步骤"：

| 次 | 谁推给谁 | 结果 |
|---|---|---|
| 1 | Task 2 → Task 3（动作声明） | Task 3 初稿没接 |
| 2 | Task 4 → Task 5（前向风险） | 写进计划才接住 |
| 3 | 「随 Task 5 落地」（懒建 + `command_timeout`） | Task 5 步骤里没有 |
| 4 | Task 3 → Task 6（`graph_relation`） | Task 6 没接 |
| 5 | spec「收敛见 Task 7 接线清单」 | Task 7 原文一字未提 |
| 6 | 计划 L131「留给 Task 7 的暴露面裁决」（`command_timeout`） | **Task 7 原文一字未提**（Task 7 实现者自查发现） |

**前五次我的对治都是"在计划里写得更清楚"——而"写文字"正是失败的那个手段**（第六次是 Task 7 实现者自己发明了 grep 才防住的）。所以：

**每个 Task 开工前，先跑这一条，并把输出贴进报告：**

```bash
grep -nE "留给 Task|随 Task|那是 Task .* 的范围|Task [0-9] (/|和) [0-9]|待 Task|由 Task" \
  docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md
```

**判据**：输出的每一条，要么①其目标 Task 的步骤里确有对应步骤（grep 目标节确认），要么②在这一轮被显式认领并补上。**两者都没有 = 第七次复发，停下来处理。**

> **⚠️ 首次实跑（2026-09-23，Task 7 收口时）暴露了这条检查自身的噪音问题——请先读这段再跑。**
>
> 首次实跑命中 **11 条**，而**其中 10 条是"历史叙述"**：本节的六次复发表、以及各 Task 里解释"为什么在这里 / 这是第 N 次"的说明块——**它们用的措辞与被检查的"活的归属语句"完全一样**（都含"那是 Task N 的范围"）。
>
> **一个检查如果大部分输出是噪音，人会开始跳过它——那就等于没有检查**（与本文件反复出现的"覆盖声称高于覆盖事实"同源）。
>
> **当前的已知集合（跑出这 11 条即为正常，无需处理）**：本节的复发表（3 条）· Task 3 Step 4b/Step 9 的说明块 · Task 5 Step 6 的说明块 · 进度节的 `/scope` 与命令阶段两处闭合块 · 以及那行 grep 命令自身。**超出这个集合的命中才是新的，才需要按判据处理。**
>
> **分布位**（Task 7 实跑观察）：**活的归属语句目前为 0 条**——六次都已在各节内闭合。**若你在 Task 8/9/10 开工前跑出这个集合之外的命中，那就是第七次。**

### ⚠️ 每个 Task 的验证清单必须包含 format 检查（Task 1–2 的教训）

**ontostudio 没有 Makefile，所以没有 `make lint` 替你兜底。** 主仓 `make lint` 是**两条**命令：`ruff check .` **加** `ruff format --check .`。只跑前者会漏掉排版问题——Task 2 就漏了一次（新测试文件是全仓唯一未格式化的文件，被规格审查者抓到）。

所以每个 Task 的 Verify 步骤固定为：

```bash
./.venv/Scripts/python.exe -m ruff check <改动路径>
./.venv/Scripts/python.exe -m ruff format --check <改动路径>   # ← 别省这一条
```

若 `format --check` 报要重排，直接 `ruff format <该文件>` 修掉再提交。**只格式化本次改动的文件**，不要顺手格式化别的（`app/auth.py:272` 有一处既有未格式化，不属任何 Task 的范围）。

**本计划的代码块一律不是 format-clean 的**（Task 1–2 已出现 5 例：`-> "StateChange"` 引号触发 UP037、未用 import 触发 F401、import 顺序触发 I001、紧凑 dict 被重排、以及一条陈旧计数）。**实现者请把「跑 format 后重排」视为本任务的常规步骤，而非偏离**——但仍要在报告的偏离清单里如实计入。

### 派发给实现者的通用要求（每个 Task 一致）

- **若计划给的代码过不了计划给的测试或 lint，不要改测试迁就代码、也不要默默改了了事。** 判明是计划错还是测试错，按"哪个符合本任务声明的意图"定，然后在报告里**点名哪一行、为什么、怎么改的**。Task 1–2 共 5 次这样顶回来，每次都值回票价。
- **偏离清单以「全部偏离」为准，包含 lint/format 驱动的调整。** 只报功能性的偏离会制造"已完全合规"的错觉。

### 审查方法学：变异检验的合法手法（Task 2 的教训）

**变异检验**（删掉/放宽一段代码，看测试是否变红）是本计划审查者最有价值的手法——Task 2 靠它找到了 3 个盲区，其中一个是"唯一一处为契约而写的代码，删掉 264 条测试全绿"。**后续每个 Task 的审查者都应做**。

但它**有假阴性陷阱**，Task 2 实测踩到过一次：

审查者在 Task 2 自核了这套手法，并**发现自己踩了 4 个更隐蔽的坑**（其中一个是"假阴性的镜像假阳性"）。所以判定一条变异结论要过**三关**：

#### 关一 · 合法性（手法本身能不能禁用目标代码）

| 算真禁用 ✅ | 不算 ❌ |
|---|---|
| 删装饰器 / 注册语句 | **改函数名**（pydantic 的 `@model_validator` 按装饰器注册、不按名解析 → **假阴性**） |
| 删分支 / 删守卫 / 删条件（连 `if` 行一起删，别留空体） | 改类型签名 / 参数名 |
| 条件改恒真恒假（`if False:`） | 只改注释 / docstring |
| 放宽正则 / 常量改过宽值 | |
| 清空方法体 / 提前 `return` | |
| **反转条件**（`!=`→`==`，用于验接受路径） | |
| **挪动检查顺序**（用于验顺序性前提） | |
| 换掉 `except` 的异常类型使其不再捕获目标异常 | |

#### 关二 · 有效性（这次变异真的作用到代码上了吗）

- **不做这三件事，结论不可信**：① 副本与活树 **hash 比对**（保真）；② 未变异基线必须**全绿**；③ 每条用后**还原并再比 hash**。
- **绝不在活树里做变异实验**——会污染并发审查者的快照。审查者实测踩到：它 `cp -r` 快照的那一刻，实现者正在活树里跑"删装饰器"变异，于是它复制到一棵校验器已禁用的树，**所有行显示同一个指纹**，差点报出"改名会禁用 pydantic 校验器"——正是那条假阴性的**镜像假阳性**。
- **多行锚点必须断言"变异已生效"**：锚点不匹配时文件根本没变却报 GREEN，是另一种假阴性。

#### 关三 · 可测性（RED 是真的 RED 吗）

- **解析/收集错误不算 RED**：`IndentationError` / `SyntaxError` / `error during collection` 在 pytest 里同样显示 failed，但那是**假 RED**，不是"守卫被钉住了"。判定为 `INVALID` 而非 RED。
- **pytest 必须在完整继承的环境里跑，且要看真实输出**（Task 3 实测）：传受限 `env` 会让收集直接崩，**`rc != 0` 被误读成"变异被抓"**。变异脚本必须完整继承环境 + 输出解码用 `errors="replace"` + 逐条打印 pytest 的真实尾行。**rc≠0 不是 RED 的充分证据。**
- **删了代码留下空体**（只删 `try:` 里的行、留下裸 `try:`）同样产出 `SyntaxError` 假红——变异"看起来生效了"不等于"变异体合法"。

**一条无法消除的盲区，必须知情**：**"断言状态存在"型的测试，在状态已经存在之后就对变异免疫**。Task 3 实测：`dg_action_audit` 建出来之后，把 lifespan 里的建表调用删掉，那条真库测试**仍然绿**。对策是**补一条断言"可观测效果"的测试**（例如 DB 不可达时是否留下 WARNING、服务是否仍能起）——它断言的是行为而非状态，在任何环境都跑，删掉调用即红。**新写"某物存在"型测试时，先问一句：这个断言在东西已经存在之后还测得到什么？**
- **换行符会静默毁掉锚点，且本仓不统一——逐文件确认，勿假设**：实测 `ontology/schemas.py` 与 `ontology/registry.py` 是 **CRLF**；而 `doc_graph/tables.py`、`ontology/kernel/validate.py`、`ontology/scope.py`、`.yaml` 与测试文件都是 **LF**。**同一段多行锚点在不同文件上行为不同。**（Task 3 的派发把这条说成了"通例"，被实现者实测纠正——这类环境事实一律现场用 `\r` 计数确认，不要从别处外推。）

**假阴性比假阳性危险**：它让人把一个**有保护**的实现判成**没保护**，去"补"一个本就存在的测试，同时把真实盲区留在阴影里。**审查者报"某段代码无测试保护"时，必须说明变异手法与三关证据；任一关不过，结论作废、须重做。**

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `ontostudio/backend/app/ontology/scope.py`（新建） | `FilterRule` 数据类（wire 编解码）+ `rule_to_sql()` 编译为参数化 WHERE |
| `ontostudio/backend/app/ontology/actions/__init__.py`（新建） | 包标记 |
| `ontostudio/backend/app/ontology/actions/sql_write.py`（新建） | **唯一写路径标识符白名单与片段构造处**；前置条件 WHERE + UPDATE SET 构造。**语句骨架由 executor 拼装**（`text(f"UPDATE {table_q} SET {set_sql} WHERE …")`）、表名经 `quote_ident`——「唯一」不含语句级拼装 |
| `ontostudio/backend/app/ontology/actions/executor.py`（新建） | 执行管线：解析 → 鉴权 → 取范围 → 事务 → 审计 → 重投影 |
| `ontostudio/backend/app/ontology/schemas.py`（改） | `Precondition` / `StateChange` / `ActionSpec`；`DomainFile.actions`；`ObjectType.scope_resource` / `scope_bindings` |
| `ontostudio/backend/app/ontology/registry.py`（改） | 加载 `actions:` 段 + 交叉引用校验（target/field 必须已声明） |
| `ontostudio/backend/app/ontology/registry/doc_graph.yaml`（改） | 声明 `review_entity.confirm` / `.reject`；`status` enum 加 `rejected`；`graph_entity.scope_resource: ontology` |
| `ontostudio/backend/app/ontology/kernel/validate.py`（改） | status 枚举 + 提示文案加 `rejected` |
| `ontostudio/backend/app/doc_graph/tables.py`（改） | `DgActionAudit` ORM |
| `ontostudio/backend/app/ontology/routers.py`（改） | `POST /api/extensions/ontology/actions/invoke` |
| `ontostudio/backend/app/ontology/mcp.py`（改） | `invoke_action` / `review_entity` 工具 + `describe_ontology` 附动作清单 |
| `ontostudio/backend/scripts/ontology_lint.py`（改） | scope 绑定校验 |
| `backend/app/extensions/auth/routers.py`（改） | `GET /api/permissions/scope` |
| `backend/app/extensions/auth/authz_cache.py`（新建） | 授权判定的缓存键修正（见 Task 6） |
| `config/permissions.yaml` + `deploy/offline/config/permissions.yaml`（改） | `ontology:action:review` operation + `ontology_all` data_scope |

**实现顺序的理由**：1→4 是纯函数与纯校验（无 IO，最好测），5 才组合它们；6 是 gateway 侧前置（缺它 executor 拿不到范围规则）；7→8 是暴露面；9→10 收口与端到端。

---

## 📍 当前进度与续跑说明（新会话从这里读起）

**已完成（2026-09-22）**：

| Task | 产物 | 测试 | 提交链 |
|---|---|---|---|
| 1 `scope.py` | 数据范围规则树 + 参数化 WHERE 编译 | 33 | `902f0584a` → `eed650f81` → `0d6f4a971` |
| 2 registry `actions` 段 | `ActionSpec` 等三模型 + `_check_refs` 模型级校验 + `Registry.actions`/`get_action` | 20 | `cae787750` → `7a25ed2bc` → `15c435c32` → `12bb71803` → `e04dcb8af` → `d569b37db` |
| 3 审计表 + 声明动作 | `dg_action_audit`；`status` 加 `rejected`；`doc_graph.yaml` 声明两个动作；**并修复一个阻塞级缺陷**（该表此前无任何建表路径） | +9 | `4d8b2a900` → `ed572100a` → `25f5083d9` → `bec0f31ae` |
| 4 `sql_write.py` 写守卫 | 标识符白名单 + 参数化 WHERE/SET 构造；**修掉两条 fail-open**（`not_in` 空值恒真、value 形状错逐字符拆） | 39 | `dd106e3c6` → `ba4646916` → `25f95721a` |
| 5 `executor.py` 执行管线 | 解析→范围→锁定→前置→UPDATE(RETURNING)→审计→容错重投影；**Step 6 写路径韧性**（42P01 懒建 + 有界重试 + 握手超时）；返回体含 `audit_id` | 26 | `125747dad` → `a794a65ae` → `557decbd8` → `227f6a64b` → `8049e7c6d` |

| 6 gateway 侧 | `GET /api/permissions/scope`（实测活容器返回 `allow_all`）；`FilterRule.to_wire()`；两份 `permissions.yaml` 加 `ontology:action:review` + `ontology_all`；**Step 9** `graph_relation` 补 `scope_resource`；wire golden 契约守卫；`/scope` 身份改用正典 `resolve()` | +16 | `bc4609635` → `4d18b91fa` → `0fe50a398` → `dd053fc73` |
| 7 REST 暴露面 | `POST /api/extensions/ontology/actions/invoke`（双层授权 + `ActionError`→HTTP）；`app/auth.py` 增 `authorize` / `fetch_scope_rule` / `resolve_actor_role`；**节首硬性验收项闭合**：`middleware.resolve_data_scope` 抽为数据范围判定的唯一实现，`/scope` 与 `with_data_scope` 共用；**写路径命令阶段超时收口**（`command_timeout=60`，翻转 Task 5 的"缺席"钉子） | +21 | `77c7bbceb` → `31e5af471` → `a61db4c16` |

**全量基线：`384 passed, 3 skipped`**（`ontostudio/backend`，用 `PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest tests/ -q`；**系统 Python 3.14 缺 owlrl，必须用仓内 `.venv`**）。`ruff check .` 全绿；`ruff format --check .` 有 1 个既有未格式化文件 `app/auth.py`（Task 7 改动后**仍是同一处**：`/api/permissions/me -> %d` 那行 logger 调用，只是从 `_gateway_authorizes` 挪进了新抽出的 `_gateway_me`；**不属任何 Task 范围，别动**）。

**Task 3 顺带修掉的坑（后续 Task 会受益）**：ontostudio 现在**自己**在 lifespan 里建表（`app/db.py::ensure_tables`）——gateway **不挂载也不建** `dg_*` 表，2026-09-17 独立服务搬迁后的注释曾长期与此不符。`/health` 现在带 `tables_ready` 字段（**状态码恒 200**，是否据此判不健康是待定的运维决策）。**残余风险**：`create_all` 只建缺失表、不做 schema 变更；建表失败只留 WARNING，且启动**只尝试一次**——`dg_action_audit` 的「DB 后起」缺口已由**写路径懒建**兜住（Task 5 Step 6，有界 + 只对 42P01），其余 `dg_*` 表仍要靠重启补建。

**下一步：Task 8（MCP 暴露面）**。Task 7 已完成并规格审查通过，见上表。

**Task 7 闭合的三件事（供后手引用，勿重复发现）**：

1. **节首硬性验收项已闭合**：`middleware.resolve_data_scope` 是数据范围判定的唯一实现，`/scope` 与 `with_data_scope` 共用；超管旁路与 `deny_data_scopes` 扣减都在里面。**一处有意的行为变更**：超管 + 未知 resource 由 `none_allow` 变 `allow_all`（理由见 spec §3.1 的闭合块）。判据：`tests/test_permissions_scope_endpoint.py` 里 4 条两侧一致性用例，且**相等断言与绝对值断言各抓一类错**——删掉共用判定里的旁路/deny 扣减时**只有绝对值断言会红**（变异实测 M2/M3），别把它们当装饰。
2. **审计行 `actor_role` 写的是角色 code，不是显示名**（偏离计划 Step 3 的 `user.role_name`）。三个理由，最硬的是第二个：`CurrentUser.role_name` 只可能来自 JWT claims，而 gateway 签发的 Cookie claims 是 `{sub, exp, iat, ver}`（无角色）——**计划那行会给每一条真实浏览器审计行写 NULL**。取法：`app.auth.resolve_actor_role` 问 gateway `/me` 的 `identity.role_code`（与 `/scope` 同源）；失败 → `None`，**不拒动作**。
3. **`_project_incrementally` 仍是全量 `refresh()`**（P1-7 才收敛），但**代价已实测写进其 docstring**。⚠️ **别引用速率**：初版写的「约 0.8 ms/三元组」是**错的**（那次 benchmark 的 relations 用了 `locatedIn`，而 eia 的 enum 里是 `located_in`——关系全没落地，分母算小了），第二版给的表也**不可复现**（质量审查者按同一路径实测 1 000 实体 940 ms，实现者本机 2 341 ms，差 2.5×）。现行 docstring 给的是**带测量条件的量级表**（100/500/1 000/2 000/5 000 实体 → 375 ms / 1.4 s / 2.3 s / 4.6 s / 12.2 s，含三元组计数）并**明写"只作量级、勿外推"**：增长至少线性、已见超线性（2.5× 实体 → 2.65× 时间；审查者同区间 4.1×）。定向结论：**千级 ≈ 秒级、数千级 ≈ 十秒级**，且它**同步占住事件循环**——判据是"并发量 × 规模"，**千级实体起就该催 P1-7**。**它是同步函数**（executor 同步调用；写成 `async def` 会静默 `projected=True`），`tests/test_actions_rest.py` 有两条用例钉住（同步性 + 异常不吞）。

**Task 6 留下的两件（一件已闭、一件仍在）**：
1. **`reviewer`（审核员）角色什么都没拿到**——`ontology:action:review` 与 `ontology_all` 目前只授给 `superadmin`。符合计划字面（"至少 admin 与 superadmin"，而 **`admin` 角色不存在**），但语义上"审核员不能审核"。**要动 `roles_custom.yaml` overlay（base yaml 对它是整体替换，改了无效），属权限模块的产品决策。** ⚠️ **Task 10 验收 §4「有操作权限但不带 `ontology_all` → 404」目前没有可用于该场景的角色——这是会撞上的前置缺口。**（Task 7 的两侧一致性用例用 overlay 现造了一个非超管持 `ontology_all` 的角色，可作模板。）
2. ~~**`/scope` 不是平台数据范围判定的忠实投影**~~ → **已由 Task 7 闭合**（`31e5af471`），见上。

> **本节两处已在本轮订正（原为过期陈述，勿再引用旧文）**：
> - ~~「写路径的引擎没有任何阶段超时」~~ → **握手阶段已收口**（`connect_args={"timeout": 5}`，`8049e7c6d`）；**命令阶段也已收口**（Task 7，`command_timeout=60`，见下）。理由与代价见 `app/db.py` 末尾的缺口注释。
>
> **⚠️ 命令阶段那一半的归属链（Task 7 补记）**：本行原文写「命令阶段仍有意不收口…**留给 Task 7 的暴露面裁决**」，spec §1.2.2 的表格写「留 Task 6/7 裁决」，`app/db.py` 末尾也写「仍未收口，留给 Task 6/7」→ **Task 6 是 gateway 侧的，没做；而 Task 7 本节也一个字没提**。这是本计划**第六次**"凡写下'那是 X 的范围'，却没同时改 X 的步骤"。**Task 7 已裁定并实装**：写路径引擎加 `command_timeout=_WRITE_COMMAND_TIMEOUT_S=60`（`ontostudio/backend/app/ontology/actions/executor.py`），并把 Task 5 那条「断言 `command_timeout` 缺席」的测试**翻转**成正向断言 + 一条 `!=` 反向断言（挡"顺手统一成同源"）。取 60 而非 30 的理由：两条路径的**误杀面**不同（建表那边 ≈ 一条 WARNING，写路径是用户可见的 500），而唯一合法的长等待是 `FOR UPDATE` 撞并发写同一行——单行审核动作的竞争写者应为毫秒级，60s 已比"排队"宽两个数量级。顺带修掉一处只有一个线索却是空串的 detail：`str(TimeoutError())` 是空串，收口后这条路径设计上可达，故 `_write_failure_detail` 特判它（新增 1 条测试钉住）。
> - ~~「`ontology` 模块仍是 `data_scopes: []`」~~ → **Task 6 已补 `ontology_all`**（`rule_template: {}`，空模板＝全量），并授给 `superadmin`；端点已实测返回 `allow_all`。

**Task 6 的两件删除（本轮新造、又被本轮自己的修复淘汰，故删）**：`authz_cache.py`（计划 Step 4(b) 的前提是**事实错误**——主仓根本没有那个模块级 `_authz_cache`；且"将来接上真路径"大概率是**语义变更**而非接线：会给平台引入进程级 30s 缓存＝权限吊销延迟 30s）与 `AttributeSet.from_current_user`（I-3 改用正典 `resolve()` 后零调用点零测试）。**两处均经"删除前后同一条命令逐条对比"确认无测试变红**——那是"零消费者"的第二个证明。

> **上面两条在本轮已被上方的「Task 6 留下的两件（一件已闭、一件仍在）」取代并去重**（原文保留在 git 历史里即可，勿在正文留两处同义陈述——一处说"已裁定不是遗漏"、一处说"已闭"会让人以为两件事）。

**Task 10 收口（2026-09-24）——四件后手必须知道的**：

1. **🔴 spec §2 步骤 5「受影响行增量重投影进内核图」是空转**（本计划唯一未实装的管线步骤）。`routers._project_incrementally` → `get_kernel().refresh()`，而 `refresh()`（`kernel/service.py`）只做 **schema 重编 + 闭包 + 规则重跑，从不读 `dg_*` 行**；只有 `POST /formal/load`（`kernel/loader.py::load_doc_graph_rows`）才把行装进断言图。后果：一次 confirm 之后 DB 行已 `active`、接口回 `projected: true`、`errors: []`，而**断言图里没有这一行**（本机与活容器双向实测：`POST /formal/load` 前后导出 `graphs=asserted` 对比，前者无该 IRI、后者有且 `status="active"`）。`_project_incrementally` 的 docstring 只承认"**非**增量"，**没承认根本没投影**——那句话本身也需要订正。**修复位置不在 Task 10 范围**（本 Task 不改 Task 1–9 产物），故已用 `tests/test_actions_e2e.py::test_03_action_projection_does_not_reach_the_graph_KNOWN_GAP` **钉住现状**：实装步骤 5 后该用例会变红，**届时删掉它**。
2. **验收 ① 的 SHACL 半边不能由计划给的那行断言证明**：`kernel/conformance._c3_shacl_report_shape` 只校验报告**形态**（五字段齐备），`conforms=False` 时照样 `passed=True`（实测：图里塞一个 `status='bogus_status'` 的实体 → `run_shacl().conforms is False`、1 条违规，而 `all(c.passed ...)` 仍为**真**）。故 e2e 文件直接断言 `run_shacl(...).conforms`，且断言对象是**装了这一行的隔离图**（计划那行对 `get_kernel().store` 求值，那在本进程里是另一回事——见 1）。
3. **Task 10 Step 3 的 `restart` 不足以做"真人路径验证"**：`ontostudio-backend` **不 bind-mount 代码**（compose 只挂 kernel 卷），镜像烘焙 `COPY app ./app`；验收时实测活容器**连 `app/ontology/actions/` 目录都不存在**（`/openapi.json` 无 `actions/invoke`，21 条路由）。正确步骤是 `docker compose -p eai-docker -f docker-compose-dev.yaml build ontostudio-backend && ... up -d ontostudio-backend`（deps 层有缓存，实测秒级）。另：Step 3 里那条 `docker exec ... get_kernel().refresh()` 会撞 pyoxigraph 的 `/data/kernel/LOCK`（**服务进程持锁**）——本轮重建后偶然可取，**不可依赖**；等价物是 `POST /formal/infer` 与 `GET /formal/validate`（HTTP 面）。
4. **验收 §4 已闭合，且不必动角色模型**：`config/permissions.yaml` 只把 `ontology:action:review` 与 `ontology_all` 给了 `superadmin`（旁路），故 §4 需要的"有操作权限但不带 `ontology_all`"**在角色维度确实不存在**。解法**不是**新建角色（那属权限模块的产品决策，见上「Task 6 留下的两件」），而是走平台自己的 **ABAC 策略**：`POST /api/policies`，`conditions={attr:user_id, op:eq, value:<user>}`、`grants={permissions:["ontology:action:review"]}`——`/me` 会把 policy grant 并进 `permissions`（`UnifiedPermissionEngine.list_permissions`），而该用户角色（`user`）本就不带 `ontology_all` → `/scope?resource=ontology` 回 `none_allow` → 动作 **404（非 403）**。实测：同一用户同一请求，授权前 `403 {"detail":"缺少权限：ontology:action:review"}`、授权后 `404 {"detail":"目标不存在或不在可见范围内"}`。**⚠️ 测这条必须等 >30s**：`app/auth.py` 的 `_authz_cache` 按 `(user_id, permission)` 缓存 30s，短于它只会拿到缓存里的旧 403（本轮踩过：32s 不够、45s 稳）。

**Task 5 遗留、仍需在后续处理的两件**（该实现者本轮提醒）：① Task 8 的 `_ok()` 用 `json.dumps` **无 `default=str`**，而 `after` 现在可能带 `datetime`（Task 5 改用 `RETURNING` 的连带）——**已写进 Task 8 节**；② `test_permissions_scope_endpoint.py` 里"（Task 6 产物）"那句标注。

**Task 5 开工前必须知道的三件事**（前四个 Task 的审查反复确认过；**对每个 Task 同样成立**）：

1. **本计划所有代码块都不是 format-clean 的**（Task 1–2 已出现 5+ 例）。跑 `ruff format` 是本任务常规步骤，不是偏离；但**仍要在偏离清单里如实计入**。
2. **`schemas.py` / `registry.py` 是 CRLF，`scope.py` 与 `tests/*.py` 是 LF。** 用脚本改注释时多行锚点会**静默不匹配**——改完必须 `git diff` 确认真改到了，且**别把 CRLF 文件改成 LF**。
3. **每个 Task 的 Verify 必须跑 `ruff format --check`**，不能只跑 `ruff check`——ontostudio 没有 Makefile，主仓 `make lint` 是两条命令的组成，只搬命令名会漏掉排版。

**Task 3 特有的前置约束（Task 2 的校验会拦你）**：

- 新动作的 `action.domain` **必须与 target 对象类型的 `domain` 一致**（Task 2 的 M-2 校验），否则加载直接报 `domain ... 与 target 所属域 ... 不一致`。
- `status` 加 `rejected` **必须三处同步**：`kernel/validate.py` 的 `Literal(...)`、同文件的提示文案、以及 `doc_graph.yaml` 里 `status` 属性的 `enum`。**漏一处 SHACL 会当场判违规。**
- `graph_entity` 要加 `scope_resource: ontology`——但**别忘 `config/permissions.yaml` 的 `ontology` 模块当前是 `data_scopes: []`**（Task 6 才补 `ontology_all`）。Task 3 只加 YAML 声明，**那时 `scope_resource` 会解析为 `none_allow`，属预期**，不是 bug。

**执行方式**：`docs/superpowers/plans/` 本计划 + `superpowers:subagent-driven-development`（每个 Task 派全新实现者 → 规格审查者 → 代码质量审查者 → 修正 → 复审）。**派发提示里必须带上本计划开头的「派发给实现者的通用要求」与「审查方法学：变异检验的合法手法」两节**——Task 1–2 的经验表明这两节直接决定审查能否抓到真问题。

**未纳入本计划**（spec §4 的折叠步）：`merge_entities` / `unmerge` 折叠为动作、删除旧实现。必须**另起计划**，且在本计划全部 Task 绿之后才能开工。

---

## Task 1: `scope.py` —— FilterRule 与 SQL 编译

**Files:**
- Create: `ontostudio/backend/app/ontology/scope.py`
- Test: `ontostudio/backend/tests/test_scope_rule_to_sql.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_scope_rule_to_sql.py
"""FilterRule → 参数化 WHERE 编译。安全要点：字段名走标识符白名单，值一律绑定。"""
import pytest

from app.ontology.scope import FilterRule, ScopeCompileError, rule_to_sql


def test_allow_all_compiles_to_true():
    assert rule_to_sql(FilterRule(operator="allow_all")) == ("TRUE", {})


def test_none_allow_compiles_to_false():
    assert rule_to_sql(FilterRule(operator="none_allow")) == ("FALSE", {})


def test_eq_binds_value_not_interpolates():
    sql, params = rule_to_sql(FilterRule(operator="eq", field="dept_id", value="d1"))
    assert sql == '"dept_id" = :scope_0'
    assert params == {"scope_0": "d1"}


def test_in_uses_any():
    sql, params = rule_to_sql(FilterRule(operator="in", field="id", value=["a", "b"]))
    assert sql == '"id" = ANY(:scope_0)'
    assert params == {"scope_0": ["a", "b"]}


def test_overlap_uses_array_operator():
    sql, _ = rule_to_sql(FilterRule(operator="overlap", field="dept_ids", value=["a"]))
    assert sql == '"dept_ids" && :scope_0'


def test_and_or_not_nest_with_parens():
    left = FilterRule(operator="eq", field="a", value=1)
    right = FilterRule(operator="eq", field="b", value=2)
    sql, params = rule_to_sql(FilterRule(operator="or", children=[left, right]))
    assert sql == '("a" = :scope_0 OR "b" = :scope_1)'
    assert params == {"scope_0": 1, "scope_1": 2}

    sql, _ = rule_to_sql(FilterRule(operator="not", children=[left]))
    assert sql == 'NOT ("a" = :scope_0)'


def test_bindings_override_physical_column():
    sql, _ = rule_to_sql(
        FilterRule(operator="eq", field="user_id", value="u1"),
        bindings={"user_id": "created_by"},
    )
    assert sql == '"created_by" = :scope_0'


def test_unbound_field_raises():
    with pytest.raises(ScopeCompileError, match="unbound"):
        rule_to_sql(FilterRule(operator="eq", field="user_id", value="u1"), bindings={})


@pytest.mark.parametrize("bad", ['a"; DROP TABLE x --', "a b", "1col", ""])
def test_illegal_identifier_rejected(bad):
    """注入用例：字段名不走值绑定，必须走白名单。"""
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field=bad, value=1))


def test_wire_roundtrip():
    rule = FilterRule(
        operator="or",
        children=[
            FilterRule(operator="eq", field="a", value=1),
            FilterRule(operator="allow_all"),
        ],
    )
    assert FilterRule.from_wire(rule.to_wire()) == rule


def test_none_allow_means_all_fields_none():
    r = FilterRule.from_wire({"operator": "none_allow"})
    assert r.operator == "none_allow" and r.field is None and r.children is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_scope_rule_to_sql.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.scope'`

- [ ] **Step 3: 实现**

> **⚠️ 下方代码块是初版，已作废。** 两阶段审查修正了 5 处，其中一处是**与网关判定相反的 fail-open**（空 `and`/`not` 曾编译成 `TRUE`，放行全域；网关对同一棵树判 deny）。
> **权威实现是文件本身**：`ontostudio/backend/app/ontology/scope.py`（33 条测试守着）。修正清单见本 Task 末尾的「审查裁定引入的偏离」表。
>
> **不要照抄下面的代码块。** 后续 Task 只依赖这三个**未变更**的接口：
> ```python
> class FilterRule:            # 字段：operator / field / value / children
>     def to_wire(self) -> dict: ...
>     @classmethod
>     def from_wire(cls, data: dict) -> "FilterRule": ...
> class ScopeCompileError(ValueError): ...
> def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict]: ...
> ```
> **行为差异须知**：空 `and`/`not` 现在 **raise** 而非返回 `TRUE`；`in`/`not_in` 的裸字符串按单元素集合处理；畸形 wire 一律抛 `ScopeCompileError` 而非 `KeyError`/`TypeError`。

```python
# ontostudio/backend/app/ontology/scope.py
"""数据范围规则树：wire 编解码 + 编译为参数化 SQL WHERE。（初版，见上方警告）

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
FilterRule 的字段形态**对齐** gateway backend/app/extensions/auth/engine.py::FilterRule——
两侧各自持有数据类（OntoStudio 是独立服务，无法 import app.*），wire 用同名字段。
gateway 侧字段或算子变更时，此处必须同步。

安全：字段名不经值绑定，故走标识符白名单 + 加引号；任何值一律命名参数绑定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# 叶子算子 → SQL 模板（{c}=列占位，{p}=参数占位）
_LEAF_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "overlap": "{c} && {p}",
}


class ScopeCompileError(ValueError):
    """规则树不合法（未知算子 / 未绑定字段 / 非法标识符）。"""


@dataclass
class FilterRule:
    operator: str = "none_allow"  # allow_all|none_allow|and|or|not|eq|ne|in|not_in|overlap
    field: str | None = None
    value: Any = None
    children: list["FilterRule"] | None = None

    def to_wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "FilterRule":
        return cls(
            operator=data["operator"],
            field=data.get("field"),
            value=data.get("value"),
            children=[cls.from_wire(c) for c in data["children"]] if data.get("children") else None,
        )


def _quote(field_name: str, bindings: dict[str, str] | None) -> str:
    """把模板字段名解析为物理列名并加引号。

    ``bindings=None`` 表示不做映射（恒等：模板字段名即列名）；
    ``bindings={...}`` 表示显式映射表——此时**每个**字段都必须命中，未命中即报错。
    两者语义不同（None=恒等，{}=全未绑定），这是刻意的：显式映射下静默退回恒等会让
    registry 里漏配的 scope_bindings 变成"看起来能用"的越权读，故宁可直接失败。
    """
    if bindings is None:
        physical = field_name
    else:
        if field_name not in bindings:
            raise ScopeCompileError(f"unbound field in scope bindings: {field_name!r}")
        physical = bindings[field_name]
    if not _IDENT.match(physical):
        raise ScopeCompileError(f"illegal identifier for scope field {field_name!r}: {physical!r}")
    return f'"{physical}"'


def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict[str, Any]]:
    """编译为 (WHERE 片段, 命名参数)。bindings=None 表示不做字段名映射（恒等）。"""
    params: dict[str, Any] = {}
    counter = [0]

    def walk(node: FilterRule) -> str:
        op = node.operator
        if op == "allow_all":
            return "TRUE"
        if op == "none_allow":
            return "FALSE"
        if op in ("and", "or"):
            kids = node.children or []
            if not kids:
                return "TRUE" if op == "and" else "FALSE"
            joiner = " AND " if op == "and" else " OR "
            return "(" + joiner.join(walk(k) for k in kids) + ")"
        if op == "not":
            kids = node.children or []
            if not kids:
                return "TRUE"
            return "NOT (" + walk(kids[0]) + ")"
        if op in _LEAF_SQL:
            if node.field is None:
                raise ScopeCompileError(f"operator {op!r} requires a field")
            key = f"scope_{counter[0]}"
            counter[0] += 1
            params[key] = node.value if op not in ("in", "not_in") else list(node.value or [])
            return _LEAF_SQL[op].format(c=_quote(node.field, bindings), p=f":{key}")
        raise ScopeCompileError(f"unknown operator: {op!r}")

    return walk(rule), params
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_scope_rule_to_sql.py -v`
Expected: PASS（13 项）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/scope.py ontostudio/backend/tests/test_scope_rule_to_sql.py
git commit -m "feat(ontostudio): 数据范围规则树编译(FilterRule → 参数化 WHERE)"
```

### 审查裁定引入的偏离（2026-09-22，两阶段审查后）

本任务的字面代码块**已被审查裁定修改**，后续读者以实际代码为准：

| 处 | 计划字面 | 实际 | 裁定理由 |
|---|---|---|---|
| `_quote` 的 `bindings` 语义 | `(bindings or {}).get(f, f)` | `bindings is None` → 恒等；否则**未命中即报错** | 计划原文在 `bindings={}` 时静默退回恒等，**通不过计划自己的 `test_unbound_field_raises`**；且那是一个真实 fail-open（registry 漏配 `scope_bindings` → 静默越权读） |
| 空 `and` / 空 `not` | `TRUE`（放行全域） | **`raise ScopeCompileError`** | 网关参考实现 `engine.py:99-129` 对同一棵树判 **deny**——两侧相反且静默。`allow_all` 有独立算子，空复合式无合法含义，拒绝它不会让任何合法规则回归。空 `or` 保持 `FALSE`（本就同向） |
| `in` / `not_in` 的 value | `list(node.value or [])` | **仅当 `op in ("in","not_in")` 时**先特判 `str` → `[str]`，再 `list(...)`；标量算子完全不归一 | 裸字符串会被按字符拆（`"abc"`→`['a','b','c']`），`in` 方向是**放宽**。特判不是新增语义，是复刻 `engine.py:52` 的既有语义（非 list 视为单元素集合）。**注意：审查者给的初版修法是无条件特判 `str`，那会把 `eq` 的标量值也包成列表、打破规格原有的 `test_eq_binds_value_not_interpolates`——实现者收窄了范围，是对的。** |
| `from_wire` / `_quote` 的输入校验 | 直接索引与 `match` | 缺键/非 str/非 dict/`children` 非 list 一律归一为 `ScopeCompileError`；标识符用 `fullmatch` | 原实现下 `KeyError`/`TypeError`/`AttributeError` 会逃出模块声明的错误类型，Task 5 映射错误码时会变 500。`fullmatch` 顺带堵住 `$` 锚点容许尾部换行。`children` 类型校验属实现者自主延伸（同一漏检类，经复审确认不误伤 `children: null` 这一合法形态） |
| `not` 的多余子节点 | 静默取 `children[0]`，其余丢弃 | `raise`（`not expects exactly one child, got N`） | 安全过滤器上静默丢弃输入不可接受；与 `_quote`「宁可直接失败」的姿态一致 |
| `ne` / `not_in` 测试 | 无 | 各补 1 条 | 安全相关算子零覆盖，手工探针不是回归护栏 |

**未采纳**：`not_in` 空集守卫（修复位置定在 gateway 解析层，见 spec §9 风险表）；`counter=[0]` 改 `nonlocal`（风格偏好）。

**本模块的安全属性已被审查者独立实测确认**（非"规格如此"）：SQL 文本中不存在任何调用方值的拼接路径；标识符白名单作用在**映射后的物理列名**上，不是只校验模板字段名。

---

## Task 2: registry 支持 `actions:` 段

**Files:**
- Modify: `ontostudio/backend/app/ontology/schemas.py`
- Modify: `ontostudio/backend/app/ontology/registry.py`
- Test: `ontostudio/backend/tests/test_actions_schema.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_schema.py
"""动作声明 schema + registry 加载路径。

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §1.1。
"""
from __future__ import annotations

import yaml
import pytest
from pydantic import ValidationError

from app.ontology.schemas import ActionSpec, DomainFile, StateChange


def _ot(api_name="graph_entity", domain="doc_graph"):
    return {
        "api_name": api_name, "display_name": "实体", "description": "d", "domain": domain,
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [
            {"name": "id", "api_name": "id", "type": "uuid", "description": "pk"},
            {"name": "status", "api_name": "status", "type": "string", "description": "s"},
        ],
    }


def _action(**over):
    base = {
        "id": "review_entity.confirm", "display_name": "确认实体", "description": "d",
        "domain": "doc_graph", "target": "graph_entity",
        "required_permissions": ["ontology:action:review"],
        "preconditions": [{"field": "status", "op": "eq", "value": "pending_review"}],
        "postconditions": [{"field": "status", "set": "active"}],
    }
    base.update(over)
    return base


def test_valid_domain_parses_with_actions():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action()]})
    assert d.actions[0].id == "review_entity.confirm"
    assert d.actions[0].behavior_type == "COMMAND"


def test_unknown_target_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(target="nope")]})
    with pytest.raises(ValueError, match="unknown action target"):
        d.validate_action_refs()


def test_unknown_field_rejected():
    d = DomainFile.model_validate({
        "object_types": [_ot()],
        "actions": [_action(postconditions=[{"field": "nosuch", "set": 1}])],
    })
    with pytest.raises(ValueError, match="unknown action field"):
        d.validate_action_refs()


def test_empty_postconditions_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(postconditions=[]))


def test_illegal_op_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(preconditions=[{"field": "status", "op": "drop", "value": 1}]))


def test_set_and_now_mutually_exclusive():
    with pytest.raises(ValidationError, match="set 与 now"):
        ActionSpec.model_validate(_action(postconditions=[{"field": "status", "set": "x", "now": True}]))


def test_required_permissions_must_not_be_empty():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(required_permissions=[]))


def test_duplicate_action_id_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(), _action()]})
    with pytest.raises(ValueError, match="duplicate action id"):
        d.validate_action_refs()


def test_neither_set_nor_now_rejected():
    """互斥是「二选一」而非「至多一个」：两者同时缺省同样拒绝。

    （计划初稿只测了「同时给出」这一半；`self.now == (self.set is not None)`
    在两者皆缺省时同样为 True，是真分支，必须钉住另一半。）
    """
    with pytest.raises(ValidationError, match="set 与 now"):
        StateChange.model_validate({"field": "status"})


def test_scope_bindings_must_reference_declared_property():
    ot = _ot()
    ot["scope_resource"] = "ontology"
    ot["scope_bindings"] = {"user_id": "nosuch_column"}
    d = DomainFile.model_validate({"object_types": [ot], "actions": []})
    with pytest.raises(ValueError, match="unknown scope binding"):
        d.validate_action_refs()


# ── Registry 加载路径 ────────────────────────────────────────────────────────
# 为什么需要这一组：真实 registry 的 YAML 到 Task 3 才会有 actions: 段，所以
# 全量测试里 RegistryStore 的 `for a in domain.actions:` 循环体一次都不执行——
# 即本任务声称的「核心」（按 id 索引的动作字典 + 跨文件重复守卫）在提交的测试里
# 零覆盖。用临时 registry 目录把它钉住，而不是靠一次性脚本。

def _write_registry(tmp_path, files: dict[str, str]):
    """最小 registry 目录：manifest + 各域文件。"""
    (tmp_path / "_manifest.yaml").write_text(
        "schema_version: 2\nhot_reload: true\nfiles:\n" + "".join(f"  - file: {n}\n" for n in files),
        encoding="utf-8",
    )
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_registry_exposes_actions_by_id(tmp_path):
    d = _write_registry(tmp_path, {
        "a.yaml": yaml.safe_dump({"object_types": [_ot()], "actions": [_action()]}, allow_unicode=True),
    })
    from app.ontology.registry import RegistryStore

    reg = RegistryStore(registry_dir=d).get()
    assert reg.get_action("review_entity.confirm").target == "graph_entity"
    assert reg.get_action("nope.nope") is None


def test_cross_file_duplicate_action_id_rejected(tmp_path):
    """跨文件重复由 RegistryStore 的合并循环兜住（文件内的由 validate_action_refs 兜）。

    两个域各自声明**不同**对象类型（否则会先在对象类型重复注册处报错），
    但动作 id 相同——必须报「动作 id 跨域重复」。
    """
    d = _write_registry(tmp_path, {
        "a.yaml": yaml.safe_dump({
            "object_types": [_ot(api_name="graph_entity")],
            "actions": [_action(id="dup.check", target="graph_entity")],
        }, allow_unicode=True),
        "b.yaml": yaml.safe_dump({
            "object_types": [_ot(api_name="graph_entity2")],
            "actions": [_action(id="dup.check", target="graph_entity2")],
        }, allow_unicode=True),
    })
    from app.ontology.registry import RegistryError, RegistryStore

    with pytest.raises(RegistryError, match="动作 id 跨域重复"):
        RegistryStore(registry_dir=d).get()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_schema.py -v`
Expected: FAIL —— `ImportError: cannot import name 'ActionSpec'`

- [ ] **Step 3: 实现 —— `schemas.py` 追加**

在 `ontostudio/backend/app/ontology/schemas.py` 末尾（`DomainFile` 之前）插入：

```python
class Precondition(BaseModel):
    """动作前置条件：只允许「列 op 字面量」——不做表达式求值。

    EAI-CUSTOM: 设计 §1.1。对标 M2 行为模型的谓词语法，收窄到可静态校验的子集。
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    op: Literal["eq", "ne", "in", "not_in", "is_null", "not_null"]
    value: Any | None = None


class StateChange(BaseModel):
    """动作后置：受影响列的新值。set 与 now 互斥。"""

    model_config = ConfigDict(extra="forbid")

    field: str
    set: Any | None = None
    now: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> StateChange:  # 不加引号：本文件已有 from __future__ import annotations，引号会触发 ruff UP037
        if self.now == (self.set is not None):
            raise ValueError(f"{self.field}: set 与 now 必须二选一（不可同时给出或同时缺省）")
        return self


class ActionSpec(BaseModel):
    """注册表动作声明（设计 §1.1）。本期只支持 COMMAND。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    domain: str
    target: str  # ObjectType.api_name
    behavior_type: Literal["COMMAND"] = "COMMAND"
    required_permissions: list[str] = Field(min_length=1)
    preconditions: list[Precondition] = Field(default_factory=list)
    postconditions: list[StateChange] = Field(min_length=1)
    version: int = 1
```

把 `from pydantic import BaseModel, ConfigDict, Field` 改为
`from pydantic import BaseModel, ConfigDict, Field, model_validator`。

`ObjectType` 追加两个字段（放在 `etype_classes` 之后）：

```python
    # EAI-CUSTOM (动作层, 设计 §3): 数据范围归属——值取 permissions.yaml 的**模块 key**
    # （ontology / contract_price / spare_parts / bid_quote…），不是 scope id。
    scope_resource: str | None = None
    # 模板字段名 ≠ 本表列名时的覆盖；缺省恒等映射。
    scope_bindings: dict[str, str] | None = None
```

`DomainFile` 追加 `actions` 字段与校验方法：

```python
    actions: list[ActionSpec] = []

    @model_validator(mode="after")
    def _check_refs(self) -> DomainFile:
        """交叉引用校验。fail-closed：任一不满足即拒绝加载。

        分工边界（Task 2 质量审查 M-1）：**列引用**在本校验器；**`scope_resource` 的
        值域**（是否为已知权限模块 key）在 `scripts/ontology_lint.py`（Task 9）——
        别在这里以为漏了。

        不对称说明（M-4）：`actions.target` 只允许**同文件**解析，而 `link_types` 的
        source/target 允许跨文件前向引用（见 registry.py 的 pending 集）。这是有意的：
        动作要落到具体物理表，跨文件引用会让"哪个域拥有这条写路径"变得含糊。
        """
        by_api_name = {ot.api_name: ot for ot in self.object_types}
        props = {name: {p.name for p in ot.properties} for name, ot in by_api_name.items()}

        seen: set[str] = set()
        for a in self.actions:
            if a.id in seen:
                raise ValueError(f"duplicate action id: {a.id}")
            seen.add(a.id)
            if a.target not in by_api_name:
                raise ValueError(f"unknown action target: {a.target!r} (action {a.id})")
            # 域一致性（Task 2 质量审查 M-2，**超出设计 §1.1 三类校验的范围外补强**）：
            # action.domain 会被写进 dg_action_audit.domain，而同行表名来自 target 对象。
            # 两者不一致会产出"domain 与表对不上"的审计行，而审计是这条链路唯一的追溯凭据。
            target_domain = by_api_name[a.target].domain
            if a.domain != target_domain:
                raise ValueError(f"action {a.id}: domain {a.domain!r} 与 target 所属域 {target_domain!r} 不一致")
            declared = props[a.target]
            for cond in list(a.preconditions) + list(a.postconditions):
                if cond.field not in declared:
                    raise ValueError(f"unknown action field: {cond.field!r} on {a.target} (action {a.id})")

        for ot in self.object_types:
            declared = props[ot.api_name]
            for template_field, physical in (ot.scope_bindings or {}).items():
                if physical not in declared:
                    raise ValueError(f"unknown scope binding: {template_field}->{physical} on {ot.api_name}")
```

- [ ] **Step 4: 在 registry.py 加载后调用校验**

把 `ontostudio/backend/app/ontology/registry.py:69-74` 的 `_validate_domain_file` 整体改为：

```python
def _validate_domain_file(path: Path, data: dict) -> DomainFile:
    try:
        return DomainFile.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in err.get("loc", ()))
        raise RegistryError(f"schema 校验失败: {path.name}: {f'{loc}: ' if loc else ''}{err.get('msg', e)}") from e
```

（**原版是两个 try**——第二个专门包 `validate_action_refs` 抛的 `ValueError`。经 Task 2 质量审查裁定改为 `model_validator(mode="after")` 后，该校验并入 `model_validate` 的 `ValidationError`，第二个 try 整块删除。那个被删掉的包装本身**零测试保护**：审查者实测把它整块删掉，264 条测试照样全绿。）

注意三点：

1. **`f'{loc}: ' if loc else ''` 是必需的，不是美化**：pydantic 根级 after-validator 的 `e.errors()[0]["loc"]` 是**空 tuple**，照原样拼会渲染出 `a.yaml: : Value error, ...`（两个冒号）。审查者实测确认。
2. (c) 的跨文件守卫与模型内的文件内查重是**两件事**，别只做一半：文件内重复由 `_check_refs`（模型校验器）挡，跨文件重复由 `RegistryStore` 的合并循环挡。两者各有测试（`test_duplicate_action_id_rejected` 与 `test_cross_file_duplicate_action_id_rejected`）。**跨文件重复的报错不受模型校验器改动影响**——它从不在模型里。
3. **不要再引入"须显式调用的公开校验方法"**。本仓既有模式是 `model_validator(mode="after")`（对照 `app/doc_graph/schemas.py:154` 的 `ExtractionPayload._check_domain_and_refs`，其测试在 `model_validate` 处断言 `ValidationError`）。计划初稿的 `validate_action_refs()` 公开方法**在本仓没有先例**，且它立的"只允许经 `_validate_domain_file` 解析"约定会被本计划后面自己的 Task 9/10 代码绕过（那两处的 `DomainFile.model_validate(...)` 是直接调用）。

**同一文件还需让 `Registry` 承载动作**——`Registry` 是合并快照，**不保存 per-domain 的 `DomainFile`**（`__init__` 只有 `object_types` / `link_types` 两个合并字典），所以不能遍历 domain 找动作。照 `object_types` 的样子加一个合并字典：

(a) `Registry.__init__`（L31-48）追加参数与属性（放在 `formal_by_domain` 之后，保持既有参数顺序不动）：

```python
        actions: dict[str, ActionSpec] | None = None,
```
```python
        self.actions = actions or {}
```

同文件顶部 import 改为 `from app.ontology.schemas import ActionSpec, DomainFile, FormalSection, LinkType, Manifest, ObjectType`。

(b) 追加访问器（放 `Registry.__init__` 之后。**注意：`get()` 在 `RegistryStore` 上，不在 `Registry` 上**——计划初稿说"与 `get()` 同层"措辞不准，实质指令以本行为准）：

```python
    def get_action(self, action_id: str) -> ActionSpec | None:
        return self.actions.get(action_id)
```

(c) 在 `RegistryStore` 的加载函数里汇总动作。**不要新起一遍遍历**——`registry.py:129` 已有第二遍循环 `for name, domain in parsed:`（`parsed: list[tuple[str, DomainFile]]` 在 L119，用 `_validate_domain_file` 产出），把动作合并**并进这个循环**：

```python
    objects: dict[str, ObjectType] = {}
    links: dict[str, LinkType] = {}
    # ...（既有局部变量不动）
    actions: dict[str, ActionSpec] = {}          # ← 新增

    for name, domain in parsed:
        # ...（既有 object_types / link_types 处理不动）
        for a in domain.actions:                  # ← 新增块，放在 link_types 循环之后
            if a.id in actions:
                raise RegistryError(f"{name}: 动作 id 跨域重复: {a.id}")
            actions[a.id] = a
        fingerprints[name] = _read_fingerprint(registry_dir / name)
        _check_cross_refs(registry_dir / name, objects, links, pending - set(objects))
```

**注意**：`validate_action_refs()` 已在 `_validate_domain_file` 内跑过（见上一步），它只挡**文件内**重复；**跨文件**重复由上面这个 `actions` 字典兜住。

(d) 把 L152-160 的 `Registry(...)` 调用补一个关键字参数（其余参数一个字不动）：

```python
    return Registry(
        manifest,
        objects,
        links,
        fingerprints,
        registry_version=manifest.registry_version,
        namespaces_by_domain=namespaces_by_domain,
        formal_by_domain=formal_by_domain,
        actions=actions,
    )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_schema.py -v`
Expected: PASS（**12 项**——计划初稿写 9 项，后补 `test_neither_set_nor_now_rejected` 与两条 Registry 加载路径测试，见 Step 1 末尾）

- [ ] **Step 6: 回归既有 registry 测试（确认没打坏加载）**

Run: `PYTHONPATH=. uv run pytest tests/ -k registry -v`
Expected: 全 PASS。若 `eia.yaml` 因 `validate_action_refs` 报错，说明旧文件里有非法绑定——按提示修 YAML，不要放宽校验。

- [ ] **Step 7: 提交**

```bash
git add ontostudio/backend/app/ontology/schemas.py ontostudio/backend/app/ontology/registry.py ontostudio/backend/tests/test_actions_schema.py
git commit -m "feat(ontostudio): registry 支持 actions 段 + 交叉引用校验"
```

### 审查裁定引入的偏离（2026-09-22，两阶段审查后）

本任务的字面代码块**已被审查裁定修改**，后续读者以实际代码为准：

| 处 | 计划字面 | 实际 | 裁定理由 |
|---|---|---|---|
| 校验的挂载方式 | 公开方法 `validate_action_refs()`，须显式调用 | **`@model_validator(mode="after") _check_refs()`** | 本仓既有模式就是后者（`app/doc_graph/schemas.py:154`），"公开方法须显式调用"**无先例**；且计划自立的"只允许经 `_validate_domain_file` 解析"约定会被本计划 Task 9/10 的代码立刻绕过。改完还闭合一个盲区：原 `registry.py` 里为 `ValueError→RegistryError` 写的包装**整块删掉 264 条测试全绿**（零保护），改后该包装消失、错误落回已被 `test_ontology_registry.py:65-77` 覆盖的分支 |
| 空 loc 的渲染 | `f"{loc0}: {msg}"` | `f"{loc}: " if loc else ""` 前缀条件化 | pydantic 根级 after-validator 的 `loc` 是空 tuple，照原样拼出 `a.yaml: : Value error`（双冒号）。审查者实测 |
| `action.domain` 一致性 | 不校验 | **加校验**（须与 target 所属域一致） | **范围外补强**，审查者 M-2：`domain` 会进审计行而表名来自 target，不一致会产出对不上的审计行，审计是唯一追溯凭据 |
| `-> "StateChange"` 的引号 | 带引号 | 去引号 | 文件已有 `from __future__ import annotations`，引号触发 ruff **UP037** |
| 测试 import 顺序 | `yaml` 在 `pytest` 前 | `pytest` 在前 | 触发 ruff **I001** |
| 测试文件头 | 无 docstring / 无 future import | 补齐 | 仓内测试文件惯例 |
| 测试数 | 9 项 | **12 项**（+`test_neither_set_nor_now_rejected`、+两条 Registry 加载路径、+若干变异补测） | 原 9 项漏了互斥校验"同时缺省"那一半；且 `Registry.actions`/`get_action`/跨文件守卫在初始测试里**零覆盖**（真实 YAML 到 Task 3 才有 `actions:` 段，合并循环一次都不执行） |

**未采纳**：`scope_bindings` 有而 `scope_resource` 缺省时的拒绝（M-3，兜底方向 fail-closed，非越权，记为后续项）；跨文件重复 id 的报错带上首次出现的文件名（M-5，需把 `actions` 换成 `dict[str, tuple[str, ActionSpec]]`，波及 `get_action`，不值当）；`actions` 改私有（M-6，与既有 `object_types`/`link_types` 同模式，不新增风险）。

**变异检验的结论请记住**：审查者用"删掉/放宽某段代码看测试是否变红"的方法，在初始 12 条测试里找到 **3 个盲区**——`id` 正则、`preconditions` 那一半校验、以及那个 fail-closed 包装。**这三条都已补测**。后续 Task 的审查者应沿用同一手法。

---

## Task 3: `dg_action_audit` 表 + `status` 加 `rejected`

**Files:**
- Modify: `ontostudio/backend/app/doc_graph/tables.py`
- Modify: `ontostudio/backend/app/ontology/kernel/validate.py:58,61`
- Modify: `ontostudio/backend/app/ontology/registry/doc_graph.yaml`
- **Modify: `ontostudio/backend/scripts/ontology_lint.py`** ← 计划初稿漏了（见 Step 4c）
- **Modify: `ontostudio/backend/app/db.py`** ← 计划初稿漏了（见下方「建表路径」）
- **Modify: `ontostudio/backend/app/main.py`** ← 同上
- Test: `ontostudio/backend/tests/test_action_audit_table.py`
- **Test: `ontostudio/backend/tests/test_ontology_lint.py`** ← 同上
- **Test: `ontostudio/backend/tests/test_kernel_p4.py`** ← 两条 SHACL 新用例放这里（与既有 `test_shacl_bad_status_violation_report` 同族成对；见 Step 4d）

> **⚠️ 本任务的真实范围比初稿大：初稿只写了「建表声明」，实测该表此前没有任何建表路径。** `dg_*` 模型在 2026-09-17 独立服务搬迁时已从 gateway 的 `Base` 摘到本地 `app.db.Base`，而 gateway **不挂载** `ontostudio/`、其 `Base.metadata` 里 `dg_*` 表为零、ontostudio 全仓 `create_all` 只出现在注释里从未被调用——**现存 4 张 `dg_*` 表是搬迁前建的**。计划与设计文档都逐字采信了那三处已成谎话的注释。
>
> **建表路径**：`app/db.py` 新增 `ensure_tables()`（`create_async_engine(_ext_url(), poolclass=NullPool)` + `await conn.run_sync(Base.metadata.create_all)`），由 `app/main.py` 的 lifespan 调用。**降级为非致命**（建表失败只留 WARNING，不阻断启动）——fail-closed 会用一个功能级缺口换整服务不可用，是错的轴。但**必须**配：连接超时（否则黑洞地址下 uvicorn 有 ~21s 不服务）、`/health` 就绪字段、以及设计文档里的降级契约。`create_all` **只建缺失表、不做 schema 变更**，列变更仍需人工迁移。

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_action_audit_table.py
"""审计表随 Base.metadata 注册 + status 枚举含 rejected。"""
from app.db import Base
from app.doc_graph.tables import DgActionAudit


def test_audit_table_registered_in_metadata():
    assert "dg_action_audit" in Base.metadata.tables


def test_audit_columns():
    cols = set(DgActionAudit.__table__.columns.keys())
    assert {
        "id", "action_id", "domain", "target_table", "target_pk",
        "actor_id", "actor_role", "params", "before", "after", "source", "created_at",
    } <= cols


def test_status_enum_includes_rejected():
    from pathlib import Path
    src = Path("app/ontology/kernel/validate.py").read_text(encoding="utf-8")
    assert '"rejected"' in src, "status 枚举未加 rejected——SHACL 会判拒绝后实体违规"


def test_registry_doc_graph_status_enum_includes_rejected():
    from pathlib import Path
    yaml_src = Path("app/ontology/registry/doc_graph.yaml").read_text(encoding="utf-8")
    assert "rejected" in yaml_src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_action_audit_table.py -v`
Expected: FAIL —— `ImportError: cannot import name 'DgActionAudit'`

- [ ] **Step 3: 加表（`tables.py` 末尾追加）**

```python
class DgActionAudit(Base):
    """动作审计（设计 §1.2）。业务状态与审计行同事务落库；图上的 MergeAudit 节点
    降级为本表的投影（属折叠步范围，本表先建）。

    EAI-CUSTOM: 本模块随 app/ontology/__init__.py 导入注册进 Base.metadata，
    由 ontostudio 自身 lifespan 的 ensure_tables()（app/db.py）建表。
    ⚠️ 初稿此处的「由 gateway 启动时的 create_all 建表」是错的——见 app/db.py 的说明。
    """

    __tablename__ = "dg_action_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(60), nullable=False)
    target_table: Mapped[str] = mapped_column(String(120), nullable=False)
    target_pk: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'api'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_dg_action_audit_target_created", "target_pk", "created_at"),
        Index("ix_dg_action_audit_actor_created", "actor_id", "created_at"),
    )
```

（若 `tables.py` 顶部未导入 `Index`，在同行的 sqlalchemy import 中补上。）

- [ ] **Step 4: 加 `rejected` 到 SHACL 枚举**

`ontostudio/backend/app/ontology/kernel/validate.py:58` 改为：

```python
    Collection(g, head, [Literal(v) for v in ("active", "pending_review", "merged", "rejected")])
```

`:61` 的提示改为：

```python
    _severity(g, ps, "status 必须是 active/pending_review/merged/rejected 之一")
```

`ontostudio/backend/app/ontology/registry/doc_graph.yaml` 中 `graph_entity` 的 `status` 属性 `enum` 追加 `rejected`（该行现为 L25 的 `enum: [active, pending_review, merged]`）；`scope_resource: ontology` 加在该 mapping 的**最后一个字段之后**（即 `properties` 列表之后）：

```yaml
    scope_resource: ontology
```

> **⚠️ 计划初稿此处写的是「同一对象的 `etype_classes` 块之后」——那个锚点不存在。** `graph_entity` **没有** `etype_classes` 块（全仓只有 `eia.yaml` 有）。照字面改会**静默不匹配**。以"该 mapping 的最后一个字段之后"为准。
>
> **只加 `graph_entity` 一个**，不要顺手加 `graph_relation`——设计 §3 提到两个对象类型，但那是 Task 6 的范围。

### Step 4c: 把新表加入 lint 白名单（**计划初稿漏了这一步**）

> **为什么必须做**：新表以 `dg_` 前缀落进 `scripts/ontology_lint.py` 的 D14 规则「市场域表须在 ontology 注册表登记」的射程，**不加白名单会让 3 条既有测试变红**（`test_all_checks_pass_on_real_registry` / `test_main_exit_zero` / `test_doc_graph_tables_registered`），报 `table dg_action_audit: 市场域表未在 ontology 注册表登记`。

该规则的语义是「**对外**的 `dg_*` 表必须登记；**内部审计表**豁免」——`WHITELIST_TABLES` 现已含 `dg_merges`（注释即「内部审计表, 永不对外暴露」）。`dg_action_audit` 按设计 §1.2 正是审计表：**只写不给读投影**，没有 `ObjectType` 可登记（设计 §4 的 MCP 面只有 `invoke_action` / `review_entity`，无任何审计读工具）。故加入 `WHITELIST_TABLES`。

**不要**改为把该表登记成 object type——那等于把内部审计表开成对外读模型，是一个没人要求过的数据暴露决策。

同时 `tests/test_ontology_lint.py::test_doc_graph_tables_registered` 把豁免集**硬编码**为 `- {"dg_merges"}`，需加上 `dg_action_audit`，并补一条 `assert "dg_action_audit" not in registered` 把「豁免 = 不登记」这个契约显式钉住。**保持显式、不要改成从 `WHITELIST_TABLES` 派生**——派生会让"有人把一个真·对外表塞进白名单"静默通过。

- [ ] **Step 4b: 声明两个动作（**计划初稿漏了这一步**）**

> **为什么在这里**：本计划的文件结构表写着 `doc_graph.yaml` 要"声明 `review_entity.confirm` / `.reject`"，但初稿**没有任何 Task 的步骤包含这段 YAML**。后果是 Task 5/7/8/10 全部依赖 `review_entity.confirm` 存在，而 `_resolve` 会抛 `unknown action` → 那四个 Task 的测试成片失败。**这是 Task 2 派发时"别加 actions 声明，那是 Task 3 的范围"那句话留下的悬空**——Task 3 没接住。在文件的**末尾**（`link_types` 段之后）追加顶层键 `actions:`：

```yaml
actions:
  - id: review_entity.confirm
    display_name: 确认实体
    description: 将待审抽取实体置为 active，同一事务内记审计
    domain: doc_graph
    target: graph_entity
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

**三条硬约束**（会被 Task 2 已落地的校验直接拦下）：

1. `domain: doc_graph` **必须与 `graph_entity.domain` 一致**——已核实该对象类型确为 `domain: doc_graph`。不一致会报 `action ... domain ... 与 target 所属域 ... 不一致`（Task 2 的 M-2 校验）。
2. `target: graph_entity` 必须是**同文件**已声明的 `ObjectType.api_name`（actions 不允许跨文件引用）。
3. `preconditions`/`postconditions` 的 `field` 必须是该对象类型的**已声明属性名**——这里是 `status`（L25 已声明）。

**并补一条测试**（否则"声明存在"本身没有护栏）：

```python
def test_real_registry_declares_review_actions():
    """真实 registry 已声明两个审核动作——Task 5/7/8/10 全靠它们。"""
    from app.ontology.registry import get_registry

    reg = get_registry()
    assert reg.get_action("review_entity.confirm") is not None
    assert reg.get_action("review_entity.reject") is not None
    assert reg.get_action("review_entity.confirm").target == "graph_entity"
```

（**注意**：这条测试会让 `Registry.actions` 从空字典变为非空——Task 2 里那两条用临时 registry 目录的测试不受影响，但如果你想给"真实 registry 的 actions 非空"写断言，放在这里。）

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_action_audit_table.py tests/test_kernel_p4.py tests/test_actions_schema.py -v`
Expected: 全 PASS（P4 是 SHACL 金测试，确认改枚举没打坏既有形状；`test_actions_schema.py` 确认新声明没触发 Task 2 的校验）

- [ ] **Step 6: 提交**

```bash
git add ontostudio/backend/app/doc_graph/tables.py ontostudio/backend/app/ontology/kernel/validate.py ontostudio/backend/app/ontology/registry/doc_graph.yaml ontostudio/backend/tests/test_action_audit_table.py
git commit -m "feat(ontostudio): dg_action_audit 表 + status 枚举加 rejected"
```

---

## Task 4: `sql_write.py` —— 写守卫

**Files:**
- Create: `ontostudio/backend/app/ontology/actions/__init__.py`
- Create: `ontostudio/backend/app/ontology/actions/sql_write.py`
- Test: `ontostudio/backend/tests/test_actions_sql_write.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_sql_write.py
"""动作写路径的 SQL 构造与守卫。安全要点：标识符走白名单+加引号，值一律绑定。"""

import pytest

from app.ontology.actions.sql_write import (
    WriteGuardError,
    build_precondition_where,
    build_update_set,
    quote_ident,
)
from app.ontology.schemas import Precondition, StateChange


def test_quote_ident_ok():
    assert quote_ident("status") == '"status"'


@pytest.mark.parametrize("bad", ['a"; DROP TABLE t --', "a b", "1a", "", "abc\n", None, 123])
def test_quote_ident_rejects(bad):
    """含 `"abc\\n"`（`$` 锚点容许尾部换行）、None 与非 str —— 白名单是本模块唯一的注入防线。"""
    with pytest.raises(WriteGuardError, match="identifier"):
        quote_ident(bad)


def test_precondition_eq():
    sql, params = build_precondition_where([Precondition(field="status", op="eq", value="pending_review")])
    assert sql == '"status" = :pre_0'
    assert params == {"pre_0": "pending_review"}


def test_precondition_is_null():
    sql, params = build_precondition_where([Precondition(field="valid_to", op="is_null")])
    assert sql == '"valid_to" IS NULL'
    assert params == {}


def test_precondition_in():
    sql, params = build_precondition_where([Precondition(field="status", op="in", value=["a", "b"])])
    assert sql == '"status" = ANY(:pre_0)'
    assert params == {"pre_0": ["a", "b"]}


def test_empty_preconditions_is_true():
    assert build_precondition_where([]) == ("TRUE", {})


@pytest.mark.parametrize(
    ("op", "value", "expect_sql", "expect_params"),
    [
        ("eq", "a", '"f" = :pre_0', {"pre_0": "a"}),
        ("ne", "a", '"f" <> :pre_0', {"pre_0": "a"}),
        ("in", ["a"], '"f" = ANY(:pre_0)', {"pre_0": ["a"]}),
        ("not_in", ["a"], 'NOT ("f" = ANY(:pre_0))', {"pre_0": ["a"]}),
        ("is_null", None, '"f" IS NULL', {}),
        ("not_null", None, '"f" IS NOT NULL', {}),
    ],
)
def test_all_six_operators_render_expected_sql(op, value, expect_sql, expect_params):
    """6 算子逐个钉住 SQL 文本与绑定形态——not_in 掉 NOT 即 fail-open（守卫放行本不该放的行）。"""
    assert build_precondition_where([Precondition(field="f", op=op, value=value)]) == (expect_sql, expect_params)


def test_preconditions_are_conjoined_with_and():
    """合取，不是析取——OR 会让复合前置条件"任一成立即放行"，是未授权状态迁移。"""
    sql, params = build_precondition_where([Precondition(field="status", op="eq", value="pending_review"), Precondition(field="tenant", op="ne", value="x")])
    assert sql == '"status" = :pre_0 AND "tenant" <> :pre_1'
    assert params == {"pre_0": "pending_review", "pre_1": "x"}


@pytest.mark.parametrize("empty", [None, []])
def test_in_empty_value_is_false(empty):
    """空集的「属于」没有行匹配 → 恒假（fail-closed），绝不产出恒真式。"""
    assert build_precondition_where([Precondition(field="status", op="in", value=empty)]) == ("FALSE", {})


@pytest.mark.parametrize("empty", [None, []])
def test_not_in_empty_value_is_rejected(empty):
    """「不在空集里」字面等于「全部」——漏填 value 若静默放行，前置条件形同不存在（fail-open）。"""
    with pytest.raises(WriteGuardError, match="empty value set for not_in"):
        build_precondition_where([Precondition(field="status", op="not_in", value=empty)])


@pytest.mark.parametrize("op", ["in", "not_in"])
@pytest.mark.parametrize("bad", ["rejected", 123, {"a": 1}])
def test_in_not_in_non_sequence_value_rejected(op, bad):
    """`list("rejected")` 会拆成字符 → 「not_in rejected」放行它声明要拦的那一行（fail-open）；
    标量则漏出裸 TypeError，不是本模块的错误契约（调用方 catch WriteGuardError 会放过它）。"""
    with pytest.raises(WriteGuardError, match="must be a list"):
        build_precondition_where([Precondition(field="status", op=op, value=bad)])


def test_identifier_check_is_order_independent():
    """畸形标识符不因它与空 in 的声明顺序而被漏检。"""
    with pytest.raises(WriteGuardError, match="identifier"):
        build_precondition_where([Precondition(field="s", op="in", value=[]), Precondition(field="bad ident", op="eq", value=1)])


@pytest.mark.parametrize("op", ["eq", "ne"])
def test_eq_ne_without_value_rejected(op):
    """`col = NULL` 恒不成立且 NULL 该写 is_null——静默容忍会让前置条件永不满足、动作永不触发。"""
    with pytest.raises(WriteGuardError, match="requires a value"):
        build_precondition_where([Precondition(field="status", op=op)])


@pytest.mark.parametrize("falsy", [0, "", False])
def test_eq_falsy_but_present_value_is_legal(falsy):
    """0 / "" / False 是合法值——「漏填」的判别必须是 `is None`，不是 falsy。"""
    sql, params = build_precondition_where([Precondition(field="s", op="eq", value=falsy)])
    assert sql == '"s" = :pre_0'
    assert params == {"pre_0": falsy}


def test_unknown_operator_rejected_on_unvalidated_construct():
    """经 pydantic 校验不可达；model_construct（绕过校验的反序列化路径）仍须被守卫拒绝。"""
    bogus = Precondition.model_construct(field="status", op="bogus", value="x")
    with pytest.raises(WriteGuardError, match="unknown precondition op"):
        build_precondition_where([bogus])


def test_in_params_do_not_alias_caller_list():
    """绑定值 copy 自声明——调用方随后改动 list 不应影响已编译的 params。"""
    src = ["a"]
    _, params = build_precondition_where([Precondition(field="s", op="in", value=src)])
    assert params["pre_0"] == ["a"]
    assert params["pre_0"] is not src


def test_update_set_literal_and_now():
    sql, params = build_update_set([StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)])
    assert sql == '"status" = :set_0, "updated_at" = NOW()'
    assert params == {"set_0": "active"}


def test_update_set_requires_at_least_one():
    with pytest.raises(WriteGuardError, match="no state change"):
        build_update_set([])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_sql_write.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.actions'`

- [ ] **Step 3: 实现**

```bash
# 空包标记
printf '"""OntoStudio 动作层（设计 §2）。EAI-CUSTOM。"""\n' > ontostudio/backend/app/ontology/actions/__init__.py
```

```python
# ontostudio/backend/app/ontology/actions/sql_write.py
"""动作写路径的 SQL 构造与守卫——**全库唯一的写路径标识符白名单与片段构造处**。

EAI-CUSTOM: 设计 §2。安全约定：
- 表名与列名只来自解析后的 ActionSpec（registry 声明），**绝不来自调用方 params**；
- 列名/表名一律过标识符白名单（``quote_ident``）并加引号；
- 值一律命名参数绑定。
语句骨架（``UPDATE ... SET ... WHERE ...``）由 executor 拼装、表名经 ``quote_ident``——
「唯一」限定在白名单与片段构造，**不含语句级拼装**。
读路径的 sqlguard.assert_readonly_select 只放 SELECT，不能复用，故单独成模块。
"""

from __future__ import annotations

import re
from typing import Any

from app.ontology.schemas import Precondition, StateChange

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_PRE_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "is_null": "{c} IS NULL",
    "not_null": "{c} IS NOT NULL",
}


class WriteGuardError(ValueError):
    """动作声明不合法或试图构造越界语句。"""


def quote_ident(name: str) -> str:
    # fullmatch 而非 match：`$` 锚点容许尾部换行（`_IDENT.match("abc\n")` 通过），
    # 而白名单是"本模块唯一的注入防线"，锚点必须严格。同 Task 1 的 scope.py::_quote。
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise WriteGuardError(f"identifier rejected: {name!r}")
    return f'"{name}"'


def build_precondition_where(preconditions: list[Precondition]) -> tuple[str, dict[str, Any]]:
    """前置条件合取（AND）。空列表 → TRUE（声明方未加前置条件，这是明确语义）。

    **不因「值退化」而产出恒真式**——`Precondition.value` 是 `Any | None` 且 registry 是
    热加载数据，故漏填与形状错都可达：
    - ``in`` / ``not_in`` **形状错**（str / 标量 / 映射）→ 拒绝：`list("rejected")` 会拆成
      字符，让「not_in rejected」放行它声明要拦的那一行（fail-open），标量则漏出裸 TypeError；
    - ``in`` 空 → 编译为 ``FALSE``（「不在空集里」没有行匹配，fail-closed）；
    - ``not_in`` 空 → **拒绝**（「不在空集里」字面等于「全部」，对守卫永远不是想要的）；
    - ``eq`` / ``ne`` 漏填 → 拒绝（``col = NULL`` 恒不成立，NULL 语义请用 ``is_null``）；
    - ``is_null`` / ``not_null`` 不带 value，不受影响。
    """
    if not preconditions:
        return "TRUE", {}
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, cond in enumerate(preconditions):
        tmpl = _PRE_SQL.get(cond.op)
        if tmpl is None:
            raise WriteGuardError(f"unknown precondition op: {cond.op!r}")
        col = quote_ident(cond.field)
        if cond.op in ("is_null", "not_null"):
            # 这两个模板不含 {p}，故不喂占位符（喂了也是被丢弃的幽灵参数）。
            parts.append(tmpl.format(c=col))
            continue
        key = f"pre_{i}"
        if cond.op in ("in", "not_in"):
            # 形状守卫（与 F1 同一条 fail-open 线）：str 会被 list() 拆成字符，标量则抛
            # 裸 TypeError（不是本模块的错误契约，调用方 catch WriteGuardError 会放过它）。
            # None 不算形状错——它表示漏填，与空序列同走下面的「空值」语义。
            if cond.value is not None and not isinstance(cond.value, (list, tuple, set)):
                raise WriteGuardError(f"{cond.op} value must be a list on {cond.field!r}, got {type(cond.value).__name__}")
            if not cond.value:
                if cond.op == "not_in":
                    raise WriteGuardError(f"empty value set for not_in on {cond.field!r}")
                # 空集的「属于」恒假。追加恒假合取项而非提前 return：两者都 fail-closed，
                # 差别只在诊断一致性——提前 return 会让畸形标识符是否被拒取决于声明顺序。
                parts.append("FALSE")
                continue
            params[key] = list(cond.value)  # list() 兼作拷贝：绑定值不与调用方的 list 别名
        else:
            # eq / ne：必须给出值。`col = NULL` 恒不成立（NULL 该用 is_null），静默容忍会让
            # 前置条件永不满足、动作永不触发——与 F1/C1 同一类作者笔误。
            if cond.value is None:
                raise WriteGuardError(f"{cond.op} requires a value on {cond.field!r}; use is_null / not_null for NULL")
            params[key] = cond.value
        parts.append(tmpl.format(c=col, p=f":{key}"))
    return " AND ".join(parts), params


def build_update_set(changes: list[StateChange]) -> tuple[str, dict[str, Any]]:
    """SET 子句。至少一条，否则拒绝（避免生成空 UPDATE）。"""
    if not changes:
        raise WriteGuardError("no state change declared")
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, ch in enumerate(changes):
        col = quote_ident(ch.field)
        if ch.now:
            parts.append(f"{col} = NOW()")
            continue
        key = f"set_{i}"
        params[key] = ch.set
        parts.append(f"{col} = :{key}")
    return ", ".join(parts), params
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_sql_write.py -v`
Expected: PASS（**39 项**——初稿写 11 项是陈旧值：`fullmatch` 预防性修复把拒绝用例从 4 项加到 7 项时没同步计数。三轮复审逐次回填：6 算子 parametrize、合取断言、**空值/形状/漏填**三组拒绝与 falsy 接受路径、顺序无关性、未知算子纵深防御、绑定值拷贝。**每条都经变异买过单**：`" AND "`→`" OR "` 只被合取断言抓到；还原 `or []` 只被空值 4 例抓到；**去掉形状守卫只被那 6 例抓到（其中 2 例报的是裸 `TypeError`，即 I1）**；append-`FALSE` 改提前 return 只被顺序无关性那条抓到）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/actions/ ontostudio/backend/tests/test_actions_sql_write.py
git commit -m "feat(ontostudio): 动作写守卫(sql_write)——标识符白名单 + 参数化构造"
```

---

## Task 5: `executor.py` —— 执行管线

**Files:**
- Create: `ontostudio/backend/app/ontology/actions/executor.py`
- Test: `ontostudio/backend/tests/test_actions_executor.py`

- [ ] **Step 1: 写失败测试**

测试用 mock 的对象类型 + 假 action，直接调 `invoke_action_core(...)`（把鉴权与取范围规则作为**已解析参数**传入，使本 Task 不依赖 gateway）。真实 DB 走 `_ext_url()`，与 `test_doc_graph_*` 同一套环境。

```python
# ontostudio/backend/tests/test_actions_executor.py
"""执行管线：解析→范围→锁定→前置→UPDATE→审计→重投影。

本文件把「权限判定的结果」与「数据范围规则」作为入参喂给核心函数，
从而与 gateway 解耦（gateway 侧单测在 backend/tests/test_permissions_scope_endpoint.py）。
"""
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions.executor import ActionError, ScopeDenied, invoke_action_core
from app.ontology.connectors import _ext_url
from app.ontology.scope import FilterRule

pytestmark = pytest.mark.integration


async def _seed_entity(status: str = "pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status)
                       VALUES ('doc_graph','mine','测试实体', :norm, '{}'::jsonb, 0.9, :status) RETURNING id"""
                ),
                {"norm": f"测试实体-{uuid.uuid4().hex[:8]}", "status": status},
            )
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _get_status(pk: uuid.UUID) -> str:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT status FROM dg_entities WHERE id = :id"), {"id": pk})
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows(pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT action_id, before, after, source FROM dg_action_audit WHERE target_pk = :id"),
                {"id": pk},
            )
            return [dict(r._mapping) for r in rows]
    finally:
        await engine.dispose()


async def test_happy_path_writes_status_and_audit():
    pk = await _seed_entity()
    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="mcp",
        scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}
    assert await _get_status(pk) == "active"
    audit = await _audit_rows(pk)
    assert len(audit) == 1
    assert audit[0]["before"] == {"status": "pending_review"}
    assert audit[0]["source"] == "mcp"


async def test_precondition_violation_returns_409():
    pk = await _seed_entity(status="active")
    with pytest.raises(ActionError) as e:
        await invoke_action_core(
            "review_entity.confirm", {}, target_pk=pk,
            actor_id=uuid.uuid4(), actor_role="admin", source="api",
            scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
        )
    assert e.value.status_code == 409
    assert "pending_review" in e.value.detail


async def test_out_of_scope_returns_404():
    pk = await _seed_entity()
    with pytest.raises(ScopeDenied) as e:
        await invoke_action_core(
            "review_entity.confirm", {}, target_pk=pk,
            actor_id=uuid.uuid4(), actor_role="user", source="api",
            scope_rule=FilterRule(operator="none_allow"), project=lambda *a, **k: True,
        )
    assert e.value.status_code == 404


async def test_unknown_action_rejected():
    with pytest.raises(ActionError, match="unknown action"):
        await invoke_action_core(
            "nope.nope", {}, target_pk=uuid.uuid4(),
            actor_id=uuid.uuid4(), actor_role="admin", source="api",
            scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
        )


async def test_scope_sql_is_executable_with_list_params():
    """M-8（Task 1 审查遗留）：`= ANY(:p)` 传 Python list 给 asyncpg 的类型推断
    从未被任何测试证明过（`col = ANY($1)` 依赖列类型推出 uuid[]）。
    Task 1 的绿只证明 SQL 文本形态正确，不证明这条通道能跑——故在此显式钉住。

    **⚠️ 并需覆盖空 list**（Task 4 审查前向风险）：`in`/`not_in` 编译为 `= ANY(:pre_0)`
    且绑定 Python list，而**空 list 是可达的**——网关 `backend/app/extensions/auth/engine.py:52`
    在模板解析出空 list 时正是产出 `FilterRule(operator="in", value=[])`。
    `ANY(:[])` 传空 Python list 时 asyncpg 能否推断数组元素类型**未经验证**。
    **⚠️⚠️ 本段的初版修法是错的，已在 Task 4 审查中被证伪，勿照抄**：初版写「空集短路
    （`in` 空 → `FALSE`、**`not_in` 空 → `TRUE`**）」——**`not_in` 空 → TRUE 本身就是 fail-open**。
    真库实测：`NOT ('a' = ANY(ARRAY[]::text[]))` = `NOT FALSE` = **TRUE**，
    即**前置条件恒满足、守卫静默失效**；而参数为 `NULL` 时 `NOT(...)` = NULL → 行被过滤 → 拒绝。
    也就是说 `sql_write.py` 里那句 `list(cond.value or [])` **把"漏填 value"从 fail-closed 翻转成了 fail-open**。

    **读路径与写路径的空集语义必须分开裁决**：

    | 路径 | `in` 空 | `not_in` 空 |
    |---|---|---|
    | 读（`scope.py` 数据范围过滤） | `FALSE`（filter 掉，安全） | 需单独裁决 |
    | **写（`sql_write.py` 前置条件守卫）** | `FALSE`（拒绝该动作，安全） | **绝不能是 TRUE**——守卫不该产出恒真式 |

    修法：`sql_write.py` 侧——`in` 空编译为 `FALSE`；**`not_in` 空直接 `raise WriteGuardError`**
    （"不在空集里"字面意义上等于"全部"，对守卫永远不是想要的东西）。类型推断那一半（`ANY(:[])`
    传空 list 时 asyncpg 能否推断元素类型）**仍未验证**，需 Task 5 用真库测试钉住；
    显式转型 `= ANY(CAST(:pre_0 AS text[]))` 是备选。

    **只覆盖 `in`。`overlap`（`col && $1`）是另一条绑定路径，本测试证不了它**——
    `&&` 要求操作数是 array 列，而本体面对的表（cpa_*/csp_*/dg_*）无 array 列，
    构造不出用例。**这不是死代码**：`config/permissions.yaml:99` 有真实模板
    `allowed_depts OVERLAP: $identity.dept_ids` 在用。**触发条件**：一旦某对象类型的
    `scope_bindings` 指向 array 列，必须先补一条 overlap 的集成测试再上线。
    """
    pk = await _seed_entity()
    rule = FilterRule(operator="in", field="id", value=[str(pk)])
    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="api",
        scope_rule=rule, project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}


async def test_projection_failure_does_not_rollback():
    """投影失败不回滚业务状态：审计与 UPDATE 已提交，errors 里留痕。"""
    pk = await _seed_entity()
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("projection boom")

    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="api",
        scope_rule=FilterRule(operator="allow_all"), project=boom,
    )
    assert result["projected"] is False
    assert result["errors"] and "projection boom" in result["errors"][0]
    assert await _get_status(pk) == "active"
    assert len(await _audit_rows(pk)) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_executor.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.actions.executor'`

- [ ] **Step 3: 实现**

```python
# ontostudio/backend/app/ontology/actions/executor.py
"""动作执行管线（设计 §2）。

Postgres dg_* 是唯一真相源；提交后的增量重投影失败**不回滚**业务状态，
只记入 errors 并可重放——与 kernel/infer.py 的失败降级取向一致。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions.sql_write import build_precondition_where, build_update_set, quote_ident
from app.ontology.connectors import _ext_url
from app.ontology.registry import get_registry
from app.ontology.scope import FilterRule, rule_to_sql


class ActionError(Exception):
    """动作执行失败。status_code/detail 直接映射到 HTTP 与 MCP 错误体。"""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ScopeDenied(ActionError):
    """目标行不在调用者的数据范围内。用 404 而非 403——不泄漏行是否存在。"""

    def __init__(self, detail: str = "目标不存在或不在可见范围内") -> None:
        super().__init__(detail, status_code=404)


def _resolve(action_id: str):
    """解析动作声明与其目标对象类型。未知即拒（fail-closed）。

    Registry 是合并快照（actions / object_types 两张扁平字典），不保存 per-domain
    DomainFile——所以这里按 id 直查，不遍历域。
    """
    registry = get_registry()
    action = registry.get_action(action_id)
    if action is None:
        raise ActionError(f"unknown action: {action_id}", 404)
    obj = registry.object_types.get(action.target)
    if obj is None:  # registry 加载时已校验，此处是纵深防御
        raise ActionError(f"action {action_id} target unresolved: {action.target}", 500)
    return action, obj


async def invoke_action_core(
    action_id: str,
    params: dict[str, Any],
    *,
    target_pk: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str | None,
    source: str,
    scope_rule: FilterRule,
    project: Callable[[str, uuid.UUID], None],
) -> dict[str, Any]:
    """管线主体。鉴权与取范围规则由调用方（REST/MCP）完成后传入。

    project(action_id, pk) 在**提交后**调用，用于增量重投影；抛异常不回滚。
    """
    action, obj = _resolve(action_id)
    table = obj.access.table
    if not table:
        raise ActionError(f"action {action_id} target has no physical table", 500)

    bindings = obj.scope_bindings or None
    scope_sql, scope_params = rule_to_sql(scope_rule, bindings)
    pre_sql, pre_params = build_precondition_where(action.preconditions)
    set_sql, set_params = build_update_set(action.postconditions)

    pk_col = quote_ident(obj.pk.column)
    table_q = quote_ident(table)
    where = f"{pk_col} = :pk AND ({scope_sql})"
    params_all = {"pk": target_pk, **scope_params, **pre_params, **set_params}

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    errors: list[str] = []
    try:
        async with engine.begin() as conn:
            locked = await conn.execute(
                text(f"SELECT * FROM {table_q} WHERE {where} FOR UPDATE"), params_all
            )
            row = locked.mappings().first()
            if row is None:
                raise ScopeDenied()

            ok = await conn.execute(text(f"SELECT ({pre_sql}) AS ok FROM {table_q} WHERE {pk_col} = :pk"), params_all)
            if not ok.scalar_one():
                expected = ", ".join(f"{c.field} {c.op} {c.value!r}" for c in action.preconditions)
                raise ActionError(f"前置条件不满足：需要 {expected}", status_code=409)

            before = {c.field: row.get(c.field) for c in action.postconditions}
            after = {c.field: (None if c.now else c.set) for c in action.postconditions}

            await conn.execute(
                text(f"UPDATE {table_q} SET {set_sql} WHERE {pk_col} = :pk"), params_all
            )
            await conn.execute(
                text(
                    """INSERT INTO dg_action_audit
                       (action_id, domain, target_table, target_pk, actor_id, actor_role, params, before, after, source)
                       VALUES (:action_id, :domain, :tbl, :pk, :actor, :role,
                               CAST(:params AS jsonb), CAST(:before AS jsonb), CAST(:after AS jsonb), :source)"""
                ),
                {
                    "action_id": action.id, "domain": action.domain, "tbl": table, "pk": target_pk,
                    "actor": actor_id, "role": actor_role,
                    "params": _json(params), "before": _json(before), "after": _json(after), "source": source,
                },
            )
    finally:
        await engine.dispose()

    try:
        project(action.id, target_pk)
        projected = True
    except Exception as e:  # 投影失败不回滚业务状态（设计 §2 步骤 5）
        projected = False
        errors.append(f"{type(e).__name__}: {e}")

    return {
        "action_id": action.id, "target": obj.api_name, "pk": str(target_pk),
        "before": before, "after": after, "source": source,
        "projected": projected, "errors": errors,
    }


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)
```

> **注**：`before`/`after` 里的 datetime 等非 JSON 类型由 `default=str` 兜底；`after` 中 `now=True` 的列记 `None`，表示"由 DB 决定"，真实值以重投影后的图为准（这是有意的：避免在事务外再查一次）。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_executor.py -v`
Expected: PASS（5 项）。

> **⚠️ 若报 `dg_action_audit` 不存在，不要重启 gateway——那不会建表。** 本计划初稿此处写的是「说明 gateway 尚未重启建表——先跑 restart gateway」，**那个诊断已被 Task 3 审查实测证伪**：`dg_*` 模型在 2026-09-17 独立服务搬迁时已从 gateway 的 `Base` 摘到 ontostudio 本地 `app.db.Base`，**gateway 的 `Base.metadata` 里 `dg_*` 表为零**。
> **实际建表路径**：ontostudio 自身 lifespan 的 `ensure_tables()`（`app/db.py`）。若表缺失，看 ontostudio 启动日志里的建表 WARNING，并检查 `/health` 的就绪字段（Task 3 质量审查新增）。

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/actions/executor.py ontostudio/backend/tests/test_actions_executor.py
git commit -m "feat(ontostudio): 动作执行管线(事务/前置/审计/容错重投影)"
```

### Step 6: 写路径韧性 —— 懒建 + `command_timeout`（**归属裁定：Task 5**）

> **为什么在这里**：计划 line 112 与 spec §1.2.1 表格把「首次用 DB 时重试 / 懒建」派给 Task 5，`app/main.py:101` 与 `app/db.py:28-29` 的注释也写着「随 Task 5 落地」——**但 Task 5 的 Step 1–5 里没有这两件**。这是本计划**第三次**出现"被推迟的项没人认领"（Task 2→Task 3 的动作声明、Task 4→Task 5 的前向风险、现在是这个）。**归属 Task 5，理由是职责而非补窟窿**：`executor.py` 是 `dg_action_audit` 的唯一写入方，"表不存在时写不进去"属**写路径韧性**，不是运维配置。

**Files**：`ontostudio/backend/app/db.py`、`ontostudio/backend/app/main.py`、`ontostudio/backend/app/ontology/actions/executor.py`、`ontostudio/backend/tests/test_actions_executor.py`（或新建专项测试文件）

**(a) 懒建 + 有界重试**：写路径上 `INSERT INTO dg_action_audit` 因**表不存在**失败时，调一次 `ensure_tables()` 并**重试一次事务**。硬要求：

- **必须有界**：模块级 flag 保证每进程只尝试一次懒建，第二次失败照常抛。**不要写成重试循环。**
- **只对"表不存在"触发**（`asyncpg.exceptions.UndefinedTableError` / SQLSTATE `42P01`）。**不要 catch 宽泛的 DBAPIError**——否则连接失败、权限错误也会被吞进重试。
- 失败**如实抛**（转 `ActionError`，DB 不可达是服务端问题 → 500）。
- 重试必须在**原事务之外**（原事务已因异常回滚）。

**(b) `command_timeout`**：`app/db.py` 的引擎加 `command_timeout`（建议 30）。理由：`connect_args={"timeout":5}` **只界握手**；TCP 建好后命令阶段默认无界，链路被防火墙/NAT 静默掐断时要等 TCP keepalive（Windows 约 2 小时）——**原 I2"启动楔死"模式的后移版**。失败已是非致命，误杀代价 ≈ 一条 WARNING。

**(c) 把指向它的注释改准**：`app/main.py:101` 与 `app/db.py:28-29` 现写「随 Task 5 落地」→ 做成"已落地"。spec §1.2.1 表格第三行同步。

**测试要求**（都要能咬；**别只断言"调了 ensure_tables"**——本计划已有一条被变异证伪的覆盖声称）：
1. **懒建**：模拟"表先不存在" → 写路径仍成功，**断言可观测效果**（写成功且审计行在）
2. **只对表不存在触发**：连接失败 / 权限错误**不得**触发懒建（否则是吞错）
3. **有界**：懒建后仍失败 → 抛出且**不再重试**（数 `ensure_tables` 调用次数）
4. **`command_timeout` 生效**：**捕获传给引擎的实参**（照 Task 3 的 `test_ensure_tables_bounds_connect_timeout`），**不要用计时上界**——上界抓不到值漂移，那条已被变异证伪

**已知限制写进注释**：`create_all` **不做 schema 变更**——懒建只解决"表不存在"，解决不了"表存在但列不全"。别让人以为有了自动迁移。

> **回填（2026-09-23 实测，实施者记）**：
> 1. **测试①的机制换过一次**：初版按「改名藏真表」造 42P01，**实测证伪**——PostgreSQL 的
>    `ALTER TABLE ... RENAME` **不会**跟着改索引名（`dg_action_audit_pkey`、`ix_dg_action_audit_*`
>    都留在原表上），懒建的 `create_all` 建表时撞名失败（`DuplicateTableError`），不但测不出懒建，
>    还把改名后的活库留在原地污染后续用例。改成**一次性 scratch 库**（`DROP DATABASE ... WITH (FORCE)`
>    → `CREATE DATABASE` → `ensure_tables()` → `DROP TABLE dg_action_audit`）：真 42P01 链、真建表、
>    真重试、真落审计行，且最坏只脏自己的库。
> 2. **测试④照要求捕获引擎实参**；`30→300` 的值漂移由「常量 ≤ 60」的上界钉住（变异实测红）。
> 3. 识别器必须**走异常链**：真库实测链为 `sqlalchemy.exc.ProgrammingError`（顶层 `sqlstate=None`）
>    → 适配层 `ProgrammingError`(42P01) → `asyncpg.exceptions.UndefinedTableError`。只判最外层永远不触发
>    （变异实测：只判顶层 → 懒建的 e2e 测试红）。
> 4. **`command_timeout` 触发的异常形状（实测订正）**：asyncpg 的 `command_timeout` 超时时抛的是
>    **asyncio `TimeoutError`**，**不是** 57014（引擎带 `command_timeout=1` 跑 `pg_sleep(5)` → 链上只有
>    `TimeoutError`、无 sqlstate）。行为本来就对（非 42P01 → 不懒建），错的是注释里的归因；已补一条
>    该形状的反例钉住。
> 5. **写路径引擎本轮未加超时**（有意）：同样两个超时的理由建立在「误杀 ≈ 一条 WARNING」上，
>    写路径的同类失败是用户可见的 500。属 Task 6/7 的暴露面决策。

```bash
git add ontostudio/backend/app/db.py ontostudio/backend/app/main.py ontostudio/backend/app/ontology/actions/executor.py ontostudio/backend/tests/
git commit -m "feat(ontostudio): 写路径韧性——懒建审计表 + command_timeout 收口"
```

---

## Task 6: gateway 侧 —— 授权缓存键修正 + `/api/permissions/scope` + 权限声明

**Files:**
- Modify: `backend/app/extensions/auth/routers.py`
- Create: `backend/app/extensions/auth/authz_cache.py`
- Modify: `config/permissions.yaml`, `deploy/offline/config/permissions.yaml`
- Modify: `ontostudio/backend/app/auth.py`（缓存键同步修正）
- Test: `backend/tests/test_permissions_scope_endpoint.py`

> **必须先修的既有缺陷**：OntoStudio 的 `_authz_cache: dict[user_id, (bool, float)]` **只按用户做键**，值的含义却是"该用户对**某一次查询的那个权限**是否放行"。目前只用一个权限（`system:access`）所以没暴露；本设计要按动作查第二个权限（`ontology:action:review`），**同一用户在 30s 内查两个权限会命中错误缓存**。两处都要改成 `(user_id, permission)` 复合键，并各加一条回归测试。

- [ ] **Step 1: 写失败测试（缓存键 + 端点）**

```python
# backend/tests/test_permissions_scope_endpoint.py
"""数据范围端点 + 授权缓存键回归。"""
import uuid

import pytest

from app.extensions.auth.authz_cache import AuthzCache


def test_authz_cache_keys_by_user_and_permission():
    """同一用户查两个权限不得互相污染——历史实现只按 user_id 做键。"""
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "system:access", True)
    c.put(uid, "ontology:action:review", False)
    assert c.get(uid, "system:access") is True
    assert c.get(uid, "ontology:action:review") is False


def test_authz_cache_expires():
    c = AuthzCache(ttl_seconds=0.0)
    uid = uuid.uuid4()
    c.put(uid, "p", True)
    assert c.get(uid, "p") is None


def test_authz_cache_invalidate_user_drops_all_permissions():
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "a", True)
    c.put(uid, "b", False)
    c.invalidate_user(uid)
    assert c.get(uid, "a") is None and c.get(uid, "b") is None
```

以及端点测试（沿用现网 `admin_client` / `user_client` 装置；若不存在则用 `TestClient(app)` + 登录 helper）：

```python
@pytest.mark.asyncio
async def test_scope_endpoint_returns_none_allow_without_scopes(admin_client):
    ""'ontology' 模块未授 ontology_all 的角色 → none_allow。"""
    r = await admin_client.get("/api/permissions/scope", params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] in ("none_allow", "allow_all")


@pytest.mark.asyncio
async def test_scope_endpoint_unknown_resource_is_none_allow(admin_client):
    r = await admin_client.get("/api/permissions/scope", params={"resource": "no_such_module"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] == "none_allow"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_permissions_scope_endpoint.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.extensions.auth.authz_cache'`

- [ ] **Step 3: 实现 `authz_cache.py`**

```python
# backend/app/extensions/auth/authz_cache.py
"""授权判定结果缓存。

EAI-CUSTOM (2026-09-22): 键必须是 (user_id, permission) 复合键。
历史实现只按 user_id 做键、值的语义却是"某一次查询的那个权限"——
在只查单一权限（system:access）时未暴露；本体动作层引入第二个权限后
会造成跨权限串味（把一个权限的放行结果当成另一个的）。见
docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
"""

from __future__ import annotations

import threading
import time
import uuid


class AuthzCache:
    """进程内 TTL 缓存。部署为单实例，进程内即可；失败方向恒为 fail-closed。"""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._data: dict[tuple[uuid.UUID, str], tuple[bool, float]] = {}
        self._lock = threading.Lock()

    def get(self, user_id: uuid.UUID, permission: str) -> bool | None:
        with self._lock:
            hit = self._data.get((user_id, permission))
            if hit is None:
                return None
            allowed, expires_at = hit
            if time.monotonic() >= expires_at:
                self._data.pop((user_id, permission), None)
                return None
            return allowed

    def put(self, user_id: uuid.UUID, permission: str, allowed: bool) -> None:
        with self._lock:
            self._data[(user_id, permission)] = (allowed, time.monotonic() + self._ttl)

    def invalidate_user(self, user_id: uuid.UUID) -> None:
        with self._lock:
            for key in [k for k in self._data if k[0] == user_id]:
                self._data.pop(key, None)
```

- [ ] **Step 4: 接入 `routers.py` 并加 `/scope` 端点**

在 `backend/app/extensions/auth/routers.py` 中：

(a) 把 `/me` 所在 router 的 `@router.get("/me", ...)` **之前**插入新端点：

```python
@router.get("/scope")
async def get_data_scope(
    resource: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """返回当前用户对某资源的数据范围规则（序列化 FilterRule）。

    EAI-CUSTOM (2026-09-22): 供 OntoStudio 动作层做实例级权限判定。
    只读、无副作用；resource 为 permissions.yaml 的**模块 key**。
    未知资源或角色无 scope → none_allow（fail-closed）。
    """
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.identity import AttributeSet

    engine = DataScopeEngine.from_registry()
    identity = AttributeSet.from_current_user(current_user)
    rule = engine.get_data_scope(identity, resource)
    return {"resource": resource, "rule": rule.to_wire()}
```

**已验证：这两个方法都不存在，必须新增**（`engine.py` 的 `FilterRule` 是纯 dataclass 无任何方法；`identity.py` 的 `AttributeSet` 只有 `to_dict` / `get_attr`）。

在 `backend/app/extensions/auth/engine.py` 的 `FilterRule` 类内追加：

```python
    def to_wire(self) -> dict[str, Any]:
        """序列化给 OntoStudio（独立服务，无法 import 本模块）。

        形态必须与 ontostudio/backend/app/ontology/scope.py::FilterRule.to_wire 逐字段一致；
        经 FastAPI 返回时 uuid.UUID 由 jsonable_encoder 转为字符串，对端按字符串处理。
        """
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out
```

在 `backend/app/extensions/auth/identity.py` 的 `AttributeSet` 类内追加：

```python
    @classmethod
    def from_current_user(cls, user, *, member_projects: list[str] | None = None) -> "AttributeSet":
        """由 gateway CurrentUser 构造授权身份（供 /api/permissions/scope 使用）。

        字段面与既有 rule_template 的 `$identity.*` 引用面一致
        （user_id / role_code / dept_ids / member_projects）。
        member_projects 需调用方查库后传入；缺省空表会让
        `id IN $identity.member_projects` 解析为 none_allow（fail-closed，安全方向）。
        """
        return cls(
            user_id=str(user.id),
            role_code=user.role_name,
            dept_ids=[str(user.dept_id)] if getattr(user, "dept_id", None) else [],
            member_projects=member_projects or [],
        )
```

> **必须验证的一处**：`DataScopeEngine` 用 `identity.role_code` 去查 `_role_data_scopes`，而该字典由 `registry.list_role_codes()` 建键——是角色 **code**；而 `CurrentUser.role_name` 拿到的可能是角色 **名称**。**两者若不同名，角色永远匹配不到任何 scope，结果恒为 `none_allow`（动作全部 404）**。在 Step 7 前先跑一次实证：
> ```bash
> cd backend && PYTHONPATH=. uv run python -c "
> from app.extensions.auth.registry import get_permission_registry as g
> print('list_role_codes:', g().list_role_codes()[:5])
> print('a role data_scopes:', g().get_data_scopes_for_role('admin'))
> "
> ```
> 若键与 `CurrentUser.role_name` 不一致，改用能对上的那个字段（可能是 `user.role_id` 反查），并在 `from_current_user` 的 docstring 里写明依据。**不要靠猜。**

(b) 用 `AuthzCache` 替换 `routers.py` 中模块级的 `_authz_cache` dict，并把 `get/put` 调用改为传 `(user.id, permission)`。

- [ ] **Step 5: 声明权限点与数据范围**

`config/permissions.yaml` 的 `ontology:` 模块（约 L259）内：

- `pages[0].operations` 追加 `- { id: "ontology:action:review", display_name: "审核抽取实体" }`
- 模块级追加 `data_scopes`（该模块当前是 `data_scopes: []`）：

```yaml
    data_scopes:
      - { id: "ontology_all", display_name: "全部本体数据", rule_template: {} }
```

- 给需要审核权的角色补上（至少 `admin` 与 `superadmin`）：
  `ontology:action:review` 加到其 `permissions`；`ontology_all` 加到其 `data_scopes`。

`deploy/offline/config/permissions.yaml` **做完全相同的三处改动**——漏掉则离线部署恒 404。

- [ ] **Step 6: 同步修正 OntoStudio 侧的缓存键**

`ontostudio/backend/app/auth.py`：把 `_authz_cache: dict[uuid.UUID, tuple[bool, float]]` 及 `_gateway_authorizes` 的读写改为 `(user.id, permission)` 复合键。在 `ontostudio/backend/tests/test_main.py` 补一条与 Step 1 同形的回归测试（同用户两权限不串味）。

- [ ] **Step 7: 跑测试确认通过**

Run:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permissions_scope_endpoint.py -v
cd ../ontostudio/backend && PYTHONPATH=. uv run pytest tests/test_main.py -v
```
Expected: 全 PASS

- [ ] **Step 8: 提交**

```bash
git add backend/app/extensions/auth/ backend/tests/test_permissions_scope_endpoint.py config/permissions.yaml deploy/offline/config/permissions.yaml ontostudio/backend/app/auth.py ontostudio/backend/tests/test_main.py
git commit -m "feat(auth): 数据范围端点 + 授权缓存键改 (user,permission) 复合键

缓存键缺陷: 原实现只按 user_id 做键, 值语义却是某一次查询的权限——
单权限时未暴露, 本体动作层引入第二个权限后会造成跨权限串味。
ontology 模块补 ontology_all 数据范围与 ontology:action:review 操作权限。"
```

---

### Step 9: `graph_relation` 绑 `scope_resource`（**Task 3 交棒、Task 6 掉落的一步**）

> **本步骤是补一个跨 Task 的漏接**。Task 3 的计划明文写着「只加 `graph_entity` 一个，不要顺手加 `graph_relation`——设计 §3 提到两个对象类型，但**那是 Task 6 的范围**」。**而 Task 6 全节没有这一步，Task 7–10 也没有**（全计划 `graph_relation` 只出现在那一句里）。
>
> **这是本计划第四次出现"被推迟的项没人认领"**（前三次：Task 2→Task 3 的动作声明、Task 4→Task 5 的前向风险、以及"随 Task 5 落地"的懒建）。**规律：凡写下"那是 X 的范围"，就必须同时改 X 的步骤——否则那句话只是自我安慰。**

在 `ontostudio/backend/app/ontology/registry/doc_graph.yaml` 的 `graph_relation` mapping 上，同样加：

```yaml
    scope_resource: ontology
```

**影响**：今日无运行期后果（现有动作只 targeting `graph_entity`），但任何将来 targeting `graph_relation` 的动作会恒 `none_allow`（权限配了但没用）。

> **⚠️ 订正（Task 6 质量审查）**：本步骤初稿末尾写「且 Task 9 的 `scope_bindings` lint 可能就此报错」——**那是错的，已删**。Task 9 的 `check_scope_resources` 只校验"**已声明**的 `scope_resource` 是已知模块 key"，其自带验收用例 `test_object_without_scope_resource_is_fine` **明确祝福"缺绑定是正常的"**——所以**缺绑定永远绿**。留着那句会让下一个人依赖一个不会触发的守卫。

**防复发的结构性做法（Task 9 已落地，口径经实测收窄）**：断言「**凡被动作层可达的对象类型，必须声明 `scope_resource`**」——**口径是"从每个 `actions[].target` 出发、沿 `enabled` 的 link_types 双向遍历得到的闭包"**，不是字面的"凡被动作或链接类型引用"。

> **⚠️ 口径订正（Task 9 实现者实测）**：本行初稿写的是「凡被动作**或链接类型**引用的对象类型」。**那个口径在真实 registry 上不可满足**——实测 **16 个对象里 12 个**未绑（`bid`/`bid_item`/`contract_document`/`contract_item`/`customer`/`data_source`/`dataset`/`goods_cluster`/`part_cluster`/`spare_part_document`/`spare_part_item`/`graph_mention`），其中 **`data_source`/`dataset` 在 `permissions.yaml` 里没有对应模块 key**（它们走 `system:access`，不走 data_scope 模块）——**不新增模块就无正确取值**。字面口径还会打破 3 条既有验收（本计划 Step 4 退出码 0、Task 10 ⑥、以及 `test_all_checks_pass_on_real_registry`/`test_main_exit_zero`）。
>
> **收窄后的口径仍能抓住设计要防的那一类**：`graph_relation`/`graph_mention` 都是"链接端点、非动作 target"，正是第四次与这次复发的形态。**该检查第一遍跑就抓到 `graph_mention` 未绑**（真问题，已补），真 registry 上现为 `OK (16 object types, 16 links)` EXIT=0。
>
> **要放回全量口径**只需改 `check_action_reachable_objects_are_scoped` 一处判定，代价是先决定那 11 个市场域对象的模块归属（其中 2 个无可用 key）。**运行时今日都不变**（读路径不查 `scope_resource`），但它是一份治理声明。

**只靠"补上这一次"防不住复发——本计划已用六次证明了这一点。**

**要有的测试**：`assert get_registry().object_types["graph_relation"].scope_resource == "ontology"`（与 `graph_entity` 那条同形）。

```bash
git add ontostudio/backend/app/ontology/registry/doc_graph.yaml ontostudio/backend/tests/
git commit -m "fix(ontostudio): graph_relation 补 scope_resource（Task 3 交棒、Task 6 掉落）"
```

---

## Task 7: REST 暴露面

> ### ⚠️ 开工前必读：本任务多了一条硬性验收项（Task 6 质量审查 I-1）
>
> **spec §3.1 记录的 `/scope` 判定缺口，收敛动作就在这里——此前它是个悬空指针。** 我在 spec 里写了「收敛方向见 Task 7 接线清单」，但 grep 全计划 `deny_data_scopes|超管旁路|is_system|with_data_scope` 只有那一处，**Task 7 本节原本没有任何一条涉及它**。这是本计划**第五次**出现"凡写下'那是 X 的范围'，却没同时改 X 的步骤"。
>
> **必须在 Task 7 内闭合并验收**：让 `/scope` 与平台正典 `with_data_scope`（`backend/app/extensions/auth/middleware.py:350-388`）共用同一条判定路径，即补齐两步：
> 1. **超管旁路**（`:380`：`is_system` 或 `permissions` 含 `"*"` → `allow_all`）
> 2. **ABAC `deny_data_scopes` 扣减**（`:385`；`get_data_scope` 本身支持 `deny_scope_ids`，`/scope` 没传）——**这一半是 fail-open**
>
> **验收测试**：造两态——`deny_data_scopes: [ontology_all]` + 非超管持有 `ontology_all`——断言两侧判定一致。
>
> **⚠️ 时间性事实（改变了这条缺口的可触发性）**：`policy_routers.py:47-50` 校验 `deny_data_scopes` 的每个 id 必须在 registry 中已声明，而 **`bc4609635` 之前 `ontology_all` 在 yaml 里出现 0 次**——**是那次提交本身第一次让"deny 掉 `ontology_all`"成为可创建的策略**。风险从"理论上"变成"管理员一次操作即可"。最坏情形：`{conditions: {}, grants: {deny_data_scopes: [ontology_all]}}` 在平台侧是**全域读封锁**（空模板 deny ⇒ `none_allow`），而 OntoStudio 的读与动作**完全无视它**。
>
> **另（不在本任务，登记以免再丢）**：`/scope` 的身份构造应改用**本文件已 import 的正典 `provider.resolve()`**（见 Task 6 审查 I-3），而不是手工复刻半个 `resolve`。这项由实现者在 Task 6 收口轮处理；若未处理，在本任务一并做——**它决定 `dept_ids`/`member_projects` 是否与平台等价**。

**Files:**
- Modify: `ontostudio/backend/app/ontology/routers.py`
- Test: `ontostudio/backend/tests/test_actions_rest.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_rest.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_invoke_requires_auth():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/extensions/ontology/actions/invoke",
                         json={"action_id": "review_entity.confirm", "pk": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invoke_unknown_action_is_404(auth_headers):
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post("/api/extensions/ontology/actions/invoke",
                         json={"action_id": "nope.nope", "pk": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_rest.py -v`
Expected: FAIL —— 404（路由不存在）

- [ ] **Step 3: 实现（`routers.py` 追加）**

```python
@router.post("/actions/invoke")
async def invoke_action_endpoint(
    body: ActionInvokeRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("system:access")),
):
    """执行一个已声明的动作（设计 §2）。

    权限分两层：操作权限（required_permissions，经 request_action 判定）
    与数据范围（scope_resource → FilterRule）。两者任一不过即拒。
    """
    from app.ontology.actions.executor import ActionError, invoke_action_core
    from app.ontology.scope import FilterRule

    try:
        action, scope_rule = await _authz_for_action(request, user, body.action_id)
        return await invoke_action_core(
            body.action_id,
            body.params,
            target_pk=uuid.UUID(body.pk),
            actor_id=user.id,
            actor_role=user.role_name,
            source="api",
            scope_rule=scope_rule,
            project=lambda aid, pk: _project_incrementally(aid, pk),
        )
    except ActionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
```

配套在本文件内新增：

```python
class ActionInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    pk: str
    params: dict[str, Any] = Field(default_factory=dict)


async def _authz_for_action(request: Request, user: CurrentUser, action_id: str) -> tuple[Any, "FilterRule"]:
    """解析动作 → 逐条校验 required_permissions → 取 scope_resource 的范围规则。"""
    from app.ontology.actions.executor import ActionError, _resolve
    from app.ontology.scope import FilterRule

    action, obj = _resolve(action_id)
    for perm in action.required_permissions:
        if not await authorize(request, user, perm):
            raise ActionError(f"缺少权限：{perm}", status_code=403)

    if not obj.scope_resource:
        return action, FilterRule(operator="allow_all")
    rule = await fetch_scope_rule(request, obj.scope_resource)
    return action, rule


def _project_incrementally(action_id: str, pk: uuid.UUID) -> None:
    """增量重投影：只刷新受影响行对应的三元组（设计 §2 步骤 5）。

    当前实现委托给既有的全量入口（P1-7 收敛为独立任务）；此处保证异常向外抛，
    由 executor 记入 errors——不吞异常。
    """
    from app.ontology.kernel.service import get_kernel
    get_kernel().refresh()
```

`authorize(...)` / `fetch_scope_rule(...)` 放在 `ontostudio/backend/app/auth.py`：前者是对既有 `_gateway_authorizes` 的公开包装（含复合键缓存），后者调用 gateway 的 `/api/permissions/scope` 并把 `rule` 反序列化为本地 `FilterRule`；二者失败均 fail-closed（`False` / `none_allow`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_rest.py -v`
Expected: PASS（2 项）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/routers.py ontostudio/backend/app/auth.py ontostudio/backend/tests/test_actions_rest.py
git commit -m "feat(ontostudio): POST /actions/invoke + 动作级授权(权限+数据范围双层)"
```

---

## Task 8: MCP 暴露面

**Files:**
- Modify: `ontostudio/backend/app/ontology/mcp.py`
- Test: `ontostudio/backend/tests/test_actions_mcp.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_mcp.py
import pytest

from app.ontology.mcp import TOOLS


def _tool(name):
    return next((t for t in TOOLS if t.name == name), None)


def test_invoke_action_tool_registered():
    t = _tool("invoke_action")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"action_id", "pk"}


def test_review_entity_tool_registered():
    t = _tool("review_entity")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"pk", "decision"}
    assert set(t.inputSchema["properties"]["decision"]["enum"]) == {"confirm", "reject"}


def test_action_ids_match_registry():
    """工具暴露的动作 id 必须与 registry 声明一致（防手写清单漂移）。"""
    from app.ontology.registry import get_registry
    declared = set(get_registry().actions)
    assert "review_entity.confirm" in declared
    assert "review_entity.reject" in declared
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_mcp.py -v`
Expected: FAIL —— `invoke_action` 为 None

- [ ] **Step 3: 加工具声明（`_TOOLS_SPEC` 追加两项）**

```python
    (
        "invoke_action",
        "执行一个已声明的受治理动作（写回业务数据并记审计）。先用 describe_ontology 查看可用 action_id 清单与参数。权限与数据范围在服务端强制。",
        {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "如 review_entity.confirm"},
                "pk": {"type": "string", "description": "目标对象主键(uuid)"},
                "params": {"type": "object", "description": "动作参数(按 describe_ontology 声明的形状)"},
            },
            "required": ["action_id", "pk"],
        },
    ),
    (
        "review_entity",
        "审核抽取实体的快捷入口（高频动作的具名包装，内部走同一条动作执行体）。decision=confirm 置 active，reject 置 rejected。",
        {
            "type": "object",
            "properties": {
                "pk": {"type": "string", "description": "实体主键(uuid)"},
                "decision": {"type": "string", "enum": ["confirm", "reject"]},
            },
            "required": ["pk", "decision"],
        },
    ),
```

- [ ] **Step 4: 加分派与处理函数**

在 `call_tool` 的 `handlers` 字典中加入：

```python
        "invoke_action": _invoke_action,
        "review_entity": _review_entity,
```

并在本文件内实现（与既有 handler 同形，返回 `list[TextContent]`）：

```python
async def _invoke_action(arguments: dict):
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    try:
        return _ok(await run_action_for_mcp(arguments.get("action_id", ""), arguments.get("pk", ""), "mcp"))
    except ActionError as e:
        return _err(e)


async def _review_entity(arguments: dict):
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    mapping = {"confirm": "review_entity.confirm", "reject": "review_entity.reject"}
    action_id = mapping.get(arguments.get("decision"))
    if action_id is None:
        return _err(ValueError(f"decision must be one of {sorted(mapping)}"))
    try:
        return _ok(await run_action_for_mcp(action_id, arguments.get("pk", ""), "mcp"))
    except ActionError as e:
        return _err(e)
```

`_ok(...)` 是本文件内与既有 `_err(...)` 对称的小助手（`_err` 已存在）：`return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]`。

> **⚠️ 订正（Task 8 实现者实测）：本节初版把 `default=str` 写成"待补的前向风险"——那个前提不成立。**
> `mcp.py::_ok` **自 `325bb8e47`（后端独立化）起就一直带 `default=str`**，早于整个动作层计划。所谓"当前不可达 + 别等它可达"是**我的误记**。
> 实现者做的正确处理：① 读 `git show HEAD:.../mcp.py` 逐字确认；② 新增 `test_invoke_action_result_survives_datetime` 用 `datetime` 走**真实 `call_tool` → `_invoke_action` → `_ok` 路径**断言 `success is True` 且 `after.updated_at == str(stamp)`；③ 变异删 `default=str` → 该用例红。**即兜底现在被测试钉住，不再只是"碰巧还在"。**
> **教训同"归属语句"那一类**：把"我以为缺"写成待办，会让下一个 Task 把"已完成"当成"要做"——**陈述必须由实测买单**。
>
> **⚠️ 若要动 `_ok`，必须加 `default=str`**（原交接的意图，保留于此以防将来有人真去改它）：
> ```python
> json.dumps(payload, ensure_ascii=False, default=str)
> ```
> 理由：Task 5 把 `after` 从「`now` 列记 `None`」改成了**用 `RETURNING` 取真值**（审计不能说谎）。于是 `now=True` 的列在返回体里是 **`datetime` 对象**，而 `json.dumps` 无 `default=` 会抛 `TypeError: Object of type datetime is not JSON serializable`。
> **当前 registry 无 `now=True` 声明，故不可达**——但那是声明，不是约束：`doc_graph.yaml` 是热加载的，谁加一行 `{field: updated_at, now: true}` 就会让 MCP 工具炸。**加 `default=str` 是零成本，别等它可达。**

`run_action_for_mcp` 放在 `actions/executor.py`（**不是** routers.py）——MCP 层不应依赖 REST 层。它需要在该文件顶部补 `from app.ontology.kernel.service import get_kernel`（`_resolve` 同文件已有）：

```python
async def run_action_for_mcp(action_id: str, pk: str, source: str) -> dict[str, Any]:
    """MCP 侧入口：MCP 走共享头鉴权而非 cookie，故数据范围按服务身份取（域级）。

    EAI-CUSTOM: 设计 §3「今日实际形态」——无身份列时范围只可能是
    allow_all / none_allow 二态，与调用者身份无关；故 MCP 通道直接取
    registry 声明的 scope_resource 对应模块的**服务级**范围（当前恒 allow_all），
    待行级具备归属轴后再按调用者解析。
    """
    from app.ontology.actions.executor import invoke_action_core
    from app.ontology.scope import FilterRule
    action, _obj = _resolve(action_id)
    return await invoke_action_core(
        action_id, {}, target_pk=uuid.UUID(pk),
        actor_id=uuid.UUID(int=0), actor_role="mcp", source=source,
        scope_rule=FilterRule(operator="allow_all"),
        project=lambda aid, p: get_kernel().refresh(),
    )
```

> **这是一处有意的简化**，用 `ponytail:` 注释在代码里标明：MCP 通道当前不区分调用者身份（域级二态下没有可区分的维度）。待行级归属轴落地的任务里必须改成按调用者解析——**这是已知的、被记录的天花板，不是遗漏**。

- [ ] **Step 5: `describe_ontology` 附动作清单**

在 `_describe` 的返回值中追加（与既有字段并列）：

```python
        "actions": [
            {
                "id": a.id, "display_name": a.display_name, "description": a.description,
                "target": a.target, "required_permissions": a.required_permissions,
                "preconditions": [c.model_dump() for c in a.preconditions],
                "postconditions": [c.model_dump() for c in a.postconditions],
            }
            for a in get_registry().actions.values()
        ],
```

- [ ] **Step 6: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_mcp.py -v`
Expected: PASS（3 项）

- [ ] **Step 7: 提交**

```bash
git add ontostudio/backend/app/ontology/mcp.py ontostudio/backend/app/ontology/actions/executor.py ontostudio/backend/tests/test_actions_mcp.py
git commit -m "feat(ontostudio): MCP invoke_action + review_entity 具名包装(共用执行体)"
```

---

## Task 9: lint 扩展 —— scope 绑定校验 **+ 动作声明的作者笔误**

> **本任务的范围在 Task 4 审查后扩大了一条（务必纳入）**：`ontology_lint.py` 目前对 **precondition 的 `value` 零校验**（已 grep 确认）。结果是"注册表里的作者笔误"要等到 **invoke 时**才被 `sql_write` 的三处守卫拒绝、变成 400——而它是**加载期就能查出来的静态错误**。
>
> 典型笔误（都是自然写法，不是构造）：
> - `{field: status, op: not_in, value: rejected}` —— **漏引号**，YAML 给字符串 → `sql_write` 会拒（Task 4 的 C1），但应当在 lint 阶段就报
> - `{field: status, op: in, value: []}` —— 空集
> - `{field: status, op: in, value: 123}` —— 形状错
> - `{field: status, op: in}` —— 漏 value
>
> **要在 lint 里加的检查**：`in`/`not_in` 的 `value` 必须是非空 list/tuple/set；`eq`/`ne` 必须有 value 且非 None（Task 4 的 M1 已把它变成运行期 400，lint 应提前）；`is_null`/`not_null` 不应带 value。
>
> 另有一条**够不到**的，记录在案、不在本任务：`in`/`not_in` 的**目标列是否为数组型**仍无校验（registry 只交叉校验字段存在、不校验类型）。要收它需要 schema 层能拿到列的 PG 类型——属另一个议题。

**Files:**
- Modify: `ontostudio/backend/scripts/ontology_lint.py`
- Test: `ontostudio/backend/tests/test_lint_scope_bindings.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_lint_scope_bindings.py
from app.ontology.schemas import DomainFile


def _ot(**over):
    base = {
        "api_name": "graph_entity", "display_name": "实体", "description": "d", "domain": "doc_graph",
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
    }
    base.update(over)
    return base


def test_object_without_scope_resource_is_fine():
    DomainFile.model_validate({"object_types": [_ot()]})

def test_scope_resource_requires_known_module():
    """scope_resource 必须是已知模块 key（离线模板也要有）。"""
    from scripts.ontology_lint import check_scope_resources
    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="no_such_module")]})
    problems = check_scope_resources(d, known_modules={"ontology", "contract_price"})
    assert problems and "no_such_module" in problems[0]


def test_scope_resource_known_module_passes():
    from scripts.ontology_lint import check_scope_resources
    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="ontology")]})
    assert check_scope_resources(d, known_modules={"ontology"}) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_lint_scope_bindings.py -v`
Expected: FAIL —— `ImportError: cannot import name 'check_scope_resources'`

- [ ] **Step 3: 实现（`ontology_lint.py` 追加）**

```python
def check_scope_resources(domain_file, known_modules: set[str]) -> list[str]:
    """每个 scope_resource 必须是已知模块 key。

    EAI-CUSTOM: 设计 §3。模块 key 取自 config/permissions.yaml 的顶层 modules。
    未知模块会让 DataScopeEngine 返回 none_allow → 动作恒 404。
    """
    problems: list[str] = []
    for ot in domain_file.object_types:
        if ot.scope_resource and ot.scope_resource not in known_modules:
            problems.append(
                f"{ot.api_name}: scope_resource {ot.scope_resource!r} 不是已知权限模块"
                f"（可选：{sorted(known_modules)}）"
            )
    return problems
```

并在 `main()` 中用 yaml 解析 `config/permissions.yaml` 的 `modules` 顶层键取得 `known_modules`，对每个域文件调用 `check_scope_resources`，非空则计入失败并以非零码退出。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_lint_scope_bindings.py -v && PYTHONPATH=. uv run python scripts/ontology_lint.py`
Expected: PASS + lint 退出码 0（真实 registry 全绿）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/scripts/ontology_lint.py ontostudio/backend/tests/test_lint_scope_bindings.py
git commit -m "chore(ontostudio): lint 校验 scope_resource 指向已知权限模块"
```

---

## Task 10: 端到端验收

**Files:**
- Create: `ontostudio/backend/tests/test_actions_e2e.py`

- [ ] **Step 1: 写验收测试（对应 spec §7 的 6 条）**

```python
# ontostudio/backend/tests/test_actions_e2e.py
"""spec §7 端到端验收。需要 ONTOSTUDIO_GATEWAY_URL 可达（容器网络内跑）。"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.connectors import _ext_url
from app.ontology.kernel.service import get_kernel

pytestmark = pytest.mark.integration


async def _seed(status="pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text("""INSERT INTO dg_entities (domain,etype,canonical_name,norm_name,attrs,confidence,status)
                        VALUES ('doc_graph','mine','E2E', :n, '{}'::jsonb, 0.9, :s) RETURNING id"""),
                {"n": f"E2E-{uuid.uuid4().hex[:8]}", "s": status},
            )
            return r.scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_01_confirm_then_shacl_clean():
    """① pending_review → confirm → active，审计有行，重投影后 SHACL 无违规。"""
    pk = await _seed()
    get_kernel().refresh()                      # 投影前
    # 通过 run_action_for_mcp 走完整链路
    from app.ontology.actions.executor import run_action_for_mcp
    result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert result["after"] == {"status": "active"}

    from app.ontology.kernel.conformance import run_conformance
    from app.ontology.registry import get_registry
    checks = run_conformance(get_kernel().store, get_registry())
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


@pytest.mark.asyncio
async def test_02_precondition_violation_is_409():
    pk = await _seed(status="active")
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    with pytest.raises(ActionError) as e:
        await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_04_projection_failure_recorded_not_rolled_back():
    """④ 投影失败：业务状态已提交、errors 有记录。"""
    pk = await _seed()
    from app.ontology.actions.executor import invoke_action_core
    from app.ontology.scope import FilterRule

    def boom(*a, **k):
        raise RuntimeError("proj boom")

    r = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk, actor_id=uuid.uuid4(),
        actor_role="admin", source="api", scope_rule=FilterRule(operator="allow_all"), project=boom,
    )
    assert r["projected"] is False and r["errors"]


@pytest.mark.asyncio
async def test_05_lint_reports_unbound_scope_field():
    """⑤ lint 对"模板字段无绑定"报错（用一个构造出的坏绑定）。"""
    from app.ontology.schemas import DomainFile
    with pytest.raises(ValueError, match="unknown scope binding"):
        DomainFile.model_validate({
            "object_types": [{
                "api_name": "x", "display_name": "x", "description": "d", "domain": "d",
                "access": {"path": "postgres_ext", "table": "t"},
                "pk": {"column": "id", "api_name": "id", "type": "uuid"},
                "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
                "scope_bindings": {"user_id": "missing_col"},
            }],
        })
```

> **⚠️ 订正（Task 9 实现者预警）**：本用例初版末尾有 `.validate_action_refs()` —— **那个方法在 Task 2 就已被 `@model_validator(mode="after") _check_refs` 取代**（见本计划 Task 2 的偏离表），照抄会以 `AttributeError` 失败，而 `unknown scope binding` 其实**由 `model_validate` 直接抛出**。现已删掉那个调用。
>
> **这是"计划里的陈旧符号引用"第二次咬人**（第一次是 Task 6 的 `test_cross_file_...` docstring）——**删一个公开方法时，必须同时清理全计划对它的调用**，否则下一个照抄的 Task 会撞上一个"看起来该存在"的方法。

③（无 `ontology:action:review` → 403）与 ⑥（lint 真实 registry 全绿）在 Task 6 与 Task 9 已各自覆盖，此处不重复；验收时把两处测试的通过结果一并记录。

- [ ] **Step 2: 跑验收**

Run:
```bash
cd ontostudio/backend && PYTHONPATH=. uv run pytest tests/test_actions_e2e.py -v
```
Expected: PASS（4 项）

- [ ] **Step 3: 重启容器并做一次真人路径验证**

> **⚠️ 订正（Task 10 实跑，2026-09-24）**：`restart` **不够**——`ontostudio-backend` 不 bind-mount 代码（compose 只挂 kernel 卷），镜像烘焙 `COPY app ./app`；实跑时活容器里**连 `app/ontology/actions/` 都不存在**（`/openapi.json` 只有 21 条路由、无 `actions/invoke`）。**必须先 build**（deps 层有缓存，实测秒级）。另：下面那条 `docker exec … get_kernel().refresh()` 会撞 pyovigraph 的 `/data/kernel/LOCK`（服务进程持锁）——本轮重建后偶然可取，**别依赖**；等价 HTTP 面是 `POST /formal/infer` / `GET /formal/validate`。

```bash
cd ../../docker
docker compose -p eai-docker -f docker-compose-dev.yaml build ontostudio-backend   # ← 订正：restart 不会带进代码
docker compose -p eai-docker -f docker-compose-dev.yaml restart gateway ontostudio-backend
docker compose -p eai-docker -f docker-compose-dev.yaml up -d ontostudio-backend
# 建表由 ontostudio 自身 lifespan 的 ensure_tables() 负责（app/db.py）；
# 下面这条只是确认表真的在（修复前 to_regclass 为 null）
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\dt dg_action_audit"
# 内核重载（⚠️ 上面的订正：容器内直调会撞 LOCK；等价 HTTP 面更稳）
curl -s -X POST http://localhost:8005/api/extensions/ontology/formal/infer   # 需带 Cookie，见 `app/auth.py`
```
Expected: `dg_action_audit` 出现在 `\dt` 列表；infer 的 `errors=[]`

- [ ] **Step 4: 提交**

```bash
git add ontostudio/backend/tests/test_actions_e2e.py
git commit -m "test(ontostudio): 动作层端到端验收(spec §7)"
```

---

## 收尾（不属任何单个 Task）

- [ ] **⚠️ 本计划全部测试在 CI 里不会被执行**（Task 1 审查实测发现）：`.github/workflows/backend-unit-tests.yml:118-120` 明写 ontology 域 CI 职责"由 ontostudio 侧后续自建"，而 `.github/workflows/` 下**没有任何 ontostudio workflow**。叠加 `pytestmark = pytest.mark.integration`（需外部 PG，多数环境 skip），实际效果是 **ontostudio 的 33 条单测 + 集成测试都只在人手执行时跑**。这使本计划里所有"回归护栏"的承诺降级为"人手护栏"。**是否补 CI 需单独决策**（新增 workflow 是仓库级改动，不属本计划范围）；但**决策前不要假设这些测试会在 PR 上自动拦住回归**。

- [ ] **`scope.py` 的 docstring 措辞需收窄**（Task 1 复审 Minor）：类 docstring 写"**所有**畸形输入都归一到这里"，被深层嵌套证伪——实测 3000 层 → `RecursionError` 且 `isinstance(e, ScopeCompileError)` 为 `False`。但该路径**经 HTTP 不可达**（`json.loads` 对同深度 payload 先抛 `RecursionError`，请求层比 `from_wire` 先死），故不需代码改动，只需把措辞收窄为"所有**形状**畸形输入"，或注明"深度递归由请求边界兜底"。**要点是别让 Task 5 读到绝对承诺而以为不必兜 `RecursionError`。**


- [ ] 全量回归：`cd ontostudio/backend && PYTHONPATH=. uv run pytest tests/ -v` 与 `cd backend && PYTHONPATH=. uv run pytest tests/ -k "auth or permissions" -v`
- [ ] `ruff check . && ruff format --check .`（ontostudio/backend 与 backend 各跑一次）
- [ ] 更新 `.wolf/anatomy.md`（新增 4 个文件）与 `.wolf/memory.md`
- [ ] **未纳入本计划**（属 spec §4 的折叠步）：`merge_entities` / `unmerge` 折叠为动作、删除旧实现。**必须另起计划**，且在本计划全部 Task 绿之后才能开工。
