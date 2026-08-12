---
name: spare-parts-analysis
description: |
  当用户需要查询/分析已入库的备品备件价格时使用:按备件名查含税单价统计(均值/中位/区间)、
  **跨客户比价**(同一备件在不同客户/采购方的价格差异)、列出异常高价项、查某客户的备件合同明细。
  **只读分析技能,不触发任何流水线/OCR 执行**。触发场景:"X备件的单价是多少""同一备件各客户
  报价对比""哪些备件价格异常""某客户的备件采购""备件均价统计"等。
---

# 备品备件价格体系分析技能(只读查询)

## ⛏️ 关键规则(必须遵守)

1. **本技能只读不写**:仅通过 `scripts/query.py` 从已入库的 `csp_` 表查询分析,**绝不触发 OCR / 流水线 / 重解析**。
2. **流水线执行不在本技能职责内**:备件合同 OCR 提取、聚类、重解析等**重计算/重 IO 操作**,统一由「备件价格分析」**管理模块**(`/spare-parts` 页面)触发。原因:
   - OCR 结果**需人工溯源校验**(数字粘连/量级异常标 needs_review),对话页面无法做这个工作;
   - 流水线可能涉及**上千份合同文档**,普通用户在对话里随意触发会**严重影响系统性能**。
   - 若用户要求"重新提取/重跑/上传合同分析",**明确告知**:请到管理页面「备件价格分析」操作,本技能只能查已入库数据。
3. **价格统计规则**:只用 `validation_status IN (ok, corrected)` 的 `unit_price` 算均值/区间(待核验 needs_review 项不入统计,与聚类统计同规则)。
4. **数据可信度提示**:回答价格时,附上样本数(基于多少条已校验数据);若该备件多为 needs_review,明确提示"数据待人工核验,仅供参考"。
5. 每条分项带溯源坐标(`source_page` + `source_bbox`),管理页面可溯源比对原文;对话里只报数字结论。
6. 自动聚类结果(备件名归一)需在管理页面审核确认后统计才作为最终结论;查询时若命中 pending 聚类,提示"该备件分组尚未人工确认"。
7. **客户维度(D3)**:OCR 抽出的脏客户名经 `csp_customers` 别名表归一为 customer_id。若查询的客户名未命中主数据(status=pending,待认领),提示"该客户尚未认领归一,数据可能不完整"。

## 数据来源(背景,无需用户关心)

- 备件合同扫描件由管理模块上传到 MinIO `csp-parts` bucket,经独立 OCR 服务(`eai-flow-ocr`)提取表格(rapid-layout + rapid-table + rapidocr),分类校验后入库。
- 增量检测用文件 SHA-256(`csp_documents.file_hash`),改名/重上传不重解析。
- 持久化用 PostgreSQL `postgres-ext`,`csp_` 表前缀(`csp_documents` / `csp_items` / `csp_clusters` / `csp_customers` / `csp_run_history`)。
- **客户归一**:OCR 脏客户名 → `csp_customers.canonical_name`/`aliases` 匹配 → customer_id;未命中建 pending 客户,管理页面认领/合并。
- **备件名归一**:OCR 脏备件名 → 聚类引擎(`clustering/engine`)→ cluster_id,cluster_id 是跨客户比价的连接键。
- 管理模块 API 挂载在 Gateway 扩展 `backend/app/extensions/spare_parts/`,路由前缀 `/api/extensions/spare-parts`。

## 工作流(查询已处理数据)

### 步骤1:判断能回答
本技能只能回答**已入库数据**范围内的查询。若用户问的备件/合同从未经管理模块处理过(工具查不到),如实告知"未找到该备件的价格数据,请先在备件价格分析管理页面上传并分析相关合同"——**不要尝试触发流水线,也不要退化成网搜**。

### 步骤2:调用 MCP 工具查询(直接函数调用,无需 bash)
本技能通过 MCP 服务器 `spare-parts-analysis` 暴露**只读查询工具**,直接调用即可(不要去找 bash / sandbox / CLI 脚本):

| 工具 | 用途 |
|------|------|
| `spare_part_summary()` | 数据总览:合同数/备件数/聚类数/客户数/待核验数/价格区间与均值 |
| `query_part_price(part_name)` | **核心**:按备件名模糊查含税单价统计(均值/中位/区间/校验状态/异常/来源合同/样本)。用户问"X 的单价/均价"→ 调它 |
| `compare_part_price_by_customer(part_name)` | **④ 特色**:同一备件在**不同客户/采购方**的价格对比(各客户均价 + 偏离标记)。用户问"同一备件各客户报价/谁买贵了"→ 调它 |
| `list_part_price_outliers()` | 异常高价备件分项(IQR 离群) |
| `customer_parts_contracts(customer_name)` | 某客户的备件采购明细 + 来源合同清单 |

工具返回 JSON,把其中价格统计原样转述给用户即可。统计只用已校验数据(ok/corrected),待核验项不入均值。跨客户比价时,各客户分别统计再对比。

### 步骤3:报告 + 可信度
- 报告价格时附样本数(基于 N 条已校验数据)。
- 若返回 `confidence_note: 价格待人工溯源核验,仅供参考` 或多数为 needs_review,明确提示用户。
- 跨客户对比时,注明各数据来自哪个客户(`customer_name`)和合同号(`source_contract_no`);若某客户是 pending(未认领),注明"该客户名尚未归一,可能含重复/别名"。

### 步骤4(仅诊断用):若 MCP 工具不可用
若工具未注册/报错,可在 gateway 容器内用 CLI 诊断数据是否就绪(**仅诊断,非对话常规路径**):
```bash
cd /app/backend && PYTHONPATH=/app/skills/public/spare-parts-analysis uv run python -m scripts.query --part <名称>
```
不要在对话里向用户暴露此命令;数据就绪后告知用户"工具已恢复"。

## 边界:这些不做(转交管理模块)
| 用户请求 | 本技能回应 |
|----------|-----------|
| 上传/分析新备件合同 | 请到管理页面「备件价格分析」上传 |
| 重新 OCR / 重跑流水线 | 请到管理页面「总览」点立即分析(或单文档重解析) |
| 修正某条价格 | 请到管理页面「分项明细」修正(支持溯源核验) |
| 审核/合并/拒绝聚类 | 请到管理页面「聚类审核」操作 |
| 认领/合并客户(pending 客户) | 请到管理页面「客户管理」认领归一 |

## 环境依赖
- 环境变量:`CSP_DATABASE_URL`(查 csp_ 表用)、`CSP_MINIO_ENDPOINT`(默认 ragflow-minio:9000);MCP 子进程用 `CSP_QUERY_DB_URL`(stdio env 白名单,bug-1162)。
- Python 包:见 `requirements.txt`(sqlalchemy[asyncio]、asyncpg、numpy)。
- 仅查询,不依赖 OCR 服务运行状态。

## 参考文档
- 工程计划:`docs/superpowers/specs/2026-08-13-spare-parts-eng-plan.md`
