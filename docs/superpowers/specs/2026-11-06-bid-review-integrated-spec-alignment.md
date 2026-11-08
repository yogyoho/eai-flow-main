# 投标方案审查：整合版规格书对齐审计与裁决回写

> 日期：2026-11-06。状态：LANDED（W1~W5 已随 2026-11-06 P0 计划落地：43ae36f98 / 886824d42 / de028f020；W6~W8 为永久裁决记录）；quick 层裁剪已由并发会话兑付（commit ec77631ef，_prune_rules_for_mode + worker 测试）。
> 审计来源：两轮共 6 只读代理证据核对（2026-11-05 vs 头脑风暴素材稿；2026-11-06 vs 整合版规格书全 17 章）。
> 规格书：`D:\knowbase\技术知识库\投标方案审查_整合版.md`（v1.0-integrated，10 片段 A-H 合并，22 条冲突裁决 C-01~C-22，规则 90 条，fields/anchors/enums 全注册表，24 注入算子，分阶段门禁）。
> 仓库正式设计稿：`docs/designs/2026-10-29-bid-review-design.md`（= 素材片段 A 的裁剪落位，P1-P6 裁决）。

## 0. 结论速览

- **整合版 = 目标规格书**。仓库实现 ≈ 其「阶段一 + 阶段二前半」的提前实现：五阶段 worker 主链、双引擎、七道校验、基准确认门、金标准回归（55 案 + bootstrap CI + MVP 档门禁 + 单条 fatal 零召回硬门）、M5 治理看板全部在场。
- **规则覆盖 50/90**（迁移后 L1=17/29，L2=6/26，L3=16/25，L4=0/10；P1-β批一 L3-019 兑付 → L3=17/25；P1-β批二 L2-021 兑付+L2-031 迁移（W11）→ L1=16/29、L2=8/26，L4 结构落地 0/10；P1-β批二续 文件级 6 条+要件级 3 条兑付 → L2=17/26、总 50/90，L4 激活 advisory 面落地但仍 0/10（advisory 不计正式覆盖），2026-11-07）。
- **原唯一阻断性冲突已消除（W1~W5 迁移 LANDED 2026-11-06）**：仓库 5 条与整合版同号不同义（L2-021/022/023、L3-019/020）已按本文件 §3.1 迁移清零（43ae36f98 / 886824d42 / de028f020）——规则扩展前置已满足。
- 已兑付动态：11-05 审计 P0 之③复核耗时真聚合（routers.py:558）、⑨enabled 切换端点（:1042）、⑩偏离表入导出（:658/692）、score_coverage 正名+derive_score_risk 涉险面——均已由并发会话落地。
- 大面积空白区：规格 §12 安全合规、§13 非功能（建议平台级立项，不在本模块内单打）；评测规模化项（holdout/自然集/24 算子实装 9：lte/gte/eq+mul/close+regex/subset_of/level_ge/col（check-op 层 or 增至 6），P1-β批二）。

## 1. 规格书定位与采纳策略

| 决策 | 内容 |
|---|---|
| 采纳 | 整合版作为 bid_review 的 target spec；其 C-01~C-22 裁决表为编号/枚举/命名唯一权威 |
| 编号权威 | 各层规则 ID 空间以整合版为准（L1-001~029 / L2 分段 / L3-001~025 / L4-001~010）；EAI 独有规则按 C-01/C-02 先例追加到各层段尾 |
| 分歧处置 | 仓库与规格的 8 处有意分歧以「裁决回写 EAI-W1~W8」形式记录（§3），不静默偏离 |
| 实施节奏 | 规格四阶段（打底→确定性完备→语义深化→竞争力规模化）映射到仓库既有 M1-M4 进度，错位处按 §6 backlog 追平 |

## 2. 十七章对齐矩阵

