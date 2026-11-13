# 投标方案(商务部分)智能写作——P0 四技能规格(落地态)

日期:2026-11-13 · 批十九 T7 交付 · 分支:main-dev-fork
来源:用户提供《P0 四技能详细规格》全文(通用约定 §0 + bid_letter/price_sheet/response_table/attachment_index + 跨技能公共件 §5 + 排期 §6);本文档 = 该规格 **适配本仓真实路径与现行规则包** 的落地态转录。母设计:《投标方案(商务部分)智能写作》设计稿(F1–F9,P0/P1/P2)。

## 0. 与仓库真相的适配(先读;直接决定下面各节的取舍)

| 规格原文 | 仓库落地态 | 处置 |
|---|---|---|
| 契约文件 `bid_tender_common_schema.yaml` v2.4.0 | **repo 不存在**(愿景名);活契约=`bid_review/engine/extract.py FIELD_TYPE_CONTRACTS` | 写作端 import 复用,零复制;写作端新增词汇落 `bid_write/contracts.py`(SCHEMA_VERSION=1.0.0) |
| `tender.clauses(star)` | 不存在该路径 | 以 `tender.required_declarations` + `tender.attachment_requirements`(mandatory=="★")承接;`tender.substantive_clauses` 专项契约挂 M2(与 L4 激活同批) |
| `material.*` 素材实体 | M0 不建(设计 P1) | 槽位/断言按 D0 缺件诚实落(entity_ref 类一律缺件);素材六类实体批二十兑现 |
| `project.policy.*`(letter_defaults/tax_rates/调价开关) | 不存在 | 挂 P1 配置面;M0 有效期/税率走抽取值或人工确认 |
| `skills/assertions.yaml` | 断言属写作服务端非 agent 技能 | 落 `backend/app/extensions/bid_write/assertions/p0.yaml`(43 条含 CMN 共享层,注册表钉 `test_bid_write_assertions.py`) |
| 规则 id L1-018 / L3-015 / L2-010 / L2-042 / L4-011 | **现行两包不存在**(core 60=L1×21+L2×22+L3×17;L4=001..010) | 断言注册表只钉真实 id 或 null;映射见 §6 |

## 1. 通用约定(四技能共享,契约落 `bid_write/contracts.py`)

- **槽位语法**:`{{slot}}` 必填(缺失即断言失败)/`{{slot|default:"—"}}` 可选/`{{#if}}…{{/if}}` 条件段/`{{#each}}…{{/each}}` 循环段/`{{calc(expr)}}` 确定性计算(**禁 LLM 参与**)/`{{ref(entity_id)}}` 实体引用(渲染时校验存在性)。
- **槽位类型**:`str/enum/decimal(2位 ROUND_HALF_UP)/date(时序约束)/money(大小写成对)/entity_ref(素材实体)/list[T](非空·唯一键·覆盖率)/computed(重算比对)`。
- **降级等级**:D0 阻断(渲染 TODO 块+进待补清单+导出前置校验失败)/D1 降级(默认值填充+标黄+计预审查 UNKNOWN)/D2 提示(看板)/D3 静默。`BLOCK_EXPORT_LEVELS=("D0",)`。
- **断言编号** `SK-<SKILL>-<n>`、错误码 `E-<SK>-<n>` 一一对应;每条断言声明:判定表达式、失败等级、关联规则 id、是否阻塞导出——机器真源=`assertions/p0.yaml`。

## 2. 四技能(P0)

### 2.1 bid_letter 投标函(SK-BL,6 人日)

