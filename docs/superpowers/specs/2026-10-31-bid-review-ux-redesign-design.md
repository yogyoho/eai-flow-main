# 投标审查模块 UX 全面重构设计(方案丙)

- 日期:2026-10-31
- 状态:APPROVED(设计呈现 2026-10-31,用户逐节确认)
- 范围裁决:方案丙(全量对齐原型)+ 裁决 1(全量复核队列)+ 裁决 2(复核落库)
- 前置文档:`docs/designs/2026-10-30-bid-review-ui.html`(原型)、`docs/superpowers/specs/2026-10-30-bid-review-phase2-adjudication-design.md`(二期)
- 基线:main-dev-fork @ ab6e28fde

## 1. 背景与诊断

用户反馈:投标审查模块功能设计和操作不清晰,难以用明白。经原型(10 屏)与现状(6 页)元素级逐页核查(两轮审计,行号级证据),确认四个结构性根因:

| # | 根因 | 核心证据 |
|---|------|---------|
| A | 无流程引导 | 原型侧栏=流程图(6 步闭环+计数徽标+warn 警示+「步骤 2/3」卡点叙事);现状侧栏纯路由目录。徽标 CSS(`.nav-cnt`/`.nav-cnt.warn`)已移植但零渲染;徽标数据三项(进行中/待基准确认/待复核)全部可从现有 `GET /tasks` 端点算出,零后端增量 |
| B | 缺屏 | s2 新建=TasksView 单步弹窗(原型=独立向导页);s3 解析与抽取无专屏,信息散落 4 处;页级置信契约不存在 |
| C | 命名相近易混 | 「审查工作台」一页承担原型三屏职责(WorkbenchView.tsx 1567 行 = s3 步骤条+s5 审查结果+s6 复核交互);「审查工作台」vs「复核工作台」一字之差 |
| D | 跨页上下文断层 | 页间互跳全靠 `?task_id=` 手工传递;侧栏不感知当前任务;无 task_id 时死空态 |

现状优于原型、设计确认保留的元素:资料完备性卡、基准只读门+后端 409 卡点、DocLocateModal(pdf 真页码/docx quote 窗口)、字段置信 pill、权限过滤导航(canPage)、空/错/载三态、六步 stepper 词汇、创建即跳工作台。

## 2. 范围

**纳入**:IA 重构(侧栏流程化+徽标+任务上下文)、WorkbenchView 拆分、/new 向导页、/parsing 专屏、任务总览 9 列改造、baseline 增强、复核页全量队列重构、治理页增强、后端增量 B1-B7。

**维持挂账(不纳入)**:
- s7 响应偏离表 / s8 版本差异**整屏**(B7 diff 端点只做数据地基,UI 走轻量「版本对比卡片」)
- 规则逐条启停写端点(维持「启停走规则包版本发布」语义)
- 评测 runner(重跑评测/导出评测报告按钮继续缺省)
- failed 任务重试端点(P2 可选,里程碑尾部视余量)
- PDF 报告导出(报告预览 modal 渲染现有 md,下载维持 .md)

## 3. 信息架构

### 3.1 侧栏(6+2,流程图化)

| 导航项 | 路由 | 徽标 | 权限点 |
|---|---|---|---|
| 任务总览 | `/bid-review` | 进行中 N(status ∈ parsing/extracting/running) | 既有 |
| 新建审查任务 | `/bid-review/new` | — | 新 page id |
| 解析与字段抽取 | `/bid-review/parsing` | — | 新 page id |
| 招标基准确认 | `/bid-review/baseline` | warn 待确认 N(awaiting_confirm 计数) | 既有 |
| 审查结果 | `/bid-review/results` | — | 新 page id |
| 人工复核工作台 | `/bid-review/review` | 待复核 N(Σ TaskOut.need_human_count) | 既有 |
| 规则库 | `/bid-review/rules` | — | 既有 |
| 规则效果 | `/bid-review/metrics` | — | 既有 |

