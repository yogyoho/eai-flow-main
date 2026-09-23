"""Task 9 单测：lint 的三类动作层检查（无 DB，纯模型 + 注册表快照）.

计划: docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md「## Task 9」

  ① `check_scope_resources` —— 已声明的 `scope_resource` 必须是已知权限模块 key
     （**缺绑定永远绿**：`test_object_without_scope_resource_is_fine` 是这条口径的显式祝福）。
  ② `check_action_reachable_objects_are_scoped` —— 动作层可达的对象类型必须声明
     `scope_resource`（本计划四次"被推迟的项没人认领"的结构性对治；第四次 graph_relation
     漏绑正是这个检查的形状）。
  ③ `check_action_preconditions` —— 动作前置条件的 `value` 形状（`sql_write` 的守卫只在
     invoke 时拒，那是 400；这些是加载期就能查出来的静态错误）。
"""

from __future__ import annotations

from app.ontology.registry import Registry
from app.ontology.schemas import ActionSpec, DomainFile, LinkType, Manifest, ObjectType, Precondition


def _ot(**over) -> dict:
    base = {
        "api_name": "graph_entity",
        "display_name": "实体",
        "description": "d",
        "domain": "doc_graph",
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
    }
    base.update(over)
    return base


def _obj(**over) -> ObjectType:
    return ObjectType.model_validate(_ot(**over))


def _link(source: str, target: str, *, enabled: bool = True, **over) -> LinkType:
    base = {
        "api_name": f"{source}_to_{target}",
        "display_name": "l",
        "source": source,
        "target": target,
        "cardinality": "N:1",
        "reverse": f"{target}_to_{source}",
        "enabled": enabled,
        "join": {"type": "foreign_key", "source_column": "id", "target_column": "id"},
    }
    base.update(over)
    return LinkType.model_validate(base)


def _action(**over) -> ActionSpec:
    base = {
        "id": "review_entity.confirm",
        "display_name": "确认",
        "description": "d",
        "domain": "doc_graph",
        "target": "graph_entity",
        "required_permissions": ["ontology:action:review"],
        "preconditions": [],
        "postconditions": [{"field": "status", "set": "active"}],
    }
    base.update(over)
    return ActionSpec.model_validate(base)


def _registry(objects=(), links=(), actions=()) -> Registry:
    """真 `Registry`（非 FakeReg）——检查函数读的正是 `object_types`/`link_types`/`actions` 三张扁平表。"""
    return Registry(
        manifest=Manifest.model_validate({"schema_version": 1, "files": [{"file": "t.yaml"}]}),
        object_types={o.api_name: o for o in objects},
        link_types={lt.api_name: lt for lt in links},
        file_fingerprints={},
        registry_version=1,
        actions={a.id: a for a in actions},
    )


# ────────────────────────── ① scope_resource 值域 ──────────────────────────


def test_object_without_scope_resource_is_fine():
    DomainFile.model_validate({"object_types": [_ot()]})


def test_scope_resource_requires_known_module():
    """scope_resource 必须是已知模块 key（离线模板也要有）。"""
    from scripts.ontology_lint import check_scope_resources

    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="no_such_module")]})
    problems = check_scope_resources(d, known_modules={"ontology", "contract_price"})
    assert problems and "no_such_module" in problems[0]


def test_scope_resource_known_module_passes():
    from scripts.ontology_lint import check_scope_resources

    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="ontology")]})
    assert check_scope_resources(d, known_modules={"ontology"}) == []


# ────────────────────── ② 动作层可达者必须绑定 scope_resource ──────────────────────


def test_action_target_without_scope_resource_is_flagged():
    """验收：被动作引用却没绑 → 必须报错（这是这个检查存在的全部理由）。"""
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(objects=[_obj()], actions=[_action(target="graph_entity")])
    problems = check_action_reachable_objects_are_scoped(reg)
    assert problems and "graph_entity" in problems[0]


def test_object_linked_to_action_target_must_be_scoped():
    """第四次复发的形状：graph_relation 是**链接端点**（非动作 target），漏绑也应被抓。"""
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(
        objects=[_obj(api_name="graph_entity", scope_resource="ontology"), _obj(api_name="graph_relation")],
        links=[_link("graph_relation", "graph_entity")],
        actions=[_action(target="graph_entity")],
    )
    problems = check_action_reachable_objects_are_scoped(reg)
    assert problems and "graph_relation" in problems[0]


