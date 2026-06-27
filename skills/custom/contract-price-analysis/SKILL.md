---
name: contract-price-analysis
description: |
  当用户需要从合同扫描件中提取分项价格(工程量清单计价表)、对同类货物(设备/物资/工程量清单项)按
  名称+技术参数聚类归并、计算单价统计量并导出带图表的 Excel 报告时使用。每条价格可溯源到原文位置。
  触发场景:"合同价格分析""分项价格汇总""工程量清单提取""货物单价对比""采购价格统计"
  "聚类分析价格""合同金额提取"等。支持手动触发和定时增量更新。
---

# 合同分项价格分析技能(v2)

## ⛏️ 关键规则

1. 本技能通过 `scripts/cli.py` 执行数据流水线:MinIO 扫描 → eai-flow-ocr 提取表格 → 分类校验 → 聚类 → Excel → 入库。
2. **合同原文存 MinIO 独立 bucket(`cpa-contracts`),不走 RAGFlow**(v2 弃用 RAGFlow chunk 提取,因其破坏表格完整性)。
3. **表格提取由独立 OCR 服务 `eai-flow-ocr`(rapid-layout + rapid-table + rapidocr)完成,不进 gateway**。
4. **增量检测用文件 SHA-256**(`cpa_documents.file_hash`),精确比对(改名/重上传不重解析)。
5. **价格强校验**:OCR 数字粘连/量级异常标 `needs_review`,不进统计均值,需人工溯源核验后修正。
6. **每条分项带溯源坐标**(`source_page` + `source_bbox`),前端可溯源比对原文。
7. 自动聚类结果需用户在管理页面审核确认(`status=confirmed`)后统计才作为最终结论。
8. 持久化用 PostgreSQL `postgres-ext`,`cpa_` 表前缀;DB 不可达时管线仍可解析/聚类/导出(跳过持久化)。
9. 管理页面 API 已挂载到主后端 Gateway 扩展 `backend/app/extensions/contract_price/`(复用 cookie-JWT 认证 + 共享 DB 引擎),路由前缀 `/api/extensions/contract-price`。本技能 `scripts/` 仅保留流水线逻辑。

## 工作流

### 步骤1:上传合同
管理页面「合同清单」上传 PDF/DOCX(存 MinIO `cpa-contracts`),或直接投放 MinIO bucket。

### 步骤2:触发分析
管理页面「总览」点「立即分析」(后台调 cli),或直接 CLI:
```bash
cd skills/custom/contract-price-analysis
PYTHONPATH=. python -m scripts.cli --trigger manual
```

### 步骤3:报告结果
向用户报告:处理合同数、提取分项数、货物表数、聚类组数、待核验(needs_review)数、Excel 文件路径。

## 增量机制
`document_scanner.scan_changed` 对比 MinIO 对象 SHA-256 与 `cpa_documents.file_hash`,只重新处理新增/内容变更的合同,避免全量重算。

## 表格提取(v2 核心)
- **eai-flow-ocr 服务**(`mcp-server/ocr-service/`,容器 `eai-flow-ocr:8010`):`rapid-layout` 版面分析(区分 table/text 区域,排除多栏正文误检)+ `rapid-table` 结构识别 + `rapidocr` 文字识别。
- **输出**:每张表行列结构 + 每单元格文字 + bbox(归一化 0~1,溯源用)+ 置信度 + 页预渲染 PNG。
- **Phase 0 验证**:137 页真实盖章合同识别完整"工程量清单计价表"(11列:序号/项目名称/单位/工程量/不含税单价/合价/税率/税金/含税单价/合价)。

## 价格校验(needs_review)
扫描件 OCR 价格数字易错(粘连/量级)。`price_validator`:
- 数字粘连("824.79 1.20" 工程量+单价粘连)→ needs_review
- 量级异常(<0.01)/ 偏离同列中位(>10x)→ needs_review
- needs_review 项不进统计均值,进审核队列,人工溯源核验后修正。

## 溯源比对
每条分项带 `source_page` + `source_bbox`(归一化坐标)。前端 TracebackDrawer:点击 → 拉预渲染 PNG + bbox 红框叠加,人工对照原文核验价格。

## 聚类说明
- **特征**:货物名称的 char-ngram TF-IDF 向量 ⊕ 技术参数标准化数值向量。
- **算法**:DBSCAN(cosine 距离,eps=0.6,min_samples=2),无需预设簇数,离群点标为 -1。
- **为什么含技术参数**:同名不同规格(如 10kV vs 35kV)价格差异巨大,仅按名称聚类会让均值失真。

## Excel 产出(6 个 Sheet)
1. 汇总总表(类别/均值/最大/最小/中位数/标准差/异常值数)
2. 分项明细(needs_review 单价显示"待核验")
3. 图表-价格分布 4. 图表-价格趋势 5. 图表-供应商对比 6. 图表-区间分布

## 环境依赖
- 环境变量:`OCR_SERVICE_URL`(默认 http://eai-flow-ocr:8010)、`CPA_MINIO_ENDPOINT`(默认 ragflow-minio:9000)、`CPA_MINIO_ACCESS_KEY`/`SECRET_KEY`/`BUCKET`(默认 cpa-contracts)、`CPA_DATABASE_URL`、`CPA_OUTPUT_DIR`
- Python 包:见 `requirements.txt`(httpx、minio、numpy、xlsxwriter、sqlalchemy[asyncio]、asyncpg)
- 服务:eai-flow-ocr 容器(docker-compose `ocr` service)+ ragflow-minio(MinIO)+ postgres-ext(PostgreSQL)

## 参考文档
- 设计文档:`docs/superpowers/specs/2026-06-26-contract-price-analysis-design-v2.md`(supersedes v1)
