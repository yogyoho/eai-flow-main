# 市场分析四大模块设计文档

- **日期**:2026-08-13
- **来源**:企业市场部门业务需求(四项)
- **参考实现**:合同价格分析(`contract_price`,单客户定制扩展)
- **状态**:设计稿(待评审,未写代码)
- **范围**:四个独立业务分析模块的架构与实现模式;不含具体编码
- **修订**:
  - 2026-08-13 (R1):模块②③从"各自建扩展包"改为**统一复用 data_source 模块的 MCP**(③零自建代码;②查询同走 data_source,仅行级权限需额外方案)。
  - 2026-08-13 (R2):模块①的友商价格构成是**客户已持有的真实数据**(投标/开标过程获得),非爬虫/非估算 → 砍掉"可信度分层"机制,我方/友商对称分析。
  - 2026-08-13 (R3):模块①投标数据为**结构化数据**(客户系统已有),**无需投标文件、无需 OCR** → ①从"路线A 文档抽取"整体翻到"路线B 结构化查询",与②③同形态(骑 data_source,零自建代码)。**至此只有④是 OCR 完整扩展;①②③全是 data_source 复用。** 背景见文末"修订记录"。

---

## 1. 背景与目标

市场部门提出四项业务需求,要求在本系统内定制实现,用户通过 AI Agent 对话问答进行查询、分析、获取决策建议:

1. **智能投标报价分析**:结合以往投标历史价格,从我方系统抓取每次投标我方价格构成(自产+外购)和友商价格构成(自产+外购)。**客户每次投标即持有双方完整构成(投标/开标过程获得,非爬公示),且为结构化数据(客户系统已有),无需投标文件 OCR。**
2. **销售人员查询**:查询销售人员的考勤、差旅、个人履历。
3. **投标/合同/开票管线查询**:查询近期投标项目、已中标、新签合同、开票金额。
4. **备品备件价格体系分析**:分析备品备件价格水平、客户备件合同、价格体系管理(跨合同比对发现价格问题)。**数据为扫描件,需 OCR。**

**目标交付形态**:每个模块 = 应用中心内一个定制前端 app(查询类模块可选)+ 一份数据(结构化或非结构化)+ 一个只读 MCP 通道 + 一个引导技能。Agent 通过 MCP 工具拿到数据,技能 prompt 指导它在数据之上推理出"决策建议"。

> **核心判断:"决策建议"不是新架构。** 它是技能 prompt 的一层:Agent 调 MCP 工具取数 → 技能 instruct 它按业务规则推理 → 输出建议。无需额外的"决策引擎"模块。

---

## 2. 架构总览(共享脊柱)

四个模块的"对话侧"架构相同,直接复制自 `contract_price`:

```
┌─────────────────────────────────────────────────────────────────┐
│  用户在对话页提问  ──▶  Lead Agent(技能 + MCP 工具 function-call) │
│                              │                                    │
│              ┌───────────────┴────────────────┐                   │
│              ▼                                  ▼                   │
│   skills/public/<mod>/SKILL.md        只读 MCP 通道(两种来源)     │
│   (只读引导:何时用哪个工具、         ┌─④:app/extensions/<mod>/    │
│    怎么推理决策建议)                 │     mcp.py(自建领域工具)   │
│                                       └─①②③:复用 data_source 模块│
│              │                           的 MCP(dataset+只读SQL)│
│              ▼                                                    │
│   extensions_config.json 注册 MCP server + skill 开关              │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼(写/管理侧,仅④)               ▼(数据层,两类不同)
   app/extensions/spare_parts/        路线A:OCR 抽取(仅模块4)
   routers/crud/service/storage       路线B:结构化查询(模块1、2、3)
   + 应用中心前端 app(/spare-parts)    —— 复用 data_source MCP,不自建
   + permissions.yaml 权限点
```

**模块按实现形态分两类(R3 后):**

