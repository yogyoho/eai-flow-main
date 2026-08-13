# Ontology 概念移植设计 — 统一语义层（市场/分析数据域）

- **日期**: 2026-08-14
- **意图**: 把 Palantir Ontology（对象类型/链接/属性 + 统一读写面）**概念移植**为本系统原生轻量语义层，评估并落地"企业智能化应用平台"支撑
- **状态**: 设计稿（已完成 brainstorming 三轮确认，待评审后进入 writing-plans）
- **分支**: `main-dev-fork`
- **范围**: 一期 = 市场/分析数据域的**只读统一语义层**（声明式 YAML 注册表 + 通用引擎 + 统一 MCP + 前端语义地图页）；**不含 Action 写路径、函数、对象级 ACL、协作域**
- **研究依据**: Palantir Foundry Ontology 权威技术面（workflow 研究输出，2026-08-14）；市场分析四模块设计稿 `2026-08-13-market-analysis-modules-design.md`
- **修订**:
  - 2026-08-14 (R1): 意图确认为**概念移植**（非产品采购/非纯文档）。一期价值 = 统一语义层（平台一致性）。覆盖域 = 市场/分析数据域。消费端 = MCP + 前端语义地图页。
  - 2026-08-14 (R2): 方案定为 **方案 A：声明式 YAML 注册表 + 通用引擎**。
  - 2026-08-14 (R3): 三个开放项拍板——跨模块链接用**聚类代表名匹配**；读路径权限用**管理员级门控**（system:access + hidden:true 列级隐藏）；前端语义地图页用**独立应用中心 app**。

---

## 1. 背景与目标

### 1.1 什么是 Palantir Ontology（研究摘要）

Ontology 是 Palantir Foundry 的操作性语义层：把表格式数据管线变成**面向业务的图**——对象类型（Object Types）、链接类型（Link Types）、动作（Actions）、函数（Functions）、接口（Interfaces）。核心机制：

- **对象类型** = 实体 schema（API 名不可变 snake_case、显示名、**描述**、不可变主键），背书一个数据集 + 若干补充集。
- **链接类型** = 对象间类型化关系（基数 1:1/1:N/N:N，反向链接自动维护），是"表变成图"的关键；N:N 或带属性的链接需关联表。
- **动作 Actions** = 唯一受治理写路径（参数化、提交前校验、审计、VALIDATE 预检），读路径无 Action 则只读。
- **函数 Functions** = 服务端派生逻辑，**对对象集合批处理**（禁止 N+1）。
- **对象级权限** = 查询时强制过滤（Restricted View 行级谓词、属性安全策略列级可见性、图传播隐藏），规则在 Ontology 层，所有消费端（Workshop/OSDK/AIP agent）自动看到同一过滤视图。
- **AIP 消费** = Agent 经一组 ontology 工具（Query Objects / Apply Action / Call Function）读写语义数据；**对象/属性描述是 LLM 查询生成的精度乘数**（已实证），且按对象类型限定可见属性（安全边界 + token 控制）。

**关键借鉴点（概念而非产品）**：
- 最小可移植集 = 对象类型 + 类型化属性 + 链接类型 + 只读 API + 描述元数据 + 行/列级可见性（可选 Action）。
- 主键不可变是最高杠杆决策（业务键变更 = 本体重建）。
- 派生属性必须集合级批处理。
- 不要复刻 Palantir 的 dataset→索引 funnel（有同步延迟/最终一致）——原生读 Postgres 直接获得强一致 + join。

### 1.2 系统现状（为什么需要语义层）

市场/分析模块（合同价格 `cpa_`、备品备件 `csp_`、投标 `mock_bid` + data_source）是**三个独立扩展**，存在四个结构性缺口：

1. **无统一语义层**：对象模型硬编码在各 `models.py`，跨 3 套物理 schema（扩展库 cpa_/csp_ + 独立 mock_market 库），跨库无法做对象链接。
2. **访问面三裂**：同一实体经 MCP 只读工具（agent）+ REST CRUD（前端）+ skill 子进程直写 DB 三条路暴露，无统一读/写契约。
3. **跨模块键是"提示"不是"链接"**：goods_name/part_name、contract_no、supplier/customer、project_name 等只在注释里标注可连接，无强制链接。
4. **权限粗粒度**：分析模块全 `system:access`，无对象级；`data_source.connection_config` 等含凭据字段暴露面未统一治理。

