# 封面母版 OOXML 透传 + 槽位绑定 — 设计文档

**日期**: 2026-08-07
**范围**: 报告输出扩展（`backend/app/extensions/output/` + `frontend/src/extensions/output/`）
**目标**: 让排版模板对话框的「封面配置」能真实还原样例 .docx 的封面样式与内容，生成时只替换项目变量。
**关联**: `docs/superpowers/specs/2026-08-06-word-export-layout-import-design.md`（排版导入总设计，本文件是其封面子专题的深化）。

---

## 1. 问题与根因

用户反馈：排版模板对话框的封面设置"不能真实还原样例文件的封面样式和内容"。

对真实样例 `backend/data/users/f8766d55-2b1b-422e-a945-5fcf268a8a39/knowledge/8376f624-95de-47b1-b871-0bb000b5a934/基地项目-消防设计专篇.docx` 的 OOXML 探测结论：

- 封面第 0–6 段为空段（留白）。
- `table[0]`（10×7 合并单元格）：**标题横幅**，合并大单元格里多行文字 `项目名 / 基础设计 / 第三册 消防设计专篇`。
- `table[1]`（11×6）：**编制人员会签表**，表头「编制人员」，列：专业名称 / 编制 / 校对 / 审核 / 审定，行：总图 / 结构 / …。
- 图片数 0，文本框 0，页眉页脚空，`different_first_page = False`。

三层全断：

1. **提取端瞎**：`layout_import.py::_detect_cover` 只读「首个 Heading 之前的段落」，但真实封面是表格（不是段落），且本样例在"目录"前没有任何 Heading 段落 → `pre=[]` → 返回 None，啥也没提取。
2. **模型端装不下**：`CoverTemplate` = `{showLogo, logoPosition, showTitle, showClient, showDate, showProjectNumber}`（6 布尔 + 1 位置），没有"合并单元格标题横幅""会签表格""多行结构化标题""真实 Logo 图"的任何概念。
3. **生成端只会居中段落**：`generator.py::_render_cover` 只会 `add_paragraph` 居中，画不出表格/会签栏，Logo 是假文字 `[编制单位 LOGO]`。

**结论**：当前架构从原理上无法还原表格类封面，不是调参能解决，是数据模型表达力天花板问题。封面本质是"一小块页面排版（表格+段落+可能的图）"，不是固定形状的表单。

## 2. 目标与非目标

**目标**
- 从样例 .docx 提取封面区（含表格、会签栏、图片），原样存为可复用的"封面母版"。
- 生成报告时，把封面母版 OOXML 原样注入首页，只替换预定义的"变量"槽位（报告标题/项目名/建设单位/项目编号/设计阶段/日期）为当次项目值。
- 编辑器「封面配置」改为：母版来源展示 + 槽位列表（变量/字面切换、靶文本可编辑、来源提示）+ 重新导入。

**非目标（本期不做）**
- 不做封面的可视化拖拽设计器（YAGNI；封面来自样例，不需要从零画）。
- 不做封面母版的实时 HTML 预览（表格封面 HTML 画不出真实效果，预览靠"生成输出"看真实 docx）。
- 不预填会签表签字人（那是"项目团队花名册"子系统，另期）。
- 不动 docmgr 的 `cover_presets.py` / `_render_cover_preset`（docmgr 导出专用，与报告输出排版模板互不影响）。

## 3. 已确认决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| D1 | 封面核心目标 | **还原样例**：布局/样式取自样例 .docx，生成时只替换项目变量 | 最贴合"真实还原"，对应 OOXML 透传 |
| D2 | 变量识别方式 | **固定槽位 + 编辑器核对**：标准槽位规则自动预填，用户在编辑器核对/微调 | 可预测、不繁琐 |
| D3 | 实现方案 | **B1 原始 OOXML 透传 + 槽位替换** | 唯一能保真还原表格封面的方案 |
| D4 | 图片存储 | base64 入 JSON（`cover_master.images`） | 封面图通常 0–2 张小 Logo，不值当独立资源存储 |
| D5 | 会签表 | 整张当**字面量**原样保留，签字格留空（供手签），不做槽位 | 避免引入花名册子系统 |
| D6 | 编辑器预览 | v1 不做封面母版实时预览，靠"生成输出"看效果 | 实时预览需服务端转 PNG 端点，本期 YAGNI |

