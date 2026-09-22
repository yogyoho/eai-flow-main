"""动作层 schema 单测（Task 2）：ActionSpec 解析 + 交叉引用 fail-closed 校验.

设计: docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §1.1 / §3
计划: docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md Task 2
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ontology.schemas import ActionSpec, DomainFile, StateChange


def _ot(api_name="graph_entity", domain="doc_graph"):
    return {
        "api_name": api_name, "display_name": "实体", "description": "d", "domain": domain,
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [
            {"name": "id", "api_name": "id", "type": "uuid", "description": "pk"},
            {"name": "status", "api_name": "status", "type": "string", "description": "s"},
        ],
    }


def _action(**over):
    base = {
        "id": "review_entity.confirm", "display_name": "确认实体", "description": "d",
        "domain": "doc_graph", "target": "graph_entity",
        "required_permissions": ["ontology:action:review"],
        "preconditions": [{"field": "status", "op": "eq", "value": "pending_review"}],
        "postconditions": [{"field": "status", "set": "active"}],
    }
    base.update(over)
    return base


def test_valid_domain_parses_with_actions():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action()]})
    assert d.actions[0].id == "review_entity.confirm"
    assert d.actions[0].behavior_type == "COMMAND"


def test_unknown_target_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(target="nope")]})
    with pytest.raises(ValueError, match="unknown action target"):
        d.validate_action_refs()


def test_unknown_field_rejected():
    d = DomainFile.model_validate({
        "object_types": [_ot()],
        "actions": [_action(postconditions=[{"field": "nosuch", "set": 1}])],
    })
    with pytest.raises(ValueError, match="unknown action field"):
        d.validate_action_refs()


def test_empty_postconditions_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(postconditions=[]))


def test_illegal_op_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(preconditions=[{"field": "status", "op": "drop", "value": 1}]))


def test_set_and_now_mutually_exclusive():
    with pytest.raises(ValidationError, match="set 与 now"):
        ActionSpec.model_validate(_action(postconditions=[{"field": "status", "set": "x", "now": True}]))


def test_neither_set_nor_now_rejected():
    """互斥是「二选一」而非「至多一个」：两者同时缺省同样拒绝。"""
    with pytest.raises(ValidationError, match="set 与 now"):
        StateChange.model_validate({"field": "status"})


def test_required_permissions_must_not_be_empty():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(required_permissions=[]))


def test_duplicate_action_id_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(), _action()]})
    with pytest.raises(ValueError, match="duplicate action id"):
        d.validate_action_refs()


def test_scope_bindings_must_reference_declared_property():
    ot = _ot()
    ot["scope_resource"] = "ontology"
    ot["scope_bindings"] = {"user_id": "nosuch_column"}
    d = DomainFile.model_validate({"object_types": [ot], "actions": []})
    with pytest.raises(ValueError, match="unknown scope binding"):
        d.validate_action_refs()