- 分组名:「审查闭环」(6 项,顺序即流程序)、「规则治理」(2 项)。原型 g-tag「N 屏」徽标不迁(对用户无信息量)。
- 徽标数据源:layout 层挂共享任务查询(见 3.3),客户端计算;点击徽标直达对应页并带「最近一条命中任务」的 task_id。
- 命名:六页名与原型全量对齐;「审查工作台」名称退役;「任务总览」保留(2026-10-30 定案)。

### 3.2 任务上下文(2026-10-31 s1 复核裁决:选中任务模型,替代原「任务选择器」方案)

- **单一事实源 = URL `?task_id`**,零新状态层:`effectiveTaskId = URL param → 最新任务(useBidTasks[0])→ null`。共享 hook `useSelectedTask()` 封装 fallback 链,审查闭环六页统一消费——无 param 进入任何任务链页都直接显示最新任务数据(替代原「任务选择器」屏与「未指定任务」死空态)。
- 列表行点击 = **选中**(`router.replace` 写 `?task_id=`,选中行高亮);页面跳转改走操作列状态分派(见 4.1)。
- 侧栏顶部「当前任务」chip(业务任务号+项目名+状态 pill,B1 后升级)显示 **effective** 选中(含最新任务 fallback);审查闭环四任务链页的 nav link 自动携带当前 effective task_id(`taskHref(page, taskId)` 收口,Plan 1 已落地),六页互跳不断档。
- 路由迁移:`/bid-review/workbench` → 重定向 shim 到 `/bid-review/results`(保深链,同 `tasks/[id]` shim 模式);`tasks/[id]` shim 保留。

### 3.3 数据地基(纯前端)

- hooks.ts 导出共享 `useBidTasks`(现状 TasksView 自建 useQuery 不共享);layout 徽标、任务 chip、任务选择器复用同一 `bidReviewKeys.tasks` 查询缓存。
- 徽标近实时:复用既有 mutation invalidate;不引入轮询(YAGNI,创建/复核动作后已有 invalidate 链)。

### 3.4 权限

- 新页面点(新建/解析与抽取/审查结果)注册进权限 yaml,沿用 `page:`/`nav:` 授权粒度与 canPage 过滤;micro-B 权限回归门同步扩展,锁定新点。
- 旧路径授权兼容:`workbench` 权限点映射到 `results`(yaml 里做别名或迁移授予,以现有 grants 数据迁移成本最小为准,实施计划定)。

## 4. 页面设计(逐页)

### 4.1 任务总览 `/bid-review`(s1)

- **metric-strip 换血为「当前任务体征」**(2026-10-31 用户定案:任务彼此独立,跨任务汇总无行动价值;统计卡骨架保留、内容更换):致命未处理(err)/待人工复核(warn)/问题总数/误报已剔除/审查用时(done_at−created_at,B1 前显 —)。数据源:TaskOut 聚合字段 + `useBidIssues(选中任务)`;半程态(created/parsing/extracting/running)问题集是快照,四格显 —(伪零纪律,「未进入审查 ≠ 通过」)。跨任务计数由侧栏徽标承担(Plan 1 已落地),页头不重复。
- **列表 9 列**(依赖 B1):任务号(业务号 TBR-*)/项目·标段/模式/状态/可提交判定/致命·主要/创建人/更新时间/操作。
  - 可提交判定:客户端按 TaskOut 计算——done 且 fatal_unhandled>0 →「不建议提交」(err);done 且 =0 →「建议提交」(ok);其余「—」(表尾保留「未进入审查 ≠ 通过」文案)。
  - 操作列按状态分派:awaiting_confirm →「去基准确认」;done →「查看结果」;running/extracting/parsing →「查看进度」;failed →「重试解析」(B8 落地前不渲染)。
  - 搜索框支持业务号+项目名(B1 后);seg 五档保留(「待基准确认」措辞)。
- 「导出列表」继续不做(v1 无后端,挂账)。
- 保留:骨架屏、errbar+重试、空态、刷新按钮。行点击语义改为**选中**(D3-A,2026-10-31;原「行点击跳转 /results」退役),跳转全部走操作列。

