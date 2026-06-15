---
name: contract-price-analysis
description: |
  当用户需要从 RAGFlow 合同知识库中提取分项价格、对同类货物（设备/物资/配件）按
  名称+技术参数聚类归并、计算单价均值/最大/最小值并导出带图表的 Excel 报告时使用此技能。
  触发场景：用户提及"合同价格分析""分项价格汇总""货物单价对比""采购价格统计"
  "合同分项提取""聚类分析价格""合同金额提取"等关键词；或需要批量统计合同中同类货物价格时。
  支持手动触发和定时增量更新。
---

# 合同分项价格分析技能

## ⛏️ 关键规则

1. 本技能通过 `scripts/cli.py` 执行数据流水线，产出 Excel 报告到 `/mnt/user-data/outputs/contract-price/`。
2. 解析模式（表格/清单/混合）由用户在调用时指定，默认 `table`。
3. 聚类基于"货物名称 + 技术参数"双维度，使用 DBSCAN 自动归并同类货物；离群价格标为噪声供人工审核。
4. 自动聚类结果需用户在管理页面审核确认（`status=confirmed`）后统计才作为最终结论。
5. 缓存与持久化使用 PostgreSQL `postgres-ext`，表前缀 `cpa_`；DB 不可达时流水线仍可解析/聚类/导出（跳过持久化）。
6. 不直接生成 .docx；只产出 Excel。不使用 procurement-service 代码。
7. 管理页面 API 已挂载到主后端 Gateway 扩展 `backend/app/extensions/contract_price/`（复用 cookie-JWT 认证 + 共享 DB 引擎），路由前缀 `/api/extensions/contract-price`。本技能 `scripts/` 仅保留流水线逻辑。

## 工作流

### 步骤1：确认参数
- 解析模式（表格 `table` / 清单 `list` / 混合 `mixed`）
- 触发方式（手动 `manual` / 定时 `scheduled`）
- 分析范围（全部合同 / 指定时间段 / 指定项目）—— 当前 CLI 默认全量增量

### 步骤2：执行流水线
```bash
cd skills/custom/contract-price-analysis
PYTHONPATH=. python -m scripts.cli --mode table --trigger manual
```

### 步骤3：报告结果
向用户报告：处理合同数、提取分项数、聚类组数、待审核（异常价格）组数、Excel 文件路径。

## 增量机制
通过 `cpa_documents.doc_hash` 与 RAGFlow 返回的文档 hash 比对，只重新解析新增/变更的合同，避免全量重算。

## 聚类说明
- **特征**：货物名称的 char-ngram TF-IDF 向量 ⊕ 技术参数（电压/电流/容量等）标准化数值向量。
- **算法**：DBSCAN（cosine 距离，eps=0.6，min_samples=2），无需预设簇数，离群点标为 -1。
- **为什么含技术参数**：同名不同规格的货物（如 10kV vs 35kV 开关柜）价格差异巨大，仅按名称聚类会让均值失真。

## Excel 产出（6 个 Sheet）
1. 汇总总表（类别/均值/最大/最小/中位数/标准差/异常值数）
2. 分项明细（货物/规格/参数/单价/来源合同/签订日期/供应商/是否异常）
3. 图表-价格分布（各组均价柱状图）
4. 图表-价格趋势（各组均价折线图）
5. 图表-供应商对比（各供应商均价柱状图）
6. 图表-区间分布（价格区间分布直方图）

## 环境依赖
- 环境变量：`RAGFLOW_API_KEY`（必需）、`RAGFLOW_BASE_URL`、`RAGFLOW_KB_ID`、`CPA_DATABASE_URL`、`CPA_OUTPUT_DIR`
- Python 包：见 `requirements.txt`（httpx、scikit-learn、xlsxwriter、sqlalchemy[asyncio]、asyncpg）
- 数据库：PostgreSQL `postgres-ext`（`cpa_` 前缀表）

## 参考文档
- 设计文档：`docs/superpowers/specs/2026-06-15-contract-price-analysis-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-15-contract-price-analysis-pipeline.md`