| 形态 | 模块 | 数据层 | 对话侧 MCP | 管理侧 |
|---|---|---|---|---|
| **完整扩展(文档摄入)** | ④ 备品备件 | MinIO+OCR+`csp_` 表(挂共享 Base) | **自建** `app/extensions/spare_parts/mcp.py` | 完整 routers/前端页/权限 |
| **data_source 复用(结构化查询)** | ① 投标报价、② 销售、③ 管线 | 外部业务系统库(投标/HR/报销/CRM/财务) | **复用** `data_source` 模块 MCP | 几乎无;可选只读看板 |

> **关键结论(R1+R3):** ①②③是只读结构化查询,系统已有 `data_source` 模块原生提供"只读 SQL + 预存 dataset"能力且带 fail-closed 守卫。给它们再造扩展包/mcp.py 是重复造轮子。**只有④(扫描件)需要 OCR 完整扩展。** 详见第 3、5、6、7 节。

---

## 3. 两条数据层路线(四模块的真正分野)

| 路线 | 模块 | 数据形态 | 机制 | 复用 contract_price 程度 |
|---|---|---|---|---|
| **A. 文档/价格抽取** | ④ 备品备件 | 扫描件/PDF 里的价格表 | OCR 服务抽取 → 校验 → 聚类 → 入库 | ≈ contract_price 原样换域+客户维度 |
| **B. 结构化系统查询** | ① 投标报价、② 销售、③ 管线 | 外部业务系统的结构化数据 | **复用 data_source 模块 MCP**(接外部库;只读 SQL + 预存 dataset) | 不复用 OCR/管理侧;只复用"只读查询"基建 |

**路线 A**(模块 ④):扫描件进 MinIO → 独立 OCR 服务 `eai-flow-ocr` 抽表 → SHA-256 增量去重 → 校验 → 聚类 → 入 `postgres-ext`。这是 contract_price 的重型管线,**直接复用**。

**路线 B**(模块 ①、②、③):无文档、无 OCR、无自建表。数据在客户投标系统/HR/报销/CRM/财务系统里,通过 **`data_source` 模块**(managed MCP provider,对接外部数据库,自带只读守卫)连接。**不自建 mcp.py**:聚合查询存 dataset,参数化查询让 Agent 经 `query_data_source` 写只读 SQL。详见第 5、6、7 节。

### data_source 模块已有能力(决定①②③不自建的基础)

| 工具 | 位置 | 作用 |
|---|---|---|
| `query_data_source(name, params={sql})` | `data_source/mcp.py:70` | 对外部库跑**任意只读 SQL**(强制 SELECT/WITH,自动 LIMIT 200)—— 参数化查询的唯一路径 |
| `query_dataset(source_name, label)` | `data_source/mcp.py:100` | 跑 dataset 的 `default_query`(**静态罐装查询,不带运行时参数**) |
| `list_datasets` / `get_data_source_schema` | `mcp.py:90/61` | 列业务数据集 / 取表字段概览(给 Agent 写 SQL 用) |
| `assert_readonly_select` + `SET TRANSACTION READ ONLY` | `data_source/service.py:37/236` | fail-closed 只读守卫:挡写动词/SELECT INTO/改写型 CTE,强制 LIMIT |

**两条参数化路径的真相:**
- 静态聚合(中标率、构成对比、开票汇总等)→ 存 dataset(`default_query`),零代码。
- 按人/按号/按货物的参数化查询 → dataset 不支持参数,**只能让 Agent 经 `query_data_source` 写 SQL**(配 schema,只读守卫兜底——错了也安全,只是可能答错)。

### data_source 的能力边界(①②③需注意)

- **只读安全:有。** SQL 级 fail-closed 只读守卫,挡一切写操作。
- **行级可见性:无。** 守卫只管"只读",不管"谁能看哪些行"。②是 HR 敏感数据,行级 RBAC(经理只看本组)是 day-1 需求 → 需额外方案(Postgres RLS 或薄注入层),见第 6 节。①③为经营层数据,`system:access` 粒度通常够。
- **查询可靠性:取决于 Agent。** 罐装 dataset 可靠;参数化靠 Agent 写 SQL,有 schema 辅助但仍可能写错。先观察,某个查询反复错再补一个薄领域工具(YAGNI)。

