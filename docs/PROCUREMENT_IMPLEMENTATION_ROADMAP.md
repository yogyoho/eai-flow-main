# 招标采购九大功能技术方案 - 实施路线图

> 基于 EAIFlow 平台构建的招标采购全流程数字化管理模块

## 一、已构建内容（Phase 0 完成）

### 1.1 后端基础设施 (已完成)

#### 数据库模型 (`procurement-service/backend/app/models.py`)

新建 **11 张数据库表**，覆盖招标采购全生命周期：

| 序号 | 表名 | 说明 |
|------|------|------|
| 1 | `tender_plans` | 招标计划 |
| 2 | `tender_projects` | 招标项目 |
| 3 | `evaluation_experts` | 评标专家库 |
| 4 | `expert_draws` | 专家抽取记录 |
| 5 | `bidders` | 投标人库 |
| 6 | `bids` | 投标记录 |
| 7 | `evaluations` | 评标记录 |
| 8 | `winning_bids` | 中标记录 |
| 9 | `contracts` | 合同管理 |
| 10 | `complaints` | 投诉记录 |
| 11 | `witness_records` | 见证记录 |
| 12 | `venue_spaces` | 场所工位 |

**特性**：
- PostgreSQL UUID 主键，支持异步操作
- JSONB 字段存储弹性数据（能力画像、AI分析结果等）
- 完整的索引设计（复合索引、分页优化）
- SQLAlchemy ORM 2.0 风格Mapped Column

#### Pydantic Schema 层 (`procurement-service/backend/app/schemas.py`)

- **枚举定义**：采购方式、项目状态、投标状态、评标状态、合同状态、投诉状态
- **请求/响应 Schema**：Create、Update、Response 分离
- **分页参数**：skip/limit 标准模式
- **AI 辅助 Schema**：`ProcurementDecisionRequest`、`ComplianceCheckRequest`

#### 服务层 (`procurement-service/backend/app/services/`)

| Service | 核心方法 |
|---------|--------|
| `ExpertService` | 专家 CRUD、智能抽取（含回避规则、加权随机算法）、批量导入 |
| `BidderService` | 投标人 CRUD、黑名单管理、批量导入、匹配合格投标人 |
| `TenderPlanService` | 招标计划 CRUD、年度计划查询 |
| `ProjectService` | 招标项目 CRUD、发布/关闭投标流程 |
| `BidService` | 投标 CRUD、撤回、合规性自查（时间/价格/文档检查） |
| `EvaluationService` | 评标 CRUD、核验（专家打分一致性检测）、完成确认 |
| `WinningBidService` | 中标记录创建、确认、合同生成 |
| `ContractService` | 合同 CRUD、签署、激活、完成、终止、风险检测 |
| `ComplaintService` | 投诉 CRUD、答复、决定、AI 分析（类型预测/紧急度评估） |

#### API 路由 (`procurement-service/backend/app/routers/`)

**60+ 个 RESTful 端点**，前缀 `/api/v1`：

```
专家管理:   GET/POST/PUT/DELETE /experts, POST /experts/batch
专家抽取:   POST/GET /expert-draws
专家评价:   POST /expert-reviews
投标人:     GET/POST/PUT/DELETE /bidders, POST /bidders/batch
招标计划:   GET/POST/PUT/DELETE /plans
招标项目:   GET/POST/PUT/DELETE /projects, POST /projects/{id}/publish
投标管理:   GET/POST/PUT/DELETE /bids, POST /bids/{id}/compliance-check
评标管理:   GET/POST /evaluations, POST /evaluations/{id}/verify/complete
中标管理:   POST /winning-bids, PUT/POST /winning-bids/{id}/confirm/contract
合同管理:   GET/POST/PUT/DELETE /contracts, POST /contracts/{id}/risk-check
投诉处理:   GET/POST/PUT /complaints, POST /complaints/{id}/reply/decide
见证记录:   GET/POST /witness-records
场所工位:   GET/POST/PUT /venue-spaces
仪表盘:     GET /dashboard/stats
```

**权限控制**：所有端点通过 `require_permission(resource:action)` 装饰器保护

### 1.2 前端框架 (已完成)

#### 模块结构 (`procurement-service/frontend/src/`)

前端代码位于 `procurement-service/frontend/`，基于 Next.js 独立部署。
通过 Nginx 路由 `/procurement/*` 访问。

#### 页面路由 (`procurement-service/frontend/src/app/page.tsx`)

- 主页面入口
- 侧边栏导航（招标项目、投标管理、评标管理、合同管理等模块）
- EAIFlow 主系统侧边栏"招标采购"链接指向 `/procurement`

---

## 二、待开发内容（按实施阶段）

### Phase 1：核心流程数字化（4-6周）

#### P1.1 招标计划管理（场景2）
**前端组件**：
- `PlanListPage.tsx` - 计划列表（表格+筛选+分页）
- `PlanFormDialog.tsx` - 新增/编辑表单（Dialog）
- `PlanDetailDrawer.tsx` - 详情侧滑抽屉

**AI 增强**：
- 调用 LLM 分析历史中标数据 → 推荐招标策略
- 对接 `采购决策智能体` 进行预算合理性评估

#### P1.2 投标人库 + 投标管理（场景7-8）
**前端组件**：
- `BidderListPage.tsx` - 投标人列表（卡片/表格视图切换）
- `BidderFormDialog.tsx` - 新增投标人表单
- `BidderProfileDrawer.tsx` - 投标人画像（含能力雷达图）
- `BidListPage.tsx` - 投标列表
- `BidSubmissionForm.tsx` - 投标提交表单（含 AI 合规自查）
- `ComplianceCheckPanel.tsx` - 合规检查结果展示

