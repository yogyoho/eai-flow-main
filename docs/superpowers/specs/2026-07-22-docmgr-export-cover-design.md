# 文档空间 Word 导出 — 封面(cover)设计

> 状态:已批准,待实现
> 日期:2026-07-22
> 范围:`文档空间 → 我的文档 → 文档编辑页 → 导出 Word` 增加可选封面页
> 关联:`2026-07-07-output-cover-toc-numbering-design.md`(output 模块封面 helper);`2026-07-22-docmgr-export-toc-design.md`(目录,已实现)

## 1. 背景与目标

`generate_docx()`(output 模块 `/generate` 端点)已有封面能力:`_render_cover` + `cover_template`(toggle schema)+ `cover_fields`(title/client/date/project_number,优先级 API>front-matter>兜底)。但:

- docmgr 导出走 `generate_docx_simple()`,**无封面**(2026-07-07 §5.8 推迟)。
- 现有 `_render_cover` 是**固定国标式样**(LOGO 占位 + 居中标题 + 建设单位/项目编号/日期),toggle schema 只控显隐,**不能表达不同报告类型的字段+排版差异**。

**用户需求**(已确认):多报告类型,**每类一套固定封面,字段+排版都不同**(对齐/列/字号/间距),不要图片/背景/表格,不要可视化设计器。导出时选报告类型 → 套对应封面。

**目标**:docmgr 导出 Word 时,可按报告类型选封面;封面为结构化预设(数据驱动,加类型只加 config 不改代码);封面独立节无页码,正文页码从 1 重起。默认不选则无封面,保留现有行为。

## 2. 非目标(本次不做)

- 真实 LOGO 图片 / 背景图 / 表格框(封面用占位文字,同现状)。
- 封面可视化设计器 / 自由排版编辑。
- 文档元数据/报告类型字段驱动(已选「导出时选报告类型」)。
- 目录单独罗马页码节(docmgr 简化:目录与正文同节、阿拉伯从 1;封面才独立节)。
- 改动无封面导出路径(零回归)。

## 3. 架构与数据流

```
[后端:封面预设 = 唯一真相]
  app/extensions/output/cover_presets.py → COVER_PRESETS: list[dict],按报告类型
  GET /api/extensions/docmgr/cover-presets → [{id, label, fields:[{name,label,default_from?}]}]
       (前端只需 id/label/fields 画选择器+输入框;elements 布局是后端渲染用,不下发)

[前端:ExportDocxDialog 新增「封面」区]
  打开弹窗 fetch cover-presets;选报告类型 → 按 preset.fields 画值输入框
  (标题默认=文档标题,日期默认=今天 ISO)
  payload 加:cover_preset_id, cover_values:{field:value}

[后端:导出端点]
  ExportRequest/ExportContentRequest 加 cover_preset_id / cover_values
  端点按 id 查 preset(查无 → 400)→ 传给 generate_docx_simple

[后端:generate_docx_simple]
  新增 cover_preset / cover_values 形参
  有封面:[封面节 section 0,无页码] → 分节 → [目录] → 正文(节 pgNumType start=1)
  _render_cover_preset(doc, preset, values) 遍历 preset["elements"]
```

## 4. 预设 schema(封面布局 DSL)

```python
{
  "id": "fire_protection",
  "label": "消防设计专篇",
  "fields": [
    {"name": "title",          "label": "标题",     "default_from": "doc_title"},
    {"name": "client",         "label": "建设单位"},
    {"name": "project_number", "label": "项目编号"},
    {"name": "date",           "label": "日期",     "default_from": "today"},
  ],
  "elements": [
    {"type": "spacer", "lines": 3},
    {"type": "text", "field": "title", "align": "center", "font": "黑体", "size": 22, "bold": true},
    {"type": "spacer", "lines": 4},
    {"type": "info", "label": "建设单位", "field": "client", "align": "center", "font": "宋体", "size": 14},
    {"type": "info", "label": "项目编号", "field": "project_number", "align": "center", "font": "宋体", "size": 14},
    {"type": "info", "label": "日期",     "field": "date", "align": "center", "font": "宋体", "size": 14},
  ],
}
```