---

## 4. 接入步骤(按形态分两套)

### 4a. 完整扩展(仅模块 ④)—— 7 步,照搬 contract_price

1. **建扩展包** `app/extensions/spare_parts/`,含 `models.py`(表挂 `app.extensions.database.Base`)、`mcp.py`、`__init__.py`(导出 `router` 与 models)。
2. 加 `routers.py`(prefix `/api/extensions/spare-parts`,端点加 `Depends(require_permission("..."))`)、`crud.py`、`service.py`、`schemas.py`、`storage.py`。
3. **挂路由**:在 `app/gateway/app.py` 仿 `contract_price_router`:`from app.extensions.spare_parts import router as spare_parts_router` + `app.include_router(spare_parts_router)`。models 挂共享 Base,gateway 启动自动建表。
4. **建技能** `skills/public/spare-parts-analysis/SKILL.md`。
5. **注册 MCP**:在 `extensions_config.json` 的 `mcpServers` 加:
   ```json
   "spare-parts-analysis": {
     "enabled": true, "type": "stdio",
     "command": "/app/backend/.venv/bin/python",
     "args": ["-m", "app.extensions.spare_parts.mcp"],
     "env": { "CSP_QUERY_DB_URL": "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow" }
   }
   ```
   并在 `skills` 段加 `"spare-parts-analysis": { "enabled": true }`。
6. **权限**:`config/permissions.yaml` 加模块权限点 + 角色 `pages`。
7. **应用中心前端 app**:仿 `/contract-price`(6 子路由)。

**自建 mcp.py 写法模板**(照抄 `contract_price/mcp.py`):`Tool(...)` 列表;handler 用 `_run_in_db(lambda s: s.execute(select(...)))` 跑只读查询,`_ok(payload)` 返回 `TextContent(JSON)`;DB URL 用环境变量覆盖,默认从 `get_extensions_config().database.url` 解析。

### 4b. data_source 复用(模块 ①、②、③)—— 3 步,零/近零自建代码

1. **建 data_source 连接**:在数据源模块加一条连接配置,指向外部业务库(①→投标系统/CRM;②→HR/报销库;③→CRM/财务/合同系统)。mock 阶段指向一个 seed 过的 mock 库(连 URL,不写表到 postgres-ext)。**零 Python。**
2. **定义 datasets(罐装聚合查询)**:把各模块的核心聚合(①构成对比/中标率、②部门汇总、③管线汇总)写成 dataset 的 `default_query`。**治理要求:datasets 从版本化 seed 文件生成,不在界面随手加**(详见第 12 节)。**零 Python(数据 + seed)。**
3. **建技能** `skills/public/<mod>-query/SKILL.md`:教 Agent 用哪个 data_source / 哪个 dataset、参数化查询时怎么用 `get_data_source_schema` + `query_data_source` 写 SQL、怎么在结果上推理决策建议。**零 Python。**
4. **(仅②)行级权限方案**:②需 RBAC。二选一:(a) DB 层 Postgres RLS(行级安全策略绑连接角色,零应用代码);(b) 极薄 mcp.py 只做"把调用者范围注入 WHERE",查询仍走 data_source。**接入前必须先定,不定不接。**
5. **(可选)只读看板前端**:①③若想要可视化,做轻应用中心 app(`/bid-quote`、`/biz-pipeline`),只读看板,无数据加工。

> ①②③**不建** extension 包、**不建** mcp.py(②的薄注入层除外)、**不建** postgres-ext 业务表、**不进** `gateway/app.py` 注册路由。对话能力完全由 data_source MCP + 技能提供。

---

## 5. 模块 1:智能投标报价分析(bid-quote-analysis)

**路线 B(结构化查询)。data_source 复用,零自建代码。**

