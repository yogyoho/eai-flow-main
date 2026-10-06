# MCP 工具总表

> 对齐：`backend/app/ontology/mcp.py` + `backend/app/doc_graph/mcp.py` @ 2026-10-06
> ⚠️ 下方表格由 `scripts/gen_reference_tables.py` 代码生成，勿手改；工具增删后重跑该脚本。

OntoStudio 向 EAI 系统 Agent 暴露两组 MCP 服务（streamable-http，注册于主系统 `extensions_config.json`）：

- **ontology**（`/mcp/ontology`，只读，17 工具）：语义层查询与推理——对象导航、全文搜索、多跳遍历、聚合、推理物化、规则违规、写作上下文、类比素材、C 库沉淀管线。
- **doc-graph**（`/mcp/doc-graph`，写侧，5 工具）：文档图谱构建——抽取入库、待审清单、实体合并/撤销、规则前向链推理。

调用纪律（与主系统 `ontology-graph-query` 技能一致）：

1. **先 `describe_ontology` 再查询**——对象类型与链接以运行时输出为准，不要凭记忆硬编码。
2. 工具名在 Agent 侧带服务名前缀（如 `ontology_list_objects`）；主系统开启工具延迟加载时，需先经 `tool_search` 晋升 schema 才能调用（首次约 3-4 次晋升开销）。
3. 读写分工：查询走 ontology 只读服务；抽取入库/合并/规则计算走 doc-graph 写服务。组合用法见 [Agent 集成指南](./agent-integration)。

<!-- GENERATED:MCP-TOOLS BEGIN -->
| 工具 | 侧 | 用途 | 关键参数 |
|---|---|---|---|
| `describe_ontology` | 读 | 查看本体语义地图：对象类型(名称+一行描述)、链接(含 enabled:false stub 及原因)。紧凑默认；full=true 输出完整属性/列映射。先看这个再查询。 | — |
| `list_objects` | 读 | 按对象类型列出实例：typed filter（声明列+eq/ne/gt/gte/lt/lte）、q 全文搜索、keyset 分页(next_cursor)、排序。跨模块导航入口。 | object_type |
| `get_object` | 读 | 取单个对象实例（按主键）。字段名用 api_name(camelCase)，hidden 列永不透出。 | object_type, pk |
| `search_objects` | 读 | 全文搜索某对象类型（q 命中 searchable 列，ILIKE 绑定参数）。是 list_objects q 参数的便捷封装。 | object_type, q |
| `get_links` | 读 | 取某实例沿一条链接的对侧行（如合同条目→所属货物簇）。enabled:false 的 stub 链接会被拒绝并给原因。 | object_type, pk, link_type |
| `traverse` | 读 | 多跳遍历（≤5 跳）：如 ['item_in_cluster','part_cluster_matches_goods_cluster'] 回答'这批备件对应哪些合同条目'。每跳 fan-out ≤200。 | object_type, pk, steps |
| `aggregate` | 读 | 按声明列分组聚合（count/sum/avg/min/max；sum/avg/min/max 需 metric_column 数值列）。如按货物簇统计合同金额。 | object_type, group_by |
| `ontology_reason` | 读 | 运行形式化推理：schema 重编→OWL 2 RL 闭包(graph:entailment)→CONSTRUCT 派生(graph:derived:*)。返回输入/物化三元组数与各规则派生计数（置信度门默认 0.7）。 | — |
| `invoke_action` | 读 | 执行一个已声明的受治理动作（写回业务数据并记审计）。先用 describe_ontology 查看可用 action_id 清单与参数。写路径在服务端（事务/审计/身份标注）；本通道的授权在 MCP 配置层，不逐条校验动作声明的 required_permissions。 | action_id, pk |
| `review_entity` | 读 | 审核抽取实体的快捷入口（高频动作的具名包装，内部走同一条动作执行体）。decision=confirm 置 active，reject 置 rejected。 | pk, decision |
| `query_entity` | 读 | 按名称/实体类型查询环评（EIA）图实体并带邻域关系（出/入边+对端名）。写作取材与跨章节核对入口。etype 如 waste_stream/sensitive_point/emission_point；name 支持子串；scope 按图谱归属库过滤（样例素材/项目工作本/领域共性）。 | — |
| `check_consistency` | 读 | 对 EIA 图全量跑 12 条校验规则（矸石闭合/敏感点防护/监测覆盖/限值适配等），返回各规则违规计数+样例消息+分级汇总；scope 可把体检限定在某个归属库（涉事节点后置过滤）。报告出稿前体检用。 | — |
| `get_writing_context` | 读 | 取某实体的写作上下文：实体+邻域关系+关联阈值/条款/标准等约束实体的 attrs。写章节前注入核心，防跨章节数据打架。chapter 模式（子项目 4）：按章节关键词返回主题过滤的 B 库规律（domain_pattern）+ C 库项目实体，供每节开写前注入。 | — |
| `get_rule_violations` | 读 | 取校验规则违规清单（完整变量绑定+message）。可按 severity=error\|warn\|info 或 rule_id 过滤；只返回有违规的规则。 | — |
| `query_analogy` | 读 | 类比素材与领域规律查询（A 库样例 scope=sample + B 库领域共性 scope=domain_common；C 库 project 不入本通道，走 query_entity scope=project）：查实体+邻接关系，每条必带 source_report 可溯源到来源报告。etype=domain_pattern 查 B 库蒸馏规律条目（attrs 含 pattern_type/subject_name/object_name/support_count）。etype 或 label_contains 至少给一个。类比值引用须在写作侧标注 param_source=analog_mine+来源报告（纪律在技能侧）。 | — |
| `ingest_project_forms` | 读 | C 库沉淀写入：门 1 数据齐套后把整份 stage JSON 的 forms 对象经声明式映射写进项目工作本（dg_*，scope=project + project_id）并投影装载进图。返回实体/关系计数 + unmapped_families（未映射族清单——汇报不阻塞，按 spec 恒不 fail）。stage JSON 唯一写者纪律不变：本工具是图侧投影消费者，不回写 stage JSON。 | project_id, forms |
| `check_project_coverage` | 读 | 门 1「图上齐套」检查：对照映射表必填族，报告本项目 C 库（scope=project + project_id）实体覆盖度与缺失族清单——替代旧的 JSON 文件在场检查。coverage_complete=false 时按缺失族回技能侧补数。 | project_id |
| `ingest_extraction` | 写 | 把抽取出的投标实体/关系/证据入库（幂等：同名实体归并）。payload 须严格符合投标域抽取 schema（extra 字段会被拒绝）。 | domain, entities |
| `list_pending_review` | 写 | 列出低置信度待复核实体（status=pending_review），可请用户确认后用 merge_entities 合并。 | — |
| `merge_entities` | 写 | 把候选实体合并进规范实体（candidate 置 merged + dg_merges 留痕，可撤销）。 | candidate_id, canonical_id |
| `unmerge` | 写 | 撤销一次合并（删留痕行，candidate 置回 active）。 | merge_id |
| `evaluate_rules` | 写 | 在真库图数据上跑注册规则的前向链推理（现算现返，零落库）。domain 选择事实域（eia=环评样例）。返回派生事实、每条规则的触发轨迹（哪些源事实触发了哪条规则）与统计；max_derived_reached/max_rule_fires_reached/max_iterations_reached=true 表示到达推理工作预算（不必然截断）。 | domain |
<!-- GENERATED:MCP-TOOLS END -->
