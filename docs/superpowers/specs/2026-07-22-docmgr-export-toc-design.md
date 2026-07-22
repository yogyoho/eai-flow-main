# 文档空间 Word 导出 — 根据 Markdown 标题生成目录(TOC)

> 状态:已批准,待实现
> 日期:2026-07-22
> 范围:`文档空间 → 我的文档 → 文档编辑页 → 导出 Word` 增加可选目录
> 关联:`2026-07-07-output-cover-toc-numbering-design.md` §5.8(该设计推迟的"后续")

## 1. 背景与目标

文档空间的"导出 Word"调用 `generate_docx_simple()`(`backend/app/extensions/output/generator.py:1003`),目前**不生成目录**——只渲染标题/正文/公式/表格。

目录能力其实已存在于其兄弟函数 `generate_docx()`(输出模块 `/generate` 端点使用),且相关 helper 均为模块级、可直接复用:

- `_render_toc(doc, toc_settings)` — 插入原生 Word 目录域 `TOC \o "1-N" \h \z \u` + 居中"目录"标题
- `_set_update_fields(doc)` — 写 `<w:updateFields w:val="true"/>`,使 Word/WPS 打开时自动更新目录页码
- `parse_markdown()` 已把 markdown 的 `#`/`##`/`###` 解析为标题层级

关键点:`generate_docx_simple` 用 `doc.add_heading(level=level)` 渲染标题(generator.py:1060),套用 Word 内置 `Heading 1/2/3` 样式;目录域正是靠收集这些样式生成。故 markdown 标题结构可直接映射为 Word 目录,无需改动标题渲染逻辑。

该功能在 `2026-07-07-output-cover-toc-numbering-design.md` §5.8 被刻意推迟(原文:"本次不暴露到 docmgr 的导出 API(留作后续)")。本设计即完成该"后续"。

**目标**:文档空间导出 Word 时,可按需生成基于 markdown 标题层级的目录,默认关闭,保留现有导出行为。

## 2. 非目标(本次不做)

- **封面页(cover)**——用户已确认**后续单独设计**(独立任务)。
- 标题自动编号(`1 / 1.1 / 1.1.1`,output 模块另有 `_compute_heading_numbers`)。
- 多节罗马/阿拉伯页码。
- `GET /documents/{doc_id}/export`(简易下载端点,导出弹窗不使用)。

## 3. UX

导出弹窗(`frontend/src/extensions/docmgr/ExportDocxDialog.tsx`)的导出设置区新增:

- 「包含目录」勾选框,默认**未勾选**(保留现有行为)。
- 勾选后展开「收录到几级标题」下拉,选项 `1 / 2 / 3 / 4`,默认 `3`;未勾选时下拉禁用。

## 4. 方案

复用 `generate_docx` 的目录 helper,给 `generate_docx_simple` 增加可选目录。三处改动:生成器、导出端点、导出弹窗。

### 4.1 `generate_docx_simple`(generator.py:1003)

签名增加 `toc_settings: dict | None = None`:

```python
def generate_docx_simple(
    markdown_content: str,
    buf,
    template_data: dict | None = None,
    watermark: str | None = None,
    toc_settings: dict | None = None,
) -> None:
```

逻辑:

- 页面设置之后、正文循环之前:若 `toc_settings` 且 `maxDepth > 0`,调用 `_render_toc(doc, toc_settings)`,随后 `doc.add_page_break()`(正文从新页开始)。
- `doc.save(buf)` 之前:若已渲染目录,调用 `_set_update_fields(doc)`。

`_render_toc` / `_set_update_fields` 均为 generator.py 内既有模块级函数,直接调用即可。

### 4.2 docmgr 导出端点(`backend/app/extensions/docmgr/routers.py`)

`ExportRequest`(line 277)与 `ExportContentRequest`(line 330)各增加两个字段:

```python
with_toc: bool = False
toc_depth: int = 3
```

两处调用点(line 322、line 372)构造并透传:

```python
toc_settings = {"maxDepth": request.toc_depth} if request.with_toc else None
generate_docx_simple(
    content, buf,
    template_data=request.layout_template,
    watermark=request.watermark,
    toc_settings=toc_settings,
)
```

### 4.3 前端 `ExportDocxDialog.tsx`

- 新增状态:`withToc`(默认 `false`)、`tocDepth`(默认 `3`)。
- UI:在导出设置区加「包含目录」勾选框;勾选后展开深度下拉(`1/2/3/4`,默认 3);未勾选时下拉禁用。
- `handleExport` 的两个 payload 分支(line 457-469)均带上 `with_toc: withToc`、`toc_depth: tocDepth`。
- `useCallback` 依赖数组补充 `withToc, tocDepth`。

## 5. 行为与边界

- 目录层级直接来自 markdown `#`/`##`/`###`;`generate_docx_simple` 已把标题级 cap 在 4(`min(block.level, 4)`,generator.py:1058),故深度选项上限给到 4。
- 目录为 Word **域**:Word/WPS 打开时自动更新页码(靠 `updateFields`);少数不更新域的预览器(如部分在线预览)会显示占位提示"打开文档后右键更新域"——域式目录固有表现,非缺陷。
- 文档无标题时:仍按用户勾选插入目录(用户自决),不做自动跳过分支(少一个分支)。

## 6. 错误处理(沿用 `2026-07-07` 设计 §6 约定)

- `toc_settings` 为 None 或 `maxDepth ≤ 0` → 跳过目录节。
- 域注入失败 → 跳过目录节,正文照常生成。
- 生成**永不因目录崩溃**:正文始终产出。

## 7. 测试(TDD,backend 强制)

扩展 `backend/tests/test_docmgr_export.py`:

- `with_toc=True, toc_depth=3` → 生成 docx 的 `document.xml` 含 `TOC \o "1-3"`、`settings.xml` 含 `updateFields val="true"`。
- `with_toc=False`(默认)→ 两者均不含。
- 直接对 `generate_docx_simple(..., toc_settings={"maxDepth": 2})` 做单元断言 `TOC \o "1-2"`(绕过 HTTP,聚焦生成器)。

验证手段沿用既有测试:用 `python-docx` / zipfile 重新打开生成的 docx,断言域 XML 与 `settings.xml`。

## 8. 实施触及面

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/output/generator.py` | `generate_docx_simple` 加 `toc_settings` 形参;条件渲染 `_render_toc` + 分页 + `_set_update_fields` |
| `backend/app/extensions/docmgr/routers.py` | `ExportRequest` / `ExportContentRequest` 加 `with_toc` / `toc_depth`;两调用点透传 `toc_settings` |
| `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` | 加「包含目录」勾选框 + 深度下拉;两 payload 分支带 `with_toc` / `toc_depth` |
| `backend/tests/test_docmgr_export.py` | 新增 TOC 断言用例 |

## 9. 验证(Docker 环境)

- 后端改完:`docker compose -p eai-docker restart gateway`。
- 前端改完:`docker compose -p eai-docker restart frontend`(纯组件改动,未动依赖,无需 rebuild)。
- 端到端:文档编辑页导出 Word,勾选「包含目录」,下载后用 Word/WPS 打开确认目录自动生成且页码正确。

## 10. 后续

- **封面页(cover)设计**——用户已确认为下一步独立任务(单独 spec)。
- 标题自动编号——如需要,复用 output 模块 `_compute_heading_numbers`,可单独迭代。
