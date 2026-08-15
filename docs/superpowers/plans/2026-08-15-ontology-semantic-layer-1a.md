# Ontology 语义层 Phase 1a 实施计划（市场域后端楔子）

- **日期**: 2026-08-15
- **Extends**: `docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md`（母稿）+ `docs/superpowers/specs/2026-08-14-ontology-enterprise-expansion-plan.md`（APPROVED 前向约定）
- **产出方式**: /plan-eng-review — 4 节交互评审（8 决策门）+ 外部独立声音（Claude 子代理，9 发现）→ 6 跨模型张力全裁决
- **范围**: Phase 1a 后端楔子（registry + engine + connectors + MCP + 6 REST + CI lint + 召回预测量）。1b（前端语义地图页 + 剩余 REST + 旧工具退役）另立。
- **分支**: main-dev-fork（不提交 main）

## 评审决策总表

| # | 决策 | 结论 |
|---|------|------|
| D1 | 评审对象 | 设计文档（母稿 432 行） |
| D2 | 阶段拆分 | 1a 后端楔子先行 / 1b 前端 |
| D3 | 链接 stub 字段 | link_types 补 `enabled`（默认 true；false 时 describe 可见、遍历拒绝） |
| D4 | 双进程一致性 | 逐调用 SHA-256 指纹校验（gateway 与 MCP 进程各自） |
| D5 | 工具分工 | ontology 工具描述明确分工；query_goods_price/query_part_price 于 1b 标 deprecated |
| D6 | 引擎契约 | ① filter 值绑定参数 + declared-only 列/操作符 ② keyset 分页 pk tiebreaker ③ 集合遍历 max 5 跳 |
| D7 | CI lint | AST 层（表/列存在性，无需 DB）+ 运行时可用性层（部署后可选） |
| D8 | 命名 | `mcp.py`（非 server.py）、无 models.py、pydantic 入 `schemas.py` |
| D9 | 复用边界 | import `assert_readonly_select`（安全单一真源）；连接管道 ontology 自建（`_build_db_url` 为 5 行字段映射，复制非安全双源） |
| D10 | 测试 | 全量 ~25-35 安全优先 + 1 条 LLM eval 作 1b go/no-go |
| D11 | 跨 connector 跳（外部声音 P0） | 引擎标准能力：分块应用侧 join（键集分批 ≤200 过守卫，对侧 IN 查询），基数正确性可断言 |
| D12 | 链接召回（外部声音 P1） | 建引擎前一次性 SQL 测 4 条链接匹配率；低于阈值降 `enabled:false` stub + 备注原因 |
| D13 | 谓词索引（外部声音 P1） | 维持零拷贝；顺序扫描天花板具名化（升级触发：P95>500ms 或 >10万行 → 物化链接表） |
| D14 | lint 范围（外部声音 P1） | 范围配置（市场域四模块）+ 白名单文件（run_history/非市场扩展）+ 同 PR 规则仅对"新模块新建表"生效 |
| D15 | 视图替代（外部声音 P1） | 维持 YAML+引擎（注册表=前向约定契约工件、跨 connector、hidden/分页契约需引擎层）；Postgres 视图记为 connector 内部优化备选 |
| D16 | 1a REST 面（外部声音 P2） | 砍到 6 核心端点（registry/object-types/objects 列表+详情/links/aggregate）作 pytest HTTP 集成测试载体；search/traverse/reload 包装随 1b |
| D17 | TODOS 延后项 | 4 项全录（性能升级触发器/1b 旧工具退役/新域登记检查点/真数据召回复测） |

外部声音澄清项（直接采纳，无冲突）：`run_readonly_query` 无绑定参数支持 → D9 边界如上；describe_ontology 紧凑默认（类型名+一行描述，opt-in 全量）；归一化标准（LOWER(BTRIM)+非空守卫）属引擎强制非每链接 ad-hoc。

## NOT in scope

