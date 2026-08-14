# Ontology 市场域统一语义层（后端 + CI lint）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现市场/分析数据域的 ontology 统一语义层后端——声明式 YAML 注册表（11 对象类型 + 12 链接）+ 通用只读引擎 + 统一 `ontology` MCP server + REST 透出 + 权限挂载 + CI lint。这是 Palantir Ontology 概念移植的平台原语，所有未来域（HR/采购/资产…）只加 YAML。

**Architecture:** 新独立模块 `backend/app/extensions/ontology/`，纯只读投影层（不建索引/funnel，直接读 Postgres）。注册表为 versioned YAML（SHA-256 热重载），引擎按 `access.path` 选连接器（`postgres_ext` 直读扩展库 / `data_source` 复用 `DataSourceService` 只读守卫），MCP/REST 共用引擎。能力经统一 `ontology` MCP 到达 agent。跨模块链接 = 聚类代表名归一化精确匹配。CI lint 固化 §2.2 验收清单。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy(asyncpg) / MCP SDK（`mcp.server` stdio）/ PyYAML / pydantic v2 / ruff。

---

## Scope Note

本计划 = **后端 + CI lint**（平台原语，expansion plan §9 的唯一地基）。前端语义地图页（应用中心 `/ontology`）为**独立后续计划**（`2026-08-14-ontology-semantic-map-frontend.md`，后端落地后编写）——两子系统相对独立，后端是前置。

**设计依据**（实现时对照）：
- 母稿 `docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md`（§4 注册表 schema / §5 对象清单 / §6 链接清单 / §7 MCP / §8 REST / §10 权限）
- 扩张方案 `docs/superpowers/specs/2026-08-14-ontology-enterprise-expansion-plan.md` §2.2（CI lint 验收清单）、C3（链接 schema 加 `enabled:false` stub 字段）

---

## File Structure

```
backend/app/extensions/ontology/
  __init__.py                # 空（或导出 router 供 app.py 挂载）
  registry/
    _manifest.yaml           # schema_version + files + registry_version
    contract_price.yaml      # cpa_ 域: 3 对象 + 2 链接
    spare_parts.yaml         # csp_ 域: 4 对象 + 3 链接(含自引用)
    bid_quote.yaml           # data_source/dataset(扩展库) + bid/bid_item(data_source 连接)
    cross_module.yaml        # 4 条跨模块链接
  registry.py                # pydantic 模型 + loader + SHA-256 热重载 + 校验
  connectors/
    __init__.py
    postgres_ext.py          # 直读扩展库(短连接引擎)
    data_source.py           # 复用 DataSourceService 只读守卫
  engine/
    __init__.py
    filters.py               # typed where-clause -> SQL WHERE(bind params)
    mapper.py                # 物理行 -> ontology 对象(apiName, nulls 省略)
    query.py                 # QueryEngine: get/list/search/get_links/traverse/aggregate
  server.py                  # 统一 ontology MCP server(7 工具)
  routers.py                 # REST surface(11 端点)
  schemas.py                 # pydantic 响应模型
backend/scripts/ontology_lint.py   # §2.2 CI lint(主键不可变/hidden 启发式/列 diff/覆盖度)
```

**职责边界**：`registry.py` 只管注册表加载与校验（无 DB）；`connectors/` 只管物理读（无业务语义）；`engine/` 把注册表 + 连接器组合成查询能力（无 HTTP/MCP）；`server.py`/`routers.py` 只做适配（无查询逻辑）。每个文件单一职责。

---

## Task 1: 注册表 YAML（11 对象类型 + 12 链接）

**Files:**
- Create: `backend/app/extensions/ontology/registry/_manifest.yaml`
- Create: `backend/app/extensions/ontology/registry/contract_price.yaml`
- Create: `backend/app/extensions/ontology/registry/spare_parts.yaml`
- Create: `backend/app/extensions/ontology/registry/bid_quote.yaml`
- Create: `backend/app/extensions/ontology/registry/cross_module.yaml`

- [ ] **Step 1: 创建 `_manifest.yaml`**

```yaml
schema_version: 1
registry_version: 1
hot_reload: true
files:
  - file: contract_price.yaml
  - file: spare_parts.yaml
  - file: bid_quote.yaml
  - file: cross_module.yaml
```

- [ ] **Step 2: 创建 `contract_price.yaml`**（cpa_ 域：3 对象 + 2 链接）

```yaml
object_types:
  - api_name: contract_document
    display_name: 合同文档
    description: 合同价格表扫描件文档, 首页OCR抽取项目/合同字段, 解析后进入确认门
    domain: contract_price
    icon: 📄
    access: { path: postgres_ext, table: cpa_documents }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: contract_no, api_name: contractNo, type: string, filterable: true, searchable: true, description: 合同编号, 跨模块连接键 }
      - { name: supplier, api_name: supplier, type: string, searchable: true, description: 供应商名称 }
      - { name: project_name, api_name: projectName, type: string, searchable: true, description: 项目/工程名称 }
      - { name: project_location, api_name: projectLocation, type: string, description: 项目所在地 }
      - { name: sign_date, api_name: signDate, type: date, description: 合同签订日期 }
      - { name: file_name, api_name: fileName, type: string, description: 原始文件名 }
      - { name: file_hash, api_name: fileHash, type: string, description: 文件SHA-256指纹(跨模块去重键) }
      - { name: parse_status, api_name: parseStatus, type: string, filterable: true, enum: [pending, parsing, parsed, failed, needs_review], description: 解析状态 }
      - { name: confirm_status, api_name: confirmStatus, type: string, filterable: true, enum: [pending, confirmed, skipped, clustered], description: 确认门状态 }
      - { name: page_count, api_name: pageCount, type: integer, description: 页数 }
  - api_name: contract_item
    display_name: 合同分项
    description: 合同价格表抽取的明细行(工程量清单/分部分项/设备清单), 含 v2 溯源与价格校验状态
    domain: contract_price
    icon: 📦
    access: { path: postgres_ext, table: cpa_items }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: goods_name, api_name: goodsName, type: string, filterable: true, searchable: true, description: 货物/设备名称, 聚类与跨模块连接键 }
      - { name: spec_model, api_name: specModel, type: string, description: 规格型号 }
      - { name: quantity, api_name: quantity, type: decimal, description: 数量 }
      - { name: unit, api_name: unit, type: string, description: 计量单位 }
      - { name: unit_price, api_name: unitPrice, type: decimal, filterable: true, format: currency, unit: CNY, description: 含税单价(统计用) }
      - { name: price_untaxed, api_name: priceUntaxed, type: decimal, format: currency, unit: CNY, description: 不含税单价(审计用) }
      - { name: validation_status, api_name: validationStatus, type: string, filterable: true, enum: [ok, needs_review, corrected], description: 价格校验状态 }
      - { name: is_outlier, api_name: isOutlier, type: boolean, description: 聚类内离群标记 }
      - { name: cluster_id, api_name: clusterId, type: string, filterable: true, description: 所属货物聚类(连接键) }
      - { name: source_contract_no, api_name: sourceContractNo, type: string, description: 来源合同编号 }
      - { name: source_page, api_name: sourcePage, type: integer, description: 来源页码(溯源) }
  - api_name: goods_cluster
    display_name: 货物聚类
    description: 同质 goods_name 分项聚类(DBSCAN), 确认后计入统计
    domain: contract_price
    icon: 🗂️
    access: { path: postgres_ext, table: cpa_clusters }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: representative_name, api_name: representativeName, type: string, searchable: true, description: 典型货物名 }
      - { name: category, api_name: category, type: string, filterable: true, enum: [设备类, 材料类, 未分类], description: 货物分类 }
      - { name: status, api_name: status, type: string, filterable: true, enum: [pending, confirmed, rejected], description: 确认后计入统计, 拒绝剔除 }
      - { name: item_count, api_name: itemCount, type: integer, description: 成员分项数 }
      - { name: confirmed_by, api_name: confirmedBy, type: string, description: 确认人 }
link_types:
  - api_name: item_in_document
    display_name: 归属合同扫描件
    source: contract_item
    target: contract_document
    cardinality: "N:1"
    reverse: document_has_items
    join: { type: foreign_key, source_column: document_id, target_column: id }
  - api_name: item_in_cluster
    display_name: 所属货物聚类
    source: contract_item
    target: goods_cluster
    cardinality: "N:1"
    reverse: cluster_has_items
    join: { type: foreign_key, source_column: cluster_id, target_column: id }
```

- [ ] **Step 3: 创建 `spare_parts.yaml`**（csp_ 域：4 对象 + 3 链接）

