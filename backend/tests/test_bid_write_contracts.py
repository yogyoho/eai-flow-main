"""批十九 T1 契约层自检:商务子集全部是审查端宇宙真实成员(零新契约铁律)、
禁用词表形状、断言/错误码编号格式。"""

import pytest

from app.extensions.bid_review.engine.registry import pack_inputs, universe
from app.extensions.bid_write import contracts


def test_commercial_subset_is_real_universe_members():
    """COMMERCIAL_TENDER_SUBSET ⊆ registry.universe()(M0 零新增抽取契约铁律:
    幽灵路径会进 prompt 却永远抽不到值,装配器缺行静默=假缺口)。"""
    uni = set(universe())
    missing = [p for p in contracts.COMMERCIAL_TENDER_SUBSET if p not in uni]
    assert missing == []


def test_commercial_subset_no_bid_paths():
    """子集无 bid.* 路径(写作端 tender-only;bid.* 由生成过程产出,不由招标抽取)。"""
    assert all(p.startswith("tender.") for p in contracts.COMMERCIAL_TENDER_SUBSET)


def test_subset_covers_matrix_row_sources():
    """装配器行源路径全部在子集内(契约层与装配器的耦合面钉死)。"""
    for p in ("tender.attachment_requirements", "tender.required_declarations", "tender.deposit_required", "tender.bid_deadline", "tender.min_warranty_period"):
        assert p in contracts.COMMERCIAL_TENDER_SUBSET


def test_forbidden_words_shape():
    """词表每项=(合法降级级, 非空处置说明);D0/D1 级词非空。"""
    for word, (level, note) in contracts.FORBIDDEN_WORDS.items():
        assert level in contracts.DEGRADE_LEVELS, word
        assert note.strip(), word
        assert word.strip()


def test_forbidden_words_red_lines_are_d0():
    """合规红线(围标/串标/保证中标等)必须 D0(导出阻断级)。"""
    for w in ("保证中标", "围标", "串标", "包过", "内部渠道"):
        assert contracts.FORBIDDEN_WORDS[w][0] == "D0"


def test_assertion_and_error_codes():
    assert contracts.assertion_id("BL", 1) == "SK-BL-001"
    assert contracts.assertion_id("PS", 12) == "SK-PS-012"
    assert contracts.error_code("RT", 3) == "E-RT-003"
    assert contracts.error_code("AI", 9) == "E-AI-009"
    with pytest.raises(ValueError):
        contracts.assertion_id("XX", 1)


def test_schema_version_and_vocab():
    """SCHEMA_VERSION 语义化;枚举词汇与规格 §四/§0 对齐。"""
    assert contracts.SCHEMA_VERSION.count(".") == 2
    assert contracts.MATRIX_STRATEGIES == ("pending", "full", "positive", "negative")
    assert contracts.MATRIX_STATUSES == ("draft", "confirmed", "blocked")
    assert set(contracts.MATERIAL_ENTITY_TYPES) == {"qualification", "performance", "personnel", "capacity", "network", "past_bid"}
    assert set(contracts.SLOT_TYPES) == {"str", "enum", "decimal", "date", "money", "entity_ref", "list", "computed"}
    assert contracts.BLOCK_EXPORT_LEVELS == ("D0",)


def test_l4_pack_inputs_not_broken_by_subset():
    """子集引入不改变规则包输入面(审查端零改动交叉验证:pack_inputs 是包 yaml
    的 inputs 全集,与写作端子集无交集要求不成立——重叠合法,但审查端输入集
    必须原样不动)。"""
    inputs = pack_inputs()
    assert "tender.attachment_requirements" in inputs  # 审查端既有输入仍在