### 1.3 目标与意图（三轮确认）

| 决策 | 选择 | 理由 |
|---|---|---|
| 核心意图 | **概念移植**（轻量原生实现） | 不引入 Palantir 产品，不建索引/funnel；借思想做本系统语义层 |
| 一期首要价值 | **统一语义层（平台一致性）** | 对象/链接/属性注册表让平台像"一个整体"，是"企业智能应用平台"定位的骨架；风险最低 |
| 一期覆盖域 | **市场/分析数据域** | cpa_/csp_/bid 只读、对象关系清晰，能直接演示跨模块推理；协作/文档域二期 |
| 消费端 | **MCP + 前端语义地图页** | 能力经 MCP 到达 agent（3 层模型铁律）+ 平台一致性对用户可见 |

---

## 2. 范围

### 本期（Phase 1 — 只读语义层）

- ✅ 新独立模块 `backend/app/extensions/ontology/`
- ✅ 声明式 YAML 注册表：11 个对象类型 + 12 条链接类型（8 模块内 + 4 跨模块），versioned、热重载
- ✅ 通用查询引擎：`postgres_ext` 直连 + `data_source` 连接（复用只读守卫）
- ✅ 统一 `ontology` MCP server（7 工具），注册进 `extensions_config.json`
- ✅ REST surface（~11 端点）供前端语义地图页
- ✅ 前端应用中心 app `/ontology`（语义地图页）+ `shell/Sidebar.tsx` +1 导航行
- ✅ 权限：`ontology:read` / `ontology:view` 权限点 + `system:access` + `hidden:true` 列级隐藏 + fail-closed 只读

### 非本期（明确排除 / 后续）

- ❌ **Action 写路径**（受治理写：参数化 + 校验 + 审计）—— 二期，只作为**新对象类型**的前向路径，不 retro-fix 现有 skill 直写
- ❌ 函数/派生属性（中标率等自动计算）—— 仅留 `aggregate_objects` 批处理钩子
- ❌ 对象级 ACL 泛化（行/列级镜像现有 RBAC）—— 一期只做 admin 门控 + hidden 列隐藏
- ❌ 协作/文档域对象（collab_projects/sections/tasks/gates、ai_documents）—— 二期
- ❌ run_history 两类运维对象（cpa_run_history/csp_run_history）—— 二期
- ❌ 模糊匹配（跨模块链接只做归一化精确匹配）
- ❌ 接口/多态（Interfaces）—— 平台暂无真正多态实体，YAGNI
- ❌ 修改现有模块业务代码 / deer-flow harness 核心

---

## 3. 架构总览

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent(对话) ──功能调用──▶ ontology MCP server(统一语义查询/导航)      │
│  Frontend ──REST──▶ /api/extensions/ontology(薄透出,供语义地图页)     │
└───────────────────────────────┬────────────────────────────────────┘
                                │ 读 ontology 引擎(通用,按 YAML 解析)
┌───────────────────────────────┴────────────────────────────────────┐
│  ontology 注册表(versioned YAML, 热重载)                            │
│   对象类型 ×11: contract_document/item/goods_cluster ·             │
│               customer/spare_part_document/item/part_cluster ·     │
│               data_source/dataset/bid/bid_item                      │
│   链接类型 ×12: 8 模块内 FK + 4 跨模块(聚类代表名/contract_no/       │
│               project_name/supplier 归一化精确匹配)                 │
│   语义属性: 描述/单位/枚举/filterable/searchable/hidden              │
└──────────────┬───────────────────────────────┬─────────────────────┘
               ▼                               ▼
   connector: postgres_ext            connector: data_source
   (cpa_/csp_/data_sources/datasets    (mock_bid/mock_bid_item 外部库,
    直接只读 SELECT)                   复用 assert_readonly_select 守卫)
