# eia 域术语（环评）

域命名空间下的实体类型（etype 枚举与 registry `eia.yaml` 严格同名）：

## 文档结构类

| etype | 术语 | 含义 |
|---|---|---|
| `report` | 报告 | 环评报告根实体 |
| `chapter` / `section` | 章 / 节 | 报告章节结构（`has_chapter` / `has_subsection` 组织） |
| `section_element` | 节内要素 | 小节内的结构化要素 |

## 治理合规链

链形：**源 → 治理措施 → 标准 → 监测**

| etype | 术语 | 含义 |
|---|---|---|
| `pollution_source` / `mine` | 污染源 / 矿井 | 排放与影响来源（烟气、废水、矿井水等） |
| `treatment_measure` | 治理措施 | 脱硫塔、污水处理站、除尘器等（`treated_by` 关联） |
| `emission_standard` / `standard` | 排放标准 / 标准 | GB/HJ/DB 标准实体（由标准号正则抽取） |
| `standard_threshold` | 标准阈值 | 污染物 + 限值符 + 数值 + 单位（`has_limit` 关联） |
| `monitoring` | 监测 | 监测计划/在线监测要求（`monitored_by` 关联） |

## 影响链

链形：**源 → 污染物 → 敏感点**

| etype | 术语 | 含义 |
|---|---|---|
| `pollutant` | 污染物 | SO2、NOx、颗粒物、COD 等 |
| `sensitive_point` | 敏感点 | 保护区、水源地、村庄、河流等受影响对象（`threatens` / `impact_to` 关联） |
| `place` | 地点 | 地理位置实体（`located_in`，传递公理生效） |

## 法规与佐证

| etype | 术语 | 含义 |
|---|---|---|
| `regulation_clause` | 法规条款 | 《法名》第 X 条（`cites_clause` / `regulated_by` 关联） |
| `evidence_requirement` | 佐证需求 | 报告中要求提供的表/图/公式/附件 |
| `evidence_artifact` | 佐证材料 | 实际附上的佐证（`evidenced_by` 关联） |

## 组织与活动

| etype | 术语 | 含义 |
|---|---|---|
| `org` | 组织 | 建设单位/编制单位等（`org_compiles_project` 等关联） |
| `project` / `activity` | 项目 / 活动 | 建设项目与其活动 |
| `logic_node` | 逻辑节点 | 上下文逻辑链条目 |

## 核心谓词

| 谓词 | 含义 | 备注 |
|---|---|---|
| `monitored_by` | 受监测于 | 治理合规链首环 |
| `has_limit` | 有限值 | 指向标准阈值 |
| `governed_by` | 受治理于 | 措施→标准 |
| `covered_by_standard` | 被标准覆盖 | **属性链推导**：`monitored_by ∘ has_limit ⇒ covered_by_standard`（prp-spo2），非直接抽取 |

::: tip 状态与确认
eia 域实体同样走状态机：抽取后 `pending_review`，在**消解审核**确认后翻转为 `active`——确认即落图，推理立即可见。驳回翻转为 `rejected`（保留不删）。
:::
