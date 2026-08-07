# 封面配置重构：结构化多页元素编辑器 — 设计文档

**日期**: 2026-08-07
**状态**: APPROVED（2026-08-07）
**范围**: 报告输出扩展
- 后端 `backend/app/extensions/output/{schemas.py, layout_import.py, generator.py, service.py}`
- 前端 `frontend/src/extensions/output/{cover-state.ts, components/LayoutTemplateEditor.tsx, types.ts, api.ts}`

**关联**: `2026-08-07-cover-config-editor-remediation-design.md`（P0-P3 修复，已合入；本文档是封面配置的**结构性重构**，取代母版透传思路）。

---

## 1. 背景与问题

当前封面配置 = **OOXML 母版透传 + 槽位绑定**（cover_master.xml/images/slots）。真实样例验证暴露三个结构性问题：

1. **僵化**：封面结构锁死在导入样例的 OOXML 里。换一种报告封面就不适用——消防设计专篇（标题横幅表 + 会签表）与环评报告（3 页：封面/批准页/名单表）结构完全不同。
2. **提取偏差无法手工纠正**：槽位只能改 sampleValue/kind，布局结构改不了。已发现偏差：`project_name` 误绑「基础设计」（实为项目阶段）、`设计单位` 被定字面量（用户要变量）、报告名称/版次 kind 语义冲突。
3. **多页封面**：环评样例目录前 18 块实为 **3 页**（每页由分节符 w:pPr/w:sectPr 分隔）。现有模型没有"页"概念。

**结论**：封面本质是"目录前的一段多页排版内容"，应建模为**可编辑的结构化元素**（文本/表格/图片/间距），而非不可拆的 OOXML 快照。

## 2. 设计目标

- 封面 = 目录前所有内容，支持**多页**（页 = 样例分节符切分）。
- 导入样例 → 提取 → **可编辑元素**，偏差直接改。
- 文本/表格/图片/间距均为可增删、排序、改样式的元素。
- 变量绑定挂元素：每个文本元素可选绑定变量（报告标题/建设单位/项目编号/日期/项目名/设计阶段/设计单位），生成时替换。
- 表格可编辑（行列增删、单元格文本）。
- 旧 cover_master（OOXML）模板：首次编辑自动转换，旧渲染路径保留兜底。

## 3. 数据模型（替代 cover_master）

### 3.1 后端 schema（`schemas.py`）

```python
class CoverImageSchema(BaseModel):
    b64: str
    ext: str = "png"

class CoverElementSchema(BaseModel):
    id: str
    type: Literal["text", "table", "image", "spacer", "divider"]
    # text
    text: str = ""
    fontFamily: str = "宋体"
    fontSize: int = 12
    bold: bool = False
    color: str = "#000000"
    alignment: Literal["left", "center", "right"] = "center"
    spaceBefore: int = 0   # pt
    spaceAfter: int = 0
    slotId: str | None = None   # 变量绑定: title/client/project_number/date/project_name/stage
    # table
    rows: int = 0
    cols: int = 0
    cells: list[list[str]] = Field(default_factory=list)   # [row][col] 文本
    headerBg: str | None = None
    borderColor: str = "#000000"
    # image
    image: CoverImageSchema | None = None
    widthCm: float | None = None
    # spacer
    lines: int = 1

class CoverPageSchema(BaseModel):
    elements: list[CoverElementSchema] = Field(default_factory=list)

class CoverSchema(BaseModel):   # 新封面模型
    mode: Literal["elements"] = "elements"
    pages: list[CoverPageSchema] = Field(default_factory=list)
    sourceFile: str = ""
```

`LayoutTemplate` 三个 schema 增加 `cover_elements: CoverSchema | None = None`；`cover_master` 保留为**旧数据字段**（迁移/兜底）。

### 3.2 生成优先级

1. `cover_elements` 存在 → `_render_cover_elements`（新）
2. 否则 `cover_master` 存在 → `_render_cover_master`（旧，兜底）
3. 否则 `cover_template` → 旧开关渲染（兜底）
4. 都没有 → 无封面

### 3.3 前端类型（`types.ts`）

`CoverElement` / `CoverPage` / `Cover` 镜像后端；`LayoutTemplate.coverElements: Cover | null`；`coverMaster` 保留旧类型。

## 4. 提取（`layout_import.py`）

新增 `_extract_cover_pages(doc) -> list[CoverPageSchema]`（替换 `_extract_cover_master` 为主路径）：

1. **边界**：目录文本/首个 Heading 前的所有 `<w:p>`/`<w:tbl>` = 封面区（与现有一致）。
2. **切页**：遇到段落 `pPr/sectPr`（分节符）或 `w:br type="page"` → 开启新页。无分节符的样例 → 单页流。
3. **逐块转元素**：
   - 段落 → text（从 run/rPr 提取 fontFamily/fontSize/bold/alignment；空段 → spacer）。
   - 表格 → table（rows/cols/cells 文本；探测首行底纹 → headerBg）。
   - 图片 → image（base64 + ext + 可选 widthCm）。