```

**核心思想**：ontology 是现有表之上的**只读业务语义投影**——不建对象索引、不复刻 Object Data Funnel、零数据拷贝；直接读 Postgres 获得读后写一致性（优于 Palantir 的最终一致）。任何现有模块的表都不用迁移。

**数据流示例（跨模块导航）**：

> 用户问 agent："某客户备件 A 的价格与合同价格体系市场均价比如何？"
> → `query_objects(spare_part_item, {part_name:"A"})` → `get_links(spare_part_item, id, "spare_item_in_cluster")` 到 part_cluster → `get_links(part_cluster, id, "part_cluster_matches_goods_cluster")` 跨模块到 goods_cluster → 沿 `item_in_cluster`(反向) 到 contract_item 拿价格对比。全部经一个语义层，agent 无需知道底层是 csp_ 还是 cpa_。

---

## 4. 注册表设计（声明式 YAML）

### 4.1 文件布局

```
backend/app/extensions/ontology/
  registry/
    _manifest.yaml          # schema_version + files 清单 + registry_version
    contract_price.yaml     # cpa_ 域: 3 对象类型 + 2 链接
    spare_parts.yaml        # csp_ 域: 4 对象类型 + 3 链接(含自引用)
    bid_quote.yaml          # data_source/dataset(扩展库) + bid/bid_item(data_source 连接)
    cross_module.yaml       # 跨模块链接类型(仅链接)
  registry.py               # loader: YAML -> 类型化模型, mtime+content-hash 热重载, versioning
  connectors/
    __init__.py
    postgres_ext.py         # 直接读扩展库(get_extensions_config().database.url)
    data_source.py          # 解析 data_sources 行 -> connection_config -> 守卫 SELECT
  engine/
    query.py                # get/list/search/aggregate + 链接遍历, keyset 分页
    mapper.py               # 物理行 -> ontology 对象(camelCase, nulls 省略, format/unit 应用)
    filters.py              # typed where-clause 解析 -> SQL
  server.py                 # 统一 ontology MCP server(stdio)
  routers.py                # REST surface(前端语义地图页)
  models.py / schemas.py    # pydantic 响应模型
```

### 4.2 清单（_manifest.yaml）

```yaml
schema_version: 1            # YAML 语法版本, 仅破坏性声明变更时升
registry_version: 7          # 内容哈希变化即递增, describe_ontology + REST 暴露
hot_reload: true             # 逐文件 SHA-256; 变化 -> 原子重载 + version++ + 缓存失效
files:
  - file: contract_price.yaml
  - file: spare_parts.yaml
  - file: bid_quote.yaml
  - file: cross_module.yaml
```

**版本化**：逐文件 SHA-256 为内容指纹（mtime 在挂载环境不可靠，同 config.yaml 签名模式）。`registry_version` 内存单调递增；每对象/链接类型带 `version` int 供 schema 级迁移跟踪。无历史回填——类型是投影，当前 schema 恒适用于活数据。

### 4.3 对象类型声明 schema

```yaml
object_types:
  - api_name: contract_item          # 不可变 snake_case; 用于 URL/REST/MCP 参数
    display_name: 合同分项
    description: 合同价格表抽取的明细行(工程量清单/分部分项/设备清单), 含 v2 溯源与价格校验状态  # 对 LLM 生成查询是承重元数据
    domain: contract_price
    icon: 📄
    enabled: true
    deprecated: false
    access:
      path: postgres_ext            # postgres_ext | data_source
      table: cpa_items
      # path: data_source
      # source_id: bid-quote        # data_sources.name, 解析 connection_config
      # table_name: mock_bid
    pk:
      column: id
      api_name: id
      type: string
      immutable: true
    properties:
      - name: goods_name
        api_name: goodsName
        type: string
        indexed: true
        filterable: true
        searchable: true
        description: 货物/设备名称, 聚类与跨模块连接键
        format: null                # currency | percent | date | text
        unit: null
        enum: null
        hidden: false               # hidden:true 永不透出 agent/MCP(如 connection_config)
    run_source: cpa_run_history      # 溯源提示(对象类型延迟, 此处仅留钩子)
