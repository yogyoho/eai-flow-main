---
name: fire-protection-extract
description: |
  用户已上传设计说明书（.docx/.pdf，文件名可能为「总说明书」「设计说明书」等）并请求编写消防设计专篇 → 用本技能（不用 fire-protection-report-v2）。
  报告由流水线脚本自动生成（bash run.sh），你不是报告作者。
  未上传附件时改用 fire-protection-report-v2。
  **如果 bash 工具不可用（工具列表里没有 bash），直接回退到 fire-protection-report-v2——不要手动读取设计说明书来拼凑报告。**
---

# 适用条件（路由确认）

**以下条件全部满足 → 使用本技能：**
1. 用户已上传附件（.docx 或 .pdf）
2. 用户请求编写消防设计专篇

**附件类型识别：**
- 文件名含「设计说明书」「总说明书」「说明书」→ 直接确认
- 文件名不含上述关键字 → 先读附件第一页内容，检查是否包含「设计说明书」「总说明书」「说明书」任一关键字
- 确认为设计说明书 → 继续；不匹配 → 回退到 fire-protection-report-v2

**未上传附件 → 直接用 fire-protection-report-v2，不要切到本技能。**

**如果你看到的是 fire-protection-report-v2 的内容——你选错了。立即切换到 fire-protection-extract。**

---

# 消防设计专篇 — 智能流水线（E3 契约生成 + E4 契约库）

## ⚠️ 启动前必检：bash 工具是否可用

**在动手前，先确认你的工具列表里有 `bash`。** 如果没有 bash，你无法执行任何 Python 脚本。

**有 bash** → 按下面章节走。

**没有 bash** → 不要手动读说明书、不要手动拼凑报告。直接告知用户"当前环境缺少 bash 工具，无法执行流水线，建议改用 fire-protection-report-v2 从模板生成"，然后**立即停止**。

---

## 阶段判定（初步设计 / 基础设计）

消防设计专篇按设计阶段区分大纲：**初步设计 7 章** / **基础设计 8 章**，由 `references/stage-outlines/{阶段}.json` 锁定（标题逐字对齐样例，不得自创章节）。

1. 用户请求里显式写了「初步设计」「基础设计」→ 作为 `run.sh` 第 3 参传入（显式覆盖）。
2. 否则 run.sh 自动从源说明书前 60 段+标题识别（"初步设计"/"基础设计" 字样，见 detect_stage.py）。
3. 阶段不同 → 大纲不同 → 抽取映射（sources）也不同，E3 按所选阶段大纲的 `guide[]` 生成。

---

## 你的操作流程

### 第 1 步：跑流水线
```bash
WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs \
  bash /mnt/skills/public/fire-protection-extract/scripts/run.sh \
  "/mnt/user-data/uploads/<说明书.docx>" "<项目名>" [初步设计|基础设计]
```
- 把 `<设计说明书.docx>` 换成 uploads/ 下实际文件名，`<项目名>` 换成项目名。
- 终端最后一行 `REPORT_READY: <path>` 即成品路径。

### 第 2 步：检查契约命中情况

**情况 A：run.sh 输出含 `✓ 使用契约: <name>`**
→ 契约库有匹配，报告已生成。跳到第 4 步展示成品。

**情况 B：run.sh 输出含 `CONTRACT_NEEDED` 或 `CONTRACT_ERROR`（契约缺失/格式异常）**
→ 都需要走 E3 生成新映射后重跑。**契约未就绪时 run.sh 已硬失败（exit 3），不会产出半成品报告。**

### 第 3 步（E3）：为新项目生成专属契约

当 run.sh 输出 `CONTRACT_NEEDED: <structure.json 路径>` 时，你需要帮这个新项目生成一份 mapping 契约。

**⚠️ 工具限制：整个 E3 流程最多 10 次 bash 调用。不要逐锚搜索——用批量脚本一次获取所有信息。**

**3a. 批量提取关键信息（1 次 bash 调用完成全部搜索）**
```bash
python3 -c "
import json
struct = json.loads(open('<STRUCT_PATH>', 'r', encoding='utf-8').read())

# 1. 输出所有 headings（用于章节映射）
print('=== HEADINGS ===')
for h in struct.get('headings', []):
    print(f'L{h[\"level\"]} ¶{h[\"para_i\"]}: {h[\"text\"][:80]}')

# 2. 输出所有表格（用于表号映射）
print()
print('=== TABLES ===')
for no, t in struct.get('tables', {}).items():
    title = t.get('title', '')[:60]
    print(f'{no}: {title}')

# 3. 对所选阶段大纲的每个 verbatim 节，用其 guide[] 关键词批量搜索最佳段落
print()
print('=== GUIDE SEARCH ===')
outline = json.loads(open('<OUTLINE_PATH>', 'r', encoding='utf-8').read())
for sec in outline.get('sections', []):
    if sec.get('class') != 'verbatim':
        continue
    label = sec['fire']
    found = []
    for kw in sec.get('guide', []):
        for p in struct['paras']:
            if kw in p['text']:
                found.append((p['i'], p['text'][:100], kw))
                if len(found) >= 6:
                    break
        if len(found) >= 6:
            break
    print(f'{label}:')
    for pi, pt, kw in found[:6]:
        print(f'  ¶{pi} [{kw}]: {pt}')
    print()
"
```
- `<OUTLINE_PATH>` 换成所选阶段大纲路径（run.sh 输出 `OUTLINE:` 行）。搜索词取大纲每节 `guide[]`，不是硬编码列表。

