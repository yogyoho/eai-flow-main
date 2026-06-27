# 合同分项价格分析技能(v2)

从合同扫描件提取分项价格(工程量清单计价表),按货物名称+技术参数聚类归并,计算单价统计量(均值/最大/最小/中位数/标准差),标记异常价格,导出带图表的 Excel。每条价格可溯源到原文位置。

> **v2 弃用 RAGFlow**(其 chunk 机制破坏表格完整性),改用独立 OCR 服务 + MinIO 存储。

## 快速开始

```bash
# 1. 启动 OCR 服务(独立容器,不进 gateway)
docker compose -p eai-docker -f docker/docker-compose-dev.yaml up -d --build ocr

# 2. 上传合同到 MinIO(管理页面「合同清单」上传,或投放 cpa-contracts bucket)

# 3. 触发分析
cd skills/custom/contract-price-analysis
PYTHONPATH=. python -m scripts.cli --trigger manual
```

Excel 输出到 `CPA_OUTPUT_DIR`(默认 `/mnt/user-data/outputs/contract-price/`)。

## 架构(v2:MinIO + OCR 服务 + 溯源)

```
合同(MinIO cpa-contracts)
  → eai-flow-ocr(rapid-layout 版面分析 + rapid-table 结构 + rapidocr 文字)
  → table_classifier(只取货物分项表,排除付款/验收表)
  → price_validator(数字粘连/量级异常 → needs_review)
  → DBSCAN 聚类 → 统计 + IQR 异常值
  → 6-Sheet Excel + 入库(带溯源坐标 source_page/bbox)
```

## 流水线阶段

1. **扫描增量** — MinIO `list_objects` + SHA-256 比对,只处理新增/内容变更合同
2. **OCR 提取** — eai-flow-ocr 服务:版面分析(区分表格/正文)+ 表格结构 + 文字 + bbox + 预渲染 PNG
3. **分类** — 表头打分判定,只取货物分项表(排除付款计划/验收标准表)
4. **校验** — 价格数字粘连/量级异常 → `needs_review`(不进统计均值)
5. **聚类** — DBSCAN(cosine,eps=0.6,min_samples=2),离群价格标噪声
6. **统计** — 均值/最大/最小/中位数/标准差 + IQR 异常值
7. **导出** — 6-Sheet Excel(needs_review 显示"待核验")+ 入库(带溯源坐标)

## 模块结构

| 文件 | 职责 |
|------|------|
| `scripts/config.py` | 环境变量配置(OCR_SERVICE_URL + CPA_MINIO_* + DB) |
| `scripts/storage.py` | MinIO ContractStore(独立 cpa-contracts bucket + 预览图) |
| `scripts/document_scanner.py` | MinIO 扫描 + SHA-256 精确增量 |
| `scripts/document_parser.py` | HTTP 调 eai-flow-ocr → TableExtract |
| `scripts/table_classifier.py` | 表头打分(货物/付款/验收/未分类)+ 多行表头规范化 + 列角色映射 |
| `scripts/price_validator.py` | 价格强校验(粘连/量级 → needs_review) |
| `scripts/clustering/` | DBSCAN 聚类(vectorizer + engine) |
| `scripts/stats.py` | 价格统计 + IQR 异常值 |
| `scripts/excel_generator.py` | 6-Sheet Excel + 图表 |
| `scripts/cli.py` | 端到端流水线入口 |

## 环境依赖

- **服务**:eai-flow-ocr(docker-compose `ocr` service,端口 8010)+ ragflow-minio(MinIO)+ postgres-ext(PostgreSQL)
- **环境变量**:`OCR_SERVICE_URL`、`CPA_MINIO_ENDPOINT`/`ACCESS_KEY`/`SECRET_KEY`/`BUCKET`、`CPA_DATABASE_URL`、`CPA_OUTPUT_DIR`
- **Python 包**:见 `requirements.txt`

## 设计文档

`docs/superpowers/specs/2026-06-26-contract-price-analysis-design-v2.md`(supersedes v1 `2026-06-15-contract-price-analysis-design.md`)。

## 测试

```bash
cd skills/custom/contract-price-analysis
PYTHONPATH=. python -m pytest tests/ -v
```

> 注:v2 改造后部分测试待更新(`test_cli`/`test_config`/`test_db_models` 对应新模块);`test_ragflow_client`/`test_parser` 已删(对应模块 v2 已移除)。数据库往返测试(`test_db_models`)需可达的 `postgres-ext`,Docker 外自动跳过。

## 管理页面 API(后端扩展)

挂在 `backend/app/extensions/contract_price/`,路由前缀 `/api/extensions/contract-price`,复用主后端 cookie-JWT 认证与共享 `postgres-ext` 引擎。流水线触发端点(`POST /pipeline/run`)以子进程方式调用本技能 CLI。

| 功能区 | 端点 |
|--------|------|
| 文档管理 | `POST /documents/upload`、`GET/DELETE /documents`、`GET /documents/{id}/preview/{page}` |
| 聚类审核 | `GET /clusters`、`GET /clusters/{id}`、`POST /clusters/{id}/confirm`、`POST /clusters/merge`、`POST /items/{id}/move` |
| 分项明细 | `GET /items`、`PATCH /items/{id}` |
| 任务历史 | `GET /runs`、`GET /runs/{id}/excel` |
| 配置/看板 | `GET/PUT /config`、`GET /dashboard` |
| 流水线 | `POST /pipeline/run`、`GET /pipeline/runs/{id}/status` |

部署:修改扩展后重启 gateway(`docker compose -p eai-docker restart gateway`),`cpa_` 表随共享 Base 在启动时自动创建。
