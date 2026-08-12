# 模块④ 备品备件价格体系分析 — 工程实现方案(已锁)

> 由 `/plan-eng-review` 于 2026-08-13 锁定。设计稿:`docs/superpowers/specs/2026-08-13-market-analysis-modules-design.md` §8。
> 本稿是④的**可执行实现计划**(步骤/数据模型/风险/验收),设计稿第8节的数据模型以本稿为准(D3 新增 `csp_customers`、聚类升为 MVP 必需)。

## 0. 已锁决策

| ID | 决策 | 选定 |
|---|---|---|
| D1 | 评审对象 | 设计稿 §8 |
| D2 | 数据形态 | 扫描件 OCR(确认非结构化,fork OCR 管线成立) |
| D3 | 实体归一 | **混合**:客户主数据表 + 别名映射;备件名复用 `clustering/engine`(聚类) |
| Step0 | fork 范围 | fork contract_price 最小子集,每个 fork 文件头注 `# EAI-CUSTOM: forked from contract-price-analysis`;第 3 个 OCR 模块出现再抽共享库 |
| Step0 | MVP defer | `csp_price_system` 表、`excel_generator/stats` 富功能、前端完整 6 子路由 |
| Step0(纠正) | 聚类 | **MVP 必需**(非 phase-2)—— OCR 备件名脏,精确匹配会大面积落空 |

## 1. 数据模型(`csp_` + 客户主数据)

挂在共享 `app.extensions.database.Base`,gateway 启动自动建表。bucket `csp-parts`。

```
┌─────────────┐        ┌──────────────────────────────────────┐
│csp_documents│        │ csp_items                             │
│ (备件合同扫描件)│   │  part_name, spec, unit_price,         │
│ bucket       │        │  price_untaxed, quantity,             │
│ csp-parts    │        │  customer_id (FK) , customer_name(冗余)│
└──────┬───────┘        │  cluster_id (FK),                     │
       │ 1:N            │  source_page, bbox (溯源),            │
       └───────────────▶│  validation_status                    │
                        └──────────┬───────────────┬────────────┘
                                   │ N:1           │ N:1
                          ┌────────▼─────┐   ┌─────▼──────────┐
                          │ csp_clusters │   │ csp_customers  │ ← D3 新增
                          │ (备件名聚类) │   │ canonical_name │   客户主数据
                          │ cluster_id   │   │ aliases[]      │   + 别名映射
                          │ 代表名        │   │ source         │   (OCR 脏名→id)
                          └──────────────┘   └────────────────┘
```

- `csp_documents` — 仿 `cpa_documents`,仅换 bucket/前缀。
- `csp_items` — 仿 `cpa_items` + **`customer_id`/`customer_name`**(④ 与 cpa_ 的核心差异)。
- `csp_clusters` — 仿 `cpa_clusters`;**`cluster_id` 是跨客户比价的键**。
- `csp_customers`(**D3 新增**)— `customer_id, canonical_name, aliases(text[]/json), source`。OCR `customer_name` 经别名映射得 `customer_id`。
- `csp_price_system` — **DEFER**(可选,价格体系提炼阶段再建)。
- `csp_run_history` — 仿 `cpa_run_history`(管线运行记录)。

## 2. 归一流程(D3,核心命门)

```
OCR 抽出 (customer_name 脏, part_name 脏)
   │
   ├─▶ 客户归一: customer_name → 查 csp_customers.aliases
   │       ├─ 命中 → customer_id
   │       └─ 未命中 → 入"待确认"队列(管理前端人工认领/合并,不静默丢)
   │
   └─▶ 备件归一: part_name → clustering/engine 向量化聚类 → cluster_id
           (同 cluster = 同一备件,跨客户比价按 cluster_id 聚合)
```

理由:客户是小集合(几十~几百),主数据表 + 别名最可控;备件是高基数脏名,复用本项目已验证的聚类引擎。

## 3. MCP 工具(`app/extensions/spare_parts/mcp.py`,自建,5 个)

| 工具 | 入参 | 逻辑 | 返回 |
|---|---|---|---|
| `spare_part_summary()` | — | 全量统计 | 备件/客户/合同总览 |
| `query_part_price(part_name)` | 备件名 | part_name→cluster_id(聚类)→聚合该 cluster 价格 | 均值/区间/跨客户 |
| `compare_part_price_by_customer(part_name)` | 备件名 | cluster_id→GROUP BY customer_id | 各客户价格对比 + 偏离标注(**④核心**) |
| `list_part_price_outliers()` | — | 同 cluster 内价格偏离均值超阈值 | 异常备件价格 |
| `customer_parts_contracts(customer)` | 客户 | customer_name→customer_id | 该客户备件合同明细 |

