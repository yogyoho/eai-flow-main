# Output 模块:封面 + 目录 + 标题自动编号 设计

- **日期**:2026-07-07
- **分支**:main-dev-fork
- **状态**:设计稿(待用户复核 → 转 writing-plans)
- **范围**:`backend/app/extensions/output/` 的 DOCX 生成器补齐封面、目录、标题自动编号
- **关联**:`docs/superpowers/plans/2026-06-03-layout-template-system.md`(原 layout-template 系统);`backend/app/extensions/output/seed.py`(已新增「消防设计专篇」内置模板)

---

## 1. 背景与问题

`output` 模块的**数据模型/Schema/种子模板早已声明**封面(`cover_template`)与目录(`toc_settings`),但**生成层从未消费**:

- `generator.py`(558 行)全文无 `cover_template` / `toc_settings` / `add_page_break` / TOC 域代码——零渲染。
- `routers.py:150-159` 组装 `template_data` 时**主动丢弃**了 `cover_template` 和 `toc_settings`(只传 page/body/heading/table/header_footer/reference/appendix)。

结果:用任意模板生成 Word,只有正文样式生效,**没有封面、没有目录**;`heading_styles[].numbering="decimal"` 配了也不生效(标题无自动编号)。这是"spec 设计了但实现没跟上"的典型缺口。

`docmgr` 协同编辑器的"导出 Word"走同一个 `generator.py::generate_docx_simple`,同样缺封面/目录。

## 2. 真实样例印证

解析客户样例 `基地项目-消防设计专篇.docx`(吉林院,75KB)得出:

| 维度 | 实测 | 印证的设计决策 |
|---|---|---|
| 页面 | A4 纵向,上下 2.54cm / 左右 3.17cm | 与"环评报告国标"种子一致 |
| 分节(共 6 节) | 封面段(无页码)→ 目录段(`upperRoman` 从 Ⅰ)→ 正文段(`decimal` 从 1)→ 一节横向(landscape) | 多节页码方案 |
| 目录域 | 原生 `TOC \o "1-2" \h \z \u`,`updateFields=False` | 原生域方案 ✓ |
| 标题编号 | `1` / `1.1` / `4.2.1`,`numbering.xml` 不存在——数字直接写在标题文本里 | 预计算前缀(方案 A)✓ |
| 封面 | **样例无封面**(直接从"目 录"开始,属"第三册"正文) | 封面按国标惯例做,不能照抄 |

**结论**:样例完美印证了"多节页码 + 原生 TOC 域 + 标题文本前缀编号"三个核心方案。封面因样例缺失,按国标惯例实现。

## 3. 目标 / 非目标

### 目标
1. 生成 Word 时,按模板 `cover_template` 渲染**封面页**(独立分节,无页眉页脚页码)。
2. 按模板 `toc_settings` 渲染**目录页**(原生 Word TOC 域,打开自动回填页码)。
3. 按 `heading_styles[].numbering=="decimal"` 给各级标题**自动编号**(数字前缀到标题文本)。
4. 多节页码:封面无码 → 目录罗马(Ⅰ Ⅱ)→ 正文阿拉伯从 1 重起。
5. 顺带修复 `/generate` 路径中文 eastAsia 字体不生效的既有 bug。

### 非目标(本次不做)
- `source=project` 的 TODO 桩(按项目生成报告从 DB 取章节)——单独议题。
- 图题编号(`figure_styles`)、参考文献(`reference_style`)、附录(`appendix_rules`)的渲染——后续。
- 封面 LOGO 图片上传——本次用占位文字。
- docmgr 快导默认带封面/目录——保持现状(单文档快导),仅复用 helper 并留开关。

## 4. 关键决策(已与用户确认)

1. **范围**:封面 + 目录 + 标题自动编号。
2. **目录**:原生 Word TOC 域 + `settings.xml` 写 `updateFields=true`(Word/WPS 打开自动回填真实页码,与正文同步)。已知代价:服务端预览(无渲染器)里目录显示为空/占位——用户接受。
3. **封面数据源(混合)**:API 表单字段 > markdown front-matter > 兜底(标题=首个 H1,日期=今日 ISO)。
4. **标题编号方案 A(预计算前缀)**:生成器算出 `1 / 1.1 / 1.1.1` 拼到标题文本前。与原生 TOC 域天然契合(目录直接显示带编号的标题文本),确定性高,实现简单。放弃方案 B(Word 原生多级列表 numbering.xml)——python-docx 对多级列表支持极差,且"编辑后自动重排"对一次性生成的报告是伪需求。

