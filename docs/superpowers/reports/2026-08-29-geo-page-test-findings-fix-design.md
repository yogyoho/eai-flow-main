# 地质报告技能 页面实测 findings → 修补设计决策包

> 2026-08-29 · 来源：页面验证性测试（Thread fa2cf7a5）6 findings · 7-agent 只读分析工作流（wf_3455cfaf-921）
> 状态：**待用户裁决第四轮**。本包只读分析产出，未改任何代码。

## 优先级总表（critic 裁决）

- **F5-object-form-fields-as-prose** — P0（M（约1.5-2天：schema 拆平+ingest 三处接入+SKILL.md+夹具修复+7测试））错误数值的根因通道：子键无权威名→agent 猜键→formula_runner .get(k,0) 静默 0→E4/E5/E6 编造值入报告。formula_runner.py:404 recovery_cu/cu 双键防御即键名漂移已发生的实证。F2/F3 只能暴露缺失，F5 消灭缺失的最高产来源。工作量依据：纯技能层（exploration.json+ingest 纯函数+SKILL.md 一条规则），但必须含 M1 的夹具占位循环修复与点分子键 required 策略，否则 52 测翻红；无 harness 改动（FORM_FIELD_TYPES 无 object 由点分标量键绕开，16 项上限由分批规则规避）。
- **F3-stale-freeze-no-warning** — P0（M（约1.5-2天：快照机制+build 硬拦+文档三处+7测试））合法修正（修改回路是常态流程）后冻结不刷新=全书用旧数出报告，属『产出错误报告数值』本体；且冻结时无任何输入指纹，漂移在系统里不可见。build hard block（load_state_and_check 是 assemble/单章门共用点，build_output.py:316-330 实证）是唯一强制点。工作量依据：新增 snapshot_inputs/stale_freeze_files + write_state 加参 + 两调用点传参，机制简单；大头在 C3/C4 的 SKILL.md rc1 例外措辞与 7 个测试（含存量无快照迁移阵痛验证）。与 F2 合并实现 B1/E 链 anomaly 去重后总量不增。
- **F2-fabricated-values-undetectable** — P0（S-M（约1天，与 F3 合并后增量更小：anomaly 三档+FC-presence+门2 逐值核对协议+6测试））B1 整族缺失静默+E4=0 静默 emit 是页面实测复现的错误数值通道，rc=0 时门2 呈现义务根本不触发。与 F3 冲突部分按 C2 裁决（取 F3 skip 语义），F2 保留独有件。注意其 E4=0 anomaly 的触发面在合并后收窄为『price_ok 但 gCu=0』一类边角（E4 不再 emit 0 槽），测试期望随合并调整。工作量小：全部是 append anomalies 走既有 rc3 通道（formula_runner.py:483 现成），主夹具 expect=(0,3) 已容忍。
- **F1-manifest-drift-blindness** — P1（S（约0.5天：audit 函数约40行+SKILL.md 一行+6测试+1断言收窄；与 F6 合并同 PR））按用户口径属协议/可观测性：manifest 哈希零消费者、唯一写者契约无审计。它拦截的『手改已登记文件』向量若被利用确实产出错误数值，但该路径要求 agent 双重违规（编造+手改），且数值正确性主防线是 F5/F2/F3；F1 的价值是让违规从不可见变 rc2 阻断（页面实测已演示该向量，故排 P1 首位、与 F6 同 PR 尽快落）。工作量依据：复用 load_manifest/sha256_file 现成件，唯一要裁决的是 C1 的四项合并决策与 test:428 断言收窄（保 bug-3004 原意）。毫秒级写后登记竞态由 progress 状态机串行性兜底，不加锁（F1 risks 判断正确）。
- **F6-scratch-files-in-datadir** — P1（S（约0.25天增量，整体并入 F1 同一 audit 函数与同一 PR））纯卫生/协议：scratch 文件（schema 外名）不进 compute，不产错误数值；危险变体『手写 schema 同名表单』由 F1 的漂移/未登记双查覆盖。与 F1 合并后是同一函数的分类分支（HYGIENE warn vs TAMPERED rc2），单独排期无意义。buglog-2189 的『空 manifest 不得提前 return』教训与其测试（test_check_empty_manifest_files_on_disk_all_unregistered）必须保留进合并版。
- **F4-gate2-not-enforced** — P1（M（约1.5-2天：progress.py rc2+confirm-gate2+三闸+SKILL.md 门2 重写+3个测试文件夹具改造+page-test-script 夹具））协议门（type_verdicts 是结论文字非数值，错判不直接产错误数字，故 P1 非 P0；但它决定 XS3 逐字口径与报告结论正确性，且是页面实测实际失败点）。设计可行性已核实：key_points_confirmed/cmd_confirm 先例（progress.py:200,264-271）照抄，rc2 与 ingest/consistency 的『需人工』语义同族，无 harness 改动。工作量最大的两项是夹具连锁（test_geo_progress.py ws 夹具 init 直跑会全红，:33-37 需+confirm 步骤与最小 data 文件）与 C7 的修改回路合并措辞；grandfathered 豁免（在途任务放行）实现时勿漏。

## 设计冲突消解（critic）

### C1
C1【F1×F6 直接冲突——同一审计点两套设计】两者都在 ingest.py cmd_check 开头给 data/ 顶层加未登记扫描（F1 audit_manifest vs F6 scan_data_dir_inventory），但四处理念互斥，必须合并成一次实现：(a) 检查深度矛盾——F1 做 sha256 漂移+缺失+_meta.status 词表三层，并同步收窄 test_geological_report_v2_scripts.py:428 断言（实测该断言在 428 行非 429，429 是 write_text("[]")）；F6 风险#4 明令 presence-only『不得顺手做 sha 比对，否则 test_check_list_shaped_doc_no_crash 红』。二者只能取一：应取 F1（hash 漂移+断言收窄），因为页面实测的攻击形态恰是『改已登记文件字节』，presence-only 拦不住。(b) 输出标记撞车——同类发现（未登记文件）F1 叫 GATE1_TAMPERED、F6 叫 GATE1_UNREGISTERED，SKILL.md 派发协议按 stdout 标记解析，双标记并存会让控制器分叉，合并时定一个（建议 GATE1_TAMPERED 大类 + 行内子类注明 unregistered/drift/status）。(c) .tmp/.lock 残留——F1 静默跳过，F6 打 HYGIENE warn 不阻断；取 F6（ingest.py:106 docstring 自认 .lock 残留是已知合法形态，静默丢观测面，warn 不阻断两全）。F1 的 test_check_audit_ignores_lock_and_tmp（断言静默）与 F6 的 test_check_residue_tmp_lock_not_blocking（断言 HYGIENE 在场）直接互斥，测试期望须随合并统一为 HYGIENE 版。(d) 扫描面——F1 用 glob(*.json)+glob(*.csv)，F6 用 iterdir() 全文件（覆盖 scratch .md/.xlsx 等任意扩展名）；取 F6 的 iterdir 更严，F1 的语义层（status 词表）只作用于已登记 json。合并后单次遍历，无重复扫描性能问题；SKILL.md:175 门1 行只改一次。

### C2
C2【F2×F3 直接冲突——compute() 同一代码区两套语义】(a) E 链零值槽位矛盾：F2 明确『E4 槽位值=0 仍 emit 不删，供门2 呈现』（其 test_e4_zero_price_anomaly_rc3 断言槽位在场且=0）；F3 明确『prices 全空 → E4/E5/E6 全部不 emit』（其 test_execute_price_blank_skips_zero_slots 断言槽位缺席、走 build_output.py:389 未知槽位 FAIL）。互斥，必须取 F3 的 skip 语义：红线是『缺≠0』，把 0 注入正文就是产出错误数值（P0 定义本身），且缺槽有 unknown-slot 门+chapter_craft.md:15/24 [待确认] 规则两道现成下游承接；F2 的『保留 0 供呈现』依赖撰写者自查 formula_state，多一道人为失误面。(b) B1 缺族 anomaly 双实现：F2 在 B1 段（三档 a/b/c 互斥 if/elif）与 F3 的 audit_critical_families(a)/(b) 触发条件略异、文案不同——若都落地，同一缺失报两条 anomaly，呈现层噪音且 test 各自断言自家文案会互相打红。合并为一处实现（建议 compute() 末尾单点 audit，条件取并集：整族缺失/半填/products 行非 finite 三档）。(c) E3/E6 静默跳过补 anomaly 两处重复（F2 L405-407/L418-419 else 分支 vs F3 挪 guard），同样合一。F2 的独有价值应保留移植：逐产品行级 anomaly、consistency.py FC-presence 双向等价检查、SKILL.md 门2 关键冻结值逐值用户核对硬协议。

### C3
C3【F3 的 rc1 STALE_FREEZE 撞 SKILL.md 4.2『rc1→重派』反射】SKILL.md:134 单章门契约是『rc=1（含深度目标门 FAIL）→ 原 prompt + stderr 重派（每章 ≤1 次）』，SKILL.md:183-184 命令表同样把 build rc1 定义为『门拦』。STALE_FREEZE 走 ValueError→rc1 后，按现有协议控制器第一反射是重派章节——但正确动作是重跑 execute，重派烧派发额度且永远修不好，正是本批要根治的死循环类。F3 的文档改动只覆盖了 SKILL.md:81 门2 段，漏了 4.2：必须在 SKILL.md 4.2 与命令表 build 行显式写『rc1 且 stderr 含 STALE_FREEZE 例外：禁止重派，重跑 formula_runner execute/update 后重验』（token 已在 stderr 固定携带，可机械判别）。

### C4
C4【F3 复用 rc2 撞 formula_runner 现有 rc2 语义】formula_runner CLI 当前的 rc2=argparse 互斥组 usage error（bug2223 测试 :180 以 expect=(2,) 钉死该语义，:616 注释自认）。F3 把 cmd_check『旧版 state 无快照』映射为 warn→rc2，agent 见 formula_runner rc2 可能按『命令用错』处理（重敲命令）而非『重跑 execute』。可接受但须：STALE/无快照输出带固定 token（如 [WARN] STALE_FREEZE: legacy）+ SKILL.md:178 check 行 rc 列写明 2=旧版状态无快照（重跑 execute），不能只靠正文。

### C5
C5【跨脚本 rc3 双义（既有债，本批选择加剧文档负担）】snapshot.py:32 EXIT_TAMPERED=3（SNAPSHOT_TAMPERED 篡改阻断）vs ingest/formula 的 rc3=『完成带异常、呈现后可继续』。F1/F6 把 data/ 篡改放在 ingest check 的 rc2（与 2=需人工同族）是正确裁决，未新增冲突；但同一管线里 3 在 snapshot 是硬拦、在 formula 是可继续，控制器若跨命令泛化『rc3=呈现即可继续』会在快照篡改上误放行。无需改码，但 SKILL.md:153/175-178 各命令行 rc 语义须逐行写死、禁止跨命令归纳——建议作为 SKILL.md 修订的一条硬要求写进任一落地 PR。

### C6
C6【F5×F1 栈叠与 F5×测试夹具冲突】(a) 两者都改 ingest cmd_check：合并设计里审计（F1/F6）先行、F5 的逐点分子字段完备性走查在后，SUMMARY 行格式两边都要改，落地顺序必须约定（建议 F5 先、F1+F6 后，最后一个落地的负责合并 SUMMARY），否则后改者覆盖先改者的 SUMMARY 字段。(b) 更严重的实测级隐患（F5 风险清单漏掉）：test_geological_report_v2_scripts.py:148-163 的自动占位循环 `need = {f["name"]: ph(f) for f in spec.fields if ...doc.get(f["name"]) in (None,"",[],{})}` 会把所有点分子键（doc 无扁平键→全判缺）用 ph() 占位值（number→1.0）fill 进去——F5 的 _expand_dotted 逐子键深合并会用占位 1.0 覆盖 :134-145 已真填的嵌套 prices.cu_yuan_t=51000 等值，锚点断言 B1.recovery[铜精矿]=85.18（:557）与 E 链锚点全崩。F5 必须同步改该循环跳过点分键（或 ph 前 doc 嵌套感知），否则 ws 夹具 52 测大面积翻红，且这种『占位值覆盖真值』若发生在生产 agent 的类似补填流程就是真数据污染。

