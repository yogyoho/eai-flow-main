# 天玛智控市场营销域本体建模详细方案

- 日期：2026-10-07
- 依据：《Palantir 本体实操指南》三部曲（方法论 / 交付稿 / 三元组+规则+问数样例）+ OntoStudio 平台实况（market.yaml v1 已于 2026-10-06 入册）
- 关联：`ontostudio/backend/app/ontology/registry/market.yaml`（TBox 已落地）、`docs/designs/2026-10-06-ontostudio-vs-palantir-ontology-completeness.md`（平台完备性评估）
- 状态：PROPOSED（待评审）

## 1. 背景与目标

天玛智控（688570.SH，SAC/SAM/SAP「大脑—神经—心脏」三大产品线）的营销数据分散在 CRM/ERP/SRM/MES/APS/招投标平台/售后系统及外部政策公告等异构源。营销本体要回答四件事：**有哪些对象、各自代表什么、彼此如何发生关系、受什么规则约束**——它定义含义，图谱承载实例，流程引擎推动步骤，Agent 编排层调用工具。

四个业务价值锚点（来自设计指南，直接决定建模优先级）：

1. **长周期项目型销售可视**：线索→示范面→招投标→合同→验收→回款→备件复购，6–24 个月跨系统断点多
2. **多层级客户穿透**：能源集团→二级子公司→矿井→工作面，决策链与装机存量分布在不同层级
3. **资质与配套硬约束推理**：MA/IECEx/ATEX 证书、主机厂配套关系直接决定「能不能投」
4. **存量+第二曲线精细经营**：已装机设备—服役年限—易损件—改造窗口的串联

## 2. 分层架构：指南蓝图 → OntoStudio 实况映射

指南建议「TBox 用 OWL/Protégé + ABox 用属性图」双栈并存。**OntoStudio 已把双栈合成为一个工程正典**，无需另起 Neo4j/Protégé：

| 指南分层 | OntoStudio 落点 | 状态 |
|---|---|---|
| TBox 概念层（OWL 类·属性·公理） | `registry/market.yaml`（etype/谓词/etype_classes/formal 公理）→ kernel 编译为 OWL/RDF schema 图（pyoxigraph） | ✅ v1 已落地（20 etype/21 谓词/传递归属公理） |
| ABox 实例层 | `dg_entities/dg_relations/dg_mentions`（domain=market，零 DDL）+ kernel 断言图 | ✅ 容器就绪，**待灌数** |
| 推理层（SHACL + 规则引擎 + 概率） | owlrl 闭包（graph:entailment）+ CONSTRUCT 派生（graph:derived:*）+ SHACL 全图校验 + 应用层规则引擎 | ✅ 平台能力，**market 规则未配** |
| 治理层（术语词典/主数据/质量门控/版本/Owner） | 建模器（registry 编辑+fingerprint 乐观并发）+ 人审闸门（force_review+消解审核）+ 国标 C1-C5 门禁 + git 版本 | ✅ 平台能力 |
| 应用层（Agent 编排：问数/画像/预警/复用） | ontology MCP（17 工具）+ doc-graph MCP（5 工具）+ ontology-graph-query / doc-graph-extract 技能 | ✅ 通道就绪，**market 意图路由未配** |
| 数据源层（CRM/ERP/爬虫） | **缺口**：MarketExtraction 域分发器（TODOS「抽取管线多域化」）+ CRM/ERP ETL 映射 | ❌ 本方案 §6 |

**结论**：平台侧（TBox/ABox/推理/治理/Agent 通道）五层已备，market.yaml v1 已入册；本方案把指南的模型细节**补全到 market.yaml v2**、把规则与问数**配到平台三层**、把数据接入**做成域分发器 + ETL**。

## 3. TBox v2：从 20 etype 补全到指南全集

market.yaml v1 已覆盖 MVP 四类簇+差异化资产。v2 按指南 §三 的 8 类簇补齐（分两批，宁窄而准）：

### 3.1 第一批（+8 etype，补齐八类簇骨架）