- 输入:`tender.*(deadline/required_sections/signature_slots/deposit)`+`price_sheet.total_amount`(**金额必须引用报价表结果**)+`material.bidder_profile`(主体信息,M0 缺位=D0)。
- 模板骨架:致(招标人)→一、投标报价(大写+小写)→二、投标有效期→三、承诺(保证金/真实合法/extra_commitments 逐条)→四、落款(盖章位+签字位+日期)。
- 槽位要点:`total_amount_cn/num` money D0;`bidder_name/legal_rep_name` entity_ref D0(**不允许模型补写企业名称类事实**);`sign_date ≤ deadline` D1;`extra_commitments` 逐条带 clause_id 溯源 D2。
- 禁用词五类(绝对化/模糊承诺/占位符/越权违规/法律表述漂移)——词表真源=`contracts.FORBIDDEN_WORDS`;法律表述漂移=固定段相似度<0.98 即 D0 回退模板原文。
- 降级:报价未定→D0 整体待补(法定要素);主体低置信→D1 标黄进人工队列;固定条款被改写→D0 回退+diff 留审计。
- 验收:3 份真实招标文件(含 1 份答疑修订)`SK-BL-001~009` 全绿;人工改写率 ≤15%;禁用词 0 命中。

### 2.2 price_sheet 投标报价表(SK-PS,8 人日;风险项=boq_items 解析)

- **硬约束**:算术全部代码完成(Decimal 中间 4 位落表 2 位 ROUND_HALF_UP,零浮点累加);**明细表唯一事实源**(开标一览/汇总/投标函金额全派生);单价=人工输入或历史价参考,**不自动出价**。
- 输入:`tender.boq_items`(宇宙真实路径,L1-011 input)+人工 `unit_price` 映射;`qty/unit` 与招标清单逐行一致(不得改数量 D0)。
- 计算:`line_amount=unit_price×qty`;`amount_with_tax=line_amount×(1+tax_rate)`;合计=各行求和;大写转换固定函数(单测 20 组边界值);改单价→全表重算+派生表同步+增量重审。
- 降级:清单覆盖率<100%→D0 切人工填表模式(CSV 导入),**禁止自动补行**;单价缺失→D0 留空标注;限价未抽到→D2 跳过 SK-PS-006 标注「限价未确认」;任何计算断言失败→D0 禁止「近似修正」。
- 验收:50 行清单用例 `SK-PS-001~008` 全绿;改单价派生表 100% 同步;重复运行零漂移。

### 2.3 response_table 商务响应表(SK-RT,7 人日)

- 输入:`response_matrix[]`(批十九 F1 落地,本批核心交付)+`tender.required_tables`+素材佐证。
- 模板:表二响应表(条款号/要求原文摘录/响应/结论/偏离说明/证据索引)+表三偏离表(仅偏离存在时;偏离原因+替代方案+是否★)。
- 铁律:★条款 100% 覆盖(D0)且零负偏离(D0)——生成期拦截与批十九 `PATCH matrix` 卡点(SK-RT-002 前置面)同一律;空应答(「满足招标文件要求」类)即 D0 补参数化应答;负偏离必须原因+替代方案闭环(D0)。
- 降级:★条款语义低置信→D1 标黄且不参与「完全响应」统计;无对应素材→D0 进待补清单(写明所需材料);摘录跨页→D1 截断留锚点;结论冲突→D0 以招标要求为基准回退。
- 验收:含 12 条★用例 `SK-RT-001~009` 全绿;注入 1 条★负偏离必须被阻断;空应答检出率 100%。

### 2.4 attachment_index 附件索引与目录(SK-AI,5 人日)

- 输入:素材六类实体(P1)+章节树(M1 F3)+`tender.attachment_requirements`+指纹字典与 `norm()`(**审查端已就绪,批十九前已外置**)。
- 模板:附件索引表(编号/名称/章节/页码/份数/状态/备注)+目录(标题…页码)。
- 要点:编号唯一 D0;要求逐项有索引项或标「待补」D0;悬空引用(见附件X 不可解析)D0;页码经 offset 校正 D1;**素材缺失生成占位行 status=待补进待补清单,不静默省略**(漏报直接相关设计点);`待补` 允许出现在 status=待补 的备注列,禁止出现在名称列 D0。
- 验收:20 附件场景 `SK-AI-001~009` 全绿;删除 1 素材实体必须出现待补行;悬空引用检出率 100%。

## 3. 跨技能公共件(§5 规格;M0 状态)

