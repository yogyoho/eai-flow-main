# Design: self-improving 自进化循环移植（零 harness / 零既有代码改动版 capture → dedup → promote → extract）

> 来源：github.com/peterskoett/self-improving-agent (v4.0.2) 分析 + 8-agent 评审面板（3 scout 挂载点验证 + 3 独立设计 + 2 judge 打分），2026-09-11/12。
> 克隆留档：`D:\eai\_analysis-self-improving-agent`。完整分析结论见 `.wolf/memory.md` 2026-09-11/12 条目。

## 问题与目标

原版 skill 在 OpenClaw 平台上实现了一个经验自进化闭环：捕获（learnings/errors/feature-requests 三日志 + 会话末自动 sweep）→ 去重（Pattern-Key `area.symptom` 分类法，折叠而非新增）→ 晋升（量化规则：recurrence≥3 且跨≥2任务且≤30天 → 写入永久注入的系统提示文件）→ 提取（满足 5 条件之一 → 脚手架出新 skill）。

目标：把该闭环移植到 DeerFlow/EAI 平台，硬约束为 **零改动 harness（`deerflow/*`）与 gateway（`app/gateway/*`）的任何既有文件**——只新增文件 + 配置条目，完全落在 `no-core-code-changes` 规则内，上游同步零冲突面。

### 平台已有原语（scout 已验证，不重建）

| 原语 | 位置 | 作用 |
|---|---|---|
| `skill_manage` 工具 | `deerflow/tools/skill_manage_tool.py:262`（create）、`:158/176/202`（缓存刷新） | agent 运行时创建/patch per-user custom skill；名称正则 + 防覆盖 + 双重安全扫描 + (user,skill) 锁 + 历史 + prompt 缓存失效，全继承 |
| per-user 存储 | `storage/__init__.py:107-108` → `users/{uid}/skills/custom/` | 平台唯一 per-user 跨线程 markdown 存储（注意：`/mnt/user-data` 是 per-THREAD，不能当 ledger） |
| 系统提示注入 | `lead_agent/prompt.py:827-870` `<available_skills>` | 每个 enabled skill 的 name+description 永久注入 → description 即"晋升面" |
| skills 投影 | `deerflow/skills/projection.py` → `/mnt/skills` | agent 按需读 skill 正文 |
| MCP stdio 配方 | `app/extensions/data_source/mcp.py`、`app/extensions/ontology/doc_graph/mcp.py` | 新扩展暴露 agent 工具的既定模式 |
| RunEventStore | `deerflow/runtime/events/store/`，`list_messages_by_run(thread_id, run_id)` | 结构化事件读取（app→deerflow import 方向合法） |
| extensions 模板 | `app/extensions/eia_samples/`（models/Base/create_all）、`doc_graph/mcp.py`（stdio） | 新模块照抄的房屋风格 |
| `update_agent` 工具 | custom-agent 会话已绑定 | 写 agent 的 SOUL.md = 原版"晋升到 SOUL.md"的精确对应物 |

## 决策记录（本设计已拍板）

| # | 决策 | 依据 |
|---|---|---|
| D1 | 砍掉 harness 中间件方案（原 P3，judge 66/81 分） | 3 个 hunk 在上游最常合并冲突文件；extensions-only 已足够 |
| D2 | 零改动任何既有代码文件；连 `deps.py:515` fan-out 也不做 | 用户明确要求不碰核心；自动 sweep 改 **lazy catch-up ingest**（读取时补扫） |
| D3 | P0 条目 schema 与 P1 SQL schema 完全一致，P1 写一次性 importer 吸收 ledger | 数据前向兼容，P0 不产生废数据 |
| D4 | 捕获双通道：判断类（纠正/知识过时/更好做法）= agent 自觉（skill 教学）；机械类（工具错误）= lazy sweep | 原版哲学 learning is delayed；sweep 只扫 `role=="tool"` 结构性消灭原版"把 agent 的话当错误"弱点 |
| D5 | ~~`user_id` 永不出现在 MCP 工具参数；身份由服务端 thread→user 反查~~ **已被 OV2 升级**：身份由子进程 **cwd 工作区路径推导**（平台不配 cwd 时自动把子进程 cwd 锁到调用者 thread 工作区，路径编码真实 user/thread），`sys.path.insert` 免掉 `cwd=/app/backend` 依赖；推导失败 **fail-closed 拒绝**。user_id/thread_id 均不再信任模型参数 | OV2：thread_id 是模型给的，纯反查=可被幻觉/注入的 thread_id 写穿到他人账本+读泄漏；cwd 推导堵死读写两路 |
| D6 | `pattern_key` 由服务端从 enum 参数 canonicalize，agent 不能自造 key | 原版教训：自由文本 key 使 recurrence 不可数 |
| D7 | 晋升/提取全走 `skill_manage` 既有管线，永不自动创建 skill | 白拿安全扫描+历史+缓存失效；保持 human/agent-in-the-loop |
| D8 | 脱敏→fence 转义→200字符截断，固定顺序，单测钉死 | 原版正确设计，防止泄密 + 防止截断后的 markdown 越狱 |