| 章 | 主题 | 判定 | 关键差异 |
|---|---|---|---|
| §1 | 定位/两档模式/免责 | 🟡 | deep 确认门✅免责✅；quick 层裁剪已落地（commit ec77631ef，`worker.py:478`，rules_total 取裁剪后分母）；报告版本清单缺 |
| §2 | 总体架构 | 🟡 | 五阶段主链一致；独立 Verifier 模块化/知识检索/灰度 shadow/双模型交叉缺 |
| §3 | 数据模型 | 🟡 | 四实体对齐；~~verdict/state/semantic_verdict 三拆~~ → 已兑付（2026-11-06 P1-α：b08932b68）；gate_status 四态、severity 四档、Anchor logical_page/bbox/ocr_conf、Field type/unit/confidence 缺 |
| §4 | 规则体系 | ❌→🟡 | 覆盖 59/90（L1 21/29 L2 21/26 L3 17/25；批七 2026-11-08 +4 hyb2/sem1/det1：L1-004 项目负责人资格/L1-020 分包冲突/L1-022 格式份数/L1-026 递交时间，见 §6.1 批七兑付清单；批六 2026-11-08 +5 det：L1-017 联合体/L2-012 技术章节/L2-013 承诺章节/L2-014 附图/L2-040 必备表格，见 §6.1 批六兑付清单；L2-021+W9+L2-031 迁移批二兑付；文件级 L2-001/002/003/004/050/051+要件级 L2-030/032/033 批二续兑付 2026-11-07，含 L1-006 precondition 兑付 C-17 与 L2-051/L1-007 两条泛化主责折叠）；5 条同号不同义已迁移（§3.1 LANDED 2026-11-06）；主责矩阵/方向互斥缺；L2\|ATT 去重键三层键已落地（P1-β批二） |
| §5 | 端到端流程 | 🟡 | 主流程对齐；~~解析广度❌~~ → 大体兑付：xlsx✅（2026-11-05 对齐审计⑤ per-sheet table blocks/rows 双键+|a|b| 扁平/sheet 注记/500 行上限，钉子 test_bid_review_parse.py::test_xlsx_sheets_to_table_blocks+test_xlsx_row_cap_truncates）、zip✅（审计⑥ zip-slip 防护/≤20 文件/≤200MB/嵌套 zip 拒/成员 source 传播，6 钉子）、章节兜底✅（2026-11-08 批四 `_scan_heading_anchors` hint 通道注入第二段 prompt，签名零变 a022f1ef3）；OFD/text_hash 挂 P2（P1 括号外）；招标抽取 33 字段批五逐字段权威复核（2026-11-08：✅20 别名集映射／⚠️2 窄化／❌11 缺，前记 6/33 系粗口径审计，差表见 §6.1；批六 2026-11-08 兑付⚠️2+❌5、差表刷新 ✅25/❌4+挂账2）；~~门禁 gate_status 判定式未落~~ → 已兑付（2026-11-08 批五：worker.compute_gate_status 四态按规格 §5.7.2+summarize additive 键+双渲染器四态文案+前端 GateMetricsRow 四态 pill，2fd8498ca/bff6d31aa/ee57865b52；L3-fatal 人工升格理论分歧记档 §6.1 尾注） |
| §6 | 注册表 | 🟡 | 命名同源但仓库走别名集；抽取器配置化❌；lint 端点❌；~~boq_unit_checks 等 3 处 LLM 派生布尔违反规格 L2233「禁模型换算」禁令~~ → 已兑付 derive_joins 服务端派生（2026-11-06，见 §5 第 3 条） |
| §7 | 语义 Prompt | ✅🟡 | 铁律 1-7 落地（无证据不出结论硬校验/unclear→need_human/禁心算）；第 8 条防泄露缺；12 道后处理 vs 现七道 |
| §8 | API | 🟡 | 主端点对齐；缺 rules lint/publish/rollback、bulk-feedback、Idempotency-Key、业务错误码体系；MCP=规格外扩展 |
| §9 | 复核工作台 | 🟡 | 布局+四动作✅；快捷键（J/K/Y/N）/批量操作已落地（2026-11-06 复核确认，前记「缺」过时）；fatal 逐条/断线恢复缺；角色视图❌ |
| §10 | 输出物 | 🟡 | 概览/清单/偏离表/差异在；评分预估=有意不做（W6）；雷达图缺 |
| §11 | 评测 | 🟡✅ | 四态判定决策表逐字采纳（CALIBRATION.md）✅bootstrap CI（1000 固定种子）✅MVP 档门禁齐✅；缺 holdout/自然集/双人标注/24 算子（实装 9：lte/gte/eq + mul/close + regex/subset_of/level_ge/col，check-op 层 or，P1-β批二）/ATT 组门禁；匹配阈值 0.55 与规格一致（2026-11-06 复核确认），仅匹配权重微差（0.5/0.3/0.2 vs 0.55/0.30/0.15）待对齐 |
| §12 | 安全合规 | ❌ | 威胁模型/数据分级/审计/销毁/脱敏/上线清单模块内全无（owner 隔离+免责+注入拦截除外）→ 平台级立项 |
| §13 | 非功能 | ❌ | SLO/容量/成本/灰度演练全无 → 平台级立项 |
| §14 | 路线图 | 🟡 | 实际路径≈PoC 超集；跳过「30 份真实文档评测」（golden 合成件替代）、未过上线门禁带条件推进——两点记入风险 |
| §15 | 二十四坑 | ✅🟡 | 最致命六坑中 4 个有显式对抗（UNKNOWN 不判通过✅/抽取失败不判 MISSING✅/L4 不入门禁✅vacuously/去重主责✅🟡）；「基准未确认硬卡点」「评测泄漏（无 holdout）」部分 |
| §16 | 创新点 | 🔵 | 七项全未做（与仓库 v2 挂账一致）；derive_score_risk ≈ 「解释卡」克制版 |
| §17 | 完善建议 | 🟡 | 规格 P0 十项：✅4 / 🟡2 / ❌4；与仓库 P0 清单合并见 §5 |

## 3. 裁决回写（本文件核心）

### 3.1 编号迁移 W1~W5（阻断性，随 P0 plan 落地）

迁移原则：**整合版编号空间为权威；仓库规则按业务实质映射到同义规格规则；无规格对应物的迁各层段尾扩展号**（C-01/C-02 先例：追加编号）。迁移为纯改名+层归属修正，不改 check 逻辑与字段契约。

