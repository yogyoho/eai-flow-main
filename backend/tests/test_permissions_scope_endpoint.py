"""数据范围端点 ``GET /api/permissions/scope`` + 跨服务 wire 契约 golden。

EAI-CUSTOM (2026-09-22): 本体动作层经本端点取序列化的 ``FilterRule`` 做实例级判定
（设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3）。

本文件守四件事：
① 端点各态（``none_allow`` / ``allow_all`` / **非退化规则**）与未知资源 fail-closed；
② 身份走正典 ``IdentityProvider.resolve``（I-3）——``dept_ids`` 取 ``user_departments``
   关联表而非 ``users.dept_id``，两者不等价，用能区分二者的用例钉住；
③ **跨服务 wire 契约**（I-2）：golden 由产出侧代码生成，本文件断 ``to_wire == golden``，
   消费侧（ontostudio/backend/tests/test_scope_wire_contract.py）断 ``from_wire(golden)`` 可编译；
④ **与 ``with_data_scope`` 判定一致**（Task 7 硬性验收项，2026-09-23）：两侧逐态相等——
   含 ``deny_data_scopes`` 扣减态与无 deny 对照态。此前 ``/scope`` 自建判定、缺超管旁路与
   deny 扣减（后者 fail-open）。

**已删除**（审查裁定 2026-09-23）：``AuthzCache`` 及其 3 条测试。理由：该缓存**零消费者**
（gateway 的判定是本地 registry+DB，不需要它；需要缓存的是 OntoStudio——那边每次判定都是
一次跨服务 HTTP，已在 ontostudio/backend/tests/test_main.py 用变异证明有效的那条守着）。
"留着将来接线"不成立：接进 ``require_permission`` 等于给平台引入**进程级 30s 缓存**
（权限吊销延迟 30s）——那是语义变更，不是接线，须独立评审。
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import _wire_golden
import pytest
from fastapi import APIRouter, Depends
from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_row, policy_rows_db

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import with_data_scope
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
    """超管 → ``allow_all``。

    ⚠️ **本用例现在由超管旁路产生该结果，不再由 ``ontology_all`` 的空模板产生**（Task 7
    硬性验收项补齐旁路后）——超管的 ``data_scopes`` 里有没有 ``ontology_all`` 都已不影响这条
    断言。空模板 ⇒ allow_all 的覆盖改由
    ``test_scope_endpoint_matches_with_data_scope_when_scopes_present`` 里的**非超管**角色承担
    （本仓没有任何非超管角色配了 ``ontology_all``，只能用 overlay 造）。docstring 必须写明这点，
    否则它会静默宣称一份已失去的覆盖。
    """
    patch_identity(monkeypatch, fake_identity("superadmin"))
    r = build_app(router, user=make_user(role_name="超级管理员"), db=policy_rows_db()).get(SCOPE, params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json() == {"resource": "ontology", "rule": {"operator": "allow_all"}}


def test_scope_endpoint_unknown_resource(monkeypatch, caplog):
    """未知资源：非系统角色 ``none_allow``（fail-closed）／超管 ``allow_all``；两种都**留痕**。

    留痕（M-3）：typo 与"角色没配 scope"今天都产出 ``none_allow``，调用方只看到 404 分不清是
    哪种；注册表能区分"模块不存在"，那就别让它静默。

    ⚠️ 超管那一支是 Task 7 硬性验收项**改变**的行为（此前本例只断言前一支，且用的是超管身份
    ——旁路补齐后那条断言会红）。判据：``with_data_scope("no_such_module")`` 对超管同样返回
    ``allow_all``（旁路排在 ``get_data_scope`` **之前**，资源存不存在根本到不了那一步），
    而"两侧一致"是本任务明文的第一目标——**一致性优先于"未知资源一律 none_allow"** 那句更早的
    口号，否则同一个超管会在两侧拿到相反答案。非超管那一支不受影响，仍是 fail-closed。
    """
    with caplog.at_level(logging.WARNING):
        patch_identity(monkeypatch, fake_identity("user"))
        r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "no_such_module"})
        assert r.status_code == 200
        assert r.json()["rule"]["operator"] == "none_allow"
        assert any("no_such_module" in rec.getMessage() for rec in caplog.records), caplog.text

    with caplog.at_level(logging.WARNING):
        patch_identity(monkeypatch, fake_identity("superadmin"))
        r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "no_such_module"})
        assert r.json()["rule"]["operator"] == "allow_all", "超管旁路与 with_data_scope 保持一致"
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
    正典身份的 ``dept_ids`` 取自 ``user_departments`` **关联表**；端点此前自建身份时取的是
    ``users.dept_id``（单值）——两者对"dept_id 有值但关联表无行"的用户不同（那个自建入口已
    随 I-3 删除）。

    变异检验：把端点换回自建身份 + 手工 ``db.get(Role, …)`` → ``dept_ids`` 变空 → 本用例红
    （下一条断言同时钉住空集形态与取值形态，二者不能互串）。
    """
    patch_identity(monkeypatch, fake_identity("dept_head", dept_ids=["D-1", "D-2"]))
    r = build_app(router, user=make_user(), db=policy_rows_db()).get(SCOPE, params={"resource": "contract_price"})
    assert r.status_code == 200
    assert r.json()["rule"] == {"operator": "in", "field": "dept_id", "value": ["D-1", "D-2"]}