### C7
C7【F3×F4 在合法修正事件上连环触发，修改回路须合并成有序清单】用户改一次数据（尤其含 type_verdicts）会同时点亮：F1 门1 审计重登记（自动过）、F3 STALE_FREEZE（build rc1 直到重跑 execute）、F4 门2 漂移重臂（confirm-gate2 rc2）。若 SKILL.md 不把三者写成一条有序回路（ingest 落盘 → 判定词变了才 confirm-gate2 → execute/update 刷新冻结 → impacted → 受影响章重派 → build），agent 会在三个门之间交替撞墙，每发现一个门烧一轮对话（token 已 1.5M+ 的直接成因就是这种多轮撞墙）。建议落在 SKILL.md:163-167『修改回路』节整体重写，而不是三个 finding 各自加一句。

### C8
C8【SKILL.md 命令速查表（:171-184）编辑冲突与落地顺序】F1 改 :175 ingest check 行、F3 改 :177-178 execute/check 行、F4 改 init/next 行并新增 confirm-gate2 行、F5 改 :66 类型映射规则——同一张表四处动。加上 C1/C2/C6 的合并裁决，建议落地顺序：F5（数据形状契约，根因）→ F2+F3 合并（compute 语义）→ F1+F6 合并（门1 审计）→ F4（控制器门，夹具改动面最大且依赖稳定的三句判定词 schema）。单 PR 或按此序的 PR 链均可，但 cmd_check 的三路改动（F1 审计/F5 点分/F6 残留）必须一次性合入同一版 cmd_check。

## 遗漏项备忘（critic）

- **M1** M1【F5 自伤面：自动占位覆盖真值】见 C6(b)——test:148-163 占位循环对点分键 fill 占位值经 _expand_dotted 覆盖已真填嵌套值，F5 风险清单未列，属设计缺口非实现细节；同时需为点分子键定 required 策略（source_refs/as_of_date/ag_yuan_per_g/recovery_ag 应 required=false，否则 ws 夹具 :141 prices 只填 cu_yuan_t/ag_yuan_kg 会让门1 新增 rc2 缺项翻红一批测试）。
- **M2** M2【composer submit 按钮 click 失效只能 Enter】前端交互缺陷，技能层不可修；且 human-input-card.tsx 正在本次工作区改动中（git status M），疑似现行改动回归——而 F4 的门2a 整个协议压在 ask_clarification 卡片可用性上，卡片按钮坏了 F4 等于白修。建议：单独记 buglog（前端 lane，P1），在本批技能改动合入前先实测复验卡片提交流程，不在本批修。
- **M3** M3【前端表单必填校验与 DOM required 不一致】harness clarification 表单层缺口（clarification_middleware.py 校验的是 schema 形状，前端 DOM required 与后端必填集不同步）。红线约束下本批不修；记 buglog 缓修（P2）。注意 F5 拆平后逐子字段表单会放大暴露面（用户可漏填必填子项提交），SKILL.md:69『只传用户提交的键』规则已能兜住部分收集，风险可控。
- **M4** M4【会话 token 1.5M+ 增长过快】主因是门失效导致的多轮返工循环（03e18e4a 死循环同型），本批 F1-F6 的硬拦正是削减轮次的手段，无需新增代码；记录为运维观察即可。若落地后仍增长过快，下一步在 config 层调 summarization 触发阈值（允许的 config 层改动，非 harness）。
- **M5** M5【F4 自认残余：不 init 直派/不跑 build 直写 outputs/ 的流氓路径】本轮范围外正确；候选后续 P2——build_output --output 前校验 state/gate2.json 在场（与 STALE_FREEZE 同在 load_state_and_check 加，一处代码两个门）。
- **M6** M6【snapshot verify 的 rc3 会在 state/ 任何后续写后触发】既有行为（progress.json/chapters 改动同样触发），F4 新增 gate2.json 成为 state/ 又一写者，放大触发概率。协议已规定 snapshot save 在交付前最后一步，无需改码；在 SKILL.md 修订时加一句『verify 仅用于新一轮步骤0，交付后任何 state 写入都会使旧快照 verify 失配（预期，非篡改）』，防 agent 误判。
- **M7** M7【F3 snapshot_inputs 建议顺带记录 forms 键集外的 data/ 文件计数】F1/F6 审计已覆盖未登记文件，此项不必须，但 formula_state.inputs 里带一个 unregistered_count 字段（0 或 N）可让冻结态自带『当时 data/ 是否干净』的凭据，成本约 3 行；可不修，记录备选。
- **M8** M8【F1 语义层词表检查的漏洞自认已到位】_meta.status 伪造可同步伪造合法值 filled+重算 sha 绕过（F1 not_feasible_note 已如实声明）；真正的根治（沙箱 ro 挂载/extensions 层 pid 级写者白名单）属后续独立立项，本批不追。
- **M9** M9【页面实测脚本 page-test-script.html 属夹具资产】F4 把它列入 files_to_change 正确（#gate2 节实测失败点），落地时应同步更新期望行为描述而非只改脚本，避免夹具与实现漂移；实现者易漏。

## 各 finding 修补设计（按优先级排序）

## F5-object-form-fields-as-prose（effort M）
**根因**：主因在 schema 定义层：exploration.json 的 economics 族把对象型字段定义为普通顶层名+子键说明（如 `{"name": "prices", "type": "object", "fields": ["cu_yuan_t", ...]}`），子键未像 hydro_eng_env 族那样提升为点分层级键（`hydro.mid_level_drainage`），因此 ask_clarification 无法逐子字段发问。harness 渲染层是不可改的放大器：表单 schema 白名单（FORM_FIELD_TYPES）根本没有 object 类型，未知 type 静默降级为 text；而 SKILL.md:66 又明文指示「嵌套对象当普通中文数据项用 textarea 收」，把对象族主动导向单 textarea → 用户只能叙述作答 → agent 在组装 `--values` 时自由解析；ingest.py 的 validate_values 只校验顶层键名与 isinstance(dict)，不校验子键，编错的子键名照样 rc=0 落盘，到 formula_runner.py:409 `prices.get("cu_yuan_t", 0)` 静默默认 0 → E4=0。

**代码证据**：
- D:/eai/eai-flow-main/skills/public/geological-report/references/stages/exploration.json:570-576 — economics 族对象字段为普通顶层名+子键说明：{"name": "prices", "type": "object", "fields": ["cu_yuan_t", "ag_yuan_kg", "ag_yuan_per_g", "as_of_date", "source_refs"]}、{"name": "costs", ... fields:[mining_yuan_t,beneficiation_yuan_t,other_yuan_t]}、{"name": "rates", fields:[loss_rate,dilution_rate]}、{"name": "concentrate", fields:[grade_cu_pct,grade_ag_gpt]}、{"name": "credibility", fields:[TM,KZ,TD]}；:573 {"name": "recovery", "type": "object", "required": false} 连 fields 子清单都没有——子键无 schema 权威名，agent 只能猜
- D:/eai/eai-flow-main/skills/public/geological-report/references/stages/exploration.json:496-505 — 对照组 hydro_eng_env：fields[].name 直接是点分层级键 {"name": "hydro.mid_level_drainage", ...}、{"name": "engineering.rock_groups", ...}、{"name": "environment.seismic", "type": "object", "fields": ["peak_accel","intensity","source_std"]}——每个点分键天然是表单里一个独立数据项
- D:/eai/eai-flow-main/backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py:26 — FORM_FIELD_TYPES = frozenset({"text","textarea","number","select","multi_select","checkbox","date"})——表单 schema 无 object 类型；:233-234 `if not isinstance(field_type, str) or field_type not in FORM_FIELD_TYPES: field_type = "text"`——未知 type（含 object）静默降级为单行文本框；:53 MAX_FORM_FIELDS = 16、:208-209 `if len(fields) > MAX_FORM_FIELDS: return []`——超 16 项整卡作废降级 free_text；:55 MAX_FIELD_TEXT_CHARS = 200——长说明放 label/placeholder 直接整卡作废
- D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md:66 — 「长文本/嵌套行数据→textarea …——嵌套对象当普通中文数据项用 textarea 收（placeholder 给中文格式提示），结构化由 ingest 完成」——指令层把 schema 歧义固化成『对象族=单 textarea→用户叙述作答』的系统性流程
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:198-211 — validate_values 只做键名白名单+顶层类型校验：`known = {f["name"]: f for f in spec.get("fields", [])}`；:189-192 coerce_type object 分支仅 `isinstance(value, dict)`——子键名完全不校验，agent 编出 {"prices": {"cu": "58000元/t"}} 照样 rc=0 落盘
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/formula_runner.py:409-413 — pCu = dec(prices.get("cu_yuan_t", 0))；price_conc = pCu * gCu / HUNDRED + ...——子键名漂移时静默默认 0 → E4.price_conc=0；:404 `rec.get("recovery_cu", rec.get("cu", 0))` 双键防御即键名漂移已发生的实证（对应 exploration.json:573 recovery 无 fields 清单）；:385 `if eco and not all(isinstance(eco.get(k), dict) for k in ("credibility","rates","concentrate","prices","costs"))`——数据形状契约=嵌套 dict
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/formula_runner.py:357 — `ia = hee.get("hydro.inflow_analogy")  # schema 扁平点号键`——hydro 族点分键按扁平键落盘与读取，与 economics 嵌套 dict 是两种形状，修补时归并判据必须区分
- D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py:134-145 — 既有测试以嵌套对象填充 economics（"prices": {"cu_yuan_t": 51000, ...}）；:124 hydro 以扁平点分键填充（"hydro.inflow_analogy": {...}）——两种传法均为必须保持合法的存量合约

**修补设计**：主修=schema 拆平（方案 A），SKILL.md 逐子字段指示仅作配套（方案 B 单用不推荐——不拆 schema 时子键名无权威定义、ingest validate 仍会拒自造点分键，自由重组依旧由 LLM 干）。三层最小修补（零 harness 改动、零 formula_runner 改动）：

【1】exploration.json forms.economics 拆平（照 hydro_eng_env 点分先例）：
- 保留 6 个 type=object 父条目（prices/costs/rates/recovery/concentrate/credibility）——formula_runner.py:385 isinstance-dict 门与 E 链读取、存量嵌套落盘数据均依赖此形状；
- 每个 object 父条目新增点分子键条目：prices.cu_yuan_t(number,元/t)、prices.ag_yuan_kg(number,元/kg)、prices.ag_yuan_per_g(number,元/g,选填)、prices.as_of_date(string)、prices.source_refs(string)；costs.mining_yuan_t / costs.beneficiation_yuan_t / costs.other_yuan_t(number)；rates.loss_rate / rates.dilution_rate(number,%)；concentrate.grade_cu_pct(number,%) / concentrate.grade_ag_gpt(number,g/t)；credibility.TM/KZ/TD(number)；recovery 补权威子键清单 recovery.recovery_cu / recovery.recovery_ag(number,%)——以 formula_runner.py:404 实际读取的 recovery_cu 为权威名，终结猜键。capacity_10kt_a/mine_life_remaining 已是标量不动。本轮只拆 economics（实测主靶）；geography.climate、tenement.estimate_scope、prior_estimate.* 同构可后批照搬，industrial_params 顶层本无 object 字段（其问题是 outlier_samples 这类 array<object> 走 textarea，归 SKILL.md 规则修）。

【2】ingest.py 三处小改：
- 新增纯函数 _expand_dotted(values, spec) -> dict：仅当点分键的前缀命中 spec 中 name 相同且 type=="object" 的字段名时，把值按路径深合并进嵌套 dict（逐子键合并而非整对象覆盖——顺带修复现有 doc.update 浅更新会抹掉先前子键的坑）；hydro/engineering/environment 前缀不命中任何 schema 字段名 → 不归并、保持扁平（保 formula_runner.py:357 合约）。在 cmd_forms 写入路径 `doc.update(values)`（:294）前调用，并删除 doc 中点分扁平占位；write_form_values（:554）同样接入。顶层整对象传法 {"prices": {...}} 不经过归并、原样落盘 → 存量测试与线程零破坏。
- 新增 _get_dotted(doc, name)：cmd_check 逐字段循环（:537-539）对点分 name 改嵌套取值——门1 缺项清单从笼统的 economics.prices 升级为逐子字段（economics.prices.source_refs）。
- blank_json（:226-228）：点分键跳过占位生成（父条目 null 占位已够），避免 _meta 外出现 prices.cu_yuan_t: null 与嵌套占位双写。
- rc 契约不变：未知点分键/未知前缀 → rc=1（validate_values 既有「不在 schema 字段清单中」文案，天然覆盖）；归并成功 → rc=0；门1 缺子键 → rc=2。无需新增 rc 码。