| # | 仓库现 ID/名称 | 整合版同义规则 | 迁移为 | 类型/严重度处理 | 依据与注记 |
|---|---|---|---|---|---|
| W1 | L2-021 附件类型指纹核对（hyb） | L2-023 附件类型正确（sem） | **L2-023** | 保持 hyb | 指纹字典 det 粗筛+模型确认=规格 sem 判定的工程化精化（C-10 同款先例）；「原件不得翻拍」语义边界由 verdict_gloss unclear→人工兜底；规格 L2-023 状态映射「不符→PARTIAL 不确定→UNKNOWN」与仓库 verdict 语义一致 |
| W2 | L2-023 附件实体内容空白（det major） | L2-022 附件内容非空可辨识（det major） | **L2-022** | 保持 major | 业务同义（非空白/非截断）；规格 OCR 置信≥0.85 门为能力挂账（解析层无 ocr_conf，extract.py:57 已显式延后）；is_empty_text 启发近似保留并注明误标兜底=major 人工裁决 |
| W3 | L2-022 必填清单行未报价（det fatal） | L2-041 表格必填字段非空（det major） | **L2-041** | **保持 fatal（EAI 上调，C-11 第 3 条 severity_override 机制，记录于此）** | 机制同构：规格 L2-041「required 由招标要求回填，bid 侧不自判」= 仓库 M3 铁律原文；v1 实现覆盖 boq 单价实例，table_cells 一般化挂账。上调理由：必填清单行缺价属实质性不响应，与 L1-011 漏项同档；规格 major 为全表格字段的一般档 |
| W4 | L3-019 业绩条目聚类存疑（det major） | 无同义规格规则（最近亲：L2-025 复合附件配套「分组失败→UNKNOWN」子路径） | **L3-026**（段尾扩展） | 保持 L3/major | 重复凑数检测为 EAI 独有判定；规格 L2-025 落地时本规则作为其分组子通道复用，届时评估并归 |
| W5 | L3-020 章节正文空缺（det major） | L2-015 占位符与空章节检测（det major） | **L2-015**（层归属 L3→L2） | 保持 major | 业务同义（空章节/待补充/模板残留）；规格 L2-051 草稿残留为文档级姊妹规则（full_text 命中）后续补；层移动不改变门禁行为（L2 major 不阻断，与 L3 major 等价） |
| W11 | L1-021 声明函存在性（det major） | L2-031 要件级声明函存在性 | **L2-031**（层归属 L1→L2） | 保持 major | 改名不改 check（现 check=声明函存在性恰为规格 L2-031 语义，W1-W5 先例，P1-β批二 2026-11-07）；签署维度+承诺函清单挂抽取面（批二续）；旧 override 键 L1-021 孤儿 no-op 记档（A-β2-⑥） |

迁移连带影响（P0 plan 的施工清单）：`1.0.0.yaml` 五条 id/name/layer；`test_bid_review_golden.py` EXPECTED_COVERAGE 精确相等清单；golden/cases 引用旧 ID 的题（改名不改编题断言语义）；CALIBRATION.md 引用；registry 宇宙清单；包头注释条数修正（32→迁移后实际数）；DB rule_overrides 旧键处置见下方修正注记。
DB 注记（质量审查 Important-1 修正，2026-11-06）：**轮换使旧 override 键语义翻转，非无害回落**——迁移前入库的 `L2-022`/`L2-023` 键现指向不同规则（旧 022=必填报价→现 022=附件空白；旧 023=附件空白→现 023=指纹）：任何早于 commit 43ae36f98 的库在启用逐规则 enabled 开关前必须先清空或重映射这两键；L2-021/L3-019/L3-020 旧键才真回落 yaml enabled。2026-11-06 实测 dev ext 库 `bid_review_rulepacks` 尚无 rule_overrides 列（models.py 已声明、迁移未跑）=现网零残键，该列迁移落地时须带旧键重映射；另 8 行 bid_review_issues 历史 rule_id=L2-021 成孤儿 ID（规格已接受不迁移）。

迁移后对规格缺口的影响：L2 覆盖 5→6（新增 L2-015 位），L3 17→16（L3-019/020 腾出的规格位 L3-019 单价×数量、L3-020 大写小写进入待建清单——注意规格 L3-020 标注「被 L1-010 抑制」，仓库 L1-010 第 3 步 number_to_words 已覆盖其判定，无需独立实现，照规格抑制关系记 absent 即可）。

### 3.2 永久裁决 W6~W8（有意分歧，规格侧回写候选）

| # | 分歧点 | 仓库立场 | 裁决 |
|---|---|---|---|
| W6 | 规格 §10.4 评分预估表（得分区间+提分建议） | 不建评分预估；反向建 derive_score_risk 涉险面 + 措辞纪律（禁「预估得分/预估扣分」，extract.py:594） | **维持仓库立场**=规格 §17.6 开放问题 Q6 的保守侧已默认落位；规格侧回写「评分预估降级为涉险面提示」候选，待业务评审翻案才反转 |
| W7 | 规格 §8 无 MCP 条目 | mcp.py 七工具为规格外扩展（agent 对话式审查入口的落地件） | **保留扩展**；挂账补 diff/deviations/report 三工具消除「REST 有 MCP 无」不对称 |
| W8 | 规格 §4.8/§7 未定义 hybrid 数值豁免 | A12 三型分治：hyb 一律不派生 numeric_expr，防「粗筛表达式复核模型结论」结构性反转；prefilter 求值失败 fail-open | **保留为 EAI 精化**；规格侧回写候选（C-10 的补强细则） |
| W9 | 规格 L3-012「被 L2-021 抑制」（:884/:4661），存在性归 L2-021 主责（:958） | 仓库 L2-021 未建，L3-012（正文引用附件齐备，1.0.0.yaml:461 `present==True` 存在性判定）独立运行无抑制 | **维持独立运行**（L2-021 缺位下抑制=静默漏检，违反 L1 宁可多报取向）；P1-β 建 L2-021 时须同步落抑制联动 + 去重键模板（规格 :981 同实体引用编号），届时复核 L3-012 的存在性/一致性职责切分；**已兑付**（P1-β批二 2026-11-07）：L2-021 附件编号引用+抑制联动（同实体 entity_keys 折叠，suppressed_by 记账，message 禁入匹配面）+去重键三层键落地；L3-012 一致性职责独存（存在性归 L2-021） |
| W10 | 规格 §4.8.2 算子空值行为「null→UNKNOWN」三值传播 | 仓库 KeyError→need_human→UNKNOWN 不判通过，机制分歧结果同构 | 维持仓库机制（无哨兵）；规格侧回写候选 |