| 公共件 | M0 落地态 | 批次 |
|---|---|---|
| 断言执行器 | 注册表已落(`assertions/p0.yaml` 43 条含 CMN 共享层+levels 行为表+钉);执行器(注册表→可执行校验、D0 短路、`skill_run` 落库)未建 | M1 批二十 |
| 待补清单 | 数据面=`gaps` 端点诚实伪零(M0 全部「无对应素材」);可指派/闭环面未建 | M1/P1 |
| 导出前置校验 | 口径已钉(`BLOCK_EXPORT_LEVELS`;重跑全量 D0+四层规则,L1 fatal 阻断,L4 不阻断加风险水印) | M2 批廿一 |
| 埋点指标 | 未建(slot_fill_rate/assertion_pass_rate/D0·D1_count/manual_edit_ratio/latency_p95/retry_count) | P1 |

## 4. 排期(规格 §6,P0 合计 26 人日;M0 批十九已完成契约层=前置)

公共件 4 → attachment_index 5 → bid_letter 6 → price_sheet 8(boq_items 解析 POC 并行先行,覆盖率<0.95 则先交付「人工填表+计算内核+断言」)→ response_table 7 → 导出前置+埋点+回归 3。风险与对策照录规格 §6。

## 5. 断言注册表(机器真源)

43 条断言(BL 10 / PS 10 / RT 9 / AI 9 / **CMN 共享层 5**)的 id/name/level/blocks_export/rule_ref/expr 全量真源 = `backend/app/extensions/bid_write/assertions/p0.yaml`,钉 = `backend/tests/test_bid_write_assertions.py`(编号连续/规则锚真实/级别词汇/D0⇔blocks_export/错误码一一对应/硬门 D0 下限/总数 43/**levels 行为表**/**delegates_to 单实现律**/CMN 层范围)。本文档不复制逐条表(双真源=漂移)。

### 5.1 v2 增量吸收裁决(2026-11-13 二版规格)

已吸收(落地):
- **levels 行为表**——D0..D3 每级行为元组(blk/render/todo/pre_review_state/retry)入 yaml,执行器(批二十)按表分派,不再靠约定;D0 blk=true 其余 false 有钉。
- **SK-CMN-001..005 共享层**——导出级全文面(占位符/绝对化/未登记实体引用/渲染可重放/待补必带负证据)从四技能抽出为 CMN 技能,`contracts.SKILL_IDS += "CMN"`;技能级只做本技能范围。
- **delegates_to 单实现律**——SK-AI-009(负证据留痕)delegates_to SK-CMN-005:同口径只允许一份实现,执行器不重复跑,SK-AI-009 仅登记技能级 ID 与错误码;钉保证目标存在。

未吸收(愿景面,挂账):
- `shared_schema schemas/bid_tender_common_schema.yaml@2.4.0`——repo 无此文件;tender.* 真源=审查端 `FIELD_TYPE_CONTRACTS` import 复用(既定裁决不变)。
- `namespace_delta 2.5.0` / `operator_delta 21 det` / `slot_syntax`+`validator_registry 34`+`lexicons 8 类`——执行器落地面,随批二十执行器按需引入,注册表 M0 不预置空骨架。
- `metrics.gates.WR_pack` / `executor`/`todo_list`/`export_gate`/`static_checks`/`tests`(MUT-026..029 注入算子)——属执行器与测试集范畴(见 §7 批二十)。
- 「L2 包尚未落盘」说法本仓不成立:L2 22 条规则在 core 包内,断言 rule_ref 直接引用即可。

### 5.2 v3 对账裁决(同日三版)

已吸收(落地):
- **human_action 待补清单话术**——43 条全量入 yaml(M1 todo 消费;`null`=处置自动闭环,如 SK-PS-004 大小写重算);钉 test_human_action_present 保证在位。
- **输入面补漏**——`tender.required_validity_days` 入 `COMMERCIAL_TENDER_SUBSET`(21→22 条;SK-BL-003 有效期操作数,L1-005 同 input,universe 真实成员)。