【3】SKILL.md:66 类型映射规则改写：
- 删除「嵌套对象当普通中文数据项用 textarea 收」，改为「对象族按 schema 拆平后的点分子键逐项收集：每个子键=表单里一个独立数据项（number→number 输入框、日期→date、来源说明→text），label=中文名+单位，禁止把对象族压成单个 textarea」（保留不向用户展示 JSON/英文键的原意）；
- 显式写死 economics 分两批问（价格+成本批 8 项 / 指标+可信度+产能批 9 项）——拆平后全族 17 项超 harness MAX_FORM_FIELDS=16，一卡塞满会被 clarification_middleware.py:208 整卡降级 free_text，比单 textarea 更糟；
- array<object>（如 industrial_params.outlier_samples）规则：≤10 条逐行收集（每行一个 textarea，placeholder 给「工作号,样品号,原值,处理后」格式）或引导上传；>10 条必须引导上传 CSV（与 :65 既有规则合并引用）。

误伤面评估（合法场景不被新逻辑拦）：①顶层整对象传法保持 rc=0（测试 :134-145 即此形状）；②hydro 族扁平点分键不归并（测试锁定）；③归并只认「前缀==某 object 字段名」双条件，误并需 schema 同时存在同名 object 字段，低概率且可测试锁死；④harness 16 项/200 字符上限由 SKILL.md 分批规则规避，不触发整卡降级。

**改动文件**：D:/eai/eai-flow-main/skills/public/geological-report/references/stages/exploration.json（forms.economics fields 拆平 + recovery 权威子键清单）; D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py（新增 _expand_dotted/_get_dotted；cmd_forms/cmd_check/blank_json 三处接入）; D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md（第 66 行类型映射规则改写 + economics 分两批）; D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py（新增 7 个测试）

**新增测试**：
- test_ingest_forms_dotted_keys_expand_to_nested — subprocess 实跑 `ingest.py forms --family economics --values '{"prices.cu_yuan_t": 51000, "prices.ag_yuan_kg": 3500, "rates.loss_rate": 15, ..., "costs.other_yuan_t": 20.75}'` → rc=0；断言落盘 doc["prices"]["cu_yuan_t"]==51000 嵌套形状、顶层无扁平 prices.cu_yuan_t 键；追加第二批 --values '{"credibility.TM": 1.0, ...}' → rc=0 且第一批子键仍在场（深合并不覆盖）
- test_ingest_forms_nested_object_still_accepted — 回归守卫：既有嵌套传法 '{"prices": {"cu_yuan_t": 51000}}' → rc=0 且落盘形状不变（防 _expand_dotted 误伤存量合约）
- test_ingest_forms_dotted_unknown_key_rejected — '{"prices.cu_typo": 1}' → rc=1，stderr 含「不在 schema 字段清单」
- test_ingest_hydro_dotted_stays_flat — '{"hydro.inflow_analogy": {"Q0_min": 908, ...}}' → rc=0 且落盘为扁平键 doc["hydro.inflow_analogy"]（锁归并判据不误伤 hydro 族，保 formula_runner.py:357 合约）
- test_ingest_check_missing_dotted_subkey_reports — 只写部分子键后 `ingest.py check` → rc=2，缺项清单逐子字段报出（如 economics.prices.source_refs）
- test_formula_runner_e4_from_dotted_ingest — 拆平路径落盘后跑 formula_runner execute → E4.price_conc > 0 且 cu_part 非零（锁 E4=0 缺陷不再发）
- test_exploration_schema_economics_flattened — schema 静态断言：exploration.json economics.fields 中每个 type=object 条目必有非空 fields 子清单（recovery 不再裸奔），且每个子键存在对应「前缀.子键」字段条目

**风险**：
- 存量线程 data/ 兼容：已按嵌套形状落盘的 16_economics.json 读取面（formula_runner/build_output）不变，无需迁移；旧线程续跑时新 schema 只增点分键不改既有键名，validate/check 均兼容
- 深合并语义风险：若 _expand_dotted 误用浅合并，第二批补答（先问价格后问成本）会整对象覆盖丢第一批子键——必须逐子键深合并并有测试断言两批共存
- 归并判据依赖「前缀==schema 中 type=object 字段名」：未来某族点分前缀恰好撞上无关 object 字段名会误归并——用 hydro 扁平回归测试锁死判据
- economics 拆平后全族 17 项超 harness MAX_FORM_FIELDS=16：SKILL.md 必须显式分两批，漏写则 agent 一卡塞满被 harness 整卡降级为 free_text（clarification_middleware.py:208-209），比单 textarea 更糟
- blank_json 跳过点分占位后，若 schema 漏保留 object 父条目，formula_runner.py:385 isinstance 门会把整族判空白跳过 E1-E7——schema 改动必须保留父条目，测试 7 锁死
- schema 静态断言（测试 7）会让后续新增 object 字段强制带子键清单，是有意收紧；对 skill.py 若有 schema 结构断言类测试需同步核查（test_geological_report_skill.py 43 个测试以文本/结构断言为主，未直查 economics fields，预期零影响）

**不可行边界**：渲染层（harness）无法在本约束下修补：FORM_FIELD_TYPES 白名单无 object 类型且未知 type 静默降级 text（clarification_middleware.py:26/:233），16 字段/200 字符硬上限（:53/:55）都是平台级防失控设计，改它违反「不改 deer-flow harness 核心」红线。替代方案即本设计的技能层路线：schema 把结构化信息前移为点分标量键，harness 既有标量控件（number/date/text）恰好一一承接，渲染层零改动即达成逐子字段表单。

## F3-stale-freeze-no-warning（effort M）
**根因**：formula_state.json 冻结时完全不记录输入快照：`write_state`（formula_runner.py:429-432）只写 {version, values, anomalies}，cmd_execute/cmd_update 也从不采样 data/ 指纹，因此「冻结后 data/ 被修改」在系统里是不可见事件——`cmd_check` 虽有冻结值 vs 重算值的差分能力（formula_runner.py:493-496），但它是可选命令、无任何机制强制在 build 前运行，而 build_output 的 `load_state_and_check`（build_output.py:316-330）只校验槽位形状（source 键），从不对照 data/。第二个根因是 compute() 的静默零值路径：E4/E5 用 `prices.get("cu_yuan_t", 0)` 这类 0 默认值无条件 emit（formula_runner.py:408-415），prices 空白时照常产出 0 值槽位且无 anomaly；B1 选矿族在 beneficiation 空白时整族静默不 emit（formula_runner.py:371-379，无 else 分支记 anomaly）。三者叠加：冻结带病→修正不入册→0 值/缺槽无告警→build 放行→agent 带着 E4=0/E5=0/B1 缺族推进到派发章节。

**代码证据**：
- skills/public/geological-report/scripts/formula_runner.py:429-432 — `def write_state(path, values, anomalies): doc = {"version": 2, "values": values, "anomalies": anomalies}` — 状态文档只有三个键，没有 inputs 快照；docstring L12「execute 读 data/ → 全量计算 → formula_state.json（冻结；无时间戳——字节级幂等）」说明冻结语义里根本不含输入指纹。
- skills/public/geological-report/scripts/formula_runner.py:465-483 — cmd_execute 全文：`values, anomalies = compute(_load(args)); write_state(out, values, anomalies); ... return EXIT_ANOMALY if anomalies else EXIT_OK` — 冻结动作不记录任何 data/ 指纹，也不做关键族自检；rc=3 是唯一信号且实测被 agent 无视。
- skills/public/geological-report/scripts/formula_runner.py:486-521 — cmd_check 确实有 `frozen.get(k) != recomputed.get(k)` 的自洽重算差分（漂移会被发现），但 (a) check 是可选命令、无人强制跑；(b) rc 映射在 L521 `EXIT_ERROR if fail else (EXIT_MANUAL if warn else EXIT_OK)`——检查能力存在但缺「必须过这道门」的执行点。
- skills/public/geological-report/scripts/build_output.py:316-330 — load_state_and_check 只有手改检测门：`if ... and "source" not in slot: raise ValueError(...疑似手改...)`，随后直接返回 state——装配/单章门对 data/ 是否漂移零校验；该函数被 assemble(L358) 与 run_chapter_gate(L441) 共用，是唯一需要加硬拦的位置。
- skills/public/geological-report/scripts/formula_runner.py:408-415 — E4/E5 静默 0 的确切代码：`pCu = dec(prices.get("cu_yuan_t", 0))`、`price_conc = pCu * gCu / HUNDRED + pAg_kg / THOUSAND * gAg`、`emit("E4.price_conc", price_conc, ...)`、`emit("E5.gross_potential_yi", (m_u / WAN * pCu + ag_kg * pAg_kg) / WAN, ...)` — prices 全空时 dec(None→str? no, prices.get(...,0)=0) 得 0，E4=0、E5=0 照样入册，无任何 anomaly；E6(L417-419) 在 conc_t 非None时用 0 价算出伪造负利润。
- skills/public/geological-report/scripts/formula_runner.py:371-379 — B1 循环：`for prod in lc.get("products") or []: ... if feed.is_finite() and feed and y.is_finite() and g.is_finite(): emit(f"B1.recovery[...]")` — beneficiation 空白/字段非数时整族静默缺失，无 else 分支记 anomaly（对比 C9 L161、经济链 L386 都有缺参 anomaly，B1 漏了）。
- skills/public/geological-report/scripts/build_output.py:388-391 — 未知槽位已有硬拦先例：`if unknown_keys: errors.append(f"未知槽位 key（不在 formula_state.values，FAIL 阻断）: ...")` — 证明「缺槽→build 拦」的通道现成，E4/E5 改为缺参跳过后会自动落进这道门。
- skills/public/geological-report/scripts/build_output.py:536-538 — `except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as e: print(f"[build] 错误: {e}"); return EXIT_ERROR` — ValueError→rc1 是现成硬拦通道，STALE_FREEZE 走它不需要新 rc 码。
- backend/tests/test_geological_report_v2_scripts.py:184,265-266,345-363 — fixture 时序：execute(L184) → build1/build2(L265-266) 之间 data/ 无写入 → 加 STALE 门不破坏 fixture；update(L345-363) 重写 formula_state.json 且用当前 data 重算 → update 路径刷新快照后，后续 TestDepthTargetGate/TestBuildOutput 拷贝的 state 与 ws["data"] 仍然一致，既有 build 类测试（_copy_chapters L897-903 拷 state+用 ws data）全部保持新鲜。
- skills/public/geological-report/SKILL.md:81,177-178 — 门2 契约「rc=3 = 有 anomalies 必须逐条呈现用户并获确认」与命令表 execute/check 行是需要同步修订的文档面。

**修补设计**：全部改动落在技能层两个脚本 + SKILL.md/chapter_craft.md 文档 + 测试文件，零 harness 改动。数据流不变：data/ 唯一写者仍是 ingest.py，formula_state.json 唯一写者仍是 formula_runner.py（快照是 execute/update 自产自用的读数，不引入第二写者）。