### 2026-09-12 eng-review 增补决议（D9-D15）

| # | 决策 | 依据 |
|---|---|---|
| D9 | 价值定调：**维持 P0+P1 全量计划**（用户拍板，否决实验框架缩减）。证据：库内 292 runs 中 **37% error**、run_events 表 11,672 行无人挖、feedback 表 **0 行**（显式反馈通道无人用→恰好证明需要零用户努力的隐式捕获） | 2026-09-12 只读查询 dev 库实证 |
| D10 | P1 裁剪到 ~8 文件：`schemas.py` 内联进 service；首版 **4 工具**（surface/log_learning/stats/resolve），`search`/`get` 延后（去重由 log_learning 服务端强制，回顾由 surface 承担） | 复杂度门（11 文件>8 阈值）；少工具=小提示面=高 agent 合规 |
| D11 | lazy 补扫 **按 thread 扫域**（surface 被调的 thread 才扫）+ **每次 ≤20 个未扫 run（新→旧）+ 仅近 30 天**，更老 run 永不回填（receipts 预种游标） | A1 + OV4：RunEventStore API 天生 (thread,run) 键控；agent 面向工具的响应时间必须有界 |
| D12 | sweep 幂等**唯一归 `learning_sweep_receipts`**（扫过的 run 永不重扫）；命中即无条件折叠 recurrence+1；**删除 event_hash 唯一约束**（相同错误文本 hash 相同，唯一约束会让最高频错误的 recurrence 永卡 1，晋升门失效） | OV3：一个字段不能同时背幂等和计数两个职责 |
| D13 | `agent_learnings` **砍掉 `quarantined`/`priority` 两列**（零触碰版无生产者/消费者）；将来加纠正启发式时一次 ALTER（extensions/database.py 机制现成） | CQ1：无消费者的列=投机抽象 |
| D14 | 约束面补强：每个 learnings_* 工具**响应尾部由服务端拼 pending 计数行**；skill 把"非平凡任务前必调 surface"从建议升为**硬规则**。系统提示注入（prompt.py）留给约束解除后的 P2 | OV5：零触碰内最强约束面，不依赖模型自觉 |
| D15 | P0→P1 **硬切换**：P1 验收通过即关 P0 捕获 flag（skill 转只读归档角色）→importer 一次性吸收→ledger 冻结为历史档；单一真相源，回退=重开一条 flag | OV9：并行双捕获=计数分歧+importer 变持续对账 |
| D16 | **不建独立管理页**（P0/P1 阶段）：可见性三层免费获得——①现有 workspace 技能管理页（`skill-settings-page.tsx`：list/enable/安装，gateway 另有 history/rollback）直接展示 ledger 与 learned-behaviors；②agent 问答式透明（stats/surface + D14 响应尾注）；③`enableSkill` 开关=**紧急停止**（禁用 learned-behaviors 即撤销全部晋升规则的注入）。P2 triage 页按**四条触发条件**驱动（见 TODOS.md）：错误晋升事故 / pending 积压超 agent 处理能力 / 企业客户合规审计要求 / 多租户运营健康度视图 | 2026-09-13 用户问询"黑盒"问题；行为层本就透明（住在技能页），草稿层（SQL）无 UI 是零触碰的故意取舍 |

另：OV1（冷 thread 身份反查循环）与评审 A2 独立撞车互证，最终由 D5 的 cwd 推导方案整体取代（cwd 同时给出权威 user+thread，冷启动问题不复存在）；OV8（[learn:N] 依赖 patch frontmatter description）**已当场证伪**——`skill_manage_tool.py:179-203` patch 对含 frontmatter 的全文做 replace，`skill_storage.py:65-77` 校验只锁 name 与目录一致，description 自由，patch 后 `:202` 缓存刷新。

## 总体架构

