---
name: bid-proposal-writing
description: 当用户需要编写投标方案/标书响应文件(分析招标文件、编写商务/技术标、响应技术参数、偏离表、按评分标准模拟打分)时使用此技能。该技能把招标文件(含答疑/补遗)转化为带原文锚点的机器可核对义务清单,产出商务/技术双卷逐项响应骨架与偏离表,并对成稿按评分办法逐项模拟评分、给出改进建议。
---

# 投标方案编写技能(bid-proposal-writing)

## 概述

把**招标文件**变成**机器可核对的义务清单**(每条要求分类 ★强制/评分/普通、锚定原文位置),产出**商务/技术双卷逐项响应骨架 + 偏离表**供团队分发填写,终稿前按**评分办法模拟打分**并给出失分点与改进建议。用确定性管线消灭三类结构性风险:漏响应(丢分/废标)、汇总对不齐、旧内容没改净。

分工原则(全管线不变):

- **脚本 = 确定性工作**(解析/校验/落账/渲染/重灌/汇总,五个脚本全都不调 LLM);
- **Agent = 编排者 + 上下文内 LLM 循环**(分块提取、相似度候选、主观评分评审——可审计、可中断、每步候选落盘);
- **两道人工确认门**(清单锁定 / 补遗+终稿复核),Agent 不替用户做废标级决定。

## 铁律(违反任何一条立即停下)

1. 条款数据的唯一来源 = `clauses.json`;严禁在 prose 里转写/改分类——改分类必须改文件。
2. 先跑通 ingest/extract 才允许谈清单;校验失败的块标 `[待确认]`,绝不绕过自提取。
3. 禁止"整篇方案生成器"脚本;商务部/技术部骨架由 build_output.py 从 clauses.json + structure.json 渲染;商务部章节结构**只镜像不自创**。
4. 全程写盘仅限:脚本产出的 artifacts + 最终 Word 落盘(每卷单次成文,共两次);禁止多次 append 拼接。
5. 耗时自检(分级阈值,不同阶段不同量级):脚本/Agent 提取循环=分钟级,确认门1 前超 ~5 分钟无 clauses.json 产出→偏轨停下;OCR 全文=百页量级十几分钟属正常(OCR 服务实测节奏),只设每 N 页心跳进度,不设一刀切死线。
6. 多轮承接锚点:每会话结束写 `project_snapshot.json`(当前招标文件/清单版本/待办/评分报告版本),防止跨会话漂移回"重新生成";评分报告 version++ 留痕,不覆盖。
7. **评分纪律(阶段5)**:模拟评分必须逐项引用评分办法原文锚点+成稿证据片段;无证据的响应按空缺计分(不为留印象给分);主观项一律标"模拟参考值",skill 不承诺与真实评审一致;改进建议必须落到具体 rubric_id 与缺失内容,不写空话。

另有一条贯穿红线(废标风险):**无出处的值一律标 `[待确认]`,绝不编造**;每条提取项必须带原文位置锚点;`source_ref.quote` 只能照抄原文片段(≤50字),不得改写、拼接、意译。

## 管线总览:六阶段 + 两道确认门

```
阶段0 输入受理(分流:docx/pdf/扫描件;补遗标记)
  → 阶段1 ingest(纯结构化 → sections.json,发 chunk/table id)
  → 阶段2 extract(Agent 上下文内分块提取循环 → 候选落盘 → extract.py 校验/合并三状态文件)
──── 确认门1:计数+异常项+完整清单工件+clause_id 改分类回写+实体白名单锁定 ────
  → 阶段3 merge(补遗/答疑到达即处理:ingest --addendum → 提取循环 → merge_addenda.py 落账)
  → 阶段4 build(build_output.py 六件套 → markdown-to-docx 出双卷 Word)
──── 确认门2:补遗 diff 表(新增/被替代/作废逐项确认+新实体确认列)+终稿复核清单 ────
  → 阶段5 模拟评分(填写后可反复:双形态对齐 → 主观评审循环 → aggregate → report version++)
```

阶段0-4 是主线(每份基础文件各走一遍);阶段5 在团队填写/回传后可重跑,每次报告 version++ 留痕。

## 路径、状态目录与退出码