4. **变量绑定启发式**（best-effort 默认，编辑器可改）：
   - 冒号字段（`项目编号：XX`/`档 案 号：XX`/`工程编号：…`）→ 整段一个 text 元素（`text` 保留全文），`slotId` 绑对应变量；生成时保留「标签：」前缀、只替换冒号后的值部分（见 §5.2）。
   - 独立「项目名」占位 → 绑 project_name。
   - 最大字号的「第…册…专篇/报告书/计算书」行 → 绑 title。
   - `20\d{2}年\d{1,2}月|20XX年0X月` → 绑 date。
   - 其余不绑（留原文）。

**提取偏差根治**：`项目名`/`基础设计`（阶段）/`第三册 消防设计专篇`（报告名）成为**独立文本元素**，编辑器对每个元素选绑定——不再有 `project_name` 误抓下一行的正则问题。

## 5. 生成（`generator.py`）

新增 `_render_cover_elements(doc, cover, resolved)`：

1. 逐页构建；页间 `doc.add_section(WD_SECTION.NEW_PAGE)`。
2. text 元素 → `add_paragraph`（fontFamily/fontSize/bold/color/alignment/spaceBefore/spaceAfter）；若 `slotId` 有解析值 → 替换文本：文本含冒号（`：`/`:`）时**保留冒号前标签、只替换冒号后值部分**（兼容「项目编号：XX」→「项目编号：P001」）；无冒号则整体替换（「项目名」→ 真实项目名）。
3. table → python-docx 表格（rows/cols 建表，逐格填 `cells` 文本；headerBg 设首行底纹；borderColor 设边框）。
4. image → 复用 `get_or_add_image` 重嵌；widthCm 设宽。
5. spacer → N 个空段；divider → 下边框段。
6. 槽位解析：复用 `_resolve_cover_fields` + frontmatter（title/client/project_number/date/project_name/stage），同现有。

## 6. 编辑器 UI（`LayoutTemplateEditor.tsx` 封面 section 重构）

- 有 `cover_elements` 时：**页签**（页1/页2/…）+ 每页**元素列表**。
- 元素行：类型图标 + 内容预览 + 编辑（展开：文本、字体、字号、加粗、对齐、段前段后、**变量绑定下拉**）+ 删除 + 拖拽排序。
- 变量绑定下拉：无 / 报告标题 / 建设单位 / 项目编号 / 日期 / 项目名 / 设计阶段 / 设计单位。
- 「添加元素」：文本 / 表格 / Logo / 分隔线 / 空行。
- 表格元素：网格编辑器（行列增删 + 单元格输入）。
- 每页基础预览（渲染元素样式，非 OOXML 保真）。
- 保留：重新导入、移除封面。
- 复用 `cover-state.ts` 纯逻辑（元素模型 helpers + 状态 patch）。

## 7. 迁移

- 旧模板（`cover_master` 存在且 `cover_elements` 为空）：**首次编辑时后端转换** `_cover_master_to_elements(cover_master)` —— 对存储的 cover 区 OOXML 跑一遍切页/转元素（与 `_extract_cover_pages` 同源），编辑器展示元素，保存存 `cover_elements`。
- 转换失败 → 保留旧母版 + 前端提示"转换失败，仍按旧母版渲染"，不阻塞。
- `_render_cover_master` 保留作旧数据兜底渲染。

## 8. 错误处理

- 提取：块级 try/except，坏块降级为 spacer/text，绝不中断。
- 生成：元素级 try/except，坏元素跳过 + `logger.warning`（沿用 M5 可见性）。
- 表格空行列 / 图片解码失败 → 跳过 + warning。
- 转换失败 → 保旧母版 + 提示。

## 9. 测试

两个真实样例金标准：`基地项目-消防设计专篇.docx`、`2横城矿区总体规划（修编）环评——报告书报批版2021.1.docx`。

- **提取**：消防 → 1 页、标题横幅+会签表元素、绑定正确（title/date/项目编号等）；环评 → 3 页、封面/批准页/名单表元素、页数正确。
- **生成**：元素 → docx → 文本/表格/图片存在；绑定槽位值替换、未绑定保留原文。
- **往返**：导入 → 改元素（换绑定/增删/改字号）→ 保存 → 再生成 → 验证。
- **表格**：行列增删、单元格文本。
- **迁移**：旧 cover_master → 元素转换正确。
- **前端**：cover-state.ts 元素模型纯逻辑测试。

## 10. 风险与回退

- **OOXML → 元素转换保真度**：复杂格式（嵌套表格/文本框/浮动图）可能降级 → 回退 = 旧 `_render_cover_master` 路径保留，转换失败仍能出封面。
- **切页**：依赖分节符；无分节符的自然分页样例提取为单页流，用户编辑器手动加分页符。
- **绑定启发式误差**：用户编辑器逐个元素改绑定，误差不阻塞。
- 后端改动较大，但旧路径全保留，回退安全。

## 11. 非目标（本期不做）

- 完整 WYSIWYG 画布（绝对定位拖拽）——结构化流式元素足够，YAGNI。
- 文本框（w:txbxContent）自由排版——复杂格式降级为整块或跳过。
- 每页像素级预览——基础样式预览即可。
- 会签表签字人预填（花名册子系统，另期）。