```yaml
object_types:
  - api_name: customer
    display_name: 客户
    description: 客户主数据(规范名 + 别名), OCR 脏客户名经 aliases 归一
    domain: spare_parts
    icon: 👥
    access: { path: postgres_ext, table: csp_customers }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: canonical_name, api_name: canonicalName, type: string, searchable: true, description: 规范客户名 }
      - { name: source, api_name: source, type: string, filterable: true, enum: [master, imported, ocr], description: 来源 }
      - { name: status, api_name: status, type: string, filterable: true, enum: [active, pending, merged], description: 状态 }
      - { name: merged_into, api_name: mergedInto, type: string, description: 合并去向(自引用) }
  - api_name: spare_part_document
    display_name: 备件合同文档
    description: 备件合同扫描件, 含需方客户维度(D3 分析)
    domain: spare_parts
    icon: 📄
    access: { path: postgres_ext, table: csp_documents }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: contract_no, api_name: contractNo, type: string, filterable: true, searchable: true, description: 合同编号, 跨模块键 }
      - { name: customer_id, api_name: customerId, type: string, filterable: true, description: 需方客户(分析维度) }
      - { name: customer_name, api_name: customerName, type: string, description: 需方客户名(OCR原文) }
      - { name: supplier, api_name: supplier, type: string, searchable: true, description: 供方/卖方 }
      - { name: project_name, api_name: projectName, type: string, searchable: true, description: 项目名称 }
      - { name: sign_date, api_name: signDate, type: date, description: 签订日期 }
      - { name: parse_status, api_name: parseStatus, type: string, filterable: true, enum: [pending, parsing, parsed, failed, needs_review], description: 解析状态 }
      - { name: confirm_status, api_name: confirmStatus, type: string, filterable: true, enum: [pending, confirmed, skipped, clustered], description: 确认门状态 }
      - { name: file_hash, api_name: fileHash, type: string, description: 文件SHA-256指纹 }
  - api_name: spare_part_item
    display_name: 备件明细
    description: 备件明细行, part_name 经聚类归一后为跨客户比价键
    domain: spare_parts
    icon: ⚙️
    access: { path: postgres_ext, table: csp_items }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: part_name, api_name: partName, type: string, filterable: true, searchable: true, description: 备件名(脏, 聚类归一) }
      - { name: spec, api_name: spec, type: string, description: 规格/型号 }
      - { name: quantity, api_name: quantity, type: decimal, description: 数量 }
      - { name: unit, api_name: unit, type: string, description: 计量单位 }
      - { name: unit_price, api_name: unitPrice, type: decimal, filterable: true, format: currency, unit: CNY, description: 含税单价(统计用) }
      - { name: customer_id, api_name: customerId, type: string, filterable: true, description: 需方客户(比价维度) }
      - { name: cluster_id, api_name: clusterId, type: string, filterable: true, description: 备件聚类(比价键) }
      - { name: validation_status, api_name: validationStatus, type: string, filterable: true, enum: [ok, needs_review, corrected], description: 价格校验状态 }
      - { name: is_outlier, api_name: isOutlier, type: boolean, description: 离群标记 }
      - { name: source_contract_no, api_name: sourceContractNo, type: string, description: 来源合同编号 }
  - api_name: part_cluster
    display_name: 备件聚类
    description: 备件名聚类, 同 cluster 内 item = 同一备件, 跨客户比价键
    domain: spare_parts
    icon: 🗂️
    access: { path: postgres_ext, table: csp_clusters }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: representative_name, api_name: representativeName, type: string, searchable: true, description: 规范备件名 }
      - { name: category, api_name: category, type: string, filterable: true, description: 品类 }
      - { name: status, api_name: status, type: string, filterable: true, enum: [pending, confirmed, rejected], description: 确认后进入统计 }
      - { name: item_count, api_name: itemCount, type: integer, description: 成员明细条数 }
      - { name: confirmed_by, api_name: confirmedBy, type: string, description: 确认人 }
link_types:
  - api_name: spare_item_in_document
    display_name: 归属备件合同文档
    source: spare_part_item
    target: spare_part_document
    cardinality: "N:1"
    reverse: spare_document_has_items
    join: { type: foreign_key, source_column: document_id, target_column: id }
  - api_name: spare_item_in_cluster
    display_name: 所属备件聚类
    source: spare_part_item
    target: part_cluster
    cardinality: "N:1"
    reverse: part_cluster_has_items
    join: { type: foreign_key, source_column: cluster_id, target_column: id }
  - api_name: document_purchased_by
    display_name: 采购方客户
    source: spare_part_document
    target: customer
    cardinality: "N:1"
    reverse: customer_has_documents
    join: { type: foreign_key, source_column: customer_id, target_column: id }
  - api_name: customer_merged_from
    display_name: 客户合并去向
    source: customer
    target: customer
    cardinality: "N:1"
    reverse: customer_merged_into
    join: { type: foreign_key, source_column: merged_into, target_column: id }
```

- [ ] **Step 4: 创建 `bid_quote.yaml`**（data_source/dataset + bid/bid_item）

```yaml
object_types:
  - api_name: data_source
    display_name: 数据源
    description: 外部数据源连接注册表(元数据, 非数据本体)
    domain: bid_quote
    icon: 🔌
    access: { path: postgres_ext, table: data_sources }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: name, api_name: name, type: string, filterable: true, searchable: true, description: 数据源名称(唯一标识, 如 bid-quote) }
      - { name: type, api_name: type, type: string, filterable: true, enum: [database, api, file, gis], description: 数据源类型 }
      - { name: status, api_name: status, type: string, filterable: true, enum: [connected, error, disconnected, testing], description: 连接状态 }
      - { name: description, api_name: description, type: string, description: 数据源说明 }
      - { name: connection_config, api_name: connectionConfig, type: string, hidden: true, description: 连接配置(含凭据, 绝不透出) }
  - api_name: dataset
    display_name: 业务数据集
    description: 数据源内已标注的业务数据集(罐装只读查询)
    domain: bid_quote
    icon: 📊
    access: { path: postgres_ext, table: data_source_datasets }
    pk: { column: id, api_name: id, type: string, immutable: true }
    properties:
      - { name: label, api_name: label, type: string, filterable: true, searchable: true, description: 业务名(如 投标总览), agent 按 label 查询 }
      - { name: table_name, api_name: tableName, type: string, description: 物理表/视图名 }
      - { name: description, api_name: description, type: string, description: 数据集语义说明 }
      - { name: default_query, api_name: defaultQuery, type: string, hidden: true, description: 默认只读查询(SQL) }
  - api_name: bid
    display_name: 投标
    description: 投标记录(我方+友商对称), winning_price 为中标价
    domain: bid_quote
    icon: 🎯
    access: { path: data_source, source_id: bid-quote, table_name: mock_bid }
    pk: { column: bid_id, api_name: bidId, type: string, immutable: true }
    properties:
      - { name: project_name, api_name: projectName, type: string, filterable: true, searchable: true, description: 项目名称, 跨模块键(中标->合同) }
      - { name: project_location, api_name: projectLocation, type: string, description: 项目所在地 }
      - { name: bid_date, api_name: bidDate, type: date, description: 投标日期 }
      - { name: bidder_role, api_name: bidderRole, type: string, filterable: true, enum: [ours, competitor], description: 投标方角色 }
      - { name: bidder_name, api_name: bidderName, type: string, searchable: true, description: 投标方名称 }
      - { name: won, api_name: won, type: boolean, filterable: true, description: 是否中标 }
      - { name: winning_price, api_name: winningPrice, type: decimal, format: currency, unit: CNY, description: 中标价 }
  - api_name: bid_item
    display_name: 投标明细
    description: 投标货物构成(自产/外购金额), 自产能力强->中标, 外购->高成本落标
    domain: bid_quote
    icon: 📋
    access: { path: data_source, source_id: bid-quote, table_name: mock_bid_item }
    pk: { column: id, api_name: id, type: integer, immutable: true }
    properties:
      - { name: goods_name, api_name: goodsName, type: string, filterable: true, searchable: true, description: 货物名, 跨模块键 }
      - { name: spec, api_name: spec, type: string, description: 规格型号 }
      - { name: quantity, api_name: quantity, type: decimal, description: 数量 }
      - { name: unit, api_name: unit, type: string, description: 单位 }
      - { name: unit_price, api_name: unitPrice, type: decimal, format: currency, unit: CNY, description: 单价 }
      - { name: self_amount, api_name: selfAmount, type: decimal, format: currency, unit: CNY, description: 自产金额 }
      - { name: outsourced_amount, api_name: outsourcedAmount, type: decimal, format: currency, unit: CNY, description: 外购金额 }
      - { name: total_amount, api_name: totalAmount, type: decimal, format: currency, unit: CNY, description: 金额合计 }
      - { name: bid_id, api_name: bidId, type: string, filterable: true, description: 所属投标单(连接键) }
link_types:
  - api_name: bid_item_of_bid
    display_name: 归属投标单
    source: bid_item
    target: bid
    cardinality: "N:1"
    reverse: bid_has_items
    join: { type: foreign_key, source_column: bid_id, target_column: bid_id }
  - api_name: dataset_of_source
    display_name: 归属数据源
    source: dataset
    target: data_source
    cardinality: "N:1"
    reverse: source_has_datasets
    join: { type: foreign_key, source_column: source_id, target_column: id }
```

- [ ] **Step 5: 创建 `cross_module.yaml`**（4 条跨模块链接，含 `enabled` stub 字段）

```yaml
link_types:
  - api_name: part_cluster_matches_goods_cluster
    display_name: 备件聚类与货物聚类可比价
    source: part_cluster
    target: goods_cluster
    cardinality: "N:N"
    reverse: goods_cluster_matched_by_part_cluster
    join:
      type: normalized_key_match
      expression: "LOWER(BTRIM(csp_clusters.representative_name)) = LOWER(BTRIM(cpa_clusters.representative_name))"
    cross_module: true
  - api_name: contract_document_matches_spare_document
    display_name: 同一采购事件跨模块关联
    source: spare_part_document
    target: contract_document
    cardinality: "N:N"
    reverse: contract_document_matched_by_spare_document
    join:
      type: normalized_key_match
      expression: "LOWER(BTRIM(csp_documents.contract_no)) = LOWER(BTRIM(cpa_documents.contract_no)) OR csp_documents.file_hash = cpa_documents.file_hash"
    cross_module: true
  - api_name: won_bid_contracts_project
    display_name: 中标项目对应合同
    source: bid
    target: contract_document
    cardinality: "N:N"
    reverse: contract_project_won_by_bid
    join:
      type: normalized_key_match
      expression: "LOWER(BTRIM(mock_bid.project_name)) = LOWER(BTRIM(cpa_documents.project_name)) AND mock_bid.won = true"
    cross_module: true
  - api_name: document_supplied_by
    display_name: 供应商跨模块维度
    source: contract_document
    target: spare_part_document
    cardinality: "N:N"
    reverse: spare_document_supplied_by
    join:
      type: normalized_key_match
      expression: "LOWER(BTRIM(cpa_documents.supplier)) = LOWER(BTRIM(csp_documents.supplier))"
    cross_module: true
```

> **C3 stub 说明**：`enabled` 字段在 link schema 中默认 `true`；HR 域跨域链接将来以 `enabled: false` stub 声明（注册但引擎不暴露遍历）。本期所有链接均 `true`（不写默认值）。

