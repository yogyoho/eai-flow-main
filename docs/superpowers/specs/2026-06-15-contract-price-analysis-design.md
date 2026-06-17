# 合同分项价格分析技能 — 设计文档

> **状态**:已批准待实现
> **日期**:2026-06-15
> **作者**:brainstorming 协作产出
> **关联**:`skills/custom/contract-price-analysis/`(新)、主前端新路由 `/contract-price`

---

## 1. 目标与背景

### 1.1 目标

从 RAGFlow 合同知识库中提取所有合同文档的分项价格,对同类货物(设备/物资/配件等)按"货物名称 + 技术参数"双维度聚类归并,计算每类单价的均值/最大值/最小值等统计量,导出为带图表可视化的 Excel 报告。

### 1.2 背景约束

- **数据源**:RAGFlow 合同知识库
  - REST API:`http://localhost:9380/api/v1/`
  - 知识库 ID:`a8e8f3dc660d11f1ad61e1631bd6f152`
  - 知识库管理面:`http://localhost:9381/dataset/dataset/a8e8f3dc660d11f1ad61e1631bd6f152`
  - API Key:从后端 `.env` 的 `RAGFLOW_API_KEY` 环境变量读取
- **合同文档格式**:PDF 扫描件 / PDF 文本型 / Word 文档混合
- **分项价格在文档中的形式**:表格 / 清单列表 / 混合(由用户选择解析模式)
- **规模**:>1000 份合同,持续增量更新
- **触发方式**:手动 + 定时混合(定时作为兜底,手动可随时跑)
- **隔离约束**:不碰 procurement-service(采购管理)的前后端代码

### 1.3 非目标(YAGNI)

- ❌ 不做合同条款语义合规审查
- ❌ 不做供应商信用评估
- ❌ 不直接生成 .docx(只产出 Excel)
- ❌ 不重写 procurement-service

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  Skill Layer (skills/custom/contract-price-analysis/)   │
│  SKILL.md → Agent 调度 → 用户交互、参数确认、结果呈现    │
│  scripts/ 下承载全部后端逻辑                             │
└──────────────────────┬──────────────────────────────────┘
                       │ 直接调用
┌──────────────────────▼──────────────────────────────────┐
│  Scripts Layer (skills/custom/contract-price-analysis/  │
│                 scripts/)  ← 数据流水线「引擎」          │
│  ├── ragflow_client.py     # RAGFlow API 客户端         │
│  ├── parser/               # 文档解析(表格/清单/混合) │
│  ├── clustering/           # 聚类引擎                   │
│  │   ├── vectorizer.py     # 文本+技术参数向量化        │
│  │   └── engine.py         # DBSCAN + 用户审核          │
│  ├── stats/                # 均值/最大/最小统计          │
│  ├── excel_generator.py    # Excel + 图表生成           │
│  ├── db.py                 # PostgreSQL 持久层(cpa_ 表)│
│  ├── cli.py                # 入口(手动/定时触发)      │
│  └── models.py             # cpa_ 表镜像(自有 Base)    │
└──┬───────────────────────────────┬──────────────────────┘
   │ ① agent 在对话中直接跑          │ ② Gateway 扩展以子进程拉起
   │   python -m scripts.cli         │    service.run_pipeline_subprocess()
   ▼                                 ▼