```

### 4.4 链接类型声明 schema

```yaml
link_types:
  - api_name: item_in_document
    display_name: 归属合同扫描件
    source: contract_item
    target: contract_document
    cardinality: N:1
    direction: bidirectional
    reverse: document_has_items
    join:
      type: foreign_key             # foreign_key | normalized_key_match
      source_column: document_id
      target_column: id
    cross_module: false
  - api_name: part_cluster_matches_goods_cluster
    display_name: 备件聚类与货物聚类可比价
    source: part_cluster
    target: goods_cluster
    cardinality: N:N
    direction: bidirectional
    reverse: goods_cluster_matched_by_part_cluster
    join:
      type: normalized_key_match
      expression: "LOWER(BTRIM(csp_clusters.representative_name)) = LOWER(BTRIM(cpa_clusters.representative_name))"
    cross_module: true
```

---

## 5. 对象类型清单（11 个）

| api_name | 背书表 | 访问路径 | 关键语义属性 |
|---|---|---|---|
| `contract_document` | cpa_documents | postgres_ext | contract_no(filterable,跨模块键)、supplier(searchable)、project_name(searchable)、project_location、sign_date、file_hash、parse_status[5]、confirm_status[4]、page_count |
| `contract_item` | cpa_items | postgres_ext | **goods_name**(searchable+filterable,连接键)、spec_model、quantity/unit、unit_price(currency,CNY)、price_untaxed、validation_status[ok/needs_review/corrected]、is_outlier、cluster_id、source_contract_no、confidence + 溯源四件套 |
| `goods_cluster` | cpa_clusters | postgres_ext | **representative_name**(searchable)、category(设备类/材料类/未分类)、status[pending/confirmed/rejected]、stats(jsonb)、item_count、version、confirmed_by |
| `customer` | csp_customers | postgres_ext | **canonical_name**(searchable)、aliases(jsonb)、source[master/imported/ocr]、status[active/pending/merged]、merged_into(自引用) |
| `spare_part_document` | csp_documents | postgres_ext | contract_no(filterable)、customer_id+customer_name(D3 分析维度)、supplier、project_name/location、sign_date、parse_status[5]、confirm_status[4]、file_hash |
| `spare_part_item` | csp_items | postgres_ext | **part_name**(searchable+filterable)、spec、quantity/unit、unit_price(currency)、price_untaxed、customer_id(filterable)、cluster_id、validation_status、is_outlier、source_contract_no + 溯源 |
| `part_cluster` | csp_clusters | postgres_ext | **representative_name**(searchable)、category、status[3]、stats、item_count、version、confirmed_by |
| `data_source` | data_sources | postgres_ext | name(filterable)、type[database/api/file/gis]、status[connected/error/disconnected/testing]、sync_mode、description、**connection_config(hidden:true,含凭据绝不透出)** |
| `dataset` | data_source_datasets | postgres_ext | label(filterable,如 投标总览)、table_name、description、key_columns、**default_query(hidden:true 可选)** |
| `bid` | mock_bid | data_source(bid-quote) | **project_name**(searchable+filterable)、project_location、bid_date、bidder_role[ours/competitor]、bidder_name、won(filterable)、winning_price(currency,CNY) |
| `bid_item` | mock_bid_item | data_source(bid-quote) | **goods_name**(searchable+filterable)、spec、quantity/unit、unit_price(currency)、**self_amount/outsourced_amount/total_amount**(currency,自产→中标/外购→落标故事)、bid_id(连接键) |

> **主键说明**：除 `bid.bid_id`（自然键 `BD-2025-001`）与 `bid_item.id`（serial）外全为 UUID surrogate。Palantir 铁律（主键不可变）已记录；mock_market 是外部 seed 库非我们可控，**一期保留自然键（文档化风险），二期加 surrogate 列**。

---

## 6. 链接类型清单（12 条）

### 6.1 模块内（8 条，FK 确定性）

| api_name | source → target | 基数 | join |
|---|---|---|---|
| `item_in_document` | contract_item → contract_document | N:1 | cpa_items.document_id = cpa_documents.id |
| `item_in_cluster` | contract_item → goods_cluster | N:1 | cpa_items.cluster_id = cpa_clusters.id |
| `spare_item_in_document` | spare_part_item → spare_part_document | N:1 | csp_items.document_id = csp_documents.id |
| `spare_item_in_cluster` | spare_part_item → part_cluster | N:1 | csp_items.cluster_id = csp_clusters.id |
| `document_purchased_by` | spare_part_document → customer | N:1 | csp_documents.customer_id = csp_customers.id |
| `customer_merged_from` | customer(脏) → customer(规范) | N:1 自引用 | csp_customers.merged_into = csp_customers.id |
| `bid_item_of_bid` | bid_item → bid | N:1 | mock_bid_item.bid_id = mock_bid.bid_id |
| `dataset_of_source` | dataset → data_source | N:1 | data_source_datasets.source_id = data_sources.id |

### 6.2 跨模块（4 条，归一化精确匹配，无物理关联表）

| api_name | source ↔ target | 基数 | join 表达式 | 业务价值 |
|---|---|---|---|---|
| `part_cluster_matches_goods_cluster` | part_cluster ↔ goods_cluster | N:N | `LOWER(BTRIM(representative_name))` 相等（**聚类代表名匹配，R3 拍板**） | 备件价 vs 合同价体系比对（④核心价值） |
| `contract_document_matches_spare_document` | spare_part_document ↔ contract_document | N:N | `contract_no` 相等 **或** `file_hash` 相等 | 同一采购事件跨模块关联 |
| `won_bid_contracts_project` | bid(won=true) ↔ contract_document | N:N | `LOWER(BTRIM(project_name))` 相等 且 won=true | 投标→合同链路 |
| `document_supplied_by` | contract_document ↔ spare_part_document | N:N | `LOWER(BTRIM(supplier))` 相等 | 供应商跨模块维度（买方-卖方角色反查） |

> **R3 决策**：跨模块比价链接在**聚类代表名**层匹配，复用模块已做的 DBSCAN 归一（脏 OCR 名经聚类后链接更准），不直接在原始脏名上匹配。item 级导航路径 = `spare_part_item → spare_item_in_cluster → part_cluster → part_cluster_matches_goods_cluster → goods_cluster → item_in_cluster(反向) → contract_item`。
>
> 链接无属性、无关联表（一期）——纯键匹配谓词；反向遍历对同一谓词换向重查（关系型，不建物理链接表）。如需链接置信度/匹配对象元数据，二期建关联表。

---

## 7. 统一 MCP server（`ontology`）

stdio 注册进 `extensions_config.json`（同 data_source mcp.py 模式），7 个工具：

| 工具 | 签名 | 说明 |
|---|---|---|
| `describe_ontology` | `(object_type?: str)` | 返回注册表版本 + 对象类型/链接类型 schema（含属性描述与 allowlist；隐藏 hidden:true；每对象类型属性 allowlist 服务端强制——镜像 AIP "selected types + specific properties"） |
| `list_objects` | `(object_type, filter?, order_by?, limit≤200, cursor?, include_properties?)` | typed filter（eq/ne/gt/gte/lt/lte/in/between/and/or/not）；**keyset 分页**（非 offset）；读后写一致 |
| `get_object` | `(object_type, primary_key, include_properties?)` | 按不可变主键取对象 |
| `search_objects` | `(object_type, term, limit≤200, include_properties?)` | 对该类型 searchable:true 文本属性 ILIKE（goods_name/part_name/representative_name/project_name/supplier/contract_no/canonical_name） |
| `get_links` | `(object_type, primary_key, link_type, limit≤200, cursor?, include_properties?)` | 正向或反向遍历（反向名自动解析到同一 FK/键谓词） |
| `traverse_path` | `(object_type, primary_key, path, limit≤200)` | 点分多跳路径，如 `spare_part_item.spare_item_in_cluster.part_cluster.part_cluster_matches_goods_cluster.goods_cluster.item_in_cluster.contract_item.item_in_document.contract_document`；跨模块链接可参与 |
| `aggregate_objects` | `(object_type, group_by?, metric:{field,fn:count/sum/avg/min/max/percentile_cont(p)}, filter?, limit?)` | **对象集合级批处理**（单查询，绝不 N+1）；价格统计/按客户比价/中标率 |

**输出契约**：属性 camelCase、null 省略、format/unit 应用（currency/percent/date）；响应对象与 Palantir `properties` map 同构。

---

## 8. REST surface（前端语义地图页，~11 端点）

前缀 `/api/extensions/ontology`，扩展 JWT 认证，新权限点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/registry` | 注册表版本 + 逐文件 SHA-256 + 对象/链接清单（页头 + 版本徽章） |
| POST | `/registry/reload` (admin) | 强制重载 YAML（热重载兜底） |
| GET | `/object-types` | 对象类型导航（节点面板） |
| GET | `/object-types/{api_name}` | 全 schema + availability（data_source 背书断开时 available:false） |
| GET | `/link-types` | 链接类型清单（边） |
| GET | `/objects/{type}?filter=&order_by=&limit=&cursor=` | 实例列表（keyset 分页） |
| GET | `/objects/{type}/{pk}` | 对象详情（?expand=links → 链接摘要） |
| GET | `/objects/{type}/{pk}/links/{link_type}` | 链接展开（点击沿边导航） |
| POST | `/objects/traverse` | 多跳路径下钻 |
| GET | `/search?term=&type=&limit=` | 全局语义搜索（跨 searchable 类型） |
| POST | `/aggregate` | 统计组件（聚类均价/按客户比价/中标率） |