| etype | 类簇 | 中文 | 关键 attrs 约定 |
|---|---|---|---|
| market_segment | 市场与客户 | 市场细分 | attrs.region（区域枚举：华东/西北/国际-澳洲/国际-俄罗斯…） |
| decision_unit | 市场与客户 | 决策单元 | 决策者/技术把关/采购/使用者四角色经 decides_by 关联 |
| service_item | 资产与服务 | 服务项 | 后市场服务目录（维修/改造/培训） |
| spare_part_demand | 资产与服务 | 备件需求 | 衍生自 installed_base + 服役年限（derived_from 关系） |
| component | 资产与服务 | 部件 | 易损件清单（与 product_model 的组成关系） |
| lead | 商机与交易 | 线索 | 商机前置态（originates_from 链头） |
| price_benchmark | 竞争与情报 | 价格基准 | 竞品中标价分位数（Q10 问数数据源） |
| news | 竞争与情报 | 情报资讯 | attrs.kind=资本开支收紧/评级下调（触发 R12 风险传导） |

### 3.2 第二批（按场景触发，先记词表不入枚举）

quota（指标）、exhibition/training/campaign（活动触点）、content_asset（内容资产）、invoice/payment（发票/回款——与财务域对接缝，主数据源约定后再落）、oem_host（主机厂——若 pairedWith 升格实体）。

### 3.3 谓词扩展（21 → 约 34）

在 v1 的 21 个谓词上补：`holds`（竞品持有证书）、`of_model`（设备→型号）、`for_product_line`（结果→产品线，失标归因维度）、`completed_for`（示范面完成于某集团）、`capital_plan_contains`（矿井资本开支含改造——或作 attrs 字段，建模评审定）、`at_site`（联系人驻点）、`includes`（方案包含型号）、`for_product`（证书针对型号）、`belongsTo`（销售员隶属）、`for_region`（证书准入区域——与 qualified_for 的推导关系见 §5）。

### 3.4 属性约定（沿用 v1 三原则）

- **业务属性**进 `attrs` JSONB（摊平）：商机阶段状态机、金额+币种、失标原因码（C01–C99 枚举禁自由文本）、证书 valid_from/to、服役年限、is_related_party
- **治理元数据**走表列：created_at/updated_at/valid_from/valid_to + mention 证据链（quote 逐字溯源）——指南「治理元数据不能省」已由表结构保证
- **同义词典**：`norm_name`（归一化主名）+ `attrs.aliases` 数组（如 SAC=支架电液控=电液控制系统；榆家梁煤矿=榆家梁矿）——与 eia 域 pollutant_concept.aliases 同模式
- **黄金值铁律**：多系统可取的字段只存一份权威值，其余作 `attrs.provenance`（来源系统/置信度/更新时间）旁挂，不做合并覆盖

## 4. 关系与状态机

v1 谓词已覆盖指南 22 条关系中的 17 条；v2 补齐后约 30 条。两个指南预先要求定规矩的取舍，落定如下：

1. **关系升格实体的判断**：quote（报价）、bid（投标）、tender（标段）、pilot_project（示范面）已实体化 ✅；paired_with（配套协议）v1 作边+valid_from/to，**若出现佣金/多版本管理再升格** oem_host 实体（触发条件记 TODOS）
2. **时序与版本**：关键关系一律挂 valid_from/valid_to（表列已备）——V6 时序正确性用例（集团归属变更后历史商机仍挂原时段）的模型保证；组织调整（served_by 变更）同样走时序边不做覆盖写

**商机阶段状态机**（固化进 attrs.stage 枚举 + 校验规则，不沿用 CRM 默认）：
`线索 → 初步接触 → 需求确认 → 技术方案/示范面 → 投标立项 → 报价审批 → 投标 → 中标/失标 → 合同生效`；阶段回退留痕（回退次数/原因进 attrs）；每阶段停留天数上限（超期降权触发 R14）。

## 5. 规则层：R1–R15 的三层落位

