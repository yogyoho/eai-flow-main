# 两模式编排细节(自审 / 子系统)

模式路由与铁律见 SKILL.md;本文给流程、字段提取对照、判据与排错。命令一律照抄 SKILL.md 速查表(唯一合法形态),本文不新增任何命令。

---

## 模式一:管线自审(零后端,source=local-det)

进入条件:无 bid_review MCP 工具(离线/子系统未部署),或用户明确只要本地快查。审查对象:bid-proposal-overall workspace 产物(`clauses.json`/`structure.json`/册集 md;优先复用,含确认门1 锁定的实体白名单),或用户直接提供的招标+投标文档(uploads 转出的 .md)。

### Step 1 求值器自检

先跑速查表 `selftest`:输出 `SELFTEST OK` 才继续。失败=技能分发损坏(规则副本与求值器不配套),停下报告;**禁止改 references/ 数据凑绿**(数据是三方契约)。

### Step 2 字段提取(逐锚点读文档 → 填 fields.json)

- 字段路径=`references/rules-det-subset.yaml` 各规则 `inputs` 的 dotted 路径,是规则↔求值器↔呈现三方契约,**不得私自改名**。
- 提取纪律:读 uploads 转出的 .md 行区间定位锚点;数值/大写金额**照抄原文,不心算不换算**(铁律 5);**缺失字段不猜不造**——fields.json 里直接不写该键,求值器按 `on_missing_input: need_human` 出"待人工",这是设计行为不是错误(见排错表)。
- 锚点键与规则 `evidence` 列表一致;提取对照表(字段 → 锚点 → 读哪里 → 形态):

| 字段(dotted 路径) | 锚点 | 读哪里 | 形态 |
|---|---|---|---|
| bid.total_price | A-PRICE-SHEET | 报价汇总表/开标一览表投标总价 | number(元) |
| tender.max_price | A-TENDER-NOTICE | 招标公告/投标人须知最高限价 | number(元) |
| bid.price_includes_tax | A-PRICE-SHEET | 投标报价含税口径说明 | bool |
| tender.price_includes_tax | A-TENDER-NOTICE | 招标文件对报价含税的要求 | bool |
| bid.detail_rows | A-PRICE-DETAIL | 报价明细表逐行 | `[{code, amount}]` |
| bid.subtotal | A-PRICE-SHEET | 明细合计/合价 | number(元) |
| bid.total_price_words | A-PRICE-SHEET | 大写金额 | str(照抄;求值器按整数元+"元整"口径比对,角分场景误报交人工裁决) |
| tender.boq_items | A-TENDER-BOQ | 招标工程量/供货清单逐项 | `[{code}]` |
| bid.boq_items | A-BOQ | 投标清单逐项 | `[{code}]` |
| tender.project_identity.name | A-TENDER-NOTICE | 招标项目名称 | str |
| tender.project_identity.code | A-TENDER-NOTICE | 招标项目编号(编号比对 deferred:bid 侧编号字段字典 v2 定义,当前仅提取输入) | str |
| bid.header_footer.project_name | A-HEADER | 投标文件页眉/封面项目名 | str |
| bid.entity.license_name | A-LICENSE | 营业执照主体全称 | str |
| bid.entity.name_in_bid_letter | A-BID-LETTER | 投标函投标人全称 | str |
| project.entity_whitelist.names | (state) | bid-proposal-overall 确认门1 锁定的实体白名单;无管线 state 时请用户提供,不自行推断 | `[str]` |
| bid.duration_main_text | A-MAIN-TEXT | 正文工期条款 | `{value, unit}` unit∈day/month/week(月按 30 日历天折算;工作日口径 v2) |
| bid.duration_schedule | A-SCHEDULE | 进度表/供货计划工期 | `{value, unit}` |
| bid.duration_commitment_letter | A-COMMIT | 投标承诺函工期 | `{value, unit}` |
| bid.amount_occurrences | A-COMMIT + 正文 | 全文金额出现处(承诺函/正文引用总价处) | `[{where, value}]` |

fields.json 落 `/mnt/user-data/workspace/bid/fields.json`(速查表路径)。结构化字段形态必须与上表一致——形态错了求值器出 need_human 或误报,不是它的缺陷。

### Step 3 跑求值器

跑速查表 `run` 命令;**stdout 单行 JSON 摘要(`{"issues": N, "need_human": M}`)是本阶段事实唯一口径**。

- 退出码 `0`=干净;`3`=有异常(violation 或 need_human)——**退出码 3 不是失败**,必须读摘要并逐条呈现,绝不静默吞掉。
- `--md` 概览落 outputs,但它是**中间产物不是最终交付**——最终交付须经 Step 4 证据补齐后重新成文。

### Step 4 证据补齐(编排层的交付责任)

求值器产出的问题 `evidence` 一律为空数组(`evidence: []`):副本求值器只做数值判定,不做原文定位,这是刻意的边界。**按铁律 1,每条问题必须由编排层(agent)补齐 文档+页码+原文摘录(照抄原文片段,≤50 字) 后才可向用户呈现**;定位不到证据的问题降级标 `[待确认]` 并注明缺什么。这是编排步骤的交付责任,不是求值器的——**禁止以"求值器没给证据"为由输出无证据清单**。need_human 条目同样须补齐"缺哪些字段、去哪个锚点补"的指引。

