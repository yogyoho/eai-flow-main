# 提取 prompt 模板(extraction_prompt.md)

> 依据:设计文档 2026-08-16『详细设计』阶段2。Agent 在上下文内跑分块提取循环,三类子任务共用下述循环纪律;每次一个 chunk,候选 JSON 落盘后交 extract.py 确定性校验(锚点/枚举/去重/Σ/全量裁决)。

## 通用循环纪律(三个子模板共用)

1. **每次只处理一个 chunk**——绝不把多个 chunk 拼进同一次提取;读原文用 `read_file` 行区间,不整读文件(防百页招标文件打爆上下文)。
2. **候选 JSON 即刻落盘**:每处理完一个 chunk,立即把候选结果写入候选文件作为 checkpoint,只保留计数与异常摘要进上下文;超长文档分批处理,必要时经 `task()` 子代理分卷(注意 3 并发上限)。
3. **全量裁决(D5 覆盖度防线)**:每个 `chunk_id` / `table_id` 必须产出一条裁决记录;提取 **0 条** 也必须显式报"0 条——需确认门1 判空",绝不静默跳过——零漏检是管线不变量,不是验收口号。未裁决 id 一律 `[待确认]` 进确认门1。
4. **锚点格式按来源分流**:`docx=section+段落序`;`PDF/OCR=page+section`。锚点必须真实存在于 sections.json(extract.py 校验,对不上→该候选 `[待确认]`)。
5. **绝不编造**:无出处的值、无法核实的字段一律标 `[待确认]`;`source_ref.quote` 只能照抄原文片段(≤50字),不得改写、拼接、意译。
6. **枚举与字段严格按 schema**:clauses 候选→`clauses.schema.json`;structure 候选→`structure.schema.json`;rubric 候选→`rubric.schema.json`。字段名逐字一致,不多不少。
7. **ID 分配**:`clause_id` = `<文件代号>-C-<全局序号>`(ZB=招标文件/JS=技术规范书/PB=评分办法…),序号在当前文件内单调递增、类别无关;跨块重复由 extract.py 去重拦截。
8. 分类判据(`class`)一律按 `classification.md` 执行,判据冲突按其优先级规则(mandatory > scoring > normal)。

---

## 子模板① 条款提取 → clauses 候选

对当前 chunk 逐段识别"对投标方构成义务/要求的条款",产出 clauses 候选。`class` 判据见 classification.md(★/"实质性响应"/废标条款字样→mandatory;评分细则表→scoring;其余→normal)。`requirement` 是结构化转写,不是原文照抄;`response_status`/`response_skeleton`/`from_addendum`/`superseded_by` 由管线归一,候选可不填。

```
你是投标文件义务清单提取器。只处理下面这一个 chunk(来源: {source_file},锚点: {anchor})。
逐条识别对投标人构成义务或要求的条款,按以下 JSON 形态输出候选数组(0 条也要输出空数组并说明判空理由):

{
  "clause_id": "<文件代号>-C-<全局序号>",
  "source_file": "<来源文件名>",
  "class": "mandatory | scoring | normal",
  "category": "technical | commercial | qualification | format | service",
  "source_ref": {"page": <int|null>, "section": "<章节号或标题>", "para": <int|null>, "quote": "<原文片段,≤50字,照抄>"},
  "requirement": "<要求内容的结构化转写>",
  "response_status": "unassigned",
  "response_skeleton": {"points": [], "evidence_ref": null, "suggestion": null},
  "from_addendum": false,
  "superseded_by": null
}

(后四个字段为管线归一默认值,候选按此形态给出即可,不自行填写进展状态。)

硬性纪律:
- 只依据 chunk 原文提取;无出处/拿不准的字段值写 [待确认],绝不编造。
- quote 必须是 chunk 中真实存在的连续原文片段(≤50字)。
- 锚点取 chunk 自带的锚点,不得自行推算页码/段落序。
- 分类判据按 classification.md;判据冲突时 mandatory 优先。
```

## 子模板② 格式章节槽位定型 → structure 候选

ingest 只给出格式章节的章节树骨架;本子模板完成槽位语义定型:识别"此处为盖章扫描件"=image 槽、从散文复原表格规格=table 槽、签字/盖章/份数/页码/目录等非内容格式义务=format_check 槽、纯章节容器=group。格式章节若同时规定了技术部结构,技术卷同样入镜像(volume=technical);未规定处不造结构(由条款清单兜底组织)。

注意:`fill_status` 是派生字段,由管线在渲染/重灌时现算——候选与落盘**均不得包含**该字段(D7)。

```
你是投标文件结构镜像定型器。只处理下面这一个格式章节 chunk(来源: {source_file},锚点: {anchor})。
把章节树骨架定型为带槽位语义的 structure 节点,按以下 JSON 形态输出候选数组:

{
  "node_id": "S-<序号>",
  "volume": "commercial | technical",
  "path": "<章节标题链,如 投标文件格式/三、法定代表人身份证明>",
  "slot_type": "text | table | image | format_check | group",
  "required_format": {"desc": "<格式要求/待填内容提示|null>", "table_spec": <列头/行列结构对象|null>},
  "linked_clause_ids": ["<关联条款 clause_id,无则空数组>"]
}

硬性纪律:
- 章节结构只镜像招标文件规定,绝不自创章节/改写标题;path 的每一段必须是原文标题。
- slot_type 判定:文字内容=text;要求复刻表格=table(table_spec 从原文复原列头与行列数);
  需插入证件/图纸扫描件=image;签字/盖章/份数/页码/目录等非内容格式义务=format_check;纯容器=group。
- 合并单元格/列宽等无法在 table_spec 中精确表达时,如实降级标注,交确认门1 人工确认。
- 无出处的格式要求标 [待确认],绝不编造。
```

## 子模板③ 评分细则表 → rubric 候选

对当前以 `table_id` 锚定的评分细则表逐行抽取评分项;`scoring_method` 照抄评分办法原文(它是阶段5 主观评审的唯一标尺);`score_type` 判定:证书有无/参数满足=objective(状态汇总,不走 LLM)、需要评委主观评判=subjective、报价公式=price(依赖竞对报价,模拟时标"无法模拟")。

```
你是评分细则表抽取器。只处理下面这一张评分表(table_id: {table_id},来源: {source_file},锚点: {anchor})。
逐行抽取评分项,按以下 JSON 形态输出候选数组:

{
  "rubric_id": "R-<序号>",
  "item": "<评分项名称>",
  "max_score": <该项满分>,
  "scoring_method": "<评分办法原文,照抄>",
  "score_type": "objective | subjective | price",
  "linked_clause_ids": ["<该评分项考核的条款 clause_id,无则空数组>"],
  "source_ref": {"page": <int|null>, "section": "<章节,如 评分办法>", "para": <int|null>, "quote": "<原文片段,≤50字>"}
}

硬性纪律:
- scoring_method 必须照抄原文档的评分表述,不得概括改写。
- Σmax_score 必须与评分办法声称总分一致(extract.py 双检;不一致→异常项)。
- 合并单元格/跨页导致行结构无法可靠解析时,不得猜测拆行——整表降级为 [待确认],
  走"整表+人工确认"路径,并在裁决记录中说明降级原因。
- 无出处的分值/表述标 [待确认],绝不编造。
```
