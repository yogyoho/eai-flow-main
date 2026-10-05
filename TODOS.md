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

## TODO: OntoStudio 抽取任务 API（任务队列/进度概念）

- **What:** 后端补「抽取任务」实体与 REST 面（任务行：来源线程/文档、域 profile、状态 排队/抽取中%/完成、实体/关系/提及计数），供 08 抽取导入页任务队列表、置信度直方图（按任务过滤）消费；抽取动作本身复用既有 regex/v1 确定性抽取器 + ingest 管线。
- **Why:** 2026-09-26 页面盘点定案的真缺口——`doc_graph/ingest.py` 是内部装载器（单事务入库），没有「任务」概念；08 页的任务表/进度条目前只能是静态示例（已标注 规划）。缺它则多文档批量抽取无观测点（卡在哪篇、失败重试）只能翻后端日志。
- **Pros:** 批量抽取可观测（进度/失败/重试入口）；置信度直方图与证据链引文获得真实数据源；为方案 C（agent 预审分层）的「抽取→预审→人审」流水线提供任务锚点。
- **Cons:** 新表（dg_extraction_tasks）+ 状态机（排队/运行/完成/失败）+ 与主系统线程的来源关联字段；08 页从静态转真需要前后端同步动。
- **Context:** 2026-09-26 会话页面盘点（设计 docs/designs/2026-09-26-ontostudio-review-loop-closure.md「Status Quo」节）；IngestPage 原型稿已按真任务概念画好（docs/designs/ontostudio-frontend-redesign-20260926.html#ingest），后端就绪即可接线。**触发条件：多文档批量抽取场景实际出现（≥3 篇/批），或用户抱怨「不知道抽到哪了」。**
- **Depends on / blocked by:** 人审闭环切片已落地（2026-09-27，2ae60a40b/41504e3cb）——任务产出与待审队列已能衔接；无其他前置。

## TODO: ingest 任务进度真百分比插桩（2A 延期项）

- **What:** 给 ontostudio ingest 任务进度加真实百分比（持久化循环 item 计数回调），替代阶段枚举制的粗粒度展示。
- **Why:** 2026-10-01 eng-review D3 裁决阶段枚举（queued/extracting/loading/done/failed）满足 v1；但任务量/时长涨上去后操作者无法区分「62% 推进中」和「卡住」。
- **Pros:** 进度可信；UI 可恢复 IngestPage 原型的百分比列形态。
- **Cons:** 侵入 ingest_extraction 内部或包一层计数回调；单人内网工具当前收益低。
- **Context:** 插桩点=ontostudio/backend/app/doc_graph/ingest.py:55 的落库循环；UI 侧前端无测试 runner，改完靠容器 build+截图验收。任务 API 契约见 docs/designs/2026-10-01-ontostudio-ux-governance.md B2。
- **Depends on / blocked by:** B2（ingest_tasks 表+runner）落地。

## TODO: OntoStudio 快照调度 + 跨域链路启用（office-hours 方案 C 遗项）

- **What:** ①每日 06:00 可恢复快照调度器（导出页快照历史卡已画好等接真）；②cross_module 四链路启用评估与补数据。
- **Why:** 导出页自述「计划中——待快照调度」；跨域四链路全禁用（3×NO_DATA+1×匹配率 0.0%）=本体平台宣称的跨域能力是死链（2026-09-22 三轴判定，2026-10-01 复核仍成立）。
- **Pros:** 「计划中」标记清零；跨域是平台核心卖点。
- **Cons:** 快照调度=新 cron 基建；跨域是数据/匹配率问题非纯代码，强启产出低质量链路。
- **Context:** 2026-10-01 office-hours 方案 C 被否决理由=深水区单独立项；跨域阈值 30% 匹配率，数据基础=cross_module.yaml（ontostudio/backend/app/ontology/registry/）；快照历史卡 UI 在 ExportPage。
- **Depends on / blocked by:** 快照调度无前置；跨域启用前置=匹配率达标或人工入库补链。