## 4. 数据模型

### 4.1 后端 schema（`backend/app/extensions/output/schemas.py`）

新增两个 schema；`cover_master` 作为 `template_data` JSON 中的可选字段（JSON 列，无需 DB 迁移）。

```python
class CoverSlotSchema(BaseModel):
    id: str                       # 稳定 id: "title"|"project_name"|"client"|"project_number"|"stage"|"date"
    label: str                    # 显示名 "报告标题" / "建设单位"
    kind: str = "variable"        # "variable"(生成时替换) | "literal"(原样保留)
    sample_value: str             # 样例原文 —— 生成时被替换的"靶文本"
    default_from: str | None = None  # 解析来源: "doc_title"|"today"|"frontmatter:client"|None

class CoverMasterSchema(BaseModel):
    mode: str = "master"
    xml: str                      # 封面区 OOXML 片段(序列化的 <w:p>/<w:tbl>，deep-copy 自样例)
    images: list[dict] = []       # [{"orig_rid": str, "ext": str, "b64": str}]
    slots: list[CoverSlotSchema] = []
    source_file: str = ""         # 样例文件名，编辑器展示来源
    boundary: str = "before_toc"  # 提取边界(调试/重导用): "before_toc"|"before_first_heading"|"none"
```

`LayoutTemplateCreate` / `LayoutTemplateUpdate` / `LayoutTemplateResponse` 增加：
```python
cover_master: dict | None = None   # 与现有 cover_template 并列
```

### 4.2 生成优先级

`generator.py` 渲染封面时：
1. `cover_master` 存在且 `mode=="master"` → `_render_cover_master(...)`（新）
2. 否则 `cover_template` 存在 → 老的 `_render_cover(...)`（兜底，向后兼容）
3. 都没有 → 无封面

两个现有模板（给排水单体计算书、消防设计专篇）当前只有 `cover_template`（6 布尔），不受影响；用户重新"从样例导入"后才会产生 `cover_master`，之后走母版渲染。

### 4.3 前端类型（`frontend/src/extensions/output/types.ts`）

```ts
export interface CoverSlot {
  id: string;
  label: string;
  kind: "variable" | "literal";
  sampleValue: string;
  defaultFrom?: string | null;
}
export interface CoverMaster {
  mode: "master";
  xml: string;
  images: { origRid: string; ext: string; b64: string }[];
  slots: CoverSlot[];
  sourceFile: string;
  boundary: string;
}
// LayoutTemplate 增加:
//   coverMaster: CoverMaster | null;
```

`transforms.ts::transformTemplate` 增加手动字段映射 `cover_master → coverMaster`（该文件是逐字段手写转换，非通用 snake↔camel，需显式加）；保存方向（api 序列化）同步加 `coverMaster → cover_master`。

## 5. 提取（`layout_import.py`）

新增 `_extract_cover_master(doc, source_file="") -> dict | None`，与 `_detect_cover` 并存：`_detect_cover` 继续产出老的 `cover_template`（6 布尔，向后兼容），`_extract_cover_master` 产出新的 `cover_master`（返回 None 即视为无封面，走兜底）。

### 5.1 边界判定（命门，已对真实样例验证）

按 body 文档顺序遍历 `doc.element.body` 子元素，收集 `<w:p>` 与 `<w:tbl>`。**边界 = 先到者**：
- 第一个文本匹配 `^目\s*录$|^contents$` 的段落（本样例 TOC 是 Normal 样式"目录"二字，**必须靠文本匹配**），或
- 第一个 `p.style.name.startswith("Heading")` 的段落。

边界前的所有 `<w:p>`/`<w:tbl>`（按文档顺序，保持交错）= 封面区。

边界判定规则：
- 封面区只有空段（无表格、无非空段落）→ `boundary="none"`，返回 None（无封面，兜底）。
- 命中文本"目录"/contents → `boundary="before_toc"`。
- 命中 Heading → `boundary="before_first_heading"`。

