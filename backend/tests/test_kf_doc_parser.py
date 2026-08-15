"""Unit tests for doc_parser — heading detection, text normalization, regex fallback.

These tests run without external services (no RAGFlow, no DB).
They verify the core parsing logic with inline test data.
"""

from app.extensions.knowledge_factory.doc_parser import (
    _TOC_ENTRY,
    DocTable,
    Heading,
    ParsedDocument,
    _is_noise_line,
    _scan_headings_regex,
    normalize_text,
)

# ── normalize_text ──


def test_normalize_removes_punctuation_and_spaces():
    # normalize_text strips Chinese stop words and spaces, but preserves
    # structural dots (used in chapter numbering). Same heading format
    # with different whitespace normalizes to the same string.
    assert normalize_text("1 总则") == normalize_text("1总则")
    assert normalize_text("一、 概述") == normalize_text("一概述")
    # Dot is structural (distinguishes "1.1" from "11"), intentionally preserved
    assert "." in normalize_text("1.1 任务由来")


def test_normalize_case_insensitive():
    assert normalize_text("ABC") == normalize_text("abc")


def test_normalize_chinese_stop_words():
    """的、，。；：（） should be stripped."""
    result = normalize_text("第一章 的 概述，内容")
    assert "的" not in result
    assert "，" not in result


# ── _scan_headings_regex ──


def test_regex_detects_numbered_chapters():
    text = """1. 总则
1.1 任务由来
2. 建设项目概况
3. 工程分析
14. 结论与建议"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    assert "1. 总则" in titles
    assert "2. 建设项目概况" in titles
    assert "14. 结论与建议" in titles


def test_regex_levels_correct():
    text = """1. 总则
1.1 任务由来
1.1.1 评价目的
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    by_title = {h.title: h.level for h in headings}
    assert by_title["1. 总则"] == 1
    assert by_title["1.1 任务由来"] == 2
    assert by_title["1.1.1 评价目的"] == 3
    assert by_title["2. 建设项目概况"] == 1


def test_regex_chinese_chapter_patterns():
    text = """第一章 总则
第一节 任务由来
（一）评价范围
一、概述"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    assert "第一章 总则" in titles


def test_regex_deduplicates():
    """Repeated titles (page headers) should be deduplicated."""
    text = """1. 总则
1. 总则
1. 总则
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    assert len(headings) == 2