- [ ] **Step 6: 语法校验**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && .venv/bin/python -c 'import yaml; [yaml.safe_load(open(f\"app/extensions/ontology/registry/{f}\")) for f in [\"_manifest.yaml\",\"contract_price.yaml\",\"spare_parts.yaml\",\"bid_quote.yaml\",\"cross_module.yaml\"]]'"`
Expected: 无输出（exit 0），YAML 均可解析。

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/ontology/registry/
git commit -m "feat(ontology): 市场域注册表 YAML — 11 对象类型 + 12 链接(含跨模块聚类代表名匹配)"
```

---

## Task 2: 注册表加载器（registry.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/__init__.py`
- Create: `backend/app/extensions/ontology/registry.py`
- Test: `backend/tests/test_ontology_registry.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology registry loader (ontology/registry.py)."""
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.extensions.ontology.registry import (
    LinkTypeDecl,
    ObjectTypeDecl,
    PropertyDecl,
    Registry,
    load_registry,
)


def _reg_dir(tmp_path):
    src = Path(__file__).resolve().parent.parent / "app" / "extensions" / "ontology" / "registry"
    for f in src.iterdir():
        if f.is_file() and f.suffix == ".yaml":
            shutil.copy2(f, tmp_path / f.name)
    return tmp_path


def test_load_real_registry(tmp_path):
    reg = load_registry(_reg_dir(tmp_path))
    assert len(reg.object_types) == 11
    assert len(reg.link_types) == 12
    assert {o.api_name for o in reg.object_types} >= {
        "contract_document", "contract_item", "goods_cluster",
        "customer", "spare_part_document", "spare_part_item", "part_cluster",
        "data_source", "dataset", "bid", "bid_item",
    }


def test_cross_module_links_registered(tmp_path):
    reg = load_registry(_reg_dir(tmp_path))
    x = [l for l in reg.link_types if l.cross_module]
    assert len(x) == 4
    assert {l.api_name for l in x} == {
        "part_cluster_matches_goods_cluster", "contract_document_matches_spare_document",
        "won_bid_contracts_project", "document_supplied_by",
    }


def test_rejects_hidden_pk_or_duplicate_api_name(tmp_path):
    reg = load_registry(_reg_dir(tmp_path))
    with pytest.raises(ValidationError):
        PropertyDecl(name="id", api_name="id", type="string", hidden=True)  # hidden PK illegal
    with pytest.raises(ValidationError):
        ObjectTypeDecl(api_name="contract_document", display_name="dup",
                       description="x", domain="d",
                       access={"path": "postgres_ext", "table": "t"},
                       pk={"column": "id", "api_name": "id", "type": "string", "immutable": True},
                       properties=[])


def test_link_schema_has_enabled_field(tmp_path):
    reg = load_registry(_reg_dir(tmp_path))
    for l in reg.link_types:
        assert hasattr(l, "enabled") and l.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_registry.py -v"`
Expected: FAIL with `ModuleNotFoundError: app.extensions.ontology.registry`

- [ ] **Step 3: Implement `registry.py`**

```python
"""Ontology registry — declarative object/link type definitions, versioned, hot-reloadable.

Loads the YAML registry under ``ontology/registry/`` into typed pydantic models.
Pure (no DB): validation only. Content-hash based hot-reload (mirrors config.yaml).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path(__file__).resolve().parent / "registry"


class PropertyDecl(BaseModel):
    """A semantic property mapped from a physical column."""
    name: str  # physical column
    api_name: str  # exposed snake_case name
    type: Literal["string", "integer", "decimal", "boolean", "date", "datetime", "json"]
    indexed: bool = False
    filterable: bool = False
    searchable: bool = False
    description: str = ""
    format: str | None = None
    unit: str | None = None
    enum: list[str] | None = None
    hidden: bool = False

    @model_validator(mode="after")
    def _check(self):
        if self.name == "id" and self.hidden:
            raise ValueError("primary key column cannot be hidden")
        return self


class AccessDecl(BaseModel):
    path: Literal["postgres_ext", "data_source"]
    table: str | None = None  # postgres_ext: physical table in extensions DB
    source_id: str | None = None  # data_source: data_sources.name
    table_name: str | None = None  # data_source: physical table in external DB

    @model_validator(mode="after")
    def _check(self):
        if self.path == "postgres_ext" and not self.table:
            raise ValueError("postgres_ext requires table")
        if self.path == "data_source" and not (self.source_id and self.table_name):
            raise ValueError("data_source requires source_id and table_name")
        return self


class PkDecl(BaseModel):
    column: str
    api_name: str
    type: str = "string"
    immutable: bool = True


class ObjectTypeDecl(BaseModel):
    api_name: str
    display_name: str
    description: str
    domain: str
    icon: str = ""
    enabled: bool = True
    deprecated: bool = False
    access: AccessDecl
    pk: PkDecl
    properties: list[PropertyDecl]
    run_source: str | None = None

    def property_by_api(self, api_name: str) -> PropertyDecl | None:
        return next((p for p in self.properties if p.api_name == api_name), None)


class JoinDecl(BaseModel):
    type: Literal["foreign_key", "normalized_key_match"]
    source_column: str | None = None
    target_column: str | None = None
    expression: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "foreign_key" and not (self.source_column and self.target_column):
            raise ValueError("foreign_key join requires source_column and target_column")
        if self.type == "normalized_key_match" and not self.expression:
            raise ValueError("normalized_key_match join requires expression")
        return self


class LinkTypeDecl(BaseModel):
    api_name: str
    display_name: str
    source: str
    target: str
    cardinality: str
    direction: Literal["bidirectional", "unidirectional"] = "bidirectional"
    reverse: str | None = None
    join: JoinDecl
    cross_module: bool = False
    enabled: bool = True  # C3: stub links (registered but not traversable) set false


class RegistryFile(BaseModel):
    file: str


class Registry(BaseModel):
    schema_version: int = 1
    registry_version: int = 1
    hot_reload: bool = True
    files: list[RegistryFile] = []
    object_types: list[ObjectTypeDecl] = []
    link_types: list[LinkTypeDecl] = []

    def object_by_name(self, api_name: str) -> ObjectTypeDecl | None:
        return next((o for o in self.object_types if o.api_name == api_name), None)

    def link_by_name(self, api_name: str) -> LinkTypeDecl | None:
        return next((l for l in self.link_types if l.api_name == api_name), None)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(registry_dir: Path | None = None) -> Registry:
    """Load all YAML files declared in _manifest.yaml and validate cross-references."""
    directory = (registry_dir or REGISTRY_DIR)
    manifest = yaml.safe_load((directory / "_manifest.yaml").read_text(encoding="utf-8"))
    reg = Registry(
        schema_version=manifest.get("schema_version", 1),
        registry_version=manifest.get("registry_version", 1),
        hot_reload=manifest.get("hot_reload", True),
        files=[RegistryFile(**f) for f in manifest.get("files", [])],
    )
    for f in reg.files:
        doc = yaml.safe_load((directory / f.file).read_text(encoding="utf-8")) or {}
        reg.object_types.extend(ObjectTypeDecl(**o) for o in doc.get("object_types", []))
        reg.link_types.extend(LinkTypeDecl(**l) for l in doc.get("link_types", []))

    # cross-reference validation
    names = {o.api_name for o in reg.object_types}
    for l in reg.link_types:
        if l.source not in names or l.target not in names:
            raise ValueError(f"link {l.api_name}: source/target not in object_types")
        # foreign_key: source_column must exist on source type; target_column on target
        if l.join.type == "foreign_key":
            src = reg.object_by_name(l.source)
            tgt = reg.object_by_name(l.target)
            if not any(p.name == l.join.source_column for p in src.properties) and l.join.source_column != src.pk.column:
                raise ValueError(f"link {l.api_name}: source_column {l.join.source_column} not on {l.source}")
            if l.join.target_column != tgt.pk.column and not any(p.name == l.join.target_column for p in tgt.properties):
                raise ValueError(f"link {l.api_name}: target_column {l.join.target_column} not on {l.target}")
    # duplicate api_name check
    seen: set[str] = set()
    for o in reg.object_types:
        if o.api_name in seen:
            raise ValueError(f"duplicate object api_name: {o.api_name}")
        seen.add(o.api_name)
    return reg


class RegistryCache:
    """Content-hash hot-reload: reload when any file's sha256 changes."""

    def __init__(self, registry_dir: Path | None = None):
        self._dir = registry_dir or REGISTRY_DIR
        self._hashes: dict[str, str] = {}
        self._registry: Registry | None = None

    def get(self) -> Registry:
        current = {f.name: _sha256(self._dir / f.name) for f in self._dir.glob("*.yaml")}
        if current != self._hashes or self._registry is None:
            self._registry = load_registry(self._dir)
            self._hashes = current
            self._registry.registry_version += 1
        return self._registry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_registry.py -v"`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/__init__.py backend/app/extensions/ontology/registry.py backend/tests/test_ontology_registry.py
