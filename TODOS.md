# TODOS

## TODO: self-improving 自进化循环 P2 升级路径（三条件触发项）

- **What:** P1（extensions/learnings）验收且价值验证后可做的三项升级：① 独立 poller 容器做实时 sweep（替代 lazy catch-up，参照 dcs_qa cron-poll 模式）；② 人工 triage UI（届时才需 gateway app.py 一行 include_router + /api/extensions/learnings 路由）；③ 零触碰约束解除后（如上游大版本重排后），把 pending 计数注入系统提示（prompt.py，OV5 的 C 选项，约束内最优解的升级路径）。
- **Why:** 三项都有明确前置条件，现在做是过早优化；但约束/条件变化时（上游大版本、P1 数据证明价值）需要有人记得这条升级路径存在。
- **Pros:** 升级路径不失忆；每项独立小批次互不阻塞。
- **Cons:** TODO 面板多一条；前置条件判断需要人。
- **Context:** 设计文档 docs/designs/self-improving-loop-port.md P2 章节 + 2026-09-12 eng-review OV5/OV6 决议 + 2026-09-13 D16 决议（不提前建管理页，触发条件驱动）。**triage 页四条扳机（任一命中即开工，最小范围=列表/过滤(pattern_key,status)/resolve/dismiss/晋升确认/CSV导出 + 权限分层[用户看自己、管理员看全部]，~3-4人日）：①错误晋升事故——用户溯源 agent 异常行为到某条晋升规则，需逐条否决界面；②pending 积压超出 agent 自 triage 能力；③企业客户合规审计要求（学习数据含客户环境错误摘录，数据安全法场景，需审计/导出/删除权）；④多租户运营需要跨用户健康度视图（dismissed-ratio/捕获量）。另两项触发：lazy sweep 延迟被实测抱怨（poller）；harness 零触碰约束解除（系统提示注入，OV5-C）。**
- **Depends on / blocked by:** P1 落地 + Success Criteria (P1) 全绿。

## TODO: snapshot.py 多副本同步维护约定（四副本）

- **What:** snapshot.py 现存四份副本（water-drainage / bid-proposal-writing / geological-report / coal-eia-report，2026-09-06 coal-eia v2 D5 定案扩员）——任一副本修 bug 时必须检查另三副本是否存在同缺陷并同步修复。coal-eia 副本额外携带 mapping.json 枚举与版本指纹/漂移报告（eng-review OV#8），这两个增强若验证有效应反向移植回前三副本。
- **Why:** 2026-08-20 eng review 3A 决策接受第三份副本（技能=自包含分发单元，兄弟技能不互相 import），代价是修复不自动传播。bug-2198（正典文件名守卫）/bug-2200（show 显式 --input）类缺陷大概率三副本同在。
- **Pros:** 一条约定防静默漂移，成本近零。
- **Cons:** TODO 面板多一项；修复 bug 时多一步检查。
- **Context:** water 版 168 行 stdlib 为正典源。geological-report 副本将额外携带 SHA-256 状态哈希清单（2B）与目录扫描差集报警——这两个增强若验证有效，应反向移植回 water/bid 两副本。发现新缺陷时先查 water 版是否已有修复。
- **Depends on / blocked by:** 无。

## TODO: 技能多副本脚本族扩员同步约定（snapshot → progress/calibrate/bank_compile）

