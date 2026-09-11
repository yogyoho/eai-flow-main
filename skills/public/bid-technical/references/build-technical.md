# 阶段4a+4: 技术响应生成(供源级联) → build 两文档册集渲染(分组执行指南)

进入条件: 确认门1 已过(snapshot `phase` ∈ {3/4-合并与构建}); 补遗到达时先走 stage3-merge-gate2 再回来 build。
本组配套契约(进入前**先读全篇** `tech_response_prompt.md`(供源级联+编造边界+落位规则+输出契约)与 `responses.schema.json`)。
命令一律照抄 SKILL.md 速查表(唯一合法调用形态); 本文给流程与判据, 不重复罗列调用。

## 阶段4a 技术响应生成(供源级联——v4 编造政策)

对象=clauses.json 里 `category ∈ {technical, service}` 的**活**条款(商务/资格/格式条款走模板镜像管线, 不走本通道)。

供源级联(逐条款按序评估, **不跳步**; 全文见 tech_response_prompt.md):

1. **第一层 样例库检索(sample)**: RAGFlow 投标样例知识库按章节组批量检索(filters 圈定+top-K 段落本地匹配 clause_id, **不逐条款发请求**)。命中→参照样例段落**仿写**: `source_mode="sample"`、`citations` 逐条 `{title, source_doc, quote_span, quote}`(sample 引用无 URL)、`needs_human_verify=true`。
2. **第二层 编造(fabricated)**: 样例库无命中/未建→依据条款原文+通用工程知识**编写完整响应正文**, 逐项响应不留空: `source_mode="fabricated"`、`needs_human_verify=true`(**强制**, validate 拒收漏标项), 全量进人核清单交付前批量确认。**编造是合法默认, 不是失败**——空项=技术偏离=丢分。
3. **self 重组**: 条款原文可直接逐项满足、无需引入外部内容→仅重组原文口径: `source_mode="self"`、`needs_human_verify=true`。
4. **四类硬围栏(绝不编造)**: 报价数字/资质证号留 `<SLOT:待填>` 占位(槽位注入落地后由 build_output 注入冻结值); 公司实体名只用白名单内名称; 招标原文引用必须照抄。
5. **已废除**: `ask_clarification` 停下要样例、`web_search` 深写——不阻塞、不联网(空项丢分, 完备性优先); 旧枚举 `kf|uploads|web` 保留兼容(uploads 仅当用户主动上传样例), 新响应只产 `sample|fabricated|self`。

落位(placement): 优先挂接招标格式目录的技术章节锚点(如"技术/产品解决方案", 名称可能不同→`placement.anchor_node_id`); 格式目录无技术章节锚点→自拟合适位置(`placement.self_created_path`, 可带 `after_node_id` 插序)——自拟挂接位由 responses.py merge 在 structure.json 建 `origin=self_created` 的 group 节点并挂接条款, 确认门2 人核落位(铁律3 唯一例外)。二选一形态: anchor_node_id 与 self_created_path **恰好提供一个**(after_node_id 仅与 self_created_path 同用, 或整体省略)。

候选即刻落盘(一个生成批次一个文件, 如 `candidates/RESP-tech-001.json`, 形态 `{"kind": "responses", "items": [...], "note": "..."}`)→确定性校验→合并(与阶段2 同款纪律):

1. validate(命令照抄速查表; 只校验不落盘, 异常项逐项呈现处置):
   - 常见异常与含义: `clause_not_live`(条款已被补遗替代/作废——应对新条款生成响应)、`clause_category_out_of_scope`(商务/资格/格式条款不走本通道)、`citations_missing_for_web`/`citations_url_missing_for_web`(web 供源必须逐条留引用+URL)、`citations_missing_for_sample`/`citations_source_doc_missing_for_sample`(sample 供源必须逐条留源文档引用)、`fabricated_requires_human_verify`(编造漏标人核——P4 强制)、`pipeline_metadata_in_text`(响应正文携带"槽位类型/待填提示"等管线 bullet——重写后再合并)、`placement_shape`/`placement_node_missing`(落位形态/锚点不在 structure.json)、`duplicate_clause_response`(同 clause_id 多条候选——保留唯一最新版)、`thin_response`/`boilerplate_heavy`(实质正文过薄且无供源留痕/高频套话占比超标——疑似空响应或套话填充, 重写后再合并; **fabricated 长正文不受影响**)。