### 5.2 序列化

deep-copy 封面区每个块元素，`etree.tostring(el, encoding="unicode")` 拼接 → `xml`。

### 5.3 图片

扫封面区所有 `a:blip`，取 `r:embed`（`{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed`）→ `doc.part.related_parts[rId]` → image part → 取字节 + 扩展名 → `images: [{orig_rid, ext, b64}]`。（本样例 0 张，但通用支持。）

### 5.4 槽位预填（固定槽位规则）

扫封面区拼接文本，按标准槽位预填 `slots`：

| id | label | 识别规则 | default_from |
|----|-------|---------|--------------|
| `title` | 报告标题 | 标题横幅单元格的多行文字（最大字号的单元格/段落文本，或含"专篇/报告书/计算书"关键词的单元格） | `doc_title` |
| `project_name` | 项目名 | 匹配 `项目名(称)?` 标签后的值，或单独成行的"项目名"占位 | None |
| `client` | 建设单位 | `建设单位|业主单位|建设单位：` 标签后的值 | `frontmatter:client` |
| `project_number` | 项目编号 | `项目编号|工程编号|编号：` 标签后的值 | None |
| `stage` | 设计阶段 | `设计阶段|阶段：` 标签后的值 | None |
| `date` | 日期 | 日期正则 `\d{4}[-/年]\d{1,2}` | `today` |

每个槽位：`kind` 默认 `"variable"`；`sample_value` = 样例里的原文字（生成时的靶文本）；未命中的槽位不创建。用户在编辑器可把某槽位切到 `"literal"`（原样保留，不替换），或编辑 `sample_value`（改靶文本）。

### 5.5 组装

`layout_import.py` 主提取函数在现有结果 dict 上增加：
```python
"cover_master": cover_master,          # 新
"cover_template": <老的 _detect_cover 布尔结果或 None>,  # 保留向后兼容
"cover_detected": cover_master is not None,
```

前端"从样例导入排版"已调用该提取端点，`cover_master` 随其余参数一起返回；编辑器据此填充「封面配置」。"重新从样例导入封面"按钮复用同一端点。

## 6. 生成（`generator.py`）

新增 `_render_cover_master(doc, master: dict, resolved: dict) -> None`，挂在现有 `has_cover` 分支（约 `generator.py:818-827`）。

### 6.1 步骤

1. 解析 `master["xml"]` 回元素（`etree.fromstring`，带 OOXML 命名空间映射）。
2. **槽位替换**：对每个 `slot.kind == "variable"` 且 `resolved` 有对应值的槽位，在 XML 的段落/单元格内把 `slot.sample_value` 替换为解析值。
   - 替换粒度：段落级。遍历每个 `<w:p>`，拼接其所有 `<w:t>` 文本；若含靶文本，则保留首个 `<w:r>` 的格式（`<w:rPr>`），把替换后的整段文本写入首 run 的 `<w:t>`，清空其余 run。
   - `ponytail:` 天花板——段落内混合格式（一段多字体）会丢失；封面槽位通常是整行/整格，影响可忽略。升级路径：按 run 边界做更细粒度替换，若日后出现混合格式槽位。
   - 表格单元格：对 cell 内每个 `<w:p>` 同上处理。
3. 把克隆的元素追加到新文档 body 开头（`doc.element.body.insert(0, cloned)` 或在首段前插入）。
4. **图片重嵌入**：对 `master["images"]` 每张图，base64 解码为字节，`doc.part.get_or_add_image_part(...)` 注册新 image part 拿新 rId，遍历克隆 XML 里的 `a:blip` 把 `r:embed` 从 `orig_rid` 重写为新 rId。
5. 封面后插分节符 → 封面独占一节、无页码（现有 `_apply_section_chrome` 的 `has_cover` 已处理 sections[0] 无 chrome，复用）。

### 6.2 槽位值解析

