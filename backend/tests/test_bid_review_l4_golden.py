"""L4 golden 两题(cases-l4 独立冻结面,A-β2-⑧):用 run_case(case, pack=l4pack) 跑,
主 golden 套件/CLI(bid-review-core 62 题)零触碰,L4 不入主面。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden.loader import load_case
from app.extensions.bid_review.golden.runner import run_case

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml"
CASES_DIR = Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "golden" / "cases-l4"


def _pack():
    return load_rulepack(PACK)


@pytest.mark.asyncio
async def test_l4_golden_warranty_overcommit():
    res = await run_case(load_case(CASES_DIR / "L4-001-warranty-overcommit.yaml", _pack()), pack=_pack())
    assert res.ok, res


@pytest.mark.asyncio
async def test_l4_golden_hedge_words_need_human_fail_open():
    res = await run_case(load_case(CASES_DIR / "L4-008-hedge-words.yaml", _pack()), pack=_pack())
    assert res.ok, res
