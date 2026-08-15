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
        cover_master=None,
        cover_elements=None,
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


def test_build_template_data_includes_cover_elements():
    """Task 4: cover_elements (JSONB column) must flow through _build_template_data."""
    tpl = _fake_template()
    tpl.cover_elements = {
        "mode": "elements",
        "pages": [{"elements": [{"id": "e1", "type": "text", "text": "T"}]}],
    }
    td = _build_template_data(tpl)
    assert td["cover_elements"]["pages"][0]["elements"][0]["text"] == "T"


def test_collect_cover_fields_drops_none():
    fields = _collect_cover_fields(cover_title="T", cover_client=None, cover_date="2026-07", cover_project_number=None)
    assert fields == {"title": "T", "date": "2026-07"}


def test_collect_cover_fields_all_none_returns_empty():
    assert _collect_cover_fields(None, None, None, None) == {}


def test_strip_cover_master_payload_removes_xml_and_images():
    from app.extensions.output.routers import _strip_cover_master_payload

    cm = {
        "mode": "master",
        "xml": "<w:p/>",
        "images": [{"origRid": "rId1", "ext": "png", "b64": "AAA"}],
        "slots": [{"id": "client", "label": "建设单位"}],
        "sourceFile": "a.docx",
        "boundary": "before_toc",
    }
    stripped = _strip_cover_master_payload(cm)
    assert "xml" not in stripped
    assert "images" not in stripped
    assert stripped["mode"] == "master"
    assert stripped["slots"][0]["id"] == "client"
    assert stripped["sourceFile"] == "a.docx"
    assert stripped["boundary"] == "before_toc"


def test_strip_cover_master_payload_none_passthrough():
    from app.extensions.output.routers import _strip_cover_master_payload

    assert _strip_cover_master_payload(None) is None


def _minimal_template_dict():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "T",
        "report_type": "g",
        "is_builtin": False,
        "page_settings": {"paperSize": "A4"},
        "body_styles": {"fontFamily": "宋体"},
        "heading_styles": [],
        "reference_style": "gb7714",
        "cover_template": None,
        "cover_master": None,
        "toc_settings": None,
        "table_styles": None,
        "figure_styles": None,
        "header_footer": None,
        "appendix_rules": None,
        "created_at": "2026-08-07T00:00:00",
        "updated_at": "2026-08-07T00:00:00",
    }


def test_list_response_validates_stripped_cover_master():
    """L1: list items carry no xml/images but still validate through the list schema."""
    from app.extensions.output.routers import _strip_cover_master_payload
    from app.extensions.output.schemas import LayoutTemplateListResponse

    item = _minimal_template_dict()
    item["cover_master"] = _strip_cover_master_payload({"mode": "master", "xml": "<w:p/>", "images": [{"b64": "x"}], "slots": [], "sourceFile": "a.docx", "boundary": "before_toc"})
    resp = LayoutTemplateListResponse(items=[item], total=1)
    cm = resp.items[0].cover_master
    assert "xml" not in cm
    assert "images" not in cm
    assert cm["mode"] == "master"
    assert cm["sourceFile"] == "a.docx"


def test_detail_response_preserves_full_cover_master():
    """L1: detail (getTemplate) must keep xml/images so the editor can save."""
    from app.extensions.output.schemas import LayoutTemplateResponse

    item = _minimal_template_dict()
    item["cover_master"] = {"mode": "master", "xml": "<w:p/>", "images": [{"b64": "x"}], "slots": [], "sourceFile": "a.docx", "boundary": "before_toc"}
    resp = LayoutTemplateResponse.model_validate(item)
    assert resp.cover_master["xml"] == "<w:p/>"
    assert "images" in resp.cover_master
