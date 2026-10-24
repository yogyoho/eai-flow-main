"""Pure domain rule tests for QW2.

These tests avoid a database on purpose: the rules under test are the stable
contracts that must survive future persistence refactors.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain import can_advance, compute_rule_probability, evaluate_gates, gates_blocked

PROBABILITY_CFG = {
    "base": {"S1": 10, "S2": 20, "S3": 35, "S4": 50, "S5": 60, "S6": 70, "S7": 80, "S8": 90, "S9": 100},
    "overdue_penalty_pp": 15,
    "max_penalty_pp": 20,
    "floor": 5,
}


class _EmptyResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    """Only implements the rule-config lookup used by STAGE_FIELDS/R9 tests."""

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        return _EmptyResult()


def full_opportunity(**overrides):
    values = {
        "customer_id": "customer-1",
        "product_line": "智能综采",
        "amount": Decimal("1000000"),
        "expected_close_date": date(2027, 1, 1),
        "owner_id": "owner-1",
        "stage": "S1",
        "result": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("from_stage", "to_stage", "expected"),
    [
        ("S1", "S2", True),
        ("S4", "S5", True),
        ("S8", "S9", True),
        ("S1", "S3", False),
        ("S5", "S4", False),
        ("S9", "S8", False),
        ("S1", "S1", False),
        ("S1", "S99", False),
    ],
)
def test_stage_machine_only_allows_adjacent_advances(from_stage, to_stage, expected):
    assert can_advance(from_stage, to_stage) is expected


def test_probability_uses_stage_base():
    assert compute_rule_probability("S4", None, PROBABILITY_CFG) == Decimal("50")
    assert compute_rule_probability("S9", None, PROBABILITY_CFG) == Decimal("100")


def test_probability_applies_overdue_penalty_once():
    now = datetime(2026, 10, 22, tzinfo=UTC)
    overdue_by = now - timedelta(days=1)
    assert compute_rule_probability("S4", overdue_by, PROBABILITY_CFG, now) == Decimal("35")


def test_probability_honours_floor():
    now = datetime(2026, 10, 22, tzinfo=UTC)
    overdue_by = now - timedelta(days=120)
    cfg = {**PROBABILITY_CFG, "base": {**PROBABILITY_CFG["base"], "S1": 5}}
    assert compute_rule_probability("S1", overdue_by, cfg, now) == Decimal("5")


@pytest.mark.asyncio
async def test_stage_fields_block_until_required_data_is_complete():
    opp = full_opportunity(expected_close_date=None)
    gates = await evaluate_gates(_FakeDB(), opp, "S2")
    stage_gate = next(g for g in gates if g["gate_code"] == "STAGE_FIELDS")
    assert stage_gate["status"] == "block"
    assert stage_gate["evidence"]["missing"] == ["expected_close_date"]
    assert gates_blocked(gates)


@pytest.mark.asyncio
async def test_stage_fields_pass_when_required_data_is_complete():
    gates = await evaluate_gates(_FakeDB(), full_opportunity(), "S2")
    stage_gate = next(g for g in gates if g["gate_code"] == "STAGE_FIELDS")
    assert stage_gate["status"] == "pass"
    assert not gates_blocked(gates)


@pytest.mark.asyncio
async def test_r9_requires_result_before_s8():
    opp = full_opportunity(stage="S7")
    gates = await evaluate_gates(_FakeDB(), opp, "S8")
    assert any(g["gate_code"] == "R9" and g["status"] == "block" for g in gates)


@pytest.mark.asyncio
async def test_r9_requires_lost_reason_for_lost_result():
    opp = full_opportunity(stage="S7")
    gates = await evaluate_gates(_FakeDB(), opp, "S8", result="lost")
    assert any(g["gate_code"] == "R9" and g["action"] == "set_lost_reason" for g in gates)
