---
name: fire-protection-report-v2
description: |
  为化工/石化/工业项目生成消防设计专篇报告。触发词："消防设计专篇"、"消防设计报告"、"防火设计专篇"等。
  
  报告结构优先取自知识工厂模板（generation_hint / compliance_rules / content_contract 元数据驱动），不可用时回退内置参考文档。
  
  ⚠ 本技能仅在用户未上传设计说明书(.docx)时使用。有说明书时路由到 fire-protection-extract。
---

# ⛔ 第一步：检查是否应该使用本技能（路由关卡，必须最先判断）

**如果用户已上传设计说明书（.docx 文件）或提到"upload"中包含设计说明书：**

→ **立即停止。不要使用本技能。** 改用 `fire-protection-extract` 技能。

这是硬规则，无例外。设计说明书存在 = 本技能不适用。不管你看到了什么触发词，先检查这个条件。

**如果用户没有上传设计说明书：** 继续阅读下面的内容。

---

# 消防设计报告技能 v2

## ⛔ 关键规则

### 关于输出语言

0. **所有输出一律用中文。** 包括但不限于：对话对用户的回复正文、任务描述、**SESSION INTENT → 会话意图**、**SUMMARY → 摘要**、**ARTIFACTS → 产出文件**、**NEXT STEP → 下一步**——这些框架标签**不准出现英文原文**，必须用中文替换。报告本身（Markdown 内容）更是全程中文。这是硬规则，用户的对话语言是中文，所有框架级标签和说明文字也必须用中文。

### ⛔ 关于缺失信息（最高铁律——贯穿全程）

**任何缺失信息一律由用户填写和提供。** 无论出现在哪个步骤、哪个章节——项目背景、火灾危险性分类、建筑规模、消防水量、投资金额、设备清单、气象条件中的具体数值——只要信息缺失：

- **绝不联网搜索**项目/工程内部数据（项目处于设计阶段，网上根本不存在，搜索只会引入幻觉；联网仅限地理/气象/标准三类客观信息，见"关于联网搜索"）
- **绝不编造、推断、估算、补全**任何具体数值
- **绝不**根据"行业常见值""经验数据""类似项目"自行填入
- **唯一正确做法**：在对应位置标注 `[待用户提供: 信息名]`，并立即用 `ask_clarification` 向用户追问，等用户提供后才能继续生成该部分。宁可整段留 `[待用户提供]` 占位、宁可报告不完整，也绝不填入来源不明的数据。

### 关于输出方式

1. 本技能生成**结构化 Markdown 文本**，用 `write_file` 写入 `/mnt/user-data/outputs/`，再 `present_files` 展示——**后端会自动把 outputs 文件同步进文档空间（docmgr）为 AIDocument**，供用户在文档空间编辑排版后导出 Word。
2. **不直接生成 .docx，也不调用任何"docmgr API/工具"**——项目无 docmgr MCP，agent 没有也无法直接创建 AIDocument。文档空间的 AIDocument 由 `present_files` 的后端回调自动创建（见关键规则第 12 条与步骤 5）。
3. 不使用 `word-document-server` MCP 工具、`markdown-to-docx` skill 或自写 Python 脚本来生成 Word。

这样设计是因为：文档空间提供了协作编辑、版本管理、排版工具和 Word 导出的完整工作流，比在技能中硬编码排版参数更灵活、更可维护。

### 关于模板获取（最高优先级 — 强制）

4. **调用 `knowledge-factory_kf_resolve_template` 是本技能的第一个工具动作，强制执行，不可跳过。** 该工具属于 knowledge-factory MCP 服务，已绑定可用，**不要假设它不可见或不可用**。

   **必须传入以下参数，一字不改**——漏传 domain_keywords 或传空数组会匹配到无关模板（如煤炭环评）：
   ```json
   {
     "domain_keywords": ["消防设计专篇", "消防设计", "消防"],
     "report_type": "fire_protection_design"
   }
   ```
   若返回 `found=true`，模板即为 `公用工程_消防设计专篇_模板`（8 章，score≥80），直接使用其 root_sections 的 generation_hint + content_contract 生成报告。
   若返回 `found=false`，按规则 7 回退。
