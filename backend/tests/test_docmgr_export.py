"""Regression tests for document-space export (Markdown + Word).

Root cause these guard against: the docmgr export endpoints and the
``generate_docx_simple`` helper were implemented on a divergent branch and
only ever captured in a git stash (c97665ec). They never landed on the
working branch, so the frontend's export menu hit non-existent routes and
both Markdown and Word export failed with 404. These tests lock the
endpoints + generator in place so they cannot silently disappear again.
"""

from io import BytesIO


def _docmgr_paths():
    """Return the set of (path, method) tuples registered on the docmgr router."""
    from app.extensions.docmgr.routers import router

    paths = set()
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            paths.add((route.path, method))
    return paths


def test_docmgr_router_registers_get_export():
    """GET /documents/{doc_id}/export must be registered (Markdown / simple export)."""
    paths = _docmgr_paths()
    assert (
        "/api/extensions/docmgr/documents/{doc_id}/export",
        "GET",
    ) in paths, "docmgr GET export route is missing — Markdown export would 404"


def test_docmgr_router_registers_post_export():
    """POST /documents/{doc_id}/export must be registered (Word export with layout)."""
    paths = _docmgr_paths()
    assert (
        "/api/extensions/docmgr/documents/{doc_id}/export",
        "POST",
    ) in paths, "docmgr POST export route is missing — Word export would 404"


def test_generate_docx_simple_produces_valid_docx():
    """generate_docx_simple must emit a non-empty, valid OOXML (.docx) buffer."""
    from app.extensions.output.generator import generate_docx_simple

    md = "# 测试标题\n\n这是正文段落。\n\n## 二级标题\n\n- 列表项一\n- 列表项二\n"
    buf = BytesIO()
    generate_docx_simple(md, buf)

    data = buf.getvalue()
    assert len(data) > 100, "generated docx buffer is suspiciously small"
    # .docx is a ZIP archive — must start with the PK\x03\x04 magic bytes.
    assert data[:2] == b"PK", "generated buffer is not a valid .docx (ZIP) file"


def test_generate_docx_simple_applies_watermark_and_layout():
    """generate_docx_simple must accept layout_template + watermark without error."""
    from app.extensions.output.generator import generate_docx_simple

    md = "# 报告\n\n正文内容。"
    buf = BytesIO()
    generate_docx_simple(
        md,
        buf,
        template_data={
            "page_settings": {"paperSize": "A4", "orientation": "portrait"},
            "body_styles": {"fontFamily": "宋体", "fontSize": 12},
            "heading_styles": [{"level": 1, "fontSize": 22, "fontWeight": 700}],
            "header_footer": {"footerText": "页脚", "showPageNumber": True},
        },
        watermark="draft",
    )
    data = buf.getvalue()
    assert data[:2] == b"PK"