def test_regex_skips_toc_entries():
    """TOC lines ending with page numbers should be skipped."""
    text = """1. 总则\t3
1.1 任务由来     5
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    # TOC entries skipped, only real heading remains
    assert "2. 建设项目概况" in titles
    assert len(headings) == 1


# ── _is_noise_line ──


def test_noise_detects_survey_items():
    assert _is_noise_line("1、您了解本项目的环境影响吗？") is True
    assert _is_noise_line("2、噪声：合理布局，噪声高的设备需要采用低噪声设备并进行减振处理") is True


def test_noise_passes_real_headings():
    assert _is_noise_line("1. 总则") is False
    assert _is_noise_line("2. 建设项目概况") is False
    assert _is_noise_line("第一章 总则") is False


# ── TOC detection ──


def test_toc_detects_page_numbers():
    assert _TOC_ENTRY.match("1. 总则\t3") is not None
    assert _TOC_ENTRY.match("1.1 任务由来     5") is not None


def test_toc_ignores_normal_headings():
    assert _TOC_ENTRY.match("1. 总则") is None
    assert _TOC_ENTRY.match("2. 建设项目概况") is None


# ── Heading dataclass ──


def test_heading_fields():
    h = Heading(title="1. 总则", level=1, line_number=5, style_name="Heading 1")
    assert h.level == 1
    assert h.title == "1. 总则"


# ── DocTable dataclass ──


def test_doc_table_fields():
    t = DocTable(
        caption="表 1-1 监测点位",
        columns=["编号", "经度", "纬度"],
        rows=[["1#", "120.5", "30.2"]],
    )
    assert len(t.columns) == 3
    assert len(t.rows) == 1


# ── ParsedDocument dataclass ──


def test_parsed_document_empty():
    doc = ParsedDocument(file_path="/tmp/test.docx", file_type="docx")
    assert doc.headings == []
    assert doc.tables == []
    assert doc.full_text == ""


def test_parsed_document_error():
    doc = ParsedDocument(file_path="/tmp/bad.pdf", file_type="pdf", error="PDF 无可提取文字")
    assert doc.error != ""
    assert doc.error == "PDF 无可提取文字"


# ── Grounding: 精确章节切片 ──


def test_finalize_sections_exact_slice():
    """finalize_sections 算 text_offset，section_text_by_title subtree 含子节。"""
    paragraphs = ["1 总则", "本章节介绍项目背景。", "1.1 任务由来", "任务由来说明。", "2 工程分析", "工艺流程内容。"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 任务由来", level=2, para_idx=2),
        Heading(title="2 工程分析", level=1, para_idx=4),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    # H1 "1 总则" subtree 到下一个 H1，含子节 1.1
    assert "任务由来说明" in doc.section_text_by_title("1 总则", level=1)
    assert "工艺流程" not in doc.section_text_by_title("1 总则", level=1)
    # H2 "1.1" 叶子切片
    h2_text = doc.section_text_by_title("1.1 任务由来", level=2)
    assert "任务由来说明" in h2_text
    assert "1 总则" not in h2_text


def test_section_text_by_title_normalizes_spaces():
    """标题带多余空格时，normalize 后仍能匹配到精确切片。"""
    paragraphs = ["1 总  则", "总则正文内容。", "2 概述", "概述内容。"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="1 总  则", level=1, para_idx=0), Heading(title="2 概述", level=1, para_idx=2)]
    doc.finalize_sections(paragraphs)
    doc.full_text = "\n\n".join(paragraphs)
    text = doc.section_text_by_title("1 总则", level=1)
    assert "总则正文内容" in text


def test_section_text_by_title_empty_when_regex_fallback():
    """regex 兜底的 heading 无 para_idx（text_offset=-1），返回空串让调用方回退。"""
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="第一章 总则", level=1, para_idx=-1)]
    doc.full_text = "第一章 总则 正文"
    assert doc.section_text_by_title("第一章 总则") == ""


# ── section_length (min_section_length 过滤支撑) ──


def test_section_length_subtree():
    """section_length 返回 heading 子树字符长度（含子节）。"""
    paragraphs = ["1 总则", "正文A较长内容。" * 10, "2 概述", "短"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="1 总则", level=1, para_idx=0), Heading(title="2 概述", level=1, para_idx=2)]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    # H1 "1 总则" 子树到 H1 "2 概述"，应较长
    assert doc.section_length(0) > 50
    # H1 "2 概述" 到文末，较短
    assert doc.section_length(1) < 10


def test_section_length_no_anchor_returns_zero():
    """无锚点的 heading（regex 兜底）返回 0，调用方保留不过滤。"""
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="第一章", level=1, para_idx=-1, text_offset=-1)]
    doc.full_text = "正文"
    assert doc.section_length(0) == 0


# ── 表格展平进全文 (bug-1120): Step 2 LLM 必须看到真实表行列 ──


def test_expat_flattens_table_into_full_text(tmp_path):
    """w:tbl 的单元格文本必须进入 full_text（带 | 前缀标记）。

    回归 bug-1120：data() 曾把 w:tc 文本进 cell_buf 而非 cur_text，导致
    full_text/section_text_by_title 不含表格内容 → Step 2 LLM 看不到表，
    table_schemas 列定义全靠猜。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>1 监测点位</w:t></w:r></w:p>'
        "<w:tbl>"
        "<w:tr><w:tc><w:p><w:r><w:t>序号</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>点位名称</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>类型</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>矿区边界</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>有组织</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
        "</w:document>"
    ).encode()
    fp = tmp_path / "t.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None
    # 表结构照旧提取
    assert len(r.tables) == 1
    assert r.tables[0].columns == ["序号", "点位名称", "类型"]
    # 表行列已展平进全文
    assert "| 序号 | 点位名称 | 类型" in r.full_text
    assert "| 1 | 矿区边界 | 有组织" in r.full_text
    assert "【表格】" in r.full_text and "【表格结束】" in r.full_text


