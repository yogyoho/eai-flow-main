---
name: contract-price-analysis
description: |
  当用户需要查询/分析已入库的合同分项货物或服务的价格时使用:按货物名称查含税单价统计(均值/中位/区间)、
  列出异常高价项、待核验项、按聚类查看明细、跨合同价格对比。**只读分析技能,不触发任何流水线/OCR 执行**。
  触发场景:"X货物的单价是多少""分项价格对比""哪些货物价格异常""采购均价统计""合同金额查询"等。
---

# 合同分项价格分析技能(只读查询 v2)

## ⛏️ 关键规则(必须遵守)

1. **本技能只读不写**:仅通过 `scripts/query.py` 从已入库的 `cpa_` 表查询分析,**绝不触发 OCR / 流水线 / 重解析**。
2. **流水线执行不在本技能职责内**:合同 OCR 提取、聚类、Excel 导出、重解析等**重计算/重 IO 操作**,统一由「合同价格分析」**管理模块**(`/contract-price` 页面)触发。原因:
   - OCR 结果**需人工溯源校验**(数字粘连/量级异常标 needs_review),对话页面无法做这个工作;
   - 流水线可能涉及**上千份合同文档**,普通用户在对话里随意触发会**严重影响系统性能**。
   - 若用户要求"重新提取/重跑/上传合同分析",**明确告知**:请到管理页面「合同价格分析」操作,本技能只能查已入库数据。
3. **价格统计规则**:只用 `validation_status IN (ok, corrected)` 的 `unit_price` 算均值/区间(待核验 needs_review 项不入统计,与聚类统计同规则)。
4. **数据可信度提示**:回答价格时,附上样本数(基于多少条已校验数据);若该货物多为 needs_review,明确提示"数据待人工核验,仅供参考"。
5. 每条分项带溯源坐标(`source_page` + `source_bbox`),管理页面可溯源比对原文;对话里只报数字结论。
6. 自动聚类结果需在管理页面审核确认(`status=confirmed`)后统计才作为最终结论;查询时若命中 pending 聚类,提示"该组尚未人工确认"。

## 数据来源(背景,无需用户关心)

- 合同扫描件由管理模块上传到 MinIO `cpa-contracts` bucket,经独立 OCR 服务(`eai-flow-ocr`)提取表格(rapid-layout + rapid-table + rapidocr),分类校验后入库。
- 增量检测用文件 SHA-256(`cpa_documents.file_hash`),改名/重上传不重解析。
- 持久化用 PostgreSQL `postgres-ext`,`cpa_` 表前缀(`cpa_documents` / `cpa_items` / `cpa_clusters`)。
- 管理模块 API 挂载在 Gateway 扩展 `backend/app/extensions/contract_price/`,路由前缀 `/api/extensions/contract-price`。

## 工作流(查询已处理数据)

### 步骤1:判断能回答
本技能只能回答**已入库数据**范围内的查询。若用户问的货物/合同从未经管理模块处理过(query 查不到),如实告知"未找到该货物的价格数据,请先在合同价格分析管理页面上传并分析相关合同"——**不要尝试触发流水线**。

### 步骤2:用 query.py 查询(秒级,只读)
```bash
cd skills/custom/contract-price-analysis
PYTHONPATH=. python -m scripts.query --goods 多孔砖墙        # 指定货物的含税单价统计(均值/中位/区间/异常/校验状态/来源合同)
PYTHONPATH=. python -m scripts.query --goods 电缆 --summary   # 查货物 + 附数据总览
PYTHONPATH=. python -m scripts.query --outliers              # 异常高价分项
PYTHONPATH=. python -m scripts.query --needs-review          # 待核验分项(OCR 不确定)
PYTHONPATH=. python -m scripts.query --cluster <uuid>        # 某聚类的明细 + 统计
PYTHONPATH=. python -m scripts.query                         # 不带参数 = 数据总览
```
把脚本输出原样转述给用户即可。DB 不可达时脚本会明确报错(不会编造数据)。

### 步骤3:报告 + 可信度
- 报告价格时附样本数(基于 N 条已校验数据)。
- 若全部/多数为 needs_review,提示"价格待人工溯源核验,仅供参考"。
- 跨合同对比时,注明各数据来自哪个合同号(`source_contract_no`)。

## 边界:这些不做(转交管理模块)
| 用户请求 | 本技能回应 |
|----------|-----------|
| 上传/分析新合同 | 请到管理页面「合同价格分析」上传 |
| 重新 OCR / 重跑流水线 | 请到管理页面「总览」点立即分析(或单文档重解析) |
| 修正某条价格 | 请到管理页面「分项明细」修正(支持溯源核验) |
| 审核/合并/拒绝聚类 | 请到管理页面「聚类审核」操作 |
| 导出 Excel | 请到管理页面「任务历史」下载 |

## 环境依赖
- 环境变量:`CPA_DATABASE_URL`(查 cpa_ 表用)、`CPA_MINIO_ENDPOINT`(默认 ragflow-minio:9000)。
- Python 包:见 `requirements.txt`(sqlalchemy[asyncio]、asyncpg、numpy)。
- 仅查询,不依赖 OCR 服务运行状态。

## 参考文档
- 设计文档:`docs/superpowers/specs/2026-06-26-contract-price-analysis-design-v2.md`
- 前端对齐重构:`docs/superpowers/specs/2026-06-30-contract-price-frontend-backend-alignment.md`