**后端完善**：
- Web Scraper 抓取招标公告 → 推送匹配投标人

#### P1.3 专家库 + 抽取（场景10）
**前端组件**：
- `ExpertListPage.tsx` - 专家列表
- `ExpertFormDialog.tsx` - 专家新增/编辑
- `ExpertDrawDialog.tsx` - 专家抽取界面（选择专业、人数、回避规则）
- `ExpertDrawResultPanel.tsx` - 抽取结果展示 + 确认/替换

#### P1.4 评标管理（场景11）
**前端组件**：
- `EvaluationListPage.tsx` - 评标记录列表
- `EvaluationScoreForm.tsx` - 评分表单（技术分/商务分）
- `EvaluationRankingPanel.tsx` - 排名对照表
- `BidComparisonPanel.tsx` - 投标响应性分析对照表

**后端完善**：
- 多模态解析：PDF/Word 投标文件 → LLM 提取关键要素
- 评审指标体系配置

#### P1.5 档案管理（场景17）
**前端组件**：
- `ArchiveListPage.tsx` - 档案列表（按项目关联）
- `ArchiveViewer.tsx` - 档案查看器
- `ArchiveUploadZone.tsx` - 拖拽上传

### Phase 2：AI 能力深化（4-6周）

#### P2.1 采购决策智能体（场景1）
**实现路径**：
1. 构建 `采购知识库`（采购法规 + 历史案例 + 评分标准）→ RAGFlow
2. 开发 `采购决策 Agent`（LangGraph Subagent）
3. 输入：采购需求描述、预算金额、市场竞争情况
4. 输出：采购方式推荐 + 理由说明 + 风险提示

**API 端点**：已预留 `ProcurementDecisionRequest/Response` Schema

#### P2.2 招标文件 AI 全流程（场景4-6）
**功能点**：
- 招标文件模板库（按类型：工程/货物/服务）
- AI 生成 + 合规检测 + 错敏词检测
- 招标方案审核规则引擎扩展

**关键实现**：
- 复用 Knowledge Factory 的 Rule Engine
- 新增 `tendering_compliance_rules` 规则集

#### P2.3 数字开标人（场景9）
**流程自动化 Agent**：
1. 宣读纪律
2. 公布投标人
3. 标书解密
4. 唱标
5. 异常检测（超时未解密、报价异常）

**API 端点**：已预留 `WitnessRecord` 表和服务

#### P2.4 评标报告核验 + 定标辅助（场景12-13）
**功能点**：
- 规则引擎扩展（评标专项）
- 候选人多维画像（行业+信用+税务+司法+历史交易）
- 数字人答辩 Agent

#### P2.5 智慧问答引擎（场景18）
**构建**：
- 政策法规知识库 → RAGFlow
- 招标问答 Agent（LangGraph Subagent）
- 功能：政策咨询 / 操作引导 / 范本推荐 / 异常预警问答

#### P2.6 智能问数（场景25）
**实现路径**：
- 数据库原子级字段解构 + 关联图谱
- NL2SQL 引擎（自然语言 → SQL）
- 多维分析图表 + 文字解读
- 自适应填表能力

### Phase 3：监管与合规增强（3-4周）

#### P3.1 见证管理（场景16）
- 全流程节点记录
- AI 语音转写（WebRTC + LLM Whisper API）
- 敏感词实时检测 + 违规行为预警

#### P3.2 专家全生命周期管理（场景19）
- 动态考核机制（抽取参与率 + 评标费收入 + 专业匹配度）
- 信用评分模型

#### P3.3 围串标识别（场景20）
**高复杂度 AI 功能**：
- 企业画像 + 关系图谱（工商数据 + 股权穿透）
- 投标行为分析：报价雷同性 + 文件相似度 + 时间规律
- 专家打分异常分析
- 结构化风险报告生成

#### P3.4 信用管理（场景21）
- 招标人画像：信誉 + 履约 + 合作风险
- 投标人画像：信誉 + 财务 + 技术实力 + 中标率分析
- 精准信用评分模型 + 风险预警

#### P3.5 协同监管（场景22）
- 标前/标中/标后全链路数据采集
- 异常预警：应招未招/转包/违法分包/人员变更/进度滞后
- 线索转办系统（预留行刑纪对接接口）

#### P3.6 投诉处理（场景23）
- 异议预处理 Agent：预判异议类型 + 生成答复策略
- 智能答复生成：知识图谱 + 模板 + 历史案例检索
- 投诉处理决定书辅助生成

#### P3.7 管理决策分析（场景24）
- 实时接入政策法规 → 制度完善建议生成
- 投标人知识图谱 + 商情全景透视
- 自动生成统计分析报告

### Phase 4：非招标采购扩展（2-3周）

#### P4.1 非招标采购实施（场景26）
- 复用 Phase 1-2 能力，针对非招标采购特点适配
- 采购方式：单一来源 / 竞争性谈判 / 询价 / 比选
- 简化流程节点 + 适配合规规则

---

## 三、技术架构