- **`fields`**:前端据此画输入框。`name`/`label` 必填;`default_from` 可选,取值 `doc_title`(默认=文档标题)或 `today`(默认=今日 ISO)。
- **`elements`**:布局描述。
  - `spacer`:`{"type":"spacer","lines":N}` — N 个空段落(垂直留白),恒渲染。
  - `text`:独立值行(如标题):`{"type":"text","field":X,"align","font","size","bold"}`。
  - `info`:「标签：值」行:`{"type":"info","label","field","align","font","size"}`,全角冒号「：」。
  - `align`:`left|center|right`(默认 center);`font` 默认宋体;`size` 默认 14(text 默认 16)。
- **缺值规则**:text/info 元素若 `values[field]` 为空 → **该元素整行跳过**(不显示空标签);spacer 恒渲染。沿用既有「缺值不渲染」约定。

## 5. 渲染器 `_render_cover_preset(doc, preset, values)`

- `preset` 为 None → no-op(返回)。
- 遍历 `preset["elements"]`:
  - `spacer` → `for _ in range(lines): doc.add_paragraph()`。
  - `text` → `values[field]` 有值才渲染:段落按 `align`,run 设 font/size/bold,文本=值。
  - `info` → `values[field]` 有值才渲染:段落按 `align`,run 设 font/size,文本=`f"{label}：{value}"`。
- 字体经 `_set_run_font`(同时设 eastAsia,中文正确渲染)。

## 6. 分节与页码(封面独立节,正文从 1 重起)

`generate_docx_simple` 当前单节。有封面时:

1. 页面设置仍先作用于初始节(section 0)。
2. `_render_cover_preset(doc, cover_preset, cover_values)` 渲染封面内容进 section 0。
3. `doc.add_section(WD_SECTION.NEW_PAGE)` → 新增正文节(section 1)。**页面尺寸/页边距复制自 section 0**(python-docx 新节不自动继承,需显式复制)。
4. 目录(若开)+ 正文渲染进 section 1。
5. chrome(页眉/页脚/水印,**含 PAGE 域**)挂到**正文节(section 1)**;封面节(section 0)**不挂页脚 PAGE 域 → 无页码**。
6. 复用 output 模块现成 helper `_set_section_pagenum(section, fmt="decimal", start=1)` 让正文节页码从 1 重起。
7. `header_footer`/`watermark` 块的目标由 `section` 改为「正文节」(有封面时 `doc.sections[-1]`,无封面时仍是 `doc.sections[0]`)。

**关键安全约束:无封面路径(cover_preset=None)行为一字不变**——不分节、chrome 仍挂 section 0,与今天完全一致。封面逻辑全部在 `if cover_preset:` 分支内。

> 目录+封面共存:封面=section 0(无码),目录+正文=section 1(阿拉伯从 1);目录不再单独罗马节(docmgr 简化)。

## 7. 后端端点与模型

- **新端点** `GET /api/extensions/docmgr/cover-presets`(需登录):返回 `[{"id","label","fields":[...]}]`——preset 的 trimmed 视图(不下发 elements)。
- `ExportRequest` / `ExportContentRequest` 各加:
  - `cover_preset_id: str | None = None`
  - `cover_values: dict | None = None`
- 端点逻辑:
  ```python
  cover_preset = None
  if request.cover_preset_id:
      cover_preset = get_cover_preset(request.cover_preset_id)  # 未知 id → HTTP 400
  generate_docx_simple(content, buf, template_data=..., watermark=...,
                       toc_settings=..., cover_preset=cover_preset,
                       cover_values=request.cover_values)
  ```

## 8. 前端 `ExportDocxDialog.tsx`

- 新状态:`coverPresetId`(默认 `null`=无封面)、`coverValues`(默认 `{}`)、`coverPresets`(打开弹窗时 fetch,同 templates 加载)。
- `SECTIONS` 加 `{ id: "cover", label: "封面", icon: <ImageIcon/> }`;内容区:
  - 报告类型 `Select`(选项:无 + 各 preset.label)。
  - 选中后按 `preset.fields` 渲染输入框:`default_from==="doc_title"` 预填 docTitle;`default_from==="today"` 预填今日 ISO;其余空。存入 `coverValues[name]`。