### 3.3 口径分叉处置表（P1，alias 层渐进，不一次性改库表）

| 裁决 | 仓库现状 | 处置 |
|---|---|---|
| C-05/C-22 | 附件状态 MATCHED 直接入库 | 视图层/入库前归一 PRESENT（MATCHED 保留为清单视图别名） → 已兑付（2026-11-06 P1-α：0f5cb6d68；入库 PRESENT+清单别名） |
| C-08 | review_state 五态（复核口径） | 补 verdict（引擎五值）/semantic_verdict（full/partial/none/unclear）两字段，state 分层映射；review_state 保留为复核投影 → 已兑付（2026-11-06 P1-α：b08932b68；semantic_verdict+state 落库，verdict 值域迁 P1-β）；verdict 值域五值迁已兑付（2026-11-07 P1-β批三：T1 9ea415c15 引擎五值域 verdicts.py 唯一真相+四生产者+golden loader 别名面/T2 863f725dc DB 幂等 remap（表名 bid_review_issues）+routers 五点+反馈转待人工 UNKNOWN/T3 62319e817 前端 verdictPill 五值映射；golden 夹具零改动 73/0 保持，family 680p/6s/0f） |
| C-09/C-18 | extract.py 用别名集（substantive_clauses/required_declarations/required_qual_level…） | 注册表真源名 + 加载期 alias 解析（规格 6.1 本就预期双命名并存，仓库已在 alias 侧，只差 alias 表显式化） |
| C-16 | tender.bid_deadline | alias 到 tender.deadline |
| C-21 | logical_page 无 | extract.py:57 已显式延后；解析层支持 logical_page 时一并落 |
| C-11 | 无 src 严重度覆盖 | 附件清单条目 src→severity 覆盖进 att_check/att_count 分支 → 已兑付（2026-11-06 P1-β批一：src 五枚举覆盖+合并最严档+rg 保守 fatal；规则级 severity_override 配置后台=P2） |

## 4. 规则覆盖缺口（迁移后基线：39/90——W1~W5 为改名与层归属修正，总数不变；L2 5→6、L3 17→16；P1-β批一 L3-019 兑付 → 40/90、L3 17/25；P1-β批二 L2-021 兑付+L2-031 迁移 → 现 41/90、L1 16/29、L2 8/26，2026-11-07）

| 层 | 实有 | 待建 | 备注 |
|---|---|---|---|
| L1 | 16/29 | -004 负责人(hyb)/-017 联合体/-018 关联披露(hyb)/-020 分包(sem)/-022 格式密封(hyb)/-023 资格件效期/-024 信用(默认关)/-025 法人证件/-026 递交/-027 电子标(major)/-028 偏离表/-029 围串标(默认关) | H 追加段 -023~-029 全缺；-024/-029 依赖外部数据源默认关；-021 声明函存在性已迁 L2-031（W11，P1-β批二 2026-11-07） |
| L2 | 17/26 | 章节级 -010~014/-011(hyb)、字段级 -040/-042/-043、复合 -025 | 缺幅收窄；文件级 -001~004/-050/-051+要件级 -030/-032/-033 已兑付（P1-β批二续 2026-11-07，9 条 det，A-续-①②③④ 裁决内落地）；挂账：L2-002 逐册份数对齐（v1=册数下限）、L2-050 MIME-扩展名一致性（需映射表）、bid.full_text 运行期生产者接线（L2-051 live 暂恒 need_human 诚实面，golden stub 直注）、折叠 entity 级细化（rule 级已落地） |
| L3 | 17/25 | -011 服务承诺(sem)/-015 偏离表一致(hyb)/-017 图表(hyb)/-021 正副本/-022 印章(sem)/-023 数字文字/-024 附件年份/-025 表格正文 | L3-020 大写小写由 L1-010 抑制覆盖，不建；-019 单价×数量已兑付（P1-β批一 2026-11-06，需乘法算子已落地） |
| L4 | 0/10 | 全部（advisory 不计正式覆盖） | 规格 C.2 已给全套可落地 YAML；永不入门禁；**结构落地+激活全兑付**（10 卡独立包 bid-review-l4；P1-β批二 2026-11-07 离线态 → P1-β批二续 2026-11-07 激活：RulePack.meta 结构化 counts_toward_bid_gate=false/max_issues_per_report=10、worker 并列 ADVISORY_RULEPACK_PATH 合包单次 evaluate、summarize advisory 单列正式四档排 L4、_fatal_hits 显式守卫+_LAYER_RANK/_cross_layer_group 排除、报告「竞争力建议」独立尾节、反馈归属按 L4- 前缀入 bid-review-l4 行、rulepacks 三端点双包、前端 RulesView 多包聚合+ResultsView advisory 分节 FP 三通道过滤；审查六观察 N1-N6 非阻塞记档） |