## TODO: OntoStudio 直连文档抽取通道（extract.py 文档→text + samples 卷挂载）

- **What:** 让 ontostudio ingest 任务能直连原始文档抽取（gateway eia_samples/extract.py 的 read_source_text/_read_docx ~300 行移植 + kf_samples 源文件卷挂载进 ontostudio-backend + extract_ontology.py 移植），替代当前「消费 kf_samples.outline_json 已持久化产物」的 v1 路径。
- **Why:** 2026-10-01 eng-review D10 终裁 v1 走产物消费（outline_json），因源文件在 gateway 容器文件系统（kf_samples 真源不在仓库内）且 ontostudio-backend 只挂 kernel 卷——worker 打不开引用文件。直连通道是任务化抽取的完整形态。
- **Pros:** 新上传文档可即时任务化抽取，不依赖离线批量管线预产 outline_json。
- **Cons:** ~300 行移植 + 容器卷变更 + mention 合成边界（首次去重跨文档、quote 归属）需重新设计。
- **Context:** 外部声音 2026-10-01 证伪移植路径三连（text→dict 边界/文件可达性/置信度过 0.7 人审门——末条已由 force_review 解）；converter 模式参照 ontostudio/backend/app/ontology/c_ingest/pipeline.py:374。
- **Depends on / blocked by:** B2 v1（产物消费路径）落地并验证闭环。
## TODO: OntoStudio 多域接入四步清单（标注聚合/域筛选/同域合并约束/透镜注册）

- **What:** 接入第二域（bid_quote 等）时的四步：①etype/谓词中文标注改多域聚合（各域 yaml 注释块合并，键加域名空间防同名冲突）②pending 端点（fetchPending/resolution/pending）与消解面板加域筛选 ③合并建议加同域硬约束（跨域实体禁止合并建议——防同名 etype 误配事故）④registry 注册新域透镜对象类型（实体库类型选择器才可浏览）。
- **Why:** 现有中文标注源（fetchEiaEtypeLabels/getPredicateLabels，explorerDataSource.ts）只解析 eia.yaml 注释块——其他域 etype/谓词回退英文；pending 队列（fetchPending）不带域参数——多域待审混流无法拆分；相似合并按 etype 匹配——跨域同名 etype 会产生错误合并建议（合并跨域实体是数据事故）。
- **Pros:** 多域数据可审可管；实体库/消解审核/图谱浏览全链路支持新域。
- **Cons:** 四处改动分散（标注解析/resolution 端点/前端面板/registry yaml），需一次性设计。
- **Context:** 2026-10-02 消解审核页审计探针实证：registry 仅 5 对象类型（图谱实体/关系/证据 + eia 实体/关系双透镜），待审 230 全 eia 域；当前单 eia 闭环刚打通，多域改造无真实第二域数据验证，刻意缓行。涉及：explorerDataSource.ts（fetchEiaEtypeLabels/getPredicateLabels）、ontology-graph-api.ts（fetchPending）、ResolutionPanel.tsx、registry yaml。
- **Depends on / blocked by:** 第二域真实数据产生（bid_quote 管线或新域接入）。

## TODO: OntoStudio 抽取管线多域化（converter 域分发 + kf_samples 域标注）