复用现有 `_resolve_cover_fields(api_fields, frontmatter, blocks)`（`generator.py:85`）：`title > client/project_number > date` 的 api > frontmatter > fallback 优先级。槽位 id 与其返回 key 映射：`title→title, client→client, project_number→project_number, date→date`；`project_name`/`stage` 暂从 frontmatter 取，无则保留 sample_value（即不替换）。

## 7. 编辑器交互（`LayoutTemplateEditor.tsx`「封面配置」区块）

替换现有 5 开关布局：

- **有 coverMaster**：
  - 来源行："来自样例：`{sourceFile}`" + 「重新从样例导入封面」按钮。
  - 槽位列表：每行 = 标签 / `kind` 切换（变量 ⇄ 字面）/ `sampleValue` 可编辑（显示靶文本）/ `defaultFrom` 来源提示。
- **无 coverMaster**：保留现有 5 开关简单封面（兜底）+ 醒目的「从样例导入封面」按钮。
- **预览**：v1 不做封面母版实时预览（D6）；保留"生成输出"看真实效果。

State/patch：新增 `coverMaster` state + `patchCoverMaster`/`patchSlot` 辅助（仿现有 `patchCover`）。保存时把 `coverMaster` 一并写入 onSave 载荷。

## 8. 受影响文件

**后端**
- `backend/app/extensions/output/schemas.py` — 新增 `CoverSlotSchema`/`CoverMasterSchema`；LayoutTemplate 三 schema 加 `cover_master`。
- `backend/app/extensions/output/layout_import.py` — 新增 `_extract_cover_master(doc, source_file)`；主函数组装 `cover_master`；`_detect_cover` 保留兜底或并入。
- `backend/app/extensions/output/generator.py` — 新增 `_render_cover_master(doc, master, resolved)`；`has_cover` 分支优先用母版。

**前端**
- `frontend/src/extensions/output/types.ts` — 新增 `CoverSlot`/`CoverMaster`；`LayoutTemplate.coverMaster`。
- `frontend/src/extensions/output/transforms.ts` — `transformTemplate` 加 `cover_master→coverMaster`；保存方向加反向映射。
- `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` — 重写「封面配置」区块（state + 槽位 UI + 导入按钮）。
- `frontend/src/extensions/output/api.ts` — 若保存载荷未透传 `cover_master`，补字段（实现时核实）。

**无 DB 迁移**：`template_data` 是 JSON 列。

## 9. 测试（TDD，对真实样例）

`backend/tests/test_cover_master.py`（新建）：

- **提取**：喂真实 `基地项目-消防设计专篇.docx` → 断言 `xml` 含 2 张 `<w:tbl>`、`images==[]`、`boundary=="before_toc"`、`slots` 含 `client`/`title` 等、`source_file` 正确。
- **生成 round-trip**：母版 + 样例原槽位值生成 doc → 断言封面含两张表、横幅文字一致；改 `client` 槽位值再生成 → 断言已替换、会签表未被替换（字面）。
- **边界**：
  - 有 TOC（"目录"为 Normal 样式）文档 → `boundary=="before_toc"`，封面区不含 TOC 段。
  - 无封面（body 开头即 Heading）文档 → 返回 None。
  - 带 Logo 图的文档 → `images` 非空，生成后图被嵌入、`r:embed` 重写。
- **槽位替换**：跨多 `<w:r>` 的段落替换、表格单元格替换、`literal` 槽位不替换各一例。

`frontend`：`LayoutTemplateEditor` 槽位 UI 的渲染/切换/保存载荷测试（若有前端测试惯例则补，否则手动验证）。

## 10. 风险与回退

- **边界误判**：若样例封面与正文之间没有"目录"/Heading 标志（少见），提取可能吃进正文前几段。缓解：封面区元素数/类型合理性校验（如全是正文段落而无表格 → 降级为无封面）。实现时加启发式上限。
- **槽位跨 run 替换丢格式**：已知天花板（6.2），封面场景可接受。
- **向后兼容**：`cover_template`（6 布尔）路径完整保留；新代码仅在 `cover_master` 存在时启用，回退安全。
- **图片 rId 重写**：实现时单测覆盖，避免断链。