> **R2+R3:** 友商价格构成是客户已持有的**真实数据**(投标/开标过程获得,非爬公示、非估算),且为**结构化数据**(客户系统已有),**无需投标文件、无需 OCR**。①从原"OCR 完整扩展"改为 data_source 复用,与②③同形态;我方/友商对称分析。

### 数据层(骑 data_source,不自建表)

数据源 = 客户的投标管理系统/CRM(结构化投标记录)。通过 data_source 建连接配置;mock 阶段连 seed mock 库。**不建 `bqa_` 表、不建 mcp.py。**

逻辑数据视图(对客户系统现有表的业务命名,供 dataset/技能引用):

| 业务视图 | 关键字段 |
|---|---|
| 投标 | `bid_id`, `project_name`, `project_location`, `bid_date`, **`bidder_role`(我方/友商)**, `bidder_name`, `won`, `winning_price` |
| 投标分项 | `bid_id`, `goods_name`, `spec`, `quantity`, `unit`, `unit_price`, **`self_amount`(自产)**, **`outsourced_amount`(外购)**, `total_amount` |

**我方/友商对称**:每条投标的双方分项都含自产+外购构成,`bidder_role` 区分是谁的。

### 对话侧 MCP(全走 data_source,不自建)

| 用途 | 走法 |
|---|---|
| 全局聚合(总投标数、中标率、各货物均价、构成配比对比) | **dataset**(罐装 `default_query`) |
| 按货物/按投标方深挖(某货物我方 vs 友商 报价+构成) | Agent 经 `query_data_source` 写只读 SQL(配 schema);反复错再补薄工具 |

### 核心 dataset(罐装分析查询)

- `bid_summary`:投标数 / 中标率 / 均价 / 时间范围
- `composition_compare_by_goods`:各货物的 **我方自产/外购 vs 友商自产/外购** 配比对比(①核心价值,非参数化全局版)
- `win_rate_by_segment`:按项目类型/金额段中标率

### 技能(`bid-quote-analysis/SKILL.md`)

教 Agent:用哪个 data_source / 哪个 dataset、按货物深挖时怎么写 SQL、怎么基于"我方构成 vs 友商构成 + 中标率"给出**报价区间建议 + 自产/外购配比建议**。建议类返回预聚合决策量(区间/中标率加权价),不靠 LLM 心算。

### 前端(可选)

应用中心 app `/bid-quote`:只读看板(我方/友商报价+构成对比、中标率)。**无摄入/审核 UI**(数据来自客户系统)。

### 数据来源

客户投标系统的**结构化数据**(我方+友商双方完整自产/外购构成,投标/开标过程录入)。**无需 OCR、无需爬公示、无需人工估算。**

---

## 6. 模块 2:销售人员查询(sales-personnel-query)

**路线 B(结构化查询)。data_source 复用,近零自建代码。**

### 数据层(骑 data_source,不自建表)

数据源 = 客户 HR 系统 + 报销系统。通过 data_source 模块建连接配置;mock 阶段连一个 seed 过的 mock 库。**不建 `spq_` 表、不建 mcp.py。**

逻辑数据视图:

| 业务视图 | 来源 | 关键字段 |
|---|---|---|
| 员工/履历 | HR 库 | `employee_id`, `name`, `employee_no`, `department`, `position`, `hire_date`, `resume`, `status` |
| 考勤 | HR 库 | `employee_id`, `date`, `status`, `check_in`, `check_out` |
| 差旅/报销 | 报销库 | `employee_id`, `trip_id`, `destination`, `start/end_date`, `purpose`, `amount`, `reimburse_status` |

### 对话侧 MCP(全走 data_source,不自建)

| 用途 | 走法 |
|---|---|
| 部门级聚合(某人出勤率、某组差旅总额) | **dataset**(罐装 `default_query`) |
| 按人/按时间段查(某销售近 3 个月考勤明细) | Agent 经 `query_data_source` 写只读 SQL(`get_data_source_schema` 提供表字段) |

### 技能(`sales-personnel-query/SKILL.md`)