## 5. 设计

### 5.1 架构与数据流

```
POST /api/extensions/output/generate
  Form: source, layout_template_id, watermark,
        cover_title?, cover_client?, cover_date?, cover_project_number?,   ← 新增
        (现有: project_id, chapter_ids, content, file, format)
   │
   ├─ 取 template → 组装 template_data
   │     ✅ 补传 cover_template / toc_settings(现在被丢弃)
   ├─ 取 markdown(project | markdown/file/content)
   ├─ cover_fields = {非 None 的 cover_* 表单字段}                       ← 新增
   └─ generate_docx(md, template_data, output_path, watermark, cover_fields)  ← 新增形参
         │
         ├─ _split_frontmatter(md) → (frontmatter_dict, body_md)          ← 新增
         ├─ 解析 body_md → blocks
         ├─ 解析封面值:cover_fields(API) > frontmatter > 兜底            ← 新增
         ├─ [section 0] _render_cover(...)  封面(独立节,无页码)        ← 新增
         ├─ doc.add_section(NEW_PAGE)
         ├─ [section 1] _render_toc(...)     目录(原生域,罗马页码)     ← 新增
         ├─ doc.add_section(NEW_PAGE)
         ├─ [section 2] 正文(阿拉伯页码从 1 重起)
         │     ├─ _compute_heading_numbers(blocks) 前缀编号              ← 新增
         │     └─ 渲染 blocks(现有逻辑,改用 _set_run_font 修 CJK)
         └─ _set_update_fields(doc)  settings.xml 写 updateFields=true   ← 新增
```

**关键修复**:`routers.py:150` 的 `template_data` 必须补 `cover_template` 和 `toc_settings`,否则后续一切白搭。

### 5.2 封面页(`_render_cover`)

国标式样(样例无封面,按惯例):

```
┌─────────────────────────────────┐
│        [编制单位 LOGO]           │  showLogo (logoPosition: center|left)
│                                 │
│                                 │
│        ××项目消防设计专篇        │  showTitle(二号黑体居中,值取封面标题)
│                                 │
│                                 │
│   建 设 单 位：××公司            │  showClient
│   编 制 单 位：××院              │  (固定 label "编制单位")
│   项 目 编 号：××××              │  showProjectNumber
│   二〇二六年七月                 │  showDate
│                                 │
└─────────────────────────────────┘
        → add_section(NEW_PAGE) 进目录
```

- 每个字段由 `cover_template.showXxx` 开关控制显隐(沿用已存在 schema)。
- 值优先级:`cover_fields`(API/front-matter 合并后)> 兜底。**任一字段缺值则该行整行不渲染**(不显示空 label)。
- 封面节(section 0)关闭页眉页脚与页码(footer 不挂 PAGE 域)。
- 标题居中黑体二号;建设单位等行用黑体/宋体小四,左对齐或居中。
- LOGO 本次用占位文字 `[编制单位 LOGO]`(showLogo=true 时),真图片上传后续做。

### 5.3 目录(`_render_toc`)

- 目录节(section 1)先放"目 录"标题(黑体居中),再放 TOC 域。
- TOC 域(注入 OOXML):
  ```xml
  <w:p>
    <w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>
    <w:r><w:instrText xml:space="preserve"> TOC \o "1-{maxDepth}" \h \z \u </w:instrText></w:r>
    <w:r><w:fldChar w:fldCharType="separate"/></w:r>
    <w:r><w:t>（打开文档后右键“更新域”生成目录）</w:t></w:r>
    <w:r><w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
  ```
  `maxDepth` 取自 `toc_settings.maxDepth`(消防模板为 2)。
- `_set_update_fields(doc)`:`doc.settings.element` 追加 `<w:updateFields w:val="true"/>`,Word/WPS 打开时自动回填页码。
- **目录与编号衔接**:编号前缀到标题文本(方案 A),TOC 域直接显示 `"1.1 总论 … 12"`,无需额外处理。
- 目录节页码:`w:pgNumType w:fmt="upperRoman" w:start="1"`,footer 挂 PAGE 域(显示 Ⅰ Ⅱ)。
- `toc_settings` 为 None 或 maxDepth≤0 → 跳过整个目录节,封面后直接进正文。

