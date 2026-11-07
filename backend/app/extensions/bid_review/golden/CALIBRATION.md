# 建库校准记录

流程(spec §9):每题①按 trigger 表构造最小字段 → ②跑引擎取现输出起草 expect_issues →
③逐处 diff 裁决:引擎对→修标注 / 标注对→修引擎 bug(buglog 记录,此处记编号与结论) →
④入库后该题必须绿。裁决格式:`| case | 裁决 | 结论/bug编号 |`

## 四态判定决策表(L2 专项题裁决依据,口径唯一,spec §1.5 采纳)

| 事实 | 金标准态 |
|---|---|
| 检索过且确认不存在 | MISSING |
| 存在但子件/份数不足 | PARTIAL |
| 存在且齐备 | MATCHED(PRESENT) |
| 解析失败/分组失败/语义低置信 | UNKNOWN(引擎侧=need_human) |
| 抽取失败被误判为缺失 | 标注错误示范,不入库(记录进培训集) |

## 批A(L1×17 + A族×3)裁决表

rulepack 实有 L1=17 条(计划表估 20 与文件不符,以文件为准;L1-004/017/018/020 不存在)。
L1-009 复用既有 L1-009-over-max-price.yaml,未新建。除下表「标注对」两行外,
各题均为「引擎对」:期望按引擎现输出起草,逐处 diff 后与 rulepack 触发语义逐字核对一致。

| case | 裁决 | 结论/bug编号 |
|---|---|---|
| L1-001-license-scope | 引擎对 | 执照有效期 "2026-01-01" < 截止 "2026-06-30"(ISO 串词法比较,日期值一律 YAML 加引号防 PyYAML 转 date);covers 子串包含达标,单因触发 |
| L1-002-qual-level-low | 引擎对 | covers 串包含判定(无序数比较器,v2);消息含要求等级与投标列表原文 |
| L1-003-performance-short | 引擎对 | hyb 粗筛 count<min 产候选 → scripted partial → violation(major=rulepack);message 占位符剥离为 _render_message 既定行为,尾缀 "(clause_id: reason)" 上下文摘要入 contains 钉 |
| L1-005-validity-short | 引擎对 | 60<90 gte 违例,消息含两值 |
| L1-006-deposit-mismatch | 引擎对 | eq 违例;:money 渲染 ¥50,000.00/¥100,000.00 入 contains 钉语义 |
| L1-007-signature-missing | 引擎对 | hyb 粗筛非空产候选 → scripted partial → violation(fatal=rulepack);同 L1-003 占位符剥离钉法 |
| L1-008-signatory-mismatch | 引擎对 | steps 双条件;授权书存在性达标、签用人不一致单因触发 |
| L1-009-over-max-price | (既有) | T1 期已入库,本批未动 |
| L1-010-price-sum-mismatch | 标注对 | 计划草样 detail_rows 行键用 total,rulepack 契约读 `[*].amount`(DEMO-001 field_snapshot 同证)→ 夹具改 amount;引擎求和/渲染均正确 |
| L1-011-boq-missing-item | 标注对→引擎bug已修 | 见下「引擎修复 #1」;修复后 漏项=tender−bid、增项=bid−tender 与规则名/fix_tpl 语义一致 |
| L1-012-tax-rate-mismatch | 引擎对 | op:all 逐出现值;0.09≠0.13,消息含出现处 where |
| L1-013-substantive-clause | 引擎对 | 计划草样 severity=major 与 rulepack fatal 不符,以 rulepack 为准(标注修正);scripted partial → violation(fatal),message="实质性条款 ★1 响应为 partial:响应偏离" |
| L1-014-duration-over | 引擎对 | 原始数值按 normalize_unit 天口径;200>180 |
| L1-015-warranty-short | 引擎对 | {value,unit} 结构月×30(360<720);_fmt 渲染 "12个月"/"24个月" 入 contains 钉 |
| L1-016-entity-name-mismatch | 引擎对 | op:all 逐处;出现值与执照名差「制造」二字,消息含 (where) |
| L1-019-alternative-offer | 引擎对 | count≠0 即违例;消息含替代方案描述串 |
| L2-031-declaration-missing | 引擎对 | all-in 差集(清单外自附不算违规);缺 DECL-INT 单条 |
| A-1-clean-price | 引擎对 | 价格族全达标零 violation;detail_rows 行键同 L1-010 改 amount(strict=True,need_human 全数容忍) |
| A-2-clean-qual | 引擎对 | 资质族(L1-001/002)全达标零 violation;日期串加引号 |
| A-3-clean-mixed | 引擎对 | 有效期/质保/保证金/声明函族全达标零 violation;bid 自附额外声明函 DECL-EXTRA 不触发=all-in 语义 FP 探针 |

