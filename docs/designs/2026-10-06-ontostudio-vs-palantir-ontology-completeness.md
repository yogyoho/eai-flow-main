# OntoStudio 对照 Palantir 操作本体框架的完备性评估

- 日期：2026-10-06
- 方法：以《Palantir 本体实操指南：从零建一套能推理的本体》（2026-09-23）的五构件+八工程项框架逐项对照，证据全部来自当时代码实况（grep 实证 + 本会话已核验事实）
- 关联：前次完备性判定 docs/designs/2026-10-05-ontostudio-capability-matrix.md（结论一致：缺动力学层）；本次为外部框架视角的复检

## 总判定

**骨架完备度：高（五构件 4.5/5，八工程项 6.5/8）。** OntoStudio 走的正是该文推崇的「场景优先、最小闭环」路线（单域 eia 闭环、多域刻意缓行且 TODOS 在册）。实质缺口集中在五处：**Function 构件、Action 幂等/版本、属性级权限、registry 回滚 UI、OWL 公理级形式化**——多数是有意识的缓行（触发条件驱动），非无意识遗漏。

## 一、五大构件对照

| 构件 | 文章要求 | OntoStudio 现状（证据锚点） | 判定 |
|---|---|---|---|
| Object Type 对象类型 | 类型≠实例；场景内 1-2 个核心 | registry yaml 声明式建模；建模器可视化+YAML 双模式编辑闭环（draftText 单一草稿→校验→fingerprint 乐观并发保存）；单域 eia 刻意缓行多域（TODOS「抽取管线多域化」+「多域接入四步清单」） | ✅ 完备 |
| Property 属性 | 三层：业务/治理/技术元数据，治理层不能省 | 业务=attrs JSON+typed 声明列（filterable/searchable）；治理=created_at/updated_at/extracted_by/thread_id/document_id（doc_graph.yaml 全量在册）；技术=uuid pk+hidden 列永不透出 | ✅ 完备 |
| Link Type 关系类型 | 方向/基数/关系属性；弱关联记待评估不断言无价值 | link_types 带 source/target/cardinality/reverse/join（doc_graph.yaml 4 条 N:1）；关系带 attrs；跨域弱链=enabled:false stub 并写明原因——正是「记待评估」的形态（TODOS 跨域四链路） | ✅ 完备 |
| Action Type 动作类型 | 九要素至少五项：输入/前置/副作用/权限/审计 | 有：输入(action_id+pk+params)、前置(preconditions)、副作用(postconditions，含 confirm 置信升格 0.7)、权限(required_permissions+scope_resource 实例级)、审计(dg_action_audit before/after 同事务)、事务边界(executor 单条管线)。缺：**幂等键**（actions 层 grep 零命中）、**动作版本/废弃策略**（grep 零命中） | ⚠️ 5/7 |
| Function 函数 | 计算和规则独立于写动作（分级/路由/SLA 类） | **无独立 Function 构件**。规则引擎部分替代：evaluate_rules 前向链（现算现返带触发轨迹）+ CONSTRUCT 派生（per-rule named graph）+ 属性链/传递公理（prp-spo2、located_in）。但「纯计算函数」（告警分级/工单路由/SLA 剩余时间类）无声明式承载 | ⚠️ 部分替代 |

## 二、八项工程补项对照