5. **禁止在调用 `knowledge-factory_kf_resolve_template` 之前用 `read_file` 读取 `references/` 下任何文件**（`report_structure.md` / `terminology.md` / `content_guidelines.md` 一律先不读）。先调 MCP 拿到返回值，再读补充知识。
6. **禁止凭猜测跳过调用**——不得以"工具可能不可见 / 可能不可用 / 先读参考文件再说"为由不调用。唯一允许回退到 markdown 的情况是：你已**真正发起过这一次工具调用**，且返回结果明确为 `found=false`，或调用确实抛出了错误。
7. 仅当第 6 条的回退条件成立时，才读取 `references/report_structure.md` 作为 8 章结构来源。

### 执行顺序

8. 实际执行顺序：**① 调用 `knowledge-factory_kf_resolve_template` → ② 读 `terminology.md` + `content_guidelines.md` → ③ 内存中起草报告 → ④ 写入文档空间**。步骤 ① 是硬前置，未完成不得进入 ②。
9. 起草报告内容在内存中完成，不写中间文件。
10. 落盘用一次 `write_file` 写入 `outputs/`，再 `present_files` 触发后端自动同步为文档空间 AIDocument。

### 关于写盘与防循环（⚠️ 防止死循环 — 完整规范见步骤5"写盘铁律"）

11. **一次性写完整报告**：内存中完整生成全部 8 章（含封面、附录）后，用**一次 `write_file`（`append=false`）**写入。禁止分章节 `append`、禁止写完用 `str_replace` 修补落盘文件——二者引发"改一错、引入一新错"的级联，撞上循环上限被强制中止。有误则在内存整体重生成后再整体覆盖。
12. **直接写到 `outputs/`**：落到 `/mnt/user-data/outputs/{项目名称}消防设计专篇.md`，不先写别处再 `cp`/`mv`/二次 `write_file` 复制。写完用一次 `present_files` 展示——后端自动同步进文档空间（docmgr）。
13. **工具失败不盲目重试**：禁用相同参数重试；最多修正一次（如纠正路径）再试，**连续失败 2 次必须停止并如实告诉用户**。

### 关于工具范围（⚠️ 不要调用无关工具）

14. 本技能**仅用**以下工具：`read_file` / `bash` / `write_file` / `present_files` / `knowledge-factory_kf_resolve_template` / `ask_clarification` / `web_search`（仅限下述"关于联网搜索"的三类查询）。
15. **禁止**调用 `text-to-cad_*` / `cad_*` / `word-document-server_*` 等与消防报告编写无关的工具——它们是 CAD 模型生成 / Word 排版工具，**不能用来执行 Python、读取文档或推进报告**。若想"跑代码"用 `bash`；想"读文档"用 `read_file` 或先按第 17 条转换。

### 关于联网搜索（⛔ 重要——禁止搜索项目信息）

**项目处于设计阶段，项目相关信息网上根本不存在，搜索纯属浪费且会引入幻觉。**

**禁止联网搜索的内容**（项目信息——必须由用户提供或从上传的设计说明书中提取）：
- ❌ 项目名称、建设单位、设计单位、投资金额、建设规模、产能（如"吉林石化 转型升级 新建 乙烷 丙烯腈 ABS 项目"这类查询**严禁发起**）
- ❌ 具体装置/设备清单、工艺流程、物料参数、火灾危险性分类
- ❌ 建筑规模、占地面积、建构筑物一览表
- ❌ 用户已在对话中提供或可从上传文档提取的任何信息

缺失上述信息时，用 `ask_clarification` 向用户追问，**绝不联网搜索**。

**允许联网搜索的内容**（仅三类客观辅助信息）：
- ✅ **地理信息**：项目所在城市/区域的经纬度、周边环境（如"吉林市 龙潭区 地理位置"）
- ✅ **气象信息**：项目所在地的气象参数（如"吉林市 年平均气温 降水量 风速 气压 雷暴日"）——用于报告第2章气象条件表
- ✅ **标准规范**：GB/HG 标准的具体条款、版本、适用范围（如"GB50160 防火间距 条款"）

