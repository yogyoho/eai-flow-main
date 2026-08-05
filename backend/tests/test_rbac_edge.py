"""引擎边界：inherit 环检测 / not 组合 / overlap 空值 / knowledge scopes / bare-* 写拦截。"""
import uuid

import pytest
from fastapi import HTTPException

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.policy_routers import _validate_grants
from app.extensions.auth.registry import PermissionRegistry, get_permission_registry
from app.extensions.models import KnowledgeBase


def test_inherit_cycle_detected(tmp_path):
    main = tmp_path / "permissions.yaml"
    main.write_text(
        "version: 3\nmodules: {}\nroles:\n"
        "  a:\n    display_name: A\n    permissions: ['#inherit:b']\n    nav: []\n    data_scopes: []\n"
        "  b:\n    display_name: B\n    permissions: ['#inherit:a']\n    nav: []\n    data_scopes: []\n",
        encoding="utf-8",
    )
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    reg = PermissionRegistry(str(main), overlay_path=str(overlay))
    perms = reg.resolve_role_permissions("a")  # 环：不无限循环、不抛
    assert perms == set()


def test_not_over_allow_all_is_false():
    rule = FilterRule(operator="not", children=[FilterRule(operator="allow_all")])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    compiled = str(expr.compile()).lower()
    assert "false" in compiled  # NOT TRUE 被常量折叠 = FALSE（deny allow_all → 全否）


def test_not_over_none_allow_is_true():
    rule = FilterRule(operator="not", children=[FilterRule(operator="none_allow")])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    compiled = str(expr.compile()).lower()
    assert "true" in compiled  # NOT FALSE 被常量折叠 = TRUE（deny none → 全真）


def test_overlap_empty_value_false():
    rule = FilterRule(operator="overlap", field="allowed_depts", value=[])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"allowed_depts": KnowledgeBase.allowed_depts})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "false" in compiled  # 空值 → WHERE FALSE


def test_knowledge_scopes_declared():
    """三个真实 knowledge scope 必须声明（owner/public/dept）。

    注：spec §6 测试矩阵里的 knowledge_law_all 是历史残留名——kb_type(law) 分类型差异化
    已按 08-04 设计 §2 明确 deferred，yaml 现无该 scope；不为此造数据。
    """
    reg = get_permission_registry()
    for sid in ("knowledge_owner", "knowledge_public", "knowledge_dept"):
        assert reg.get_data_scope(sid) is not None, f"scope {sid} 未声明"
    assert reg.get_data_scope("knowledge_law_all") is None  # 已 deferred，确无此 scope


def test_bare_star_deny_rejected_on_write():
    with pytest.raises(HTTPException) as ei:
        _validate_grants({"deny_permissions": ["*"]}, get_permission_registry())
    assert ei.value.status_code == 400