MCP server 经 `extensions_config.json` 注册为 stdio,env **`CSP_QUERY_DB_URL`**(bug-1162:stdio 子进程 env 白名单,必须显式写 `server.env`,镜像 `CPA_QUERY_DB_URL`)。

## 4. 后端扩展文件(fork `contract_price/`,8 文件)

| 文件 | 来源 | 改动 |
|---|---|---|
| `__init__.py` | fork | 导出 `Csp*` 模型 + `router`;docstring 写对 `skills/public/`(contract_price 的写成了 custom/,琐) |
| `models.py` | fork | `CspDocument/CspItem/CspCluster/CspCustomer/CspRunHistory`,挂共享 Base |
| `schemas.py` | fork | Pydantic |
| `crud.py` | fork | DB 操作 |
| `service.py` | fork | `run_pipeline_subprocess` 指向新 skill CLI 路径 |
| `storage.py` | fork | MinIO bucket `csp-parts` |
| `routers.py` | fork | 管理 API(上传/列表/触发管线/客户认领),`require_permission` |
| `mcp.py` | fork | FastMCP + 5 工具 + `CSP_QUERY_DB_URL` |

## 5. Skill(`skills/public/spare-parts-analysis/`,fork 子集)

| 文件 | 处理 |
|---|---|
| `SKILL.md` | 新写(备件价格体系分析 + 决策建议 prompt) |
| `scripts/cli.py` | fork(管线入口) |
| `scripts/{db,models,config,storage}.py` | fork(改 `csp_`/bucket) |
| `scripts/{document_parser,table_classifier,document_scanner,project_fields}.py` | fork(**备件合同字段**:客户/备件名/规格/单价/数量) |
| `scripts/clustering/{engine,vectorizer}.py` | fork(**MVP 必需**,备件名归一) |
| `scripts/price_validator.py` | fork(备件价格校验) |
| `scripts/query.py` | fork(5 工具查询逻辑) |
| `tests/` | fork 对应测试 + **加脏键归一测试** |
| **复用(不 fork)** | `eai-flow-ocr` 服务(rapid-layout/table/ocr) |
| **DEFER** | `excel_generator.py`、`stats.py` 富功能 |

## 6. 注册触点

- **`extensions_config.json`**
  - `mcpServers.spare-parts-analysis`:`{enabled:true, type:stdio, command:/app/backend/.venv/bin/python, args:["-m","app.extensions.spare_parts.mcp"], env:{CSP_QUERY_DB_URL: postgresql+asyncpg://agentflow:...@postgres-ext:5432/agentflow}, cwd:/app/backend}`
  - `skills.spare-parts-analysis`:`{enabled:true}`
- **`backend/app/gateway/app.py`**:L14 类似 `from app.extensions.spare_parts import router as spare_parts_router`;仿 L585 `app.include_router(spare_parts_router)`
- **`config/permissions.yaml` + `config/roles_custom.yaml`**:④ 沿用 `system:access` 基线 + `canPage('spare-parts')` 子页可见性

## 7. 前端(第二波,非 MVP 阻塞)

应用中心 app `/spare-parts`:仿 `/contract-price` 6 子路由 + 客户比价视图 + **客户认领界面**(D3 人工认领待确认队列)。MVP 先后端+skill+MCP 跑通对话,前端后补。

## 8. 验收标准(MVP)

1. mock 3–5 份备件合同扫描件(含同一备件不同客户、脏客户名/脏备件名变体)。
2. 上传 → OCR → 入库 → 聚类 → 客户归一 全链路跑通。
3. Agent 对话能答:"X备件各客户什么价"(compare)、"Y客户买了哪些备件"(customer_parts_contracts)、"哪些备件价格异常"(outliers),并给定价/异常建议。
4. **脏键归一测试覆盖**:客户别名命中/未命中(入队列)、备件名变体聚类同簇。
5. `csp_*` 表 gateway 启动自动建表;MCP 启动探测 DB 连接(CSP_QUERY_DB_URL 白名单不漏)。

## 9. 风险登记(已识别 + 处置)

| 级别 | 风险 | 处置 |
|---|---|---|
| P1(已解) | OCR 脏键让 compare/query 返回空 | D3 混合归一 |
| P2 | MCP env 白名单漏 CSP_QUERY_DB_URL → 静默连不上 DB | 照抄 `CPA_QUERY_DB_URL` pattern;启动探测 |
| P2 | DRY: fork 重复 ~12 脚本 | EAI-CUSTOM 头注;第 3 个 OCR 模块抽共享库 |
| P3 | 管线子进程指向旧 skill | `service.py` 指向新 skill CLI |
| P3 | per-user 数据隔离 | 同 contract_price 现状,本期不做 |
| P3 | compare 查询 GROUP BY customer×cluster | 标准索引 `(cluster_id, customer_id)` |