教 Agent:用哪个 data_source、哪个 dataset 做汇总、参数化按人查询时怎么写 SQL、怎么对比"该销售历史均值/部门均值"给异常提示。**不暴露薪资等敏感字段**(技能规则 + 可选 DB 列权限)。

### 🔒 行级权限(day-1,接入前必须定)

data_source 只读守卫不提供行级可见性。②是 HR 敏感数据,需:
- **方案 a(推荐,零应用代码)**:DB 层 Postgres RLS,行级安全策略绑连接角色(经理→本组,HR→全员)。
- **方案 b**:极薄 mcp.py 只做"把调用者范围注入 WHERE",查询仍走 data_source。

**不定清 RBAC 不接②。** 这是②比①③多出的唯一自建工作量。

### 前端

**建议不做**(纯 Agent 对话即天然 UI)。需可视化时做一个简单员工列表 + 详情页。

### 风险

数据访问可能需 HR 审批/合规(非技术)。mock 先行,真实接入取决于客户能否开放 HR/报销库**只读**访问 + 行级权限配合。

---

## 7. 模块 3:投标/合同/开票管线查询(biz-pipeline)

**路线 B(结构化查询)。data_source 复用,零自建代码。**

### 数据层(骑 data_source,不自建表)

数据源 = CRM / 财务(金税)/ 合同系统。统一 `contract_no` 作为跨系统 join key。mock 阶段连 seed mock 库。**不建 `bpp_` 表、不建 mcp.py。**

逻辑数据视图:

| 业务视图 | 来源 | 关键字段 |
|---|---|---|
| 投标 | CRM | `bid_id`, `project_name`, `contract_no`, `bid_date`, `our_bid_amount`, `status`, `competitor_info` |
| 合同 | 合同系统 | `contract_no`(join key), `contract_name`, `customer`, `sign_date`, `amount`, `status` |
| 开票 | 财务/金税 | `invoice_id`, `contract_no`, `invoice_date`, `amount`, `tax_amount`, `status` |

### 对话侧 MCP(全走 data_source,不自建)

| 用途 | 走法 |
|---|---|
| 近期投标/中标/新签/开票**汇总** | **dataset**(罐装聚合 `default_query`) |
| 按 `contract_no` 追溯"投标→中标→合同→开票"全链路(4 表 join,参数化) | Agent 经 `query_data_source` 写 SQL(配 schema);**先不建工具,反复写错再补一个薄追溯工具** |

### 技能(`biz-pipeline-query/SKILL.md`)

教 Agent:各环节用哪个 dataset、追溯链路怎么写 join SQL、怎么做对账(开票 vs 合同金额)、中标转化率/待开票待回款预警。

### 前端(可选)

应用中心 app `/biz-pipeline`:管线漏斗看板(投标→中标→合同→开票)+ 按合同号追溯。只读看板,无数据加工。

### 数据来源

mock 库;真实接 CRM/财务/合同系统 via data_source,统一 `contract_no` 串联。

---

## 8. 模块 4:备品备件价格体系分析(spare-parts-pricing)

**路线 A(文档抽取),完整扩展。四模块中唯一的 OCR 模块,复用度最高,几乎 = contract_price 换域。建议第一个做。**

### 数据模型(`csp_` 前缀,仿 `cpa_*` + 客户维度)

| 表 | 关键字段 | 与 cpa_ 差异 |
|---|---|---|
| `csp_documents` | 仿 `cpa_documents`(备件合同扫描件,bucket `csp-parts`) | 仅换 bucket/前缀 |
| `csp_items` | 仿 `cpa_items` + **`customer_id`/`customer_name`** | 加客户维度 |
| `csp_clusters` | 仿 `cpa_clusters`(按备件聚类) | 同 |
| `csp_price_system`(可选) | `part_name`, `customer`, `price_level`, `discount_rule` | 从合同比对提炼的价格体系 |

### 复用

OCR 服务、聚类引擎(`scripts/clustering/engine.py`)、`mcp.py` 模板、管理前端结构**全部直接复用**,仅换域 + 加客户分组维度。

