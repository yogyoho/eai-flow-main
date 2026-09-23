"""数据范围端点 ``GET /api/permissions/scope`` + 跨服务 wire 契约 golden。

EAI-CUSTOM (2026-09-22): 本体动作层经本端点取序列化的 ``FilterRule`` 做实例级判定
（设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3）。

本文件守三件事：
① 端点各态（``none_allow`` / ``allow_all`` / **非退化规则**）与未知资源 fail-closed；
② 身份走正典 ``IdentityProvider.resolve``（I-3）——``dept_ids`` 取 ``user_departments``
   关联表而非 ``users.dept_id``，两者不等价，用能区分二者的用例钉住；
③ **跨服务 wire 契约**（I-2）：golden 由产出侧代码生成，本文件断 ``to_wire == golden``，
   消费侧（ontostudio/backend/tests/test_scope_wire_contract.py）断 ``from_wire(golden)`` 可编译。

**已删除**（审查裁定 2026-09-23）：``AuthzCache`` 及其 3 条测试。理由：该缓存**零消费者**
（gateway 的判定是本地 registry+DB，不需要它；需要缓存的是 OntoStudio——那边每次判定都是
一次跨服务 HTTP，已在 ontostudio/backend/tests/test_main.py 用变异证明有效的那条守着）。
"留着将来接线"不成立：接进 ``require_permission`` 等于给平台引入**进程级 30s 缓存**
（权限吊销延迟 30s）——那是语义变更，不是接线，须独立评审。
"""

from __future__ import annotations

import logging

import _wire_golden
import pytest
from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_rows_db

from app.extensions.auth.permission_routers import router

# ── /api/permissions/scope ────────────────────────────────────────────

SCOPE = "/api/permissions/scope"


def test_scope_endpoint_none_allow_for_role_without_scope(monkeypatch):
    """能访问本体（有 system:access）但角色不带 ontology_all → none_allow。

    这是 spec §3 的"今日实际形态"：本体表无身份列，故带 ``ontology_all`` 的角色解析为
    ``allow_all``、不带者为 ``none_allow``，二者之间**没有中间态**。本体动作层的
    ``ontology_all`` 正是靠本条的反向（返回 none_allow ⇒ 动作恒 404）成立。
    """
    patch_identity(monkeypatch, fake_identity("user"))
    r = build_app(router, user=make_user(role_name="普通用户"), db=policy_rows_db()).get(SCOPE, params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json() == {"resource": "ontology", "rule": {"operator": "none_allow"}}


def test_scope_endpoint_allow_all_for_role_with_ontology_all(monkeypatch):
    """角色带 ontology_all（rule_template: {}）→ allow_all（空模板 = 全量）。"""
    patch_identity(monkeypatch, fake_identity("superadmin"))
    r = build_app(router, user=make_user(role_name="超级管理员"), db=policy_rows_db()).get(SCOPE, params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json() == {"resource": "ontology", "rule": {"operator": "allow_all"}}


def test_scope_endpoint_unknown_resource_is_none_allow(monkeypatch, caplog):
    """未知资源 fail-closed，且**留痕**（M-3）：typo 与"角色没配 scope"今天都产出
    ``none_allow``，调用方只看到 404 分不清是哪种；注册表能区分"模块不存在"，那就别让它静默。"""
    patch_identity(monkeypatch, fake_identity("superadmin"))
    with caplog.at_level(logging.WARNING):
        r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "no_such_module"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] == "none_allow"
    assert any("no_such_module" in rec.getMessage() for rec in caplog.records), caplog.text


def test_scope_endpoint_requires_system_access(monkeypatch):
    """M-1：本端点此前只挂 ``get_current_user``，比同 router 的 ``/registry``(role:read)、
    ``/me``(system:access) 松一档。角色解析不出来（被禁用/已删除的自定义角色）→ 403。"""
    patch_identity(monkeypatch, fake_identity("no_such_role"))
    r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "ontology"})
    assert r.status_code == 403