## 引擎修复 #1(批A唯一)

- **位置**:`backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml` L1-011 check(L58-60 → EAI-CUSTOM 注释块)
- **现象**:招标清单有 BM-003、投标清单缺之(典型漏项),引擎消息渲染为「清单不一致:漏项  ,增项 BM-003」——漏项/增项与事实互换。
- **根因**:rule_runner set_eq 渲染契约为恒等式 `{missing}`=right−left、`{extra}`=left−right(L3-007「仅技术标出现 {missing}」实测同款,求值器与该契约自洽);L1-011 却声明 left=tender/right=bid,使真漏项(tender−bid)落 {extra}、投标自附项(bid−tender)落 {missing}。声明侧转置,非求值器缺陷。
- **红先证据**:L1-011-boq-missing-item.yaml 按正确标注(contains "漏项 BM-003")跑出 RED(关键词未命中,引擎现输出为「增项 BM-003」);修复后 GREEN。
- **修法**:L1-011 left/right 对调为 `left: "codes(bid.boq_items)"` / `right: "codes(tender.boq_items)"`。备选方案(求值器统一反转 miss/extra)否决——会破坏 L3-007 消息契约。
- **为什么标注对**:规则名「清单无漏项、无擅自增项」+ fix_tpl「删除擅自新增项或补充漏报项」语义唯一:漏项=tender 要求而 bid 未报。若按现输出钉 contains,即把 bug 固化成标准(spec §9 明否)。
- **buglog**:由 controller 落账;后续挂账:同源 M1 副本 `skills/public/bid-proposal-review/references/rules-det-subset.yaml`(L52-53)载同一转置声明,属技能分发件(bid_review/ 之外),批A未动,须另行对账。

## 批A运行时行为备忘(建库时实测,T2+ 建库者直接受益)

1. **sem/hyb script 三道闸**:evidence 在 docs_text=""(golden runner 缺省)下必走「证据未对齐」降级 → issue.need_human=True 但 verdict=violation 不变;期望匹配不理 need_human 旗标,严格度不受影响。confidence 须 ≥ rulepack confidence_gate(0.75)否则 gate_confidence 转 need_human(verdict 变 need_human → 期望失配)。reason/fix/evidence 文本过 injection_guard(勿含「忽略…要求」「请你扮演」等句式)。
2. **hyb 消息形态**:llm_runner._render_message 对含字段占位符的 message_tpl(如 L1-003/L1-007)剥占位符并尾缀 " ({clause_id}: {reason})";contains 钉「规则关键词 + scripted reason 子串」最稳。L1-013 的 tpl 占位符全由 ctx 供给,消息为纯渲染无尾缀。
3. **det 消息直接可钉**:message_tpl 占位符由 fields+extra 渲染(:money 千分位、list 顿号连接、{value,unit} 中文单位),contains 从现输出照抄即可。
4. **日期值一律加引号**:PyYAML 把裸 `2026-01-01` 转 datetime.date,与 str 混比会 TypeError→逐规则隔离降级 need_human(假阴性)。
5. **A 族 strict 语义实测**:未供 inputs 的规则全部落 need_human(not counted),供齐且 PASS 也不产出——A 族只需保证「供齐的族全 PASS、供不齐的族宁缺勿错」。
6. **命名字**:loader `_NAME_RE` 要求 `^[A-Z0-9]+-[0-9]+-[a-z0-9-]+$`,A 族计划草名 A-clean-l1-* 不合法(第二段须数字),本批落地为 A-1/A-2/A-3-。

## 批B(L3×15)裁决表

rulepack 实有 L3=15 条(计划标题 16 与文件不符,以文件为准;L3-011/015/017 不存在;det 13 条 + hyb 2 条)。
全部为「引擎对」:期望按引擎现输出起草,逐处 diff 后与 rulepack 触发语义逐字核对一致;零引擎修复,rulepack 未动。