def test_expat_flattened_table_lands_in_section_slice(tmp_path):
    """展平后的表格行必须落入所在章节的 section_text_by_title 切片。

    这是 bug-1120 的端到端判据：Step 2 _enrich 用 section_text_by_title
    取章节内容，若表格行不进切片则 LLM 仍看不到表。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>1 监测点位</w:t></w:r></w:p>'
        "<w:tbl>"
        "<w:tr><w:tc><w:p><w:r><w:t>序号</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>点位名称</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>矿区边界</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>2 工程分析</w:t></w:r></w:p>'
        "</w:document>"
    ).encode()
    fp = tmp_path / "t2.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None
    sec1 = r.section_text_by_title("1 监测点位", level=1)
    # 表格数据必须进入章节 1 的切片
    assert "矿区边界" in sec1, f"表格行应进章节切片, 得: {sec1[:300]}"
    # 不越界进下一章
    sec2 = r.section_text_by_title("2 工程分析", level=1)
    assert "矿区边界" not in sec2


def test_expat_table_pipe_in_cell_does_not_split(tmp_path):
    """单元格内含 '|' 时替换为全角 '｜'，防止列边界歧义。"""
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:tbl><w:tr><w:tc><w:p><w:r><w:t>甲|乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:document>').encode()
    fp = tmp_path / "pipe.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None
    assert "甲｜乙" in r.full_text
    assert "甲|乙" not in r.full_text


def test_expat_table_rows_not_detected_as_headings(tmp_path):
    """| 前缀表格行不能被 _scan_headings_regex 误判为章节标题。

    bug-1120 设计约束：标题 pattern 锚定行首数字/汉字序号，| 开头行不命中。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>矿区边界</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:document>"
    ).encode()
    fp = tmp_path / "h.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    # 表格行 "| 1 | 矿区边界" 即使数字开头 + | 前缀，也不得成为 heading
    assert r is not None and r.headings == []


# ── expat handler: 真实命名空间 docx ──


def test_expat_extracts_namespaced_docx(tmp_path):
    """expat 必须从带 xmlns:w 命名空间的真实 Word XML 提取标题/表格。

    回归: namespace_separator=':' 曾导致 name 变 URI 形式，name=='p' 失效，
    expat 返回空，静默回退 python-docx。此测试用真实命名空间 docx 覆盖。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>正文</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>c1</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>c2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:document>"
    ).encode()
    fp = tmp_path / "t.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None
    assert len(r.headings) == 1, f"expat 应提取 H1，得 {len(r.headings)}（namespace 比较可能失效）"
    assert r.headings[0].level == 1
    assert len(r.tables) == 1
    assert r.tables[0].columns == ["c1", "c2"]


def test_expat_gridspan_horizontal_merge(tmp_path):
    """gridSpan 水平合并：跨列 cell 内容复制对齐列数。"""
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:tbl><w:tr>"
        b'<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>merged</w:t></w:r></w:p></w:tc>'
        b"<w:tc><w:p><w:r><w:t>c3</w:t></w:r></w:p></w:tc>"
        b"</w:tr></w:tbl></w:document>"
    )
    fp = tmp_path / "g.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None and len(r.tables) == 1
    cols = r.tables[0].columns
    assert len(cols) == 3, f"gridSpan=2 应展开成3列，得 {len(cols)}: {cols}"
    assert cols[0] == "merged" and cols[1] == "merged"


def test_expat_vmerge_vertical(tmp_path):
    """vMerge 垂直合并：continue 行继承上一行同列文本。"""
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:tbl>"
        b'<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>top</w:t></w:r></w:p></w:tc>'
        b"<w:tc><w:p><w:r><w:t>r1c2</w:t></w:r></w:p></w:tc></w:tr>"
        b"<w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p><w:r><w:t>ignored</w:t></w:r></w:p></w:tc>"
        b"<w:tc><w:p><w:r><w:t>r2c2</w:t></w:r></w:p></w:tc></w:tr>"
        b"</w:tbl></w:document>"
    )
    fp = tmp_path / "v.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None and len(r.tables) == 1
    # row2 的 vMerge continue cell 应继承 row1 的 "top"，忽略自身 "ignored"
    assert r.tables[0].rows[0][0] == "top", f"vMerge continue 应继承上一行，得 {r.tables[0].rows[0][0]}"
    assert r.tables[0].rows[0][1] == "r2c2"


# ── body-text guard: 样式法把正文段误读成 heading 的守卫 (bug-404) ──


def test_looks_like_body_text_rejects_clause_punctuation():
    """真标题是名词短语，不含子句/句末标点（，。；！？）；含则一定是被误套了
    标题样式的正文段。顿号 、 可在真标题里作连词，故不判定为正文。"""
    from app.extensions.knowledge_factory.doc_parser import _looks_like_body_text

    # 3218 掘进作业规程里被误判为章节的真实正文段（全部含子句标点）
    assert _looks_like_body_text("2、掘进中涉及的开口、拐弯时，需对开口处及其左右两侧各不小于5000mm范围内的顶板进行锚索补强") is True
    assert _looks_like_body_text("（4）遇顶板巷帮岩体破碎、巷道成型差时，顶板支护时，根据现场实际情况") is True
    assert _looks_like_body_text("②掘进巷道回风流甲烷传感器处安设1路摄像仪，监视回风流甲烷传感器的运行情况。") is True
    assert _looks_like_body_text("26、对应力集中区（向斜和背斜轴部）用锚杆钻机探测一次顶板岩性，并增加一组") is True
    assert _looks_like_body_text("8、工作面积水、巷中积水严禁上输送机，生产过程中开机开水") is True
    # 真章节标题（名词短语，无子句标点）
    assert _looks_like_body_text("概况") is False
    assert _looks_like_body_text("巷道布置及支护说明") is False
    assert _looks_like_body_text("施工工艺") is False
    assert _looks_like_body_text("灾害应急措施及避灾路线") is False
    assert _looks_like_body_text("第一章 总则") is False
    # 顿号在真标题里作连词，不算子句标点
    assert _looks_like_body_text("设计、施工及验收") is False


def test_expat_skips_body_paragraph_with_heading_style(tmp_path):
    """正文段被套了 Heading1 样式但含子句标点 → 守卫应过滤掉，不识别为 heading。

    回归 3218.docx：作者把"2、掘进中…，需对…补强"等正文段也标成了 chapter
    样式（styleId '2'/outlineLvl 0），样式法曾忠实读成 H1，污染章节结构。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat

    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        # 真章节（名词短语，无标点）
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>概况</w:t></w:r></w:p>'
        # 正文段被误套 Heading1（含逗号）—— 应被守卫过滤
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>2、掘进中涉及的开口，需对顶板补强</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>施工工艺</w:t></w:r></w:p>'
        "</w:document>"
    ).encode()
    fp = tmp_path / "body.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    titles = [h.title for h in r.headings]
    assert "概况" in titles and "施工工艺" in titles
    assert "2、掘进中涉及的开口，需对顶板补强" not in titles, "含子句标点的正文段不应被当成 heading"


