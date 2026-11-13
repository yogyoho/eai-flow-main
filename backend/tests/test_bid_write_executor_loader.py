"""批二十 M1 断言执行器 loader/数据面测试(EAI-CUSTOM 2026-11-13)——加载期静态
校验拒载分支(临时 yaml)+ 真实注册表 43 条全载钉 + SkillRun 共享 Base 注册钉。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.extensions.bid_write.contracts import SCHEMA_VERSION, SKILL_IDS
from app.extensions.bid_write.executor.loader import RegistryError, _load, load_registry
from app.extensions.bid_write.executor.models import LEVEL_RANK
from app.extensions.database import Base

# ── 真实注册表全载钉 ──────────────────────────────────────────────────────────


def test_load_registry_43_assertions_and_level_distribution():
    snap = load_registry()
    assert len(snap.assertions) == 43
    by_skill: dict[str, int] = {}
    d0 = 0
    for a in snap.assertions:
        by_skill[a.skill] = by_skill.get(a.skill, 0) + 1
        if a.level == "D0":
            d0 += 1
            assert a.blocks_export is True
    assert by_skill == {"CMN": 5, "BL": 10, "PS": 10, "RT": 9, "AI": 9}
    assert d0 == 31
    assert set(by_skill) == set(SKILL_IDS)
    assert snap.schema_version == SCHEMA_VERSION


def test_levels_table_four_rows_and_d0_blk():
    snap = load_registry()
    assert set(snap.levels) == {"D0", "D1", "D2", "D3"}
    assert snap.levels["D0"]["blk"] is True
    for lvl in ("D1", "D2", "D3"):
        assert not snap.levels[lvl].get("blk")


def test_level_rank_monotonic():
    assert LEVEL_RANK["D0"] < LEVEL_RANK["D1"] < LEVEL_RANK["D2"] < LEVEL_RANK["D3"]


def test_delegate_edge_ai009_to_cmn005():
    snap = load_registry()
    by_id = snap.by_id()
    assert by_id["SK-AI-009"].delegates_to == "SK-CMN-005"
    assert by_id["SK-CMN-005"].delegates_to is None


def test_human_action_present_on_all_but_ps004():
    snap = load_registry()
    for a in snap.assertions:
        if a.id == "SK-PS-004":
            assert a.human_action is None  # null=处置自动闭环(v3 规格)
        else:
            assert a.human_action


def test_skillrun_table_registered_on_shared_base():
    # bug-4303 律:共享 Base(经 routers import 链注册),gateway create_all 可建
    assert "bid_write_skill_runs" in Base.metadata.tables


# ── 拒载分支(临时 yaml)────────────────────────────────────────────────────


def _valid_registry() -> dict:
    return {
        "meta": {"schema_version": SCHEMA_VERSION, "skills": ["AI"], "shared_layer": "CMN"},
        "levels": {
            "D0": {"blk": True, "render": "TODO_BLOCK", "todo": "required", "pre_review_state": "MISSING", "retry": "self_refine_max_2"},
            "D1": {"blk": False, "render": "MARK_YELLOW", "todo": "optional", "pre_review_state": "UNKNOWN", "retry": "self_refine_max_1"},
            "D2": {"blk": False, "render": "BOARD_ONLY", "todo": "none", "pre_review_state": None, "retry": "none"},
            "D3": {"blk": False, "render": "NONE", "todo": "none", "pre_review_state": None, "retry": "none"},
        },
        "assertions": [
            {"id": "SK-CMN-005", "skill": "CMN", "name": "待补项必带负证据", "level": "D0", "blocks_export": True, "rule_ref": None, "expr": "x", "human_action": "补"},
        ],
    }


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "registry.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


def _expect_reject(tmp_path: Path, doc: dict, fragment: str) -> None:
    with pytest.raises(RegistryError, match=fragment):
        _load(_write(tmp_path, doc))


def test_reject_version_mismatch(tmp_path):
    doc = _valid_registry()
    doc["meta"]["schema_version"] = "9.9.9"
    _expect_reject(tmp_path, doc, "schema_version")


def test_reject_duplicate_id(tmp_path):
    doc = _valid_registry()
    doc["assertions"].append(dict(doc["assertions"][0]))
    _expect_reject(tmp_path, doc, "重复")


def test_reject_bad_level(tmp_path):
    doc = _valid_registry()
    doc["assertions"][0]["level"] = "D9"
    _expect_reject(tmp_path, doc, "非法 level")


def test_reject_d0_blocks_export_mismatch(tmp_path):
    doc = _valid_registry()
    doc["assertions"][0]["blocks_export"] = False
    _expect_reject(tmp_path, doc, "D0⇔blocks_export")
    doc = _valid_registry()
    doc["assertions"][0].update({"level": "D1", "blocks_export": True})
    _expect_reject(tmp_path, doc, "D0⇔blocks_export")


def test_reject_id_prefix_skill_mismatch(tmp_path):
    doc = _valid_registry()
    doc["assertions"][0]["skill"] = "BL"  # id 仍是 SK-CMN-005
    _expect_reject(tmp_path, doc, "前缀")


def test_reject_dangling_delegates(tmp_path):
    doc = _valid_registry()
    doc["assertions"].append(
        {"id": "SK-AI-009", "skill": "AI", "name": "负证据留痕", "level": "D0", "blocks_export": True, "rule_ref": None, "expr": "x", "human_action": "补", "delegates_to": "SK-CMN-999"}
    )
    _expect_reject(tmp_path, doc, "悬空")


def test_reject_delegate_chain_over_one_hop(tmp_path):
    doc = _valid_registry()
    doc["assertions"].append(
        {"id": "SK-AI-009", "skill": "AI", "name": "负证据留痕", "level": "D0", "blocks_export": True, "rule_ref": None, "expr": "x", "human_action": "补", "delegates_to": "SK-CMN-005"}
    )
    doc["assertions"][0]["delegates_to"] = "SK-AI-009"
    _expect_reject(tmp_path, doc, "一跳")


def test_reject_delegate_target_non_cmn(tmp_path):
    doc = _valid_registry()
    doc["assertions"][0] = {
        "id": "SK-AI-001", "skill": "AI", "name": "编号唯一", "level": "D0", "blocks_export": True, "rule_ref": None, "expr": "x", "human_action": "补"
    }
    doc["assertions"].append(
        {"id": "SK-AI-002", "skill": "AI", "name": "要求对齐", "level": "D0", "blocks_export": True, "rule_ref": None, "expr": "x", "human_action": "补", "delegates_to": "SK-AI-001"}
    )
    _expect_reject(tmp_path, doc, "CMN 共享层")


def test_reject_missing_levels_row(tmp_path):
    doc = _valid_registry()
    del doc["levels"]["D3"]
    _expect_reject(tmp_path, doc, "levels 行为表缺 D3")


def test_reject_d1_blk_true(tmp_path):
    doc = _valid_registry()
    doc["levels"]["D1"]["blk"] = True
    _expect_reject(tmp_path, doc, "D1 行 blk")


def test_load_valid_registry_ok(tmp_path):
    snap = _load(_write(tmp_path, _valid_registry()))
    assert [a.id for a in snap.assertions] == ["SK-CMN-005"]
    assert snap.levels["D0"]["blk"] is True