判断标准：**能查到的客观地理/气候/法规信息 → 可搜；属于某个具体工程项目的内部数据 → 绝不搜，问用户。**

### 关于上传的源文档（.docx/.pdf 设计说明书等）—— ⚠️ 必读

16. 系统配置 `uploads.auto_convert_documents=true`——**上传的 docx/pdf 会自动在 `uploads/` 下生成同名的 `.md` 文件**（gateway 使用 markitdown 转换，已在容器内验证可用）。所以读取上传源文档**只需 `read_file /mnt/user-data/uploads/<文档名>.md`** 提取项目信息——不需要 bash、不需要写转换脚本。

17. 若 `.md` 未自动生成（极端情况，如超大文件转换超时），回退用技能自带转换脚本（按第 5 条规则，先调 kf_resolve_template 再读 reference）：
    ```
    bash: /app/backend/.venv/bin/python /mnt/skills/custom/fire-protection-report-v2/references/docx_to_md.py \
              "/mnt/user-data/uploads/<文件名>.docx" \
              "/mnt/user-data/workspace/<文件名>.md"
    ```
    但正常情况下不需要——先检查 uploads/ 下是否有 `.md`。**禁止自己编写 docx 提取脚本**，也不要用物理路径 `/app/backend/...`。

18. **路径一律用虚拟路径**（`/mnt/user-data/uploads/...`、`/mnt/user-data/workspace/...`、`/mnt/skills/...`），**禁止**用容器物理路径（`/app/backend/...`）——物理路径只在 bash 进程内部偶然有效，传给 `write_file`/`read_file`/`present_files` 等工具一定出错。脚本里也写虚拟路径，不要写成 `/app/backend/.deer-flow/...`。

19. 若转换失败、文件非 docx/pdf、或关键信息缺失：用 `ask_clarification` 一次性向用户补齐（项目名/编号、火灾危险性分类、建筑规模），不要卡在提取上反复尝试。

## 概述

此技能为化工和石化工程项目生成专业的消防设计专篇报告。优先从知识工厂获取报告模板元数据，利用模板中从样本报告抽取的结构化知识（生成提示、合规规则、内容契约）驱动更精准的报告生成。当知识工厂模板不可用时，自动回退到内置参考文档。

生成的内容为结构化 Markdown，写入文档空间供用户后续编辑排版和 Word 导出。

## 报告结构（8章）

标准消防设计专篇报告遵循以下结构（来源：模板 `root_sections` 或 `references/report_structure.md`）：

| 章节 | 标题 | 内容 |
|------|------|------|
| 1 | 设计依据及采用的标准 | 设计依据、技术标准、地方法规 |
| 2 | 概述 | 项目位置、功能定位、建设规模、气象条件 |
| 3 | 火灾危险性分析 | 项目明细表、火灾危险性分类 |
| 4 | 防火安全措施 | 总平面布置、防雷接地、供电安全、建筑防火、通风措施 |
| 5 | 消防设施 | 室外水消防、室内水消防、灭火器、火灾报警、视频监控 |
| 6 | 灭火救援设施 | 消防通道、回转场地 |
| 7 | 消防设施专项投资概算 | 投资估算表 |
| 8 | 图纸及表格 | 附图清单、设备表 |

## 引用的核心标准

- GB50160-2008（2018版）- 石油化工企业设计防火标准
- GB50016-2014（2018版）- 建筑设计防火规范
- GB50058-2014 - 爆炸危险环境电力装置设计规范
- GB50116-2013 - 火灾自动报警系统设计规范
- GB50140-2005 - 建筑灭火器配置设计规范
- GB50974-2014 - 消防给水及消火栓系统技术规范
- GB50057-2010 - 建筑物防雷设计规范（第4章防雷设计引用）
- GB50223-2008 - 建筑工程抗震设防分类标准（第4章抗震措施引用）
- GB50189-2015 - 公共建筑节能设计标准（第4章节能措施引用）
- 《中华人民共和国消防法》（2019修订）

