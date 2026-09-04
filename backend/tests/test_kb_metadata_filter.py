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
