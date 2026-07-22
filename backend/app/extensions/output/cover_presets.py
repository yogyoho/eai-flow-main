"""Built-in cover-page presets for the docmgr Word export.

Each preset is a data-driven cover layout (no visual designer): ``elements``
describes the layout (spacer/text/info rows) consumed by
``generator._render_cover_preset``; ``fields`` describes the value inputs the
frontend should prompt.

Adding a new report type = append one config entry here; no code change elsewhere.
"""

COVER_PRESETS: list[dict] = [
    {
        "id": "fire_protection",
        "label": "消防设计专篇",
        "fields": [
            {"name": "title", "label": "标题", "default_from": "doc_title"},
            {"name": "client", "label": "建设单位"},
            {"name": "project_number", "label": "项目编号"},
            {"name": "date", "label": "日期", "default_from": "today"},
        ],
        "elements": [
            {"type": "spacer", "lines": 3},
            {"type": "text", "field": "title", "align": "center", "font": "黑体", "size": 22, "bold": True},
            {"type": "spacer", "lines": 4},
            {"type": "info", "label": "建设单位", "field": "client", "align": "center", "font": "宋体", "size": 14},
            {"type": "info", "label": "项目编号", "field": "project_number", "align": "center", "font": "宋体", "size": 14},
            {"type": "info", "label": "日期", "field": "date", "align": "center", "font": "宋体", "size": 14},
        ],
    },
]

_PRESET_BY_ID = {p["id"]: p for p in COVER_PRESETS}


def get_cover_preset(preset_id: str) -> dict | None:
    """Return the cover preset with ``preset_id``, or None if unknown."""
    return _PRESET_BY_ID.get(preset_id)


def public_cover_presets() -> list[dict]:
    """Trimmed preset view for the API/frontend: id, label, fields (no layout elements)."""
    return [{"id": p["id"], "label": p["label"], "fields": p.get("fields", [])} for p in COVER_PRESETS]