- **1b 前端语义地图页** — REST 消费面与页面同建（D2/D16）
- **旧 MCP 工具退役**（query_goods_price/query_part_price deprecated 标注）— 1b（D5/D17）
- **物化链接表 / 表达式索引** — 具名升级路径，触发条件见 D13
- **cpa_/csp_run_history 注册** — 二期（lint 白名单显式豁免）
- **非市场域模块注册**（HR/Project/采购…）— 前向约定按域逐个落
- **写路径 ontology 化** — 过渡期走模块自持 REST（扩张计划死锁闭环 #2）
- **跨 connector 微服务化** — 仅当外部 ERP/EAM/HRIS 接入时照 text-to-cad@8004 模式

## What already exists

| 已有设施 | 计划如何复用 |
|---------|-------------|
| `assert_readonly_select`（data_source/service.py:37，含 LIMIT 200 追加 :55-56） | **import 单一真源**；LIMIT 200 由 D11 分块机制显式共存 |
| data_source 模块行结构 + connection_config（hidden:true） | data_source connector 直接解析；hidden 管控在引擎层统一执行 |
| `SET TRANSACTION READ ONLY` + NullPool 每查询引擎模式（service.py:232/247/264） | 两个 connector 照抄此模式 |
| 低阶 `Server` + `stdio_server` MCP 骨架（data_source/mcp.py:296） | ontology mcp.py 同构 |
| extensions_config.json 热重载 + kebab-key stdio 注册模式 | ontology server 照 3 个既有模块模式注册 |
| contract_price/spare_parts models（cpa_/csp_ 表）+ seed_mock_market.py（mock_market/bid-quote） | 零迁移直读；不 copy 表定义（D8 无 models.py） |
| config/permissions.yaml 模块块模式 | ontology admin 门控照抄 |

## 架构（1a 组件图）

```
extensions_config.json ──(stdio spawn)──┐
                                        ▼
                          ┌─────────────────────────┐
   ontology.yaml ───────►│  registry loader         │ SHA-256 指纹
   (11 对象/12 链接)      │  (热重载/fail-closed)    │ 每次调用校验(D4)
                          └───────────┬─────────────┘
                                      ▼
                          ┌─────────────────────────┐
   REST 6 端点 ──────────►│  engine                 │
   (admin 门控)           │  · typed filter 绑定参数 │
                          │  · keyset 分页(pk tie)  │
   MCP 7 工具 ───────────►│  · hidden 列零透出      │
   (describe/list/get/    │  · 引擎级归一化+非空守卫 │
    search/get_links/     │  · traverse ≤5 跳       │
    traverse/aggregate)   │  · 跨connector分块join   │
                          └─────┬─────────────┬─────┘
                                ▼             ▼
                     ┌──────────────┐  ┌──────────────────┐
                     │ postgres_ext │  │ data_source conn │
                     │ (cpa_/csp_)  │  │ (mock_market/bid)│
                     └──────┬───────┘  └────────┬─────────┘
                            └── import assert_readonly_select ──┘
```

## Failure modes

| 失败模式 | 测试覆盖 | 错误处理 | 用户可见性 |
|---------|---------|---------|-----------|
| YAML malformed（缩进/类型错） | ✓ 启动测试 | fail-closed 带文件名行号，拒绝半加载 | 显式 |
| data_source 断连 | ✓ available:false 测试 | 对象类型标记不可用，**绝不静默空结果** | 显式 |
| filter 值注入 | ✓ 安全断言 | 绑定参数拒拼接；未声明列/操作符显式拒绝 | 显式 |
| 跨 connector 键集被 LIMIT 200 截断 | ✓ 分块基数断言 | 分批 ≤200 循环，超出报错不静默丢 | 显式 |
| hidden 列透出 | ✓ 全输出面断言 | 引擎层剔除，测试断言零出现 | — （不会发生为断言目标） |
| 排序值相同行集翻页丢行 | ✓ tie 测试 | pk tiebreaker | — |
| 双进程 YAML 版本漂移 | ✓ 指纹测试 | 逐调用 SHA-256 校验失败即报错 | 显式 |
| 链接召回≈0（死链接） | ✓ T1 前置测量拦截 | enabled:false stub + describe 备注 | 显式 |
| traverse 深度爆炸 | ✓ 5 跳上限测试 | 超 5 跳拒绝 | 显式 |