def test_is_noise_line_rejects_clause_punctuation():
    """_is_noise_line 也应拦含子句标点的行（regex 兜底路径一致性）。"""
    assert _is_noise_line("②掘进巷道回风流甲烷传感器处安设1路摄像仪，监视回风流甲烷传感器。") is True
    # 真标题仍通过
    assert _is_noise_line("第一节 概述") is False
    assert _is_noise_line("一、巷道名称及用途") is False


# ── build_structure_hint: text_offset 优先（防 TOC 劫持，bug-404）──


def test_structure_hint_uses_text_offset_not_find():
    """当文档含目录页时，find(title) 命中目录条目（带页码），
    而非正文章节。text_offset 已正确指向正文位置，应优先使用。

    回归：LLM 收到目录条目摘要，无 H2/H3 信息 → 产出一级扁平结构。
    """
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint

    # 模拟有目录页的文档: TOC 在前(title1+页码)，正文在后(含子节 H2)
    paragraphs = [
        "title1 3",  # TOC 条目 (find 命中的位置 0)
        "title2 5",  # 更多目录
        "",  # 空行
        "title1",  # para_idx=3: 正文章节位置
        "正文内容，包含子节信息。",
        "sub1 第一节",  # H2 子节
        "子节内容...",
        "title2",  # para_idx=7: 第二个正文 H1
        "正文2",
    ]
    full_text = "\n\n".join(paragraphs)
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [
        Heading(title="title1", level=1, para_idx=3),
        Heading(title="title2", level=1, para_idx=7),
    ]
    doc.full_text = full_text
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 2000)
    # 正文章节后的 snippet 应包含 "sub1 第一节"
    assert "sub1 第一节" in hint, f"应用 text_offset 取正文, 得: {hint[:500]}"
    # 不应出现目录页码 "title1 3"（完整目录行含数字）
    assert "title1 3" not in hint, "目录条目不应出现在章节摘要中"


# ── _parse_style_levels: basedOn 继承（TDD RED→GREEN）──


def test_style_levels_resolves_basedon_inheritance(tmp_path):
    """自定义样式 basedOn 内置 heading 时，应继承父的 outlineLvl。

    Word 允许 <w:style styleId="MySection"><w:basedOn w:val="2"/>...</w:style>
    继承 styleId="2"（heading 2, outlineLvl=1）。MySection 自身无 outlineLvl，
    但语义上是 H2，应被识别。
    """
    import zipfile

    from app.extensions.knowledge_factory.doc_parser import _parse_style_levels

    styles_xml = (
        b'<?xml version="1.0"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:style w:styleId="2" w:type="paragraph"><w:name w:val="heading 2"/>'
        b'<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
        b'<w:style w:styleId="MySection" w:type="paragraph"><w:basedOn w:val="2"/>'
        b'<w:name w:val="My Section"/></w:style>'
        b"</w:styles>"
    )
    fp = tmp_path / "s.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/styles.xml", styles_xml)
    with zipfile.ZipFile(fp, "r") as zf:
        levels = _parse_style_levels(zf)
    # MySection 通过 basedOn 继承 "2" 的 outlineLvl=1 → level 2
    assert levels.get("mysection") == 2, f"MySection 应继承 level 2，得 {levels.get('mysection')}"


