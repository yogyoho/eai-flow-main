# 阶段0-2: 输入受理 → ingest → extract → 确认门1(分组执行指南)

进入条件: 空工作区首跑, 或多轮续作(snapshot `phase` ∈ {0-受理, 2-提取中, 确认门1-待锁定, 0-受理(续作中断)})。
本组配套契约(进入对应子任务前先读): `extraction_prompt.md`(提取三子模板)、`classification.md`(分类判据)、三个 schema(clauses/structure/rubric)。
命令一律照抄 SKILL.md 速查表(唯一合法调用形态); 本文给流程与判据, 不重复罗列调用。

## 阶段0 输入受理

Agent 做什么:

1. 请用户上传基础文件:招标文件/技术规范书/图纸/评分办法(常为分卷), 每卷分配一个**文件代号**(2-4 位大写字母, 如 ZB=招标文件、JS=技术规范书、PB=评分办法)——clause_id 复合前缀 `<代号>-C-<序号>` 按此分配, 防跨卷撞号。约定俗成:招标文件=ZB; 其余卷按用户确认的代号。
2. 分流确认:`.docx`=python-docx 解析(带 zipfile+XML 直读兜底);`.pdf`=pdfplumber;上传时 uploads 已自动转换出同名 `.md`(markitdown 链路)——**读原文用 read_file 行区间读这个 .md, 不整读、不读二进制原文件**。扫描件(无文本层)为 V1 受限支持:ingest 退出码 2 时如实告知用户(eai-flow-ocr 全文 OCR 模式端点未部署前, 请提供文字版或分段粘贴)。**用户只有 .md 没有 .docx/.pdf 原件时**(ingest 报"不支持的文件类型"):`ask_clarification` 请用户上传原件, 拿到前不进入阶段1——**严禁**手写 sections.json、自行"转格式"或绕过 ingest 继续(E2E 实证: 手写 state 导致 extract 全候选隔离, agent 反复考古烧尽 recursion 预算)。
3. 答疑/补遗文件标记为**增量输入**, 到达时走阶段3(见 stage3-merge-gate2), 不与基础文件混跑。
4. 检查既有 `project_snapshot.json`(多轮承接, 见下节)——有快照先按快照 `phase`/`next_step` 续作, 不重新生成;无快照(首跑)在受理完成、分配代号后立即跑一次速查表中的 snapshot.py 命令登记项目与代号(`--project`/`--code` 后续每次快照自动沿用, 不重填)。

## 阶段1 ingest(纯结构化解析)

Agent 调脚本(**每个文件代号一次调用**, 共用同一 `--out` 增量合并):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py \
  --input /mnt/user-data/uploads/招标文件.docx \
  --code ZB \
  --out /mnt/user-data/workspace/bid/state
