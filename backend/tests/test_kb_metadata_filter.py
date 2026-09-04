"""build_metadata_condition(filters→RAGFlow metadata_condition)单测。"""

import pytest

from app.extensions.knowledge.service import build_metadata_condition


def test_none_and_empty():
    assert build_metadata_condition(None) is None
    assert build_metadata_condition({}) is None
    assert build_metadata_condition({"sector": ""}) is None
    assert build_metadata_condition({"keywords": []}) is None


def test_sector_is():
    assert build_metadata_condition({"sector": "环境评价"}) == {
        "logic": "and",
        "conditions": [{"name": "sector", "comparison_operator": "is", "value": "环境评价"}],
    }


def test_law_number_is():
    assert build_metadata_condition({"law_number": "HJ 130-2019"}) == {
        "logic": "and",
        "conditions": [{"name": "law_number", "comparison_operator": "is", "value": "HJ 130-2019"}],
    }


def test_keywords_expanded_to_contains():
    out = build_metadata_condition({"keywords": ["规划环评", "三线一单"]})
    assert out == {
        "logic": "and",
        "conditions": [
            {"name": "keywords", "comparison_operator": "contains", "value": "规划环评"},
            {"name": "keywords", "comparison_operator": "contains", "value": "三线一单"},
        ],
    }


def test_date_range_ge_le():
    out = build_metadata_condition({"effective_date_from": "2009-01-01", "effective_date_to": "2015-12-31"})
    assert out == {
        "logic": "and",
        "conditions": [
            {"name": "effective_date", "comparison_operator": "≥", "value": "2009-01-01"},
            {"name": "effective_date", "comparison_operator": "≤", "value": "2015-12-31"},
        ],
    }


def test_combined_order():
    out = build_metadata_condition({"sector": "环境评价", "law_number": "HJ 130-2019"})
    assert out["logic"] == "and"
    assert out["conditions"] == [
        {"name": "sector", "comparison_operator": "is", "value": "环境评价"},
        {"name": "law_number", "comparison_operator": "is", "value": "HJ 130-2019"},
    ]


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="unsupported filter key"):
        build_metadata_condition({"hacker": "x"})


def test_whitespace_sector_treated_as_absent():
    assert build_metadata_condition({"sector": "   "}) is None


class _FakeListRF:
    """list_documents 假件:按页返回预设 id,记录 metadata_condition。"""

    def __init__(self, pages, total):
        self._pages = pages
        self._total = total
        self.seen_conditions = []

    async def list_documents(self, dataset_id, page=1, size=100, metadata_condition=None, orderby=None, desc=None):
        self.seen_conditions.append(metadata_condition)
        docs = [{"id": i} for i in self._pages[page - 1]]
        return {"data": {"docs": docs, "total": self._total}}


@pytest.mark.asyncio
async def test_filter_doc_ids_single_page_under_cap():
    from app.extensions.knowledge.service import filter_doc_ids

    rf = _FakeListRF([["a", "b", "c"]], 3)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert ids == ["a", "b", "c"] and truncated is False


@pytest.mark.asyncio
async def test_filter_doc_ids_paginates_and_caps_at_100():
    from app.extensions.knowledge.service import filter_doc_ids

    pages = [[f"d{i:03d}" for i in range((p - 1) * 100, p * 100)] for p in (1, 2)]
    rf = _FakeListRF(pages, 150)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert len(ids) == 100 and truncated is True
    assert len(rf.seen_conditions) == 1  # 装满 100 上限即停,不取第 2 页


@pytest.mark.asyncio
async def test_filter_doc_ids_exactly_100_not_truncated():
    from app.extensions.knowledge.service import filter_doc_ids

    rf = _FakeListRF([[f"d{i:03d}" for i in range(100)]], 100)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert len(ids) == 100 and truncated is False  # 恰好 100 = 全命中,不算截断


@pytest.mark.asyncio
async def test_filter_doc_ids_zero_hits():
    from app.extensions.knowledge.service import filter_doc_ids

    rf = _FakeListRF([[]], 0)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert ids == [] and truncated is False
