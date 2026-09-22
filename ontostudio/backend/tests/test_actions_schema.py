"""动作层 schema 单测（Task 2）：ActionSpec 解析 + 交叉引用 fail-closed 校验.

设计: docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §1.1 / §3
计划: docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md Task 2
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from app.ontology.schemas import ActionSpec, DomainFile, StateChange


def _ot(api_name="graph_entity", domain="doc_graph"):
    return {
        "api_name": api_name,
        "display_name": "实体",
        "description": "d",
        "domain": domain,
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [
            {"name": "id", "api_name": "id", "type": "uuid", "description": "pk"},
            {"name": "status", "api_name": "status", "type": "string", "description": "s"},
        ],
    }


def _action(**over):
    base = {
        "id": "review_entity.confirm",
        "display_name": "确认实体",
        "description": "d",
        "domain": "doc_graph",
        "target": "graph_entity",
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
    # Task 5 真正要消费的是条件里的值，不是 id/behavior_type 这两个常量——一并钉住
    assert d.actions[0].preconditions[0].value == "pending_review"
    assert d.actions[0].postconditions[0].set == "active"


def test_unknown_target_rejected():
    with pytest.raises(ValidationError, match="unknown action target"):
        DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(target="nope")]})


def test_unknown_field_rejected():
    with pytest.raises(ValidationError, match="unknown action field"):
        DomainFile.model_validate(
            {
                "object_types": [_ot()],
                "actions": [_action(postconditions=[{"field": "nosuch", "set": 1}])],
            }
        )


def test_unknown_precondition_field_rejected():
    """preconditions 与 postconditions 走同一条校验分支，两半都要钉住。"""
    with pytest.raises(ValidationError, match="unknown action field"):
        DomainFile.model_validate(
            {
                "object_types": [_ot()],
                "actions": [_action(preconditions=[{"field": "nosuch", "op": "eq", "value": 1}])],
            }
        )


@pytest.mark.parametrize("bad", ["Review_entity.confirm", "review", "a.b.c", "1review.confirm"])
def test_action_id_pattern_enforced(bad):
    """`<family>.<verb>` 两段小写：大写开头 / 无点 / 三段 / 数字开头 均拒绝。"""
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(id=bad))


def test_action_domain_must_match_target_domain():
    """M-2（范围外补强）：action.domain 会写进审计行，与 target 所属域不一致即拒绝。"""
    with pytest.raises(ValidationError, match="与 target 所属域"):
        DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(domain="WRONG_DOMAIN")]})


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
    with pytest.raises(ValidationError, match="duplicate action id"):
        DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(), _action()]})


def test_scope_bindings_must_reference_declared_property():
    ot = _ot()
    ot["scope_resource"] = "ontology"
    ot["scope_bindings"] = {"user_id": "nosuch_column"}
    with pytest.raises(ValidationError, match="unknown scope binding"):
        DomainFile.model_validate({"object_types": [ot], "actions": []})


def test_scope_bindings_valid_binding_accepted():
    """接受路径也要钉：把校验改成全拒（`if True: raise`）必须变红。

    与 `test_scope_bindings_must_reference_declared_property` 是一对——只测拒绝、不测接受
    时，校验器被改成"一律拒绝"同样全绿（盲区镜像）。
    """
    ot = _ot()
    ot["scope_resource"] = "ontology"
    ot["scope_bindings"] = {"user_id": "status"}  # status 是已声明列
    d = DomainFile.model_validate({"object_types": [ot], "actions": []})
    assert d.object_types[0].scope_bindings == {"user_id": "status"}


# ── Registry 加载路径 ────────────────────────────────────────────────────────
# 为什么需要这一组：真实 registry 的 YAML 到 Task 3 才会有 actions: 段，所以
# 全量测试里 RegistryStore 的 `for a in domain.actions:` 循环体一次都不执行——
# 即本任务声称的「核心」（按 id 索引的动作字典 + 跨文件重复守卫）在提交的测试里
# 零覆盖。用临时 registry 目录把它钉住，而不是靠一次性脚本。


def _write_registry(tmp_path, files: dict[str, str]):
    """最小 registry 目录：manifest + 各域文件。"""
    (tmp_path / "_manifest.yaml").write_text(
        "schema_version: 2\nhot_reload: true\nfiles:\n" + "".join(f"  - file: {n}\n" for n in files),
        encoding="utf-8",
    )
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_registry_exposes_actions_by_id(tmp_path):
    d = _write_registry(
        tmp_path,
        {
            "a.yaml": yaml.safe_dump({"object_types": [_ot()], "actions": [_action()]}, allow_unicode=True),
        },
    )
    from app.ontology.registry import RegistryStore

    reg = RegistryStore(registry_dir=d).get()
    assert reg.get_action("review_entity.confirm").target == "graph_entity"
    assert reg.get_action("nope.nope") is None


def test_cross_file_duplicate_action_id_rejected(tmp_path):
    """跨文件重复由加载器的合并循环兜住（文件内的由 DomainFile._check_refs 兜）。

    两个域各自声明**不同**对象类型（否则会先在对象类型重复注册处报错），
    但动作 id 相同——必须报「动作 id 跨域重复」。
    """
    d = _write_registry(
        tmp_path,
        {
            "a.yaml": yaml.safe_dump(
                {
                    "object_types": [_ot(api_name="graph_entity")],
                    "actions": [_action(id="dup.check", target="graph_entity")],
                },
                allow_unicode=True,
            ),
            "b.yaml": yaml.safe_dump(
                {
                    "object_types": [_ot(api_name="graph_entity2")],
                    "actions": [_action(id="dup.check", target="graph_entity2")],
                },
                allow_unicode=True,
            ),
        },
    )
    from app.ontology.registry import RegistryError, RegistryStore

    with pytest.raises(RegistryError, match="动作 id 跨域重复"):
        RegistryStore(registry_dir=d).get()


def test_loader_wraps_action_ref_error_with_filename(tmp_path):
    """坏动作声明 → RegistryError，且消息带文件名、带 schema 校验失败标识、无双冒号退化。

    这条钉的是 _validate_domain_file 的**消息格式**：动作引用错误由模型级 after-validator
    抛出，其根级 `loc` 是空 tuple，若照原样拼接会渲染成 `a.yaml: : Value error, ...`。
    该分支与既有 bogus_field 用例共用代码路径，但没有测试断言过动作错误经此渲染的结果——
    即「错误包装」本身缺乏护栏：改坏了不会有测试变红。
    """
    d = _write_registry(
        tmp_path,
        {
            "a.yaml": yaml.safe_dump(
                {"object_types": [_ot()], "actions": [_action(target="nope")]},
                allow_unicode=True,
            ),
        },
    )
    from app.ontology.registry import RegistryError, load_registry

    with pytest.raises(RegistryError, match="schema 校验失败") as ei:
        load_registry(d)
    msg = str(ei.value)
    assert "a.yaml" in msg, msg  # 定位到具体域文件
    assert ": :" not in msg, msg  # 根级 loc 为空 tuple 的双冒号退化