def test_reachability_is_transitive():
    """可达是闭包：neighbour 已绑，但它再连到的对象未绑 → 仍报。"""
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(
        objects=[
            _obj(api_name="graph_entity", scope_resource="ontology"),
            _obj(api_name="graph_relation", scope_resource="ontology"),
            _obj(api_name="graph_mention"),
        ],
        links=[_link("graph_relation", "graph_entity"), _link("graph_mention", "graph_relation")],
        actions=[_action(target="graph_entity")],
    )
    problems = check_action_reachable_objects_are_scoped(reg)
    assert len(problems) == 1 and "graph_mention" in problems[0]


def test_scoped_action_layer_is_clean():
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(
        objects=[_obj(scope_resource="ontology"), _obj(api_name="graph_relation", scope_resource="ontology")],
        links=[_link("graph_relation", "graph_entity")],
        actions=[_action()],
    )
    assert check_action_reachable_objects_are_scoped(reg) == []


def test_disabled_link_does_not_extend_reachability():
    """`enabled: false` 是 D3 stub——遍历拒绝，故不把可达面撑到它上面。"""
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(
        objects=[_obj(scope_resource="ontology"), _obj(api_name="graph_mention")],
        links=[_link("graph_mention", "graph_entity", enabled=False)],
        actions=[_action()],
    )
    assert check_action_reachable_objects_are_scoped(reg) == []


def test_unreachable_unbound_object_is_not_flagged():
    """口径的边界（有意收窄，见检查函数 docstring）：与动作层无关的只读对象不在射程内。"""
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(
        objects=[_obj(scope_resource="ontology"), _obj(api_name="contract_item", domain="contract_price")],
        links=[],
        actions=[_action()],
    )
    assert check_action_reachable_objects_are_scoped(reg) == []


def test_registry_without_actions_is_clean():
    from scripts.ontology_lint import check_action_reachable_objects_are_scoped

    reg = _registry(objects=[_obj(api_name="contract_item", domain="contract_price")], links=[])
    assert check_action_reachable_objects_are_scoped(reg) == []


# ───────────────────────── ③ 前置条件 value 的作者笔误 ─────────────────────────


def _pre_errors(precondition: dict) -> list[str]:
    from scripts.ontology_lint import check_action_preconditions

    reg = _registry(objects=[_obj()], actions=[_action(preconditions=[precondition])])
    return check_action_preconditions(reg)


def test_in_with_scalar_value_is_flagged():
    """`value: rejected`（漏引号 → YAML 给字符串）：自然写法，实为 400 的静态版。"""
    problems = _pre_errors({"field": "status", "op": "not_in", "value": "rejected"})
    assert problems and "not_in" in problems[0] and "status" in problems[0]


def test_in_with_empty_list_is_flagged():
    problems = _pre_errors({"field": "status", "op": "in", "value": []})
    assert problems and "op=in" in problems[0]


def test_in_with_number_is_flagged():
    problems = _pre_errors({"field": "status", "op": "in", "value": 123})
    assert problems and "op=in" in problems[0]


def test_in_without_value_is_flagged():
    problems = _pre_errors({"field": "status", "op": "in"})
    assert problems and "op=in" in problems[0]


def test_eq_without_value_is_flagged():
    problems = _pre_errors({"field": "status", "op": "eq"})
    assert problems and "op=eq" in problems[0]


def test_eq_with_explicit_null_is_flagged():
    """`eq: null` 与漏 value 同罪——两者都编译不出有意义的谓词（应改用 is_null）。"""
    problems = _pre_errors({"field": "status", "op": "eq", "value": None})
    assert problems and "op=eq" in problems[0]


def test_is_null_carrying_value_is_flagged():
    problems = _pre_errors({"field": "status", "op": "is_null", "value": "active"})
    assert problems and "op=is_null" in problems[0]


def test_wellformed_preconditions_pass():
    assert _pre_errors({"field": "status", "op": "eq", "value": "pending_review"}) == []
    assert _pre_errors({"field": "status", "op": "in", "value": ["a", "b"]}) == []
    assert _pre_errors({"field": "status", "op": "is_null"}) == []
    assert _pre_errors({"field": "status", "op": "not_null"}) == []


def test_falsy_but_legal_values_are_not_flagged():
    """`value: false` / `value: 0` 合法——判据是「非 None」，不是真值。"""
    assert _pre_errors({"field": "status", "op": "eq", "value": False}) == []
    assert _pre_errors({"field": "status", "op": "eq", "value": 0}) == []


def test_precondition_value_types_are_tuple_set_friendly():
    """`in` 的值来自 pydantic `Any`，tuple/set 也算合法形状（只拒空、拒非序列）。"""
    from scripts.ontology_lint import check_action_preconditions

    pre = Precondition.model_validate({"field": "status", "op": "in", "value": ("a", "b")})
    reg = _registry(objects=[_obj()], actions=[_action(preconditions=[pre])])
    assert check_action_preconditions(reg) == []