表达式引擎缺口已清（A-β1-②/A-β2 批）：~~乘法~~/~~容差比较~~ 已兑付（P1-β批一 2026-11-06）；~~regex~~/~~subset_of~~/~~level_ge~~/~~or（check-op 层）~~/~~Decimal（加总链）~~ 已兑付（P1-β批二 2026-11-07）；三值传播（W10 已裁等价，无码）；余 check-op 结构级 neq/gt/lt/in=表达式级覆盖，YAGNI 不建。

## 5. P0 清单（本批实施范围）

1. **W1~W5 编号迁移**（§3.1 施工清单）——一切规则扩展的前置。
2. ~~quick 模式层裁剪~~ → 已兑付 ec77631ef（2026-11-06 并发会话，对齐审计①）。
3. ~~换算禁令修复~~ → 已兑付（2026-11-06，P0 计划 2026-11-06-bid-review-w1-w5-migration-server-derived-joins-plan.md Task 5/6：derive_joins 服务端派生 c6f2762+d7a84b11+751c5909f；请求面排除 346acbb85，宇宙 78 不变仅请求面 71；离线快照 26/26 零翻红；诚实降级加固 bug-4083）。
4. ~~（P1 前置）枚举三拆 alias、MATCHED→PRESENT 归一、CALIBRATION 裁决表回写整合版侧~~ → 已兑付（2026-11-06 P1-α，Task 2/3/4；verdict 值域迁移部分挂 P1-β）。

## 6. P1/P2 backlog（规格 §17 合并仓库实况）