> **架构决策**：招标采购模块采用独立微服务方式部署，与 EAIFlow 主系统解耦。前端入口通过 nginx 路由 `/procurement/*` 到独立服务。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Nginx (端口 4026)                                │
│  /procurement/*      → procurement-frontend:3000  (Next.js 独立前端)       │
│  /procurement/api/*  → procurement-backend:3001   (FastAPI 独立后端)       │
│  /api/*              → gateway:4001 / langgraph:4024                        │
│  /                   → frontend:4000                                        │
└──────────────────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌──────────────────────────┐  ┌──────────────────────────────────────────┐
│  Procurement Microservice │  │         EAIFlow Main System               │
│  ┌──────────────────┐  │  │  ┌──────────────┐  ┌──────────────┐  │
│  │  Frontend        │  │  │  │  Frontend   │  │  Gateway    │  │
│  │  (Next.js :3000)│  │  │  │  (Next.js)  │  │  (FastAPI)  │  │
│  └──────────────────┘  │  │  └──────────────┘  └──────────────┘  │
│  ┌──────────────────┐  │  │  ┌──────────────┐  ┌──────────────┐  │
│  │  Backend        │  │  │  │ LangGraph   │  │ LangGraph   │  │
│  │  (FastAPI :3001)│  │  │  │   :4024    │  │  Server    │  │
│  └──────────────────┘  │  │  └──────────────┘  └──────────────┘  │
│  ┌──────────────────┐  │  │                                       │
│  │  PostgreSQL     │  │  │  ┌──────────────┐  ┌──────────────┐  │
│  │  (独立 DB :5432)│  │  │  │ PostgreSQL   │  │ Redis      │  │
│  └──────────────────┘  │  │  │              │  │            │  │
└──────────────────────────┘  │  └──────────────┘  └──────────────┘  │
                               └──────────────────────────────────────────┘
```

### JWT 共享认证
- 招标微服务通过相同的 `JWT_SECRET_KEY` 验证 EAIFlow Gateway 签发的 Token
- 前端从 EAIFlow 侧边栏入口访问 `/procurement`，携带 localStorage 中的 JWT
- 双方共享同一套用户登录态

### 集成点
1. **Nginx 路由**：`/procurement/*` → 微服务前端；`/procurement/api/*` → 微服务后端
2. **JWT 认证**：共享密钥验证，招标微服务独立验证 Token
3. **侧边栏导航**：EAIFlow 侧边栏"招标采购"链接指向 `/procurement`

### LangGraph Agent 扩展

```python
TENDERING_AGENTS = {
    "tendering_plan": TenderingPlanAgent,    # 场景2,3
    "bid_eval": BidEvaluationAgent,             # 场景11,12
    "decision_mk": DecisionMakerAgent,          # 场景1,13,24
    "qa_engine": QAEngineAgent,                 # 场景18
    "nl2sql": NL2SQLAgent,                      # 场景25
    "compliance_check": ComplianceCheckAgent,   # 场景6,8
    "witness": WitnessAgent,                   # 场景16
    "credit_analysis": CreditAnalysisAgent,     # 场景21
    "bid_suspect": BidSuspectAgent,            # 场景20
    "complaint": ComplaintAgent,               # 场景23
}
```

### RAGFlow 知识库扩展

```
RAGFlow Datasets:
├── 采购法规库（国家/地方政策法规）
├── 招标文件范本库（工程/货物/服务）
├── 历史中标案例库
├── 招标人/投标人信用数据
├── 投诉处理案例库
└── 制度规范库
```

---

## 四、文件清单

### 后端新增文件

> 注：以下文件位于 `procurement-service/backend/`，**不在** `backend/` 主系统中。

| 文件路径 | 说明 |
|---------|------|
| `procurement-service/backend/app/__init__.py` | 模块入口 |
| `procurement-service/backend/app/models.py` | 11张表 ORM 模型 |
| `procurement-service/backend/app/schemas.py` | Pydantic Schema（含枚举、请求/响应） |
| `procurement-service/backend/app/routers/` | 路由模块（experts, bidders, plans, projects, bids, evaluations, contracts, complaints, witness_records, venue_spaces, dashboard, winning_bids）|
| `procurement-service/backend/app/services/` | 服务层模块 |

### 前端新增文件

> 注：以下文件位于 `procurement-service/frontend/`，**不在** `frontend/` 主系统中。

| 文件路径 | 说明 |
|---------|------|
| `procurement-service/frontend/src/app/page.tsx` | 招标采购主页面入口 |
| `procurement-service/frontend/src/components/ProcurementPage.tsx` | 页面组件 |
| `procurement-service/frontend/src/components/layout/` | 布局组件（侧边栏、顶栏等）|

### 后端修改文件

| 文件路径 | 修改内容 | 状态 |
|---------|---------|------|
| `docker/nginx/nginx.conf` | 添加 `/procurement/*` 和 `/procurement/api/*` 路由 | ✅ 已完成 |
| `docker/docker-compose-dev.yaml` | 添加 procurement-backend / frontend / db 服务 | ✅ 已完成 |
| `docker/docker-compose.yaml` | 添加 procurement 服务到 production 编排 | ✅ 已完成 |

### 前端修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `frontend/src/extensions/shell/Sidebar.tsx` | 保留「招标采购」导航项指向 `/procurement` |

---

## 五、数据库迁移

> **注意**：招标微服务使用独立的 PostgreSQL 数据库，与 EAIFlow 主库分离。

### procurement-service 数据库

在 `procurement-db` 容器首次启动后，FastAPI 会在启动时自动执行 `Base.metadata.create_all()` 创建所有表。

首次部署时需要执行数据库迁移，创建所有新表：

```bash
# procurement-service 使用独立数据库，连接信息：
# DATABASE_URL=postgresql+asyncpg://procurement:procurement@procurement-db:5432/procurement
# JWT_SECRET_KEY 与 EAIFlow gateway 保持一致

# 表清单（共 12 张）：
CREATE TABLE evaluation_experts (...);   -- 评标专家库
CREATE TABLE expert_draws (...);        -- 专家抽取记录
CREATE TABLE expert_reviews (...);       -- 专家评价
CREATE TABLE bidders (...);              -- 投标人库
CREATE TABLE tender_plans (...);        -- 招标计划
CREATE TABLE tender_projects (...);     -- 招标项目
CREATE TABLE bids (...);               -- 投标记录
CREATE TABLE evaluations (...);         -- 评标记录
CREATE TABLE winning_bids (...);        -- 中标记录
CREATE TABLE contracts (...);           -- 合同管理
CREATE TABLE complaints (...);          -- 投诉记录
CREATE TABLE witness_records (...);     -- 见证记录
CREATE TABLE venue_spaces (...);       -- 场所工位
```

> **提示**：`procurement-service/backend/app/database.py` 中的 `init_db()` 会自动调用 `Base.metadata.create_all()`，无需手动迁移。

### 迁移说明

`backend/app/extensions/tendering/` 目录已删除，招标采购业务使用 procurement-service 独立数据库。

---

## 六、优先级矩阵（更新）

| 优先级 | 场景 | 说明 | 状态 |
|--------|------|------|------|
| **P0** | 1, 5, 6, 11, 17, 18 | 核心AI能力体现，用户感知最强 | 框架已建，AI能力待实现 |
| **P1** | 2, 7, 10, 13, 21 | 支撑核心流程的基础模块 | 基础CRUD已完成 |
| **P2** | 3, 4, 8, 9, 12, 14, 19, 25 | 完整流程闭环所需 | 框架已建 |
| **P3** | 15, 16, 20, 22, 23, 24, 26 | 进阶监管和特色功能 | 框架已建 |

---

## 七、分阶段实施路线图与优先级

### 7.1 总体路线图概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      招标采购模块实施路线图（总工期：约 20 周）               │
├──────────┬──────────────┬──────────────┬──────────────┬───────────────────┤
│ Phase 0  │   Phase 1    │   Phase 2    │   Phase 3    │     Phase 4       │
│ 基础就绪 │  核心数字化   │  AI能力深化  │ 监管合规增强  │ 非招标采购扩展    │
│  (0-2周) │  (4-6周)     │  (4-6周)     │  (3-4周)     │   (2-3周)         │
├──────────┼──────────────┼──────────────┼──────────────┼───────────────────┤
│ 基础设施  │ 招标计划管理  │ 采购决策智能体│ 见证管理      │ 非招标采购实施   │
│ 微服务部署 │ 投标人库     │ 招标文件AI  │ 专家全周期管理│ 流程适配         │
│ JWT认证   │ 投标管理     │ 数字开标人   │ 围串标识别    │ 合规规则适配     │
│ 数据库初始化│ 专家库抽取  │ 评标报告核验 │ 信用管理      │                  │
│ Nginx路由 │ 评标管理     │ 智慧问答引擎 │ 协同监管      │                  │
│ 前端框架  │ 档案管理     │ 智能问数     │ 投诉处理      │                  │
│          │              │              │ 管理决策分析   │                  │
└──────────┴──────────────┴──────────────┴──────────────┴───────────────────┘
```

### 7.2 各阶段详细计划

---

#### Phase 0：基础就绪（第 0-2 周）

**目标**：完成招标采购微服务的完整基础设施搭建，实现可运行的最简可用系统。

| 序号 | 任务 | 负责 | 工时(人天) | 依赖 | 验收标准 |
|------|------|------|-----------|------|---------|
| P0.1 | procurement-service 后端目录结构 + pyproject.toml | 后端 | 2 | 无 | 依赖可安装 |
| P0.2 | FastAPI 骨架：main.py、config.py、database.py、auth.py | 后端 | 3 | P0.1 | `curl localhost:3001/health` 返回 200 |
| P0.3 | SQLAlchemy ORM 模型：11 张表（含索引、JSONB 字段） | 后端 | 5 | P0.2 | `python -c "from app.models import *; print('OK')"` |
| P0.4 | Pydantic Schema：枚举 + Create/Update/Response | 后端 | 3 | P0.3 | 11 张表各有 3+ Schema |
| P0.5 | Service 层：9 个服务类的 CRUD 方法骨架 | 后端 | 5 | P0.4 | pytest 覆盖基础 CRUD |
| P0.6 | Router 层：60+ API 端点骨架（含路由注册） | 后端 | 4 | P0.5 | `GET /docs` 可见所有端点 |
| P0.7 | procurement-service 前端目录结构 + package.json + next.config.js | 前端 | 2 | 无 | `pnpm install` 成功 |
| P0.8 | 前端基础布局：layout.tsx、ProcurementPage.tsx 框架 | 前端 | 3 | P0.7 | 页面可访问、无 TS 错误 |
| P0.9 | 前端类型定义：types.ts（含枚举常量） | 前端 | 2 | P0.4 | TypeScript 无 error |
| P0.10 | 前端 API 客户端：api.ts（含 8 子模块 axios 实例） | 前端 | 3 | P0.9 | API 方法签名与后端对应 |
| P0.11 | 前端 Hooks：hooks.ts（TanStack Query 封装） | 前端 | 3 | P0.10 | 数据可正常获取 |
| P0.12 | Nginx 配置：添加 /procurement/* 和 /procurement/api/* 路由 | DevOps | 2 | P0.6 | 访问 /procurement/api/v1/dashboard/stats |
| P0.13 | Docker Compose 集成：procurement-backend/frontend/db 服务 | DevOps | 3 | P0.12 | `docker-compose -f docker-compose-dev.yaml up` 全量成功 |
| P0.14 | EAIFlow 侧边栏集成：Sidebar.tsx 添加「招标采购」入口 | 前端 | 1 | P0.8 | 侧边栏链接可点击 |
| P0.15 | JWT 认证联调：procurement 微服务可验证 EAIFlow Token | 后端 | 3 | P0.6, P0.14 | Token 有效时 API 可访问，无效时 401 |

**里程碑**：第 2 周末 —— 微服务可完整运行，60+ API 全部可达，前端 11 个 Tab 面板框架就绪。

**风险**：
- R0.1: procurement-db 启动慢导致后端启动失败 → 缓解：后端增加 `depends_on: condition: service_healthy` + wait script
- R0.2: JWT 密钥共享方式不稳定 → 缓解：环境变量注入，日志记录验签失败原因

---

#### Phase 1：核心流程数字化（第 3-8 周）

**目标**：将招标采购的核心业务流程全面数字化，所有基础 CRUD 功能可用，数据链路打通。

##### 1.1 招标计划管理（场景2，第 3-4 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 招标计划列表页（表格+筛选+分页）| 前端 | 3 | Phase 0 |
| 招标计划新增/编辑 Dialog 表单 | 前端 | 2 | Phase 0 |
| 招标计划详情 Drawer 侧滑面板 | 前端 | 2 | Phase 0 |
| 招标计划年度汇总 API（按年月分组） | 后端 | 2 | Phase 0 |
| 前端年度计划视图切换（Tab：月/季/年） | 前端 | 2 | 前3项 |

##### 1.2 招标项目全流程（场景3-5，第 4-6 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 招标项目列表页 + 状态筛选 | 前端 | 3 | Phase 0 |
| 招标项目新增/编辑表单（含审批流占位） | 前端 | 4 | Phase 0 |
| 招标公告发布页面（填写信息+预览+发布） | 前端 | 4 | Phase 0 |
| 招标公告发布 API（含状态流转：草稿→公告→投标→开标→评标→定标） | 后端 | 3 | Phase 0 |
| 项目详情页：Tab（基本信息/投标/评标/合同） | 前端 | 4 | 前4项 |
| 招标文件模板管理（上传/下载/预览 PDF） | 前端 | 3 | Phase 0 |
| Web Scraper：抓取外部招标公告 + 推送 | 后端 | 5 | Phase 0 |

##### 1.3 投标人库（场景7，第 5-6 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 投标人列表页（卡片/表格视图切换） | 前端 | 3 | Phase 0 |
| 投标人新增/编辑表单 | 前端 | 2 | Phase 0 |
| 投标人画像 Drawer（能力雷达图） | 前端 | 4 | Phase 0 |
| 投标人批量导入（Excel + 格式校验） | 后端 | 4 | Phase 0 |
| 投标人匹配合格供应商 API（按资质/业绩过滤） | 后端 | 3 | Phase 0 |

##### 1.4 投标管理（场景8，第 6-7 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 投标列表页（按项目筛选） | 前端 | 2 | 1.3 |
| 投标提交表单（基本信息 + 文件上传） | 前端 | 4 | 1.3 |
| 投标合规性自查 Panel（时间/价格/文档检查） | 前端 | 3 | Phase 0 |
| 投标合规检查 API（时间窗口 + 价格范围 + 文件格式） | 后端 | 4 | Phase 0 |
| 投标撤回功能（仅限截止前） | 前端 | 2 | Phase 0 |

##### 1.5 专家库与抽取（场景10，第 5-7 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 专家列表页（专业/职称/机构筛选） | 前端 | 3 | Phase 0 |
| 专家新增/编辑 Dialog | 前端 | 2 | Phase 0 |
| 专家抽取 Dialog（选择专业、人数、回避规则） | 前端 | 5 | Phase 0 |
| 抽取算法实现（加权随机 + 回避规则 + 随机性） | 后端 | 5 | Phase 0 |
| 抽取结果 Panel（确认/替换专家） | 前端 | 3 | 前2项 |
| 专家批量导入 | 后端 | 3 | Phase 0 |

##### 1.6 评标管理（场景11，第 7-8 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 评标记录列表页 | 前端 | 2 | 1.4 |
| 评标评分表单（技术分/商务分 + 权重） | 前端 | 5 | Phase 0 |
| 评分排名 Panel（得分排序 + 中标建议） | 前端 | 3 | Phase 0 |
| 投标响应性分析对照表（多列对比） | 前端 | 4 | 1.4 |
| 评标核验 API（专家打分一致性检测） | 后端 | 4 | Phase 0 |
| 评标完成确认 API（锁定结果 + 流转状态） | 后端 | 3 | Phase 0 |

##### 1.7 档案管理（场景17，第 8 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 档案列表页（按项目关联展示） | 前端 | 2 | 1.6 |
| 档案上传 Zone（拖拽 + 进度条） | 前端 | 3 | Phase 0 |
| 档案查看器（PDF/Word 在线预览） | 前端 | 4 | Phase 0 |

**里程碑**：第 8 周末 —— 招标全流程（计划→项目→公告→投标→评标→档案）数字化完成，无断点。

**阶段验收测试用例**：
1. 创建招标计划 → 发布招标公告 → 投标 → 评标 → 生成中标记录 → 归档，全链路可走通
2. 抽取专家满足回避规则，重复抽取率 < 5%
3. 投标合规检查在 2 秒内返回结果

**风险**：
- R1.1: 前端组件数量多（20+ 组件），一人开发周期过长 → 缓解：后端和前端并行开发
- R1.2: PDF 预览依赖第三方库（如 pdf.js），兼容性风险 → 缓解：使用 iframe embed 作为 fallback

---

#### Phase 2：AI 能力深化（第 9-14 周）

**目标**：在核心流程数字化基础上，叠加 AI 智能能力，实现"智慧招标"。

##### 2.1 采购决策智能体（场景1，第 9-10 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 采购知识库构建（RAGFlow：法规+历史案例+评分标准） | 后端 | 5 | Phase 1 |
| 采购决策 Agent 实现（LangGraph Subagent） | 后端 | 8 | Phase 0 |
| 采购方式推荐 API + 前端集成（计划新增页内嵌 AI 建议） | 全栈 | 4 | 前2项 |

##### 2.2 招标文件 AI 全流程（场景4-6，第 10-12 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 招标文件模板库（工程/货物/服务 三类） | 前端 | 5 | Phase 1 |
| AI 生成招标文件（输入需求描述，输出草稿） | 后端 | 8 | Phase 0 |
| 招标文件合规检测（法规条文对照） | 后端 | 6 | 2.1 |
| 错敏词检测（政治/色情/违规表述） | 后端 | 4 | Phase 0 |
| 招标方案审核规则引擎扩展（新增 tendering_compliance_rules） | 后端 | 5 | Phase 0 |

##### 2.3 数字开标人（场景9，第 11-12 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 开标流程自动化 Agent（宣读纪律→解密→唱标→异常检测） | 后端 | 10 | Phase 1 |
| 异常检测：超时未解密、报价偏离基准价 20%+ | 后端 | 5 | Phase 1 |
| 见证记录自动生成（节点时间戳 + 事件摘要） | 后端 | 3 | Phase 0 |
| 开标过程 WebSocket 实时推送（前端进度条） | 全栈 | 6 | Phase 1 |

##### 2.4 评标报告核验 + 定标辅助（场景12-13，第 12-13 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 评标报告 AI 核验（打分明细一致性 + 异常打分标记） | 后端 | 6 | Phase 1 |
| 候选人多维画像（工商+税务+司法+历史交易） | 后端 | 8 | Phase 1 |
| 定标建议 API（综合评分 + 画像 + 历史中标率） | 后端 | 5 | 前2项 |
| 定标建议 UI（评委操作界面内嵌展示） | 前端 | 4 | 前3项 |

##### 2.5 智慧问答引擎（场景18，第 13-14 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 政策法规知识库构建（RAGFlow） | 后端 | 4 | Phase 0 |
| 招标问答 Agent（政策咨询/操作引导/范本推荐/预警） | 后端 | 8 | 前1项 |
| 问答前端界面（搜索框 + 卡片式答案 + 来源标注） | 前端 | 4 | 前2项 |

##### 2.6 智能问数（场景25，第 14 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 数据库字段解构 + 关联图谱构建 | 后端 | 5 | Phase 1 |
| NL2SQL 引擎（自然语言 → SQL） | 后端 | 8 | Phase 0 |
| 多维分析图表 + 文字解读 UI | 前端 | 4 | 前2项 |

**里程碑**：第 14 周末 —— AI 能力全面融入业务流程，智慧招标从概念走向可用。

**阶段验收测试用例**：
1. 提交采购需求 → AI 推荐采购方式（3 种方案备选） → 评委确认
2. 导入招标文件 → AI 检测出 3 处合规风险
3. 评标数据 → AI 自动生成核验报告，发现 1 处异常打分

**风险**：
- R2.1: RAGFlow 知识库质量直接影响 AI 输出可靠性 → 缓解：建立知识库质量评审流程，每批数据入库前人工抽检 10%
- R2.2: NL2SQL 生成的 SQL 有误导致数据错误 → 缓解：关键查询增加二次确认步骤，仅展示类查询允许自由探索

---

#### Phase 3：监管与合规增强（第 15-18 周）

**目标**：满足监管部门要求，增强合规审查、风险预警、跨系统协同能力。

##### 3.1 见证管理（场景16，第 15 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 全流程节点自动记录（时间戳 + 事件类型 + 操作人） | 后端 | 4 | Phase 1 |
| 语音转写集成（WebRTC + LLM Whisper API） | 后端 | 6 | Phase 2 |
| 敏感词实时检测 + 违规行为预警 | 后端 | 5 | 前1项 |
| 见证记录查看器（时间线 + 语音回放） | 前端 | 4 | 前3项 |

##### 3.2 专家全生命周期管理（场景19，第 15-16 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 专家动态考核机制（抽取参与率 + 评标费收入 + 专业匹配度） | 后端 | 5 | Phase 1 |
| 专家信用评分模型（综合评分 + 分级） | 后端 | 6 | Phase 0 |
| 专家画像 Dashboard（能力雷达 + 历史评标 + 评分分布） | 前端 | 4 | Phase 1 |

##### 3.3 围串标识别（场景20，第 16-17 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 企业画像 + 关系图谱（工商数据 + 股权穿透） | 后端 | 8 | Phase 1 |
| 投标行为分析（报价雷同性 + 文件相似度 + 时间规律） | 后端 | 8 | Phase 2 |
| 专家打分异常分析（偏离均值 2σ 以上） | 后端 | 5 | Phase 1 |
| 风险报告生成 API + 可疑行为高亮 UI | 全栈 | 5 | 前3项 |

##### 3.4 信用管理（场景21，第 17 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 招标人画像（信誉 + 履约 + 合作风险） | 后端 | 5 | Phase 1 |
| 投标人画像（信誉 + 财务 + 技术实力 + 中标率分析） | 后端 | 6 | Phase 3.3 |
| 精准信用评分模型（综合评分 0-100） | 后端 | 5 | 前2项 |
| 信用报告页面 + 风险预警通知 | 前端 | 4 | 前3项 |

##### 3.5 协同监管（场景22，第 17-18 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 标前/标中/标后全链路数据采集 + 异常预警规则 | 后端 | 6 | Phase 1 |
| 预警规则配置界面（应招未招/转包/违法分包/进度滞后） | 前端 | 4 | Phase 1 |
| 线索转办系统（预留行刑纪对接接口） | 后端 | 5 | Phase 0 |
| 监管大屏 Dashboard（关键指标 + 预警统计） | 前端 | 5 | 前3项 |

##### 3.6 投诉处理（场景23，第 18 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 异议预处理 Agent（预判类型 + 生成答复策略） | 后端 | 6 | Phase 2 |
| 智能答复生成（知识图谱 + 模板 + 历史案例） | 后端 | 5 | Phase 2 |
| 投诉处理决定书辅助生成 | 后端 | 4 | Phase 2 |
| 投诉处理工作台 UI（流程状态 + AI 辅助面板） | 前端 | 5 | 前3项 |

##### 3.7 管理决策分析（场景24，第 18 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 实时政策法规接入 → 制度完善建议生成 | 后端 | 5 | Phase 2 |
| 投标人知识图谱 + 商情全景透视 | 后端 | 5 | Phase 3.4 |
| 统计分析报告自动生成（周报/月报模板） | 后端 | 4 | Phase 1 |
| 报告导出（Word/PDF）+ 自动推送 | 前端 | 3 | 前3项 |

**里程碑**：第 18 周末 —— 监管合规体系全面就绪，满足各级监管部门的合规要求。

**风险**：
- R3.1: 外部数据源（工商/税务/司法）API 不稳定 → 缓解：实现熔断器 + 本地缓存，数据过期时展示"数据更新中"而非报错
- R3.2: 围串标识别误报率高 → 缓解：初期设为"参考"模式，不自动拦截，人工确认后再升级为"预警"

---

#### Phase 4：非招标采购扩展（第 19-21 周）

**目标**：覆盖非招标采购场景（单一来源/竞争性谈判/询价/比选），复用 Phase 1-3 能力。

##### 4.1 非招标采购实施（场景26，第 19-20 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 扩展采购方式枚举（增加单一来源/竞争性谈判/询价/比选） | 后端 | 2 | Phase 0 |
| 适配简化流程节点（非招标：无专家抽取，流程缩短） | 后端 | 5 | Phase 1 |
| 非招标采购申请表单（选择方式 + 理由说明 + 审批流） | 前端 | 5 | Phase 1 |
| 非招标合规规则适配（每种方式对应不同合规检查点） | 后端 | 4 | Phase 2 |

##### 4.2 供应商直推 + 比选（场景7扩展，第 20-21 周）

| 任务 | 负责 | 工时(人天) | 依赖 |
|------|------|-----------|------|
| 供应商直推功能（向合格供应商发送采购邀请） | 前端 | 4 | Phase 1.3 |
| 多供应商比选 Panel（报价对比 + 技术方案对比） | 前端 | 5 | Phase 1.4 |
| 竞争性谈判流程（多轮报价 + 谈判记录） | 全栈 | 8 | 前2项 |

**里程碑**：第 21 周末 —— 招标+非招标全覆盖，26 个场景全部可运行。

---

### 7.3 资源规划

#### 团队配置（建议）

| 角色 | 人数 | 职责 |
|------|------|------|
| 后端工程师 | 2 | FastAPI 微服务、AI Agent、RAGFlow、Rule Engine |
| 前端工程师 | 1 | Next.js 组件、API 集成、UI/UX |
| AI/数据工程师 | 1 | LangGraph Agent、NL2SQL、知识库、质量评审 |
| DevOps | 0.5 | Docker/K8s、Nginx、数据库、CI/CD |
| 产品/需求 | 1 | 业务梳理、需求澄清、UAT 验收 |

#### 总体工时估算

| Phase | 后端 | 前端 | AI/数据 | DevOps | 合计(人天) |
|-------|------|------|---------|--------|-----------|
| Phase 0 | 20 | 10 | 0 | 5 | 35 |
| Phase 1 | 30 | 40 | 0 | 0 | 70 |
| Phase 2 | 50 | 20 | 30 | 0 | 100 |
| Phase 3 | 50 | 25 | 10 | 0 | 85 |
| Phase 4 | 20 | 15 | 0 | 0 | 35 |
| **合计** | **170** | **110** | **40** | **5** | **325** |

按 5 人团队并行工作，约 **13 周**（含缓冲）完成全部实施。

---

### 7.4 优先级决策依据

采用 **ICE Score**（Impact × Confidence × Ease）对 26 个场景打分，决定 Phase 内优先级：

| 维度 | 1分 | 2分 | 3分 |
|------|-----|-----|-----|
| **Impact（业务价值）** | 边缘功能 | 重要功能 | 核心功能 |
| **Confidence（实现确定性）** | 新技术探索，有不确定性 | 复用相似实现 | 成熟技术，100% 可行 |
| **Ease（实现难易）** | >10 人天 | 5-10 人天 | <5 人天 |

**打分结果汇总**：

| 场景 | 名称 | Impact | Confidence | Ease | ICE 分数 | Phase |
|------|------|--------|-----------|------|---------|-------|
| 1 | 采购决策智能体 | 3 | 2 | 2 | 12 | Phase 2 |
| 2 | 招标计划管理 | 3 | 3 | 3 | 27 | Phase 1 |
| 3 | 采购需求分析 | 3 | 2 | 2 | 12 | Phase 2 |
| 4 | 招标公告生成 | 3 | 2 | 2 | 12 | Phase 2 |
| 5 | 招标文件审核 | 3 | 2 | 2 | 12 | Phase 2 |
| 6 | 招标文件合规检测 | 3 | 3 | 2 | 18 | Phase 2 |
| 7 | 投标人库 | 3 | 3 | 3 | 27 | Phase 1 |
| 8 | 投标管理 | 3 | 3 | 3 | 27 | Phase 1 |
| 9 | 数字开标人 | 2 | 2 | 1 | 4 | Phase 2 |
| 10 | 专家库抽取 | 3 | 3 | 3 | 27 | Phase 1 |
| 11 | 评标管理 | 3 | 3 | 3 | 27 | Phase 1 |
| 12 | 评标报告核验 | 3 | 2 | 2 | 12 | Phase 2 |
| 13 | 定标辅助 | 3 | 2 | 2 | 12 | Phase 2 |
| 14 | 合同管理 | 3 | 3 | 3 | 27 | Phase 1 |
| 15 | 合同履约跟踪 | 2 | 3 | 2 | 12 | Phase 3 |
| 16 | 见证管理 | 2 | 2 | 2 | 8 | Phase 3 |
| 17 | 档案管理 | 3 | 3 | 3 | 27 | Phase 1 |
| 18 | 智慧问答引擎 | 2 | 3 | 2 | 12 | Phase 2 |
| 19 | 专家全周期管理 | 2 | 2 | 2 | 8 | Phase 3 |
| 20 | 围串标识别 | 2 | 1 | 1 | 2 | Phase 3 |
| 21 | 信用管理 | 2 | 2 | 2 | 8 | Phase 3 |
| 22 | 协同监管 | 2 | 2 | 2 | 8 | Phase 3 |
| 23 | 投诉处理 | 2 | 2 | 2 | 8 | Phase 3 |
| 24 | 管理决策分析 | 2 | 2 | 2 | 8 | Phase 3 |
| 25 | 智能问数 | 2 | 2 | 1 | 4 | Phase 2 |
| 26 | 非招标采购 | 3 | 3 | 3 | 27 | Phase 4 |

**核心优先（ICE ≥ 20）**：场景 2, 7, 8, 10, 11, 14, 17 → 全部纳入 Phase 1
**AI 深化（ICE 10-18）**：场景 1, 3, 4, 5, 6, 9, 12, 13, 18, 25 → Phase 2
**监管合规（ICE ≤ 10）**：场景 15, 16, 19, 20, 21, 22, 23, 24, 26 → Phase 3+4

---

### 7.5 关键依赖与里程碑

```
W2  ── 微服务可运行 ────────────────────────── Phase 0 完成
W8  ── 核心流程数字化完成 ───────────────────── Phase 1 完成
W14 ── AI 能力全面融入 ──────────────────────── Phase 2 完成
W18 ── 监管合规体系就绪 ─────────────────────── Phase 3 完成
W21 ── 26 个场景全部可运行 ──────────────────── Phase 4 完成

关键路径（最长链路）：
微服务部署 (W2) → 评标管理 (W8) → AI核验 (W14) → 围串标识别 (W18)
```

---

### 7.6 测试策略

| 阶段 | 测试类型 | 覆盖率目标 | 工具 |
|------|---------|-----------|------|
| Phase 0 | 单元测试（API CRUD） | 80% 路由 | pytest + pytest-asyncio |
| Phase 1 | API 集成测试（全链路） | 100% 关键路径 | Playwright E2E |
| Phase 2 | AI 能力评估（人工评审） | 随机抽检 10% | 人工评审 + 评分量表 |
| Phase 3 | 合规规则回归测试 | 每条规则有对应测试用例 | pytest |
| Phase 4 | UAT（用户验收测试） | 业务方 100% 签字 | 业务方 + 产品 |

---

### 7.7 运维与监控

| 能力 | 实现方式 |
|------|---------|
| 日志 | 结构化 JSON 日志（procurement-backend → Loki） |
| 指标 | Prometheus metrics 端点（/metrics） |
| 告警 | Alertmanager → 飞书/邮件（AI 响应超时 > 30s、数据库连接失败） |
| 链路追踪 | OpenTelemetry + Jaeger（AI Agent 调用链） |
| 备份 | procurement-db 每日全量备份，保留 30 天 |
| 灰度发布 | 前端：通过 `?version=canary` 参数切换；后端：滚动更新 25% pod |

---

### 7.8 本规划与已构建内容的对应关系

| 已完成内容 | 对应规划位置 | 状态 |
|-----------|------------|------|
| `procurement-service/backend/app/models.py` | Phase 0 / P0.3 | ✅ |
| `procurement-service/backend/app/schemas.py` | Phase 0 / P0.4 | ✅ |
| `procurement-service/backend/app/services/` | Phase 0 / P0.5 | ✅ |
| `procurement-service/backend/app/routers/` | Phase 0 / P0.6 | ✅ |
| `frontend/src/extensions/shell/Sidebar.tsx` | Phase 0 / P0.14 | ✅ |
| `docker/nginx/nginx.conf` | Phase 0 / P0.12 | ✅ |
| `docker/docker-compose-dev.yaml` | Phase 0 / P0.13 | ✅ |
| `docker/docker-compose.yaml` | Phase 0 / P0.13 | ✅ |
| `procurement-service/` 微服务代码框架 | Phase 0 全部 | ✅ |

**下一步行动**：Phase 1 启动前，需先完成 Phase 0 所有遗留项（procurement-service 微服务代码框架）的代码补全和联调测试。