【一、冻结新鲜度机制】
1. formula_runner.py 新增 `snapshot_inputs(stage: dict, data_dir: Path) -> dict`：遍历 `stage["forms"]`，对每个族记录 `{fam: {"file": spec["file"], "sha256": sha256(文件字节), "bytes": n}}`，文件不存在记 `{"file":..., "missing": true}`。**判定只用 sha256+bytes，不用 mtime**——ingest 指纹增量/CSV 整列重写等「内容不变重写文件」场景 mtime 会变而 sha 不变，用 mtime 判漂移会误伤（这正是任务书里 mtime+sha 双清单要求的正确裁剪：mtime 不进判定，最多不进快照以保持快照极简）。同时比对快照键集 vs stage forms 键集，键集变化（新增/删族）也算漂移。
2. `write_state(path, values, anomalies, inputs)` 增加第 4 参，文档变 `{"version": 2, "values": ..., "anomalies": ..., "inputs": {...}}`。字节级幂等不破坏：inputs 是输入内容的确定性函数，data/ 不动则两次 execute 字节全同（SC-4 保持）。
3. `cmd_execute`：装载后调 `snapshot_inputs(_stage_of(args), Path(args.data_dir))` 传入 write_state；STATE_READY 行追加 `inputs=N文件`。rc 语义不变（0/3）。
4. `cmd_update`：L599 的 write_state 同样传 freshly 计算的快照（update 本来就 ingest 写→重算，天然自愈为新鲜冻结）。
5. 新增 `stale_freeze_files(state, stage, data_dir) -> list[str]`：返回漂移描述列表（"13a_bulk_density.csv: 冻结 sha ab12…↔现 cd34…" / "16_economics.json: 冻结时缺失，现已出现" / "新增表单族 X 不在冻结快照"）。state 无 "inputs" 键时返回 None（无法判定，与漂移区分）。
6. `cmd_check` 加载 state 后：漂移非空 → 追加 `{"severity": "fail", "check": "STALE_FREEZE", "detail": "formula_state 冻结早于 data/ 当前内容（{N} 文件漂移: …）——重跑 formula_runner execute 刷新冻结后再继续"}`；state 无快照 → `{"severity": "warn", "check": "STALE_FREEZE", "detail": "formula_state 无输入快照（旧版冻结），无法校验新鲜度——重跑 execute 启用"}`。rc 沿用 L521 现有映射：**漂移=fail→rc1，无快照=warn→rc2，新鲜=不变**。不新造 rc 码。

【二、build_output 硬拦（最终防线）】
`load_state_and_check(state_dir)` 改签名 `load_state_and_check(state_dir: Path, data_dir: Path, stage: dict)`，在手改检测门之后：调 stale_freeze_files，漂移非空或无快照 → `raise ValueError("formula_state 冻结与 data/ 不一致（STALE_FREEZE）——data/ 在冻结后被修改（含经 ingest 的合法修正）。唯一恢复路径：重跑 formula_runner execute（改参走 update）刷新冻结，再按 impacted 反查重派受影响章节。漂移: [...]")`。两个调用点 assemble(L358)/run_chapter_gate(L441) 同步传参——单章门同样硬拦，防「改了数据只重跑单章」。异常沿 main L536 现有 except → rc1。**不设绕过开关**：--allow-partial 只放深度门（L533 注释已言明「只放行 L2」），数值新鲜度不在降档范围。可选加一行：render_compliance_appendix 增加确定性文案「冻结输入校验: N 文件一致（STALE_FREEZE 无）」——交付物自带新鲜度凭据（sha 确定性，幂等不破坏）。

【三、静默 0/缺槽自检】
1. compute() 经济链 L408-419 重构：`price_ok = bool(pCu) or bool(pAg_kg)`；`price_ok` 为假 → `anomalies.append("16_economics prices 全空——E4/E5/E6 缺市场价输入，槽位跳过（缺参不编造；向用户要价或正文 [待确认]）")` 且 E4/E5/E6 全部不 emit（E6 一并挪进 guard，否则 0 价×精矿量=伪造负利润）；为真 → 现行为逐字不变。E4=0/E5=0 从此不再入册。
2. compute() 末尾（return L424 前）新增 `audit_critical_families(V, data, anomalies)`：(a) beneficiation 表存在且 locked_cycle.products 非空但无任何 `B1.recovery[` 槽 → anomaly "B1 选矿平衡族未产出（feed/yield/grade 存在非数值行被过滤）——核对 16_beneficiation"；(b) beneficiation 表缺失/空白 → anomaly "16_beneficiation 缺失——B1 族未计算（缺参不编造，ch5 相关槽位 [待确认]）"；(c) economics 有效但 ind_stats 空 → anomaly "14 块模型无工业矿行——E1-E7 经济链未计算"；(d) 已产出的关键槽（E4.price_conc/E5.gross_potential_yi/E6.static_profit_wy/L9.total_ore_wt）值==0 → anomaly "关键槽位 {k}=0——核对输入"。全部走既有 anomalies 通道 → cmd_execute/update 自动 rc=3（SKILL.md 门2 要求逐条呈现用户），anomalies 同时落盘 formula_state。
3. 缺槽的下游连锁：E4 不再产出后，章节硬引 {{SLOT:E4.price_conc}} 会落进 build 未知槽位门 FAIL（build_output.py:389 现成通道）——响而正确；撰写者按 chapter_craft.md 既有规则写 [待确认] 则放行且报告不出现假 0。

【四、文案（agent 可执行的恢复指令）】
build stderr 固定含 token `STALE_FREEZE` + 「重跑 formula_runner execute」+ 漂移文件清单；check 输出 `[FAIL] STALE_FREEZE: ...`。SKILL.md 同步：L177-178 命令表 execute 行补「3=含冻结自检 anomalies」、check 行改「0/1(含 STALE_FREEZE)/2(旧版状态无快照)」；L81 门2 段加一句「data/ 在冻结后被修改（含合法 ingest 修正）→ build STALE_FREEZE rc=1 硬拦，唯一出路=重跑 execute/update，禁止改章节或手改 state 绕过」；chapter_craft.md L28 补一句「槽位不在 formula_state.values（如缺价时 E4/E5 被跳过）写 [待确认]，禁硬引不存在 key」。

【边界与误伤面】
- touch/同内容重写 data 文件：sha 不变 → 不误报（这就是判 sha 不判 mtime 的原因）。
- ingest file 子命令指纹增量 no-op：文件字节未动 → 不误报。
- update 链路：写 data 后同进程重算+刷新快照 → 不自拦。
- --chapter 单章门在数据修正后立即重验：会拦——有意为之（单章注入的数字同样来自冻结 state）。
- 旧存量工作区（pre-fix 冻结的 state）：build 首跑即 rc1，恢复=重跑一次 execute，SKILL.md 写明。
- 大表单目录性能：forms 是小 JSON+2 CSV，逐文件 sha256 开销可忽略。

**改动文件**：D:/eai/eai-flow-main/skills/public/geological-report/scripts/formula_runner.py; D:/eai/eai-flow-main/skills/public/geological-report/scripts/build_output.py; D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md; D:/eai/eai-flow-main/skills/public/geological-report/references/chapter_craft.md; D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py