**P1**：L2 要件级/文件级规则包扩展 + L4 十条（C.2 YAML 现成）；解析广度（xlsx 表对象/zip/章节兜底）；抽取器配置化+lint 端点；评测规模化（24 算子实装/ATT 组门禁/holdout/自然集/双人标注）；漏报回流通道；错误码体系；MCP 三工具补齐（枚举三拆已于 2026-11-06 P1-α 兑付，verdict 值域迁 P1-β）。P1-β 批次划分：批一（2026-11-06）兑付：乘算引擎+L3-019+C-11 src 覆盖；批二（2026-11-07）兑付：引擎五件套（or/regex/subset_of/level_ge/col）+Decimal 加总链+L2-021 附件编号引用/W9 抑制联动/dedup_key 三层键+L2-031 迁移（W11）+L4 包结构（10 卡离线态）；批二续（2026-11-07）兑付：文件级 L2-001/002/003/004/050/051（6 新路径+泛化主责折叠 `_fold_issues_by_primary`，L2-051→L3-016/018）+要件级 L2-030/032/033（signature_slots 双路径+三 presence 布尔服务端派生禁模型自产、L1-006 precondition 兑付 C-17、L1-007→L2-030 条件折叠，A-续-①②③④ 全兑付）+L4 激活全链（meta 结构化/worker 合包/advisory 面/gate 守卫/双包端点/前端多包+advisory 分节，A-β2-⑤ 兑付；宇宙 92、包 50（det 44）、golden 73/0、family 679p/6s/0f）；挂账：L2-051 bid.full_text 生产者接线、L2-002 逐册份数对齐、L2-050 MIME 映射、折叠 entity 级细化、审查六观察 N1（advisory API 面含 FP 行，前端已三通道过滤）~N6（counts_toward_bid_gate 硬编码守卫，第二 advisory 包出现时 meta 化）、前端人工走查；批三（2026-11-07）兑付：verdict 值域五值迁全链（A-β3-①..⑦ 全兑付；violation→FAIL/unclear·need_human→UNKNOWN/基础设施降级→ERROR/PASS·SKIP 枚举留位/false_positive 复核域保留；CALIBRATION 冻结面经 loader normalize_verdict 别名保住，夹具四目录+CALIBRATION.md 零 diff；零规则变更——包 50（det 44）/宇宙 92/golden 73 题全数字不变；挂账：PASS/SKIP 引擎 issue 行遥测面留位、ERROR 仅基础设施降级路径产出、golden/schema.py 直构 Expectation 须显式带新值 verdict（默认 "violation" 经 loader 归一但直构绕过 loader）、verdictPill 前端当下零调用点（映射惰性，ResultsView iss-verdict 直出 raw 文本）、DB remap 于下次 gateway 启动 _run_migrations 幂等生效）；批四（2026-11-08）兑付：章节兜底 hint 通道+§5 解析广度复核收口（A-β4-①..⑧ 全兑付：extract 内部确定性标题锚点扫描三类形 chapter/cn_enum/arabic+[[p.N]] 页归因+80 上限，build_sections_prompt 内部自算注入候选块——签名/worker/baseline 契约零变，铁律四条逐字不动，空锚点路径经评审字节级实证与旧版等价；xlsx✅/zip✅ 收口=审计⑤⑥+16 既有钉子确认，零新代码；零规则变更——包 50（det 44）/宇宙 92/golden 73/0/family 684p/6s/0f（680+4 新锚点测试）全数字锁兑付；golden 面零触碰；plan 计 e8ad821a3、T1 a022f1ef3；挂账：P2 OFD/text_hash（P1 括号外）、批外招标抽取 6/33 字段与 gate_status 判定式、hint 通道 live 走查留待下一次 live 抽取批；记档：plan 原 arabic 正则与自带测试自相矛盾（`[\s、.：:]` 回溯误中「3.5万元预算」），实现者 TDD 以测试为规格修正分隔符类去 `.`，评审独立实证确认修后数字链 1.1/3.2.1 命中各归其位）；批五（2026-11-08）兑付：gate_status 四态判定式+tender 差表落账（A-β5-①..⑧ 全兑付：worker.compute_gate_status 规格 §5.7.2 逐字（fatal FAIL→NOT_SUBMITTABLE/fatal UNKNOWN→PENDING_HUMAN/major FAIL 或 L3 major INCONSISTENT→CONDITIONAL/else SUBMITTABLE；纯值域状态域判定、need_human 旗标零参与、L4 隔离、false_positive 不计）；summarize_issues additive 键双 API 面共享；双渲染器四态文案（「命中 N 项」计数保持 _fatal_hits 逐字不动；钉面随迁四处——旧 md 钉 fatal UNKNOWN→「未命中」确系违反规格「UNKNOWN 不得当 PASS」的二值行为，以更强断言对替换，评审四推演证正当）；前端 GateMetricsRow 四态 pill+Summary 契约锚（ee57865b52）；tender 33 逐字段权威差表落 §6.1（✅20/⚠️2/❌11，前记 6/33 系粗口径）；零规则变更零宇宙变化——包 50（det 44）/宇宙 92/golden 73/0/family 695p/6s/0f（684+11 新 gate 测试）；plan 计 73db660be、T1 2fd8498ca+bff6d31aa、T2 ee57865b52；挂账：批六 tender 字段实补清单（§6.1 ❌11+⚠️2 随消费规则）、.warn CSS 装饰（报告 html 黄级视觉）、GateMetricsRow 零调用点接线（pill 惰性）、PENDING_HUMAN live 数据集验证（live 批）、门禁前端活体走查并批二续；记档：L3-fatal 人工升格理论分歧（§6.1 尾注）、既有 flake 两枚同根因 bug-4191（uuid4 id+created_at 同毫秒平局，修法另批）、plan 实态勘误两处证伪（测试无 exact-dict 断言/前端无 Summary 接口，均随迁声明）；批六（2026-11-08）兑付：tender 字段实补+5 det 规则（A-β6-①..⑩ 全兑付，A-β6-④ 一处修订声明）：T1 12 条模型抽取契约入 FIELD_TYPE_CONTRACTS（tender 8+bid 4，849f7ea8f）+T2 bid.tables 表格骨架服务端派生（[sheet:X] 标记扫描入 SERVER_DERIVED_PATHS，normalize 闸门丢弃模型自产，65c645439；PDF 无名表格 v1 漏判容忍挂账）+T3 五条 det 规则（L1-017 联合体 and-form+precondition 不造新锚/L2-012+013 章节 contains_any+keywords 惯用式/L2-014 附图 minor/L2-040 必备表格 fatal，6e1682229）+T4 ⚠️2 兑付（L1-003 inputs 富化 min_performance_amount/performance_window_months+hyb prompt 自动富化、det_expr/tpl 逐字冻结；L1-006 forms set_eq step；steps dict 形态引擎增量：optional 免缺字段门/per-step message_tpl·fix_tpl/dedup_ent 防同键互吞，legacy string steps 逐字节保留，2bd91a390）+T5 五锁显式 bump（宇宙 92→105/det 44→49/包 50→55/EXPECTED_V1_IDS+5，a51425d2）+T6 golden 面 controller 直办（题 73→78 每新规则一专用案例+EXPECTED_COVERAGE 50→55+L1-003 夹具补富化 inputs 宽门槛值——eval_core 剥 None 故 null=不在场=inputs 门翻 need_human，null 修法不可达；A-β6-④ 修订「题 73 不变→78」控制器声明，9d7ee4f97）；家族门 718p/6s/0f 含 golden 全绿；翻案两件：L2-024 已存在担份数主责（attachment_count_reqs 不落）、sample_required 无规格规则卡纯挂账；plan 计 b061c3d89；挂账：批七清单（§6.1 ❌4：pm_req/subcontract_limit/format_requirements/required_signatures）+L2-024 年份连续性（缺 years() 函数）+keywords 纯 ASCII 必备名空集漏判（保守侧 v1 容忍，精化式 not needles or contains_any(...) 待需）+T4 评审三 nice-to-have（collect_exprs dict 分支收窄/dict-step 缺 expr 载入期拒绝/免缴 N-A 语义 yaml 注）；记档：plan 三处实态证伪被验证优先协议拦（and-form 实读 chk["all"] 非 left/right、steps 仅字符串形态、codes() 不收字符串列表），并发 merge 窗口水工提交三度（瓷件部分提交 exit 128→临时索引 commit-tree+update-ref CAS；merge「ours 侧」树冻结于 merge 起点 HEAD——批六文件可被静默回退，备份分支 bid-review-batch6 兜底，merge 落地后须验 tip 内容）；批七（2026-11-08）兑付：§6.1 ❌4 消费规则收官、33 字段差表全清（A-β7-①..⑨ 全兑付，A-β7-② 一处修订声明）：T1 21 条叶平键契约入 FIELD_TYPE_CONTRACTS（A-β7-② 修订：plan 8 容器 obj→21 叶——normalize_fields 只收注册路径，容器注册+规则点消费未注册叶=live 永久 need_human 死锁；L1-001 bid.entity.* 先例，C-09 式拍平；旧 5 容器键零残留 grep 实证，364018baf+f70dfd4d2）+T2 四规则入包（L1-004 hyb 6 叶 inputs+op:eq 判定/L1-020 sem steps:[] 形态/L1-022 op:and 合规式三支+null 字面量 skip——plan op:or 违规式方向倒置废（违规出不了候选），取反也不足（全违规才出=欠报），正解=and+合规支（L1-017 先例）/L1-026 det 递交时间逐字；锚点 +4 叶平键化贡献+0（A-TENDER-CLAUSE plan 称已注册失实，bug-3985 拒载门确需补注册），f70dfd4d2）+T3 L1-007 inputs 富化 tender.required_signatures（A-β7-③ det/op 逐字冻结）+引擎 dict-step 缺 expr 载入拒载左移（A-β7-⑧ `_validate_dict_steps` 模块级最小侵入，原态静默漏收→实评 KeyError 伪装字段缺失 need_human 错位降级）+夹具补键三处（golden 两+eval_core 内联一，bug-4227 律；L2-030-signature-slot-missing 零触碰）+L1-006 免缴 N-A yaml 注（批六 nice-to-have 三件兑付二件，ee166a522）+T4 宇宙五锁 bump 105→126/首段 93→114/anchored_126/families 126（3baeac65c）+T5 golden 面 controller 直办（题 78→82 四专用案例+EXPECTED_COVERAGE 55→59，38fadf6cc）；家族门 736p/6s/0f 全绿收官；plan 计 ae7fa4b03；备份分支 bid-review-batch7@38fadf6cc；挂账：severity_override 机制（L1-022 major 固定）、L1-026 方式集维、L1-004 business_items 跨引、L2-030↔required_signatures 关系待规格、bid.fields 命名空间别名、bid.submit_method、years()（批六续）、keywords ASCII 精化（批六续）、collect_exprs dict 分支收窄（批六 nice-to-have 余一件）、FIELD_LABELS 21 叶键扫尾（批六起沿袭）、生产侧 21 叶键抽取真值 live 验证（live 批）；记档：F-1 prefilter 机制实态（det_expr=粗筛门、check op=判定——certs 非空=候选必进模型恰 1 次、空=零通路，与 plan 注记相反，probe 实证）；plan 勘误四处随迁（op:or 方向/A-TENDER-CLAUSE 注册态/build_rule_card 签名走 .get 纯 dict 契约/3 夹具实 2+eval_core 内联 1）；claimer 满载计时 flake（bug-4013 在案）家族门首轮红单跑绿；merge 危险面延续（MERGE_HEAD=c69e9ef0bc 在案，merge 落地后须验 tip 含批六+批七内容，回退则自 bid-review-batch7@38fadf6cc 恢复）；批八（2026-11-08）兑付：引擎卫生小批、零规则/零宇宙/零题锁面（A-β8-①..⑤ 全兑付；merge 危险面同日解除：537-commit a173ee7c2 落地，验 tip 六点过+家族门 736p@tip，批六/七内容零回退，备份分支 batch6/7 保留）：plan 计 ab9ce7b3f；T2 FIELD_LABELS 扫尾 54 路径（批六/七沿袭债清偿：universe 126/labels 72 差集 54 兑付，missing/extra 双零）+registry 新钉 labels⊆universe（新 inputs 入包漏挂 labels 当场红，4b04d55d6）；T1 years() 年数文本提取原语（中文小表一~十/两+阿拉伯 (?<!\d)(\d{1,3})\s*年 负向后顾——「2024年」日历年形态保守 None；bug-4227 律 null=不在场禁 raise；两表注册实态勘误：_FUNCS 解析白名单+_BUILTIN 求值分发缺一即求值期 KeyError 伪装 need_human；组合数已知边界取紧邻「年」单字位非 None——「二十年」→10/「十一年」→1，controller inline 注释诚实化，b8d912093）+_collect_exprs dict 分支收窄（A-β8-③：dict 项仅 steps 合法，_validate_dict_steps 扩面改名 _validate_list_items——all/any/values dict 项载入期拒载；eval 面对三键列表只 str(e) 渲染垃圾串、values 无 op 消费；bug-4260(原记 bug-4228,撞号重编)同类左移，存量包零噪声）+years 三钉/收窄双钉/真包回归（740p/6s/0f，736→737 T2 钉→+3）；挂账：keywords ASCII 精化（无失败案例不动匹配语义，批七记档维持）、severity_override 机制、L1-026 方式集维、L1-004 business_items 跨引、L2-030↔required_signatures 关系、bid.fields 命名空间别名、bid.submit_method、L2-024 年份连续性规则本体（A-β6-③ v2 语义裁决，years() 原语已备）、生产侧 21 叶键抽取真值 live 验证（live 批）；销账二件：FIELD_LABELS 扫尾（批六起沿袭）、collect_exprs dict 分支收窄（批六 nice-to-have 余一件）。
**P2**：§12 安全合规与 §13 非功能（平台级立项）；角色视图五套；批量复核/快捷键/断线恢复；双模型交叉；灰度 shadow；增量审查；创新点七项（历史胜率双方一致不做）。
**风险记档**：跳过「30 份真实文档评测」以 golden 合成件替代；未过规格上线门禁（fatal_recall≥0.97 档）带条件推进；golden 匹配权重 0.5/0.3/0.2 与规格 0.55/0.30/0.15 微差待对齐。