---

## 工作流

### 步骤1：了解需求

当用户请求消防设计专篇时，确定以下信息。用户可能不会一次提供全部信息，对于缺失的关键信息应主动追问，对于可从上下文推断的信息直接使用：

**若用户上传了源文档**（如 设计说明书.docx）：先按关键规则第 17 条用 `bash` 跑一次 `docx_to_md.py` 转成 `.md` 并 `read_file`，从中提取下列信息——不要追问用户已经在文档里提供的内容。

**必须确认**（缺少则追问）：
- 项目名称和编号
- 项目类型：新建/改建/扩建
- 火灾危险性分类

**尽量收集**（缺少时可标注待补充）：
- 建筑规模和功能区
- 用户的具体要求或重点领域
- 是否有现有文档或样例可供参考
- 建设地点（用于气象条件和地方法规）
- 设计单位名称

**信息不足时的策略**：
- 如果用户只给了项目名，先基于常见化工项目模板生成草稿，在需要具体数据的表格中标注 `[待补充]`
- 绝不编造具体数值（如消防水量、投资金额），用占位符 `[XX]` 并提示用户补充

**⛔ 用户确认门禁 — 在用户确认前禁止进入步骤2：**

步骤1收集到的信息必须向用户展示并等待确认。展示格式如下：

```
已收集以下项目信息：

| 项目 | 值 | 来源 |
|------|-----|------|
| 项目名称 | {名称} | 用户提供 |
| 项目类型 | {类型} | 用户提供 |
| 火灾危险性分类 | {分类} | 用户提供 |
| 建筑规模 | {规模或[待补充]} | ... |
| 设计单位 | {单位或[待补充]} | ... |

请确认以上信息是否正确。如需修改请说明。确认后我将开始生成报告。
```

只有在用户回复"确认"/"没问题"/"开始"或等价肯定答复后，才能进入步骤2。如果用户提供了修正信息，更新对应字段后重新展示确认表格。

**变量→模板章节映射**（确认后自动建立，供步骤4使用）：

| 收集的变量 | 对应模板章节 |
|-----------|-------------|
| 项目名称、设计单位、日期 | 封面 |
| 设计依据、标准清单 | 第1章 |
| 项目位置、建筑规模、功能定位、气象条件、消防站 | 第2章 |
| 火灾危险性分类、项目主项表 | 第3章 |
| 建筑规模（面积/高度/结构类型） | 第4章 |
| 消防水量、灭火器类型（来自用户或模板默认值） | 第5章 |
| 建设地点（消防通道要求） | 第6章 |
| 项目规模（投资估算基准） | 第7章 |

步骤4生成时，对每个模板章节，使用上表中对应的变量值填充。未收集到的值标注 `[待补充]`。

### 步骤2：解析报告模板（⚠️ 必须执行 — 在读取任何参考文件之前）

**输入:** 步骤1确认的项目信息
**工具:** `knowledge-factory_kf_resolve_template`
**输出:** 模板元数据（generation_hint, compliance_rules, content_contract）或 fallback 标记（found=false）

**这是你必须执行的第一个工具调用**（不是"尝试"、不是可选项，也不要"先读参考文件再回头调"）。立即调用：

```
knowledge-factory_kf_resolve_template(
    domain_keywords=["消防设计专篇", "消防设计报告", "消防设计篇章"],
    industry="化工",
    min_completeness_score=60
)
```

**拿到 `found=true` 时**：
- 使用返回的 `sections` / `root_sections` 作为报告结构
- 每个章节独立拥有 `generation_hint`、`compliance_rules`、`content_contract`、`example_snippet`
- 输出提示：`✅ 已从知识工厂获取模板：{name} v{version}（完整度: {completeness_score}/100, 匹配级别: {match_level}）`
- **不要**读取 `report_structure.md`（直接用模板返回的 sections）