```

同名文件重跑按内容指纹分流——未变=保号跳过(摘要 `skipped_unchanged`, sections.json 字节不变);内容有变=替换旧块发新号(摘要 `replaced`+`replaced_files` 旧 id 清单, **旧 id 的候选裁决已失效, 需对替换后新 id 重跑阶段2 提取**)。

产出与职责:`<out>/sections.json` —— 按章节切块(`chunk = {chunk_id, source_file, anchor, heading_path, n_paras}`), 每张表发稳定 `table_id` 并记录行数(`table = {table_id, source_file, anchor, n_rows, n_cols, caption}`);锚点分流 docx=section+段落序、PDF/OCR=page+section;定位"投标文件格式"类章节只产出章节树骨架(槽位语义定型留给阶段2)。**不做任何语义判断, 无 LLM。**

Agent 检查点:退出码 0→进阶段2;3→摘要 anomalies 里的表行数不一致项呈现给用户;2→扫描件受限告知(不是错误, 不重试)。

## 阶段2 extract(Agent 上下文内分块提取循环)

三类子任务共用一套循环纪律, 提示词用 `references/extraction_prompt.md` 的三个子模板:①条款提取→clauses;②格式章节槽位定型→structure(识别"此处为盖章扫描件"=image 槽、从散文复原表格规格=table 槽、签字/盖章/份数/页码=format_check 槽);③评分细则表→rubric(逐行抽取, `scoring_method` 照抄原文)。分类判据一律按 `references/classification.md`(★/"实质性响应"/废标条款字样→mandatory;评分细则表→scoring;其余→normal;拿不准→保守 mandatory+`[待确认]`)。

**LLM 循环怎么跑**(每次一个 chunk 或一张表):

1. 从 sections.json 取当前块的 chunk_id/table_id、anchor、heading_path;用 `read_file` **行区间**读 uploads 转出的 .md 对应段落(定位:heading_path/section 锚点), 绝不整读文件。
2. 按对应子模板组装提示词, 产出候选条目数组(0 条也要产出空数组并写明判空理由——**全量裁决是管线不变量**:每个 chunk_id/table_id 必须有一条裁决记录, 提取 0 条也必须显式判空, 绝不静默跳过)。
3. **候选即刻落盘**(checkpoint, 铁律:只保留计数与异常摘要进上下文):每次一个裁决=一个 JSON 文件, 形态 `{"kind": "clauses|structure|rubric", "chunk_id": "..." 或 "table_id": "...", "items": [...], "note": "判空理由(可空)"}`(kind 与 id 二选一恰好一个;rubric 裁决必须挂 table_id)。建议命名 `candidates/CH-001.clauses.json`、`candidates/T-001.rubric.json`。
4. 超长文档分批处理;必要时经 `task()` 子代理分卷处理(注意 3 并发上限)。

**确定性校验与合并**(extract.py:锚点必须存在于 sections.json/枚举合法/跨块去重/Σmax_score=评分办法总分/chunk_id·table_id 全量有裁决, 未裁决→`[待确认]`):

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

(`--declared-total`=评分办法声称总分, Σ 校验基准;`--references` 缺省自动指向沙箱 references 目录。`validate` 不落盘、只出报告;`merge` 校验后写 clauses.json/structure.json/rubric.json。)

**格式保真校验(merge 后、确认门1 前必跑;补遗落账后与 build 前各再跑一次)**——格式 1:1 复刻的确定性防线(回放实证:标题被 LLM 归一化剥掉编号/（格式）后缀、模板固定文字没抄进 template_text、格式章节骨架漏节点, 全部静默漏过):

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/check_format.py \
  --state-dir /mnt/user-data/workspace/bid/state \
  --sources /mnt/user-data/uploads/招标文件.md
```

(--sources=该招标文件 uploads 转出的同名 .md, 多卷可列多个;只读校验, 绝不回写"修正"。退出码 3 时读 stdout 单行 JSON 的 anomalies 逐项呈现:标题不逐字/template_text 非逐字子串/固定行单元格对不上/骨架漏节点/未给 sources 显式降级。)校验+合并完成即进确认门1。

## 确认门1(清单锁定——防上下文打爆)

对话内**只展示计数与异常项**, 完整清单落盘为 markdown 工件(单次成文:clause_id/原文引文/锚点/章节列)。话术模板:

```
清单已生成,请核对(完整清单见工件 outputs/条款清单.md,这里只报计数与异常):
- 计数:强制条款 N1 条 / 评分条款 N2 条 / 普通条款 N3 条(共 N1+N2+N3 条)
- 异常项(逐项处置,校验失败块保持[待确认]):
  1. 强制待确认 X 条(校验失败/判据拿不准,保守预分类为 mandatory)
  2. 未锚定 X 条(锚点不在 sections.json,请核对原文位置)
  3. 评分表降级 X 项(合并单元格/跨页无法可靠解析,整表+人工确认)
  4. rubric 总分不符:Σmax_score=计算值 vs 评分办法声称总分(评分细则可能缺行)
  5. 未裁决 chunk/table X 个——显式判空确认(这些块确实无条款吗?)
  6. 格式保真异常 X 项(check_format):标题不逐字/模板原文缺失/固定行未复刻/骨架漏节点
- 实体白名单(拟锁定,请增删后确认):项目名/公司名/参数版本/人名…
请按 clause_id 告诉我要改分类的条目(如"ZB-C-017 改 scoring"),我直接回写 clauses.json。
```