**关键缺口: 0**（原外部声音 P0×2 均已由 D11/D9 闭环）

## Worktree 并行化策略

| 步骤 | 模块 | 依赖 |
|------|------|------|
| T1 召回预测量脚本 | backend/scripts/ | — |
| T2 母稿修订 | docs/ | — |
| T3 registry+schemas | backend/app/extensions/ontology/ | — |
| T4 engine | backend/app/extensions/ontology/ | T3 |
| T5 connectors | backend/app/extensions/ontology/ | T3, T4 |
| T6 mcp.py + 注册 | backend/app/extensions/ontology/ + extensions_config.json | T4, T5 |
| T7 REST 6 端点 | backend/app/extensions/ontology/ + gateway routers | T4 |
| T8 CI lint | backend/scripts/ + lint 配置 | T3（YAML schema） |
| T9 测试+eval | backend/tests/ | T4-T8 |

- **Lane A**: T3 → T4 → T5 → T6 → T7 → T9（同模块目录，顺序）
- **Lane B**: T1（独立脚本）+ T2（独立文档）— 可与 Lane A 并行 worktree
- **Lane C**: T8 lint 脚本 — 仅依赖 T3 的 YAML schema 定义，可并行
- 冲突旗标: Lane A 与 Lane C 都 touch `backend/app/extensions/ontology/`（Lane C 仅读 YAML）— 低风险；extensions_config.json 仅 T6 触碰

## Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific
finding above. Run with Claude Code or Codex; checkbox as you ship.

- [x] **T0 (P1, human: ~1h / CC: ~10min)** — docs — 母稿回写评审决议
  - Surfaced by: D3/D11-D16 — §4.4 补 `enabled` stub 字段；§6 跨 connector 链接补分块 join 机制说明；§7 describe 紧凑默认；§8 REST 砍至 6 端点；性能节补物化/视图两条具名升级路径
  - Files: `docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md`
  - Verify: 人工对照决策总表 D3/D11-D16 逐条勾验
- [x] **T1 (P1, human: ~4h / CC: ~20min)** — scripts — 4 条跨模块链接召回预测量
  - Surfaced by: 外部声音 #3 (P1) — representative_name 匹配召回未验证、won_bid mock↔真实零匹配
  - Files: `backend/scripts/ontology_link_recall_probe.py`
  - Verify: 对当前扩展库+mock_market 输出每链接匹配率；<阈值(建议 30%)者降 enabled:false 并写备注
  - **结果（2026-08-15 实测）**: 3 条 NO_DATA（csp_clusters/csp_documents 0 行——备件模块无数据）+ won_bid STUB（40 条 mock 中标名 vs 2 份真实合同，0 匹配——外部声音预测命中）。**4 条链接全部 enabled:false stub 上线**；备件数据到位后重测（脚本可复用，`docker exec deer-flow-gateway /app/backend/.venv/bin/python /app/backend/scripts/ontology_link_recall_probe.py`）。cpa 侧现状：2 文档 + 119 簇。
- [x] **T2 (P1, human: ~8h / CC: ~40min)** — ontology — registry loader + schemas
  - Surfaced by: D3/D4/D8 — YAML 加载/SHA-256/热重载/malformed fail-closed；pydantic 入 schemas.py，无 models.py
  - Files: `backend/app/extensions/ontology/{__init__,schemas,registry}.py` + `registry/{_manifest,contract_price,spare_parts,bid_quote,cross_module}.yaml`
  - Verify: pytest 加载/fingerprint/坏 YAML 拒绝 3 组单测
  - **结果（2026-08-15）**: 5 单测全绿（容器内 pytest）+ ruff clean。11 对象（cpa 3 / csp 4 / bid_quote 4）+ 12 链接（8 FK + 4 跨模块 enabled:false stub 带 note）。交叉引用检查：FK/NKM 键列必须在源对象属性中声明、hidden 不可 filterable/searchable、热重载失败保留旧快照、内容寻址指纹（字节一致恢复不触发重载不占版本号）。