### 4.2 新建审查任务 `/bid-review/new`(s2,新页)

- 独立页替代 TasksView 内弹窗(弹窗退役,页头按钮/空态按钮改 Link)。单页三卡(非分步 stepper,对齐原型):
  1. **基本信息**:项目/标段名称*(必填,B1 字段)、招标编号(B1 字段);评审模式 mode-card 单选(quick/deep,维持 v1 真实口径文案)+modeHint 随档切换(既有)。
  2. **招标文件** / **投标文件** 两组上传(后端契约必传,保留):drop 文案、文件表(文件名/大小/移除)、双组非空 disabled 门。新增单文件 ≤200MB 前端校验。
  3. 创建动作:pending「创建中…」、失败 errbar、成功 `invalidateQueries(tasks)` + 跳 `/results?task_id=`。
- 页头流程副题:「上传投标文件 → 选择评审模式 → 引擎解析并出具带证据的问题清单」(v1 口径改写)。
- 格式承诺维持现状诚实注记(txt/md 文本解码;PDF/Word 后续),**不抄**原型 OCR/PDF 承诺;OCR<0.70 note-bar 不做(无页级置信前的虚假承诺,B3 落地后再评估)。

### 4.3 解析与字段抽取 `/bid-review/parsing`(s3,新页)

归拢现状散落 4 处的解析信息,只读展示(裁定动作不迁,留在基准确认页):

- **六步 stepper**(自 WorkbenchView 区段一迁入)+「引擎:{msg} · N%」进度行 + failed errbar。
- **解析质量表**(自 BaselineView gate1 卡迁入):文件/角色/类型/页数/字符/图片扫描页/状态;B3 落地后增「识别置信度」列(meter+数值)与低置信页明细行(页区间+置信+「已列入待人工核对」注),无 B3 数据时维持文档级 OCR 注记(诚实降级)。
- **基准字段对照**(自 BaselineView 字段族区迁入只读部分):汇总行(已抽取/缺失/冲突计数+快照哈希)+字段族列表+字段卡(值/中文名/置信 pill/缺失废标风险文案/「查看原文」)。冲突字段卡此处只展示「冲突待裁定 → 去基准确认」链接,不嵌裁定 radio。
- 页头:业务号+项目名+模式(四元组,B1)+「待基准确认」pill(状态驱动)。
- 保留:资料完备性卡**迁移到 /results 左列**(它语义上属于「审查结果怎么读」,不属解析进度)。

### 4.4 招标基准确认 `/bid-review/baseline`(s4)

- 页头:**「待确认 N 项」计数 pill**(warn,= 未裁冲突数+待确认行数聚合)替换现「刷新」旁边空白;卡点主句保留;「确认门仅工作台 UI,agent 不可代确认」机制注保留。
- **五主题族分组**:前端 `FIELD_THEME` 映射(路径前缀→报价基准/清单基准/项目与主体/工期与质保/其他条款,无匹配落「其他条款」);族搜索、未决 mini-dot、族字段计数保留。零后端。
- **裁定卡增强**:radio 候选+出处保留;新增**核对勾 gate**「我已核对两处原文」——勾选后「采纳为基准值」才可点(前端仪式感,不新增后端逐字段确认状态);已裁定卡保留时间戳注。
- **已抽取字段折叠**:非冲突非缺失字段默认折叠,折叠注「其余 N 个字段已由引擎交叉校验通过,点击字段族展开」(对齐原型折叠注)。
- **gate-bar 进度升级**:meter 从二值 0/100 改渐进——pct = 1 −(待确认行+未裁冲突)/总需处理数;按钮 disabled 条件不变;文案保留。
- **proto-banner(P0-3 原型注记)清除**。
- 保留:只读门 warnbar+409 toast 分流、DocLocateModal、「无出处记录」注、常驻入口(可回看重裁定)、「冲突需人工裁定后生效」语义。

### 4.5 审查结果 `/bid-review/results`(s5,拆分)

自 WorkbenchView 拆出(s3 部分去 /parsing,s6 复核交互留在本页行内):