## 10. Failure modes(每条 = 测试 + 错误处理 + 用户可见)

- OCR 抽不出备件表格 → 空入库。测试:mock 一份表格模糊合同,验证降级提示。
- 客户别名未命中 → **入待确认队列,不静默丢**;管理前端可见。
- 聚类把不同备件归同簇 → 比价串台。测试:相近名不同规格不归同簇。
- MCP 连不到 DB(白名单漏) → 工具静默失败。测试:启动探测连接,失败显式报错。

## 11. NOT in scope(deferred,带理由)

- `csp_price_system` 价格体系表 — 价格体系提炼阶段再建。
- `excel_generator/stats` 富导出 — MVP 只要 query/compare。
- 前端完整 6 子路由 — 设计稿已定"前端可后补"。
- per-user 数据隔离 — 同 contract_price 现状(平台级数据访问控制已排除定制扩展)。
- 真实客户主数据导入 — mock 起步,接入真实数据后校准别名表。

## 12. What already exists(复用,不重建)

- `eai-flow-ocr` 服务 → 直接复用(不 fork)。
- `contract_price/` 全套(mcp/routers/models/clustering/管线)→ fork 模板。
- 共享 `app.extensions.database.Base` → 自动建表。
- MinIO → 新 bucket `csp-parts`。
- 权限 yaml + `canPage()` 机制 → 复用。
- `CPA_QUERY_DB_URL` 注册 pattern → 镜像为 `CSP_QUERY_DB_URL`。

## 13. Implementation Tasks

- [ ] **T1 (P1, CC: ~20min)** models — 建 `csp_*` 模型(含 `csp_customers` + customer_id 维度),挂共享 Base
- [ ] **T2 (P1, CC: ~40min)** skill fork — fork 管线子集,备件合同字段,聚类(MVP 必需)
- [ ] **T3 (P1, CC: ~30min)** 归一层 — 客户别名映射 + 备件聚类接入,未命中入队列
- [ ] **T4 (P1, CC: ~30min)** `mcp.py` — 5 工具,query/compare 经归一层,返回预聚合 + 偏离标注
- [ ] **T5 (P2, CC: ~15min)** 注册 — `extensions_config.json`(mcpServers + skills)+ `gateway/app.py` include_router + permissions yaml
- [ ] **T6 (P2, CC: ~30min)** 测试 — 脏键归一 + 5 工具 + E2E mock 合同
- [ ] **T7 (P3, 后补)** 前端 — `/spare-parts` 6 子路由 + 客户比价 + 客户认领界面

**④ 内部建序**:T1 → T2 → T3 → T4 → T5 → T6(MVP 可对话)→ T7 前端。
全部容器内开发:后端改完 `docker compose -p eai-docker restart gateway`;`extensions_config.json` 改完热加载;提交到 `main-dev-fork`。

## 14. 复用 ASCII 图(④ 数据流,建议落进 `service.py` 注释)

```
浏览器/Agent
   │ POST 上传统一备件合同扫描件(PDF)
   ▼
routers.upload → MinIO(csp-parts) → csp_documents
   │ 触发 service.run_pipeline_subprocess
   ▼
skill cli.py:
   eai-flow-ocr(布局+表格+OCR) → document_parser/table_classifier
   → 备件明细行(part_name, spec, unit_price, qty, customer_name)
   → 客户归一(csp_customers.aliases) + 备件聚类(clustering/engine)
   → csp_items(customer_id, cluster_id, 溯源 page/bbox)
   ▼
mcp.py 5 工具(Agent function-calling 只读查询)
   query_part_price / compare_part_price_by_customer /
   list_part_price_outliers / customer_parts_contracts / spare_part_summary
   ▼
技能 SKILL.md 引导 Agent:取数 → 推理 → 价格异常预警 + 定价建议
```

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 6 issues found, 0 critical gaps, 全部已处置或纳入 T1–T7 |
| Outside Voice | codex/subagent | Independent 2nd opinion | 0 | SKIPPED | 跳过(用户偏好"直接实现,少子代理评审仪式"+ ponytail full);可随时要求补跑 |

- **VERDICT:** ENG CLEARED — ready to implement. 三决策(D1/D2/D3)全锁;P1 脏键归一由 D3 化解;聚类升为 MVP 必需(纠正 Step 0)。
- **CODEX:** — (skipped)
- **CROSS-MODEL:** — (single-reviewer)

NO UNRESOLVED DECISIONS