- 两 payload 分支带 `cover_preset_id: coverPresetId`、`cover_values: coverValues`;`useCallback` deps 补 `coverPresetId, coverValues`。
- 复用既有 `StyledCheckbox`/`Select`/`inputCls`/`SectionTitle`(与目录区同款)。

## 9. 错误处理

- 未知 `cover_preset_id` → HTTP 400(清晰报错,不静默无封面)。
- 字段缺值 → 该元素跳过,其余照渲;空 markdown + 封面 → 仍出封面 + 空正文。
- 封面渲染或分节抛异常 → 捕获、降级为无封面,正文照常生成(永不崩,记 warning)。
- `cover_preset` None → 无封面,无分节。
- 畸形 preset(缺 elements/未知 type)→ 跳过未知元素,不崩。

## 10. 测试(TDD,backend)

新增/扩展 `backend/tests/test_docmgr_export.py`(+ 可单独 `test_cover_presets.py`):

- `test_cover_preset_renders_fields`:带 fire_protection preset + 全值 → document.xml 含标题文本 +「建设单位：XX」+ 各值。
- `test_cover_section_page_numbering`:有封面 → section 0 无页脚 PAGE 域;正文节 sectPr `pgNumType` start=1。无封面 → 单节,行为不变。
- `test_cover_missing_value_skips_line`:某字段值缺 → 该 info 行不存在,其余在。
- `test_cover_none_unchanged`:`cover_preset=None` → 无封面内容,与今天一致(回归)。
- `test_cover_presets_endpoint`:`GET /cover-presets` 返回种子 presets,每项有 id/label/fields(无 elements)。
- `test_export_request_cover_fields`:模型接受 cover_preset_id/cover_values,默认 None。
- `test_cover_unknown_preset_400`:未知 id → 端点 400。
- `test_cover_malformed_degrades`:畸形 preset → 不崩,降级。

验证手段:`python-docx`/zipfile 重开生成 docx,断言 section/sectPr/runs 文本。

## 11. 初始预设

- **机制完全确定**;预设是 `cover_presets.py` 里的 config 条目,加类型 = 加 config,不改代码。
- **首批落地预设**:本 spec 以 **`fire_protection`(消防设计专篇)** 为唯一完整范例(2026-07-07 已有其 docx 样例)。
- 其余报告类型(环评/合同/…)在 writing-plans 阶段按用户提供的样例封面补成 config 条目;每个新增类型需用户提供一份样例封面(用于确定 fields+elements)。

## 12. 实施触及面

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/output/cover_presets.py` | **新增** — `COVER_PRESETS` 列表 + `get_cover_preset(id)`;首个范例 fire_protection |
| `backend/app/extensions/output/generator.py` | 新增 `_render_cover_preset`;`generate_docx_simple` 加 `cover_preset`/`cover_values` 形参,封面分节+页码;chrome 目标改为正文节 |
| `backend/app/extensions/docmgr/routers.py` | 新端点 `GET /cover-presets`;`ExportRequest`/`ExportContentRequest` 加 cover 字段;两调用点透传 |
| `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` | SECTIONS 加「封面」;报告类型 Select + 值输入框;payload + deps |
| `backend/tests/test_docmgr_export.py`(或新文件) | 封面渲染/分节/缺值/端点/模型/降级 用例 |

## 13. 验证(Docker)

- 后端改完:`docker compose -p eai-docker restart gateway`。
- 前端改完:`docker compose -p eai-docker restart frontend`(纯组件,未动依赖)。
- 端到端:导出 Word → 选「消防设计专篇」+ 填标题/单位/日期 → 下载,Word/WPS 打开:首页封面(标题居中黑体、建设单位/项目编号/日期、无页码),第 2 页起正文(页码从 1)。不选封面 → 与今天一致。