- 脚本(沙箱路径,同 markdown-to-docx 先例):`/mnt/skills/public/bid-proposal-writing/scripts/` 下五个 Python 脚本,全部 argparse CLI、纯 Python 3.12、不调 LLM。
- 契约文档:`/mnt/skills/public/bid-proposal-writing/references/` —— 三个 JSON Schema(clauses/structure/rubric)+ `classification.md`(分类判据)+ `extraction_prompt.md`(提取三子模板)+ `scoring_prompt.md`(主观评审纪律)。提取与评审循环开始前必须先读对应文件。
- 状态目录:建议 `/mnt/user-data/workspace/bid/`,其下 `state/`(状态文件)、`candidates/`(候选 JSON checkpoint)、`output/`(渲染产物);最终交付 Word 放 `/mnt/user-data/outputs/`。
- 状态文件(权威态,均由脚本原子写盘:临时文件+os.replace):

| 文件 | 产生 | 含义 |
|---|---|---|
| `state/sections.json` | 阶段1 | 章节块/表 + chunk_id/table_id + 锚点(校验基准) |
| `state/clauses.json` | 阶段2/3 | 义务清单(条款数据唯一来源,铁律1) |
| `state/structure.json` | 阶段2/3 | 商务/技术双卷结构镜像与槽位 |
| `state/rubric.json` | 阶段2/3 | 评分标尺(Σmax_score 必须等于评分办法总分) |
| `state/entities_whitelist.json` | 确认门1 锁定 | 实体白名单(阶段4 lint 基准) |
| `state/merge_ledger.json` | 阶段3 | 补遗内容哈希台账(幂等:重复合并跳过) |
| `state/addendum_entities_pending.json` | 阶段3 | 补遗新实体增量清单(确认门2 消费) |
| `state/reingest_result.json` | 阶段5 reingest | 回传稿锚点重灌事实+异常区 |
| `state/evidence_pack.json` | 阶段5 assemble-evidence | 逐 rubric 项证据包(主观评审输入) |
| `state/aggregate_result.json` | 阶段5 aggregate | 三类分项汇总 |
| `state/评分报告/version_N.md` | 阶段5 report | 评分模拟报告(version++ 不覆盖历史) |

- 退出码(五脚本统一约定):`0`=干净完成;`1`=用法/文件错误;`2`=**仅 ingest**:存在无文本层输入(扫描件)需走 eai-flow-ocr;`3`=完成但有异常项——**退出码 3 不是失败**,必须读脚本 stdout 的单行 JSON 摘要,把 `anomalies` 逐项呈现给用户,绝不静默吞掉。
- 派生字段(如 `fill_status`)一律现算不落盘(D7);脚本外的落盘仅限候选 checkpoint 与确认门工件(单次成文,不 append)。

## 阶段0 输入受理

Agent 做什么:

1. 请用户上传基础文件:招标文件/技术规范书/图纸/评分办法(常为分卷),每卷分配一个**文件代号**(2-4 位大写字母,如 ZB=招标文件、JS=技术规范书、PB=评分办法)——clause_id 复合前缀 `<代号>-C-<序号>` 按此分配,防跨卷撞号。约定俗成:招标文件=ZB;其余卷按用户确认的代号。
2. 分流确认:`.docx`=python-docx 解析(带 zipfile+XML 直读兜底);`.pdf`=pdfplumber;上传时 uploads 已自动转换出同名 `.md`(markitdown 链路)——**读原文用 read_file 行区间读这个 .md,不整读、不读二进制原文件**。扫描件(无文本层)为 V1 受限支持:ingest 退出码 2 时如实告知用户(eai-flow-ocr 全文 OCR 模式端点未部署前,请提供文字版或分段粘贴)。
3. 答疑/补遗文件标记为**增量输入**,到达时走阶段3,不与基础文件混跑。
4. 检查既有 `project_snapshot.json`(多轮承接,见下节)——有快照先续作,不重新生成。

## 阶段1 ingest(纯结构化解析)

Agent 调脚本(**每个文件代号一次调用**,共用同一 `--out` 增量合并;同名文件重跑=替换旧块):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py \
  --input /mnt/user-data/uploads/招标文件.docx \
  --code ZB \
  --out /mnt/user-data/workspace/bid/state