## 6.1 tender 33 字段权威差表（批五 2026-11-08 落账；批六 2026-11-08 复核刷新——⚠️2 兑付✅、❌11→❌4；批七 2026-11-08 兑付 ❌4→**0，33 字段差表全清**，规格 §6.2 要求集逐字段对仓库 universe 实跑 28 路径+C-09/C-18 别名裁决）

**✅ 已映射（20）**：project_identity（仓库拆 name/code/lot_section 三子键）；deadline→bid_deadline（C-16）；validity_days→required_validity_days；max_price；price_includes_tax；tax_requirement→tax_rate+price_includes_tax（规格 {rate,includes_tax} 拆二路径）；duration_required→max_duration；warranty_required→min_warranty_period；qualification_req→required_qual_level；mandatory_declarations→required_declarations（C-18）；clauses→substantive_clauses；boq_items（L2-041 在包消费）；file_composition；volume_specs；electronic_files；required_sections；scoring_items（B4 投影+抽取双通道）；attachment_requirements；signature_slots；required_fields。

**⚠️ 窄化（2，~~批六补全子键~~ → ✅ 批六 T4 已兑付 2026-11-08）**：performance_req→min_similar_performance_count（批六 T4 inputs 富化 min_performance_amount/performance_window_months，hyb prompt 自动富化，det_expr/tpl 逐字冻结，commit 2bd91a390）；deposit→deposit_required（批六 T4 L1-006 forms set_eq step 兑付 forms 维度——subset_of×2 双侧非空前置+独立 message_tpl+dedup_ent，声明同 commit；amount 走 bid.deposit_amount 既有消费，字段级全形视为闭环）。

