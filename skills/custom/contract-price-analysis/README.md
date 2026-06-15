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

这是 Plan 1/3（数据流水线）。Plan 2 将增加管理页面 API 服务，Plan 3 增加前端管理页面。