---

## 9. 前端语义地图页（应用中心 `/ontology`，独立 app）

- **模块**：新 `src/extensions/ontology/`（仿 dashboard 风格，样式复用 `dashboard.css`）
- **路由**：`/ontology`；`shell/Sidebar.tsx` +1 导航行（唯一外部触点）
- **页面结构**：
  - 左栏：对象类型导航（11 类，图标/描述/可用性徽章/属性计数）
  - 中间：实例列表（typed filter 构建器 + keyset 分页）
  - 右侧：详情面板（属性含单位/枚举/格式 + 链接扩展，点击沿链接跨模块跳转）
  - 顶部：全局语义搜索框
  - 底部：registry_version 版本徽章
- **跨模块演示路径**：点 `part_cluster` → 沿 `part_cluster_matches_goods_cluster` 跳到 `goods_cluster` → 展开 `contract_item` → 到 `contract_document`——全程点击无 SQL
- **权限**：`ontology:view` 页面 + `system:access`；hidden 属性不出现在 schema/响应
- **数据**：TanStack Query（同现有模块）；无 WS 推送，轮询即可

---

## 10. 权限与安全

- **读门控（R3 拍板：管理员级）**：
  - **REST 侧**：所有 `/api/extensions/ontology/*` 请求需 `system:access`（同现有分析模块）；前端页面加 `ontology:view` 权限点（permissions.yaml + canPage）。
  - **MCP 侧**：`ontology` server 注册在 `extensions_config.json`（管理员启用即门控，同 data_source/contract_price MCP 现状——本系统 MCP stdio 子进程无逐调用用户上下文，不重复造鉴权）。敏感属性经 `hidden:true` 服务端强制不外泄。
  - `ontology:read` 权限点预留（二期对象级 ACL 阶段启用）。