**❌ 缺（11 → 批六兑付 5 + 挂账注记 2 + ~~批七清单 4~~ → ✅ 批七全兑付 2026-11-08，33 字段差表全清）**：
- **批六已兑付（5，随消费规则同批落地，A-β6-① 字段+消费规则同批红线）**：consortium_allowed（L1-017 联合体要件，det and-form+precondition）；tech_sections_required（L2-012 章节必备）；commitment_sections（L2-013）；required_figures（L2-014）；required_tables（L2-040，bid.tables 侧服务端派生 [sheet:X] 骨架扫描——L2-042/-043 仍缺列挂 P1 后续）。
- **挂账注记（2）**：attachment_count_reqs——L2-024 附件份数达标已担份数主责（att_count 消费 tender.attachment_requirements），规格字段名不另落，年份连续性（years() 引擎函数缺）挂批七+；sample_required——规格 §6.2 无规则卡（仅字段+extractor 行），3-layer 无消费不落，纯挂账待规格侧补卡。
- **~~批七清单（4）~~ → 批七已兑付（4，字段+消费规则同批 A-β7-① 红线）**：pm_req→**L1-004** hyb（项目负责人资格，det_expr count 门+op:eq 判定，inputs 6 叶键）；subcontract_limit→**L1-020** sem（分包冲突，L1-013 steps:[] 形态先例）；format_requirements→**L1-022** hyb（格式份数，op:and 合规式三支+null 字面量 skip——无明示跳过不触发，任一维显式违规出候选）+**L1-026** det（递交时间≤截止，L3-014 先例；规格注释误标 L1-026 系 format_requirements 消费——实态 L1-026 消费 bid.submit_time，format_requirements 由 L1-022 消费，编号勘误记档）；required_signatures→**L1-007 inputs 富化**（≠signature_slots 两字段并存维持，A-β7-③ 富化模式 det/op 逐字冻结）。A-β7-② 修订声明：抽取契约 8 容器→**21 叶平键**（normalize_fields 只收注册路径，容器注册+规则点消费未注册叶=live 永久 need_human 死锁；L1-001 bid.entity.* 先例，C-09 式拍平）；宇宙 105→126/包 55→59/golden 78→82。

**尾注（批五 T1 评审记档）**：L3 条目经 severity_change 人工升格 fatal 后计入 NOT_SUBMITTABLE（实现仅排 L4），规格 §5.7.2 严格字面为「L1/L2 fatal」——与 `_fatal_hits` layer 口径同构，实践合理，规格字面分歧记档不修；前端 GateMetricsRow 现零调用点（pill 惰性，同 verdictPill 先例，工作台顶条接线挂账）。

## 7. 审计方法附记

两轮审计均为只读代理证据核对（每条结论带 file:line 或规格行号），未采信任何未经代码验证的记忆性结论；11-05 审计中 4 项结论因并发兑付过时，已在本文件刷新。规格书位于仓库外（D:\knowbase），本文件为其在仓库内的裁决回写与对齐存档；规格侧本身的修订（W6~W8 回写候选、C 系列补充）待业务评审后另行提交给规格维护方。