┌──────────────────────────────────────────────────────────┐
│  PostgreSQL postgres-ext (cpa_* 表)                       │
│  两端共用同一物理表:skill 写入 + 扩展读写                 │
└────────────────────────▲─────────────────────────────────┘
                         │ 读写 cpa_ 表(权威定义)
                ┌────────┴─────────────────────────────────┐
                │  Gateway 扩展  backend/app/extensions/    │
                │                contract_price/            │
                │  routers.py  管理页面 REST API            │
                │   (documents/clusters/items/runs/...)    │
                │  models.py   cpa_ 表(权威 Base)          │
                │  service.py  run_pipeline_subprocess()    │
                └────────┬─────────────────────────────────┘
                         │ /api/extensions/contract-price
                         ▼
                ┌──────────────────────────────────────────┐
                │  Next.js 前端  /contract-price/*          │
                │  独立管理页面(总览/合同/聚类审核/分项/任务/配置)│
                └──────────────────────────────────────────┘
```

> **注**:RAGFlow API(`localhost:9380/api/v1`)由 Scripts 层的 `ragflow_client.py`
> 在流水线内调用,未在图中单独画出。

### 2.1 三层职责

| 层 | 职责 | 技术栈 |
|----|------|--------|
| Skill 层 | 用户对话、参数收集、进度汇报、触发分析 | SKILL.md + Agent |
| Scripts 层 | RAGFlow 拉取、文档解析、聚类、统计、Excel 生成、持久化 | Python 3.12 |
| 管理页面层 | 缓存数据管理、聚类审核、任务历史、配置、看板 | Next.js + Gateway 扩展(FastAPI) |

### 2.2 关键决策

- **持久化用 PostgreSQL**(非 SQLite):复用 `postgres-ext` 容器,表用 `cpa_` 前缀与采购模块物理隔离。理由:Docker 持久化安全(容器自带数据卷)、行级锁支持并发(定时任务+管理页并发读写)、SQL 聚合/JSONB 利于统计分析。放弃"零依赖自包含",但不碰 procurement-service 代码。
- **管理页面在主前端新增路由**,复用现有 Shadcn/Tailwind 4/认证体系,数据由主 Gateway 扩展 `backend/app/extensions/contract_price/` 提供(复用 cookie-JWT 认证 + 共享 DB 引擎);Gateway 以子进程方式拉起 skill 的 `cli.py` 跑流水线(详见 §2.3)。

### 2.3 实现阶段架构调整(相对本节原图)

实现阶段对 §2 做了一处关键调整:**管理页面 API 不再是 skill 内 `scripts/server/` 的独立 FastAPI 服务,而是挂载到主 Gateway 扩展** `backend/app/extensions/contract_price/`,复用 Gateway 的 cookie-JWT 认证与共享 DB 引擎,路由前缀 `/api/extensions/contract-price`。Gateway 通过 `service.run_pipeline_subprocess()` 以子进程方式拉起 skill 的 `cli.py`;两端共用同一组物理 `cpa_*` 表(skill 用镜像 `scripts/models.py` + 自有 Base 持久化,扩展用权威 `models.py` 读写)。

由此 skill 的角色收敛为:**对话触发入口 + 数据流水线引擎**;管理页面(独立路由 `/contract-price`)与流水线编排归属 Gateway 扩展。skill 需在 `extensions_config.json` 注册后,agent 才能在对话中直接触发分析——形成「对话 + 管理页面」双入口。

> **边界约束**:skill 的 `scripts/` 不得 import `app.*`(harness/app 隔离),故镜像 `models.py` 与扩展 `models.py` 必须手动同步,由 `backend/tests/test_contract_price_model_parity.py` 守护。

---

## 3. 数据流与聚类引擎

### 3.1 增量数据流水线

```
[触发: 手动 / 定时]
   │
   ▼
① 拉取增量 ── RAGFlow API 列出知识库文档,与 cpa_documents 的 doc_hash 比对
   │           → 只处理新增/变更的合同(增量)
   ▼
② 解析分项 ── 用户选定解析模式(表格 / 清单列表 / 混合)
   │           → PDF 扫描件走 OCR,文本型走布局解析
   │           → 提取结构化分项:{货物名称, 规格型号, 技术参数, 数量, 单位, 单价, 来源合同号}
   ▼
③ 向量化   ── 聚类特征 = 文本向量 ⊕ 技术参数向量
   │           文本: TF-IDF(货物名称+规格) 或 sentence-transformers
   │           参数: 从技术参数抽取关键数值(功率/容量/电压/尺寸)→ 标准化向量
   │           → 拼接为统一特征向量
   ▼
④ 自动聚类 ── DBSCAN(密度聚类,无需预设簇数,自动发现噪声点/离群价格)
   ▼
⑤ 用户审核 ── 聚类结果写入 cpa_clusters(status=pending)→ 管理页面展示
   │           → 用户调整分组(移动/合并/拆分)→ status=confirmed
   ▼
⑥ 统计计算 ── 仅对 confirmed 分组计算:均值/最大/最小/中位数/标准差/合同数
   ▼
⑦ Excel 生成 ── 汇总表 + 6 类图表 → 输出到 /mnt/user-data/outputs/
```

### 3.2 聚类算法选择:DBSCAN(非 KMeans)

| 维度 | DBSCAN | KMeans |
|------|--------|--------|
| 簇数 | 自动(密度发现) | 需预设 K |
| 离群点 | 显式标为噪声 | 强行归入某簇 |
| 适合货物归并 | ✅ 同类货物密度聚集 | ❌ 货物类别数未知 |

### 3.3 为什么聚类特征必须包含技术参数

举例:「高压开关柜」单价可能从 5 万到 50 万跨度极大,因为参数不同(10kV vs 35kV、630A vs 3150A)。**仅按名称聚类会把不同规格混在一起,均值无意义**。因此把从技术参数抽取的关键数值(电压、电流、容量、尺寸等)标准化后纳入特征向量,参数相近才算同类。

---

## 4. 数据库设计(PostgreSQL, `cpa_` 前缀)

复用 `postgres-ext`(连接串 `postgresql+asyncpg://agentflow:...@postgres-ext:5432/agentflow`),新建以下表:

### 4.1 表结构

```
cpa_documents        -- 缓存的合同文档元数据
  id (UUID PK)
  ragflow_doc_id (str, unique)   -- RAGFlow 文档 ID
  doc_hash (str, index)          -- 内容指纹,用于增量比对
  contract_no (str)              -- 合同号
  supplier (str, nullable)       -- 供应商
  sign_date (date, nullable)     -- 签订日期
  parse_mode (str)               -- 解析模式 table/list/mixed
  parse_status (str)             -- pending/parsed/failed
  raw_text (text, nullable)      -- 原始解析文本(可选保留)
  parsed_at, created_at, updated_at

cpa_items           -- 提取的分项价格明细
  id (UUID PK)
  document_id (UUID FK → cpa_documents)
  goods_name (str)              -- 货物名称
  spec_model (str, nullable)    -- 规格型号
  tech_params (JSONB)           -- 技术参数(键值对)
  quantity (numeric)
  unit (str)
  unit_price (numeric(18,2))
  cluster_id (UUID FK → cpa_clusters, nullable)
  source_contract_no (str)
  created_at

cpa_clusters        -- 聚类分组
  id (UUID PK)
  category (str)                -- 大类:设备/物资/配件/...
  representative_name (str)     -- 组代表名(归并后的标准名)
  status (str)                  -- pending/confirmed/rejected
  stats (JSONB)                 -- 缓存的统计量(均值/最大/最小/...)
  item_count (int)
  confirmed_by (str, nullable)
  created_at, updated_at

cpa_run_history     -- 分析任务运行历史
  id (UUID PK)
  trigger_type (str)            -- manual/scheduled
  scope (JSONB)                 -- 本次范围(全部/时间段/项目)
  status (str)                  -- running/completed/failed
  docs_processed (int)
  items_extracted (int)
  clusters_formed (int)
  duration_ms (int)
  excel_path (str, nullable)    -- 产出 Excel 路径
  error (text, nullable)
  started_at, finished_at
```

### 4.2 索引

- `cpa_documents(doc_hash)`、`(ragflow_doc_id)`
- `cpa_items(cluster_id)`、`(goods_name)`、`(source_contract_no)`
- `cpa_clusters(status)`、`(category)`

---

## 5. Excel 输出规格(6 类图表,详细版)

使用 `xlsxwriter` 生成。工作簿结构:

| Sheet | 内容 |
|-------|------|
| Sheet1 汇总总表 | 类别 \| 均值 \| 最大 \| 最小 \| 中位数 \| 标准差 \| 合同数 \| 样本数 |
| Sheet2 分项明细 | 货物 \| 参数 \| 单价 \| 来源合同 \| 签订日期 \| 供应商 |
| Sheet3 图表-价格分布 | 每类一组箱线图 |
| Sheet4 图表-价格趋势 | 按合同签订时间的折线图 |
| Sheet5 图表-供应商对比 | 各供应商均价柱状图 |
| Sheet6 图表-区间分布 | 价格区间分布直方图 |

**样式**:条件格式异常值红色高亮;冻结首行首列;数值列右对齐(tabular figures);图表网格线低对比度;图例可见;坐标轴标注单位。

---

## 6. 管理页面 UI 设计

遵循系统 UI 规范(`frontend/src/UI-SPEC.md`):Next.js 16 + React 19 + Tailwind 4 + Shadcn/ui + TanStack Query + lucide-react 图标 + framer-motion 动效。

### 6.1 路由与布局

```
/app/[lang]/contract-price/
├── layout.tsx          # 嵌入 ExtensionsShell 侧边栏(同 admin/docmgr)
├── page.tsx            # 总览看板(功能区6)
├── contracts/page.tsx  # 合同缓存清单(功能区1)
├── clusters/page.tsx   # 聚类审核(功能区2)⭐核心交互页
├── items/page.tsx      # 分项明细(功能区3)
├── tasks/page.tsx      # 任务历史(功能区4)
└── settings/page.tsx   # 配置管理(功能区5)
```

侧边栏新增一项(图标 `PackageSearch`,靛蓝激活态 `text-primary bg-primary/10`),与现有 Knowledge/Docmgr/Admin 平级。

### 6.2 页面布局结构(遵循 UI-SPEC §4.1)

```
页面头部  px-8 py-6
  ├─ 标题区: text-2xl font-bold + text-sm text-muted-foreground 描述
  └─ 操作区: [立即分析] 主按钮 + [设置] outline
工具栏  搜索框 max-w-sm + 筛选 Select + 状态 Badges
内容区  p-8
```

### 6.3 各功能区 UI 规格

**功能区6 — 总览看板**
- 4 列统计卡片(Card):合同数 / 货物条目 / 聚类组数 / 待审核组数(Lucide 图标 + text-3xl 数字 + 同比 Badge)
- 2 列图表区(Recharts):价格区间分布直方图 + 聚类组规模分布
- 最近任务卡片:Table(时间/类型/状态Badge/耗时/Excel下载)

**功能区2 — 聚类审核 ⭐最关键交互(左右分栏)**
- 左侧:聚类组列表(可滚动),待审核组用 `--warning` 黄 Badge,已确认用 `--success` 绿 Badge,含 [合并组][拆分组] 操作
- 右侧:选中组详情 — 统计卡(均值/最大/最小)+ 货物明细表(名称/参数/单价/来源)+ [移出本组] 行操作 + [确认分组] 主按钮
- 移动货物用拖拽(dnd-kit)+ 备选下拉(满足键盘可访问性)
- 异常价格(离群点)行 `bg-destructive/10` + 警示图标高亮

**功能区1/3/4/5** — 标准 Header→Toolbar→Table→Pagination 布局,与 `app/admin/users/page.tsx` 一致。功能区5(配置)用 Card 表单组(聚类参数、定时开关)。

### 6.4 数据获取

- 前端:`@/extensions/api` 模式 + TanStack Query,新增 `contractPriceApi`
- 后端:主 Gateway 扩展 `backend/app/extensions/contract_price/` 提供 REST API(复用 cookie-JWT + 共享 DB),读写 `cpa_` 表

---

## 7. 组件清单(可独立测试的单元)

| 单元 | 职责 | 依赖 |
|------|------|------|
| `ragflow_client.py` | 调用 RAGFlow API:列出文档、拉取解析结果 | RAGFlow API、`RAGFLOW_API_KEY` |
| `parser/` | 文档解析为结构化分项(table/list/mixed 三模式) | ragflow_client |
| `clustering/vectorizer.py` | 文本+技术参数 → 特征向量 | scikit-learn / sentence-transformers |
| `clustering/engine.py` | DBSCAN 聚类 + 噪声点识别 | vectorizer |
| `stats/` | 对 confirmed 组计算统计量 | cpa_clusters/cpa_items |
| `excel_generator.py` | 生成 6-Sheet Excel + 图表 | stats 产出、xlsxwriter |
| `db.py` | PostgreSQL 持久层(crud for cpa_ 表) | postgres-ext |
| `cli.py` | 入口(手动/定时触发,跑完整流水线) | 上述全部 |
| Gateway 扩展 `contract_price/`(routers/service/models) | 管理页面 REST API + 子进程编排流水线 | db.py / skill cli.py |

---

## 8. 错误处理与可靠性

- **RAGFlow 不可用**:API 超时/报错时跳过该文档,记录到 `cpa_documents.parse_status=failed`,流水线继续其余文档,不整体中断
- **OCR 解析失败**:扫描件 OCR 置信度过低时标记 `parse_status=failed` 并在管理页面提示人工介入
- **聚类质量**:`eps`/`min_samples` 参数可在功能区5 配置;离群点显式标为噪声供用户审查
- **定时任务失败**:`cpa_run_history` 记录 error,管理页面展示并提供重试
- **并发**:PostgreSQL 行级锁避免定时任务与管理页写入冲突;聚类审核用乐观锁(version 字段)防止并发覆盖

---

## 9. 测试策略

| 层 | 测试方式 |
|----|----------|
| ragflow_client | mock RAGFlow API 响应,验证增量比对逻辑 |
| parser | 用样例 PDF/Word(含表格、清单、混合)验证三种模式提取正确性 |
| vectorizer | 验证相同货物不同写法、相同名称不同参数的特征向量差异 |
| clustering/engine | 用已知分组的合成数据验证 DBSCAN 归并准确性 |
| stats | 验证均值/最大/最小/中位数计算 |
| excel_generator | 验证 6 个 Sheet 结构、图表存在、条件格式 |
| db.py | 用 test 数据库验证 cpa_ 表 CRUD |
| cli | 端到端:mock RAGFlow → 完整流水线 → 产出 Excel |

---

## 10. 配置

`scripts/config.py`:
```python
import os

RAGFLOW_API_KEY = os.environ["RAGFLOW_API_KEY"]          # 从 .env 读
RAGFLOW_BASE_URL = os.environ.get("RAGFLOW_BASE_URL", "http://localhost:9380/api/v1")
RAGFLOW_KB_ID = os.environ.get("RAGFLOW_KB_ID", "a8e8f3dc660d11f1ad61e1631bd6f152")
DATABASE_URL = os.environ.get("CPA_DATABASE_URL",
    "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow")
OUTPUT_DIR = os.environ.get("CPA_OUTPUT_DIR", "/mnt/user-data/outputs/contract-price/")
```

后端 `.env` 新增:
```
RAGFLOW_API_KEY=<your-key>
RAGFLOW_BASE_URL=http://localhost:9380/api/v1
RAGFLOW_KB_ID=a8e8f3dc660d11f1ad61e1631bd6f152
```

---

## 11. 依赖

### Scripts 层(Python)
- `httpx` — RAGFlow API 调用
- `scikit-learn` — TF-IDF + DBSCAN
- `sentence-transformers`(可选)— 语义向量化
- `xlsxwriter` — Excel 生成
- `sqlalchemy[asyncio]` + `asyncpg` — PostgreSQL 持久层
- _(skill 不再独立运行 API 服务;管理页面 API 由主 Gateway 扩展承载,故 skill 不依赖 `fastapi`/`uvicorn`)_

### 管理页面(前端,复用现有)
- Next.js 16 / React 19 / Tailwind 4 / Shadcn(均已存在)
- `recharts` — 看板图表
- `@dnd-kit/core` — 聚类审核拖拽
- `@tanstack/react-query` — 已存在

---

## 12. 开放问题(实现阶段处理)

- OCR 引擎选择:RAGFlow 内置 OCR 是否够用,还是需额外集成(如 PaddleOCR)
- 技术参数抽取规则:不同货物类别(设备/物资/配件)的关键参数字段定义,需在配置中维护映射表
- 定时任务调度:复用项目现有调度机制还是 skill 内自管(实现阶段确认项目是否有现成 scheduler)
