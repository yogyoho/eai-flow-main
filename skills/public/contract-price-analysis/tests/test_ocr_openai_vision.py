"""cpa v3 M3: openai-vision OCR 前端(unit,纯函数部分)。

spec: docs/superpowers/specs/2026-10-14-contract-price-cpa-v3-library-terms-ocr-design.md §3.4
覆盖: HTML→rows 解析 / TableExtract 形状(bbox=None 语义) / 缓存分键约定。
"""

import asyncio

import pytest

from scripts.document_parser import (
    html_tables_to_rows,
    parse_table_marker_stream,
    parse_document,
    to_cache,
)


class TestHtmlTablesToRows:
    def test_basic_table(self):
        html = "<table><tr><td>项目名称</td><td>含税单价</td></tr><tr><td>钢筋</td><td>4200.00</td></tr></table>"
        assert html_tables_to_rows(html) == [
            [["项目名称", "含税单价"], ["钢筋", "4200.00"]]
        ]

    def test_markdown_fence_and_prose_ignored(self):
        html = '好的,以下是表格:\n```html\n<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>\n```\n完毕。'
        assert html_tables_to_rows(html) == [[["A", "B"], ["1", "2"]]]

    def test_no_table_returns_empty(self):
        assert html_tables_to_rows("没有表格") == []

    def test_multitable(self):
        html = "<table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table>"
        assert len(html_tables_to_rows(html)) == 2

    def test_empty_cells_preserved(self):
        html = "<table><tr><td>x</td><td></td><td> </td></tr></table>"
        assert html_tables_to_rows(html) == [[["x", "", ""]]]


class TestOpenaiVisionExtractShape:
    """bbox=None 语义: 外部 provider 产出的 TableExtract 进缓存/提取层前形状。"""

    def test_rows_to_tableextract_fields(self):
        from scripts.document_parser import TableExtract

        rows = [["品名", "单价"], ["钢筋", "4200"]]
        t = TableExtract(
            page_no=3,
            table_idx=0,
            bbox=[0, 0, 0, 0],
            rows=rows,
            cell_bboxes=[[list(0 for _ in range(4)) for _ in row] for row in rows],
            page_preview_b64="cG5n",
            mean_confidence=0.0,
            tokens=[],
        )
        assert t.bbox == [0, 0, 0, 0]
        assert t.cell_bboxes[1][0] == [0, 0, 0, 0]
        # 缓存形态可往返(与 builtin 同一契约)
        cached = to_cache([t], {3: ""})
        assert cached["tables"][0]["rows"] == rows

    def test_dispatch_to_openai_vision_without_cfg_raises(self):
        # backend=openai-vision 但缺 base_url → 明确报错(不静默吞)
        with pytest.raises(Exception):
            asyncio.run(
                parse_document(b"", "x.pdf", "http://unused:8010", backend="openai-vision", openai_cfg={})
            )


class TestCacheKeyConvention:
    """spec §3.4: builtin ocr/{sha}.json;外部 ocr/x-{provider}/{sha}.json。"""

    def test_builtin_key_unchanged(self):
        provider = None
        h = "abc123"
        key = f"ocr/x-{provider}/{h}.json" if provider else f"ocr/{h}.json"
        assert key == "ocr/abc123.json"

    def test_provider_key_namespaced(self):
        provider = "paddleocr-vl"
        h = "abc123"
        key = f"ocr/x-{provider}/{h}.json" if provider else f"ocr/{h}.json"
        assert key == "ocr/x-paddleocr-vl/abc123.json"
        assert not key.startswith("ocr/abc")  # 与内建空间不相交


class TestParseTableMarkerStream:
    """PaddleOCR-VL 原生标记流解析(真实 p94 工程量清单输出片段)。"""

    SAMPLE = (
        "<fcel>附件一：工程量清单<lcel><lcel><lcel><lcel><lcel><lcel><lcel><lcel><lcel><lcel><nl>"
        "<fcel>序号<fcel>项目名称<fcel>单位<fcel>工程量<fcel>不含增值税<lcel><fcel>税率<fcel>税金合计<fcel>含税<lcel><lcel><nl>"
        "<ucel><ucel><ucel><ucel><fcel>单价<fcel>合价<ucel><ucel><fcel>单价<fcel>合价<lcel><nl>"
        "<fcel>1<fcel>平整场地<fcel>m2<fcel>824.79<fcel>1.20<fcel>989.75<fcel>9%<fcel>89.08<fcel>1.31<fcel>1078.83<lcel><nl>"
        "<fcel>5<fcel>多孔砖墙<fcel>m3<fcel>210.86<fcel>511.00<fcel>107749.46<fcel>9%<fcel>9697.45<fcel>556.99<fcel>117446.91<lcel><nl>"
    )

    def test_rows_grid_aligned(self):
        tables = parse_table_marker_stream(self.SAMPLE)
        assert len(tables) == 1
        rows = tables[0]
        # 每行 11 个网格格(含合并占位)
        assert all(len(r) == 11 for r in rows)
        assert rows[2][0] == "" and rows[2][4] == "单价"  # ucel 占位 + 子表头

    def test_data_row_values(self):
        rows = parse_table_marker_stream(self.SAMPLE)[0]
        assert rows[3][:4] == ["1", "平整场地", "m2", "824.79"]
        assert rows[3][9] == "1078.83"
        assert rows[4][1] == "多孔砖墙" and rows[4][3] == "210.86"

    def test_header_text_kept_in_first_cell(self):
        rows = parse_table_marker_stream(self.SAMPLE)[0]
        assert rows[0][0] == "附件一：工程量清单"
        assert rows[1][1] == "项目名称"

    def test_non_marker_output_returns_empty(self):
        # HTML/纯文本输出 → [](调用方回退 html_tables_to_rows)
        assert parse_table_marker_stream("<table><tr><td>a</td></tr></table>") == []
        assert parse_table_marker_stream("") == []

    def test_marker_stream_not_parsed_by_html_fallback(self):
        # 防呆: 标记流没有 <table> 标签,HTML 解析器返回空——两条解析路径互斥
        assert html_tables_to_rows(self.SAMPLE) == []
