"""批十九 T7 断言注册表钉(assertions/p0.yaml):编号连续、规则锚真实(禁幽灵 id)、
级别词汇合法、D0⇔blocks_export、错误码一一对应。幽灵 rule_ref 拒载=契约层铁律的
注册表版(同 test_bid_write_contracts 的 subset⊆universe 律)。"""

from pathlib import Path

import yaml

import app.extensions.bid_write.contracts as contracts

ASSERTIONS_PATH = Path(contracts.__file__).parent / "assertions" / "p0.yaml"

_SPEC_COUNTS = {"BL": 10, "PS": 10, "RT": 9, "AI": 9}  # 规格 §1.5/§2.7/§3.5/§4.5 表行数


def _load() -> list[dict]:
    with open(ASSERTIONS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["assertions"]


def _real_rule_ids() -> set[str]:
    from app.extensions.bid_review.worker import ADVISORY_RULEPACK_PATH, RULEPACK_PATH

    ids = set()
    for path in (RULEPACK_PATH, ADVISORY_RULEPACK_PATH):
        with open(path, encoding="utf-8") as f:
            for a in yaml.safe_load(f)["rules"]:
                ids.add(a["id"])
    assert "L1-009" in ids and len(ids) >= 70  # core 60 + L4 10 卫语句(结构变化显式炸)
    return ids


def test_ids_contiguous_per_skill():
    """每技能编号 SK-<SK>-001..NNN 连续无跳号(规格表即连续表)。"""
    by_skill: dict[str, list[int]] = {}
    for a in _load():
        skill, n = a["id"].split("-")[1], int(a["id"].split("-")[2])
        assert skill in contracts.SKILL_IDS
        by_skill.setdefault(skill, []).append(n)
    for skill, ns in by_skill.items():
        assert ns == list(range(1, _SPEC_COUNTS[skill] + 1)), skill


def test_rule_refs_are_real_pack_members():
    """rule_ref ∈ core+L4 真实规则 id,或 null(写作端新增校验);幽灵 id 拒载。"""
    real = _real_rule_ids()
    ghosts = [a["id"] for a in _load() if a.get("rule_ref") and a["rule_ref"] not in real]
    assert ghosts == []


def test_levels_vocab_and_export_block():
    """level ∈ DEGRADE_LEVELS;blocks_export ⇔ level==D0(§5.3 导出只看 D0)。"""
    for a in _load():
        assert a["level"] in contracts.DEGRADE_LEVELS, a["id"]
        assert a["blocks_export"] is (a["level"] == "D0"), a["id"]
        assert isinstance(a["expr"], str) and a["expr"].strip(), a["id"]


def test_error_codes_match_helpers():
    """err_code 口径 = contracts.error_code(skill, n)(断言/错误码一一对应的注册表面)。"""
    for a in _load():
        skill, n = a["skill"], int(a["id"].split("-")[2])
        assert a["id"] == contracts.assertion_id(skill, n)
        assert contracts.error_code(skill, n) == f"E-{skill}-{n:03d}"


def test_d0_floor_covers_hard_gates():
    """硬门断言必须 D0:★零负偏离/清单覆盖/限价/主体一致/负证据留痕(规格红线面)。"""
    must_d0 = {"SK-RT-002", "SK-PS-001", "SK-PS-006", "SK-BL-004", "SK-AI-009"}
    levels = {a["id"]: a["level"] for a in _load()}
    for aid in must_d0:
        assert levels[aid] == "D0", aid


def test_docstring_spec_counts_total():
    """总断言数=规格四表合计 38(BL10+PS10+RT9+AI9);表增减须同步规格与本钉。"""
    assert len(_load()) == sum(_SPEC_COUNTS.values()) == 38