未吸收(裁决):
- **SK-BL-011 拆分**(禁用词按等级拆两条断言)——不取:已落 CMN 层覆盖同语义(全文占位符=SK-CMN-001 D0;绝对化/越权=SK-CMN-002 D1+运行时词级 max);同一扫描跑两遍是浪费。v3 「混合等级无法执行器判定」的顾虑在本仓语义下不成立——`level`=静态下限,运行时按 `FORBIDDEN_WORDS` 词级取 max,词表自带等级,levels 表分派。
- **rules[] 多锚 + 指标标签**(fact_consistency/determinism_drift/anchor_alignment/missing_policy/compliance_redline)——M1 执行器面:单 `rule_ref`(真实 id 或 null)的幽灵拒载律保持;指标标签属 metrics 模块词汇(P1 挂账),不入断言注册表混淆命名空间。
- **err_code / evidence_required / dynamic_rule 显式字段**——err_code=`contracts.error_code(skill,n)` 派生(钉已保证一一对应);evidence_required 全 true、dynamic_rule 全 null=常量。常量与派生字段写进 yaml=漂移源。
- **on_fail 字段**——等级处置已由 levels 行为表(render/todo/retry)承担;断言特有处置(回退模板原文/CSV 人工填表等)已写进各条 expr 注。

## 8. 断言执行器 v0.1 原型裁决(批二十 M1 设计输入,2026-11-13)

外部原型《Assertion Runner v0.1》(4 技能/39 条/28 D0 口径)收进本节,按 repo 真相适配后为批二十 M1 开工件。口径修正:落地注册表=43 条/31 D0(含 CMN 共享层,见 §5.1)。

采纳(设计成立,直接沿用):
- **目标/非目标**——只消费快照不回写业务数据;相似度类断言吃预计算值注入(`pre.*`),`deterministic=false` 单独统计;加载期静态校验(ID 唯一/级别⇔导出/引用不悬空)= 既有注册表钉的服务端复刻。
- **执行语义**——D0→D1→D2 排序(同级按 assertion_id 字典序,结果可复现);D0 失败短路范围默认 `skill`(本技能剩余断言 SKIPPED,其他技能继续);上下文缺失=`ERROR` 视为失败(`E-CTX-MISSING`)不得静默通过——与「诚实伪零」同律。
- **SKIPPED 可解释性**——报告必须注明「因 SK-XX 失败跳过 N 条」,防误读为通过。
- **导出门禁**——任一 blocks_export 断言 FAIL 或任一 L1 fatal=VIOLATION → 阻断;L4 critical 未确认 → 只加「商务风险未确认」水印(`l4_counts_toward_gate: false`)。与审查端「商务风险非否决项」隔离口径一致(= §3 既有钉)。
- **职责分界**——「断言管生成期、规则管交付期」:SK-PS-003 与 L1-010 语义重叠处,报告中分开展示、不重复计入缺陷数。
- **确定性验收**——同输入重跑结果一致(20 次字节级);确定性 zero-drift 与 SK-CMN-004/PS-008 断言闭环。

适配(repo 真相改写):
| 原型 | 落地态 | 依据 |
|---|---|---|
| `tools/assertion_runner/` 独立目录 | `app/extensions/bid_write/executor/`(loader/models/runner/gate/report + validators) | 新功能独立模块律;app→app import 合法,与 matrix/worker 同居 |
| 受控 DSL(AST 白名单求值器) | **不建通用 DSL**;每条断言一个 Python 校验函数,按 `assertion_id` 注册(dict[str, callable]),expr 语义注释=实现验收基准 | 43 条断言的 DSL 解释器=过度工程;Python 校验器无 eval 面,类型安全;原型自己也承认 v0.2 要迁声明式条件树——不如一步到位用注册表函数 |
| `runs/run-xxx.json` 文件 sink | `skill_run` 落库(bid_write 新表,M1 模型层;JSON 报告=导出物非真相源) | 与 bid_write_tasks/matrix_rows 同库同机制(bug-4303 教训:共享 Base) |
| YAML 加载期版本比对 shared_schema@2.4.0 | 版本比对对象=`contracts.SCHEMA_VERSION`;shared_schema 文件不存在(§5.1 裁决不变) | 幽灵路径拒载 |
| CLI 退出码 0/1/2/3 | 保留为金标准 oracle 适配面(CI/离线批跑);Gateway 主通道=in-process worker 调用 | 审查端同形(worker 直调,非子进程) |
| PendingItem CSV | 待补清单走 `gaps` 端点既有数据面(M0 诚实伪零→M1 按断言结果真实产出) | routers 既有面 |