### Step 5 呈现问题清单

md 结构:`## 问题清单(自审 local-det)` → 按 severity 分节(fatal 在前)→ 每条:规则 ID / 严重度 / 问题描述 / 证据(文档+页码+摘录)/ 修复建议;need_human 与证据未补齐条目标 `[待确认]`。结论标注 `source=local-det`(与子系统结论 `source=engine` 可区分、不混排)。文末固定附免责声明:"辅助提示,最终责任由投标主体承担"。

### 自审排错表

| 症状 | 处置 |
|---|---|
| 字段缺失 → need_human | 正常设计行为(on_missing_input=need_human):呈现 `[待确认]`+缺失字段清单,指明去哪个锚点补提取;严禁编造字段值凑干净 |
| 退出码 3 | 不是失败:读 stdout JSON 摘要,逐条呈现(含 need_human 计数) |
| selftest 失败 | 技能分发损坏(副本与规则不配套):停下报告;禁改 references/ 数据凑绿 |
| ExprError / 未支持算子报错 | 规则副本含 M1 之外构造或字段形态不符对照表:停下报告,不自行扩求值器 |
| message 残留 `{…}` 占位符 | 求值器消息渲染缺陷:停下报告,该条不直接呈现 |
| 证据定位不到原文 | 该条降级 `[待确认]`;禁止"大概在某页"式模糊锚点,禁止留空证据呈现 |
| 连续 ≥5 次脚本失败 | 熔断:停下,呈现失败清单问用户(铁律 4) |

---

## 模式二:子系统审查(bid_review MCP 七工具,source=engine)

进入条件:bid_review MCP 工具可用(extensions_config.json 已注册 `bid-review`,gateway 在线)。七工具:`bid_review_start` / `bid_review_status` / `bid_review_issues` / `bid_review_issue` / `bid_review_feedback` / `bid_review_baseline_get` / `bid_review_rulepacks`——**不存在任何 confirm 类工具**(刻意设计:确认门只在工作台 UI)。

### 编排流程

1. **受理**:请用户先在聊天上传招标+投标文档;确定 mode(quick=只 L1 det 否决项概览;deep=L1+L3 全量+工作台复核),用户未表态时问一句,不代选 deep。
2. **发起**:`bid_review_start(mode, tender_doc_note, bid_doc_note)`——note 指向用户已传的文档;返回 task_id + 工作台链接(链接留存,确认门要用)。
3. **轮询**:`bid_review_status(task_id)` 读 status + progress `{stage, pct, msg}`(轮询制无推送,间隔别太密)。状态机:`created → parsing → extracting → awaiting_confirm → (人工确认后) running → done`;任一环节可 `failed`。
4. **确认门(铁律 3)**:`awaiting_confirm` → 提示用户打开工作台链接确认基准包。可用 `bid_review_baseline_get(task_id)` 只读拉基准草稿帮用户核对,但**确认动作本身在 UI 由用户点,agent 绝不代确认、不催促绕过**——基准错误将批量产生错误结论。
5. **取清单**:done 后 `bid_review_issues(task_id, severity?, layer?)` 拉清单。quick=取 fatal/major 概览汇报;deep=完整清单,**用户点哪条讲哪条**:`bid_review_issue(issue_id)` 拉单条全证据(文档+页码+摘录)再展开。
6. **讲解纪律**:引擎产出已带证据,按库内证据原样呈现,**不需要也不得做自审模式的"补齐/改写"**;数值只引用返回值(铁律 5);**不本地复算**(铁律 2)——若用户同时跑过自审模式且两者冲突,以库内(source=engine)为准并如实呈现分歧。
7. **复核回写**:用户口头明确表态某条结论后,agent 才可 `bid_review_feedback(issue_id, action, new_severity?, note?)` 代回写;action ∈ `confirm` / `false_positive` / `severity_change`(severity_change 须带 new_severity 与理由 note)。未经用户表态不得代回写。
8. **汇报**:问题清单+免责声明("辅助提示,最终责任由投标主体承担");复核、报告导出指引到工作台 UI(UI 能力,不在 MCP 工具面内,勿向用户许诺 agent 出报告)。

### 子系统排错表

| 症状 | 处置 |
|---|---|
| MCP 工具不存在/连接失败 | 子系统未部署或未注册:按 SKILL.md 模式路由转自审模式,不硬凑 |
| task failed | 读 status 的 error 如实呈现;重新发起=新 task(再调 bid_review_start),不复活旧 task |
| awaiting_confirm 长时间停留 | 属人工门:提醒用户 UI 确认即止,不代点、不超时代答 |
| issues 拉到空数组 | 先核 status 是否 done;running 中拉空属时序问题,勿当成"无问题"结论汇报 |
| feedback 报参数错 | action 取值核对(confirm/false_positive/severity_change);severity_change 必带 new_severity;记不准查工具 schema,不凭记忆造 |
| 状态长时间不动 / progress 无心跳 | 如实告知用户进度停滞,连查 2 轮无变化即停并汇报,不无限轮询 |
| 连续 ≥5 次工具失败 | 熔断:停下,呈现失败清单问用户(铁律 4) |