# ── 与 with_data_scope 的一致性（Task 7 硬性验收项）──────────────────────
# 为什么单列一节：``/scope`` 与 ``with_data_scope`` 是**同一个判定的两个出口**
# （前者喂 OntoStudio 的动作层，后者喂 gateway 自己的读路径）。它们漂移过一次，而漂移的
# 那一半是 fail-open——见 middleware.resolve_data_scope 的 docstring。此后任何一侧的改动
# 都必须让下面这些「两侧一致」断言保持绿；只钉一侧的断言挡不住漂移。

_ONTOLOGY_REVIEWER_YAML = """
roles:
  ontology_reviewer:
    display_name: "本体审核员"
    is_system: false
    level: 30
    permissions: ["system:access", "ontology:action:review"]
    data_scopes: ["ontology_all"]
"""


def _registry_with_ontology_reviewer(tmp_path):
    """真实 permissions.yaml + overlay 造一个**非超管**且持 ``ontology_all`` 的角色。

    为什么必须用 overlay：仓里的 ``ontology_all`` 只给了 ``superadmin``（``is_system: true``），
    而超管在两侧都走旁路——用超管测"deny 扣减"根本测不到扣减那一步。
    """
    from app.extensions.auth.registry import PermissionRegistry

    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text(_ONTOLOGY_REVIEWER_YAML, encoding="utf-8")
    main = Path(__file__).resolve().parents[2] / "config" / "permissions.yaml"
    return PermissionRegistry(str(main), overlay_path=str(overlay))


def _patch_registry(monkeypatch, registry) -> None:
    """让两侧都读到同一个 registry（逐个模块探测，同 rbac_helpers.patch_identity 的手法）。"""
    for mod_name in (
        "app.extensions.auth.registry",
        "app.extensions.auth.datascope",
        "app.extensions.auth.permission_routers",
    ):
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "get_permission_registry"):
            monkeypatch.setattr(mod, "get_permission_registry", lambda: registry)


def _http_scope_rule(monkeypatch, user, db) -> dict:
    """经 HTTP 打 ``/api/permissions/scope``（OntoStudio 实际消费的那条出口）。

    同一个 app 里再挂一条 ``with_data_scope("ontology")`` 探针——两侧同 app 同装置，
    差异只可能来自判定本身，不会来自装置。
    """
    probe = APIRouter()

    @probe.get("/probe/ontology-scope")
    async def _probe(scope: FilterRule = Depends(with_data_scope("ontology"))):  # noqa: B008
        return {"resource": "ontology", "rule": scope.to_wire()}

    combined = APIRouter()
    combined.include_router(router)
    combined.include_router(probe)

    http = build_app(combined, user=user, db=db)
    r = http.get(SCOPE, params={"resource": "ontology"})
    assert r.status_code == 200, r.text
    p = http.get("/probe/ontology-scope")
    assert p.status_code == 200, p.text
    return r.json()["rule"], p.json()["rule"]


async def _platform_rule(user, db) -> FilterRule:
    """平台正典出口：``with_data_scope`` 依赖直调（既有直测同款，见 test_with_data_scope_middleware.py）。"""
    return await with_data_scope("ontology")(current_user=user, db=db)


@pytest.mark.asyncio
async def test_scope_endpoint_matches_with_data_scope_under_deny_policy(monkeypatch, tmp_path):
    """**硬性验收项**：``deny_data_scopes: [ontology_all]`` + 非超管持 ``ontology_all``。

    期望：两侧都给 ``none_allow``（空模板 deny ⇒ deny everything），且**逐字相等**。

    判别力（变异验证）：把 ``/scope`` 改回自建判定（不传 ``deny_scope_ids``）后，HTTP 侧变
    ``allow_all`` 而平台侧仍是 ``none_allow`` → 本用例红。这正是"平台侧全域读封锁、而
    OntoStudio 的动作完全无视它"的那个 fail-open。
    """
    registry = _registry_with_ontology_reviewer(tmp_path)
    _patch_registry(monkeypatch, registry)
    patch_identity(monkeypatch, fake_identity("ontology_reviewer"))
    user = make_user(role_name="ontology_reviewer")
    db = policy_rows_db([policy_row("deny-ontology", grants={"deny_data_scopes": ["ontology_all"]})])

    http_rule, probe_rule = _http_scope_rule(monkeypatch, user, db)
    platform_rule = await _platform_rule(user, db)

    assert http_rule == platform_rule.to_wire(), "两侧判定必须逐字一致"
    assert probe_rule == http_rule, "探针（with_data_scope 走 HTTP）与直调必须一致"
    assert http_rule == {"operator": "none_allow"}