2. merge(命令照抄速查表): 幂等 upsert responses.json+placement 联动 structure 落位+clauses response_status 只升不降(unassigned→draft)+写盘后自动重签。

本阶段完成后跑一次 snapshot.py 更新快照, 再进阶段4 build。

## 两波编排与停车点(T7——300-1000 页标书的多轮预算纪律)

大标书响应生成跨多个 run, 编排由 **progress.py 状态机驱动**(每轮先读 `next`, 恰好一个下一步), 波次协议:

```
wave1  各章响应生成(progress next 循环: PENDING 逐章生成→候选落盘→validate+merge;
       DRAFTED 批量跑门→VERIFIED)——按章组批, 每批 ≤3 个 task() 并发(超发被运行时静默截断)
波间   要点包门(progress 相位 KEY_POINTS): 蒸馏 workspace/key_points.json 三节——
       ①报价汇总(各册 SLOT 报价值对照) ②关键承诺(工期/质保/响应时限等废标级承诺)
       ③偏离结论——ask_clarification 单表单用户确认 → confirm-key-points
wave2  build(两文档册集) + 交付; 投标函/结论章口径以要点包为唯一事实来源
```

**停车点表**(每 run 的合法终点——到点即收尾停车, 记账靠 progress.json; bug-3040/3044/3048: run 级预算烧穿即静默截断且侧报 success):

| 停车点 | 触发 | 收尾动作 |
|---|---|---|
| 门1 后 | 条款清单确认完成 | snapshot → 停 |
| 每章批次投递后 | 一个章的候选落盘+merge | progress next → 停 |
| 批量跑门后 | gate 有 PASS/FAIL 结果 | progress next → 停 |
| 波间要点包确认后 | confirm-key-points | snapshot → 停 |
| build 后 | 两文档册集+凭据落盘 | present_files → snapshot → 停 |

bash 调用目标 ≤25 次/run(批量 gate/合并脚本序列勿拆散单发); 到停车点必须收尾, "再跑一章"是偏轨念头(下一 run 从 progress next 无损恢复)。


## 阶段4 build(两文档册集渲染)

build 前自检: 重跑速查表 check_format.py 命令, anomalies 非空先回阶段2 修提取(标题/模板照抄问题不带入交付物)。

build_output.py(命令照抄速查表)产出**两文档册集**(原子写盘, 重跑字节级幂等; **正文只含交付内容, 管线元数据全部迁走**; 同时落 `delivery_manifest.json` 交付凭据与 `.delivery-contract` 契约标记——本线程此后非管线 .md 交付会被交付门整单拒):

1. `整体方案-NN-首章.md`: structure 镜像**连续切册**(软上限 50 页/册, 单章超限整章成册)——商务章节实际内容: 标题链=招标格式目录逐字; **模板原文预填**(固定文字纯正文段落照抄, 摘要计 `template_prefill_count`); 表格槽=列头+**fixed_rows 逐字复刻**+剩余(待填)行; image 槽干净占位; **技术章=占位页**(逐字标题+技术卷分册目录+指引, 零技术正文内联)。
2. `技术卷-NN-首章.md`: 技术章独立成卷按章分册: 逐条款条目, **条目标题内嵌 clause_id**——它是阶段5 重灌唯一可存活的锚点载体, 交付物中保留不删; 条目体正文=阶段4a responses.json 的 response_text(无响应条目回退待填占位); 未挂接格式槽的活条款入末册「其他技术要求响应」节, 零遗漏。
3. `0-总目录索引.md`: 确定性投影的册清单(整体方案册组/技术卷册组), 分册导航与合并导出顺序以此为准。
4. `偏离表.md`: 仅强制+偏离项, **按招标模板拆两张**(technical 条款入技术偏离表, 其余入商务偏离表)。
5. `覆盖率报表.md`: 清单总数/已响应/待确认/未分配+**槽位编排表 sidecar**(双卷净化迁出的槽位元数据归属地, 含悬挂外键标注)。
6. `人核清单.md`: format_check 项(签字/盖章/份数/页码)全部人核; 模板原文比对项(照抄非确定性, 终稿前逐字比对招标文件); **生成内容人核**节(阶段4a 编造/仿写/引用逐条批量确认——P4)。
7. `实体lint报告.md`: 实体白名单 diff 引用片段+**交付册全文**, 白名单外残留→标[待核对]并触发实体门(硬门: 未处置前无交付凭据; 连续 2 轮同残留→转人工清单); 报告含**候选白名单**节(确认入册即放行); lint 标注"LLM 辅助", 不称确定性。