**3b. 基于批量输出生成 mapping 契约**

一次性读上面脚本的输出，对照所选阶段大纲 `references/stage-outlines/{阶段}.json`，为每个 verbatim section 生成映射。
**Mapping 新格式（与大纲按索引对齐，只存锚点）：**
  ```
  {"sources": [<第0节源列表>, <第1节源列表>, ...]}  # 与所选阶段大纲 sections[] 按索引 1:1
  ```
  verbatim 节填 `[{"kind":"para","paras":[i]}]` / `[{"kind":"range","paras":[a,b]}]` / `[{"kind":"table","no":"表号"}]`；heading/template/compute 节填 `null`。用 `guide[]` 关键词一次批量搜全。不编字符串锚。

**3c. 写入、保存、重跑管线（必须执行，不可跳过）**

```bash
# 1. 写 mapping（sources 与大纲 sections[] 按索引 1:1）
write_file(<WORK_DIR>/<项目名>_mapping.json, <生成的JSON>)

# 2. 保存到契约库（save <阶段> <项目名> <structure.json>，mapping 从 stdin 读）
cat <WORK_DIR>/<项目名>_mapping.json | \
  python /mnt/skills/public/fire-protection-extract/scripts/contract_store.py \
  save "<阶段>" "<项目名>" <STRUCT_PATH>

# 3. ⛔ 必须重跑 run.sh —— 报告只有这一条生成路径
#    不要用你刚才分析 structure.json 时看到的段落自己写报告。
#    extract.py 负责逐字摘抄 + grounding_check 负责溯源验证。
#    你自己写的报告没有 grounding 保证——会编造出源文档不存在的数据。
WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs \
  bash /mnt/skills/public/fire-protection-extract/scripts/run.sh \
  "/mnt/user-data/uploads/<说明书.docx>" "<项目名>" "<阶段>"
```

**4. 展示 run.sh 生成的报告**——不是你自己写的。报告路径在 `REPORT_READY:` 行。
```
read_file(<REPORT_PATH>)
present_files(filepaths=["<REPORT_PATH>"])
```

**⛔ 你自己写的报告 = 没有 grounding = 编造数据。** 哪怕是"整理一下格式"、"补充表格"、"加一个结论"，都不行。报告的每一个字必须来自 extract.py 的输出——因为只有它经过了 grounding_check 的逐字溯源验证。

**⛔ 禁止逐锚搜索**——一次批量脚本获取全部信息，然后一次性生成完整 mapping。不要对每个 section 单独开 bash 搜索。

### 第 4 步：展示成品 + 合规检查结果 + 相关性扫描
run.sh 现在自动在末尾跑合规检查（[5/5]步骤），生成 `<项目名>消防设计合规检查报告.md`。
展示两个文件：
```
present_files(filepaths=[
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md",
  "/mnt/user-data/outputs/<项目名>消防设计合规检查报告.md"
])
```

**若 run.sh 输出 `REPORT_NEEDS_REVIEW`（grounding<0.85 或含 `[⚠未找到]` 或 missing/uncovered/conflict 非 0）→ 必须提示用户「E5 校准（仅旧格式契约可用）或 E3 重跑（两层格式）」，不得直接交付。**

**相关性扫描（C方案——标记疑似无关内容）：**
读报告，对每个 section 检查内容是否和该 section 标题主题相关。
如果某节抄进来了明显无关的内容（如经济分析出现在"建设性质"节），
在该节的 `> 源:` 标记后加一行：
> ⚠ 本节部分内容疑似与主题无关，建议人工确认

告知用户哪些 section 被标记了，让用户决定是否收窄段落范围（重跑 E3）。

**展示格式要求：**
- **不要用代码块（\`\`\`）包裹你的回复内容**——直接输出 markdown 文字、表格、列表，让前端渲染。
- 代码块只用于展示命令或代码，不用于展示报告摘要、结果总览等内容。

简要总结报告生成结果（直接 markdown 渲染，不要代码块包裹），然后列出推荐后续操作：

**推荐后续操作（列出让用户选择，不要自己执行）：**
- 📋 **格式化报告** — 去掉源文档编号残留、生成目录 → 说"格式化"
- 📄 **导出为 Word** — 转 .docx 格式 → 说"导出 docx"
- 🔧 **校准失配锚** — 修复少量未命中段落 → 说"校准"

---

## 仅在用户明确请求时执行（不要自动触发）

以下步骤**不是默认流程的一部分**。只有当用户在后续对话轮次中明确请求时才执行。

**⚠ E5/E6 当前仅兼容旧版 sections 格式契约。两层格式（{"sources":[...]}）契约下会空转，待后续迁移——新契约的校准请走 E3 重跑生成新映射。**

**E6 校准视图**（用户说"生成校准视图"/"校准报告"时）
```bash
python /mnt/skills/public/fire-protection-extract/scripts/calibration_view.py \
  <REPORT_PATH> <STRUCT_PATH> <MAPPING_PATH> \
  > /mnt/user-data/outputs/<项目名>_校准视图.html