- **What:** bid-proposal-writing v4（设计 docs/designs/bid-proposal-writing-v4-volume-architecture.md，eng-review 1A 定案 2026-09-05）照搬 geological-report 的 progress.py / calibrate.py / bank_compile.py 后，多副本脚本族从 1 种（snapshot）扩到 4 种；2026-09-06 coal-eia-report v2（设计 docs/designs/coal-eia-report-v2.md）再引入 progress / consistency / build_output / chapter_planner / formula_runner 的 geo 副本——族扩到 9 种脚本 × 2-4 副本。**coal-eia 版是演进分叉起点而非纯复制**（两层模型改造：progress 节子表+批量记账、build_output 序无关目录门+节级归因、chapter_planner uses+deps 节级反查、consistency 条件激活、formula_runner 5 域 Decimal 重写）——geo↔coal-eia 间禁盲目互抄，geo 侧 bugfix 须人工判断是否适用于分叉版；water/bid/geo 三者间仍为同构同步。
- **Why:** 副本漂移已实证：snapshot.py geo 196 行 vs bid 190 行（6 行分叉）。geo D7 决策（技能=自包含分发单元，兄弟技能不互 import）使修复不自动传播；副本族每扩一种，同步检查成本线性上涨。
- **Pros:** 延续自包含分发纪律，无架构改动；一条约定防新副本静默漂移。
- **Cons:** 修 bug 检查面从 3 副本扩到 4 脚本 × 2-3 副本；未来若再照搬（如深度门变体）需继续扩此条目。
- **Context:** 2026-09-05 bid v4 eng-review 用户拍板 1A（照搬+TODOS 扩条目，否决公共库提取与精简裁剪）。若某副本缺陷反复出现 ≥2 次，重新考虑公共库提取（geo D7 否决记录在 admin-main-dev-fork-design-20260820-geological-report-v2.md D7）。
- **Depends on / blocked by:** bid v4 WP-2.1 开工（progress.py 落地时本条目即生效）。

## TODO: 普查/详查阶段模板实质填充 + 阶段参数化机制

- **What:** 勘探版管线验证稳定后，把 v1 附录A/B 模板按 exploration.json 同构升级为 survey.json / detail.json（每章 key_elements/writing_patterns/tables/std_refs + 表单族 + 公式链 + 合约集），并定义阶段切换机制——表单清单/确认门/合约集按 stage 参数化。
- **Why:** D2 决策只迁移 v1 内容套框架，实质填充无排期则永远不发生。2026-08-20 outside voice #9 指出：阶段参数化机制完全未定义，survey.json/detail.json 会引用这些阶段不存在的章节与工件（表8-2、五因素系数、勘查类型等勘探硬编码）。
- **Pros:** 三阶段全覆盖，扩展有既定路径。
- **Cons:** 依赖勘探版验证，短期不动；提前做会在管线变化时返工。
- **Context:** v1 附录A/B 模板已在本次迁移范围（references/stages/ 轻量占位）。阶段参数化的自然落点：SKILL.md 入口按 stage 选 stages/{stage}.json，表单清单/门/合约集全部从该文件驱动。
- **Depends on / blocked by:** 勘探版管线验证通过（SC-1~6 全绿）。

## TODO: CC1 特高品位倍数条款人工核实（线程 296611de 交付物 snapshot 前置）

- **What:** standards_index.json 尚无 DZ/T 0214-2020「特高品位剔除倍数」条款的机读文本——CC1 一致性合约保持 MANUAL（run-stage finalize rc=2 停门语义，snapshot 未落）。待地质专家对照 DZ/T 0214-2020 原文核实本项目工业指标 `outlier_multiple=2` 是否在铜矿档内（如 2~3 倍档）；确认后在 standards_index.json 的 DZ/T 0214-2020 条目补 text 字段（供 `check_cc` 正则解析「特高品位…N–M 倍」）并重跑 `progress.py run-stage finalize` 落 project_snapshot.json。
- **Why:** 2026-09-01 返修交付（线程 296611de）终验 fail=0，唯余此项 MANUAL；用户裁定暂不核实、未来找专家确认后修改完善（GB/HG 条款不采信 web_search 为既定红线）。
- **Context:** 线程 296611de-448f-44b8-bdcd-f75921364b2e；交付物+delivery_manifest 已落盘线程 outputs/；consistency pass 28 / warn 19 / manual 1 / fail 0。修复入口：改 `skills/public/geological-report/references/standards_index.json` → 重跑 finalize（容器双路径已同步同版脚本）。
- **Depends on / blocked by:** 专家人工核实 DZ/T 0214-2020 原文条款。