```

补遗/答疑文件同样先过 ingest(`--addendum` 标记增量,id 全局续号):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py \
  --input /mnt/user-data/uploads/补遗文件-01.docx \
  --code BY \
  --addendum \
  --out /mnt/user-data/workspace/bid/state
```

产出与职责:`<out>/sections.json` —— 按章节切块(`chunk = {chunk_id, source_file, anchor, heading_path, n_paras}`),每张表发稳定 `table_id` 并记录行数(`table = {table_id, source_file, anchor, n_rows, n_cols, caption}`);锚点分流 docx=section+段落序、PDF/OCR=page+section;定位"投标文件格式"类章节只产出章节树骨架(槽位语义定型留给阶段2)。**不做任何语义判断,无 LLM。**

Agent 检查点:退出码 0→进阶段2;3→摘要 anomalies 里的表行数不一致项呈现给用户;2→扫描件受限告知。

## 阶段2 extract(Agent 上下文内分块提取循环)

三类子任务共用一套循环纪律,提示词用 `references/extraction_prompt.md` 的三个子模板:①条款提取→clauses;②格式章节槽位定型→structure(识别"此处为盖章扫描件"=image 槽、从散文复原表格规格=table 槽、签字/盖章/份数/页码=format_check 槽);③评分细则表→rubric(逐行抽取,`scoring_method` 照抄原文)。分类判据一律按 `references/classification.md`(★/"实质性响应"/废标条款字样→mandatory;评分细则表→scoring;其余→normal;拿不准→保守 mandatory+`[待确认]`)。

**LLM 循环怎么跑**(每次一个 chunk 或一张表):

1. 从 sections.json 取当前块的 chunk_id/table_id、anchor、heading_path;用 `read_file` **行区间**读 uploads 转出的 .md 对应段落(定位:heading_path/section 锚点),绝不整读文件。
2. 按对应子模板组装提示词,产出候选条目数组(0 条也要产出空数组并写明判空理由——**全量裁决是管线不变量**:每个 chunk_id/table_id 必须有一条裁决记录,提取 0 条也必须显式判空,绝不静默跳过)。
3. **候选即刻落盘**(checkpoint,铁律:只保留计数与异常摘要进上下文):每次一个裁决=一个 JSON 文件,形态 `{"kind": "clauses|structure|rubric", "chunk_id": "..." 或 "table_id": "...", "items": [...], "note": "判空理由(可空)"}`(kind 与 id 二选一恰好一个;rubric 裁决必须挂 table_id)。建议命名 `candidates/CH-001.clauses.json`、`candidates/T-001.rubric.json`。
4. 超长文档分批处理;必要时经 `task()` 子代理分卷处理(注意 3 并发上限)。

**确定性校验与合并**(extract.py:锚点必须存在于 sections.json/枚举合法/跨块去重/Σmax_score=评分办法总分/chunk_id·table_id 全量有裁决,未裁决→`[待确认]`):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/extract.py validate \
  --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json /mnt/user-data/workspace/bid/candidates/T-001.rubric.json \
  --sections /mnt/user-data/workspace/bid/state/sections.json \
  --declared-total 100
```

校验干净(或用户确认异常项处置)后原子合并进状态目录(按 id upsert 幂等;Σ 不一致整体中止):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/extract.py merge \
  --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json \
  --sections /mnt/user-data/workspace/bid/state/sections.json \
  --state-dir /mnt/user-data/workspace/bid/state
```

(`--declared-total`=评分办法声称总分,Σ 校验基准;`--references` 缺省自动指向沙箱 references 目录。`validate` 不落盘、只出报告;`merge` 校验后写 clauses.json/structure.json/rubric.json。)合并完成即进确认门1。

## 确认门1(清单锁定——防上下文打爆)

对话内**只展示计数与异常项**,完整清单落盘为 markdown 工件(单次成文:clause_id/原文引文/锚点/章节列)。话术模板:

```
清单已生成,请核对(完整清单见工件 output/条款清单.md,这里只报计数与异常):
- 计数:强制条款 N1 条 / 评分条款 N2 条 / 普通条款 N3 条(共 N1+N2+N3 条)
- 异常项(逐项处置,校验失败块保持[待确认]):
  1. 强制待确认 X 条(校验失败/判据拿不准,保守预分类为 mandatory)
  2. 未锚定 X 条(锚点不在 sections.json,请核对原文位置)
  3. 评分表降级 X 项(合并单元格/跨页无法可靠解析,整表+人工确认)
  4. rubric 总分不符:Σmax_score=计算值 vs 评分办法声称总分(评分细则可能缺行)
  5. 未裁决 chunk/table X 个——显式判空确认(这些块确实无条款吗?)
- 实体白名单(拟锁定,请增删后确认):项目名/公司名/参数版本/人名…
请按 clause_id 告诉我要改分类的条目(如"ZB-C-017 改 scoring"),我直接回写 clauses.json。
```

Agent 动作:①从 merge 摘要 JSON 与 clauses.json 统计 N1/N2/N3;②生成完整清单工件;③用户逐条报 clause_id 改分类→Agent 用 str_replace 只改 clauses.json 的 `class` 字段值(clause_id 不动——class 可人工改,ID 永不变);④从封面/投标人须知抽取实体(公司名/项目名/参数版本/人名),用户增删确认后写 `state/entities_whitelist.json`(形态 `{"locked_at": ..., "source": ..., "entities": [{"type": "project|company|spec_version|person", "value": ...}]}`)——供阶段4 实体 lint 与阶段3 补遗 diff 消费。本门通过前不进阶段3/4。

## 阶段3 merge(补遗/答疑增量合并——隐藏废标项主藏身处)

补遗文件**到达即处理,不重开已过的确认门**;合并 diff 统一在下一次确认门/确认门2 呈现。流程:

1. `ingest.py --addendum --code <补遗代号>`(见阶段1 示例)→ 补遗块进 sections.json。
2. Agent 对补遗块跑阶段2 同款提取循环(子模板①),并产出**合并候选映射**:每份补遗=一次调用=一个候选文件,形态 `{"addendum_file": "...", "entities": [{"type","value"}](可选,Agent 从补遗文本观察到的实体), "items": [{"mapping_id", "action": "new|modify|void", "anchor"(章节锚点)或 "target"(条款 id)之一, "clause"(new/modify 的新条款载荷)}]}`。
3. 三级合并算法:①锚点精确匹配→自动落账;②相似度候选(仅 target 无 anchor)→脚本不合并,产出新旧并排 diff 待确认;③平手(锚点多命中)/同目标冲突→必须人工裁决。确定性落账:

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/merge_addenda.py \
  --addendum-candidates /mnt/user-data/workspace/bid/candidates/BY_addendum.json \
  --state-dir /mnt/user-data/workspace/bid/state \
  --decisions /mnt/user-data/workspace/bid/candidates/BY_decisions.json
```

(`--decisions` 形态 `{"decisions": [{"mapping_id", "decision": "apply|reject", "target"?}]}`,首次运行可省,产出 pending 后再补人工裁决重跑。)

落账语义:新增条款 `from_addendum=true`;修改→旧项 `superseded_by` 指向新 id;作废→旧项标 `voided`。内容哈希台账 `merge_ledger.json` 保证幂等(同一补遗跑两遍零写入)。**D3 新实体**:补遗实体 diff 白名单→增量清单 `addendum_entities_pending.json`(默认勾入,待确认门2);**D7 悬挂外键**:落账后扫描 linked_clause_ids,指向缺失/superseded/voided 条款→异常清单不静默。

## 阶段4 build(双卷骨架渲染)

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/build_output.py \
  --state-dir /mnt/user-data/workspace/bid/state \
  --out /mnt/user-data/workspace/bid/output
```

产出六件套(原子写盘,重跑字节级幂等):`商务卷.md`(structure 镜像渲染:每槽位标注类型/格式要求/待填内容提示,image 槽列出需用户提供的扫描件清单)、`技术卷.md`(技术参数逐项:要求原文锚点→响应要点→证据引用→满足状态,**条目标题内嵌 clause_id**——它是阶段5 重灌唯一可存活的锚点载体,交付物中保留不删)、`偏离表.md`(仅强制+偏离项)、`覆盖率报表.md`(清单总数/已响应/待确认/未分配)、`人核清单.md`(format_check 项:签字/盖章/份数/页码/目录全部人核)、`实体lint报告.md`(实体白名单 diff 全部 evidence_ref 与引用片段,上一项目残留→标[待核对];lint 标注"LLM 辅助",不称确定性)。