- **列级隐藏**：`hidden:true` 属性（`data_source.connection_config` 含凭据、`dataset.default_query` 可选）在 `describe_ontology` / `list_objects` / REST schema / 响应中**绝不出现**。服务端强制，非前端过滤。
- **只读 fail-closed**：连接器复用 `data_source.service.assert_readonly_select`（禁写动词/多语句/SELECT INTO、自动 LIMIT 200、`SET TRANSACTION READ ONLY`）。ontology 模块**零写端点**。
- **背书可用性**：data_source 背书的对象类型在源 disconnected/error 时，`describe_ontology` / REST 返回 `available:false` + 原因，不静默空结果误导 agent。

---

## 11. 数据访问路径与边界

### 11.1 两个连接器

| connector | 背书 | 实现 |
|---|---|---|
| `postgres_ext` | cpa_/csp_/data_sources/data_source_datasets | 直接读扩展库（`get_extensions_config().database.url`），asyncpg/SQLAlchemy 只读 SELECT |
| `data_source` | mock_bid/mock_bid_item | 解析 `data_sources` 行（name=bid-quote）→ connection_config → 连接外部库；每查询过 `assert_readonly_select` |

> 已从探索确认 cpa_/csp_/data_sources/datasets 均在扩展库共享 Base（同一 postgres-ext），**一个 postgres_ext 连接器足够**；实现前仍需现场复核。