## TODO: 平台减负两处 + 凭据作废后 docmgr 旧副本回收（bid v4 评审延期项）

- **What:** ① collab-server `onStoreDocument` 每次 `Y.encodeStateAsUpdate` 全量落库两份、collab_updates 只增不清（`backend/collab-server/src/persistence.ts:33-44`）——增量化需同步重定义审计/恢复语义；② 编辑器 O(N) 全文序列化热点（1.5s 防抖保存全文 `blocksToMarkdownLossy` `PersonalBlockNoteEditor.tsx:424-531` + AI 面板 `documentContent` 写在 render `BlockNoteEditor.tsx:856-858`）；③ 交付凭据作废/重 build 清场后，已同步的 docmgr AIDocument 旧册行残留（项目文档空间互相可见），需按最新 manifest 的回收策略。
- **Why:** bid v4 分册架构落地后 BlockNote/协作不再是篇幅瓶颈（每册 ≤50 页），三项均降级为平台健康债；但长文档场景（非标书）仍会踩中，且 collab_updates 无限增长是存储隐患。2026-09-05 bid v4 eng-review C4 定案移出本期，外部声音 13A 增补副本回收。
- **Pros:** 三项都是独立小批次，互不阻塞；③ 依赖交付门/清场语义先落地（v4 WP-1/WP-2.3）。
- **Cons:** ① 的增量重放语义设计不当会破坏协作恢复；③ 涉及 docmgr 数据清理策略需产品确认。
- **Context:** 证据链见 docs/designs/bid-proposal-writing-v4-volume-architecture.md「平台减负项」节 + Revision 3。修复入口：persistence.ts 增量化、编辑器脏块序列化、docmgr service 按 manifest 对账清理。
- **Depends on / blocked by:** ③ blocked by bid v4 WP-1（清场语义）+ WP-2.3（deliverables manifest）；①② 无前置。

## TODO: OntoStudio 批量确认/批量投影摊销（refresh 成本）

- **What:** 动作层支持一次事务多条确认 + 一次共享投影（或投影去重合并），摊销「每条确认 = 一次 store-global 全量 refresh（秒级）」的成本。自然落点：registry 动作声明加 batch 变体，或 executor 支持多 pk 提交后单次 `project_row` 批量调用。
- **Why:** 2026-09-26 eng-review 实测口径：`refresh()`（schema 重编+owlrl 闭包+全规则）是 store-global，N 条确认 = N 次全量 refresh。单人审阅 50 条 ≈ 一分多钟串行等待可忍；但方案 C（agent 预审分层，高置信自动确认）落地后确认量涨一个数量级，几百条自动确认会把共享 ASGI worker 打死。
- **Pros:** 方案 C 时代的性能事故前置免疫；批量确认本身也是审阅者的自然动作（按类型批量过）。
- **Cons:** 现在做是 YAGNI（单人场景秒级可忍）；批量动作声明会动 registry schema。
- **Context:** 设计 docs/designs/2026-09-26-ontostudio-review-loop-closure.md（人审闭环切片）+ eng-review Section 4 观察。**触发条件（任一即开工）**：①方案 C 进入设计（自动确认量级变化）；②P95 实测确认延迟被人抱怨；③审阅者主动要求批量操作。
- **Depends on / blocked by:** 人审闭环切片落地（本 TODO 摊销的就是它的 refresh 成本）。

## TODO: OntoStudio relation 审批通道（治理链确认的结构性前置）