**仅当你已实际调用并得到 `found=false`（或调用确实抛错）时**才回退：
- 输出提示：`⚠️ 知识工厂返回 found=false，使用内置参考文档继续`
- 此时才读取 `references/report_structure.md` 获取 8 章结构
- 后续步骤使用全局 GB 标准列表替代逐章 compliance_rules
- ⚠️ 不得在未实际调用的情况下声称"不可用"而回退

### 步骤3：加载补充知识（必须在步骤 2 的 MCP 调用完成之后）

**输入:** 步骤2返回的模板元数据（或 fallback 标记）
**加载:** `references/terminology.md` + `references/content_guidelines.md`
**输出:** 已加载领域术语和编写规范，准备生成

完成步骤 2 的 `knowledge-factory_kf_resolve_template` 调用后，读取以下两个文件作为补充知识：
- `references/terminology.md` — 化工消防专业术语（火灾危险性分类、耐火等级、消防设施术语等）
- `references/content_guidelines.md` — 各章节编写规范和注意事项

注意：`references/report_structure.md` **不在本步骤读取**——仅当步骤 2 回退时才读它。

### 步骤4：起草报告内容（在内存中完整生成，一次性写出）

**输入:** 步骤1确认的变量值 + 步骤2的模板元数据（或 fallback references/）+ 步骤3的术语和编写指南
**生成:** 按模板章节结构逐章生成（模板有多少章就生成多少章，不限于 8 章）
**输出:** 内存中的完整 Markdown 报告（下一步落盘）

此步骤在内存中**完整生成全部章节**（含封面、附录），不分章节、不写中间文件、不边写边 `append`。完整内容在步骤 5 用**一次 `write_file`** 落盘——写盘铁律见步骤 5，务必遵守，否则极易触发死循环。

**⛔ 禁止生成目录：** 报告中**不要包含目录页（TOC）**。原因：Markdown 里手写的目录在导出 Word 后既不能自动更新页码、也不能联动跳转，反而是死文本占篇幅。Word 的目录应在文档空间排版阶段由 Word 的"引用→目录"功能自动生成（基于标题样式）。本技能只生成正文（封面 + 各章正文 + 附录），目录交给 Word。

**Markdown 输出格式规范**：

```markdown
# 封面信息

项目名称：{项目名称}
报告类型：消防设计专篇
编制单位：{设计单位}
日期：{编制日期}
版本：V1.0

---

# 第1章 设计依据及采用的标准

## 1.1 设计依据

1. ...
2. ...

## 1.2 设计采用的技术标准、规范

1. 石油化工企业设计防火标准（2018版） GB50160-2008
2. ...

## 1.3 地方相关法规

...

---

# 第2章 概述

...

（各章依次类推，章与章之间用 `---` 分隔）
```

**表格格式**：使用标准 Markdown 表格语法

```markdown
| 序号 | 条件 | 单位 | 数值 |
|------|------|------|------|
| 1 | 温度 | | |
| | 年平均气温 | ℃ | XX |
```

**列表格式**：使用标准 Markdown 有序/无序列表

```markdown
1. 石油化工企业设计防火标准（2018版） GB50160-2008
2. 建筑设计防火规范（2018版） GB50016-2014
```

**公式格式（LaTeX 数学渲染）**：前端已集成 KaTeX（`remark-math` + `rehype-katex`）。

- 行内公式使用 `$...$`：`$Q = 20000\ \text{m}^3/\text{h}$`
- 块级公式使用 `$$...$$`：`$$V = \frac{Q}{A} = \frac{20000}{3.14} = 6369.43\ \text{m}^3/\text{h}$$`
- 变量下标：`Q_e`, `Q_{消防}`；单位：`\text{m}^3/\text{h}`, `\text{MPa}`；乘号：`\times`
- 简单数值直接写，带计算步骤的公式用 LaTeX

**使用模板时**，每章按以下元数据约束生成：