present_files(filepaths=["/mnt/user-data/outputs/<项目名>_校准视图.html"])
```
HTML 页面用颜色标记每个 section 的状态（✅ 正常 / ⚠ 需校准），支持一键筛选失配项。比人眼扫描 markdown 高效得多。

**如果报告有少量 `[⚠未找到]`（≤5 处且契约已存在）→ 运行 E5 自动校准：**

### 第 5 步（E5）：自动校准失配锚

**⚠ E5/E6 当前仅兼容旧版 sections 格式契约。两层格式（{"sources":[...]}）契约下会空转，待后续迁移——新契约的校准请走 E3 重跑生成新映射。**

当 run.sh 显示已有契约但仍有少量失配时，用 auto_calibrate.py 自动修复：

**5a. 运行校准分析**
```bash
python /mnt/skills/public/fire-protection-extract/scripts/auto_calibrate.py \
  <REPORT_PATH> <STRUCT_PATH> <MAPPING_PATH>
```
输出 JSON 数组，每个元素是一个校准提案：
- `section`: 失配的 section 名
- `failed_anchor`: 失败的锚
- `proposal`: 候选修复（含 `confidence` 0-1）

**5b. 审核提案**
- `confidence ≥ 0.7`：高置信度，直接接受
- `confidence 0.3-0.7`：中置信度，检查 proposal.note（段落预览），判断是否正确
- `confidence < 0.3`：低置信度，需要手动在 structure.json 中搜索正确段落

**5c. 应用修复**
用 `write_file` 更新 mapping JSON 中被接受的锚，然后重跑流水线（带阶段参数）：
```bash
WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs \
  bash /mnt/skills/public/fire-protection-extract/scripts/run.sh \
  "/mnt/user-data/uploads/<说明书.docx>" "<项目名>" "<阶段>"
```

**5d. 保存更新后的契约**
```bash
cat <WORK_DIR>/<项目名>_mapping.json | \
  python /mnt/skills/public/fire-protection-extract/scripts/contract_store.py \
  save "<阶段>" "<项目名>" <STRUCT_PATH>
```

---

## ⛔ 你的回合到此结束

**执行完第 1-4 步后，你必须在这里停止。**

- **不要加载** report-format、report-enrich、report-polish 或合规检查的 SKILL.md
- **不要调用** 任何不属于本技能的工具或脚本
- **不要自动** 格式化报告、生成合规检查、或执行任何后续处理
- 上述 E5/E6 步骤**仅在你已收到用户明确请求后**才能执行

这些是独立技能，由用户在下一轮对话中自行决定是否调用。你的工作在 present_files 之后就完成了。

---

## ⛔ 不要做的事

- **不要 read_file 原始 .docx**——只读 structure.json（已解析的结构化数据）。
- **不要手动改写报告正文**——报告由 extract.py 生成。
- **不要跳过 E3 契约生成**——如果 run.sh 输出 CONTRACT_NEEDED，必须先建契约再重跑。
- **E3 生成契约时不要编造内容**——找不到匹配的段落就标记 `[⚠未找到]`。
- **E5 校准只接受高置信度提案**——低置信度的锚可能抄错段，宁可不修不要修错。
- **不要新增所选阶段大纲里没有的章节**——报告章节结构以 `references/stage-outlines/{阶段}.json` 为准（初步设计 7 章 / 基础设计 8 章），不要自创章节标题；不要加分析评论——每条 verbatim 内容必须有明确 source 锚定到源文档段落。
- **不要逐锚搜索**——E3 用批量脚本一次获取全部信息。对每个 section 单独开 bash 搜索是死循环，触发工具限制会导致管线未跑完。
- **不要 synthesise/总结/改写**——摘抄 = 逐字复制源段落。不得用自己的话重写、不得加"对策"、"分析"、不得把多个段落合并成一节评论。

## 参考文件
- `references/extractor_rules.md` — 锚点选取/防抄错规则
- `references/stage-outlines/` — 阶段大纲（初步设计 7 章 / 基础设计 8 章）
- `references/fire_spec_mapping.json` — 遗留基础设计模板（仅测试使用；权威结构以 stage-outlines 为准）
- `scripts/run.sh` — 流水线入口
- `scripts/contract_store.py` — 契约库管理
- `scripts/auto_calibrate.py` — 锚自动校准（E5）