def test_scope_endpoint_non_degenerate_rule_for_docmgr(monkeypatch):
    """**非退化规则**：docmgr 的两条 scope 合成 ``or`` 复合树。

    为什么必须有这条（审查者指出）：此前三条端点测试只产出 ``none_allow`` / ``allow_all``
    两个退化形态——**复合树、``in`` 的取值、字段名一个都没被端点路径覆盖过**。
    ``docmgr`` 同时有 ``doc_owner``(eq user_id) 与 ``doc_project_member``(in project_id)，
    而 ``writer`` 角色的 data_scopes 两者都带（``user`` 只带 ``doc_owner``，会退化成单 scope），
    正好把 or + eq + in 一次覆盖。
    """
    patch_identity(monkeypatch, fake_identity("writer", user_id="U-1", member_projects=["P-1", "P-2"]))
    r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "docmgr"})
    assert r.status_code == 200
    assert r.json() == {
        "resource": "docmgr",
        "rule": {
            "operator": "or",
            "children": [
                {"operator": "eq", "field": "user_id", "value": "U-1"},
                {"operator": "in", "field": "project_id", "value": ["P-1", "P-2"]},
            ],
        },
    }


def test_scope_endpoint_dept_ids_come_from_relation_table(monkeypatch):
    """I-3 的靶子：``dept_ids`` 必须来自正典 ``resolve``。

    ``contract_price.cpa_dept`` 的模板是 ``dept_id IN $identity.dept_ids``，``dept_head``
    角色的 data_scopes 带 ``cpa_dept``（且不带 ``cpa_all``，故只有这一支生效）。
    正典身份的 ``dept_ids`` 取自 ``user_departments`` **关联表**；端点此前自建
    ``AttributeSet.from_current_user`` 取的是 ``users.dept_id``（单值）——两者对"dept_id 有值
    但关联表无行"的用户不同。

    变异检验：把端点换回 ``from_current_user`` + 手工 ``db.get(Role, …)`` → ``dept_ids`` 变空
    → 本用例红（下一条断言同时钉住空集形态与取值形态，二者不能互串）。
    """
    patch_identity(monkeypatch, fake_identity("dept_head", dept_ids=["D-1", "D-2"]))
    r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "contract_price"})
    assert r.status_code == 200
    assert r.json()["rule"] == {"operator": "in", "field": "dept_id", "value": ["D-1", "D-2"]}


# ── 跨服务 wire 契约（I-2）─────────────────────────────────────────────


def test_wire_golden_matches_producer_output():
    """产出侧钉子：``to_wire()`` 必须逐字等于 golden。

    golden 由 ``tests/_wire_golden.py`` 用**产出侧真实构造路径**生成（见其 docstring），
    本断言是"产出侧改了形状就变红"的那一半。另一半在消费侧
    （ontostudio/backend/tests/test_scope_wire_contract.py）。

    为什么不能只靠消费侧：``from_wire`` 刻意宽容（``children: null`` 与 ``[]`` 都吃），
    只钉接受侧会掩盖漂移；而只钉产出侧又漏掉"消费侧读不懂新形状"。两侧都要。
    """
    golden = _wire_golden.load()
    actual = {name: rule.to_wire() for name, rule in _wire_golden.build_cases().items()}

    assert set(actual) == set(golden["cases"]), "golden 与产出侧用例集不一致（增删形态必须同时更新两侧）"
    for name, wire in actual.items():
        assert wire == golden["cases"][name], f"case {name!r} 的线格式已漂移"


def test_wire_golden_is_json_serializable():
    """线格式必须是纯 JSON 可序列化的——真实出口是 HTTP JSON。

    这条抓的是 M-4 那类：``overlap`` 的 value 由 ``from_template`` 强转为 ``uuid.UUID``，
    不归一成字符串时**连 golden 都生成不出来**（``json.dumps`` 直接 TypeError）。此前靠
    FastAPI 的 ``jsonable_encoder`` 兜着，非 FastAPI 消费点则拿到 UUID 对象。
    """
    import json

    json.dumps(_wire_golden.load())  # golden 自身
    json.dumps({name: rule.to_wire() for name, rule in _wire_golden.build_cases().items()})


@pytest.mark.parametrize("case", ["overlap"])
def test_to_wire_normalizes_uuid_values_to_str(case):
    """M-4 直钉：``overlap`` 的 ``value`` 元素是 ``uuid.UUID``（from_template 强转），
    ``to_wire`` 必须在函数内归一为 ``str``——不同调用路径拿到同一类型。"""
    wire = _wire_golden.build_cases()[case].to_wire()
    assert all(isinstance(v, str) for v in wire["value"]), wire