```
┌─ P0（纯 skill，零代码）────────────────────────────┐
│ skills/public/self-improving/SKILL.md  （循环教学）  │
│   ├ 判断类捕获：agent 按触发表调 skill_manage        │
│   ├ ledger = per-user custom skill `learnings-ledger`│
│   │   description 带 [learn:N] 计数 = 永久注入的 nag │
│   └ 晋升：learned-behaviors / update_agent(SOUL.md)  │
│       提取：skill_manage create（5 条件）            │
└──────────────┬───────────────────────────────────┘
               │ P1 importer 一次性吸收（schema 同构）
┌─ P1（extensions/learnings 模块，新增文件 only）────┐
│ backend/app/extensions/learnings/                   │
│   ├ mcp.py  stdio server `learnings`（5 工具）       │
│   ├ sweeper.py  lazy catch-up：surface/stats 调用时  │
│   │   先补扫未 sweep 的 terminal runs（幂等 receipts）│
│   ├ patterns.py  ordered 字面量表 + 脱敏管线          │
│   ├ service.py  mint-or-fold (user_id, pattern_key)  │
│   └ models.py  agent_learnings 表（自建 create_all） │
│ 配置：extensions_config.json mcpServers.learnings    │
│   （根 + offline 模板，手编；admin API 白名单不收 python）│
└──────────────┬───────────────────────────────────┘
               │ 可选后续
┌─ P2（可选，届时才碰 app.py 一行）──────────────────┐
│ 独立 poller 容器（实时 sweep）或 triage UI（HTTP 路由）│
└───────────────────────────────────────────────────┘
```

## P0 详细设计：纯 skill 层（~2-3 人日）

### 文件

- `skills/public/self-improving/SKILL.md` —— 循环教学（触发表/捕获纪律/pattern-key 协议/折叠·resolve·晋升·提取步骤/ledger 模板/抑制规则）
- `skills/public/self-improving/references/pattern-keys.md` —— 11 领域 × symptom 分类法 + 条目 schema + `[learn:N]` 计数规则
- `extensions_config.json` + `deploy/offline/extensions_config.json` —— skills map 加 `"self-improving": {"enabled": true}`（默认 false，按部署开启）

### Ledger（每用户一个 custom skill）

- 首次捕获时 agent 用 `skill_manage(create)` 建 `learnings-ledger`（名称冲突即 fail-closed，天然幂等）
- 正文结构：格式说明 + `<!-- LEDGER-START -->` / `<!-- LEDGER-END -->` 哨兵括起的条目区 + `## Resolved archive` 压缩归档区；**体积守卫**：条目区 ~50 条时把 resolved 低龄条目压一行进 archive（防 ledger 无限膨胀拖慢 patch/投影）
- patch 失败自愈（哨兵被 UI 编辑破坏）：SKILL.md 教 agent 重新读取 ledger→补哨兵→重试 patch；patch 语义已验证（`skill_manage_tool.py:179-203` 全文 replace + 校验只锁 name）
- frontmatter description 即 nag token：`"User lessons ledger [learn:2]. Read /mnt/skills/learnings-ledger/SKILL.md before non-trivial tasks"` —— agent 每次捕获/resolve 后重写 N（经 `skill_manage patch`，缓存自动失效）。计数字可能过期，降级为静态描述，无害
- 条目 schema（与 P1 SQL 同构）：

```markdown
### L-014 | deps.module-not-found | status:pending | count:2
summary: pnpm install 在 node:22 镜像缺 node-gyp
evidence: ```ERR! 404 ...```
first: 2026-09-12 | last: 2026-09-12 | threads: t1,t2
action: 用基础镜像预装 build-essential
```

### 触发表（教学核心）

| 触发 | 动作 |
|---|---|
| 用户纠正（"不对/应该是/其实…"，中英双语） | 捕获 kind=correction |
| 命令/工具失败且修复非显而易见 | 捕获 kind=error，pattern_key 按分类法 |
| 用户要的能力不存在 | 捕获 kind=feature_request |
| 外部 API/依赖失败 | 捕获 kind=error |
| 所依赖知识过时 | 捕获 kind=knowledge_gap |
| 发现可复用的更好做法 | 捕获 kind=best_practice |

**抑制规则**（防原版噪声弱点）：① 已在 run 内解决的瞬态失败（typo/漏参数）不捕获；② ledger 已有同 pattern_key 条目 → 折叠（patch 递增 count/last）而非新增；③ 捕获前必须先读 ledger（reuse-before-mint）。

### 捕获纪律（固定顺序，写进 SKILL.md）