M1 骨架验收(= 批二十 TDD 序):loader+models+runner 跑通 1 技能 → 全量 43 条(逐条校验函数)→ 待补清单+gate+注入负例全红 → 确定性 20 次一致+CI 门禁。注入负例清单(每技能 8–12 条)随骨架 TDD 产出,不单独立项。

## 6. 规格规则 id → 落地态映射(逐条裁决)

规格原引用而现行两包不存在的 id 一律不进注册表(幽灵 ref 拒载);真实锚定与写作端新增如下(详细理由已写进 yaml 每条 expr 注):

| 规格断言 | 规格原引 | 落地态 rule_ref | 依据 |
|---|---|---|---|
| SK-BL-003 有效期达标 | L1-016 | **L1-005** | L1-016 实为「投标主体全文档一致」;有效期规则=L1-005 |
| SK-BL-004 主体一致 | L1-018 | **L1-016** | L1-018 不存在;主体一致=L1-016 |
| SK-BL-005 日期合法 | L1-016 | null | sign_date≤deadline 时序校验,审查端无对应规则(写作端新增) |
| SK-BL-010 承诺可溯源 | L3-015 | null | L3-015 不存在 |
| SK-PS-001 清单覆盖 | L2-042 | **L1-011** | L2-042 不存在;清单漏项=L1-011 |
| SK-PS-009 无模糊调价 | L4-011 | null | L4 包止于 010;模糊调价词级 D0 升级走 FORBIDDEN_WORDS |
| SK-PS-010 异常低价 | L1-022 | null | L1-022 实为「格式份数密封」;异常低价=写作端新增(历史价参考) |
| SK-RT-005 偏离闭环 | L1-014 | null | L1-014 实为「承诺工期」;偏离闭环=写作端新增(PATCH 卡点同律) |
| SK-RT-006 与正文一致 | L3-003+L3-015 | **L3-003** | L3-015 不存在;L3-003 真实锚定 |
| SK-RT-008 结论与内容匹配 | L3-015 | null | 同上,写作端新增 |
| SK-AI-008 目录一致 | L2-010 | null | L2-010 不存在;目录一致=写作端新增 |

其余断言的原引 id(core 26 处+L4-002)均真实存在,原样锚定。

## 7. 挂账(不入 P0-M0)

**执行器落地态(批二十 M1-a..d,2026-11-13)**:§8 裁决全量兑现——executor/ 六件(loader/models/runner/gate/report/cli+validators/{ai,cmn,bl,ps,rt,amount_cn,wordscan});43 条校验函数全注册(委托 AI-009=CMN-005 单实现);exec-negatives.yaml 19 例负例全红;确定性 20× 字节级;CLI oracle 0/1/2;SkillRun 落库+gaps 断言维度。**未入 M1 挂账**:worker 生效链(record_skill_run 接线进 advance 后置 M2 导出前置同批);BL-001「12 个必填槽位」第 12 槽位无 repo 真源(L1-007 实为签章完整,input 无槽位清单)→执行器按 yaml expr 点名 11 项,第 12 槽位待 F4 模板落地时锁定;执行期 rule_ref 悬空面=CI pin(运行时不重扫,§8 适配表既裁)。
剩余:M1 面收尾=F3 章节装配+F4 四技能生成器(读本文档 §2 骨架);M2(批廿一):F6 预审查(L1/L2 复用 rule_runner/eval_core,输入=生成过程产出的 bid.*)+导出前置校验+worker 接线;P1:素材库六类实体+policy 配置面+埋点+前端三栏工作台;`tender.substantive_clauses` 契约与 L4 激活同批(M2)。
