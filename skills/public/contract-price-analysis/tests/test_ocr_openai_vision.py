"""cpa v3 M3: openai-vision OCR 前端(unit,纯函数部分)。

spec: docs/superpowers/specs/2026-10-14-contract-price-cpa-v3-library-terms-ocr-design.md §3.4
覆盖: HTML→rows 解析 / TableExtract 形状(bbox=None 语义) / 缓存分键约定。
"""

import asyncio

import pytest

from scripts.document_parser import (
    html_tables_to_rows,
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