| case | 裁决 | 结论/bug编号 |
|---|---|---|
| L3-001-header-project-name | 引擎对 | 页眉名多「利用」二字单因触发;声明 inputs 的 tender.project_identity.code 虽不入 check 表达式也须供齐(缺字段两段检查:表达式段通过后仍查 inputs 段),缺则整规则 need_human 假阴性 |
| L3-002-tenderee-name-mention | 引擎对 | op:all 逐出现;达标出现处(投标函)不产条目、违例出现处(承诺函)单条;消息措辞「与招标公告…不一致」系 message_tpl 原文 |
| L3-003-entity-license-whitelist | 引擎对 | and 两条件:署名≠执照名 False、执照名在白名单内 True → 单因触发;消息含「疑似简称/错别字」尾缀 |
| L3-004-old-project-residue | 引擎对 | hyb 粗筛 count≠0 产候选 → scripted partial → violation(major);占位符剥离后消息「残留旧项目名: (非本项目) (OLD-PRJ-1: reason)」,contains 钉规则关键词+scripted reason 子串(同批A L1-003 钉法);白名单外模型驳回(full)场景由安静应答默认覆盖 |
| L3-005-duration-triple-mismatch | 引擎对 | normalize_unit 归一:进度表 18个月=540天达标、承诺函 12个月=360天违例,单因触发;工期字段须数值或 {value,unit} 结构,裸中文文本(如 "18个月")float 强转失败 raise KeyError→need_human,勿入题 |
| L3-006-amount-occurrence-mismatch | 引擎对 | op:all 逐出现;:money 渲染 ¥48,000,000.00/¥98,000,000.00 入 contains 钉值 |
| L3-007-personnel-set-eq | 引擎对 | set_eq 双向差集钉死渲染契约:left=commercial/right=technical → missing=right−left=「仅技术标出现」、extra=left−right=「仅商务标出现」,消息与声明语义一致(L1-011 转置类回归守;声明本批未动) |
| L3-008-device-model-mismatch | 引擎对 | hyb 粗筛非空产候选 → scripted partial → violation;占位符剥离后残双空格(「招标 / 投标 (明细 )」)为 _render_message 既定行为,contains 钉词避开空白区 |
| L3-009-schedule-completion-conflict | 引擎对 | steps 双条件;开工≤竣工达标、竣工≠承诺函竣工违例,单因触发;ISO 日期串加引号 |
| L3-010-boq-unit-mismatch | 引擎对 | op:all 逐行 matched==True;TL-011 达标不产条目、TL-012 单位不符单条 |
| L3-012-appendix-missing | 引擎对 | op:all 逐行 present==True;已随卷附件不产条目 |
| L3-013-toc-section-missing | 引擎对 | all-in 差集(投标自附章节不算违规);缺「8」单条 |
| L3-014-doc-date-after-deadline | 引擎对 | steps 双条件;投标函日期达标、承诺函 2026-07-02 晚于截止违例,单因触发 |
| L3-016-version-tag-mismatch | 引擎对 | op:all 逐出现;页眉达标不产条目、封面 V3.0≠V3.2 单条 |
| L3-018-currency-occurrence-mismatch | 引擎对 | op:all 逐出现;报价表达标不产条目、承诺函「美元」单条 |

## 批P1-β1(P1-β批一)裁决表

rulepack 现 L3=17:det 15+hyb 2;本批新增 L3-019 行乘算(单价×数量=合价),单独立表(批B 表保持历史快照 15 行)。

| case | 裁决 | 结论/bug编号 |
|---|---|---|
| L3-019-price-qty-amount | 引擎对 | 行乘算 close 容差 0.01;任一分量 null 行跳过;与 L1-010 纵向加总链不重叠;校准证据:BOQ-02 超差单条 violation(¥100.00×3 ≠ ¥250.00);BOQ-01 相符/BOQ-03 全 null 行零产出 |

## 批B运行时行为备忘(建库时实测,T9 建库者直接受益)

1. **声明 inputs ≠ check 表达式字段**:run_det_rule 缺字段检查分两段(表达式字段段 → inputs 段),表达式全供齐但 inputs 有缺席仍 need_human——L3-001 的 project_identity.code、L3-004/008 的白名单与招标设备清单均属「死但必须供」字段。
2. **op:all 逐行判,每违例行各产一条 issue**(本批 cases 均单违例行,单条期望即绿;达标行零产出)。若钉多违例行须逐条 expect 并以 contains/entity 消歧。
3. **hyb 占位符剥离的空白残留**:message_tpl 含字段占位符时 _render_message 剥占位符为空格再尾缀「 (clause_id: reason)」,消息会出现双空格——contains 钉规则关键词+reason 子串最稳,勿钉空白区。

## 批C(L2×8 + E×6)裁决表

rulepack L2 实有 2 条(L2-020/L2-024,均 det,零 model_script);E 族命名按 loader 正则落 E-1..E-6(计划草名 E-l1-005-*/L2-cross-dedup-* 第二段非数字不合法,同批A A 族先例)。
全部为「引擎对」:期望按引擎现输出起草,逐处 diff 后与 rulepack/attachments 语义逐字核对一致;零引擎修复,rulepack 未动。基线 62 passed+1 skipped → 批C 后 80 passed+0 skipped(覆盖率地板翻全集,精确相等标记启用)。