### 11.2 与 data_source 的边界（显式契约）

- **data_source = 物理连通 + 只读 SQL 守卫**（连接管理、schema 概览、dataset 罐装查询）。
- **ontology = 业务语义 + 图导航**（对象/链接/属性描述、跨模块遍历、统一查询面）。
- ontology **只把 data_source 当 SQL 读路径复用**，绝不重实现连通性；两个读面并存，但语义各归其位，避免 agent 工具混淆。

---

## 12. 关键设计决策（含 Palantir 借鉴）

1. **纯只读投影层，不建索引/funnel**：直接读 Postgres，读后写一致优于 Palantir 最终一致；零数据拷贝。文档/工具文本**不得**抄 Palantir "no guarantee" 一致性语言。
2. **属性描述是 LLM 精度乘数**（AIP 实证）：对象/属性中文描述为头等公民，服务端强制每类型属性 allowlist。
3. **keyset 分页**：对齐 Palantir V1 万条上限教训，从第一天用 cursor + nextPageToken，不用 offset+count。
4. **跨模块链接 = 聚类代表名归一化精确匹配**（R3）：复用模块 DBSCAN 归一，不做原始脏名匹配；弱链接语义，无物理关联表。
5. **权限 = 管理员级门控 + hidden 列级隐藏**（R3）：一期不镜像行级 ACL（协作/文档域对象二期时再议）。
6. **前端独立应用中心 app**（R3）：/ontology 独立入口。
7. **主键不可变原则**：除 bid 自然键外全 UUID surrogate；业务键（contract_no/goods_name 等）只作链接属性，不作对象身份。
8. **聚合批处理**：`aggregate_objects` 对象集合级单查询，绝不做逐对象 N+1。
9. **热重载 + 版本化**：SHA-256 内容指纹 + registry_version，同 config.yaml/extensions_config.json 模式。
10. **YAML/seed 治理**：注册表当代码管（versioned、可评审），避免领域语义在配置行里漂移。

---

## 13. 平台支撑评估（回答"是否支撑企业智能化应用平台"）

### 结论：**支撑，且是最高杠杆的一步**

把 Ontology 概念移植为统一语义层，是让 eai-flow 从"自建模型、访问面分裂、表中心"的模块集合，转为**连贯的企业智能化应用平台**的单一最高杠杆动作——前提是做成现有表之上的薄投影注册表（不建索引/funnel）、读侧先行、与 data_source 边界显式固化。

| 维度 | 评估 |
|---|---|
| **平台一致性** | 强正向：3 套物理 schema → 一个业务图；跨模块键从"字符串提示"变"一等链接类型"；**元数据覆盖式，任何模块不用迁移自己的表** |
| **Agent 能力** | 高：把"agent 对未知 schema 手写 SQL"变"选带描述的業務对象 → 按描述属性过滤 → 沿描述链接遍历"（AIP 机制）；**逐字命中"能力经 MCP 到达 agent"铁律** |
| **治理与演进** | 互补：现有 yaml data_scopes = 行级 ACL 原生宿主；hidden = 列级可见性；**Action（受治理写路径）是未来大奖**，只作新对象前向路径，不 retro-fix 现有 skill 直写 |
| **成本与风险** | 有界：新独立模块 + 一个 MCP + 一个 REST + 一个前端页；主风险 = data_source 边界重叠、注册表腐化、脏跨模块键、ACL fail-closed |
| **vs 纯 data_source** | data_source = "数据访问平台"（必要基建）；ontology = 把表访问升格为"带治理行为的业务模型"——**这正是"企业智能应用平台"与"数据访问平台"的区别**；互补非竞争 |

---

## 14. 风险与未决项

