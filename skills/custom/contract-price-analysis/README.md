# 合同分项价格分析技能

从 RAGFlow 合同知识库提取分项价格，按货物名称+技术参数聚类归并，计算单价统计量（均值/最大/最小/中位数/标准差/异常值），导出带图表的 Excel 报告。

## 快速开始

```bash
cd skills/custom/contract-price-analysis
pip install -r requirements.txt
export RAGFLOW_API_KEY=<your-key>
PYTHONPATH=. python -m scripts.cli --mode table --trigger manual
```

Excel 输出到 `CPA_OUTPUT_DIR`（默认 `/mnt/user-data/outputs/contract-price/`）。

## 测试

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

> 数据库往返测试（`test_db_models.py::test_insert_document_and_item`）需要可达的 `postgres-ext`，在 Docker 外自动跳过；容器内运行时启用。

## 流水线阶段

1. **拉取增量** — RAGFlow API + `doc_hash` 比对，只处理新增/变更合同
2. **解析分项** — `table` / `list` / `mixed` 三模式
3. **向量化** — 名称 char-ngram TF-IDF ⊕ 技术参数标准化
4. **聚类** — DBSCAN（cosine，eps=0.6，min_samples=2），离群价格标噪声
5. **统计** — 均值/最大/最小/中位数/标准差 + IQR 异常值检测
6. **导出** — 6-Sheet Excel（汇总表、分项明细、4 类图表）

## 模块结构

| 文件 | 职责 |
|------|------|
| `scripts/config.py` | 从环境变量加载配置 |
| `scripts/models.py` | `cpa_` 表 ORM 模型 |
| `scripts/db.py` | 异步 DB 引擎 + 会话工厂 |
| `scripts/ragflow_client.py` | RAGFlow API 客户端 + 增量比对 |
| `scripts/parser/` | 表格/清单/混合解析器 |
| `scripts/clustering/vectorizer.py` | 文本+参数向量化 |
| `scripts/clustering/engine.py` | DBSCAN 聚类 |
| `scripts/stats.py` | 价格统计 + IQR 异常值 |
| `scripts/excel_generator.py` | 6-Sheet Excel + 图表 |
| `scripts/cli.py` | 端到端流水线入口 |

## 架构

见 `docs/superpowers/specs/2026-06-15-contract-price-analysis-design.md`。

- **Plan 1/3（本技能 scripts/）**：数据流水线（RAGFlow → 解析 → 聚类 → 统计 → Excel），可独立运行。
- **Plan 2/3（后端扩展）**：管理页面 API 挂载在 `backend/app/extensions/contract_price/`，路由前缀 `/api/extensions/contract-price`，复用主后端 cookie-JWT 认证与共享 `postgres-ext` 引擎。流水线触发端点（`POST /pipeline/run`）以子进程方式调用本技能 CLI。
- **Plan 3/3（前端）**：主前端 `/contract-price` 路由的 6 个管理页面（待实现）。

### 管理页面 API 端点（Plan 2）

| 功能区 | 端点 |
|--------|------|
| 1 合同清单 | `GET/DELETE /api/extensions/contract-price/documents` |
| 2 聚类审核 | `GET /clusters`、`GET /clusters/{id}`、`POST /clusters/{id}/confirm`、`POST /clusters/merge`、`POST /items/{id}/move` |
| 3 分项明细 | `GET /items`、`PATCH /items/{id}` |
| 4 任务历史 | `GET /runs`、`GET /runs/{id}/excel` |
| 5 配置 | `GET/PUT /config` |
| 6 看板 | `GET /dashboard` |
| 流水线 | `POST /pipeline/run`、`GET /pipeline/runs/{id}/status` |

部署：修改扩展后重启 gateway（`docker compose -p eai-docker restart gateway`），`cpa_` 表随共享 Base 在启动时自动创建。