### MCP 工具(`spare_parts/mcp.py`,自建)

| 工具 | 入参 | 返回 |
|---|---|---|
| `spare_part_summary()` | — | 备件总览 |
| `query_part_price(part_name)` | 备件名 | 备件价格统计(均值/区间/跨客户) |
| `compare_part_price_by_customer(part_name)` | 备件名 | 同一备件不同客户价格对比(发现价格问题核心) |
| `list_part_price_outliers()` | — | 异常备件价格 |
| `customer_parts_contracts(customer)` | 客户 | 某客户备件合同明细 |

### 技能决策建议逻辑

价格体系异常预警(同备件客户间差价过大)、备件定价建议。建议类工具返回预聚合(偏离均值标注),不靠 LLM 心算。

### 前端

应用中心 app `/spare-parts`:仿 contract-price 6 子路由 + 客户比价视图。

---

## 9. 共享基建复用清单(R3 后)

| 基建 | 模块1 | 模块2 | 模块3 | 模块4 |
|---|---|---|---|---|
| OCR 服务 `eai-flow-ocr` | — | — | — | ✅ 复用 |
| MinIO(独立 bucket) | — | — | — | ✅ `csp-parts` |
| `postgres-ext` + 共享 `database.Base`(自建业务表) | ❌ 不自建 | ❌ 不自建 | ❌ 不自建 | ✅ `csp_` |
| 聚类引擎 `clustering/engine.py` | — | — | — | ✅ |
| **data_source 模块 MCP**(连接+dataset+只读SQL) | ✅ 查询层 | ✅ 查询层 | ✅ 查询层 | — |
| **data_source dataset**(罐装聚合查询) | ✅ | ✅ | ✅ | — |
| 自建 `mcp.py` 只读模板 | ❌ | ❌(②仅可选薄权限层) | ❌ | ✅ |
| 管理前端模板(`/contract-price`) | 可选只读看板 | 可选/建议不做 | 可选看板 | ✅ |
| 权限 yaml + `canPage()` | ✅ | ✅(含行级 RBAC) | ✅ | ✅ |

**结论(R3):** **④是唯一完整扩展**(自建 OCR 管线+表+mcp.py+前端);**①②③瘦身到 data_source 复用**(连接+datasets+技能),①③零自建代码,②仅多一个行级权限方案。整体工作量从"四个完整扩展"降到"一个完整扩展 + 三个 data_source 配置项"。

---

## 10. 实现顺序与里程碑

建议 **4 → 1 → 3 → 2**(按"出成果速度/风险"排):

| 顺序 | 模块 | 形态 | 理由 | 最小可对话切片(MVP) |
|---|---|---|---|---|
| 1️⃣ | ④ 备品备件 | 完整扩展(OCR) | 复用度最高,最快出成果,且是唯一 OCR 路径 | 复刻 contract_price 管线 + 客户比价 MCP 工具 + 技能,mock 几份备件合同跑通 |
| 2️⃣ | ① 投标报价 | **data_source 复用(零代码)** | 结构化数据,双方构成真实可对标 | mock/真实投标库 + 我方/友商构成对比 datasets + 技能;Agent 能答报价构成对比 |
| 3️⃣ | ③ 管线 | **data_source 复用(零代码)** | 结构化,datasets+SQL 即可 | mock 库 + 几个 dataset + 追溯 SQL + 技能;Agent 能答管线问题 |
| 4️⃣ | ② 销售 | **data_source 复用(近零)+RBAC** | 数据接入+行级权限风险最高 | mock 库 + datasets + 技能 + 行级权限方案;真实 HR 接入取决于审批 |

> R1+R3 影响:①②③因不自建扩展包,**成本比原稿降一个量级**(①③几乎零代码;②仅 RBAC 工作量)。④是唯一重模块。建序不变。

每个模块 MVP 完成标准:**Agent 能在对话里回答该模块核心问题并给出建议**,即 data_source/MCP + 技能跑通(前端可后补)。