交付(本技能止于 md, **不产 .docx**): 用 `present_files` 把**两文档册集+索引+副表**一次性交付(build 已直接写出 `/mnt/user-data/outputs/投标文件/`, 交付后自动同步到文档空间); **Word 导出与排版由用户在文档空间完成**——Agent 不调任何转换脚本、不用 python-docx 后处理(回放实证 2026-08-18 线程 1a80a1d8: 转换链路把管线元数据当正文写进 docx)。渲染边界如实向用户声明: 管道表格无法表达合并单元格/列宽→此类表格槽标[待人工复刻]并入人核清单; 图片占位以扫描件清单交付(image 槽汇总), 终稿由用户在文档空间排版时插入; format_check 项全部人核, 不进确定性判定。技术响应正文供源已前移到阶段4a(供源级联), build 只渲染 responses.json 权威态。**实体门硬门生效时 present 会被拒(无凭据)——按 lint 报告处置后重跑 build 再交付**。

build 完成: workspace 写构建回执 `last_build.json`(阶段判定强证据, 含 `whitelist_sha256` 消费留痕与 `entity_gate` 熔断状态)→跑一次 snapshot.py→进确认门2(见 stage3-merge-gate2)。

## 本组状态文件

| 文件 | 产生 | 含义 |
|---|---|---|
| `state/responses.json` | 阶段4a merge | 技术响应正文权威态(upsert 幂等+落位联动+状态升级) |
| `last_build.json`(workspace 根) | 阶段4 build | 构建回执(out_dir/files/whitelist_sha256/entity_gate); snapshot 以它判定"门2 后"状态 |
| `delivery_manifest.json`(outputs) | 阶段4 build | 交付凭据(skill/version/deliverables/aux_md); 实体门硬门期间不写=交付被禁 |

**完成判据**: 两文档册集+索引+副表写全+交付凭据在场+present_files 交付+last_build.json 落盘+snapshot 更新→确认门2 过门。

## 排错表(本组症状→处置, 不试错绕行)

| 症状 | 处置 |
|---|---|
| present 被拒"交付门 FAIL...无 delivery_manifest.json" | 实体门硬门生效——按 实体lint报告.md 处置(候选白名单确认入册, 或回 stage4a 重写含残留实体的响应)后**重跑 build** 再 present; 严禁手拼 .md 绕门 |
| `citations_missing_for_web` / `citations_url_missing_for_web` | 补齐 `{title,url,quote}` 引用; 该支路已废除——新响应改走 sample/fabricated |
| `citations_missing_for_sample` / `citations_source_doc_missing_for_sample` | sample 引用必须带 source_doc(样例文档标识+段落定位); 无样例可引就该条改走 fabricated |
| `fabricated_requires_human_verify` | 编造条目补 `needs_human_verify: true`(P4 全量人核)重跑 validate |
| `thin_response` / `boilerplate_heavy` | 响应正文过薄/套话填充——按 tech_response_prompt.md 重写(实质内容, 供源留痕), 重跑 validate |
| `pipeline_metadata_in_text` | 响应正文混入管线 bullet("槽位类型/待填提示/填写状态/关联条款/满足状态")——剥掉元数据重写正文 |
| `placement_shape` / `placement_node_missing` | anchor_node_id 与 self_created_path 恰好提供一个; 引用的 node_id 必须在 structure.json——修正候选后重跑 |
| `clause_not_live` / `clause_category_out_of_scope` | 对补遗新条款生成响应/该条款走模板镜像管线——从候选里剔除该条目 |
| check_format anomalies 非空 | 回阶段2 修提取(标题不逐字/模板原文缺失/固定行未复刻/骨架漏节点), 修完重跑 check_format 再 build |
| 用户要求直接给 docx | 如实告知: 本技能止于 md, Word 导出在文档空间完成(实证 1a80a1d8: Agent 转换把管线元数据写进 docx) |