### 5.4 标题自动编号(`_compute_heading_numbers`)

- 维护计数器栈 `[c1, c2, c3, c4]`。遇到 H(n)(n∈1..4):栈截到 n 位,`stack[n-1] += 1`,编号 = `".".join(stack[:n])`,如 `1` / `1.1` / `4.2.1`。
- 仅当 `heading_styles[level].numbering == "decimal"` 时前缀;`"none"`(如"通用A4报告")不加。
- 编号拼到 `add_heading` 的文本前(`f"{number} {text}"`),同时写进 run;正文与目录一致。
- markdown 里若标题文本已带数字前缀(如手写 `"1.1 总论"`),去重逻辑:**本次不去重**,约定生成端 markdown 用裸标题,编号由模板加(在实施计划里加一条校验/告警)。

### 5.5 多节页码结构

| 节 | 内容 | 页码格式 | 页脚 PAGE 域 |
|---|---|---|---|
| 0 | 封面 | 无 | 不挂 |
| 1 | 目录 | `upperRoman` 从 Ⅰ | 挂(显示 Ⅰ Ⅱ) |
| 2 | 正文 | `decimal` 从 1 重起 | 挂(显示 1 2) |

实现:每个节用 `section._sectPr` 找/建 `w:pgNumType` 设 `fmt`/`start`;footer 用现有 PAGE 域注入法(generator.py 已有)。

### 5.6 API / Schema 改动

**`routers.py::generate_report`**:
- 新增 Optional Form 参数:`cover_title` / `cover_client` / `cover_date` / `cover_project_number`。
- `template_data` 补 `cover_template`、`toc_settings`。
- `cover_fields = {"title": cover_title, "client": cover_client, "date": cover_date, "project_number": cover_project_number}`,丢 None 键,传入 `generate_docx`。

**`generator.py::generate_docx`**:新增形参 `cover_fields: dict | None = None`。

**`schemas.py`**:不改。封面"值"是每次生成的 API 参数,非模板字段;`CoverTemplateSchema`/`TocSettingsSchema` 的开关 schema 已存在。

**Front-matter 契约**(供报告 skill 输出 markdown 时携带):
```yaml
---
title: ××项目消防设计专篇
client: ××建设公司
date: 2026-07
project_number: XX-2026-001
---
# 总论
...
```
解析仅支持 `key: value` 行(不引入完整 YAML 依赖, ponytail:够用即可)。

### 5.7 顺带修复:`/generate` 路径 CJK 字体

`generate_docx`(模板路径)给标题/正文设字体只调 `run.font.name`(设 `w:ascii`/`w:hAnsi`),**未设 `w:eastAsia`** → 中文不按黑体/宋体渲染。`generate_docx_simple` 里已有正确的 `_set_run_font(run, name)`(同时设 eastAsia)。本次把 `generate_docx` 内所有 `run.font.name = _resolve_font(...)` 换成 `_set_run_font(run, _resolve_font(...))`。

### 5.8 docmgr 导出路径(`generate_docx_simple`)

默认**不变**(单文档快导,无封面无目录)。封面/目录 helper 提取为模块级函数,`generate_docx_simple` 增加可选 `with_cover: bool = False`;仅当显式传 `with_cover=True` 且模板有 `cover_template` 时才渲染封面/目录。本次不暴露到 docmgr 的导出 API(留作后续)。

## 6. 错误处理

生成**永不因封面/目录崩溃**:
- front-matter 解析失败(无结束 `---`、非 `key: value`)→ 当正文处理,不崩。
- 封面字段缺值 → 该行跳过(不显示空 label)。
- `toc_settings` 为 None 或 maxDepth≤0 → 跳过目录节。
- 封面渲染抛异常 → 捕获、降级为无封面,正文照常生成(记 warning)。
- 空 markdown → 仍产出封面 + (可选)目录 + 空正文,不崩。
- TOC 域注入失败 → 跳过目录节,正文照出。

## 7. 测试(TDD,backend 强制)