- [x] **T3 (P1, human: ~16h / CC: ~90min)** — ontology — 查询引擎
  - Surfaced by: D6①②③/D11/D13 — 绑定参数+declared-only、keyset pk tiebreaker、引擎级归一化+非空守卫、跨 connector 分块 join(≤200/批)、5 跳上限、hidden 零透出
  - Files: `backend/app/extensions/ontology/engine.py`
  - Verify: 安全断言组（注入/hidden/stub 拒绝/截断基数）+ 分页/遍历单测
  - **结果（2026-08-15）**: 11 单测全绿 + ruff clean。引擎不直接连库——`ConnectorResolver` 协议注入（T4 实现）。注意：发现并归档了早前未评审草案残留的 `engine/`、`connectors/` 包目录 + `routers.py`/`server.py`（untracked, 会 shadow 平铺模块）→ `.wolf/archive/ontology-draft-2026-08-15/`。
- [x] **T4 (P1, human: ~6h / CC: ~30min)** — ontology — 双 connector
  - Surfaced by: D9 — import assert_readonly_select（单一真源）；连接管道自建（NullPool+READ ONLY 照抄模式）
  - Files: `backend/app/extensions/ontology/connectors.py`
  - Verify: 断连→available:false 显式测试；只读守卫拒写动词测试
  - **结果（2026-08-15）**: 6 单测全绿（容器内连真扩展库）+ ruff clean。`OntologyConnectors` 实现 engine 的 ConnectorResolver 协议：fetch=守卫→URL 解析→NullPool+READ ONLY→绑定参数执行；same() 判定单 SQL join vs 分块；availability() 断连显式 false。engine 的 _near_keys/_far_rows 已补显式 LIMIT 与守卫 LIMIT-200 追加共存。
- [x] **T5 (P1, human: ~8h / CC: ~40min)** — ontology+mcp — 7 工具 MCP server
  - Surfaced by: D4/D5 — stdio 注册（kebab-key + `/app/backend/.venv/bin/python -m app.extensions.ontology.mcp`）；describe 紧凑默认；工具描述与 query_goods_price/query_part_price 分工话术
  - Files: `backend/app/extensions/ontology/mcp.py`, `extensions_config.json`
  - Verify: MCP 握手 + describe_ontology token 预算断言（紧凑 <2k token）
  - **结果（2026-08-15）**: 5 单测全绿 + ruff clean + stdio 模块启动冒烟(exit 0)。describe 紧凑默认实测 ~2.5k chars ≈ 600 token（<2k 预算）；引擎错误结构化 success:false 返回 agent。发现并修正 extensions_config.json 里指向已归档草案 `ontology.server` 的 stale 注册项 → `-m app.extensions.ontology.mcp` + ONTOLOGY_DB_URL 显式 env（bug-698：MCP 子进程不继承 env）；connectors 补 `_ext_url()` 同款 override。
- [x] **T6 (P1, human: ~6h / CC: ~30min)** — gateway — REST 6 端点 + admin 门控
  - Surfaced by: D16/T6-A — registry/object-types/objects 列表+详情/links/aggregate；permissions.yaml 照模块块模式
  - Files: `backend/app/extensions/ontology/router.py`, `backend/app/gateway/routers/__init__.py`, `config/permissions.yaml`
  - Verify: pytest HTTP 级集成测试（6 端点全打）
  - **结果（2026-08-15）**: 6 HTTP 集成测试全绿（TestClient + 真扩展库）+ ruff clean，全套 ontology 33/33。落点为 `routers.py`（项目扩展模块均为复数命名；gateway/app.py 的 include_router 前一session已接线）。门控复用既有 `system:access` 权限点——无新权限点故未改 permissions.yaml（模块 pages/nav 块属 1b 前端页）。GET filters 用 JSON 字符串 query 参数（FastAPI 不支持 dict 数组 query）。