Agent 动作:①从 merge 摘要 JSON 与 clauses.json 统计 N1/N2/N3;②生成完整清单工件(直接写到 `/mnt/user-data/outputs/条款清单.md`, 单次成文——present_files 只认 `/mnt/user-data/outputs/`, 写别处再 cp 是回放实证过的弯路);③用户逐条报 clause_id 改分类→Agent 用 str_replace 只改 clauses.json 的 `class` 字段值(clause_id 不动——class 可人工改, ID 永不变), **每轮改完立即跑速查表的 `state_guard.py sign --confirm-gate1-edit` 命令重登签名**(铁律9:不重登则后续所有脚本硬错误;无旗标会被拒——内容与既有签名不符时 sign 默认拒绝防洗白);④从封面/投标人须知抽取实体(公司名/项目名/参数版本/人名), 用户增删确认后写 `state/entities_whitelist.json`(形态 `{"locked_at": ..., "source": ..., "entities": [{"type": "project|company|spec_version|person", "value": ...}]}`——白名单本就由 Agent 写, 不在签名登记范围)——供阶段4 实体 lint 与阶段3 补遗 diff 消费。本门通过前不进阶段3/4;过门后跑一次 snapshot.py 更新快照。

## 本组状态文件

| 文件 | 产生 | 含义 |
|---|---|---|
| `state/sections.json` | 阶段1 | 章节块/表 + chunk_id/table_id + 锚点(校验基准) |
| `state/clauses.json` | 阶段2(阶段3 增量) | 义务清单(条款数据唯一来源, 铁律1) |
| `state/structure.json` | 阶段2(阶段3 增量) | 商务/技术双卷结构镜像与槽位 |
| `state/rubric.json` | 阶段2(阶段3 增量) | 评分标尺(Σmax_score 必须等于评分办法总分) |
| `state/entities_whitelist.json` | 确认门1 锁定(Agent 手写) | 实体白名单(阶段4 lint 与阶段3 diff 基准; **不签名登记**) |
| `state/.meta.json` | 各脚本写盘后自动 | 权威状态文件 sha256 签名登记表(装载前自动复核;铁律9) |

派生字段(如 `fill_status`)一律现算不落盘(D7);脚本外的落盘仅限候选 checkpoint 与确认门工件(单次成文, 不 append)。

**完成判据**:确认门1 用户确认锁定 + 白名单落盘 + 过门后 snapshot.py 更新(`phase` 变为 3/4-合并与构建)。

## 多轮承接纪律(本组高频翻车点)

- 快照由 snapshot.py 确定性生成, 严禁手写;每阶段动作完成后跑一次(ingest 后/merge 后/过门后)。
- 续作 run 的冷启动只读两样:`project_snapshot.json` + 当前阶段对应的那一份 references 文件;严禁 rm -rf 工作区/state 从零重放。
- 用户要求"重新执行/重跑完整流程"时:先跑速查表 `ingest.py --resume` 命令(只读核验既有受理), 再按 snapshot 续作;确需清空重来必须先 `ask_clarification` 征得用户明确确认。
- `ask_clarification` 中断等待用户期间不落盘任何 state 改动。

## 排错表(本组症状→处置, 不试错绕行)

| 症状 | 处置 |
|---|---|
| `FileNotFoundError` / `No such file or directory` | 用**绝对路径**重跑(速查表路径), 不 `cd`;文件确不存在→按实际路径改 |
| `unrecognized arguments` / `invalid choice` | 参数/子命令记错了——跑 `<脚本> --help` 对着速查表逐字重写, 不猜参数 |
| 签名校验失败(state_guard 报"内容与落盘签名不符/文件不存在") | 按错误行恢复指令**重跑产生该文件的脚本**重建;严禁手改 JSON/rm 绕过(铁律9) |
| ingest 退出码 2 | 扫描件→走 eai-flow-ocr, 不是错误重试 |
| ingest 报"不支持的文件类型"(仅收 .docx/.pdf) | `ask_clarification` 请用户上传 docx/pdf 原件;严禁手写 sections.json 或自造 state 继续(实证 42afc10f: 手写→锚点全隔离→烧尽递归预算) |
| 任何脚本退出码 3 | 不是失败——读 stdout 单行 JSON 的 anomalies 逐项呈现给用户 |
| merge 摘要 `replaced` 非 0 | 该文件旧 id 候选已失效→对替换后新 id 重跑阶段2 提取, 不是异常 |
| 用户要求重跑/"重新执行完整流程" | 先跑速查表 `ingest.py --resume`(只读核验既有受理), 按 snapshot 续作;rm -rf 前必须 `ask_clarification` 征得用户明确确认 |
| present_files 拒绝 | 工件必须写 `/mnt/user-data/outputs/`(确认门工件直接写到那里, 别写 output/ 再 cp) |
| 连续 5 次工具失败 | 铁律8 熔断:停下, 呈现失败清单, 问用户 |
