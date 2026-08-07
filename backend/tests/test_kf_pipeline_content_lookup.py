"""Unit tests for pipeline content-lookup degradation (bug-1123).

Focus: _find_best_matching_paragraph and _find_section_content must NOT
return unrelated "document beginning" content when no match is found —
that content misleads the LLM into fabricating tables/metadata for
section titles (e.g. a "建筑设计防火规范" section getting a fire-protection
table that doesn't exist in the source).

Regression: 给排水 sec_05_06 建筑设计防火规范 (source has no such title)
previously got document-beginning content via strategy-3 fallback → LLM
invented a 耐火等级表. Now returns "" → _enrich's _short_content skip.
"""

from app.extensions.knowledge_factory.pipeline import _find_best_matching_paragraph

# ── _find_best_matching_paragraph: 匹配不到必须返回 "" ──

def test_no_keywords_returns_empty():
    """空关键词 → 返回 ""（之前返回 content 开头，诱导 LLM 幻觉）。"""
    content = "设计依据\n\n委托书和设计合同\n\n给排水专业统一规定"
    assert _find_best_matching_paragraph(content, [], 4000) == ""


def test_no_match_returns_empty_not_doc_beginning():
    """关键词完全匹配不到 → 返回 ""，绝不返回文档开头。

    回归 bug-1123：sec_05_06 "建筑设计防火规范" 在源文档无此标题，关键词
    匹配失败，之前降级返回文档开头（"设计依据...委托书"），LLM 凭标题编造
    耐火等级表。
    """
    content = "设计依据\n\n委托书和设计合同\n\n给排水专业统一规定"
    keywords = ["建筑设计防火规范", "消防"]
    assert _find_best_matching_paragraph(content, keywords, 4000) == ""


def test_match_returns_best_paragraph():
    """真正匹配到 → 返回包含关键词最多的段落（正常行为不受影响）。"""
    content = (
        "设计依据\n\n"
        "根据《建筑设计防火规范》GB50016-2014 第5章\n\n"
        "委托书和设计合同\n\n"
        "根据《石油化工循环水场设计规范》"
    )
    keywords = ["建筑设计防火规范"]
    result = _find_best_matching_paragraph(content, keywords, 4000)
    assert "建筑设计防火规范" in result
    assert "委托书" not in result


def test_partial_keyword_match_requires_all():
    """部分关键词命中但未覆盖全部 → 仍返回 ""（避免弱匹配喂误导内容）。"""
    content = "设计依据\n\n委托书和设计合同"
    keywords = ["建筑设计防火规范", "给排水"]  # 只有"给排水"可能命中
    assert _find_best_matching_paragraph(content, keywords, 4000) == ""