新增 `backend/tests/`:
- `test_output_generator_frontmatter.py` — 正常 YAML front-matter 提取;无 front-matter → 空 dict + 原文;畸形(无结束符/非 k:v)→ 忽略不崩。
- `test_output_generator_cover.py` — 按 `showXxx` 开关渲染对应行;缺值的行跳过;封面位于 section 0;封面节 footer 无 PAGE 域;`_render_cover` 异常 → 降级不抛。
- `test_output_generator_toc.py` — 生成的 docx `document.xml` 含 `TOC \o "1-{maxDepth}"`;`settings.xml` 含 `updateFields val="true"`;maxDepth=2/3/0 各情形;`toc_settings=None` → 无目录节。
- `test_output_generator_numbering.py` — 编号 `1` / `1.1` / `1.1.1` 正确;H1 前进时 H2/H3 清零;`numbering="none"` → 无前缀;编号拼进标题文本。
- `test_output_generator_section_pagenum.py` — 三节 pgNumType:section0 无、section1 upperRoman start1、section2 decimal start1。
- `test_output_generator_cjk_font.py` — `generate_docx` 渲染的标题/正文 run 的 `w:rFonts` 含 `w:eastAsia`(回归 CJK 修复)。
- `test_output_seed.py` — per-id upsert:已有内置时,新 builtin 只补缺的、不动已有(回归本次 seed.py 改动)。
- `test_output_generate_endpoint.py`(router 级,service mock)— POST /generate 带 cover_* + 带 `cover_template` 的模板 → 返回 completed;template_data 含 cover_template/toc_settings(用 spy/mock 断言传入 generate_docx 的参数)。

验证手段:测试用 `python-docx` 重新打开生成的 docx(写临时文件或 BytesIO),断言 sectPr/pgNumType/域 XML/runs。CJK 断言直接读 run 的 `w:rPr/w:rFonts@w:eastAsia`。

## 8. 实施触及面

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/output/generator.py` | 新增 `_split_frontmatter` / `_render_cover` / `_render_toc` / `_compute_heading_numbers` / `_set_update_fields`;`generate_docx` 加 `cover_fields` 形参并串三个节;CJK `_set_run_font` 统一;`generate_docx_simple` 加 `with_cover` 开关复用 helper |
| `backend/app/extensions/output/routers.py` | `/generate` 加 4 个 cover_* Form 参数;`template_data` 补 cover_template/toc_settings;组装 cover_fields 传入 |
| `backend/app/extensions/output/seed.py` | ✅ 已改(per-id upsert + 消防模板) |
| `backend/tests/test_output_*.py` | 新增上述测试文件 |

无 DB schema 变更(`LayoutTemplate` 的 `cover_template`/`toc_settings` JSONB 列早已存在)。无前端必改(前端模板编辑器已能配封面/目录开关);后续可加封面预览,本次不做。

## 9. 验收标准

- 选「消防设计专篇」模板 + 给定 markdown → 生成的 docx:
  - 第 1 节为封面(标题/建设单位/编制单位/项目编号/日期,按开关与值渲染),无页码。
  - 第 2 节为目录,Word/WPS 打开自动出真实页码,条目带 `1 / 1.1` 编号,页码 Ⅰ Ⅱ。
  - 第 3 节起正文,标题带 `1` / `1.1` / `1.1.1` 编号,页码从 1 重起。
  - 中文按黑体/宋体渲染(eastAsia 生效)。
- 所有新增测试通过;`make lint`、`make test` 绿。
- 现有 4 个内置模板 + 消防模板生成行为不回归(无 cover_template 的模板如"通用A4"→ 无封面无目录,行为不变)。

## 10. 已完成的前置项

- `seed.py` 已新增「消防设计专篇」内置模板(id `…000000000005`,`report_type=fire_protection`,maxDepth=2,黑体递减标题 + decimal 编号),并把 `seed_builtin_templates` 改为 per-id upsert。已 psql 验证落库。**该模板的封面/目录字段在本次 feature 上线前仍被生成器忽略——feature 上线即全功能。**

## 11. 待定 / 后续

- 封面 LOGO 真图片上传(本次占位文字)。
- docmgr 导出默认带封面/目录的开关 UI。
- `source=project` 按项目章节生成(单独议题)。
- 图题/参考文献/附录渲染。
- 标题文本已含手写编号时的去重告警。