双卷 Word(markdown-to-docx 链路,仅粗体/斜体,强制条款**加粗**;每卷单次成文):

```bash
python /mnt/skills/public/markdown-to-docx/scripts/convert.py \
  --markdown /mnt/user-data/workspace/bid/output/商务卷.md \
  --output /mnt/user-data/outputs/投标文件-商务卷.docx \
  --title "投标文件-商务卷"
```

技术卷同法(`--markdown .../技术卷.md --output /mnt/user-data/outputs/投标文件-技术卷.docx`)。渲染边界如实向用户声明:管道表格无法表达合并单元格/列宽→此类表格槽标[待人工复刻]并入人核清单;图片不经 md 链路插入——build_output 已生成扫描件清单,如需占位图由 Agent 用 python-docx 后处理一次性插入(每卷单次成文),终稿人工替换;format_check 项全部人核,不进确定性判定。

**技术部证据填充(双源,填骨架阶段做)**:①手动上传样例方案(主源):用户把旧标书/样例方案/资质/参数表拖进线程(uploads→sandbox),Agent 对附件全文检索(grep/read_file)引用片段进 `evidence_ref`,零持久化;②知识库:knowledge-factory MCP(`kf_query_templates`/`kf_resolve_template`)可直达,但其语料是环评/水保/消防类模板——先探测一次,空手而归则如实告知此源不可用,不虚设。

## 确认门2(补遗合并确认 + 终稿复核)

话术模板:

```
补遗已合并、骨架已产出,请确认两件事:
一、补遗合并 diff 表(工件 output/补遗diff表.md),逐项确认(有异议报 mapping_id):
  - 新增 X 条 / 被替代 Y 条 / 作废 Z 条(被替代=旧条款已 superseded,按新条款响应)
  - 新实体确认列:补遗新增实体已默认勾入白名单,可人工增删
    (确认后我更新 entities_whitelist.json 并重跑同一补遗候选,增量清单清零)
二、终稿复核清单(人核清单.md),format_check 项必须人工签字,skill 不做最终承诺:
  - 格式:签字/盖章/份数/页码/目录(全部人核)
  - 资质:证书扫描件是否已替换占位图
  - 报价:价格表与报价策略(是否开标前最终确定)
  - 承诺:服务承诺/质保期措辞
确认无误后即可分发双卷 Word 给团队填写;回传后进阶段5 模拟评分。
```

Agent 动作:①把 merge_addenda 摘要的 applied/pending/anomalies 整理成 diff 表工件,`addendum_entities_pending.json` 列"新实体确认"列(D3:补遗新增实体默认勾入白名单,人工可改,阶段4 lint 始终用最新白名单,防补遗后合法新实体被误报[待核对]);②用户确认新实体后写入 entities_whitelist.json,重跑同一 `--addendum-candidates`(幂等)使增量清单清零删除;③待裁决映射按用户决定写 `--decisions` 文件重跑落账。

## 阶段5 模拟评分(终稿提交前必跑;可重跑,报告 version++ 留痕)

**先对齐成稿状态,再评分**——两种形态:

- **会话内填写态** = clauses.json/structure.json 当前状态(即时,无需重灌;证据行可为空,评审对象=会话内骨架——Agent 自行 grep 技术卷.md/商务卷.md 检索证据)。
- **团队回传 Word** = 先经 uploads 自动转换(docx→md,既有链路),再确定性锚点重灌——**重灌输入必须显式指定**(用户指定或线程内最新回传,防多版回传并存时灌了旧版):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py reingest \
  --source /mnt/user-data/uploads/投标文件-技术卷-回传.md \
  --state-dir /mnt/user-data/workspace/bid/state
