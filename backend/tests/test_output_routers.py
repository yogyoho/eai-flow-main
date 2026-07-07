"""Tests for routers template_data assembly + cover field collection."""
from types import SimpleNamespace

from app.extensions.output.routers import _build_template_data, _collect_cover_fields


def _fake_template():
    return SimpleNamespace(
        page_settings={"paperSize": "A4"},
        body_styles={"fontFamily": "宋体"},
        heading_styles=[{"level": 1, "numbering": "decimal"}],
        table_styles=None,
        figure_styles=None,
        header_footer={"showPageNumber": True},
        reference_style="gb7714",
        appendix_rules=None,
        cover_template={"showTitle": True},
        toc_settings={"maxDepth": 2},
    )


def test_build_template_data_includes_cover_and_toc():
    """Regression: cover_template + toc_settings must NOT be dropped (the original bug)."""
    td = _build_template_data(_fake_template())
    assert td["cover_template"] == {"showTitle": True}
    assert td["toc_settings"] == {"maxDepth": 2}
    assert td["page_settings"] == {"paperSize": "A4"}
    assert td["reference_style"] == "gb7714"


def test_build_template_data_cover_none_when_absent():
    tpl = _fake_template()
    tpl.cover_template = None
    tpl.toc_settings = None
    td = _build_template_data(tpl)
    assert td["cover_template"] is None
    assert td["toc_settings"] is None


def test_collect_cover_fields_drops_none():
    fields = _collect_cover_fields(
        cover_title="T", cover_client=None, cover_date="2026-07", cover_project_number=None
    )
    assert fields == {"title": "T", "date": "2026-07"}


def test_collect_cover_fields_all_none_returns_empty():
    assert _collect_cover_fields(None, None, None, None) == {}