指南的 15 条规则不是同一层的东西，按「图上可推导 / 数据形状 / 需动外部系统」切三层落：

| 层 | 规则 | 落点 |
|---|---|---|
| **kernel 形式化层**（registry formal 段，已验证机制） | V1 传递归属（belongs_to_group transitive + located_at 链）✅ 已落；`qualified_for` 推导（certificate for_product + 证书有效 → 型号 qualified_for region——需证书时效进图，作 CONSTRUCT 规则） | formal 段 + rules_registry |
| **SHACL shapes 层**（数据形状，校验中心消费） | R2 报价唯一性（同一商机至多一份 status=正式 quote）、R9 失标码必填且枚举内、R10 撞单（同 Site+产品线在途唯一）、证书 attrs 必填 valid_to | market shapes 集（新 shapes 文件，校验中心「重新校验」消费） |
| **应用层规则引擎**（主系统/CRM 流程绑定，ERROR 真阻断） | R1 准入拦截（读 requires_cert − qualified_for 图上缺口→阻断+建任务）、R3 归属裁决、R4 示范面前置降权、R5 预测失真、R6 关联方审批流、R7 证书到期批处理、R8 存量线索生成、R11 交期对 APS、R12 风险传导、R13 活动归因、R14 僵尸商机、R15 配套锁定 | 主系统规则配置表（指南交付稿表结构直接采用），图上查询走 ontology MCP |

**分级纪律**（指南三提醒之二）：ERROR 必须真阻断流程、WARN 落到责任人待办、INFO 进看板——只做看板不做阻断，三个月后本体就「只是个报表」。

**演示第一幕**（指南自证用例，接 v1 数据后可跑）：标段要求 MA+IECEx → 我方 IECEx 证书 2026-01-09 到期 → R1 阻断 + R7 续期任务同时触发，缺口={IECEx}。

## 6. 数据接入：域分发器 + ETL 映射

### 6.1 MarketExtraction（非结构化抽取，补多域化缺口）

- `schemas.py` 新增 `MarketExtraction(ExtractionPayload)`：`domain: Literal["market"]`、`domain_etypes` = §3 全集、谓词角色对表（如 bids_on: (bid, tender)、has_installed: (working_face, product_model)、results_in: (bid, bid_result)…照 eia `_EIA_PREDICATE_ROLES` 模式，fail-closed）
- 分发器：`ingest_tasks.py` 按 payload 判域分发（BidExtraction/EiaExtraction/MarketExtraction）——即 TODOS「抽取管线多域化」的落地体
- 非结构化源（招标公告/政策文/获奖报道）走「LLM 抽取 + 术语词典约束（attrs.aliases）+ 人工抽检」；**资格要求结构化**（必需证书/最低业绩台数/交期上限）是 R1 的输入源，优先做

### 6.2 结构化 ETL（CRM/ERP 主数据回填）

- 主键锚点：CRM 客户主数据、ERP 合同订单；实例 ID 双段式 `CRM-OPT-20260017`，跨系统 `same_as` 关系对齐
- 字段口径映射（指南 §六表直接采用）：签约额=ERP 合同生效金额（CRM 预计金额≠此，问数须标注口径）；在手订单=未交付（与计划域对齐）；赢单率分母=投标数；已装机靠验收单+人工补录回填（缺失最多的一块）
- 行域标记 `domain='market'`、`extracted_by='etl-crm-erp-v1'`，走既有 ingest 管线入 force_review 人审闸门

## 7. 应用形态：问数意图路由 + 两个 Agent