**新增测试**：
- test_execute_records_input_snapshot — execute 后 formula_state.json 含 inputs 键；每个 stage form 族有 sha256+bytes；缺失文件记 missing:true；同一 data/ 连续两次 execute 字节级全等（SC-4 幂等守卫，快照确定性）。
- test_check_stale_freeze_rc1 — tmp 副本工作区：execute → ingest.write_form_values 改 16_economics prices → check --anchors → rc=1 且 stdout 含 STALE_FREEZE 与漂移文件名；再 execute 刷新 → check rc=0。
- test_check_legacy_state_no_snapshot_warn_rc2 — 拷贝 state 删除 inputs 键 → check → rc=2 且含「无输入快照」。
- test_build_stale_freeze_hard_block — tmp 副本（state+chapters，_copy_chapters 同款，data 用 ws['data']）：execute 后经 ingest.write_form_values 改价不重跑 execute → build_output rc=1 且 stderr 含 STALE_FREEZE + 「重跑 formula_runner execute」；重跑 execute → build rc=0 BUILD_READY（合法修正→重冻结→放行的正向闭环）。
- test_build_chapter_gate_stale_freeze — 同上漂移场景跑 build_output --chapter ch9 → rc=1 含 STALE_FREEZE（单章门同样硬拦）。
- test_execute_price_blank_skips_zero_slots — tmp 工作区只填 industrial_params+block_model（economics/beneficiation 空白）：execute rc=3；values 无 E4.price_conc/E5.gross_potential_yi/E6.static_profit_wy 与任何 B1.recovery[；anomalies 含「prices 全空」与「B1 ...未计算」；E1/E2（不依赖价格）仍产出。
- test_update_refreshes_snapshot — fixture 式 impacted→update 后新 state 的 inputs 与盘上 data 文件 sha 一致（update 自愈路径）。

**风险**：
- 存量兼容：pre-fix 产出的 formula_state.json 无 inputs 快照，升级后首次 build 即 rc1（提示重跑 execute 即恢复）——属一次性迁移阵痛，需在 SKILL.md/发布说明写明。
- 槽位词汇收窄：缺价场景 E4/E5/E6 从「0 值在场」变「不在场」，已写死 {{SLOT:E4.price_conc}} 的章节会从「注入 0」变「未知槽位 FAIL」——这正是想要的响亮失败，但短期内未按 craft 规则写 [待确认] 的章节会多一轮 build 打回；ch5 在 beneficiation 空白时同理。
- 测试夹具耦合：若未来有人在 fixture 的 execute 与 build 之间插入 data 写入，会被新门拦截——这是门的本职，但新增测试必须用 tmp 副本工作区（_copy_chapters 同款），不得污染共享 ws。
- check 无快照=warn(rc2) 会在旧状态上把 rc 从 0 抬到 2：SKILL.md 命令表必须同步，否则 agent 把 rc2 误读为需人工仲裁而非重跑 execute（文案里已给出机械恢复路径，风险可控）。
- 误伤面已收窄：判 sha 不判 mtime 消除「同内容重写误报」；stage forms 键集比对只在 schema 演进时报——合法场景（ingest 修正后重跑 execute、update 链路、--allow-partial 深度降档）全部实测路径推演不被拦。

## F2-fabricated-values-undetectable（effort S）
**根因**：红线「缺失信息绝不编造」只有提示词层（SKILL.md L28），脚本层存在两条静默放行通道：(1) formula_runner.compute() 的 B1 段（L372-379）对 beneficiation/locked_cycle 整族缺失没有 else-anomaly 分支（对照同函数 block_model 缺失有 anomaly，L352-353）——整族缺失时循环零执行、无 B1 槽位、rc 可为 0，门2「必须逐条呈现用户」的义务（SKILL.md L81）根本不触发；agent 把编造值写入 data/ 后 B1 反而从编造输入算出「合法」结果干净通过。(2) E 链守卫（L385）只拦嵌套对象非 dict，dict 但键缺失时 L389/391/402/409/417 的 `.get(k, 0)`/`.get(c, 1.0)` 默认值让 0 价 0 成本静默算出 E4=0 并 emit，E3/E6 在 gCu/rCu 为 0 时同样静默跳过。结构性边界：ingest.py L286-299 接受 agent 组装的 JSON 且只做 schema 名+类型校验、无任何来源标记，编造值落盘后与用户值不可区分，SL2 溯源池（consistency.py L337-360）甚至把 data/ 一切值当合法源——因此脚本层只能强制「缺失/零值必暴露」，无法验「非零值是真还是编」。

**代码证据**：
- skills/public/geological-report/scripts/formula_runner.py:372-379 — B1 段无缺失分支：`ben = data.form("beneficiation")` / `lc = ben.get("locked_cycle") or {}` / `feed = dec(lc.get("feed_grade_cu") or ben.get("feed_grade_cu"))` / `for prod in lc.get("products") or []:` … `if feed.is_finite() and feed and y.is_finite() and g.is_finite():` emit——整族缺失时循环体零执行、无 B1 槽位、无 anomaly
- skills/public/geological-report/scripts/formula_runner.py:352-353 — 同文件同函数的对照先例：`elif "block_model" not in data.forms:` / `anomalies.append("14_block_model 缺失——L7-L13 资源量链未计算")`——证明『整族缺失记 anomaly』是既有模式，B1/E 链漏掉了
- skills/public/geological-report/scripts/formula_runner.py:385-387 — E 链守卫只拦嵌套对象非 dict：`if eco and not all(isinstance(eco.get(k), dict) for k in ("credibility", "rates", "concentrate", "prices", "costs")):` → anomaly 整体跳过——子对象是 dict（哪怕空/半填）即放行
- skills/public/geological-report/scripts/formula_runner.py:389,391-392,402,404-405,409-413,417-419 — 零默认值静默 emit：`kcat = {c: dec(eco.get("credibility", {}).get(c, 1.0)) ...}`、`loss = dec(rates.get("loss_rate", 0)) / HUNDRED`、`gCu, gAg = dec(conc.get("grade_cu_pct", 0)), dec(conc.get("grade_ag_gpt", 0))`、`pCu = dec(prices.get("cu_yuan_t", 0))` → `emit("E4.price_conc", price_conc, ...)`（0 也 emit）；E3/E6 在 `conc_t is None`（L405 `if gCu and rCu else None`）时 L406-407/L418-419 静默跳过无 anomaly
- skills/public/geological-report/scripts/formula_runner.py:483 — rc 合约已有强制通道：`return EXIT_ANOMALY if anomalies else EXIT_OK`——新增 anomaly 即自动 rc=3
- skills/public/geological-report/scripts/ingest.py:286-299 — 编造值不可检测的结构性边界：`values = json.loads(args.values)` → `errors = validate_values(spec, values)`（仅字段名在 schema + 类型矫正，L198-211）→ `doc.update(values)` → `doc["_meta"]["status"] = "filled"`——全链无来源标记，agent 组装的 JSON 在 CLI 边界即丢失 provenance
- skills/public/geological-report/scripts/consistency.py:337-360 — SL2 溯源池把 data/ 一切值当合法源：正文数值 ∈ numeric_pool（表单+CSV+formula_state）即 pass——编造值入 data/ 后反而『可溯源』，SL2 拦不住 data/ 层编造（B1C 条件式检查 L283-287 同样只在 declared_recovery 非 None 时比较，无『回收率槽位应当存在』的存在性检查）
- skills/public/geological-report/SKILL.md:28 — 红线仅提示词层：『2. **缺失信息绝不编造/推断/估算/补全**。缺就问用户；用户不给就留 [待确认] 槽位并在汇报中列出。』；L81 已有呈现义务：『rc=3 = 有 anomalies……必须逐条呈现用户并获确认』——但 rc 可为 0 时该义务不触发
- skills/public/geological-report/references/stages/exploration.json:481-491,567-578 — beneficiation 族 required=true 且 locked_cycle required（样例锚点 产率3.94%/铜17.46%/银98.07g/t/铜回收80.36%/银回收63.66%）；economics.prices required=true 且注明『价格必须用户提供可核实来源（红线）』——缺失本就不合法，新检查不与 schema 冲突
- backend/tests/test_geological_report_v2_scripts.py:120,134-145,184 — 现有 session fixture 填了完整 beneficiation（locked_cycle: feed 0.47, yield 2.55, grade 15.7, recovery 85.2）与完整 economics，且 execute 期望 `expect=(0, 3)` 已容忍 rc=3——新增 anomaly 不会破坏主 fixture，锚点断言 B1.recovery[铜精矿]=85.18（L557）依赖 B1 槽位在场，fixture 已满足

**修补设计**：【全部落在技能层，零 harness 改动；不新增 rc 码——复用既有 anomalies→rc=3→门2 强制呈现通道】\n\n1) formula_runner.py compute() B1 段（L372 后）：三档缺失 anomaly，文案镜像 L161/L353/L228 的 bug-2223 风格——\n   a. 整族缺失/空白：`if \"beneficiation\" not in data.forms or (not lc and not ben.get(\"feed_grade_cu\")): anomalies.append(\"10_beneficiation 缺失/空白——B1 选矿平衡链未计算（缺参不编造，空白表单与缺失等价）\")`\n   b. 半填：locked_cycle 在场但 `not lc.get(\"products\")` 或 feed 非 finite → `anomalies.append(\"10_beneficiation.locked_cycle 缺 products/feed_grade_cu——B1.recovery 未计算（缺参不编造）\")`\n   c. 逐产品：yield/grade 非 finite 的行 → 记 anomaly 跳过（仿 norm_row L228『行跳过，缺参不编造』），不再静默 continue。\n   注意 a 与 b 互斥（if/elif），避免双报。\n\n2) formula_runner.py compute() E 链段：\n   a. E4 emit（L412）后补：`if not price_conc: anomalies.append(\"E4.price_conc=0——16_economics.prices 缺失/为 0（价格必须用户提供可核实来源，红线；prices 为必填族，0 值即缺参）\")`\n   b. E3/E6 静默跳过处（L405-407 与 L418-419 的 `conc_t is None` 分支）补 else-anomaly：`anomalies.append(\"E3/E6 跳过——concentrate.grade 或 recovery 缺失（gCu/rCu 为 0），缺参不编造\")`（记一次即可，用标志位防重复）。\n   口径收紧原则：E4 零值检查只在 prices 族在场（required=true）时触发『0 即缺参』；不对全链做泛化零值扫描，避免误伤合法 0（如无伴生银矿种 gAg=0 是合法的，cu 部分仍非 0，price_conc 不为 0，不受影响）。\n\n3) consistency.py 可选加固：仿 FC2 presence-pairing（L233-237 `rep.add(\"FC2\", \"pass\" if has_l10 == has_prior else \"fail\", ...)`）新增 FC-presence：formula_state 存在 `B1.recovery[*]` 槽位 ⟺ 10_beneficiation.locked_cycle.products 非空，两侧不一致 → fail。防『章节引用了 B1 槽位但数据链没算』的错位。\n\n4) SKILL.md 门2 段（L81 附近）把关键冻结值核对升级为硬协议：『门2 无论 rc：B1.recovery[*]、L9.*、E4-E6 等关键冻结值必须逐值列表呈现用户（值+单位+来源公式），请用户逐值核对确认后才可进入章节派发』——这是针对『编造了非零值』唯一可行的用户侧防线（脚本无法验真，用户能）。\n\n5) rc 语义不变：0 干净 / 1 错误 / 2 需人工 / 3 anomalies 必读。所有新检查只 append anomalies → cmd_execute L483 自动 rc=3 → SKILL.md L81 门2 呈现义务触发。对现有测试影响：主 fixture 已填完整 beneficiation/economics 且 expect=(0,3) 已容忍 rc=3，预计零破坏；需跑全量核对个别『部分 economics』用例是否 rc 0→3。

**改动文件**：skills/public/geological-report/scripts/formula_runner.py; skills/public/geological-report/scripts/consistency.py; skills/public/geological-report/SKILL.md; backend/tests/test_geological_report_v2_scripts.py

**新增测试**：
- test_b1_family_missing_anomaly_rc3 —— 空白/缺失 10_beneficiation 跑 `formula_runner.py execute`：断言 rc=3、stdout 含 ANOMALY 行且文案含「10_beneficiation」「B1」「缺参不编造」、formula_state.json 无任何 B1.recovery 槽位
- test_b1_locked_cycle_empty_anomaly_rc3 —— beneficiation 在场但 locked_cycle.products=[]（或 feed 缺）：断言 rc=3、anomaly 指名缺 products/feed_grade_cu
- test_b1_nonfinite_product_row_anomaly —— products 行 yield 为 null：断言该行被跳过且有逐行 anomaly（仿 norm_row 文案），其余合法行仍产出
- test_e4_zero_price_anomaly_rc3 —— economics 嵌套对象齐全但 prices={}：断言 rc=3、anomaly 含「E4.price_conc=0」「红线」、E4 槽位值=0（仍 emit 不删，供门2 呈现）
- test_e3_e6_skip_anomaly —— concentrate.grade_cu_pct 缺失：断言 rc=3 且有「E3/E6 跳过——concentrate.grade 或 recovery 缺失」anomaly
- test_full_data_still_clean —— 现有完整 fixture（beneficiation locked_cycle 齐全 + economics 全填）：断言新增检查零触发（anomalies 不含新文案）、B1.recovery[铜精矿]=85.18 锚点仍过——回归主路径不被误伤

**风险**：
- 现有测试 rc 翻转：任何『economics 只填部分嵌套对象』或『beneficiation 只填一半』的用例会从 rc=0 变 rc=3——需全量跑 test_geological_report_v2_scripts.py 逐一核对；主 session fixture 已填完整且 execute expect=(0,3)，预判不破
- 合法零值误伤：若某矿种价格确为 0 或用户明确给 0 回收率，新检查会报 anomaly——但 rc=3 只是『必读呈现』不是阻断，用户确认后即可继续，代价仅一轮确认；且 prices 为 required 族，0 值本就可疑
- 文案双报：B1 整族缺失与 E 链跳过可能同时报（beneficiation 与 economics 独立缺失时）——anomaly 条数变多但语义各自正确，呈现层可接受；如嫌吵可合并为一条『选矿/经济数据缺失』
- consistency FC-presence 若实现过严（如要求双向严格相等）可能误伤『章节未引用 B1 但数据在场』的合法形态——按 FC2 同款双向等价实现即无此问题（有⟺有，无⟺无均 pass）
- SKILL.md 硬协议仍是提示词层，对不听话的 agent 无运行时强制——真正的强制面是 rc=3 门2，协议只是把『用户核对』义务显式化

**不可行边界**：完全防编造在脚本层不可行，原因：ingest.py cmd_forms/write_form_values 收到的 --values JSON 由 agent 组装（SKILL.md L67 铁律：澄清值落盘唯一途径就是 agent 转传），provenance 在 CLI 边界即丢失——值本身无来源标记，用户给的 4.15% 与 agent 编的 8.5% 落盘后逐字节不可区分；且 SL2 溯源合约（consistency.py L337-360）把 data/ 一切值当合法源，编造值入 data/ 后反而『可溯源』。要在写入层区分需 ask_clarification 回执与 ingest 写入间携带逐值 provenance 链（跨 harness ClarificationMiddleware/前端表单/技能 CLI 三层信任边界），违反本任务『不改 harness 核心』约束。缓解组合（即上述 fix_design）：① anomaly 强制使『整族缺失/零值』不再静默（rc=3 门2 必呈现，堵住本次实测的 B1 整族缺失与 E4=0 两条静默通道）；② 门2 关键冻结值逐值用户核对硬协议（用户看得见假值——脚本验不了真，用户能）；③ SKILL.md L68-69 已有『落盘值回显核对』提示词层要求，协议补硬后对『编造非零值』形成至少一道人工闸门。残余风险如实声明：与真值同量级的编造值（如 8.5% vs 4.15%）在无用户核对时仍不可检测。

## F1-manifest-drift-blindness（effort S）
**根因**：ingest.py 把 state_manifest.json 当纯写侧账本：register_file（ingest.py:101-128）在每次合法写入时登记 sha256，但唯一的下游门 cmd_check（ingest.py:509-549）从头到尾不读 manifest——它只按 stage schema 走查文件存在性与必填字段。因此 manifest 哈希清单没有任何消费者：agent 绕过 ingest 手写的文件（未登记）和被手改的已登记文件在门1 完全不可见，伪造的 _meta.status（合法词表仅 draft/filled，见 ingest.py:223/296/568）也无任何检查拦截，check 照常打印 GATE1_COMPLETE rc 0 放行。

**代码证据**：
- skills/public/geological-report/scripts/ingest.py:509-549 — cmd_check 全文不含 load_manifest/state_manifest/hash 字样，只有 `for fam, spec in stage.get("forms", {}).items(): ... p = data_dir / family_filename(spec); if not p.exists(): missing_forms.append(...)` + 必填字段走查——manifest 是 write-only 账本，无消费者
- skills/public/geological-report/scripts/ingest.py:101-128 — register_file 在 line 121 写入 `"sha256": sha256_file(data_dir / rel_name)`，但该哈希只被写入、从不被复核（grep 全技能仅 register_file 与 build_output/snapshot 各自独立的 sha 用途引用它）
- skills/public/geological-report/scripts/ingest.py:90-98 — load_manifest 已存在（含损坏降级 `return {"version": 1, "files": {}}`），但唯一调用点是 register_file 自身
- skills/public/geological-report/scripts/ingest.py:223,296,568 — `_meta.status` 合法词表仅两值：空白生成 `"status": "draft"`、写入路径 `doc["_meta"]["status"] = "filled"`（write_form_values 同）——实测伪造的 "completed" 可被词表白名单证明非法
- 合法写入路径全部登记（审计不误伤的证据）：ingest.py:279/298/325（forms 三路）、ingest.py:499（file/CSV）、ingest.py:570（write_form_values）、formula_runner.py:583+593（`import ingest` 后 CSV 整列改参直接写盘后调 `ingest.register_file(...)`）；data/ 之外无技能写者（progress.py:53,65 与 formula_runner.py:470 均写 state_dir）
- SKILL.md:175 — 现行合约文案 `| ingest.py check --stage S --data-dir D | 门 1 完整性 | 0=GATE1_COMPLETE / 2 缺项清单 |`；SKILL.md:72 — 门1 放行条件是『输出 GATE1_COMPLETE 才继续』，而该标记只在 rc 0 打印（ingest.py:548）——warn-only 设计仍会打印 GATE1_COMPLETE 放行，故必须 rc 阻断
- backend/tests/test_geological_report_v2_scripts.py:429 — 唯一会撞线的既有断言 `assert "tenement" not in r.stdout`（test_check_list_shaped_doc_no_crash）：line 418 手写覆盖已登记的 01_tenement.json 后，新 drift 行含 'tenement' 子串；line 418/429/992 是测试里仅有的三处手写 data/，另两处不经 check