| 元数据字段 | 作用 |
|-----------|------|
| `generation_hint` | 该章的 LLM 生成提示词——描述内容要点、引用标准条款、建议结构 |
| `content_contract.key_elements` | 必须覆盖的要素清单，逐项检查 |
| `content_contract.min_word_count` | 字数下限约束，防止内容过于简略 |
| `content_contract.forbidden_phrases` | 禁止出现的用语（如"大约""可能""暂定"） |
| `content_contract.structure_type` | 输出格式：`narrative_text` / `table` / `mixed` |
| `compliance_rules` | 该章必须遵循的具体 GB 规范条款 |
| `example_snippet` | 样例内容片段，供参考风格和详略 |

**⛔ 信息缺失策略（防止编造）：**

对于 `content_contract.key_elements` 中的每个要素：
- 有信息来源（用户提供、上传文档、模板示例）→ 准确写入
- 无信息来源 → 标注 `[待补充: 要素名]`，如 `[待补充: 消防水量]`
- `min_word_count` **不适用于无信息可写的章节**——宁可字数不足，不可编造填充
- `forbidden_phrases` 中的词（"大约""可能""暂定"）表明值不确定，应改为 `[待确认]` 标注 |

各章节内容要点见 `references/report_structure.md` 和 `references/content_guidelines.md` 中的详细说明。

**回退到 markdown 时**，按旧版逻辑生成：以 `report_structure.md` 的章节描述为提示，不施加显式内容约束。

### 步骤5：一次性写入 outputs（禁止分块 / 修补 / 复制）

把步骤 4 在内存中**完整生成**的报告，用**一次** `write_file` 直接写入（这是本步骤唯一允许的落盘操作）：

```
write_file(
    path="/mnt/user-data/outputs/{项目名称}消防设计专篇.md",
    content=<步骤4 完整生成的全部 Markdown>,
    append=false
)
```

**步骤5a：立即调 present_files（⚠️ 不可跳过——不调则不会同步到文档空间）**

在 `write_file` 之后**立即独立调用** `present_files`（不是 `write_file` 的参数）：
```
present_files(filepaths=["/mnt/user-data/outputs/{项目名称}消防设计专篇.md"])
```

**写盘铁律**（全技能唯一的防循环规范——关键规则 11~13 与步骤 4 均指向此处；违反即触发死循环）：
- ✅ 一次 `write_file` 写入完整内容，`append=false`；有误则在内存整体重生成后再整体覆盖。
- ❌ 禁止分多次 `append` 拼章节（会制造重复段落）。
- ❌ 禁止写完再用 `str_replace` 修改落盘文件（会误删相邻内容）。
- ❌ 禁止"先写 workspace 再 `cp`/`mv` 复制到 outputs"——直接写到 `outputs/`。

文件落盘全流程只允许上面这一次 `write_file`；不得在 `present_files` 或同步失败后反复重试（见第 13 条）。

### 步骤6：合规检查（调用 fire-regulatory-compliance-check）

报告写入后，调用 `fire-regulatory-compliance-check` 技能的自动化检查脚本进行 10 项合规验证：

```bash
python /mnt/skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py \
  --report "/mnt/user-data/outputs/{项目名称}消防设计专篇.md" \
  --output "/mnt/user-data/outputs/{项目名称}消防设计合规检查报告.md"
```

脚本检查 10 项内容（PASS / WARN / FAIL）：
1. 火灾危险性分类（GB50016/GB50160）
2. 建筑耐火等级（GB50016 §3.2.1/§5.2.1）
3. 防火间距（GB50016 §5.2/GB50160）
4. 消防给水系统（GB50974）
5. 火灾自动报警系统（GB50116）
6. 灭火器配置（GB50140）
7. 爆炸危险环境电气（GB50058）
8. 灭火救援设施（GB50016 §7.1）
9. 标准引用完整性（6 项核心标准）
10. 法律合规（消防法 2019）

**检查结果处理**：
- 全部 PASS → 合规检查通过，向用户展示合规报告摘要
- 有 WARN/FAIL → 回到步骤 4，在内存中修正报告内容，整体重写 `/mnt/user-data/outputs/{项目名称}消防设计专篇.md`，然后重新运行检查。**最多修正 2 轮**。
- **超过 2 轮仍有 FAIL**：生成合规报告并标注 `以下项目需人工修正`（列出每项 FAIL 的具体条款和当前状态）。报告仍可导出（文档空间自动同步），但需在导出前提示用户："以下合规项未能自动修正，已标记为[待人工修正]，建议在提交审批前由专业工程师复核。"