---

## 11. 关键设计决策(可推翻)

1. **四模块分两类数据层**(A 文档抽取 / B 结构化查询),不统一用 OCR。→ 推翻代价:模块 ①②③硬上 OCR 会做无用功。
2. **【R1】①②③不自建扩展包,统一复用 data_source 模块 MCP。** 聚合查询存 dataset,参数化查询让 Agent 经 `query_data_source` 写只读 SQL;①③零自建代码,②仅加行级权限方案。理由:data_source 已原生提供只读 SQL + dataset + fail-closed 守卫,再造扩展包是重复造轮子。→ 推翻代价:若 Agent 写的参数化 SQL 反复出错,再按需补薄领域工具(不预先建)。**对原稿"①②③各建领域 mcp.py/扩展包"的推翻。**
3. **【R1】②的行级 RBAC 是 day-1,不 defer。** data_source 只读守卫不提供行级可见性,②是 HR 敏感数据,需 Postgres RLS 或薄注入层。不定清不接。→ 推翻代价:若客户确认②数据全员可见(如内部小团队),可省,但默认按需 RBAC。
4. **datasets 当代码管**:从版本化 seed 文件生成 `default_query`,不在界面随手加,避免领域逻辑在 DB 行里漂移、失评审。
5. **【R2+R3】模块①我方/友商价格构成均为真实数据(客户已持有、结构化),对称分析,走 data_source 复用(非 OCR)。** 删去"公示实际值 vs 估算值"分层;①无自建表/无 OCR/无 mcp.py,纯只读分析(datasets + 技能)。**对原稿"①是 OCR 完整扩展 + 友商数据不实分层"的双重推翻。**
6. **完整扩展仅④**,独立扩展包,不折叠进 contract_price(遵循"新功能做独立模块"偏好)。
7. **模块 4 = contract_price 换域 + 客户维度,不重写管线**。
8. **权限:④沿用 contract_price 的 `system:access` 基线,暂不做 per-user 数据隔离**;②除外(行级 RBAC day-1)。①③经营层数据,`system:access` 粒度通常够。

---

## 12. 风险与未决项

- **【day-1】模块 ② 行级权限**:data_source 不提供行级可见性。接入②前必须定 RLS 或薄注入层方案;且 HR 数据访问可能卡合规审批(非技术)。
- **datasets 治理**:统一到 data_source 后,①②③的领域逻辑落在 datasets(DB 行)+ 技能文件。datasets 必须从 seed 文件生成、版本化、可评审,否则易漂移。
- **Agent 写 SQL 的可靠性**:①②③参数化查询靠 Agent 经 `query_data_source` 写 SQL。有 schema 辅助 + 只读守卫(错了也安全),但可能答错。需观察;某查询反复错则补薄工具。
- **模块 ③ 统一合同号**:假定跨系统有统一 `contract_no`;真实系统若各用各编号,需建主数据映射表(额外工作量)。
- **模块 ①/③ 投标主数据重叠**:①的投标视图与 ③的投标视图都读"投标"数据(可能同源 CRM)。本期各模块独立连接;若同源,可共享一条 data_source 连接 + 不同 dataset,避免重复。
- **mock 数据真实性**:决策建议质量取决于 mock 是否贴近真实分布;接入真实数据后需重新校准。
- **数据隔离**:①③④暂不做 per-user 隔离(同 contract_price 现状;平台级数据访问控制已明确排除定制扩展)。②除外(RBAC day-1)。

---

## 13. 不在本设计范围内

- 具体编码(本稿为设计;实现走 `/plan-eng-review` → 编码 → `/qa`)。
- 各模块前端页面详细交互稿(建模块时再出,参考 `/contract-price`)。
- 真实外部系统(投标/HR/报销/CRM/金税)对接协议细节(取决于客户具体系统,接入时定)。
- Postgres RLS 的具体策略脚本(②接入时按客户组织架构定)。
- 跨模块数据关联(①与③是否共享投标 data_source 连接):本期独立,后续按需打通。