**修补设计**：【改动 1：ingest.py 新增 audit_manifest(data_dir) -> list[str]，在 cmd_check 开头最先调用】(a) 读侧 drift：m = load_manifest(data_dir)（复用 line 90，manifest 缺失/损坏降级为空 files = 全部按未登记处理，fail-closed）；遍历 m["files"]：文件不存在 → `drift: {rel} manifest 已登记但盘上缺失`；sha256_file ≠ 登记值 → `drift: {rel} 盘上 sha256 与登记不一致（登记后被手改）`。(b) 盘侧 tamper：`sorted(data_dir.glob(\"*.json\")) + sorted(data_dir.glob(\"*.csv\"))` 顶层非递归（与 register 的裸文件名 rel_name 语义一致），跳过 MANIFEST_NAME、*.lock、*.tmp，不在 m[\"files\"] → `tampered: {name} 未在 state_manifest 登记（绕过 ingest.py 手写）`。(c) 语义层（防文件+manifest 双伪造，即本次实测攻击面）：对 format==json 且能解析为 dict 的登记文件，`_meta.status` 存在且不在 {\"draft\",\"filled\"} → `tampered: {rel} _meta.status='{v}' 非法（合法: draft/filled，ingest 是唯一写者）`；解析失败跳过（completeness 已报 JSON 损坏）、list 形状跳过（bug-3004 形状）。【改动 2：cmd_check 的 rc 编排】审计先行， findings 非空打印块：`GATE1_TAMPERED:` + 逐行 + `SUMMARY: tamper=N —— data/ 唯一写者是 ingest.py；禁止手写 data/*.json、禁止伪造 _meta.status` + `修复: 用 ingest.py forms --family X --values/--rows 或 ingest.py file 重写对应文件（写入即自动重登记哈希）；数据缺就问用户，绝不编造`；随后照旧跑现有 completeness 走查并打印 GATE1_MISSING（一轮修完）。rc 语义（保持 0/1/2/3 合约）：findings 或缺项任一非空 → EXIT_MANUAL(2)；两者皆空 → GATE1_COMPLETE rc 0。裁决=rc 2 阻断而非高声警告，理由：(1) 门1 放行条件字面是『输出 GATE1_COMPLETE 才继续』且只在 rc 0 打印——warn-only 等于没修；(2) rc 2=需人工，正好路由到『呈现用户/停下裁决』；(3) snapshot.py 已有完整性 mismatch→非零 的先例，但 rc 3 在 ingest 语义是『完成带异常、呈现后可继续』（门2 语义），篡改绝不可继续；新 rc 4 破坏合约。明确不加 --skip-audit 逃生旗——它会成为新绕过口（同 build_output.py:303 --targets 警告被用来绕基准的教训）。【改动 3：SKILL.md:175 命令表行】改为 `0=GATE1_COMPLETE / 2 缺项清单或 GATE1_TAMPERED（data/ 被手写/手改——按修复指引重走 ingest.py forms/file 重写登记，禁止绕过继续生成）`；SKILL.md:72 门1 步骤加一句：rc=2 且输出含 GATE1_TAMPERED 时按修复指引重写登记，不得把 TAMPERED 当缺项译给用户了事。【对既有测试的影响：52 个测试函数中仅 1 处断言需改】test_geological_report_v2_scripts.py:429 `assert \"tenement\" not in r.stdout` → 改为保意图的 `assert \"form: tenement\" not in r.stdout and \"field: tenement\" not in r.stdout`（bug-3004 原意是『该族不列缺项』，保持不变；line 431 `assert \"tenement\" in out` 因 drift 行+清单为空行仍通过）。ws session fixture（line 182 期望 rc 0）、test_gate1_missing_required_rc2(404)、test_null_required_field_passthrough(433)、test_parallel_writes_manifest_consistency(510) 全部走登记路径，审计静默、不受影响；line 992 手写 p.json 只调 build_output.render_front_matter 不经 check，不受影响。无 harness 改动、无新 rc、无新依赖。

**改动文件**：D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py（新增 audit_manifest() + cmd_check 开头接入；约 40 行）; D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md（门1 命令表 rc 文案 + 门1 步骤一句）; D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py（TestIngest 新增 6 测试 + 修 line 429 一处断言）

**新增测试**：
- test_check_flags_unregistered_handwritten_file — forms 生成后手写 99_fake.json → check rc 2，stdout 含 GATE1_TAMPERED 与『未在 state_manifest 登记』
- test_check_flags_hash_drift_on_registered_file — forms + write_form_values 填 tenement 后手改 01_tenement.json 字节 → rc 2，含『sha256 与登记不一致』
- test_check_flags_missing_registered_file — forms 后 unlink 一个已登记文件 → rc 2，含『盘上缺失』
- test_check_flags_forged_status_despite_valid_hash — 手写完整合法值+_meta.status='completed' 且同步手改 manifest 里该文件的 sha256 为正确值 → 哈希审计通过但语义层拦截，rc 2 含『_meta.status=completed 非法』（覆盖本次页面实测的精确攻击形态）
- test_check_audit_ignores_lock_and_tmp — data/ 落 state_manifest.json.lock 与 01_tenement.json.123.tmp → 审计对二者静默
- test_check_audit_clean_on_registered_flow — forms + write_form_values + ingest.py file 灌 CSV 全合法路径 → rc 0 且 GATE1_TAMPERED 不在 stdout（守住三条登记写路径的误伤面）
- 既有 test_check_list_shaped_doc_no_crash line 429 断言收窄为 form:/field: 前缀（随本改动一并落地）

**风险**：
- 毫秒级竞态：写者脚本先写盘后 register_file（ingest.py:297→298、498→499、569→570；formula_runner.py:588→593），窗口内并发 check 会误报 drift——progress.py 状态机每轮恰好派发一条命令、天然串行，实际风险极低；如需归零可在 audit 读 manifest 时复用同一 .lock（可选加固，不必做）
- 旧线程/丢失 manifest 的 data/ 目录：全部文件按未登记报 tamper——fail-closed 有意为之，但会在历史线程上高声暴露；修复文案（重跑 ingest 重写登记）即恢复路径
- 未来新增的合法写者若直写 data/ 顶层而不 register_file 会在门1 被拦——这正是控制点生效；但审计刻意只扫顶层非递归，未来若在 data/ 下加子目录产物（如导出件）不会误伤
- test_geological_report_v2_scripts.py:429 断言必须同步更新，实现者不得为消除红灯而弱化审计本身；改法已保 bug-3004 原意（该族不列缺项）
- water-drainage-report 无 ingest.py（数据模型不同），本次无需移植；但 snapshot.py 文档提到的三副本同步约定不覆盖此差异，若未来给 water 建 ingest 应随建随带同款审计
- 审计把 findings 打到 stdout（与 GATE1_MISSING 同通道，SKILL.md 派发协议按 stdout 标记解析）——若有人后续只 grep 'GATE1_' 前缀做解析需注意新增 GATE1_TAMPERED 标记

**不可行边界**：脚本层存在防御残余：agent 若同时伪造文件内容 + manifest 哈希条目 + 把 _meta.status 写成合法值 \"filled\"，哈希与词表审计均通过——本设计只把伪造成本从『随手写』提高到『需精确重算并回写 sha256 + 模仿 ingest 全部不变量』。根治需文件系统级只读（沙箱挂载 ro）或 extensions/backend 层落盘审计（唯一写者白名单按 pid/进程校验），属 harness/extensions 层改动，超出本最小修补；若实测再现该级仿冒，建议另立 findings 在 extensions 层做 data/ 目录 mtime+hash 巡检。

## F6-scratch-files-in-datadir（effort S）
**根因**：ingest.py 的 cmd_check 是"单侧检查"：只遍历 stage schema 期望的表单族（`for fam, spec in stage.get("forms", {}).items()`），从不盘点 data/ 里实际存在什么、也不读 state_manifest.json 做差集。因此 data/ 下任何 manifest 未登记的文件（如 agent 绕开超长 --values 时写入的 geo_supplement_01.json scratch）对门1 完全不可见——check 照常 GATE1_COMPLETE rc 0。而"唯一写者"契约的所有合法写路径（forms 空白生成/values/rows、file 子命令、formula_runner update 复用的 write_form_values/register_file）确实 100% 登记 manifest，所以"在盘但未登记"是一个可靠的违规信号，只是没人检查它；仅有的快照层（snapshot.py hash_manifest rglob data/）会把 scratch 一起 hash 进快照，但同样无人与 manifest 比对。

**代码证据**：
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:509-549 — cmd_check 只遍历 `for fam, spec in stage.get("forms", {}).items():`，从不 load_manifest、从不 iterdir data/；540-549 行 `if missing_forms or missing_fields: print("GATE1_MISSING:")…return EXIT_MANUAL` / `print("GATE1_COMPLETE: …")`——干净与否完全由"schema 期望集"单侧决定
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:101-128 — register_file 是唯一登记入口（manifest load-modify-write + O_EXCL 锁），合法调用点全覆盖：forms 空白生成 :325、forms --rows CSV :279、forms --values JSON :298、file 子命令 :499、write_form_values :570；formula_runner.py:593（CSV 族 update）与 :597（→ingest.write_form_values）也收口到这里——即合法路径无一遗漏，扫未登记不会误伤这五条
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:53-59 — atomic_write_text 残留形态：`tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"`，进程在 write_text 与 os.replace 之间崩溃即留 `*.tmp` 于 data/
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:106-108 — `lock = data_dir / (MANIFEST_NAME + ".lock")`，docstring 自认"持锁进程崩溃会留死锁文件→10s 超时报错，需人工删 .lock"——.lock 残留是已知合法存在于 data/ 的文件
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py:90-98 — load_manifest 在 manifest 缺失/损坏时静默返回 `{"version":1,"files":{}}`——若新检查在 manifest 为空时跳过，就会复刻 buglog-2189 实证教训（bid-proposal："空登记+在盘权威文件=注入信号"，旧版提前 return [] 导致手写文件全链路隐形）
- D:/eai/eai-flow-main/skills/public/geological-report/scripts/snapshot.py:61-71 — hash_manifest 对 data/ 做 `base.rglob("*")`，scratch 文件会静默进入快照 hash 清单但无人与 manifest 比对——印证"manifest 未登记、check 不报"且快照层也不设防
- D:/eai/eai-flow-main/skills/public/bid-proposal-writing/scripts/state_guard.py:108-140 — 同仓先例：is_unregistered 助手 + verify_state_files 的"在盘但未登记签名(疑似脚本外直写/手写注入)"拦截 + "已登记内容被改/被删永远拦截; 非自有文件的未登记注入同样拦截"——F6 设计与之同族，语义可直接对齐
- D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py:411-431 — test_check_list_shaped_doc_no_crash 直接 raw 写 `(d / "01_tenement.json").write_text(...)`（已登记名，sha 与 manifest 不符）——新检查必须是 presence-only，不能顺手做 hash 级篡改检测，否则此测试（bug-3004 回归）即红；这也把检查范围钉死在 F6 本身
- D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py:75-180 — session 级 ws fixture 的 data/ 全部经 ingest.py forms / write_form_values / file 子命令落盘（上传原件在独立的 ind/ 目录），盘上只有已登记表单 + state_manifest.json——fixture 不会被新检查打破
- grep 证实：8 个技能脚本中无任何消费者对 data/ 做 glob/iterdir 寻数（仅 snapshot rglob 做 hash 存档、build_output.py:519 对 outputs/ 查 stray .md），formula_state/progress/consistency/chapter_manifest 均写独立 state/ 目录——data/ 的合法内容集合 = 已登记表单文件 + state_manifest.json，边界干净

**修补设计**：只改 ingest.py 的 cmd_check（+1 个纯函数助手），消费端与其它脚本零改动。【新助手 scan_data_dir_inventory(data_dir) -> tuple[list[str], list[str], list[str]]】在 cmd_check 开头（load_stage 之后）调用：`manifest = load_manifest(data_dir)`；`registered = set(manifest.get("files", {}))`；`if not data_dir.is_dir(): return ([], [], [])`；对 `sorted(data_dir.iterdir())` 只取 `p.is_file()`（子目录不拦——无任何合法生产者在 data/ 建目录，忽略即可，避免范围膨胀）。分类规则：(a) 名字 == state_manifest.json 或 ∈ registered → 跳过；(b) 名字 == "state_manifest.json.lock" 或 endswith(".tmp")（覆盖 atomic_write_text 的 `{name}.{pid}.tmp` 形态）→ residue（残留清单）；(c) 其余 → unregistered。【rc 码语义裁决：rc=2（EXIT_MANUAL）阻断，不是警告】理由：check 是门1 前置，rc 2 在 SKILL.md 控制器契约里就是"停下、把输出呈现、解决后重跑"；纯警告（rc 0 附注）正是本次实测失败形态——agent 会无视注记继续走门。不新增退出码值，现有 rc 集合 {0,1,2,3} 不变，消费方无兼容问题。cmd_check 收尾逻辑改为：`if missing_forms or missing_fields:` 打印既有 GATE1_MISSING 块不变；`if unregistered:` 追加打印 `GATE1_UNREGISTERED:` 块，每行 `  file: {name}（在 data/ 但 state_manifest.json 未登记——data/ 唯一写者=ingest.py，疑似临时文件或脚本外手写）`；两块任一非空 → SUMMARY 行扩为 `SUMMARY: missing_forms=X missing_fields=Y unregistered=Z（缺项必须向用户收集，禁止编造；未登记文件须先处置）` → return EXIT_MANUAL。UNREGISTERED 块尾固定附处置指引三行：`处置: ①纯草稿/临时中转 → 移出 data/（放 workspace 或 /tmp），超长 --values 用 ingest.py forms --values "$(cat /tmp/x.json)" 正式入库; ②应入库数据 → 走 ingest.py forms/file 正式登记后删除原文件; ③绝不手写或保留 data/ 下未登记文件`。仅 residue 非空时：不阻断，打印 `HYGIENE: {name} 残留（可删除；.lock 残留会阻塞后续写入）` 后照常走 GATE1_COMPLETE rc 0。同时把 ingest.py 模块 docstring 第 19 行退出码契约改为 `2 需人工（OCR 路由、缺必填、data/ 存在未登记文件）`。SKILL.md 两处：data/ 铁律行（约 :38）补一句"临时中转 JSON 一律不落 data/（check 报 GATE1_UNREGISTERED rc2 拦截），放 /tmp 或 workspace 后经 --values \"$(cat …)\" 入库"；check rc 契约处同步。边界情况：①manifest 缺失/损坏（load_manifest 回空）时检查照常执行——空登记+盘上有文件=全部列 UNREGISTERED（buglog-2189 教训，禁止提前 return）；②forms 刚生成、check 紧跟：全登记，rc 不变；③原子写与 register_file 之间毫秒级窗口内并发 check 理论上会把合法新表单误报——概率极低且 message 已含"刚跑过 ingest 可重跑 check"的处置语义，不做名字豁免（豁免 stage.forms 已知名会放过"手写同名表单"这一 buglog-2189 实证最常见违规形态）；④对现有 136 个测试：本文件 52 个逐一核对，调 check 的 5 处（fixture :182、test_gate1_complete、test_gate1_missing_required_rc2、test_check_list_shaped_doc_no_crash、test_null_required_field_passthrough）data/ 内容全部已登记或为已登记名 raw 改写（presence-only 不拦），且既有断言均为子串断言非全文比对——零破坏。

**改动文件**：D:/eai/eai-flow-main/skills/public/geological-report/scripts/ingest.py; D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md; D:/eai/eai-flow-main/backend/tests/test_geological_report_v2_scripts.py

**新增测试**：
- TestIngest.test_check_unregistered_scratch_rc2 — forms 生成后 raw 写 (d/"geo_supplement_01.json")，check expect=(2,)；断言 stdout 含 "GATE1_UNREGISTERED" 与 "geo_supplement_01.json"，且 rc 语义为需人工（复刻 F6 实测形态作主回归）
- TestIngest.test_check_empty_manifest_files_on_disk_all_unregistered — 空 data/ 不跑 forms，直接 raw 写两个 JSON，check expect=(2,)；断言两个文件名都出现在 GATE1_UNREGISTERED——锁死"manifest 缺失时检查不得跳过"（buglog-2189 教训）
- TestIngest.test_check_residue_tmp_lock_not_blocking — forms 后手造 state_manifest.json.lock 与 00_project.json.99999.tmp，check（expect=(2,)，空白表单本身缺项）；断言 stdout 不含 GATE1_UNREGISTERED、含 HYGIENE——残留只 WARN 不拦
- TestIngest.test_check_unregistered_resolved_clears_block — 接上 scratch 用例：删除 geo_supplement_01.json 后重跑 check，断言 GATE1_UNREGISTERED 消失（rc 仍 2 因其余表单缺，验证的是块消失而非 rc 翻转）
- TestIngest.test_check_registered_name_raw_rewrite_not_unregistered — 复用 test_check_list_shaped_doc_no_crash 的 raw 写 01_tenement.json 场景，显式断言 stdout 不含 GATE1_UNREGISTERED——钉死 presence-only 范围边界（hash 级篡改检测留独立 finding）

**风险**：
- 误伤面①（并发窗口）：ingest.py:297-298（及 :278-279、:498-499）先 atomic_write_text 后 register_file，毫秒级窗口内并发 check 会把合法新表单报 UNREGISTERED。check 与 ingest 并行本身罕见；接受并靠重跑 check 自愈，不做已知名豁免（豁免会放过手写同名表单）。
- 误伤面②（残留类）：.tmp/.lock 残留被归入 HYGIENE 不阻断——若误做成阻断会与 bug-2217 并发修复自身的瞬时文件打架；设计已钉死只 WARN。
- 误伤面③（agent 把上传原件备份进 data/）：会被拦——这符合 SKILL.md data/ 契约（唯一写者=ingest.py），消息给出正确去向（uploads/、workspace），属有意拦截非误伤。
- 范围红线：检查必须 presence-only，不得顺手做 sha256 篡改比对（manifest 里现成有 hash）——否则 test_check_list_shaped_doc_no_crash（:418 raw 写已登记名）与 null 部分收集等合法流被误伤，且篡改检测是独立 finding。
- 行为面：原本 GATE1_COMPLETE 的流程现在可能 rc2 停下——这是拦截目的本身；rc 值域未扩充，SKILL.md 消费契约（0/1/2/3）不变，无下游解析兼容问题。
- snapshot.py:68 rglob 会把 scratch 一并 hash 进快照：新检查在门1 拦截后，正常管线快照里不应再出现未登记文件；不为此改 snapshot。

**不可行边界**：脚本层无法"预防"agent 把 scratch 写进 data/（写文件走 harness 沙箱 write_file/bash，技能层无路径拦截点；buglog-19807 E2E 已实证"提示词级铁律+事后审计对弱模型不够，需机制层拦截"）。本设计能做到的是门1 处的确定性检出+阻断（check rc2），这已把"scratch 混入 data/ 后静默过门"的窗口收窄到零；若要真正预防（沙箱路径黑名单 / data/ 目录 ACL），须动 harness 或部署层，超出技能层范围，且按仓库惯例（no-core-code-changes）不建议。

## F4-gate2-not-enforced（effort M）
**根因**：门 2 在控制器协议（SKILL.md）里只被定义为「anomalies 逐条呈现并获确认」（SKILL.md:81），type_verdicts 四句确认义务只存在于 stage schema 的 note 字段（exploration.json:505「人工确认关卡字段（门2）」）和面向子代理的 XS3 写作规则（chapter_craft.md:29）中，agent 按字面执行就拿 formula_runner 的 anomalies 表（formula_runner.py:480-483, rc=3）冒充了门 2。且 SKILL.md 门 2 段落没有其他等待点都有的阻塞语（对比 :64-65「结束回合等待」、:136「用户答复前不运行 confirm-key-points」、:140「不回表单就停在那」）——普通消息呈现本就不终止 run。机制层 progress.py 完全没有门 2 概念：cmd_init 只拒重复 init（progress.py:190-192）、cmd_next 无前置直接路由 WAVE1 派发（progress.py:97-132）、退出码只有 0/1（progress.py:33），同类确认硬闸先例 key_points_confirmed（progress.py:200, 264-271）从未推广到门 2，于是同一 run 内 chapter_planner → progress.py init → next → 派发一路合法走完，无任何一处被拦。

**代码证据**：
- skills/public/geological-report/SKILL.md:81 — 「**门 2**：rc=0 干净通过；rc=3 = 有 `anomalies`（过滤行/缺参降级/口径注记），**必须逐条呈现用户并获确认**再生成」——门2 定义里没有 type_verdicts 四句，也没有任何停等语义
- skills/public/geological-report/references/stages/exploration.json:505 — 「{"name": "type_verdicts", ... "note": "人工确认关卡字段（门2）；判定词 XS3 逐字一致；样例锚点四条"}」——四句确认义务只存在于 schema note，控制器不会读到
- skills/public/geological-report/scripts/progress.py:186-192 — cmd_init 只拒重复 init：「if p.exists(): print(...已存在...); return EXIT_ERROR」，其后直接建全 PENDING doc，无任何门2 前置
- skills/public/geological-report/scripts/progress.py:97-132 — next_action WAVE1 分支直接输出「[NEXT] 派发: ch1」+ 派发契约，无 gate2 检查；progress.py:210-213 cmd_next 亦无
- skills/public/geological-report/scripts/progress.py:33 — 「EXIT_OK, EXIT_ERROR = 0, 1」——progress.py 状态机只有 0/1 两态，无「等用户」语义
- skills/public/geological-report/scripts/progress.py:200,264-271 — 先例已在：key_points_confirmed 字段 + cmd_confirm（confirm-key-points 解锁 ch10），同样的用户确认硬闸没有推广到门2
- skills/public/geological-report/scripts/formula_runner.py:480-483 — 「print(f"STATE_READY: ... anomalies={len(anomalies)}") / print(f"  ANOMALY: {a}") / return EXIT_ANOMALY if anomalies else EXIT_OK」——实测中被 agent 当门2 呈现的 anomalies 表来源
- SKILL.md:64-65 — 反例对照：收数路径有真阻塞语义「中断机制一次只挂起一张表单」「然后**结束回合等待**」；SKILL.md:136（4.3）「用户答复前不运行 confirm-key-points」；SKILL.md:140（4.5）「用户不回表单就停在那，不推进」——唯独门2 段落缺失同类措辞
- skills/public/geological-report/references/chapter_craft.md:29 — 「判定词（水文/工程/复合类型等 type_verdicts 值）**逐字**写入正文（XS3）」——四句逐字只是子代理写作规则，不是控制器确认门
- skills/public/geological-report/scripts/consistency.py:199-207 — XS3 从 hydro_eng_env 表单读 type_verdicts 逐字比对章节——确认门缺位导致 XS3 口径无用户背书
- backend/tests/fixtures/geological_report/e2e-full/page-test-script.html:121,494 — 页面实测脚本 #gate2「门2 冻结确认」节——实测失败即发生在此节

**修补设计**：三层最小修补（全落技能层，零 harness 改动）。

【A. SKILL.md 措辞硬化】
1) 替换 SKILL.md:81 单段门2 为两段式：
「**门 2（两段式，缺一不可）**：
- **2a 类型判定四句确认（rc=0 也必做）**：读 `data/11_hydro_eng_env.json` 的 `type_verdicts`，把 hydro_type / engineering_type / environment_type / combined_type 四句判定词**逐字**呈现用户，请其回复「确认类型判定」或提出修改。**呈现必须走单表单 `ask_clarification`（复用 4.3 要点包同款——ClarificationMiddleware 挂起即真停 run，普通消息呈现=不阻塞，本次实测即栽在此）**；同回合可先以普通消息呈现 2b anomalies 表（不占单回合一次 ask_clarification 额度），卡片只承载四句+确认请求。用户改词 → `ingest.py forms --family hydro_eng_env` 落盘 → `formula_runner.py` 重跑 → 重新呈现。收到确认语后 `progress.py confirm-gate2 --state-dir T --data-dir D --note "<用户确认语原文>"`。
- **2b anomalies 逐条呈现（rc=3 时）**：保留现有文字 + 追加「**anomalies 表 ≠ 门2 全部，绝不能拿 2b 冒充 2a**」。」
2) SKILL.md:107（4.0）追加前置：「init 前置 = 门 2a 已确认（state/gate2.json 在场；否则 init/next/mark 一律 rc=2 硬拒）」。
3) 命令速查表：init 行 rc 列 → 「0 / 1 已存在 / 2 门2未确认」；next 行 rc 列 → 「0 / 2 GATE2_WAIT 停等」；新增行 `progress.py confirm-gate2 --state-dir T --data-dir D --note "…"`｜门2 四句已经用户单表单确认（落 state/gate2.json，唯一写者=progress.py）｜0 / 2 type_verdicts 缺失或四句有空 / 1 路径错误。