**修正时**参考 `fire-regulatory-compliance-check` 技能的 `references/` 目录下的 GB 标准摘要文件获取具体要求。

修正时参考 `fire-regulatory-compliance-check` 技能的 `references/` 目录下的 GB 标准摘要文件获取具体要求：
- `references/gb50016_2014_2018.md` — 建筑设计防火规范
- `references/gb50160_2008_2018.md` — 石化防火标准
- `references/gb50058_2014.md` — 爆炸危险电气
- `references/gb50116_2013.md` — 火灾报警系统
- `references/gb50140_2005.md` — 灭火器配置
- `references/gb50974_2014.md` — 消防给水
- `references/fire_law_2019.md` — 消防法

---

## 各章节内容要点

详见 `references/content_guidelines.md` — 8 章完整内容指南（含表格格式、数据来源、关键参数）。章节结构变化只需修改该文件，不影响本技能主文件。

---

## 模板元数据驱动 vs Markdown 回退对比

| 约束维度 | 知识工厂模板 | Markdown 回退 |
|----------|-------------|---------------|
| generation_hint | 每章精准提示（从样本报告抽取） | 通用段落描述 |
| compliance_rules | 每章独立 GB 规范条款 | 全局 GB 标准列表 |
| content_contract.key_elements | 必须覆盖的要素清单 | 无强制要求 |
| content_contract.min_word_count | 字数下限约束 | 不限制 |
| content_contract.forbidden_phrases | 禁止用语排除 | 不禁止 |
| content_contract.structure_type | 输出格式约束（文本/表格/混合） | 自由选择 |
| example_snippet | 样例片段参考 | 无参考 |
| 模板演进 | 知识工厂编辑模板 → 下次生成即时生效 | 手动编辑 markdown |

---

## MCP 工具依赖

此技能依赖以下 MCP 服务：

1. **knowledge-factory**（优先使用）：
   - `knowledge-factory_kf_resolve_template` — 智能模板匹配（核心工具）
   - `knowledge-factory_kf_list_domains` — 列出可用领域（辅助发现）

2. **文档空间（docmgr）写入**（无独立 MCP，经 `present_files` 回调自动完成）：
   - agent 用 `write_file` 写入 `/mnt/user-data/outputs/` 后调用 `present_files`，后端回调自动把该文件同步为 AIDocument
   - 用户可在文档空间中编辑排版后导出 Word

## 参考文件

- `references/report_structure.md` — 8章结构详细说明（模板不可用时 fallback）
- `references/terminology.md` — 消防术语词典（补充知识，始终加载）
- `references/content_guidelines.md` — 各章节内容编写指南（补充知识，始终加载）
- `references/chapter_examples/sample_fire_design.md` — 报告样例（仅供方法论参考：风格、详略、论述逻辑；**不自动加载**，需要时 `read_file` 取具体片段即可）

> 与 `coal-eia-report` 一致：`chapter_examples/` 下的样例不参与自动加载，仅在你需要参考行文风格/详略时按需读取。

## 注意事项

- 优先级：知识工厂模板 > markdown 参考文件
- 补充知识始终加载（术语 + 编写规范独立于数据源）
- 整体判断不混用：模板整体不可用 → 全部回退 markdown，不出现"第3章用模板、第5章用 markdown"
- 模板版本自动感知：`knowledge-factory_kf_resolve_template` 按 status='published' + completeness_score DESC 自动获取最新版本
- 始终使用最新版本的 GB 标准
- 确保火灾危险性分类遵循正确的标准
- 验证所有数值满足规范要求
- 在需要时包含适当的工程计算
- 不编造具体数值，用 `[XX]` 或 `[待补充]` 标注不确定数据
- 输出为结构化 Markdown，不直接生成 .docx