- **What:** 抽取导入管线从单域硬编码改多域分发：①converter（ingest_tasks.py:155 `_drop_invalid(onto, EiaExtraction.domain_etypes, ...)` 与 :185 `payload = EiaExtraction(domain="eia", ...)`）按样例内容自动判域——entities 的 etype 命中哪个域的 domain_etypes 集即分发到对应 Extraction 子类（BidExtraction 类已存在于 schemas.py:329，域分发器是唯一缺口；基类 fail-closed 已拒未知域）；②kf_samples 加 domain 列（或 etype 推断）显式标注；③/samples 下拉加域列过滤与标注。
- **Why:** 2026-10-10 CEO 审核定案：v1 单域硬编码是有意边界，但第二条域接入抽取时此处是唯一分发缺口——BidExtraction 骨架已备（与 qualified_bidder 规则同源，Phase B 试点），届时只差分发器。下拉全环评样例是数据事实非缺陷。
- **Pros:** 多域产物可任务化入图；BidExtraction/未来域 Extraction 子类即插即用；样例域可追溯。
- **Cons:** domain 判定按内容启发式有误分风险（fail-closed 兜底：不命中任何域即拒）；kf_samples 加列需迁移。
- **Context:** 消费端/UI 侧配套见「OntoStudio 多域接入四步清单」（标注聚合/域筛选/同域合并约束/透镜注册）——两条合计才是完整多域抽取。强制人审（force_review=true）与白名单清洗（_drop_invalid）语义在各域通用，保留。
- **Depends on / blocked by:** 第二域真实抽取产物产生（同四步清单前置）；kf_samples 表结构变更窗口。

## TODO: OntoStudio 审阅角色授权 + 操作审计日志(多人化前置)

- **What:** ①消解审核/建模器/治理动作按角色授权(审阅者/建模者/只读三档, 替代当前 system:access 一刀切+superadmin 超管横幅); ②关键操作审计留痕(审核确认/驳回/合并/规则启停/快照恢复/装载——who/when/what, 现有 history jsonl 只有事件无操作者)。
- **Why:** 2026-10-05 能力矩阵新识别盲区 B1/B2——消解面板横幅自述「第一版仅超管可审」; 多人使用前任何有权限者可驳回/合并/停用规则且无追责通道。
- **Pros:** 多人协作安全前置; 审计满足内部合规。
- **Cons:** 角色模型需与主系统权限体系(role-management yaml 驱动)对齐, 跨模块设计。
- **Context:** 权限机制参照主系统 role-management yaml 驱动方案(memory: role-management-yaml-driven); 消解面板横幅与 rules_state/快照/装载等操作点为审计插桩位。
- **Depends on / blocked by:** 多人真实使用需求确认(单人当前低危)。

## TODO: OntoStudio 低优先增强池(通知/registry回滚UI/CQ库机制)

- **What:** 三件低优先: ①任务失败/违规突增/装载失败通知通道; ②建模器 registry 变更回滚 UI(yaml 在 git 有历史, 现需手工 revert); ③CQ 库扩充机制(cq.yaml 维护规范+入口, 现仅 4 条种子 1 条停用)。
- **Why:** 2026-10-05 能力矩阵 B3/B4/B5——均为低频改进, 不阻塞任何当前使用。
- **Pros:** 运维体验与工程实践完善。
- **Cons:** 均无日常痛点驱动, 排期价值低。
- **Context:** 能力矩阵 docs/designs/2026-10-05-ontostudio-capability-matrix.md; mention 治理已入「数据治理」面板可定期手动跑。
- **Depends on / blocked by:** 无硬前置, 按需认领。

## TODO: OntoStudio 校验中心按域校验（「范围:全域」按钮接真）

- **What:** 校验运行面板「范围:全域」disabled 按钮接真——run_shacl 支持域过滤(按 registry 域 shapes/data 子集校验), 前端范围选择器(全域/单域)。
- **Why:** 2026-10-05 能力矩阵缺口 G-校验——单域数据下全域校验已够用, 但多域化(G4/G5)落地后按域校验成为排查刚需。
- **Pros:** 违规定位到域; 大图校验可分段跑。
- **Cons:** shapes/data 按域切分需摸清跨域引用边界。
- **Context:** 按钮已在 ValidationPage 校验运行面板(title「按域过滤校验为规划项」); registry formal_by_domain 已按域组织, 切分基础存在。
- **Depends on / blocked by:** 建议排在 G4/G5 多域化之后(单域阶段收益低)。