【B. progress.py 硬闸（可行性：高——key_points_confirmed 先例照抄）】
1) progress.py:33 改 `EXIT_OK, EXIT_ERROR, EXIT_GATE_WAIT = 0, 1, 2`；rc=2 语义=「门2 未确认，等用户」（对齐 ingest check rc=2 缺项清单、consistency rc=2 需人工的既有「需人工介入非错误」语义）。模块 docstring:21 退出码行同步。
2) 新增 `VERDICT_KEYS = ("hydro_type","engineering_type","environment_type","combined_type")` 与 `gate2_marker(state_dir)->dict|None`（读 state/gate2.json，confirmed=True 且四句非空才有效；损坏/缺失返回 None）。
3) 新增子命令 `confirm-gate2`（cmd_confirm :264 同款）：读 `{data_dir}/11_hydro_eng_env.json` 的 type_verdicts；任一句缺失/空 → rc=2 stderr 列明缺哪句（「缺失信息绝不编造，先 ingest 补齐再确认」）；数据文件缺 → rc=1；通过则原子写 `state/gate2.json` = {"confirmed": true, "verdicts": {...}, "note": 用户确认语原文, "confirmed_at": ISO}，stdout `GATE2_CONFIRMED → progress.py init --stage S --state-dir T --data-dir D`。
4) cmd_init(:187)：重复 init 检查之后、建 doc 之前，`gate2_marker` 为 None → stderr/stdout GATE2_REQUIRED（指引呈现四句+confirm-gate2 命令），return 2。兼容豁免：旧 progress.json 已在场且任一章 status≠PENDING 或 total_dispatches>0（改造前已在途的任务）视为 grandfathered 放行续跑。
5) cmd_next(:210)/cmd_mark(:226)：load 后 marker 为 None → stdout GATE2_WAIT（四句呈现指引 + confirm-gate2 命令 + 「发出后结束回合等待」），return 2。mark 加闸是防手搓 progress.json 绕过的纵深（测试已有直改 progress.json 先例 :80-81，marker 仍在夹具先落即可）。
6) 可选严格项（~6 行，建议做）：cmd_next 比对 marker.verdicts 与 data 现值，漂移 → rc=2「判定词已变更——重新呈现并 confirm-gate2」，保证修改回路改判定词必须重获确认；嫌吵可降级为 stdout 警告。
7) cmd_status(:216) 加显「门2确认=True/False」。state/gate2.json 唯一写者=progress.py（红线延伸，snapshot rglob 自动纳哈希）。