@pytest.mark.asyncio
async def test_scope_endpoint_matches_with_data_scope_when_scopes_present(monkeypatch, tmp_path):
    """**对照态**（没有它，一个恒 ``none_allow`` 的实现也能过上一条）。

    同一角色、无 deny 策略 → ``ontology_all`` 的空模板 ⇒ 两侧都 ``allow_all``。
    这条同时接管了"空模板 = 全量"的覆盖（超管那条已改由旁路产生，见上方 docstring）。
    """
    registry = _registry_with_ontology_reviewer(tmp_path)
    _patch_registry(monkeypatch, registry)
    patch_identity(monkeypatch, fake_identity("ontology_reviewer"))
    user = make_user(role_name="ontology_reviewer")
    db = policy_rows_db([])

    http_rule, probe_rule = _http_scope_rule(monkeypatch, user, db)
    platform_rule = await _platform_rule(user, db)

    assert http_rule == platform_rule.to_wire()
    assert probe_rule == http_rule
    assert http_rule == {"operator": "allow_all"}


@pytest.mark.asyncio
async def test_scope_endpoint_matches_with_data_scope_under_deny_for_superadmin(monkeypatch):
    """**超管旁路那一半**：deny 策略对超管在两侧都不生效（``allow_all``）。

    ⚠️ **判别力归谁（变异实测，2026-09-23）**：删掉 ``resolve_data_scope`` 里的旁路分支后，
    **两侧同时**变成 ``none_allow``——上面两条 ``== platform.to_wire()`` 的相等断言**照样绿**，
    真正红的是最后那条**绝对值**断言。这个分工是刻意的，别把绝对值那几行当装饰删掉：
    相等断言抓"两处判定漂移"（M1 变异实测），绝对值断言抓"共用的那一条判定本身错了"
    （M2/M3 变异实测）。只留相等断言时，把共用判定改坏是**静默**的。
    """
    patch_identity(monkeypatch, fake_identity("superadmin"))
    user = make_user(role_name="超级管理员")
    db = policy_rows_db([policy_row("deny-ontology", grants={"deny_data_scopes": ["ontology_all"]})])

    http_rule, probe_rule = _http_scope_rule(monkeypatch, user, db)
    platform_rule = await _platform_rule(user, db)

    assert http_rule == platform_rule.to_wire()
    assert probe_rule == http_rule
    assert http_rule == {"operator": "allow_all"}


@pytest.mark.asyncio
async def test_scope_endpoint_matches_with_data_scope_for_non_ontology_resource(monkeypatch):
    """非本体资源（``docmgr``，两条 scope 合成 ``or``）也走同一条判定：复合树两侧一致。

    补这一条的理由：上面三条都在 ``ontology`` 上（单 scope、退化成标量算子），而"共用判定"
    要证明的是**整条路径**共用，不只是退化形态。``docmgr`` 用 ``writer`` 角色一次覆盖
    ``or`` + ``eq`` + ``in``（与 ``test_scope_endpoint_non_degenerate_rule_for_docmgr`` 同靶）。
    """
    probe = APIRouter()

    @probe.get("/probe/docmgr-scope")
    async def _probe(scope: FilterRule = Depends(with_data_scope("docmgr"))):  # noqa: B008
        return {"resource": "docmgr", "rule": scope.to_wire()}

    combined = APIRouter()
    combined.include_router(router)
    combined.include_router(probe)

    patch_identity(monkeypatch, fake_identity("writer", user_id="U-1", member_projects=["P-1", "P-2"]))
    user = make_user()
    db = policy_rows_db([])

    http = build_app(combined, user=user, db=db)
    http_rule = http.get(SCOPE, params={"resource": "docmgr"}).json()["rule"]
    probe_rule = http.get("/probe/docmgr-scope").json()["rule"]
    platform_rule = await with_data_scope("docmgr")(current_user=user, db=db)

    assert http_rule == platform_rule.to_wire()
    assert probe_rule == http_rule
    assert http_rule["operator"] == "or", "非退化形态没有被覆盖到就说明这条没测到真东西"


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