- **What:** 给 relation 建审批通道——registry 新声明 relation 动作（`review_relation.confirm/.reject`）或 ingest 设门（relation 行带 status），使治理链/关系边可以像实体一样走「待审→确认→投影」。
- **Why:** 2026-09-26 eng-review 查实：registry（`registry/doc_graph.yaml:136-156`）只有 `review_entity.confirm/.reject` 且仅作用于 `graph_entity`；relation 无 status 属性、`doc_graph/ingest.py` 不设门——环评域最在乎的治理链现在只能整链确认实体、关系裸奔入库。且 kernel loader 只投影同调用内双端点齐备的 relation，确认实体不补投历史 relation——结构缺口，不是顺手能带的活。
- **Pros:** 治理链（covered_by_standard 等跨报告比对的核心资产）获得与人审实体同级的可信度；跨模块链路启用（现全 disabled）的数据质量前置。
- **Cons:** registry schema 扩展 + dg_relations 加列或 ingest 改造；投影语义要处理「双端点状态不一致时 relation 投不投」。
- **Context:** 设计 docs/designs/2026-09-26-ontostudio-review-loop-closure.md「后续批次」节 + eng-review 外部声音发现4（驳回移除会留悬挂 relation 边——relation 审批设计时必须一并裁决边的新陈代谢）。**触发条件：环评域审阅者第一次问「链怎么确认」即开工，勿在无人问津时预建。**
- **Depends on / blocked by:** 人审闭环切片落地（实体审批语义先稳定）；与 reviewer 授权批次无硬依赖。

## TODO: OntoStudio 推理白盒化（解释视图 + CQ 验收单）

- **What:** ReasoningPage 两条白盒化改造。①**推理解释视图**：后端给「这条推理三元组由哪条规则/属性链推出」的溯源 API（自定义 CONSTRUCT 规则有 per-rule named graph 可直查——`rules.py` 既有设计；owlrl 内置规则无 provenance，需 post-hoc 差分：infer 前后闭包对比归因），前端把「1857 物化」这种黑盒数字展开成可下钻的论证链。②**CQ 验收单**：能力问题（competency questions）入库（域 yaml 或独立 cq.yaml，附期望答案/路径），每次 infer 后自动判定「本体能回答哪些 CQ、答案来自哪条推理路径」，替换 ReasoningPage 现挂的静态示例区块（该区块自带「示例数据」水印）。
- **Why:** 2026-09-26 逐页盘点查实：infer/validate 是真端点（月儿湾实测 1857 物化 2.3s、国标五项全过），但推理验证面是黑盒——「这条 covered_by_standard 从哪条属性链推出来的」无处可看。对建模者的实际后果：本体 axiom 改错了只能靠数字异动猜；对验收者：CQ 是摆设。另 owlrl 有「链首无实例静默零推断」的坑（见 buglog prp-spo2 条目），解释视图还应能暴露「为什么没推出来」。
- **Pros:** 建模错误可定位（哪条 axiom 推出意外结论/该推没推）；CQ 从摆设变回归测试——本体每次改动后跑一遍，能力不回退；非工程背景的领域专家能看懂推理结果（人审闭环切片落地的同一批用户）。
- **Cons:** 两类规则的 provenance 能力不对称（owlrl 内置规则需差分归因，工程量集中在「为什么没推出来」这类反事实解释）；CQ 答案匹配做精确匹配先（语义匹配是无底洞，明确不做进本条）。
- **Context:** 2026-09-26 会话页面盘点（设计 docs/designs/2026-09-26-ontostudio-review-loop-closure.md「页面分析」节）；建模器 ModelerPage 已是真编辑闭环（registry-content validate/save），推理是建模验证的下游——本体改完→推理→**看懂**，最后一步现在缺失。**触发条件（任一）：①本体建模用户（非实现者本人）第一次问「这条结论哪来的」；②axiom 改动开始需要回归验证；③国标符合性评审要求 CQ 证据。**
- **Depends on / blocked by:** 人审闭环切片（`docs/designs/2026-09-26-ontostudio-review-loop-closure.md`）落地——数据先能沉淀，推理才有稳定输入；与 relation 审批 TODO 无硬依赖但同期做可共享解释视图。