# ── P3 覆盖修复: 表 caption 过滤 + 子节树构建 ──


def test_is_table_caption_matches():
    """'表N.M-x' 标题是表格 caption，不是章节。"""
    from app.extensions.knowledge_factory.doc_parser import _is_table_caption

    assert _is_table_caption("表1.4-1") is True
    assert _is_table_caption("表 10.1-1") is True
    assert _is_table_caption("表2.3-10") is True
    # level 5 的（expat 样式路径产出）也识别
    assert _is_table_caption("表3.4-20") is True


def test_is_table_caption_rejects_real_sections():
    """真实章节标题（含数字编号）不是表格 caption。"""
    from app.extensions.knowledge_factory.doc_parser import _is_table_caption

    assert _is_table_caption("2.2.1.1 原总体规划批复情况") is False
    assert _is_table_caption("10 环境管理、监测计划与跟踪评价") is False
    assert _is_table_caption("1.1 规划背景与任务由来") is False


def test_build_structure_hint_includes_subsection_tree():
    """结构提示必须包含 H1 下的 H2/H3 子节标题（P3 根因）。"""
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint

    # 手工构造带子节的 ParsedDocument
    doc = ParsedDocument(file_path="x", file_type="docx")
    paragraphs = [
        "1 总则",
        "内容A",
        "1.1 规划背景",
        "内容B",
        "1.2 评价依据",
        "内容C",
        "2 规划方案",
        "内容D",
    ]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 规划背景", level=2, para_idx=2),
        Heading(title="1.2 评价依据", level=2, para_idx=4),
        Heading(title="2 规划方案", level=1, para_idx=6),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 5000)
    # 子节树包含 H2 标题
    assert "1.1 规划背景" in hint
    assert "1.2 评价依据" in hint
    # H1 目录仍存在
    assert "2 规划方案" in hint


def test_build_structure_hint_filters_table_captions():
    """表 caption（表N.M-x）不进入子节树。"""
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint

    doc = ParsedDocument(file_path="x", file_type="docx")
    paragraphs = ["1 总则", "见下表", "表1.4-1", "数据行", "2 结论", "结束"]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="表1.4-1", level=5, para_idx=2),  # 表格 caption 误标 Heading5
        Heading(title="2 结论", level=1, para_idx=4),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    hint = build_structure_hint(doc, 5000)
    assert "表1.4-1" not in hint  # 过滤
    assert "1 总则" in hint


def test_build_structure_hint_truncates_summary_not_tree():
    """max_chars 截断时子节树优先保留，摘要后砍。

    P3 修复的生产场景是 406 页文档（子节树 ~5650 chars > 默认 max_chars 5000），
    截断是真实路径。此测试必须真正触发 `if len(result) > max_chars` 分支：
    构造 3 章、每章 ~200 字正文，max_chars 设得比树略大 → 第 1 章摘要保留、后续章摘要被砍。
    """
    from app.extensions.knowledge_factory.doc_parser import build_structure_hint

    doc = ParsedDocument(file_path="x", file_type="docx")
    body = "本章正文内容。" * 60  # ~300 字
    paragraphs = [
        "1 总则",
        body,
        "1.1 规划背景",
        body,
        "2 环境现状",
        body,
        "2.1 监测点位",
        body,
        "3 环境影响预测",
        body,
        "3.1 预测模型",
        body,
    ]
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 规划背景", level=2, para_idx=2),
        Heading(title="2 环境现状", level=1, para_idx=4),
        Heading(title="2.1 监测点位", level=2, para_idx=6),
        Heading(title="3 环境影响预测", level=1, para_idx=8),
        Heading(title="3.1 预测模型", level=2, para_idx=10),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    # 全量结果 756 chars；树 ~305，树+首章摘要 ~518，树+前两章摘要 >700。
    # max_chars=650 落在 [树+首章摘要, 树+两章摘要) → 真正触发截断，首章摘要保留、后续章被砍。
    hint = build_structure_hint(doc, 650)
    # 子节树完整保留
    assert "1.1 规划背景" in hint
    assert "2.1 监测点位" in hint
    assert "3.1 预测模型" in hint
    # 第 1 章摘要保留（树 + 首章 200 字 ≤ 650）
    assert "本章正文内容" in hint
    # 截断必须真正发生：输出比全量结果短
    assert len(hint) < len(build_structure_hint(doc, 100000))