- [x] **T7 (P2, human: ~6h / CC: ~30min)** — CI — lint 双层 + 范围/白名单
  - Surfaced by: D7/D14 — AST 层（cpa_/csp_ 表列存在性，无 DB 依赖）+ 运行时层（可选）；范围=市场域四模块；白名单文件豁免 run_history/非市场扩展；同 PR 规则仅对新建表生效
  - Files: `backend/scripts/lint_ontology_registry.py`, lint 范围配置
  - Verify: CI 无 DB 跑通；故意删注册项→lint 红
  - **结果（2026-08-15）**: `scripts/ontology_lint.py`（既有骨架 + 本session修复）: 修正 dict 快照迭代/uuid pk 类型；新增 D14 规则——`check_market_tables_registered`（cpa_/csp_ 表未登记且非白名单即红，白名单=cpa_/csp_run_history）+ `check_data_source_access`（source_id+table_name 必填）。负向验证通过：删 goods_cluster 注册项→exit 1，恢复→exit 0。CI 步骤 + `make lint-ontology` 已在 workflow/Makefile 预接线。运行时可用性层=REST /registry 的 availability 字段（可选层已就位）。
- [x] **T8 (P1, human: ~12h / CC: ~60min)** — tests — 安全优先全量 + LLM eval
  - Surfaced by: D10 — ~25-35 条（fail-closed 断言最高优先）；1 条 agent 跨模块导航 eval（spare_part_item→part_cluster→goods_cluster→contract_item）作 1b go/no-go
  - Files: `backend/tests/test_ontology_{registry,engine,connectors,mcp,rest,security}.py`
  - Verify: `PYTHONPATH=. uv run pytest tests/test_ontology_* -v` 全绿 + eval 报告
  - **结果（2026-08-15）**: 全套 37 条绿（registry 5 / engine 12 / connectors 6 / mcp 5 / rest 6 / lint 3），安全断言覆盖注入绑定/hidden 零透出/declared-only/stub 拒绝/5跳上限/分块基数。eval：`scripts/ontology_eval_navigation.py` **连真库首跑即抓出反向 FK join 写反(bug-1210)**，修复+回归测试后 eval PASS（A1 FK 一跳 5 行 / A2 两跳 traverse / B stub 显式拒绝）；原计划的 4 跳跨模块轨迹因 4 条 NKM 链接 enabled:false（T1 召回实测）当前不可达——LLM 行为层 eval 随 1b 前端页跑。清理：归档草案残留 3 个 test 文件（query/mapper/filters 指向已归档包布局，收集即 ImportError）。
- [ ] **T9 (P3, 1b)** — 前端语义地图页 + search/traverse/reload REST 包装 + 旧工具 deprecated 标注 — 见 TODOS 追踪

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1（office-hours 2026-08-14） | CLEAR（APPROVED） | 27 问题全修复，8/10 PASS |
| Codex Review | `/codex review` | Independent 2nd opinion | 0（Codex 两次失败：arg-too-long + 5min 超时；Claude 子代理替补） | SKIPPED | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1（本评审） | CLEAR | 8 决策门 + 6 跨模型张力全裁决 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | SKIPPED（1b 前补） | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | SKIPPED | — |

- **CODEX:** 未跑（Windows arg 长度限制 + stdin 超时）；按 skill 回退用 Claude general-purpose 子代理完成外部独立声音。
- **CROSS-MODEL:** 外部声音 9 发现（2 P0/4 P1/3 P2）中 2 澄清项直接采纳、6 张力点经用户裁决（T1-A~T6-A 全选推荐项）、1 战略注折入 T1 召回前置；主评审遗漏的真罅漏 = 跨 connector join 机制（D11 闭环）。
- **VERDICT:** ENG CLEARED（1a 范围）— ready to implement。1b 启动前需 Design Review。

NO UNRESOLVED DECISIONS