```

重灌锚点契约(载体在阶段4 渲染时已埋定):商务卷锚点=structure.json 树路径标题链(章节标题=招标文件规定结构,改标题即形式违规→标题天然稳定);技术卷锚点=条目标题内嵌的 clause_id。不重灌会出现"客观项按旧状态计 0 分、主观项按新稿评高分"的自相矛盾。匹配器硬化(D6,四类失败全显式):同一锚点多命中→不取首个,整项进异常区待人核;匹配前文本归一化(去编号/空白/全半角),防样式改动导致精确匹配雪崩;clause_id 在回传稿重复出现(Word 修订模式)→异常区;命中率低于阈值(`--threshold`,默认 0.6)→整体降级为"人核覆盖率清单",不做部分计分。匹配失败项标 `needs_human_verify`——既不计 0 分也不静默通过,汇总进评分报告异常区。

**评分三分类**:objective 项=确定性汇总(基于重灌后的清单状态,是汇总不是验证);price 项=标"无法模拟"(依赖竞对报价,现库为 mock);subjective 项=Agent 逐项 LLM 评审(纪律与输出记录格式见 `references/scoring_prompt.md`:评分办法原文为尺、证据 grep 定位、逐项独立评审防锚定、给分+理由+失分点、主观分标"模拟参考值")。

执行序列(四步):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py assemble-evidence \
  --state-dir /mnt/user-data/workspace/bid/state
```

→ `evidence_pack.json`(逐 rubric 项:关联条款+证据行+评审提示)。Agent 读证据包跑主观评审循环(每次只呈现当前 rubric 项及其证据,不呈现其他项得分),逐项记录 `{"rubric_id","score","max_score","rationale","evidence_quote","missing_points","improvement"}`,落盘为评分记录 JSON(裸数组或 `{"records":[...]}`):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py aggregate \
  --scores /mnt/user-data/workspace/bid/candidates/subjective_scores_v1.json \
  --state-dir /mnt/user-data/workspace/bid/state
```

(Σmax_score 纵深复检,不一致→异常中止不落汇总;objective 确定性汇总;price 标无法模拟;消费主观记录。)

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py report \
  --state-dir /mnt/user-data/workspace/bid/state
```

→ `state/评分报告/version_N.md`:逐项得分/满分/理由/失分原因+改进建议清单(按 失分值×可改性 排序)+异常区(needs_human_verify/重灌失败/降级项);主观分标注"模拟参考值";version++ 不覆盖历史。向用户呈现报告并按铁律7 落改进建议(每条落到 rubric_id 与缺失内容)。重跑评分=重复 assemble-evidence→评审→aggregate→report,新报告 version 递增。

## 上下文纪律(全程适用,防百页招标文件打爆上下文)

- 读原文一律 `read_file` **行区间**(按锚点/heading_path 定位区间),不整读文件;候选与中间结果**即刻落盘**为 checkpoint,只保留计数与异常摘要进上下文。
- 超长文档分批处理(每批一个 chunk/一张表);必要时经 `task()` 子代理分卷处理,注意 3 并发上限(SubagentLimitMiddleware 硬限)。
- 确认门只展示计数与异常项,完整数据走落盘工件(防 Approach A 复发:纯对话内解析必漂移)。
- 脚本摘要(stdout 单行 JSON)是阶段事实的唯一口径,异常项逐项呈现,绝不静默吞掉或自行"修正"。

## 多轮承接(project_snapshot.json)

每会话结束前写 `/mnt/user-data/workspace/bid/project_snapshot.json`:当前招标文件与各卷代号、状态文件版本(clauses/structure/rubric 条目数)、待办(未过确认门的项/待裁决 mapping_id/待人工签字项)、评分报告最新 version。新会话开始先读快照续作——严禁漂移回"重新生成"。跨会话状态一致性依赖三防线(D7):装载校验悬挂外键、派生字段现算不落盘、原子写盘。

## 注意事项

- 本技能不调外部标书 SaaS,招标文件与标书不出内网;解析全部走本地/已部署服务。
- 现有 bid-quote 数据为 mock:price 评分项、报价类情报注入只做接口预留(`response_skeleton.suggestion` 槽位),不虚构竞对数据。
- 主观评分是模拟参考值,不承诺与真实评审一致;二期评分校准闭环(真实评审结果回灌)落地前,报告须原样保留该声明。
- 知识库检索:RAGFlow 语料检索暂无 agent 侧接线,不承诺;knowledge-factory 语料为环评/水保/消防类模板,投标类价值未验证,探测一次即如实分级。