---

## 修订记录

### R1 (2026-08-13):②③统一到 data_source MCP

**原稿**:②③各建独立扩展包(自建 `spq_`/`bpp_` 表 + 领域 mcp.py + mock 表 + 前端)。

**问题**:经查 `data_source` 模块已原生提供只读查询能力——`query_data_source`(任意只读 SQL,`mcp.py:70`)、`query_dataset`(罐装查询,`mcp.py:100`)、`assert_readonly_select` fail-closed 守卫(`service.py:37`)。给②③再造扩展包/mcp.py 是重复造轮子;原论证"领域工具提供安全边界"也不成立(data_source 本就只读安全)。

**修订**:②③对话侧统一复用 data_source MCP。③零自建代码(连接+datasets+技能);②查询同走 data_source,仅行级权限需额外方案(RLS 或薄注入层),且升为 day-1。datasets 从 seed 文件生成(治理)。

### R2 (2026-08-13):模块①友商价格构成是真实数据

**原稿**:假设友商分项构成拿不到(只有中标公示总价),设计"公示实际值 vs 估算值"可信度分层兜底,并标"友商分项构成可能长期拿不到 / MVP 是否 defer"为风险。

**纠正(用户澄清)**:客户每次投标即持有我方和友商双方的完整价格构成(自产+外购),来自投标/开标/评标过程,**不需要爬网上公示**。友商构成是真实数据,不是估算。

**修订**:删 `source_confidence`/`composition_confidence` 分层机制;自产/外购构成对双方对称;数据来源改为"客户持有的双方投标文件"。

### R3 (2026-08-13):模块①数据为结构化,整体翻到 data_source 复用

**原稿(R2 后)**:模块①仍是路线A 文档抽取(OCR 完整扩展),自建 `bqa_` 表 + OCR 管线 + mcp.py + 管理前端;仅把"友商构成是真实数据"修正,并留"投标数据存储形态(OCR vs 结构化)待确认"开放项。

**纠正(用户澄清)**:投标数据来源于**结构化数据**,**不需要投标方案文件、不需要 OCR 提取**。

**修订**:模块①从路线A 整体翻到路线B —— 骑 data_source,零自建代码,与②③同形态。删 `bqa_` 表/MinIO bucket/OCR 管线/自建 mcp.py/管理前端;核心分析(我方 vs 友商 自产/外购 构成对比)改由 datasets + 技能交付。**至此四模块路线定型:仅④是 OCR 完整扩展,①②③全是 data_source 复用。** "投标数据存储形态待确认"项关闭。

**R1+R2+R3 累计影响章节**:第 1(需求1/4补注)、2(形态分类)、3(路线表)、4(接入步骤 4a 仅④)、5(模块①重写为 data_source 复用)、6、7、9(复用清单①列翻面)、10(① MVP)、11(决策2/5)、12(风险)。

---

## 参考文件(实现时照此镜像)

- `backend/app/extensions/contract_price/`(完整扩展模板)—— **仅④照此**
- `backend/app/extensions/contract_price/mcp.py`(自建只读 MCP 模板)—— 仅④
- `backend/app/extensions/data_source/mcp.py` + `service.py`(**①②③复用**的只读查询 + dataset + 守卫)
- `skills/public/contract-price-analysis/SKILL.md`(只读引导技能模板)—— 四模块技能照此
- `skills/public/contract-price-analysis/scripts/cli.py`(OCR 管线)—— **仅④复用**
- `extensions_config.json`(MCP server + skill 注册;①②③仅注册技能,data_source MCP 已存在;④注册 MCP server + 技能)
- `backend/app/gateway/app.py:14,585`(扩展路由挂载点,**仅④**)
- `backend/app/extensions/database.py`(共享 Base,自动建表,**仅④**)
- `mcp-server/ocr-service/`(独立 OCR 服务,**仅④复用**)
- `config/permissions.yaml` + `config/roles_custom.yaml`(权限与角色;②含行级 RBAC)
