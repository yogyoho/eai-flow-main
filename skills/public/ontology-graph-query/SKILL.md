---
name: ontology-graph-query
description: 查询与消费本体知识图谱（OntoStudio graph_entity 实体图谱 / 环评 EIA 域 / 市场域语义层）。当用户要求"查图谱 / 图谱里有哪些实体 / 实体关系梳理 / 环评敏感点·矸石·矿井水查询 / 报告取材用图谱事实 / 类比素材 / 图谱合规体检 / 校验规则违规"时使用。文档抽取入库走 doc-graph-extract 技能；纯文档问答不需要本技能。
---

# ontology 图谱查询与消费

经 ontology MCP（只读）查询 OntoStudio 知识图谱。写侧（抽取入库/合并）见 doc-graph-extract 技能。

## 第一步永远是 describe_ontology

先调 `describe_ontology` 拿语义地图（对象类型+链接清单），再选工具——对象类型名以 describe 输出为准，不要凭记忆硬编码。

## 工具选型

| 要回答的问题 | 工具 | 要点 |
|---|---|---|
| 图上有什么类型/链接 | `describe_ontology` | full=true 看属性与列映射 |
| 按类型列实体（可过滤/排序/分页） | `list_objects` | object_type 必填；filters 用声明列 |
| 关键词搜实体 | `search_objects` | list_objects 的 q 便捷封装 |
| 单实体完整字段 | `get_object` | pk 用主键 uuid |
| 沿一条关系找对端 | `get_links` | 单跳；stub 链接（enabled:false）会被拒绝 |
| 多跳路径（≤5 跳） | `traverse` | steps 传链接名数组，每跳 fan-out ≤200 |
| 分组统计 | `aggregate` | sum/avg 需 metric_column 数值列 |

## EIA 写作消费通道（环评域专用）

| 场景 | 工具 | 要点 |
|---|---|---|
| 按名称/类型查实体+邻域关系 | `query_entity` | 写作取材与跨章节核对入口；name/etype 至少给一个 |
| 类比素材与领域规律 | `query_analogy` | A 库样例+B 库规律（domain_pattern）；每条带 source_report 溯源 |
| 章节写作上下文 | `get_writing_context` | entity_name 或 chapter 关键词（如 矸石/矿井水）；开写前注入防跨章打架 |
| 出稿前全量体检 | `check_consistency` | 12 条规则（矸石闭合/敏感点防护/监测覆盖/限值适配） |
| 违规明细清单 | `get_rule_violations` | 按 severity/rule_id 过滤，拿完整变量绑定 |

## EIA 三库 scope 概念

环评图谱按归属分三库，选对 scope 才不查错池子：

- **sample（A 库样例素材）**：历史样例报告抽取产物——类比引用的来源
- **domain_common（B 库领域共性）**：跨项目蒸馏规律（etype=domain_pattern）
- **project（C 库项目工作本）**：当前项目实体——报告正文的取材池

类比值引用须在写作侧标注来源报告（param_source=analog 类 + source_report），不得把 A/B 库素材冒充项目数据。

## 纪律与坑

- **查不到 ≠ 不存在**：抽取入库默认 force_review=true，未经消解审核确认的实体不投影进图。用户问"刚抽的怎么查不到"→ 引导去消解审核页确认，不要重抽。
- **跨域链接可能为空**：cross_module 四链路数据未补齐前，get_links/traverse 跨域部分返回空或拒绝——如实告知是数据缺口，不是工具坏了。
- **本技能只读**：审核确认（review_entity/invoke_action）属写路径，仅在用户明确要求且确认对象清单时使用；批量写与抽取走 doc-graph-extract。
- 引用图谱事实给用户时附实体名与关键属性，可溯源（mention/source_report）。

## 示例问法

- "图谱里有哪些敏感点？它们的防护距离合规吗" → query_entity(sensitive_point) + check_consistency
- "矸石相关章节的开写上下文" → get_writing_context(chapter=矸石)
- "找与本项目矿井水处理类似的样例做法" → query_analogy(etype=…) 取 A 库
- "这批实体按类型统计" → aggregate(graph_entity, group_by=etype)