- **智能问数（①优先）**：指南 18 个意图（Q1–Q18）逐条映射到 ontology MCP 工具组合（aggregate→Q1/Q3/Q4、list_objects+filters→Q2/Q15、traverse→Q8/Q9、get_rule_violations→Q11/Q12…）+ **口径脚注强制**（每个输出带口径说明+数据来源+截至时间——「两个人问出两个数」是问数项目的死穴）
- **拜访前准备 Agent**：ontology-graph-query 技能扩展 market 段（belongsToGroup* 展开集团树 → has_installed 装机年限 → competesIn 历史对手 → PilotProject 案例输出）
- **投标合规自检 Agent**：R1/R7 图上缺口计算走 ontology MCP，阻断动作走主系统——「事后补救变事前拦截」，业务接受度最高
- 意图层约定（写进路由表）：时间缺省=自然月/年+标注截至日期；组织模糊匹配走 same_as 禁字符串包含

## 8. 验收门（V1–V7 在本栈的跑法）

| 用例 | 本栈验证路径 |
|---|---|
| V1 传递归属 | market.yaml formal 公理 → 推理工作台 infer → 查 working_face 的 belongs_to_group（**已可跑**，公理已入册） |
| V2 存量线索生成 | R8 应用层规则 + derived_from 关系落库 |
| V3 准入拦截 | R1 应用层 + 图上缺口查询 |
| V4 失标归因 | aggregate(bid_result, group_by=attrs.reason_code) |
| V5 口径隔离 | Q1/Q18 意图口径脚注 |
| V6 时序正确性 | valid_from/to 表列 + 时序边约定（模型已保证） |
| V7 实体对齐 | same_as 关系 + norm_name/aliases |

V1/V6 模型侧已自证；V2–V5/V7 依赖 §5–§7 落地后逐条过。**全部通过前不扩类簇**（指南铁律）。

## 9. 实施节奏（平台已备，比指南预估大幅压缩）

| 阶段 | 内容 | 交付物 |
|---|---|---|
| 第 1–2 周 | 术语词典第一版评审（工作面/矿井/集团三级定义、示范面定义、失标码表确认）；market.yaml v2 批次一入册 | 词典定稿 + TBox v2 |
| 第 3–6 周 | MarketExtraction 分发器 + CRM/ERP ETL 映射（垂直切片：选一个集团客户把矿井/工作面/装机/近两年投标串通） | 垂直切片图谱 + R2/R9 SHACL |
| 第 7–10 周 | 规则三层落位（R1/R7/R8 先行——拦截/预警/生成三型各一）+ 智能问数 Q1/Q4/Q8/Q13 四意图 | 准入拦截 Demo + 问数 Demo |
| 第 11–16 周 | 竞争情报/政策外部源接入；拜访准备+投标合规两 Agent；V1–V7 全量验收 | 营销本体 V1.0 + 治理规范 |
| 持续 | 季度本体评审（建模器+国标门禁+人审闸门即治理机制）+ 事件触发更新 | 版本化演进 |

## 10. 治理与坑位（指南八坑的本栈对应）

1. **不做数据字典**：market.yaml 有谓词/公理/规则三层，推理能力在册（V1 公理已可跑）
2. **不一次到位**：v2 分两批，第二批全部触发条件驱动（TODOS 在册模式）
3. **关联方**：is_related_party 已入 attrs 约定 + R6 审批流隔离——披露口径问题前置
4. **国际化**：certificate/market_segment 的区域与认证体系一等公民建模（attrs.region 枚举含国际）
5. **Owner 双轨**：业务 Owner=营销管理部、技术 Owner=本体平台维护方——立项时写死，进治理规范
6. **本栈特有提醒**： OntoStudio 动作面尚未含 market 专属动作（复用 review_entity 通用人审即可，勿过早扩）； MCP doc-graph 服务名沿用历史命名（勿在本项目顺手改名——Agent 配置与技能引用会断）

## 11. 待评审决议项

1. 术语词典第一批 20 条（指南 §二表）的业务确认——尤其「工作面/矿井/集团」三级定义与「示范面」判据
2. R1–R15 中 ERROR 级的阻断位置（CRM 流程节点 vs 本体动作层）——需与主系统流程引擎对齐
3. 垂直切片的集团客户选取（建议：装机存量密、近两年投标活跃者）
4. 失标原因码 C01–C99 是否直接启用（业务侧确认后即写入 attrs 枚举约束）