| case | 裁决 | 结论/bug编号 |
|---|---|---|
| L2-020-missing-attachment | 引擎对 | att_check MISSING 聚合单条(missing 列表顿号连接),entity_keys=[attachment:E-2];checklist 平铺行 status_by_no 双行钉(MATCHED/MISSING) |
| L2-020-matched-clean | 引擎对 | 全命中零 L2 条目;strict 钉任何 att_* 误报;checklist 双 MATCHED |
| L2-020-unknown-group-failure | 引擎对 | 孤儿引用父号(3-9)归属不了子件 → 父行 UNKNOWN → expect 显式 verdict: need_human(verdict 分桶,降级不冒充命中);「零引用=诚实 MISSING」对照面由 attachments 单测钉,金标准取分组失败形态;checklist unknown_count=1 |
| L2-020-subitems-three-channel | 引擎对 | 三子件各由唯一通道命中且三通道互斥——①no 全等(H-1-11,②③双死)/②父号点序(H-1.2,①③双死)/③名称归一(X-999 无关号,①②双死);任一通道断 → 父行 MISSING/UNKNOWN 被 strict+checklist 双捕(① 原用 H-1-1 会撞 ② idx=1 位置兜底形态 H-1-1,影子命中假绿,审查修复改 H-1-11);shapes 照 test_bid_review_attachments.py 夹具 |
| L2-024-count-insufficient | 引擎对 | min_count=2 供1 → PARTIAL;消息「要求2份/提供1份」计算值入 contains 钉;att_check 侧 PARTIAL 非 MISSING 不产条目(strict 钉单规则触发) |
| L2-024-count-unknown-clamp | 引擎对 | 分组失败父行 UNKNOWN → att_count 零条目(钳位);即便子件有 PARTIAL 缺口(3.1 要求2份供1份)也不入 insufficient——strict 空期望钉:引擎若误把 UNKNOWN 计份数即红 |
| L2-020-cross-dedup-severity | 引擎对 | 同实体键 attachment:E-1 同触 L2-020 fatal(行2 MISSING)+L2-024 major(行1 PARTIAL)——单行 MISSING/PARTIAL 状态互斥,同实体双规则只能经同名两行要求构造(行1 min_count=2 贪心取走唯一一份);端点 related_issues 归并(_cross_layer_group 须跨≥2 层,L2-020+L2-024 同层不归并)不在纯函数断言面,由 test_bid_review_grouping 钉;checklist status_by_no 同 no 双行取首行(PARTIAL) |
| L2-020-flat-no-subnote | 引擎对 | 平件/复合件混池互不偷项(平件名称通道跳过引用父号的提供项);平件行 sub_results=[]、零 UNKNOWN;P2 回归面 |
| E-1-l1-005-validity-satisfied | 引擎对 | gte 边界=达(90==90 不报) |
| E-2-l1-009-within-max | 引擎对 | lte 边界=达(总价==限价不报;「总价=限价」非超限) |
| E-3-l1-015-warranty-equal | 引擎对 | {value,unit} normalize_unit 归一后 gte 边界=达 |
| E-4-l1-019-no-alternative | 引擎对 | count([])==0 显式空列表=合规(键在场非缺字段,不落 need_human 降级),钉「空=达标」语义 |
| E-5-l3-016-version-consistent | 引擎对 | op:all 全达标零违例行(页眉/封面/正文三出现处) |
| E-6-l2-020-all-matched | 引擎对 | 份数达标(min_count=2 供 2 份编号通道双命中)+名称归一通道命中(提供项无 no 键),L2-020/L2-024 双 absent |

## 批C守卫与备忘(T6 审查挂账落地的两道闸 + 覆盖率收口)

1. **loader 嵌套键守卫**(loader.py `_reject_non_str_keys`):字段值递归下钻 dict/list,嵌套映射键非 str(裸 `no` → False,bug-3938 类;下游 materials_hash 的 json.dumps(sort_keys=True) 会 TypeError)加载期即拒,报错点名字段路径+加引号修法;钉测 `test_loader_rejects_non_str_nested_keys` + 正例对照 `test_loader_accepts_quoted_no_keys`。
2. **stub 未知键守卫**(runner.py `_fields_from_stub`):stub 键对照 loader `known_field_paths()`,未知键(疑似笔误)在 `_fields_from_stub` 构造冒烟字段时大声报错(冒烟接线期,非 loader 加载期),不再被「请求路径∩stub 键」过滤静默丢弃(假绿);钉测 `test_fields_from_stub_unknown_key`。既有 smoke-1-basic stub 全键已知,守卫不误伤。
3. **覆盖率收口**:EXPECTED_COVERAGE 增 L2-020/L2-024(全 34 ids);`test_coverage_complete_marker` 去 skip 分支——EXPECTED_COVERAGE、pack 全集、题库实 coverage 三方精确相等(漏建/多建双方向即红)。
4. **L2 建库备忘**:`'no'` 键一律加引号(守卫前是 bug-3938 静默炸 materials_hash,守卫后是加载期报错);数字形 no 值("3"/"3.1"/"3-1")同样须引号防 PyYAML 转 int/float;复合件 shapes 照 test_bid_review_attachments.py 夹具;checklist status_by_no 同 no 多行时取首行(items 平铺序);UNKNOWN 行 need_human 被 strict 容忍不进余量,其断言走 expect_issues 显式 verdict: need_human。

