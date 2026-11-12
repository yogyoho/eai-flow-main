"""批十九 T7 断言注册表钉(assertions/p0.yaml):编号连续、规则锚真实(禁幽灵 id)、
级别词汇合法、D0⇔blocks_export、错误码一一对应。幽灵 rule_ref 拒载=契约层铁律的
注册表版(同 test_bid_write_contracts 的 subset⊆universe 律)。"""

from pathlib import Path

import yaml

import app.extensions.bid_write.contracts as contracts

ASSERTIONS_PATH = Path(contracts.__file__).parent / "assertions" / "p0.yaml"

_SPEC_COUNTS = {"BL": 10, "PS": 10, "RT": 9, "AI": 9, "CMN": 5}  # 规格 §1.5/§2.7/§3.5/§4.5+v2 共享层


def _load() -> dict:
    with open(ASSERTIONS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _assertions() -> list[dict]:
    return _load()["assertions"]


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
    for a in _assertions():
        skill, n = a["id"].split("-")[1], int(a["id"].split("-")[2])
        assert skill in contracts.SKILL_IDS
        by_skill.setdefault(skill, []).append(n)
    for skill, ns in by_skill.items():
        assert ns == list(range(1, _SPEC_COUNTS[skill] + 1)), skill


def test_rule_refs_are_real_pack_members():
    """rule_ref ∈ core+L4 真实规则 id,或 null(写作端新增校验);幽灵 id 拒载。"""
    real = _real_rule_ids()
    ghosts = [a["id"] for a in _assertions() if a.get("rule_ref") and a["rule_ref"] not in real]
    assert ghosts == []


def test_levels_vocab_and_export_block():
    """level ∈ DEGRADE_LEVELS;blocks_export ⇔ level==D0(§5.3 导出只看 D0)。"""
    for a in _assertions():
        assert a["level"] in contracts.DEGRADE_LEVELS, a["id"]
        assert a["blocks_export"] is (a["level"] == "D0"), a["id"]
        assert isinstance(a["expr"], str) and a["expr"].strip(), a["id"]


def test_error_codes_match_helpers():
    """err_code 口径 = contracts.error_code(skill, n)(断言/错误码一一对应的注册表面)。"""
    for a in _assertions():
        skill, n = a["skill"], int(a["id"].split("-")[2])
        assert a["id"] == contracts.assertion_id(skill, n)
        assert contracts.error_code(skill, n) == f"E-{skill}-{n:03d}"


def test_d0_floor_covers_hard_gates():
    """硬门断言必须 D0:★零负偏离/清单覆盖/限价/主体一致/负证据留痕(规格红线面)。"""
    must_d0 = {"SK-RT-002", "SK-PS-001", "SK-PS-006", "SK-BL-004", "SK-AI-009"}
    levels = {a["id"]: a["level"] for a in _assertions()}
    for aid in must_d0:
        assert levels[aid] == "D0", aid


def test_docstring_spec_counts_total():
    """总断言数=43(BL10+PS10+RT9+AI9+v2 CMN 共享层5);表增减须同步规格与本钉。"""
    assert len(_assertions()) == sum(_SPEC_COUNTS.values()) == 43


def test_levels_behavior_table():
    """v2 levels 行为表:四级行为键齐,D0 blk=true,D1-D3 blk=false(执行器分派真源,
    不再靠约定)。"""
    levels = _load()["levels"]
    assert set(levels) == set(contracts.DEGRADE_LEVELS)
    for lvl, spec in levels.items():
        for key in ("blk", "render", "todo", "pre_review_state", "retry"):
            assert key in spec, (lvl, key)
        assert spec["blk"] is (lvl == "D0"), lvl


def test_delegates_single_implementation():
    """delegates_to 律:委托断言目标必须存在;同口径单实现(执行器不重复跑)。"""
    by_id = {a["id"]: a for a in _assertions()}
    for a in _assertions():
        target = a.get("delegates_to")
        if target:
            assert target in by_id, a["id"]
            assert "同" in (a.get("expr") or ""), a["id"]  # expr 面标注委托口径


def test_shared_layer_scope():
    """CMN 共享层 5 条=导出级全文面;技能级断言不得复制共享口径(SK-AI-009 除外,
    delegates_to 登记律)。"""
    cmn = [a for a in _assertions() if a["skill"] == "CMN"]
    assert [a["id"] for a in cmn] == [f"SK-CMN-{i:03d}" for i in range(1, 6)]
    delegates = {a.get("delegates_to") for a in _assertions() if a.get("delegates_to")}
    assert delegates == {"SK-CMN-005"}