- **【实现前必须验证】cpa_/csp_/data_sources/datasets 是否同一扩展库**（探索结论是共享 Base，需现场复核；若分库则 postgres_ext 连接器需按类型分库）。
- **data_source 边界重叠**：无显式契约会产生两个竞争读面 → §11.2 契约 + 实现期 enforce（ontology 只复用其 SQL 读路径）。
- **注册表腐化**：描述/链接随模块演进过期 → 语义地图变"ontology theater"反误导 LLM → 实现期加 `describe_ontology` 覆盖度检查（描述/链接覆盖 %）+ 评审关卡。
- **脏跨模块键**：goods_name/part_name、supplier/customer 不能硬 FK → 聚类代表名 + 弱链接语义；`won_bid_contracts_project` 依赖 project_name 归一，脏名会错失链接（记录为已知局限）。
- **新读面安全**：hidden 与只读守卫必须服务端 fail-closed（同 `assert_readonly_select` 纪律），防 MCP 适配器绕过。
- **bid 自然键**：一期保留 `BD-2025-001`（文档化风险），二期加 surrogate。
- **percentiles 可用性**：`aggregate_objects` 的 `percentile_cont` 需在两条访问路径（扩展库 vs data_source 外部库）验证可用。
- **MCP 注册键**：`extensions_config.json` 的 stdio 注册键名需实现期确认（同 data_source 模式）。

---

## 15. 成功标准

1. **跨模块问答零手写 SQL**：Agent 能经 ontology 导航端到端回答"某客户备件 X 的价格 vs 合同价格体系市场均价"（走聚类代表名链接），不写一行 SQL。
2. **非工程师看得见图**：语义地图页直观展示模块间业务图，点击跨模块跳转可用。
3. **平台一致性可感知**：`describe_ontology` 一次返回市场/分析域完整业务 schema（11 对象 + 12 链接），agent 无需读各模块 models.py。

---

## 16. 决策日志

- **2026-08-14** 意图 = **概念移植**（非产品采购/非纯文档评估）。
- **2026-08-14** 一期价值 = 统一语义层（平台一致性）；Action/函数/对象 ACL 全部延后。
- **2026-08-14** 覆盖域 = 市场/分析数据域（cpa_/csp_/bid）；协作/文档域二期。
- **2026-08-14** 方案 = **声明式 YAML 注册表 + 通用引擎**（方案 A），弃代码驱动（B）与纯文档（C）。
- **2026-08-14** 跨模块链接 = **聚类代表名匹配**（R3）；不做原始脏名匹配、不做模糊匹配。
- **2026-08-14** 权限 = **管理员级门控**（system:access + hidden 列级隐藏）；不行级 ACL（二期协作域再议）。
- **2026-08-14** 前端 = **独立应用中心 app /ontology**；Sidebar +1 导航行。
- **2026-08-14** bid 自然键一期保留（文档化风险），surrogate 二期；run_history 延迟二期；aggregate 实时计算。

---

## 17. 参考文件（实现时照此）

- **Palantir Ontology 权威技术面**：workflow 研究输出（2026-08-14）——对象存储 V2 API / Action 参数与校验 / 函数集合批处理 / 双层权限模型 / AIP ontology 工具；`minimal_portable_set` 与 `mapping_notes` 为设计依据。
- `backend/app/extensions/contract_price/models.py`（cpa_ 表结构，工作区现状）
- `backend/app/extensions/spare_parts/models.py`（csp_ 表结构 + csp_customers）
- `backend/scripts/seed_mock_market.py`（mock_bid/mock_bid_item + 4 datasets）
- `backend/app/extensions/data_source/{mcp,service,routers}.py`（只读查询 + dataset + 守卫；**ontology 复用其 SQL 读路径，不改**）
- `backend/app/extensions/database.py`（共享 Base；ontology 不建业务表，仅元数据可选）
- `config/permissions.yaml` + `config/roles_custom.yaml`（权限点与角色；ontology 新增 `ontology:read`/`ontology:view`）
- `extensions_config.json`（注册 `ontology` MCP server + 技能）
- `frontend/src/extensions/dashboard/dashboard.css`（语义地图页样式复用）
- `docs/superpowers/specs/2026-08-13-market-analysis-modules-design.md`（市场分析四模块设计稿，数据层现状母稿）