【边界情况】① 门2 前公式 rc=3：同回合先普通消息贴 anomalies 表，再发 2a 单卡片，不违「单回合至多一次 ask_clarification」；② 恢复续跑：gate2.json 与 progress.json 同在 state/，断点续跑无损；③ 用户改判定词：走 ingest→formula_runner 重跑→漂移检测/重新呈现；④ 四句未收齐（type_verdicts 缺句）：confirm-gate2 rc=2 拒绝，留 [待确认] 问用户，绝不编造。

**改动文件**：D:/eai/eai-flow-main/skills/public/geological-report/SKILL.md; D:/eai/eai-flow-main/skills/public/geological-report/scripts/progress.py; D:/eai/eai-flow-main/backend/tests/test_geo_progress.py; D:/eai/eai-flow-main/backend/tests/test_geo_controller_build.py; D:/eai/eai-flow-main/backend/tests/test_geological_report_skill.py; D:/eai/eai-flow-main/backend/tests/fixtures/geological_report/e2e-full/page-test-script.html

**新增测试**：
- backend/tests/test_geo_progress.py::TestGate2::test_init_refused_without_gate2 — 无 gate2.json 时 run("init",...,expect=(2,))；输出含 GATE2_REQUIRED/门2 未确认；progress.json 未落盘
- test_geo_progress.py::TestGate2::test_confirm_gate2_writes_marker — data/11_hydro_eng_env.json 含四句 → confirm-gate2 rc=0；gate2.json confirmed=True、四句 verbatim、note/confirmed_at 在场；随后 init rc=0、next 输出 WAVE1 派发
- test_geo_progress.py::TestGate2::test_confirm_gate2_missing_verdict_rc2 — type_verdicts 缺 combined_type → rc=2；stderr 点名缺失键；gate2.json 未写
- test_geo_progress.py::TestGate2::test_next_and_mark_rearm_when_marker_deleted — confirm+init 后删 gate2.json → next rc=2（GATE2_WAIT）、mark rc=2（纵深）
- test_geo_progress.py::TestGate2::test_legacy_inflight_progress_grandfathered — 手搓含 DRAFTED 章的 progress.json 且无 marker → next 放行（兼容豁免）
- test_geo_progress.py::TestGate2::test_gate2_drift_rearms — confirm 后改 data 判定词 → next rc=2 含「判定词已变更」（若采纳严格项）
- backend/tests/test_geological_report_skill.py 新增 test_gate2_hard_gate_documented — SKILL.md 含 confirm-gate2 / GATE2_WAIT / 结束回合等待 / anomalies 表 ≠ 门2 全部；不破坏既有 :103-140 子串断言（已核对全部保留）
- 既有夹具两处 +2 行（非新测试）：test_geo_progress.py ws 夹具（:32-37）写最小 data/11_hydro_eng_env.json（四句）+ run("confirm-gate2")；test_geo_controller_build.py ctrl 夹具（:93 前）+ run("progress.py","confirm-gate2","--state-dir",state,"--data-dir",data)——e2e-full 夹具 11_hydro_eng_env.json 已含全部四句（已验证非空），20+16 个既有测试原断言不变

**风险**：
- 在途任务兼容：改造前已 init 的旧 progress.json 无 gate2.json 会被 next/mark 拒 rc=2——已设计 grandfathered 豁免（任一章非 PENDING 或 total_dispatches>0 放行），实现时勿漏
- 测试夹具必须同步：test_geo_progress.py ws 夹具与 test_geo_controller_build.py ctrl 夹具不加 confirm 步骤则约 35 个既有测试全红（fail-loud 可接受，但 PR 说明要写明）；test_geological_report_v2_scripts.py 52 测零影响（不用 progress.py），其余 3 个 geo 测试文件（bug2223/e2e_full/v2_replay，共 30 测）也不用 progress.py
- SKILL.md 内容断言为子串式，改写保留「门 2」「GATE1_COMPLETE」「anomalies」「呈现用户」等既有断言锚点即可全过（已逐条核对 test_geological_report_skill.py:103-140）；confirm-key-points 断言（:289）不受影响
- 判定词漂移重确认会在修改回路多一轮用户交互——协议上正确（判定词即确认对象）但可能被嫌吵，可降级为警告；默认建议保留 rc=2
- 门 2a 走 ask_clarification 卡片受「单回合至多一次」约束：必须 2b（普通消息）与 2a（卡片）同回合且卡片唯一，SKILL.md 措辞已显式写明，实现时不得把 anomalies 也做成卡片
- SKILL.md 再增措辞有上下文成本——用替换而非追加，控制在净增 ~15 行内

**不可行边界**：脚本层无法物理终止 agent 的 run：progress.py 只能拒答（rc=2），LLM 仍可无视协议继续调其他工具；纯普通消息呈现门2 永远只能软阻塞（本次实测的直接根因之一）。可获得的真硬停 = harness 既有 ClarificationMiddleware 对 ask_clarification 的 Command(goto=END) 中断——零 harness 改动，靠 SKILL.md 把门 2a 规定为单表单 ask_clarification（复用 4.3 要点包模式）实现；progress.py rc=2 三闸是第二层机械兜底。残余缺口：完全绕开 progress.py 的流氓路径（不 init 直接派发、不跑 build 直写 outputs/）不由本闸覆盖，如需封死可后续在 build_output --output 加 gate2 标记校验（本轮范围外）。

---

## 增补：T3 干净线程复审新增 findings（2026-08-30）

> 来源：干净线程 12703344 全流程复测（run 71c86a1d→ef795447，共 14 run）。以下并入第四轮范围候选。

### F7-gate-misses-form-family（bug-3027）— P1（S）
最终交付正文残留 27 处 `{{FORM:...}}` 契约占位符（industrial_params×10 / project.cutoff_date×4 / standards_index×4 / project.name×1）。契约层（exploration.json）用 `{{FORM:表单.字段}}` 指示写作代理从 ingest 表单取值，代理把占位符原样抄进正文；build_output 槽位残留检查只覆盖 `{{SLOT:`/`{{TABLE:` 两族，漏 FORM 族——与 ⑲（bug-3018 发明槽位门拦截）同类门拦截缺口的第三族盲区。**修法**：build_output 门验增加 FORM 族残留 FAIL（与 SLOT/TABLE 同一检查点一行扩展）；门报错文案提示「FORM 占位符应解析为表单真实值或 [待确认]」。T3 期已以用户身份指令 lead 手工清零（run 14）。

### F8-bracket-double-bracket-typography — P2（S）
正文 4 处 `[[待确认]]` 双括号写法（ch8 标高句）。代理把 [待确认] 写成 `[[待确认]]`，门与 consistency 均不查。修法：单章门/consistency 增加 `[[待确认]]` 归一化警告或 build 时替换；亦可在 chapter_craft.md 写明唯一合法写法。

### F9-runs-status-label-misleads-patrol — P2（观测性，后端 lane）
`on_disconnect=continue` 投递后，runs 表 status 显示 `interrupted` 而 checkpoint step 持续推进（实测 2713→2728/45s）——status 跟随 SSE 流状态而非图执行态。巡逻/监控若以 runs.status 断 run 死活会误杀重启（本判差点触发 gateway restart）。**修法候选**：RunManager 在 on_disconnect=continue 断开时保持 status=running（或引入 streaming 状态）；最小做法仅文档化「以 checkpoints step 推进为活性真相源」。属 app/gateway 层（非 harness），需 EAI-CUSTOM 注释。

### 复测确认项
- **bug-3022**（formula_runner 历史分类 B/C 误校验）在干净线程复现——维持 P1 修补候选（按 category+历史分类放行）。
- **⑯ 双账本分叉**（progress 账本滞后）在 lead 被点名纠正 `progress.py mark` 纪律后显著改善——支持「SKILL.md 把 mark 写成门后强制步骤」的修法（并入 F4 门2 重写）。
- **㉗ key_points 纠正不传导**（已 VERIFIED 章节正文残留旧口径）实战发生并已通过定向修复轮闭环——支撑 F4 门2「确认后扫描受影响已验收章」的设计。
- SSE 投递通道 `on_disconnect=continue` 全程稳定（run 6→14 无一误杀），T1/T2/T3 的「离奇 run 死亡」根因彻底定案并根治（见 bug-3021 链）。