| # | 补项 | OntoStudio 现状 | 判定 |
|---|---|---|---|
| 1 | 数据映射 | access.path/table 逐表声明（postgres_ext dg_*）；tables.py 逐列核对；全量装载=对账（degraded 自愈执行者） | ✅ |
| 2 | 身份解析 | 消解审核 merge/unmerge + norm_name 归一化 + dg_merges 留痕可撤销 + 低置信自动进复核队列 | ✅ |
| 3 | 命名规范 | 国标 C1：IRI=ns+id/uuid 机械可逆；C5：域命名空间唯一且非 W3C 保留；建模器保存即校验 | ✅ |
| 4 | 版本治理 | registry_version 递增 + SHA 热重载 + fingerprint 乐观并发（409 冲突保护）；缺 registry **回滚 UI**（TODOS B4：yaml 在 git 有历史，现需手工 revert）、缺 Action 版本 | ⚠️ 半 |
| 5 | 权限安全 | 动作级 required_permissions + 对象级 scope_resource（ABAC deny 扣减、超管旁路两侧一致）+ B1 消解审核权限点；缺**属性级权限**（文章要求对象/属性/动作三级） | ⚠️ 半 |
| 6 | 审计血缘 | **强项**：dg_action_audit before/after JSONB 同事务 + mention 证据链永不删（quote 逐字原文）+ query_analogy 每条带 source_report | ✅✅ |
| 7 | 数据质量 | SHACL 全图（pyshacl，重操作仅按钮触发）+ 12 条业务规则 + 数据治理面板（内核孤儿/零边 mention）+ 置信度门 0.7 + force_review 人审闸门 | ✅ |
| 8 | 推理约束 | SHACL 形状（基数/必需/值域）+ 应用层 fail-closed 校验（域枚举/谓词角色对）；OWL 公理级形式化（不相交等）**为空**——国标页诚实声明，非隐蔽缺口 | ⚠️ 半 |

## 三、OntoStudio 有而该框架没有的

1. **双层推理并存**：文章开篇把「操作本体（Palantir）」与「语义本体（OWL）」对立二选一——OntoStudio 两层都做了：Palantir 式动作闭环（registry 动作+审计+范围）叠加 owlrl 闭包（graph:entailment）与 CONSTRUCT 派生（graph:derived:*）
2. **国标符合性资产**：GB/T 48000.3—2026 C1-C5 自动化套件 + 校验中心消费（框架无此维度，评审场景的差异化能力）
3. **Agent 原生消费面**：MCP 双服务 17+5 工具 + ontology-graph-query / doc-graph-extract 读写分层技能（2026-10-05 实测闭环）
4. **证据链一等公民**：mention 永不删 + 原文逐字引用，比文章「审计血缘」条目更硬——驳回/合并后溯源依据仍在

## 四、实质缺口清单（按补课时机排序）

| # | 缺口 | 补课建议 | 时机判定 |
|---|---|---|---|
| 1 | Function 独立构件（声明式纯计算） | 接入告警分级/路由类业务时建声明式函数层，规则引擎可承接派生类但承接不了「参数→数值」计算 | 等场景触发；与 2026-09-22 完备性判定「缺动力学层」结论一致 |
| 2 | Action 幂等键 | 下一批动作扩员（relation 审批通道，TODOS 在册）时一并定契约 | 当前仅 2 个动作，实害低 |
| 3 | Action 版本/废弃策略 | 同上批次 | 动作数 <5，YAGNI |
| 4 | 属性级权限 | 与 B1 审阅角色授权多人化同批设计（role-management yaml 驱动对齐） | 多人化+合规审计要求出现时 |
| 5 | registry 回滚 UI | TODOS B4 在册 | yaml 在 git，手工 revert 够用 |
| 6 | OWL 公理级形式化 | 已在国标页诚实声明为空 | SHACL+应用层校验兜底；国标 C1-C5 口径已站得住 |

另有两条**非建模缺口**（框架外但影响「操作本体」成色）：跨域四链路数据未补齐（3×NO_DATA+匹配率 0.0%，TODOS 在册，数据问题非代码）；审阅角色多人化授权（B1 TODOS，单人阶段低危）。

## 五、结论

对照 Palantir 操作本体标准，OntoStudio **不是「不完备」，而是完备于骨架、刻意欠配了三个尚无场景的构件**（Function/幂等/版本）——这正是文章批评的「大而全自杀式建模」的反面，方法论同源。真要挑实质短板：**属性级权限**（多人化前补）与**跨域链路数据**（补数据非补代码）。

下一步若扩动作面（relation 审批），将 #2/#3（幂等+版本契约）与 #4（属性级权限）并入同一批设计，一次把 Action 九要素补齐到文章全格。
