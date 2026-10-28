"""Condition / handler expression tests (warm-flow wire format)."""

from __future__ import annotations

import pytest

from app.engine.definition import validate_flow
from app.engine.errors import WorkflowError
from app.engine.expression import evaluate_condition, expression_label, resolve_handlers


@pytest.mark.parametrize(
    ("expression", "variables", "expected"),
    [
        ("eq@@flag|4", {"flag": 4}, True),
        ("eq@@flag|4", {"flag": "4"}, True),
        ("ne@@flag|4", {"flag": 5}, True),
        ("gt@@amount|5000", {"amount": 5001}, True),
        ("gt@@amount|5000", {"amount": "5000"}, False),
        ("ge@@amount|5000", {"amount": 5000}, True),
        ("lt@@days|3", {"days": 2}, True),
        ("le@@days|3", {"days": 4}, False),
        ("like@@name|zhang", {"name": "zhangsan"}, True),
        ("notLike@@name|li", {"name": "zhangsan"}, True),
        ("default@@anything", {}, True),
        ("le@@amount|5000 || gt@@amount|8000", {"amount": 9000}, True),
        ("eq@@missing|1", {}, False),
    ],
)
def test_conditions(expression: str, variables: dict, expected: bool) -> None:
    assert evaluate_condition(expression, variables) is expected


def test_spel_is_a_safe_subset() -> None:
    assert evaluate_condition("spel@@#{amount > 100 and level == 'vip'}", {"amount": 200, "level": "vip"})
    assert not evaluate_condition("spel@@#{amount > 100}", {"amount": 20})
    # Attribute access, calls and imports are not evaluated to anything truthy.
    assert not evaluate_condition("spel@@#{().__class__.__bases__[0].__subclasses__()}", {})
    assert not evaluate_condition("spel@@#{__import__('os').system('echo hacked')}", {})


def test_handler_expressions() -> None:
    assert resolve_handlers("u1001@@u1002") == ["u1001", "u1002"]
    assert resolve_handlers("${approver}", {"approver": "u1003"}) == ["u1003"]
    assert resolve_handlers("role:manager@@${extra}", {"extra": "u1004,u1005"}) == [
        "role:manager",
        "u1004",
        "u1005",
    ]
    assert resolve_handlers("spel@@#{handlers}", {"handlers": ["u1001", "u1002"]}) == ["u1001", "u1002"]


def test_expression_label() -> None:
    assert expression_label(None) == "默认分支"
    assert expression_label("gt@@amount|5000") == "amount gt 5000"
    assert expression_label("spel@@#{a > 1}") == "#{a > 1}"


def _node(code: str, node_type: int, skip_to: str | None = None, skip_type: str = "PASS") -> dict:
    return {
        "nodeCode": code,
        "nodeType": node_type,
        "skipList": ([{"nowNodeCode": code, "nextNodeCode": skip_to, "skipType": skip_type}] if skip_to else []),
    }


def test_validate_flow_accepts_minimal_graph() -> None:
    nodes, skips = validate_flow(
        {
            "flowCode": "demo",
            "flowName": "Demo",
            "nodeList": [
                _node("start", 0, "approve"),
                _node("approve", 1, "end"),
                _node("end", 2),
            ],
        }
    )
    assert len(nodes) == 3
    assert len(skips) == 2


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"flowCode": "", "flowName": "x", "nodeList": []}, "flowCode"),
        ({"flowCode": "x", "flowName": "x", "nodeList": []}, "没有节点"),
        (
            {
                "flowCode": "x",
                "flowName": "x",
                "nodeList": [_node("start", 0, "missing"), _node("end", 2)],
            },
            "不存在",
        ),
        (
            {
                "flowCode": "x",
                "flowName": "x",
                "nodeList": [_node("start", 0, "end"), _node("end", 2), _node("orphan", 1, "end")],
            },
            "不可达",
        ),
        (
            {
                "flowCode": "x",
                "flowName": "x",
                "nodeList": [_node("end", 2)],
            },
            "缺少开始节点",
        ),
        (
            {
                "flowCode": "x",
                "flowName": "x",
                "nodeList": [_node("start", 0, "end"), _node("end", 2), _node("start2", 0, "end")],
            },
            "只能有一个开始节点",
        ),
    ],
)
def test_validate_flow_rejects_invalid_graphs(payload: dict, fragment: str) -> None:
    with pytest.raises(WorkflowError) as exc:
        validate_flow(payload)
    assert fragment in str(exc.value)


def test_validate_flow_accepts_multiple_end_nodes() -> None:
    nodes, _ = validate_flow(
        {
            "flowCode": "branch",
            "flowName": "Branch",
            "nodeList": [
                _node("start", 0, "gw"),
                {
                    "nodeCode": "gw",
                    "nodeType": 3,
                    "skipList": [
                        {"nowNodeCode": "gw", "nextNodeCode": "end_a", "skipType": "PASS"},
                        {"nowNodeCode": "gw", "nextNodeCode": "end_b", "skipType": "PASS"},
                    ],
                },
                _node("end_a", 2),
                _node("end_b", 2),
            ],
        }
    )
    assert len(nodes) == 4