- **页头**:业务号·项目名·模式·规则包·用时五元组(B1;用时=完成时间−创建时间,客户端算);常驻按钮:「发起复核」(→/review?task_id=)、「导出报告」(开预览 modal)、「刷新」。
- **verdict-band**:文案定稿——「判定口径:存在致命且未被人工判误报的问题(致命 > 0 一律不建议提交)」;红/绿语义与现状一致。
- **左列**:风险分布四格+「未判定 ≠ 通过」warnbar(挂「到复核工作台」链接)+资料完备性卡(自 WorkbenchView 迁入)+规则执行卡+复核进度卡。
  - 规则执行卡:det/sem 分组计数保留;meter 升级——B4 数据在 →「评分覆盖度 72%(评分办法 N 项已覆盖 M)」;不在 → 回落「规则命中」meter(现状口径,表尾注保留)。
  - 复核进度卡:改读服务端 review_state(B2)——「已复核 X/Y · 维持 A · 误报 B · 待人工 C」刷新不丢;表尾「误报项不进报告正文,自动回流评测集」保留。
- **右列问题清单**:iss 四行结构、seg 五段、批量 bar(文案改「批量维持违规」)、need_human 组置底分隔线(逐字保留)、分页保留(弃折叠)+表尾补「完整清单见导出报告」;「已复核 · 维持待人工」态随 B2 review_state 出现;差异值结构化高亮不做(引擎 message 无结构化差值字段,挂账)。
- **报告预览 modal**(新):免责注记「本报告为辅助提示,最终责任由投标主体承担」+ 判定带摘要 + 现有导出端点 md 内容渲染 +「下载 .md」。纯前端(md 渲染)。
- **版本对比卡片**(轻量,B7):页头「对比上一版本」按钮(有 prev_task_id 时显示)→ 行内卡片:问题级三态计数(新增 N/消失 N/未变 N)+ 新增问题列表;不做 s8 整屏。
- 保留:基准未确认只读门、审查失败 errbar、「改严重度」modal、置信度展示、加载骨架、批量误报四因(补每因解释副文案,对齐原型)。

### 4.6 人工复核工作台 `/bid-review/review`(s6,重构)

裁决 1 落地:

- **队列口径**:全量未复核(所有无 resolved verdict 的问题,review_state 判定,B2);seg 筛选「全部/致命/主要/次要/待人工」,默认落「待人工」段。
- **队列 UI**:右列恢复完整队列列表(rule id+严重度 pill+标题,当前项高亮),当前判定卡置下;左列原文对照(DocLocateBody)不变。
- **判定 radio 四选**:确认问题(维持违规)/误报(原因必选,四因+解释副文案)/**转待人工**(新,defer_need_human,落库)/调整严重度(select 联动启用);严重度 select+备注保留。
- **页头**:stage-chip「复核中 k/N」+ 任务级进度注「已复核 X/Y(维持 A/误报 B)」(B2);页脚「本任务复核进度 X/Y · 维持 A · 误报 B · 待复核 N」。
- 保留:快捷键 J/K/Y/N(语义不变)、提交即时推进(handled 集合 + 服务端 state 双源)、返回工作台、无证据项指引、空态、fpReason 必选校验。
- 工作台(/results)行内复核按钮保留,两动线并存(队列=专注过单,行内=顺手处置),同一 review_state 数据源,无双写分歧。

### 4.7 规则库 `/bid-review/rules`(s9)

- seg 改「全部/L1 实质性/L3 一致性/高误报(warn)」(层级字段已有;类型 seg 退役)。
- **规则定义抽屉**(新,B5):expr 五块(PRECONDITION/EXPR/ON_MISSING_INPUT/MESSAGE_TPL/FIX_TPL)code 展示+「修订须走规则包版本发布」foot。
- 表列增「判定」算子列(B5 回流);误报率列维持「命中/误报/采纳+高误报 pill」现状(独立 % 列可选,实施时定)。
- 保留:包头卡+只读 Switch+「无写端点」注、伪零纪律、口径 foot。

### 4.8 规则效果 `/bid-review/metrics`(s10)

- **FAIL 归因**(B6):高误报 FAIL 名单卡增归因 foot(该规则误报原因 top 聚合);「重跑评测」按钮继续不做。
- **周趋势**(B6):近 6 周误报率 6 柱(基于复核反馈时间戳聚合);「回流闭环生效」note-bar 随图。
- s9↔s10 互跳:规则库高误报段→看板 FAIL 名单锚点;看板 FAIL 行→规则库该规则。
- 保留:诚实口径注(评测端点未接入)、空态、跨包 key 前缀。

## 5. 后端增量 B1-B7

| # | 内容 | 契约要点 | 量级 |
|---|------|---------|------|
| B1 | TaskOut 扩展 | `project_name`、`tender_no`、`biz_no`(TBR-{YYYYMMDD}-{seq},创建时生成,唯一)、`created_by_name`、`updated_at`/`done_at`、`main_unhandled`(未处理「主要」severity 计数,2026-10-31 D1-A 并入,list_tasks 同循环聚合);tasks 表加列+迁移(biz_no 存量回填) | 小 |
| B2 | 复核落库 | feedback 端点动作枚举扩 `confirm`/`severity_change`/`defer_need_human`(误报已有);issues 投影加 `review_state`(unresolved/maintained/false_positive/severity_changed/deferred);全量未复核队列查询支持(按 segment 过滤) | 中 |
| B3 | 解析置信 | 解析层回传 per-doc confidence + `low_conf_pages:[{page_from,page_to,confidence,note}]`,engine_meta.docs 投影透出。**先探明 parse 层是否已产出置信再定实现**(若 parse 无置信,引擎侧补计算,量级升) | 中 |
| B4 | 评分覆盖度 | 引擎抽取评分办法项(baseline 字段族扩展或独立投影);`GET /tasks/{id}/score_coverage` → `{total, covered, items:[{name, covered_by_rules:[rule_id]}]}` | 中 |
| B5 | 规则 expr 回流 | rulepacks 明细端点:`GET /rulepacks/{id}/rules` → 每规则 id/名称/层级/算子/expr 五块(来自规则包 YAML 原文) | 小 |
| B6 | 看板聚合 | `GET /metrics/fail_attribution`(fp_reason 按规则聚合)、`GET /metrics/trends`(近 6 周误报率,基于 feedback 时间戳;依赖 B2) | 小 |
| B7 | 版本 diff | `GET /tasks/{id}/diff?prev=<task_id>` → 问题级三态:`{added:[], removed:[], unchanged_count}`(匹配键:rule_id+锚定字段路径) | 小 |

约定:B1/B2 先行(M2-M4 的依赖);B3 需先做 parse 层现状探查(半小时级 spike);每端点带 pytest;扩展模块全部在 `app/extensions/bid_review/` 边界内,不动 harness 核心(无 EAI-CUSTOM 三重规范负担,模块本身即 EAI 扩展,维持现有文件头注惯例)。

## 6. 已裁定取舍(决策记录)

1. **verdict 文案**:取现状口径(「未被人工判误报」),不用原型 `verdict=violation` 表述——与数据实际贴切;四/5 处文案统一为定稿句。
2. **字段级确认**:只做前端核对勾仪式感(裁定卡 gate);不新增逐字段确认后端状态——卡点强度由包级确认+后端 409 保证。
3. **五主题族**:前端映射,零后端;新字段类型出现时映射表随 labels 维护。
4. **次要问题**:保留分页(弃原型折叠);导出报告兜底文案补齐。
5. **新建格式承诺**:维持诚实注记;200MB 校验新增;OCR 承诺等 B3。
6. **队列口径**:全量未复核+seg(裁决 1);转待人工与严重度调整并存(四 radio)。
7. **复核落库**:confirm/severity_change/defer 三动作落库(裁决 2);本地 handled 集合保留为乐观 UI,服务端 state 为真源。
8. **命名**:「审查工作台」退役;六页名对齐原型;「任务总览」保留。
9. **规则启停/评测 runner/s7/s8 整屏/重试端点/PDF 导出**:维持挂账(见 §2)。
10. **s1 统计卡**(2026-10-31 用户两段定案):跨任务汇总无行动价值(任务彼此独立)但**不删卡**,内容换为当前选中任务体征五格(致命/待人工/问题总数/误报/用时);跨任务计数只留在侧栏徽标。
11. **D1 致命/主要列**:B1 并入 `main_unhandled` 聚合,严格对齐原型(弃「致命/待人工」零后端替代)。
12. **D2 统计卡第五格**:审查用时(B1 done_at 前显 —;弃零后端「基准确认状态」,与状态 pill 重复)。
13. **D3 行点击语义**:点击仅选中(写 `?task_id=`+高亮),跳转走操作列(选中模型见 §3.2)。

## 7. 里程碑与依赖

| 里程碑 | 内容 | 依赖 |
|---|------|------|
| M1 IA 地基 | 共享 useBidTasks、侧栏流程化(徽标+任务 chip)、选中任务模型(useSelectedTask,§3.2)、路由骨架(/new /parsing /results + /workbench shim)、权限 yaml 新点+回归门扩展 | 无 |
| M2 任务链页 | /new 向导页、/parsing 归拢专屏、任务总览 9 列+行动作、baseline 增强(主题族/核对勾/折叠/渐进 meter/计数 pill/proto-banner 清除) | M1;业务号列等 B1 |
| M3 结果页 | /results 拆分迁移、verdict 定稿、报告预览 modal、发起复核常驻、版本对比卡片 | M1;对比卡片 B7 |
| M4 复核页 | 全量队列+seg+四 radio+stage-chip+进度 footer | M1;B2 |
| M5 治理页 | rules seg/抽屉/算子列(B5)、metrics 归因/趋势/互跳(B6) | B5/B6 |
| M6 后端批次 | B1+B2 先行(与 M2-M4 并行启动);B3 spike→实现;B4;B5/B6/B7 | 每项 pytest |

排序建议:M1 → M6(B1,B2)→ M2/M3/M4(前端,互相独立可并行)→ M6(B5/B6/B7,均小)→ M5 → M6 余项(B3 spike→实现、B4;两者有独立回落,不阻塞前端里程碑,但 B7 须先于 M3 的对比卡片、B5/B6 须先于 M5)。CC 工作量估算:前端 3-4 天,后端 2-3 天。

## 8. 测试与验收

- **前端**:dom 测试(rstest,tests/unit 镜像 src)随每里程碑扩展;既有 bid-review dom 测试随路由迁移改路径;新增:徽标计算、任务 chip/选中模型 fallback 链、/new 校验门(200MB/双组必填)、/parsing 归拢渲染、/results 拆分后关键区块存在性、/review 四 radio+seg 过滤、rules 抽屉、metrics 归因渲染。
- **后端**:B1-B7 每端点 pytest(含权限与 owner 过滤用例);B2 落库后 need_human 计数与 review_state 联动用例(确认→清旗、转待人工→置旗、误报→回落)。
- **走查**:每里程碑真浏览器走查(登录态热、路由编译预算预留);最终全流程走查:新建→解析→基准确认→审查→复核→导出。
- **回归门**:micro-B 权限测试扩展锁新页面点;harness 边界测试不触(纯扩展模块)。

## 9. 风险

| 风险 | 缓解 |
|---|------|
| B3 parse 层无置信产出 → 引擎补算量级升级 | M6 先 spike;无置信时 /parsing 诚实降级为文档级注记(设计已内置回落) |
| /results 拆分回归风险(1567 行迁移) | M3 拆分为纯迁移+小改,dom 测试先锁现有区块再动;分两个提交(迁移/增强) |
| 全量队列量大(28+ 项)seg 性能 | 客户端过滤,分页/虚拟化视实测;need_human 默认段控制首屏 |
| 旧深链/授权迁移(workbench→results) | shim 重定向+权限别名,走查覆盖 |
| B2 改 feedback 语义影响既有评测回流 | 误报通道行为不变(只增不改);review_state 为派生投影,不重写历史数据 |