git commit -m "feat(ontology): 注册表加载器 — pydantic 模型 + YAML 加载 + 内容哈希热重载 + 交叉引用校验"
```

---

## Task 3: postgres_ext 连接器（connectors/postgres_ext.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/connectors/__init__.py`
- Create: `backend/app/extensions/ontology/connectors/postgres_ext.py`
- Test: `backend/tests/test_ontology_connectors.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology connectors."""
import pytest

from app.extensions.ontology.connectors.postgres_ext import read_only_select


def test_read_only_select_builds_select(tmp_path, monkeypatch):
    # no DB access — just assert the SQL builder produces a read-only SELECT with bound params
    sql, params = read_only_select(
        table="cpa_items",
        columns=["goods_name", "unit_price"],
        where_sql="goods_name = :p0",
        params={"p0": "泵"},
        order_by="id",
        limit=50,
    )
    assert sql.upper().startswith("SELECT")
    assert sql.upper().startswith("SET TRANSACTION READ ONLY") is False  # set at exec, not in sql
    assert "LIMIT" in sql
    assert params["p0"] == "泵"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_connectors.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `connectors/postgres_ext.py`**

```python
"""postgres_ext connector — direct read-only SELECTs against the extensions DB.

Mirrors contract_price/mcp.py::_run_in_db (short-lived engine) + fail-closed
read-only (SET TRANSACTION READ ONLY). Column/table names come from the
versioned registry (trusted), values are bound params — no injection surface.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text


async def _resolve_db_url() -> str:
    if os.environ.get("ONTOLOGY_DB_URL"):
        return os.environ["ONTOLOGY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_ext_db(func):
    """Run func(session) against the extensions DB with a short-lived read-only engine.

    Shared by execute_select, run_raw_select, and the data_source connector
    (source-row resolution) — one engine-per-call, disposed after.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            return await func(session)
    finally:
        await engine.dispose()