1. **脱敏**：token/secret/password 赋值、Bearer、sk-/ghp_/xox[baprs]-/AKIA/eyJ… 一律抹除
2. **fence 转义**：``` → '''（防 markdown 越狱）
3. **截断**：evidence ≤200 字符

### 晋升（行为改变）与提取（能力改变）

- **晋升资格**：count≥3 且 跨≥2 thread 且 last-first≤30天（agent 维护计数）
- 行为晋升（workspace 会话）：压缩成祈使句写入 `learned-behaviors` custom skill 的 **description**（`<available_skills>` 永久注入 = 原版 SOUL/TOOLS/AGENTS.md 晋升的等价物）；custom-agent 会话：`update_agent` 写 SOUL.md
- 提取（满足原版 5 条件之一：重复/已验证/非显而易见/跨项目/用户点名）：`skill_manage(create, 新skill)` —— 名称正则、防覆盖、双重安全扫描、历史全继承；成功后原条目 status→`promoted_to_skill` + `promoted_skill:` 回链

## P1 详细设计：extensions/learnings 模块（~5-6 人日）

### 模块布局（全部新增，零既有文件改动；D10 裁剪后 ~8 文件）

```
backend/app/extensions/learnings/
├── __init__.py      # 导出；不 import 进 gateway（零触碰的关键）
├── models.py        # AgentLearning + LearningSweepReceipt，挂共享 Base
├── patterns.py      # ordered 字面量表 + 脱敏/fence/截断管线
├── service.py       # mint-or-fold / 资格计算 / 状态机 / Pydantic 校验内联（D10）
├── sweeper.py       # lazy catch-up ingest（D11 有界）
├── mcp.py           # stdio server（doc_graph 模板；顶部 sys.path.insert 免 cwd 依赖）
└── scripts/import_ledger.py   # P0 ledger → SQL 一次性导入（兼作 P0 格式测试）
backend/tests/test_learnings_patterns.py
backend/tests/test_learnings_service.py
backend/tests/test_learnings_sweeper.py      # T1：幂等/去重/角色过滤/cap/截止
backend/tests/test_learnings_mcp.py          # T1：4工具契约/身份绑定/冷thread边界
```

环境开关直接读 env（无独立 config.py，D10）。**表创建**：gateway 不 import 本模块（零触碰），由 MCP server 子进程启动时自行 `init_engine + create_all`（同 Base、同 agentflow 库）。运维注：若 MCP 入口长期禁用则表永不建，需要时手动 create_all 一次；实施时 `\d runs` 确认 `runs.thread_id` 索引存在（补扫查询依赖）。

### 数据模型（正典 schema —— P0 条目格式与 P1 SQL 均以本节为唯一来源）

`agent_learnings`（agentflow 库）：

| 列 | 说明 |
|---|---|
| id | UUID PK |
| user_id | 索引；per-user 隔离键（cwd 推导，非模型参数） |
| kind | error\|correction\|knowledge_gap\|best_practice\|feature_request |
| area / symptom | enum；`pattern_key = area.symptom`；复合索引 (user_id, pattern_key) |
| summary | ≤200 字符 |
| details / suggested_action | 自由文本 |
| status | pending → resolved \| dismissed \| promoted_to_skill |
| recurrence_count / first_seen_at / last_seen_at | 折叠计数（D12：命中必递增） |
| distinct_thread_count | 晋升资格用（折叠时由 source_thread_ids 派生更新） |
| source | agent \| sweep |
| source_thread_id / source_run_id | 溯源（对 core 库软引用） |
| promoted_skill | 提取回链 |

> CQ1 已砍：`quarantined`（无生产者——纠正启发式方案已砍）、`priority`（无消费者——资格判定与 surface 排序均不用）；OV3 已砍：`event_hash`（其唯一性与 recurrence 计数互斥，幂等唯一归 receipts）。将来补列走 extensions/database.py 的 ALTER 机制。
> 实现注记（prior learning: pydantic-default-fill-create-trap，2026-08-07）：service create/patch 路径必须 `exclude_unset` 或显式全字段载荷，防布尔/enum 默认值静默填充。

`learning_sweep_receipts`：run_id PK + swept_at —— **唯一的 sweep 幂等凭据**（D12）。

### MCP stdio server `learnings`（4 工具，D10 裁剪后）

注册（**手编两份配置**，admin API 的 stdio 白名单只收 npx/uvx，见风险 R3）。**不配 `cwd`**（OV2 身份绑定的前提——平台会把子进程 cwd 自动锁到调用者 thread 工作区）：

```json
"learnings": {
  "enabled": true, "type": "stdio",
  "command": "/app/backend/.venv/bin/python",
  "args": ["-m", "app.extensions.learnings.mcp"],
  "cwd": null,
  "env": {}, "url": null, "headers": {}, "oauth": null,
  "description": "Agent self-learning loop: capture/search/promote learnings"
}
```

`import app` 依赖改为 mcp.py 顶部 `sys.path.insert(0, "/app/backend")`（显式 hack，bug-712 的 cwd 方案与身份绑定互斥，二选一）。工具名经适配器加前缀 → agent 看到的是 `learnings_<tool>`。

**身份绑定（D5 终版 = OV2）**：mcp.py 启动时从 `os.getcwd()` 解析所在 thread 工作区路径 → 得到权威 `(user_id, thread_id)`；解析失败 **fail-closed 拒绝所有写**（回退只读空响应+警告日志）。模型传入的 thread_id 仅作交叉校验（与 cwd 推导不符即拒绝），永不信为身份来源。

| 工具 | 签名要点 | 行为 |
|---|---|---|
| `learnings_surface` | thread_id 可选（交叉校验用）；limit=5 | **先 lazy ingest 再返回**（D11：只扫本 thread；每次 ≤20 个未扫 run，新→旧；仅近 30 天，receipts 预种游标更老 run 永不回填）→ pending 按 (recurrence desc, last_seen desc)；资格条目带 eligible_for_skill=true |
| `learnings_log_learning` | summary/kind/area 必填；symptom enum 可选；**无 user_id/thread_id 身份参数** | 身份取 cwd 推导值；pattern_key 服务端 canonicalize；mint-or-fold |
| `learnings_stats` | 无身份参数 | 按 status/kind 计数、top-pending、promotion_candidates、pending nag 数 |
| `learnings_resolve` | learning_id + note | status→resolved（停止 nag） |

**约束面（D14）**：所有工具响应尾部由服务端拼一行 `[{pending} pending learnings | {n} promotion-ready]`；SKILL.md 硬规则："非平凡任务开工前必须先调 learnings_surface"。
> D10 已裁：`learnings_search`/`learnings_get`（去重由 log_learning 服务端强制，回顾由 surface 承担；将来补齐需二次动 inputSchema，可接受）。

### Lazy catch-up sweep（sweeper.py；A1 + OV4 有界化）

1. `surface` 被调 → **只扫当前 thread**（cwd 推导；receipts 表差集 + 仅近 30 天 + 每次 ≤20 个未扫 run，新→旧；run 记录只读查询，app→deerflow 方向合法）
2. 每 run：`list_messages_by_run` 取 `role=="tool"` 且 `status=="error"` 的 ToolMessage + `list_events(event_types=["run.error","llm.error"])`
3. ordered 字面量表（17 条，specific→generic 首匹配）打 pattern_key → 脱敏→fence→截断 → 每 sweep 上限 5 条 → **无条件 mint-or-fold（recurrence+1，D12）**
4. 写 receipts（唯一幂等凭据）；**全程 try/except log-warning，永不 raise，永不影响 run**（sweep 在 run 结束之后才发生，天然无热路径风险）

依赖文档化：RunEventStore 必须为 SQL/JSONL 后端（memory-backed dev store 丢数据；dev 库已实测 run_events SQL 表 11,672 行，天然满足）。

### P0→P1 切换语义（D15 = OV9）

P1 验收（Success Criteria P1 全绿）当天执行硬切换：① `extensions_config.json` 两份中 `skills.self-improving.capture` 置 false（skill 保留只读/归档角色，回答"历史教训在哪"）；② 跑一次 `import_ledger.py`（P0 条目 → SQL，幂等）；③ ledger 冻结为只读历史档。**禁止并行双捕获**（计数分歧）；回退 = 重开 P0 flag（一条开关）。

### 晋升路径（与 P0 相同语义，SQL 判定资格）

资格 = `status=pending AND recurrence_count>=3 AND distinct_thread_count>=2 AND last_seen_at>=now()-30d`，由 service.py 确定性计算，`surface` 返回 `eligible_for_skill`。执行仍是 agent（或人工）调 `skill_manage` —— 零新晋升机制。

### "学到的东⻄"边界表（OV6+7 决议：五面是生命周期梯子，非平行真相源）

| 面 | 装什么 | 生命周期 | 真相源 |
|---|---|---|---|
| `.learnings`-类原始条目（P0 ledger / P1 `agent_learnings`） | 单次错误/纠正/缺口的**原始证据** | pending→resolved/promoted | P1 上线后 = SQL（D15 硬切换） |
| `learned-behaviors` skill description | 晋升后的**压缩规则**（可执行祈使句） | 随新证据 patch | 永久注入面 |
| SOUL.md（custom-agent 会话） | 行为/风格类规则的**人格化归宿** | update_agent 增量 | 永久注入面 |
| memory facts（MemoryMiddleware/deermem） | 用户**事实偏好**（非错误教训），无 lifecycle | 系统自管 | 独立通道，与 learnings 不互写 |
| `.wolf/*`（dev 侧，Claude Code） | **平台开发**的学习，非 runtime | dev 协议管 | 与本设计零交集 |

规则：一条知识同一时刻只住一层；晋升 = 移动而非复制（原条目标 promoted）。

### 价值基座（D9，2026-09-12 dev 库实证）

292 runs 中 **107 error（37%）**；`run_events` SQL 表 **11,672 行**（6,954 条 tool.result）持久化但无人挖掘；`feedback` 表 **0 行**——显式反馈通道无人使用，恰是"需要零用户努力的隐式捕获"的直接证据。P1 上线后 sweeper 的食物已就位（SQL 后端前提已满足）。

### 用户可见性与紧急停止（D16 正典）

| 层 | 用户看到什么 | 入口 |
|---|---|---|
| 行为层（晋升规则） | learned-behaviors skill 正文与 description——**这就是改变 agent 行为的全部内容** | 现有 workspace 设置→技能管理页；可看/可停/可删，gateway history/rollback |
| 提醒层 | `[N pending \| M promotion-ready]` 尾注 + agent 对"你学了我什么"的问答（stats/surface） | 每次工具响应；对话内随时可问 |
| 草稿层（原始条目） | P1 阶段无 UI（零触碰取舍）；P2 触发条件满足时建 triage 页 | P2：`/api/extensions/learnings`（届时 app.py 一行） |
| **紧急停止** | 禁用 learned-behaviors → 全部晋升规则退出系统提示；禁用 self-improving → 循环停转；均即时生效（缓存失效路径现成） | 技能管理页开关，零新代码 |

## 配置与开关

| 开关 | 位置 | 默认 |
|---|---|---|
| P0 skill 启用 | extensions_config.json skills.self-improving.enabled（根+offline 两份） | false |
| P1 MCP server | extensions_config.json mcpServers.learnings.enabled（根+offline 两份） | false |
| sweep 上限/截断长度 | learnings/config.py 环境变量 | 5 / 200 |

配置热加载：MCP 配置变更经 content-signature 自动失效缓存，**无需重启 gateway**（杀 in-flight run 的风险为零——这也是选 stdio 子进程模式的原因之一）。

## 隔离与安全

- 每用户：行级 user_id 隔离；ledger 是 per-user custom skill（UserScopedSkillStorage 天然隔离）
- 身份：D5，user_id 永不由模型提供
- 脱敏：D8 固定顺序 + 单测钉死顺序不变量
- 失败可观测：MCP handler/sweep 全部 fail-open + logger.warning（带 thread/run id）；禁止原版"fail-silent 无信号"弱点
- 提示注入面：evidence 经 fence 转义 + 截断；晋升正文经 skill_manage 双重安全扫描

## 范围外（Non-goals）

- 不做 harness 中间件 / prompt.py 注入 / deps.py 接线（未来可选，见 P2）
- 不做自动晋升、自动建 skill（永远 human/agent-in-the-loop）
- 不做判断类（纠正）自动配对——agent 自觉捕获承担（P0/P1 语义一致）
- 不解决 .wolf 系列文件无限增长（独立问题，bug-3300 修复另行处理）

## Success Criteria

**P0**：双用户 × 双 thread E2E——捕获→折叠（count 递增）→resolve 停 nag→晋升→提取新 skill（安全扫描通过）；`[learn:N]` 在下一消息的 `<available_skills>` 可见；全程零 gateway 重启；P0 条目可被 importer 无损读出。**加 T2 脚本化 3 场景 eval**（复用既有 API 测试通道 login+runs/stream+skills API 读 ledger）：①新会话种入用户纠正→断言 ledger 出现 correction 条目；②种入工具错误→断言 error 条目 pattern_key 正确；③同 pattern_key 二次触发→断言折叠（计数递增）非新增。SKILL.md 后续任何改动重跑此 eval。

**P1**：植入的工具错误被 lazy sweep 捕获且 pattern_key 正确；同 pattern_key 折叠计数正确（T1：sweeper 幂等/receipts 唯一/cap 20/30 天截止/角色过滤单测 + MCP 契约测试含 cwd 身份绑定与 fail-closed 边界）；跨用户零泄漏（cwd 推导错误 thread_id 拒绝）；`skill_manage` 晋升链路（扫描+历史+缓存失效）E2E；两份 extensions_config.json 同步注册后热加载生效、无重启；工具响应尾注 pending 计数存在（D14）。

## 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | P0 捕获纯靠 agent 自觉，计数可能虚报/漏报 | 接受（87 分方案独立成立）；P1 服务端 canonical 计数接管机械类 + **D14 响应尾注/硬规则补强约束面**；importer 以 SQL 为真相源 |
| R2 | `[learn:N]` 过期 | 降级无害；P1 的 stats 工具给准确数 |
| R3 | 手编 extensions_config.json：格式错误会卡配置重载 | 逐字复制 9 个现存 python stdio 条目的 shape（**注意 D5 终版 cwd 为 null**，与现有 9 条不同——单测校验本条目 shape）；根+offline 两份同步改（ea751e632 惯例）；改后 POST /api/mcp/cache/reset 验证 |
| R4 | MCP server 首调冷启动（子进程 spawn 数秒） | 一次性成本，接受 |
| R5 | skill_manage 高频 patch 造成 per-user prompt 缓存抖动 | 晋升资格门槛天然限频；失效半径=单用户 |
| R6 | dev 环境 memory-backed event store 丢 sweep 语料 | 已实测 dev 库 run_events SQL 表 11,672 行，满足；文档保留 SQL 后端要求 |
| R7 | P0→P1 schema 漂移 | D3+正典 schema 单列一节（数据模型节为唯一来源）；importer 以 P0 格式为输入契约；D15 硬切换杜绝并行期漂移 |
| R8 | **sys.path hack 与 workspace 路径约定耦合**（OV2 代价）：上游改 per-thread 工作区路径布局 → cwd 推导失败 | fail-closed：推导失败拒绝写+警告日志（不静默变弱）；上游同步时将 `mcp.py` 路径解析列入 EAI 检查清单 |

## 工作量

| 阶段 | 内容 | 估算 |
|---|---|---|
| P0 | 2 个 skill 文件 + 2 份 config + Docker 内 E2E 验证 + **T2 脚本化 3 场景 eval** + 文档 | 2.5-3.5 人日 |
| P1 | 模块 7 文件（D10 裁剪后）+ 4 MCP 工具 + 有界 lazy sweep + importer + **4 个测试文件（T1）** + E2E | 5-6 人日 |
| P2（可选，见 TODOS.md） | poller 容器 / triage UI（届时 app.py 一行 include_router）/ 约束解除后的系统提示注入 | 另议 |

## P0 实施记录(2026-09-13,已上线验证)

**交付物**:`skills/public/self-improving/SKILL.md` + `references/pattern-keys.md` + `scripts/eval_p0.py`(T2 脚本化 3 场景 eval);`extensions_config.json`(dev=true)与 `deploy/offline/extensions_config.json`(prod=false)开关;`config.yaml` skill_evolution.enabled=true。

**D17(实施中新发现的前置条件)**:P0 依赖 `config.yaml` 的 `skill_evolution.enabled=true`(harness `tools.py:118-120` 仅在该开关下绑定 skill_manage 工具)——设计初稿遗漏,eval 第 1 轮暴露。

**eval 驱动的 5 轮修复**(每轮 dump 真实 run 定位根因):
1. skill_manage 未绑定 → D17
2. description 路由太弱:显式"记录教训"请求被 agent 用 user-data 文件自行处理 → description 加强制路由(账本=custom skill,禁 user-data)
3. agent 用 `write_file` 改 SKILL.md 本体连环报错至递归爆栈 → §4a 工具使用契约(write_file 仅限附属文件;禁直接路径写)
4. 折叠进 resolved 条目未重开 → §4 生命周期规则(重开 pending)
5. 环境考古耗尽步数(guardrails 拦截每个探针烧 2 步)→ §3.4 先记录后深究 + §4 逐字调用模板(点破 new_str/replace 参数混淆陷阱 + 哨兵插入配方)

**最终 eval 结果(3/3 PASS,exit 0)**:场景① correction 捕获(L-002, output.volume-unit-m3);场景② 环境错误捕获(L-003, **infra.systemd-absent**——与 SKILL.md 示例模板同 key,说明逐字模板生效);场景③ 同 key 折叠 count 1→2。全程零 gateway 重试、零递归错误。

**诚实备注**:场景② 的 key 与 SKILL.md 示例相同(eval 部分被"教考同源"),P1 的服务端 canonical key(D6)是正解;L-001/L-002 近义不同 key 的出现恰好实证了 D6 的必要性。eval 可重复运行(条目持久,重复运行走折叠路径)。

## P1 实施记录(2026-09-14,已上线验证)

**交付物**:`backend/app/extensions/learnings/`(models/patterns/service/sweeper/mcp/__init__ + scripts/import_ledger.py)+ 4 测试文件(容器内 **29/29 PASS**)+ 两份 extensions_config.json 的 mcpServers.learnings 注册(cwd=null,env 携 DEER_FLOW_CONFIG_PATH/PYTHONPATH/EXTENSIONS_DB_HOST/PORT/USER/NAME)。

**实施中抓出并修复的 4 个部署级问题**(每个都由真机验证暴露):
1. **`-m app...` 找不到包**:cwd=null(身份绑定前提)使子进程落在 thread 工作区 → PYTHONPATH=/app/backend 进注册 env(与 bug-712 的 cwd 方案互斥,sys.path.insert 兜底)
2. **`init_engine_from_config` 未再导出**:persistence/__init__ 只导 4 个名 → 改从 deerflow.persistence.engine 直取
3. **store 的 user_id=AUTO**:独立进程无 auth contextvar → list_messages_by_run/list_events 显式传 cwd 推导的 user_id
4. **MCP SDK env 白名单 + backend/.env 端口坑**:子进程丢父进程 EXTENSIONS_DB_* → 注册 env 显式钉住非敏感四项(HOST/PORT/USER/NAME;密码仍走 .env + mcp.py 补 load_dotenv('/app/backend/.env', override=False))

**另**:工具名改裸名(surface/log_learning/stats/resolve),适配器前缀后 agent 侧显示干净的 `learnings_stats`(双前缀消除)。

**真机验证链**:29/29 测试(容器)→ cwd 身份解析 + thread-id-mismatch fail-closed 拒绝 → lazy sweep 对真实 eval 线程 swept=1/captures=1(recursion→runtime.failure)→ 二次 swept=0(receipts 幂等线上生效)→ **lead agent 真实调用 learnings_stats 返回真数据**(p1-smoke-3 线程)。全程零 gateway 重启、零既有文件改动。

**遗留**:D15 硬切换(P0 ledger → importer → 冻结)待 P1 观察稳定后执行;P0 skill 捕获 flag 暂保持开启(并行期短暂共存,importer 幂等可吸收)。

## Open Questions

1. P0 skill 默认在 dev 开还是全部 opt-in？（倾向 dev 默认 true，prod 模板 false）
2. importer 的 user 归属：P0 ledger 无显式 user 字段，靠 custom skill 的存储目录归属（天然 per-user）——确认即可，无歧义但需在 importer 文档化
3. P2 若做实时 sweep，是否复用 dcs_qa 的 cron-poll 容器模式（记忆中有先例）——延后决定（已并入 TODOS.md P2 条目）

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | （价值问题已在 eng-review D2 拍板：全量计划） |
| Codex Review | `/codex` + Claude subagent | Independent 2nd opinion | 1 | issues_found→folded | 9 findings: 1 与 A2 互证、1 证伪(OV8)、6 已决议 folded、1 记录为 R8 |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 8 issues (A1/A2/CQ1/T1/T2/OV3/OV4/OV9), 0 critical gaps, 全部 folded into D9-D15 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | （无 UI 面，N/A） |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** Codex exec 因组织 TPM 限流未产出最终结论，按预案降级 Claude 子代理完成外部声音（9 findings 全部处置，见上表）。
**CROSS-MODEL:** 外部声音与主评审在身份反查循环上独立撞车（OV1 ≡ A2）——互证；OV6（零触碰制造复杂度）为唯一真分歧，用户裁决维持零触碰（硬约束优先），复杂度税如实记入边界表一节。
**VERDICT:** ENG CLEARED — ready to implement（P0 先行；P1 依赖 P0 验收 + D15 硬切换）。

NO UNRESOLVED DECISIONS

---

## 补遗 2026-09-22：提取质量捕获源扩展（合同元数据 + 货物表定位/字段）

**原则**：一切识别/提取皆可错；凡有人工纠错面的地方，纠错动作本身必须被捕获为 ledger 候选条目——纠错是修数据，捕获才是养规则。

### D-1 文档级字段修正（合同编号/供应商/签订日期/项目所在地/项目名/项目编号）
- 触发点：既有 `PATCH /documents/{id}`（ContractsView 编辑器），零新 UI。
- 载荷：`{field, old_value, new_value, doc_sha256, 抽取来源路径(front-regex/last-pages/table-cell)}`——需 crud 在 update 前取 pre-image。
- 晋升目标：`project_fields` 锚词/邻格规则（如"该版式签订日期锚词是『签约时间』"→ 新正则候选进种子评审）。
- 裁决已定（2026-09-22）：原需求所列"合同名称"实为项目名称——`project_name` 字段已有完整链路（提取+编辑+本 D-1 回流），无需新增字段。

### D-2 货物表分类纠错
- 假阴性路径已有：UnmatchedTablesDrawer 补规则（入同一 ledger，与 D-1/D-3 同构）。
- 假阳性缺口：分项校验对某表整表删除时捕获 `{table_title_text, doc_sha256}`；可选轻交互「此表误收」标记（UI 裁决后定）。
- 晋升目标：标题排除词规则（matcher 的负向锚词），与既有标题规则同库。

### D-3 行级字段修正（货物名称/规格型号/分类/含税单价）
- 触发点：既有分项校验行修正（corrected + edit_note）与批量采纳，零新 UI。
- 载荷：在既有 L4 锚词收割（仅表头词）之上扩展：`{列头名, 原值, 新值, 错误模式类(粘连/错位/单位/命名变体), doc_sha256}`。
- 晋升目标：列语义规则（规格列/分类列/单价列的识别与清洗规则），与 v3 规则生态同库。

### 与 P0/P1 的对齐
- P0（skill 层 ledger）：先落 D-1 + D-3（纯捕获写入，无新交互）；D-2 待「误收标记」UI 裁决。
- 晋升语义不变：dedup 按 (字段/列头, 错误模式, 版式指纹) 聚簇，count 达阈值 → 人工评审 → 进种子/规则库 → 下次解析生效。