## 批D(L2-P3 负证据+同义词归一)裁决表

spec docs/superpowers/specs/2026-11-03-bid-review-l2-p3-negative-evidence-synonym-design.md(05d32c92f);引擎能力增强切片——新行为用新题钉,既有 49 题零翻红为回归证据(金标准铁律)。

| case | 裁决 | 结论 |
|---|---|---|
| L2-020-synonym-name-match | red-first→引擎增强 | 落库先红(变体名双通道落空→fatal MISSING→strict FP 探针红);normalize_name 同义词折叠(_SYNONYM_GROUPS 子串替换,组内最长变体优先)后通道② MATCHED→绿;副本/复印件/回执不入表(方向不明,走 near-miss 门降 UNKNOWN) |
| L2-020-near-miss-unknown | red-first→引擎增强 | 落库先红(现状两级精确双落空→fatal MISSING,expect verdict need_human 不符);_near_miss_pass 门(0.75,SequenceMatcher × extra 池)后 UNKNOWN(near_miss)→need_human→绿;门限标定:中标通知书 vs 回执≈0.83 入门/中标通知书 vs 业绩合同≈0.0 门外(单测 monkeypatch 钉阈值真实生效);Task 3 将补强 contains「近似候选」 |
| (L2-020-near-miss-unknown 补强) | 引擎对+题补强 | att_check UNKNOWN 按 unknown_reason 分流措辞——near_miss 带「近似候选」+相似度,grouping 维持原文(golden 分组失败题 contains 依赖回归面);entity/dedup 键两形态同构(I-1);contains 补「近似候选」钉措辞;落红证据:分流前 message 硬编码「无法自动分组」,「近似候选」断言红 |
| L2-020-subitem-near-miss-unknown | red-first 落红(引擎变更前):子行 MISSING→父行 MISSING→L2-020 fatal violation,期望 need_human;连坐: red 窗口期 test_cli_main_exit_codes 同红(CLI rc=1),非回归 | 2026-11-03 P3.2 Task1 |
| L2-020-subitem-near-miss-unknown | 中间态落红(Task1 引擎后):父行 near_miss 误入平件分支→消息「无近似候选记录」,contains 缺「子件」「3.2」;Task2 三分支收口 | 2026-11-03 P3.2 Task1 |
| L2-020-subitem-near-miss-unknown | contains 断言转绿:三分支后消息点名「3.2 中标通知书」+「近似候选」+0.83;既有 51 题零翻红 | 2026-11-03 P3.2 Task2 |

**批D 备忘——P3 负证据**:negative_evidence={channels,pool,closest(top3,≥0.30)} 双写面——per_req(rule_runner 消费)+items(端点透传);分组失败行 evidence=None/unknown_reason=grouping,与 near_miss 不混用;复合子行 P3.2 已同入近似门(见本批 2026-11-03 三行)。

## C-05/C-08 口径注记（2026-11-06，P1-α 落地）

- **C-05**：入库快照 `bid.attachments[].status`/`bid.attachment_index[].status` 的 `MATCHED` 已归一为 **PRESENT**（规格 L2 枚举；`worker._normalize_attachment_status` 单点边界）。引擎内存态与判定不变；**MATCHED 保留为清单视图别名**——golden fixtures 的 `status_by_no` 钉值与 `build_checklist` 产出口径**不动**，本表既有行继续有效。
- **C-08**：`bid_review_issues` 新增 `semantic_verdict`（引擎 raw 四值 full|partial|none|unclear，sem/hyb 专属）与 `state`（state_map 分层业务态）两列；`verdict` 收敛值（violation|need_human|unclear）与四态判定表**不变**。verdict 值域迁 PASS/FAIL/UNKNOWN/ERROR/SKIP 挂 P1-β（届时随规则扩包同批重标定本表）。