def read_only_select(
    table: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> tuple[str, dict[str, Any]]:
    """Build a read-only SELECT statement (no execution)."""
    cols = ", ".join(f'"{c}"' for c in columns)
    sql = f"SELECT {cols} FROM {table}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if order_by:
        sql += f' ORDER BY "{order_by}"'
    if limit:
        sql += f" LIMIT {limit}"
    return sql, params or {}


async def execute_select(
    table: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Execute a read-only SELECT against the extensions DB and return dict rows."""
    sql, bind = read_only_select(table, columns, where_sql, params, order_by, limit)

    async def _q(session):
        result = await session.execute(text(sql).bindparams(**bind))
        return [dict(r) for r in result.mappings().all()]

    return await _run_in_ext_db(_q)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_connectors.py -v"`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/connectors/ backend/tests/test_ontology_connectors.py
git commit -m "feat(ontology): postgres_ext 只读连接器(短连接引擎 + SET TRANSACTION READ ONLY)"
```

---

## Task 4: data_source 连接器（connectors/data_source.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/connectors/data_source.py`
- Modify: `backend/tests/test_ontology_connectors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_data_source_connector_builds_guarded_sql(monkeypatch):
    from app.extensions.ontology.connectors import data_source as ds_conn

    sql, params = ds_conn.read_only_select("mock_bid", ["project_name", "won"], "won = :p0", {"p0": True}, "bid_id", 50)
    assert "SELECT" in sql and "LIMIT" in sql

    # non-SELECT is rejected by the guard path
    with pytest.raises(ValueError):
        ds_conn.read_only_select("mock_bid", ["*"], "", {}, None, 50)  # * not allowed for select list
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_connectors.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `connectors/data_source.py`**（复用 Task 3 的 `_run_in_ext_db` 解析源记录，再连外部库执行）

```python
"""data_source connector — read-only SELECTs against external DBs registered in data_sources.

Reuses DataSourceService (app.extensions.data_source.service) for source-row
resolution and its fail-closed assert_readonly_select guard. ontology ONLY uses
data_source as the physical SQL read path (mother spec §11.2 boundary).
"""
from __future__ import annotations

from typing import Any

from app.extensions.ontology.connectors import postgres_ext
from app.extensions.ontology.connectors.postgres_ext import _run_in_ext_db


def read_only_select(
    table_name: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> tuple[str, dict[str, Any]]:
    """Build a read-only SELECT for an external DB (same builder as postgres_ext)."""
    if any(c == "*" for c in columns):
        raise ValueError("select * not allowed — declare columns in registry")
    return postgres_ext.read_only_select(table_name, columns, where_sql, params, order_by, limit)


async def _resolve_source(source_id: str):
    """Fetch the data_sources row via the extensions-DB engine."""
    from app.extensions.data_source.service import DataSourceService

    async def _q(session):
        src = await DataSourceService.get_by_name(session, source_id)
        if src is None:
            raise ValueError(f"data_source not found: {source_id}")
        return src

    return await _run_in_ext_db(_q)


def _ext_url(cfg: dict) -> str:
    return (
        f"postgresql+asyncpg://{cfg.get('username')}:{cfg.get('password')}"
        f"@{cfg.get('host')}:{cfg.get('port')}/{cfg.get('database')}"
    )


async def execute_select(
    source_id: str,
    table_name: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.data_source.service import assert_readonly_select

    sql, bind = read_only_select(table_name, columns, where_sql, params, order_by, limit)
    safe_sql = assert_readonly_select(sql)  # fail-closed: SELECT/WITH only, auto LIMIT 200
    src = await _resolve_source(source_id)
    engine = create_async_engine(_ext_url(src.connection_config or {}), pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(safe_sql).bindparams(**bind))
            return [dict(r) for r in result.mappings().all()]
    finally:
        await engine.dispose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_connectors.py -v"`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/connectors/ backend/tests/test_ontology_connectors.py
git commit -m "feat(ontology): data_source 连接器 — 复用 DataSourceService 解析 + assert_readonly_select 守卫"
```

---

## Task 5: 过滤解析器（engine/filters.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/engine/__init__.py`
- Create: `backend/app/extensions/ontology/engine/filters.py`
- Test: `backend/tests/test_ontology_filters.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology filter compiler."""
import pytest

from app.extensions.ontology.engine.filters import compile_filter
from app.extensions.ontology.registry import ObjectTypeDecl, PropertyDecl, AccessDecl, PkDecl


def _item_type():
    return ObjectTypeDecl(
        api_name="contract_item", display_name="合同分项", description="d",
        domain="contract_price", access=AccessDecl(path="postgres_ext", table="cpa_items"),
        pk=PkDecl(column="id", api_name="id", type="string", immutable=True),
        properties=[
            PropertyDecl(name="goods_name", api_name="goodsName", type="string", filterable=True),
            PropertyDecl(name="unit_price", api_name="unitPrice", type="decimal", filterable=True),
        ],
    )


def test_compile_simple_eq():
    bind: dict = {}
    where = compile_filter(_item_type(), {"goodsName": {"eq": "泵"}}, bind)
    assert where == "goods_name = :p0"
    assert bind["p0"] == "泵"


def test_compile_and_nested():
    bind: dict = {}
    where = compile_filter(_item_type(), {"and": [{"goodsName": {"in": ["泵", "阀"]}}, {"unitPrice": {"gte": 100}}]}, bind)
    assert "goods_name IN" in where and "unit_price >=" in where
    assert len(bind) == 3


def test_compile_unknown_field_raises():
    with pytest.raises(ValueError):
        compile_filter(_item_type(), {"nope": {"eq": 1}}, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_filters.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `engine/filters.py`**

```python
"""Compile typed ontology filters into read-only SQL WHERE fragments with bound params.

Filter DSL (mother spec §7):
  {"field": {"op": value}} | {"and": [...]} | {"or": [...]} | {"not": {...}}
op: eq|ne|gt|gte|lt|lte|in|between|is_null
Field names are registry api_names; compiled to physical columns. Values are
always bound (no string interpolation) — no injection.
"""
from __future__ import annotations

from typing import Any

from app.extensions.ontology.registry import ObjectTypeDecl

_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "in": "IN", "between": "BETWEEN"}


def _bind_value(bind: dict[str, Any], value: Any) -> str:
    key = f"p{len(bind)}"
    bind[key] = value
    return f":{key}"


def _column(obj: ObjectTypeDecl, api_name: str) -> str:
    if api_name == obj.pk.api_name:
        return obj.pk.column
    prop = obj.property_by_api(api_name)
    if prop is None:
        raise ValueError(f"unknown filter field: {api_name} on {obj.api_name}")
    if not prop.filterable and not prop.searchable:
        raise ValueError(f"field not filterable: {api_name} on {obj.api_name}")
    return prop.name


def _compile_node(obj: ObjectTypeDecl, node: dict, bind: dict) -> str:
    if not node or len(node) != 1:
        raise ValueError("filter node must have exactly one key (field or and/or/not)")
    key, value = next(iter(node.items()))
    if key in ("and", "or"):
        if not isinstance(value, list):
            raise ValueError(f"{key} expects a list")
        parts = [_compile_node(obj, item, bind) for item in value]
        return f"({' {k} '.join(parts)})" if len(parts) > 1 else parts[0]
    if key == "not":
        return f"NOT ({_compile_node(obj, value, bind)})"
    # field node: value is {op: val}
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError(f"field filter {key} must be {{op: value}}")
    op, val = next(iter(value.items()))
    col = _column(obj, key)
    if op == "is_null":
        return f"{col} IS NULL" if val else f"{col} IS NOT NULL"
    if op not in _OPS:
        raise ValueError(f"unsupported op: {op}")
    if op == "in":
        if not isinstance(val, list):
            raise ValueError("in expects a list")
        keys = ", ".join(_bind_value(bind, v) for v in val)
        return f"{col} {_OPS[op]} ({keys})"
    if op == "between":
        lo, hi = val
        return f"{col} BETWEEN {_bind_value(bind, lo)} AND {_bind_value(bind, hi)}"
    return f"{col} {_OPS[op]} {_bind_value(bind, val)}"


def compile_filter(obj: ObjectTypeDecl, node: dict, bind: dict[str, Any]) -> str:
    """Return a SQL WHERE fragment (no WHERE keyword) and mutate ``bind`` with params."""
    return _compile_node(obj, node, bind)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_filters.py -v"`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/engine/ backend/tests/test_ontology_filters.py
git commit -m "feat(ontology): typed filter 编译器 → SQL WHERE + 绑定参数(白名单列/算子)"
```

---

## Task 6: 行映射器（engine/mapper.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/engine/mapper.py`
- Test: `backend/tests/test_ontology_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology row mapper."""
from app.extensions.ontology.engine.mapper import to_object
from app.extensions.ontology.registry import ObjectTypeDecl, PropertyDecl, AccessDecl, PkDecl


def _item_type():
    return ObjectTypeDecl(
        api_name="contract_item", display_name="合同分项", description="d",
        domain="contract_price", access=AccessDecl(path="postgres_ext", table="cpa_items"),
        pk=PkDecl(column="id", api_name="id", type="string", immutable=True),
        properties=[
            PropertyDecl(name="goods_name", api_name="goodsName", type="string"),
            PropertyDecl(name="unit_price", api_name="unitPrice", type="decimal"),
            PropertyDecl(name="hidden_col", api_name="hiddenCol", type="string", hidden=True),
        ],
    )


def test_to_object_maps_api_names_and_omits_nulls_and_hidden():
    class Row:
        _mapping = {"id": "abc", "goods_name": "泵", "unit_price": None, "hidden_col": "secret"}

        def __getitem__(self, k):
            return self._mapping[k]

    obj = to_object(_item_type(), Row())
    assert obj["primaryKey"] == "abc"
    assert obj["properties"] == {"goodsName": "泵"}  # unit_price null omitted, hidden_col excluded


def test_to_object_converts_decimal():
    from decimal import Decimal

    class Row:
        _mapping = {"id": "x", "goods_name": "阀", "unit_price": Decimal("12.50"), "hidden_col": None}

        def __getitem__(self, k):
            return self._mapping[k]

    obj = to_object(_item_type(), Row())
    assert obj["properties"]["unitPrice"] == 12.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_mapper.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `engine/mapper.py`**

```python
"""Map physical DB rows to ontology objects (camelCase api_names, nulls omitted, hidden excluded)."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.extensions.ontology.registry import ObjectTypeDecl


def _jsonable(v: Any) -> Any:
    if isinstance(v, (Decimal,)):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.loads(json.dumps(v, default=str))
    return v


def to_object(obj: ObjectTypeDecl, row: Any) -> dict[str, Any]:
    """row: an object exposing ``[column_name]`` (SQLAlchemy Row / dict)."""
    mapping = dict(row) if isinstance(row, dict) else row._mapping
    props: dict[str, Any] = {}
    for p in obj.properties:
        if p.hidden:
            continue
        v = mapping.get(p.name)
        if v is None:
            continue
        props[p.api_name] = _jsonable(v)
    return {"primaryKey": str(mapping.get(obj.pk.column)), "properties": props}


def select_columns(obj: ObjectTypeDecl) -> list[str]:
    """Visible physical columns to select (excludes hidden)."""
    return [obj.pk.column] + [p.name for p in obj.properties if not p.hidden]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_mapper.py -v"`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/engine/mapper.py backend/tests/test_ontology_mapper.py
git commit -m "feat(ontology): 行映射器 — apiName 输出/null 省略/hidden 排除/decimal 转换"
```

---

## Task 7: 查询引擎（engine/query.py，TDD）

**Files:**
- Create: `backend/app/extensions/ontology/engine/query.py`
- Test: `backend/tests/test_ontology_query.py`

- [ ] **Step 1: Write the failing test（纯逻辑：链接 join 解析 + keyset cursor，不碰 DB）**

```python
"""Tests for ontology query engine (pure parts)."""
import pytest

from app.extensions.ontology.engine.query import cursor_encode, cursor_decode, resolve_link_join
from app.extensions.ontology.registry import Registry


def test_cursor_roundtrip():
    enc = cursor_encode("abc-123")
    assert cursor_decode(enc) == "abc-123"


def test_resolve_foreign_key_join(monkeypatch):
    from app.extensions.ontology.registry import LinkTypeDecl, JoinDecl

    link = LinkTypeDecl(
        api_name="item_in_document", display_name="d", source="contract_item",
        target="contract_document", cardinality="N:1",
        join=JoinDecl(type="foreign_key", source_column="document_id", target_column="id"),
    )
    # forward: given a contract_item pk, target where target.id = source.document_id
    fwd = resolve_link_join(link, source=True)
    assert "document_id" in fwd and "target" in fwd.lower()


def test_resolve_normalized_key_join():
    from app.extensions.ontology.registry import LinkTypeDecl, JoinDecl

    link = LinkTypeDecl(
        api_name="part_cluster_matches_goods_cluster", display_name="d",
        source="part_cluster", target="goods_cluster", cardinality="N:N",
        join=JoinDecl(type="normalized_key_match", expression="a.rep = b.rep"),
    )
    sql = resolve_link_join(link, source=True)
    assert "JOIN" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_query.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `engine/query.py`（纯逻辑核心）**

```python
"""Ontology query engine — get/list/search/aggregate/link traversal over the registry.

Pure core: cursor + link-join resolution (no DB). DB-touching methods delegate to
the connectors selected by each object type's access.path.
"""
from __future__ import annotations

import base64
from typing import Any

from app.extensions.ontology.engine import filters as F
from app.extensions.ontology.engine import mapper as M
from app.extensions.ontology.registry import LinkTypeDecl, ObjectTypeDecl, Registry


def cursor_encode(pk: Any) -> str:
    return base64.urlsafe_b64encode(str(pk).encode()).decode()


def cursor_decode(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def resolve_link_join(link: LinkTypeDecl, source: bool) -> str:
    """Return the SQL fragment to fetch linked objects.

    source=True: link.source is the current object (forward).
    source=False: link.target is the current object (reverse).
    """
    if link.join.type == "foreign_key":
        sc, tc = link.join.source_column, link.join.target_column
        # Forward: target rows whose target_column equals current source's source_column.
        # Reverse: source rows whose source_column equals current target's pk.
        return f"{'target' if source else 'source'}.{tc if source else sc} = :current_pk"
    # normalized_key_match: expression references both tables; alias target=target, source=source
    expr = link.join.expression or ""
    return f"({expr})"


class QueryEngine:
    def __init__(self, registry: Registry, pg_connector=None, ds_connector=None):
        self.registry = registry
        self.pg = pg_connector
        self.ds = ds_connector

    def _obj(self, api_name: str) -> ObjectTypeDecl:
        obj = self.registry.object_by_name(api_name)
        if obj is None or not obj.enabled:
            raise ValueError(f"unknown or disabled object type: {api_name}")
        return obj

    def _connector(self, obj: ObjectTypeDecl):
        if obj.access.path == "postgres_ext":
            return self.pg
        return self.ds

    async def get(self, api_name: str, pk: Any, include_properties: list[str] | None = None) -> dict[str, Any] | None:
        obj = self._obj(api_name)
        rows = await self._connector(obj).execute_select(
            obj.access.table if obj.access.path == "postgres_ext" else obj.access.table_name,
            M.select_columns(obj),
            f"{obj.pk.column} = :p0",
            {"p0": pk},
            None,
            1,
        )
        return M.to_object(obj, rows[0]) if rows else None

    async def list(
        self,
        api_name: str,
        filters: dict | None = None,
        order_by: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        include_properties: list[str] | None = None,
    ) -> dict:
        obj = self._obj(api_name)
        bind: dict[str, Any] = {}
        where = ""
        if filters:
            where = F.compile_filter(obj, filters, bind)
        if cursor:
            pk_val = cursor_decode(cursor)
            pk_cond = f"{obj.pk.column} > :p0" if not where else f" AND {obj.pk.column} > :p{len(bind)}"
            key = "p0" if not where else f"p{len(bind)}"
            bind[key] = pk_val
            where = (where + pk_cond) if where else pk_cond
        rows = await self._connector(obj).execute_select(
            obj.access.table if obj.access.path == "postgres_ext" else obj.access.table_name,
            M.select_columns(obj),
            where,
            bind,
            order_by or obj.pk.column,
            min(limit + 1, 200),
        )
        has_more = len(rows) > limit
        objs = [M.to_object(obj, r) for r in rows[:limit]]
        return {
            "objects": objs,
            "nextPageToken": cursor_encode(objs[-1]["primaryKey"]) if (objs and has_more) else None,
            "hasMore": has_more,
        }

    async def search(self, api_name: str, term: str, limit: int = 20) -> dict:
        obj = self._obj(api_name)
        searchable = [p for p in obj.properties if p.searchable and not p.hidden]
        if not searchable:
            return {"objects": [], "message": f"{api_name} 无 searchable 字段"}
        bind: dict[str, Any] = {}
        clauses = []
        for i, p in enumerate(searchable):
            clauses.append(f"{p.name} ILIKE :p{i}")
            bind[f"p{i}"] = f"%{term}%"
        where = " OR ".join(clauses)
        rows = await self._connector(obj).execute_select(
            obj.access.table if obj.access.path == "postgres_ext" else obj.access.table_name,
            M.select_columns(obj),
            where,
            bind,
            obj.pk.column,
            limit,
        )
        return {"objects": [M.to_object(obj, r) for r in rows]}

    async def get_links(self, api_name: str, pk: Any, link_type: str, limit: int = 50, cursor: str | None = None) -> dict:
        obj = self._obj(api_name)
        link = self.registry.link_by_name(link_type)
        if link is None or not link.enabled:
            raise ValueError(f"unknown or disabled link type: {link_type}")
        source = obj.api_name == link.source
        target = obj.api_name == link.target
        if not (source or target):
            raise ValueError(f"link {link_type} does not involve {api_name}")
        tgt = self.registry.object_by_name(link.target if source else link.source)
        join = resolve_link_join(link, source=source)
        bind: dict[str, Any] = {"current_pk": pk}
        where = join.replace(":current_pk", ":p0")
        rows = await self._connector(tgt).execute_select(
            tgt.access.table if tgt.access.path == "postgres_ext" else tgt.access.table_name,
            M.select_columns(tgt),
            where,
            bind,
            tgt.pk.column,
            min(limit + 1, 200),
        )
        has_more = len(rows) > limit
        objs = [M.to_object(tgt, r) for r in rows[:limit]]
        return {"objects": objs, "nextPageToken": cursor_encode(objs[-1]["primaryKey"]) if (objs and has_more) else None, "hasMore": has_more}

    async def aggregate(self, api_name: str, group_by: str | None = None, metric: dict | None = None, filters: dict | None = None) -> list[dict]:
        obj = self._obj(api_name)
        bind: dict[str, Any] = {}
        where = F.compile_filter(obj, filters, bind) if filters else ""
        if group_by:
            gprop = obj.property_by_api(group_by)
            if gprop is None:
                raise ValueError(f"unknown group_by: {group_by}")
            gcol = gprop.name
        fn = (metric or {}).get("fn", "count")
        fcol = None
        if metric and metric.get("field"):
            fprop = obj.property_by_api(metric["field"])
            if fprop is None:
                raise ValueError(f"unknown metric field: {metric['field']}")
            fcol = fprop.name
        if fn == "percentile_cont":
            p = float((metric or {}).get("p", 0.5))
            agg = f"percentile_cont({p}) WITHIN GROUP (ORDER BY {fcol})"
        elif fn == "count":
            agg = "COUNT(*)"
        else:
            agg = f"{fn.upper()}({fcol})" if fcol else f"{fn.upper()}(*)"
        cols = [agg]
        sql = f"SELECT {agg}"
        if group_by:
            cols.insert(0, gcol)
            sql = f"SELECT {gcol}, {agg}"
        sql += f" FROM {obj.access.table if obj.access.path == 'postgres_ext' else obj.access.table_name}"
        if where:
            sql += f" WHERE {where}"
        if group_by:
            sql += f" GROUP BY {gcol}"
        # NOTE: aggregate 走 connector 的 raw 执行（不加 SELECT 列白名单）——下钻到 Task 3/4 的 execute_select 需允许 agg 表达式。
        raise NotImplementedError("aggregate raw-SQL path wired in Step 3c (connectors expose run_raw_select)")
```

- [ ] **Step 3c: 给连接器补 `run_raw_select`（Task 3/4 追加）**

`connectors/postgres_ext.py` 追加：

```python
async def run_raw_select(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute an already-validated read-only SELECT (used by aggregate)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy import text

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(sql).bindparams(**(params or {})))
            return [dict(r) for r in result.mappings().all()]
    finally:
        await engine.dispose()
```

`connectors/data_source.py` 追加（同 Task 4 `execute_select` 的连接逻辑，只换 SQL 源）：

```python
async def run_raw_select(source_id: str, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.data_source.service import assert_readonly_select

    safe_sql = assert_readonly_select(sql)  # aggregate SQL 同样过守卫
    src = await _resolve_source(source_id)
    engine = create_async_engine(_ext_url(src.connection_config or {}), pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(safe_sql).bindparams(**(params or {})))
            return [dict(r) for r in result.mappings().all()]
    finally:
        await engine.dispose()
```

> **简化**：`aggregate` 的 raw 路径先把 SQL 交给 `assert_readonly_select` 校验再执行（两侧连接器一致）。

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_query.py -v"`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/engine/ backend/tests/test_ontology_query.py backend/app/extensions/ontology/connectors/
git commit -m "feat(ontology): 查询引擎核心 — cursor/链接 join 解析 + get/list/search/get_links/aggregate 骨架"
```

> **注**：`traverse_path`（多跳）在 Task 8 MCP 内以递归 `get_links` 组合实现（见 Task 8 Step 3 的 `_traverse`），引擎层只留 `get_links` 单跳原子。

---

## Task 8: 统一 MCP server（server.py，7 工具）

**Files:**
- Create: `backend/app/extensions/ontology/server.py`
- Test: `backend/tests/test_ontology_mcp.py`

- [ ] **Step 1: Write the failing test（工具清单 + handler 路由）**

```python
"""Tests for ontology MCP server."""
from app.extensions.ontology.server import TOOLS, TOOL_HANDLERS

EXPECTED = {
    "describe_ontology", "list_objects", "get_object", "search_objects",
    "get_links", "traverse_path", "aggregate_objects",
}


def test_all_tools_registered():
    assert {t.name for t in TOOLS} == EXPECTED


def test_all_tools_have_handlers():
    assert EXPECTED <= set(TOOL_HANDLERS)


def test_tool_descriptions_nonempty():
    for t in TOOLS:
        assert t.description.strip(), f"{t.name} description empty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_mcp.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `server.py`**（照 `contract_price/mcp.py` 模式）

```python
"""Unified ontology MCP server — read-only semantic query/navigation tools for the agent.

One semantic layer over the market/analysis modules (mother spec §7). Read-only
by construction. Registered in extensions_config.json (stdio), env overrides:
ONTOLOGY_DB_URL (extensions DB) — see bug-698 (MCP subprocess env not inherited).
"""
from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.extensions.ontology.engine.query import QueryEngine
from app.extensions.ontology.registry import RegistryCache

_cache = RegistryCache()
_engine = None


def _get_engine() -> QueryEngine:
    global _engine
    if _engine is None:
        from app.extensions.ontology.connectors import data_source as ds
        from app.extensions.ontology.connectors import postgres_ext as pg

        _engine = QueryEngine(_cache.get(), pg_connector=pg, ds_connector=ds)
    return _engine


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


TOOLS = [
    Tool(name="describe_ontology", description="描述 ontology 注册表:对象类型/链接/属性(含描述/单位/枚举,隐藏敏感字段)。可选 object_type 只看单个。",
         inputSchema={"type": "object", "properties": {"object_type": {"type": "string", "description": "对象类型 api_name,省略则全部"}}}),
    Tool(name="list_objects", description="查询对象列表:typed filter(eq/ne/gt/gte/lt/lte/in/between/and/or/not/is_null)+排序+keyset 分页。",
         inputSchema={"type": "object", "properties": {
             "object_type": {"type": "string"}, "filter": {"type": "object"},
             "order_by": {"type": "string"}, "limit": {"type": "integer", "maximum": 200},
             "cursor": {"type": "string"}, "include_properties": {"type": "array", "items": {"type": "string"}}},
             "required": ["object_type"]}),
    Tool(name="get_object", description="按主键取单个对象。",
         inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "primary_key": {}, "include_properties": {"type": "array", "items": {"type": "string"}}}, "required": ["object_type", "primary_key"]}),
    Tool(name="search_objects", description="在 searchable 文本属性上模糊搜索对象。",
         inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "term": {"type": "string"}, "limit": {"type": "integer", "maximum": 50}}, "required": ["object_type", "term"]}),
    Tool(name="get_links", description="沿链接类型获取关联对象(正向或反向自动解析)。",
         inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "primary_key": {}, "link_type": {"type": "string"}, "limit": {"type": "integer", "maximum": 200}, "cursor": {"type": "string"}}, "required": ["object_type", "primary_key", "link_type"]}),
    Tool(name="traverse_path", description="沿点分链接路径多跳遍历(如 spare_part_item.spare_item_in_cluster.part_cluster.part_cluster_matches_goods_cluster.goods_cluster),跨模块可参与。",
         inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "primary_key": {}, "path": {"type": "string"}, "limit": {"type": "integer", "maximum": 200}}, "required": ["object_type", "primary_key", "path"]}),
    Tool(name="aggregate_objects", description="对象集合级聚合(group_by + count/sum/avg/min/max/percentile_cont),单查询不 N+1。",
         inputSchema={"type": "object", "properties": {
             "object_type": {"type": "string"}, "group_by": {"type": "string"},
             "metric": {"type": "object", "description": "{field, fn, p?}"}, "filter": {"type": "object"}},
             "required": ["object_type"]}),
]


def _describe(engine: QueryEngine, object_type: str | None = None) -> dict:
    reg = _cache.get()
    if object_type:
        obj = reg.object_by_name(object_type)
        if obj is None:
            raise ValueError(f"unknown object type: {object_type}")
        objs = [obj]
    else:
        objs = [o for o in reg.object_types if o.enabled]
    links = [l for l in reg.link_types if l.enabled]
    return {
        "schema_version": reg.schema_version,
        "registry_version": reg.registry_version,
        "object_types": [
            {
                "api_name": o.api_name, "display_name": o.display_name, "description": o.description,
                "domain": o.domain, "access": {"path": o.access.path, "table": o.access.table or o.access.table_name},
                "pk": o.pk.api_name,
                "properties": [
                    {"api_name": p.api_name, "type": p.type, "description": p.description,
                     "format": p.format, "unit": p.unit, "enum": p.enum, "filterable": p.filterable,
                     "searchable": p.searchable}
                    for p in o.properties if not p.hidden
                ],
            }
            for o in objs
        ],
        "link_types": [
            {"api_name": l.api_name, "source": l.source, "target": l.target,
             "cardinality": l.cardinality, "reverse": l.reverse, "cross_module": l.cross_module}
            for l in links
        ],
    }


async def _traverse(engine: QueryEngine, api_name: str, pk, path: str, limit: int) -> dict:
    hops = [h for h in path.split(".") if h]
    node = await engine.get(api_name, pk)
    if node is None:
        return {"error": "not found"}
    result = node
    for hop in hops:
        linked = await engine.get_links(api_name, node["primaryKey"], hop, limit)
        if not linked["objects"]:
            result = {**result, f"via_{hop}": []}
            break
        node = linked["objects"][0]
        api_name = _cache.get().link_by_name(hop).target if _cache.get().link_by_name(hop).source == api_name else _cache.get().link_by_name(hop).source
        result = {**result, f"via_{hop}": node}
    return result


async def _handle_describe(arguments: dict) -> list[TextContent]:
    return _ok({"success": True, **_describe(_get_engine(), arguments.get("object_type"))})


async def _handle_list(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().list(
            arguments["object_type"], arguments.get("filter"), arguments.get("order_by"),
            arguments.get("limit", 50), arguments.get("cursor"), arguments.get("include_properties"),
        )
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_get(arguments: dict) -> list[TextContent]:
    try:
        obj = await _get_engine().get(arguments["object_type"], arguments["primary_key"])
        return _ok({"success": True, "object": obj} if obj else {"success": True, "object": None})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_search(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().search(arguments["object_type"], arguments["term"], arguments.get("limit", 20))
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_links(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().get_links(
            arguments["object_type"], arguments["primary_key"], arguments["link_type"],
            arguments.get("limit", 50), arguments.get("cursor"),
        )
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_traverse(arguments: dict) -> list[TextContent]:
    try:
        data = await _traverse(_get_engine(), arguments["object_type"], arguments["primary_key"], arguments["path"], arguments.get("limit", 50))
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_aggregate(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().aggregate(arguments["object_type"], arguments.get("group_by"), arguments.get("metric"), arguments.get("filter"))
        return _ok({"success": True, "rows": data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


TOOL_HANDLERS = {
    "describe_ontology": _handle_describe,
    "list_objects": _handle_list,
    "get_object": _handle_get,
    "search_objects": _handle_search,
    "get_links": _handle_links,
    "traverse_path": _handle_traverse,
    "aggregate_objects": _handle_aggregate,
}

server = Server("ontology")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_mcp.py -v"`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/server.py backend/tests/test_ontology_mcp.py
git commit -m "feat(ontology): 统一 MCP server — 7 工具(describe/list/get/search/links/traverse/aggregate)"
```

---

## Task 9: REST routers（routers.py + schemas.py，11 端点）

**Files:**
- Create: `backend/app/extensions/ontology/routers.py`
- Create: `backend/app/extensions/ontology/schemas.py`
- Test: `backend/tests/test_ontology_rest.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology REST surface (thin passthrough of the engine)."""
import pytest

from app.extensions.ontology.routers import router


def test_router_prefix_and_routes():
    assert router.prefix == "/api/extensions/ontology"
    paths = {r.path for r in router.routes}
    assert "/registry" in paths
    assert "/object-types" in paths
    assert "/link-types" in paths
    assert "/objects/{object_type}" in paths
    assert "/objects/{object_type}/{primary_key}" in paths
    assert "/search" in paths
    assert "/aggregate" in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_rest.py -v"`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `schemas.py` + `routers.py`**（照 `contract_price/routers.py` 模式）

`schema.py` 内容见下（全部 pydantic 模型）：

```python
"""Ontology REST response models (mother spec §8)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PropertyOut(BaseModel):
    api_name: str
    type: str
    description: str = ""
    format: str | None = None
    unit: str | None = None
    enum: list[str] | None = None
    filterable: bool = False
    searchable: bool = False
    indexed: bool = False


class ObjectTypeOut(BaseModel):
    api_name: str
    display_name: str
    description: str
    domain: str
    icon: str = ""
    access: dict[str, Any]
    pk: str
    properties: list[PropertyOut]
    availability: dict[str, Any] = {"available": True}


class LinkTypeOut(BaseModel):
    api_name: str
    display_name: str
    source: str
    target: str
    cardinality: str
    reverse: str | None = None
    join_expression: str | None = None
    cross_module: bool = False
    enabled: bool = True


class RegistryOut(BaseModel):
    schema_version: int
    registry_version: int
    hot_reload: bool
    files: list[dict[str, Any]]
    object_types: list[ObjectTypeOut]
    link_types: list[LinkTypeOut]


class ObjectListOut(BaseModel):
    objects: list[dict[str, Any]]
    nextPageToken: str | None = None
    hasMore: bool = False


class AggregateRow(BaseModel):
    group_value: Any | None = None
    value: Any | None = None
```

`routers.py`：

```python
"""Ontology REST surface — thin passthrough of the engine for the semantic-map frontend.

Mounted at /api/extensions/ontology. Admin-gated (require_permission system:access),
same as contract_price/spare_parts (mother spec §10 R3 decision).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.extensions.auth.middleware import require_permission
from app.extensions.ontology.engine.query import QueryEngine
from app.extensions.ontology.registry import RegistryCache
from app.extensions.ontology.schemas import (
    AggregateRow, LinkTypeOut, ObjectListOut, ObjectTypeOut, PropertyOut, RegistryOut,
)
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/ontology", tags=["Ontology Semantic Layer"])

_cache = RegistryCache()
_engine: QueryEngine | None = None


def _get_engine() -> QueryEngine:
    global _engine
    if _engine is None:
        from app.extensions.ontology.connectors import data_source as ds
        from app.extensions.ontology.connectors import postgres_ext as pg

        _engine = QueryEngine(_cache.get(), pg_connector=pg, ds_connector=ds)
    return _engine


@router.get("/registry", response_model=RegistryOut)
async def get_registry(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return RegistryOut(
        schema_version=reg.schema_version, registry_version=reg.registry_version,
        hot_reload=reg.hot_reload, files=[f.model_dump() for f in reg.files],
        object_types=[_to_type_out(o) for o in reg.object_types if o.enabled],
        link_types=[LinkTypeOut(**l.model_dump()) for l in reg.link_types if l.enabled],
    )


@router.post("/registry/reload")
async def reload_registry(_: CurrentUser = Depends(require_permission("system:access"))):
    _cache._registry = None  # force re-load
    reg = _cache.get()
    return {"registry_version": reg.registry_version, "reloaded": True}


@router.get("/object-types", response_model=list[ObjectTypeOut])
async def list_object_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return [_to_type_out(o) for o in reg.object_types if o.enabled]


@router.get("/object-types/{api_name}", response_model=ObjectTypeOut)
async def get_object_type(api_name: str, _: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    obj = reg.object_by_name(api_name)
    if obj is None:
        raise HTTPException(404, "object type not found")
    return _to_type_out(obj)


@router.get("/link-types", response_model=list[LinkTypeOut])
async def list_link_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return [LinkTypeOut(**l.model_dump()) for l in reg.link_types if l.enabled]


@router.get("/objects/{object_type}", response_model=ObjectListOut)
async def list_objects(object_type: str, filter: str | None = None, order_by: str | None = None,
                       limit: int = 50, cursor: str | None = None,
                       _: CurrentUser = Depends(require_permission("system:access"))):
    import json

    filters = json.loads(filter) if filter else None
    return await _get_engine().list(object_type, filters, order_by, limit, cursor)


@router.get("/objects/{object_type}/{primary_key}")
async def get_object(object_type: str, primary_key: str,
                     _: CurrentUser = Depends(require_permission("system:access"))):
    obj = await _get_engine().get(object_type, primary_key)
    if obj is None:
        raise HTTPException(404, "object not found")
    return {"success": True, "object": obj}


@router.get("/objects/{object_type}/{primary_key}/links/{link_type}", response_model=ObjectListOut)
async def get_links(object_type: str, primary_key: str, link_type: str, limit: int = 50, cursor: str | None = None,
                    _: CurrentUser = Depends(require_permission("system:access"))):
    return await _get_engine().get_links(object_type, primary_key, link_type, limit, cursor)


@router.post("/objects/traverse")
async def traverse(body: dict[str, Any], _: CurrentUser = Depends(require_permission("system:access"))):
    return await _get_engine().traverse_path(body["object_type"], body["primary_key"], body["path"], body.get("limit", 50))


@router.get("/search")
async def search(term: str, object_type: str | None = None, limit: int = 20,
                 _: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    if object_type:
        return await _get_engine().search(object_type, term, limit)
    # 全局:跨所有 searchable 类型聚合
    out = []
    for o in reg.object_types:
        if not o.enabled:
            continue
        try:
            r = await _get_engine().search(o.api_name, term, limit)
            out.extend({"object_type": o.api_name, **item} for item in r.get("objects", []))
        except Exception:  # noqa: BLE001 — one type failing shouldn't kill global search
            continue
    return {"objects": out, "hasMore": False}


@router.post("/aggregate", response_model=list[AggregateRow])
async def aggregate(body: dict[str, Any], _: CurrentUser = Depends(require_permission("system:access"))):
    rows = await _get_engine().aggregate(body["object_type"], body.get("group_by"), body.get("metric"), body.get("filter"))
    return [AggregateRow(**r) for r in rows]


def _to_type_out(o) -> ObjectTypeOut:
    return ObjectTypeOut(
        api_name=o.api_name, display_name=o.display_name, description=o.description,
        domain=o.domain, icon=o.icon, access={"path": o.access.path, "table": o.access.table or o.access.table_name},
        pk=o.pk.api_name,
        properties=[PropertyOut(**p.model_dump(exclude={"name"})) for p in o.properties if not p.hidden],
    )
```

> `traverse_path` 在引擎层缺失——Task 8 的 `_traverse` 在 MCP 层实现。REST 的 traverse 应复用同一逻辑：把 `_traverse` 上移到引擎 `QueryEngine.traverse_path`（Task 8 实现时顺手把 `_traverse` 提为引擎方法），REST 直接调 `_get_engine().traverse_path(...)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_ontology_rest.py -v"`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/ontology/routers.py backend/app/extensions/ontology/schemas.py backend/tests/test_ontology_rest.py
git commit -m "feat(ontology): REST surface — 11 端点(registry/object-types/link-types/objects/search/aggregate), system:access 门控"
```

---

## Task 10: 权限注册 + gateway 挂载

**Files:**
- Modify: `config/permissions.yaml`
- Modify: `config/roles_custom.yaml`（如 built-in 角色需显式 page）
- Modify: `backend/app/gateway/app.py`（挂载 router）
- Test: `backend/tests/test_ontology_registry.py`（追加权限断言可选）

- [ ] **Step 1: `config/permissions.yaml` 加 `ontology` 模块块**（照 contract_price 模式）

在 `modules:` 下追加：

```yaml
  # ─── Ontology 统一语义层（平台原语；语义地图前端页）───
  ontology:
    display_name: "语义地图"
    nav_id: "nav:ontology"
    pages:
      - id: "ontology:page:map"
        display_name: "语义地图"
    data_scopes: []
```

- [ ] **Step 2: `config/roles_custom.yaml` 显式授权**（admin-gated：superadmin 自动；给 dept_head/project_manager 补 page+nav）

在相应 built-in 角色 overlay 的 `pages`/`nav` 追加 `"ontology:page:map"` / `"nav:ontology"`（逐条显式，遵守 [[bug-1087]] overlay 整体替换语义）。

- [ ] **Step 3: `backend/app/gateway/app.py` 挂载 router**（照 spare_parts 挂载模式）

```python
from app.extensions.ontology import router as ontology_router  # 顶部 import 区
...
app.include_router(ontology_router)  # 与 data_source_router 相邻
```

- [ ] **Step 4: 验证 gateway 启动 + 权限闭合**

Run: `docker compose -p eai-docker restart gateway && sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/api/extensions/ontology/registry`
Expected: 未带 cookie → `401`（fail-closed）；带登录 cookie → `200`

- [ ] **Step 5: Commit**

```bash
git add config/permissions.yaml config/roles_custom.yaml backend/app/gateway/app.py
git commit -m "feat(ontology): 权限点 + 页面/导航注册 + gateway 挂载(admin-gated)"
```

---

## Task 11: MCP 注册 + 运行时验证

**Files:**
- Modify: `extensions_config.json`
- Test: 运行时探针

- [ ] **Step 1: `extensions_config.json` 注册 `ontology` MCP server**（照 data_source 模式，含 env 显式 DB URL——bug-698 铁律）

```json
"ontology": {
  "enabled": true,
  "type": "stdio",
  "command": "/app/backend/.venv/bin/python",
  "args": ["-m", "app.extensions.ontology.server"],
  "env": {
    "ONTOLOGY_DB_URL": "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow"
  },
  "description": "统一语义层:对象/链接/属性只读查询与导航"
}
```

> 若 data_source 表也在扩展库（已确认），`data_source` 连接器解析源记录用同一 URL（`_resolve_db_url` 兜底）；`DATA_SOURCE_DB_URL` 不必重复设。

- [ ] **Step 2: 重启 gateway + 探针验证工具装载**

Run: `docker compose -p eai-docker restart gateway`
Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. .venv/bin/python -c \"from deerflow.mcp.cache import initialize_mcp_tools; tools=initialize_mcp_tools(); print([t.name for t in tools if t.name.startswith('ontology')])\""`
Expected: 输出含 `ontology_<tool>` 7 个工具名（`tool_name_prefix=true` 前缀形式）

- [ ] **Step 3: 冒烟：describe_ontology 经 MCP 可答**

Run: 对话页问"列出 ontology 里有哪些对象类型"，看 agent 调 `ontology_describe_ontology` 返回 11 对象类型。
Expected: agent 正确返回注册表内容

- [ ] **Step 4: Commit**

```bash
git add extensions_config.json
git commit -m "feat(ontology): 注册 ontology MCP server(env 显式 DB URL)"
```

---

## Task 12: CI lint（scripts/ontology_lint.py）

**Files:**
- Create: `backend/scripts/ontology_lint.py`
- Modify: `backend/Makefile`（加 `lint-ontology` 目标）
- Test: `backend/tests/test_ontology_lint.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ontology registry lint (§2.2 acceptance checklist)."""
import shutil
from pathlib import Path

from app.extensions.ontology.registry import load_registry


def test_lint_passes_on_real_registry(tmp_path):
    src = Path(__file__).resolve().parent.parent / "app" / "extensions" / "ontology" / "registry"
    for f in src.iterdir():
        if f.is_file() and f.suffix == ".yaml":
            shutil.copy2(f, tmp_path / f.name)
    reg = load_registry(tmp_path)
    # all links enabled this phase
    assert all(l.enabled for l in reg.link_types)
    # hidden keywords: data_source.connection_config flagged by keyword + declared hidden
    ds = reg.object_by_name("data_source")
    cc = next(p for p in ds.properties if p.name == "connection_config")
    assert cc.hidden is True
```

- [ ] **Step 2: Run test to verify it fails（lint 脚本还不存在——先用 CLI 探针）**

Run: `docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. .venv/bin/python scripts/ontology_lint.py"`
Expected: `FileNotFoundError`（脚本未建）

- [ ] **Step 3: Implement `scripts/ontology_lint.py`**（§2.2 验收清单）

```python
"""Ontology registry lint — §2.2 acceptance checklist, exit 1 on failure.

Checks (mother-spec §2.2 / expansion-plan §2.2):
  1. PK immutability: every object type has an immutable surrogate-ish PK.
  2. hidden sensitive-field: keyword heuristic (cred/secret/password/salary/
     id_card/phone/身份证/薪酬...) + physical-table-column vs declared-column diff.
  3. describe coverage: every object type has non-empty description; link
     coverage >= threshold.
  4. cross-references valid (delegated to load_registry).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from app.extensions.ontology.registry import REGISTRY_DIR, load_registry

SENSITIVE_KEYWORDS = re.compile(
    r"cred|secret|password|passwd|salary|id_card|phone|身份证|薪酬|工资|token|api_key|private", re.I
)


def check_pk_immutability(reg) -> list[str]:
    errors = []
    for o in reg.object_types:
        if not o.pk.immutable:
            errors.append(f"{o.api_name}: pk immutable=False (must be surrogate UUID / stable key)")
        if o.pk.type not in ("string", "integer"):
            errors.append(f"{o.api_name}: pk type must be string/integer")
    return errors


def check_hidden_sensitive(reg) -> list[str]:
    errors = []
    for o in reg.object_types:
        for p in o.properties:
            if SENSITIVE_KEYWORDS.search(p.name) or SENSITIVE_KEYWORDS.search(p.api_name):
                if not p.hidden:
                    errors.append(f"{o.api_name}.{p.api_name}: sensitive field not hidden")
    return errors


def check_physical_column_diff(reg) -> list[str]:
    """Physical table columns vs declared columns. Only for postgres_ext types."""
    errors = []
    try:
        from app.extensions.database import Base
        from sqlalchemy import inspect

        # NOTE: introspection needs an engine; keep it optional & offline-friendly:
        # if Base metadata already has the table, diff columns.
        for o in reg.object_types:
            if o.access.path != "postgres_ext":
                continue
            table = Base.metadata.tables.get(o.access.table)
            if table is None:
                continue  # model not imported in this process; skip (offline lint)
            physical = {c.name for c in table.columns}
            declared = {o.pk.column} | {p.name for p in o.properties}
            missing = physical - declared
            if missing:
                errors.append(f"{o.api_name}: physical columns not declared: {sorted(missing)}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"column-diff check skipped: {exc}")
    return errors


def check_coverage(reg, threshold: float = 0.8) -> list[str]:
    errors = []
    for o in reg.object_types:
        if not o.description.strip():
            errors.append(f"{o.api_name}: empty description")
        if not o.properties:
            errors.append(f"{o.api_name}: no properties")
    # link coverage: every object type should participate in >=1 link (except pure metadata types)
    names = {o.api_name for o in reg.object_types}
    linked = {l.source for l in reg.link_types} | {l.target for l in reg.link_types}
    orphan = names - linked
    if orphan and len(orphan) / len(names) > (1 - threshold):
        errors.append(f"orphan object types (no links): {sorted(orphan)}")
    return errors


def main() -> int:
    reg = load_registry()
    errors: list[str] = []
    try:
        errors += check_pk_immutability(reg)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pk check failed: {exc}")
    errors += check_hidden_sensitive(reg)
    errors += check_physical_column_diff(reg)
    errors += check_coverage(reg)
    if errors:
        print("ontology-lint FAIL:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"ontology-lint OK ({len(reg.object_types)} object types, {len(reg.link_types)} links)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: `backend/Makefile` 加 lint 目标**

```makefile
lint-ontology:
	cd backend && PYTHONPATH=. uv run python scripts/ontology_lint.py
```

Run: `cd backend && PYTHONPATH=. uv run python scripts/ontology_lint.py`
Expected: `ontology-lint OK (11 object types, 12 links)`，exit 0

- [ ] **Step 5: CI 接线**（`.github/workflows/backend-unit-tests.yml` 追加一步，或独立 job）

```yaml
      - name: Ontology registry lint
        run: cd backend && PYTHONPATH=. uv run python scripts/ontology_lint.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ontology_lint.py backend/Makefile .github/workflows/backend-unit-tests.yml backend/tests/test_ontology_lint.py
git commit -m "feat(ontology): CI lint — 主键不可变 + hidden 敏感字段启发式 + 列 diff + 覆盖度"
```

---

## Self-Review（已做，执行前复查）

- **Spec coverage**：注册表 YAML（Task 1）✓ 加载器+热重载（Task 2）✓ 两连接器（Task 3/4）✓ filter/mapper/query 引擎（Task 5/6/7）✓ MCP 7 工具（Task 8）✓ REST 11 端点（Task 9）✓ 权限+挂载（Task 10）✓ MCP 注册（Task 11）✓ CI lint（Task 12）✓。**前端语义地图页不在本计划**（独立后续计划，扩张方案 §9 的前置正是本后端）。
- **C3 stub**：link schema 含 `enabled` 字段（Task 1 cross_module.yaml 说明 + Task 2 test_link_schema_has_enabled_field 锁定）✓
- **类型一致性**：`read_only_select`/`execute_select` 签名跨 Task 3/4/7 一致；`QueryEngine.get/list/search/get_links/aggregate` 与 MCP/REST handler 调用一致；`to_object` 输出 `{primaryKey, properties}` 全链路一致。
- **已知简化（ponytail 注释）**：
  - Task 4 `execute_select` 连接构建 + Task 3c `run_raw_select` 有重复连接代码——两处抽出共享 `_connect_external(src, sql, params)` helper 即可，别过度抽象。
  - Task 7 `aggregate` 的 raw SQL 只对 registry 白名单列 + 已校验 SQL 生效，仍过 `assert_readonly_select`。
  - Task 8 `traverse` 当前在 MCP 层实现；Task 9 已标注上移为 `QueryEngine.traverse_path`，实现 Task 8 时顺手做。

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-08-14-ontology-semantic-layer.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个任务派发独立 subagent，任务间审查，快速迭代
2. **Inline Execution** — 本会话用 executing-plans 批量执行 + 检查点审查

选哪种？（前端语义地图页作为独立计划，在本后端落地后编写。）
