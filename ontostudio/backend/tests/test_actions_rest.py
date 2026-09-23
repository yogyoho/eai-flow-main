"""REST 暴露面：``POST /api/extensions/ontology/actions/invoke``（计划 Task 7）。

设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §2/§3。

本文件覆盖**暴露面自己**的东西：路由与鉴权门槛、**双层授权**（操作权限 + 数据范围）、
``ActionError`` → HTTP 的映射、以及 ``project`` 可调用的同步性。真库路径（``ScopeDenied``
404 / 前置条件 409 / 审计行 / 懒建）由 ``tests/test_actions_executor.py`` 的 integration
用例覆盖，本文件一律不碰库。

**纪律**：``/api/permissions/scope`` 的**产出侧**（gateway）不在这里断言——两侧各自的
形状由 ``test_scope_wire_contract.py``（消费侧）与主仓 ``tests/test_permissions_scope_endpoint.py``
（产出侧）钉住；本文件只断言「网关回了这个 wire，本侧解出来的是这个规则」。
"""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

import app.auth as ontostudio_auth
from app.main import create_app
from app.ontology import routers as ontology_routers
from app.ontology.scope import FilterRule, ScopeCompileError

INVOKE = "/api/extensions/ontology/actions/invoke"
_PK = "00000000-0000-0000-0000-000000000000"


def _body(**over: object) -> dict:
    return {"action_id": "review_entity.confirm", "pk": _PK, **over}


# ── 鉴权门槛 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_requires_auth():
    """无 token → 401（鉴权先于一切业务判定，含动作解析）。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(INVOKE, json=_body())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invoke_requires_system_access(make_token):
    """非管理员 token（且无 gateway 委托 Cookie）→ 403，且**不解析动作**。

    **必须断言 detail**:两层都会产 403（路由门槛说 ``Permission denied: system:access``，
    动作门槛说 ``缺少权限：ontology:action:review``）——只断状态码的话，把路由依赖
    ``require_permission("system:access")`` 整个摘掉，本用例照样绿（动作层顺手也拒了），
    等于没测到那条依赖。detail 是这两层唯一的可区分输出。

    变异检验：摘掉路由依赖后本用例红（detail 变成动作层那句，或状态码不再是 403）。
    """
    app = create_app()
    headers = {"Authorization": f"Bearer {make_token(roles=('user',))}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=headers) as c:
        r = await c.post(INVOKE, json=_body())
    assert r.status_code == 403
    assert r.json()["detail"] == "Permission denied: system:access"


@pytest.mark.asyncio
async def test_invoke_unknown_action_is_404(auth_headers):
    """已认证（管理员 claims）但动作未声明 → 404，且 detail 点名动作 id。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(INVOKE, json=_body(action_id="nope.nope"))
    assert r.status_code == 404
    assert "nope.nope" in r.json()["detail"]


# ── 请求体契约 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_rejects_unknown_body_field(auth_headers):
    """``extra="forbid"``：多一个字段即 422（防止调用方以为参数生效）。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(INVOKE, json=_body(force=True))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invoke_malformed_pk_is_422_not_500(auth_headers):
    """``pk`` 由 Pydantic 校验成 UUID → 422。

    **偏离计划①**：计划写的是 ``pk: str`` + 函数体里 ``uuid.UUID(body.pk)``，畸形 pk 会以
    ``ValueError`` 逃到 FastAPI 变成**丢掉 detail 的裸 500**。归因是"送来的东西不可用"，
    按本仓错误契约（executor 模块 docstring 的表）该是 4xx。
    """
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(INVOKE, json=_body(pk="not-a-uuid"))
    assert r.status_code == 422


# ── 双层授权：第 1 层（操作权限）───────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_denies_when_action_permission_missing(monkeypatch, auth_headers):
    """动作声明的 ``required_permissions`` 未经 ``authorize`` 放行 → 403，detail 点名权限点。

    判别力（变异验证）：删掉 ``_authz_for_action`` 里的 required_permissions 循环后，
    请求会穿过授权层走到 ``invoke_action_core``（→ 真库路径），本用例不再拿到 403。
    """
    seen: list[tuple[object, str]] = []

    async def _deny(request, user, permission):  # noqa: ANN001, ARG001
        seen.append((user.id, permission))
        return False

    monkeypatch.setattr(ontology_routers, "authorize", _deny)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(INVOKE, json=_body())
    assert r.status_code == 403
    assert "ontology:action:review" in r.json()["detail"]
    assert [perm for _, perm in seen] == ["ontology:action:review"], "必须逐条查声明里的权限点"


@pytest.mark.asyncio
async def test_invoke_denies_when_delegation_unavailable(auth_headers):
    """管理员 claims 只过**路由**门槛；动作层仍要求 gateway 委托放行。

    这条钉住的是「claims 里的 roles 不是授权真相源」：``auth_headers`` 带 superadmin
    claims（故路由件的 ``require_permission`` 走 v1 快路径放行），但动作层调的是
    ``app.auth.authorize`` → 无 Cookie → fail-closed False。
    """
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(INVOKE, json=_body())
    assert r.status_code == 403


# ── 第 2 层（数据范围）的取规则侧 ──────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _FakeAsyncClient:
    """httpx.AsyncClient 替身：行为由类属性下发，``calls`` 记录轨迹。"""

    behavior: tuple[int, object] | Exception = (200, {})
    calls: list[tuple[str, dict | None]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None) -> _FakeResponse:
        type(self).calls.append((str(httpx.URL(url, params=params)) if params else url, headers))
        behavior = type(self).behavior
        if isinstance(behavior, Exception):
            raise behavior
        return _FakeResponse(*behavior)


class _FakeRequest:
    """``fetch_scope_rule`` 只读 ``request.headers['cookie']``。"""

    def __init__(self, cookie: str = "access_token=fake-cookie") -> None:
        self.headers = {"cookie": cookie}


def _install_fake_gateway(monkeypatch, behavior: tuple[int, object] | Exception) -> None:
    monkeypatch.setattr(ontostudio_auth.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.behavior = behavior
    _FakeAsyncClient.calls = []
    monkeypatch.setenv("ONTOSTUDIO_GATEWAY_URL", "http://gateway-test:9999")


@pytest.mark.asyncio
async def test_fetch_scope_rule_deserializes_gateway_wire(monkeypatch):
    """网关下发的 ``rule`` 必须被**真正解成 FilterRule 树**（而非退化成某个默认算子）。

    变异检验：把 ``FilterRule.from_wire(payload["rule"])`` 换成 ``FilterRule()``
    （默认 ``none_allow``）后，下面三条字段级断言全红——只断 ``operator`` 的写法挡不住
    这种退化（``or`` 与 ``none_allow`` 都是字符串）。
    """
    _install_fake_gateway(
        monkeypatch,
        (
            200,
            {
                "resource": "ontology",
                "rule": {
                    "operator": "or",
                    "children": [
                        {"operator": "eq", "field": "user_id", "value": "U-1"},
                        {"operator": "in", "field": "project_id", "value": ["P-1", "P-2"]},
                    ],
                },
            },
        ),
    )

    rule = await ontostudio_auth.fetch_scope_rule(_FakeRequest(), "ontology")

    url, headers = _FakeAsyncClient.calls[0]
    assert url == "http://gateway-test:9999/api/permissions/scope?resource=ontology"
    assert "access_token=" in (headers or {}).get("Cookie", ""), "必须原样透传调用方 Cookie（委托身份）"
    assert rule.operator == "or"
    assert rule.children is not None and len(rule.children) == 2
    assert rule.children[0].field == "user_id"
    assert rule.children[0].value == "U-1"
    assert rule.children[1].operator == "in"
    assert rule.children[1].value == ["P-1", "P-2"]


@pytest.mark.asyncio
async def test_fetch_scope_rule_failclosed_when_gateway_unreachable(monkeypatch):
    """网关不可达 → ``none_allow``（动作恒被拒），**不是** allow_all。"""
    _install_fake_gateway(monkeypatch, httpx.ConnectError("boom"))
    rule = await ontostudio_auth.fetch_scope_rule(_FakeRequest(), "ontology")
    assert rule.operator == "none_allow"


@pytest.mark.asyncio
async def test_fetch_scope_rule_failclosed_without_cookie(monkeypatch):
    """**无 Cookie** → ``none_allow``，且**不发起 HTTP**。

    这条是变异补出来的（2026-09-23）：把本分支改成 ``allow_all`` 时，其余 14 条用例**全绿**
    ——因为 ``_FakeRequest`` 默认带 Cookie，没有任何用例走到"无 Cookie"这一支，而它正是
    fail-open 最容易写错的那一支（"没有身份 ⇒ 放行"读起来甚至像合理的默认）。
    断言"未发起 HTTP"同样必要：真去问了才失败与压根不问，是两种不同的实现。
    """
    _install_fake_gateway(monkeypatch, (200, {"resource": "ontology", "rule": {"operator": "allow_all"}}))
    rule = await ontostudio_auth.fetch_scope_rule(_FakeRequest(cookie=""), "ontology")
    assert rule.operator == "none_allow"
    assert _FakeAsyncClient.calls == [], "无 Cookie 时不该去问网关"


@pytest.mark.asyncio
async def test_fetch_scope_rule_failclosed_on_non_200(monkeypatch):
    """网关 403/500 等非 200 → ``none_allow``。"""
    _install_fake_gateway(monkeypatch, (403, {"detail": "denied"}))
    rule = await ontostudio_auth.fetch_scope_rule(_FakeRequest(), "ontology")
    assert rule.operator == "none_allow"


@pytest.mark.asyncio
async def test_fetch_scope_rule_failclosed_on_malformed_rule(monkeypatch):
    """wire 畸形（``children`` 不是 list）→ ``none_allow``，异常不逃出本函数。

    ``FilterRule.from_wire`` 刻意把畸形输入归一到 ``ScopeCompileError``；本函数必须接住它
    ——否则畸形规则会以裸异常逃成 500（而不是「按拒处理」）。
    """
    _install_fake_gateway(monkeypatch, (200, {"resource": "ontology", "rule": {"operator": "or", "children": "boom"}}))
    rule = await ontostudio_auth.fetch_scope_rule(_FakeRequest(), "ontology")
    assert rule.operator == "none_allow"


def test_scope_compile_error_is_the_wire_failure_type():
    """钉住上面那条的**前提**：畸形 wire 抛的确实是 ``ScopeCompileError``。

    没有这条，``fetch_scope_rule`` 里那个 except 的名字就成了猜测；将来 ``from_wire``
    改抛别的异常时，上一条会以"异常逃出 → 测试红"的方式报警，本条约等于它的规格说明。
    """
    with pytest.raises(ScopeCompileError):
        FilterRule.from_wire({"operator": "or", "children": "boom"})


@pytest.mark.asyncio
async def test_authz_skips_scope_lookup_when_object_declares_no_scope_resource(monkeypatch):
    """对象类型未声明 ``scope_resource`` → ``allow_all``，且**不查网关**。

    这是本层唯一的放行回退分支，必须被钉住：它一旦变成"查不到就拒"会让无范围对象
    （今日所有动作都 targeting ``graph_entity``，将来可能不是）全灭；而它一旦变成
    "异常时放行"就是越权。今日用 monkeypatch 造这个形态——registry 里没有这样的对象。
    """
    calls: list[str] = []

    async def _deny(request, user, permission):  # noqa: ANN001, ARG001
        calls.append(permission)
        return True

    monkeypatch.setattr(ontology_routers, "authorize", _deny)

    async def _unreachable(*a, **k):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("未声明 scope_resource 时不应查网关")

    monkeypatch.setattr(ontology_routers, "fetch_scope_rule", _unreachable)
    monkeypatch.setattr(
        "app.ontology.actions.executor._resolve",
        lambda action_id: (SimpleNamespace(id=action_id, required_permissions=["x:y"]), SimpleNamespace(scope_resource=None)),
    )

    action, rule = await ontology_routers._authz_for_action(None, SimpleNamespace(id=uuid.uuid4()), "whatever")
    assert action.id == "whatever"
    assert rule == FilterRule(operator="allow_all")
    assert calls == ["x:y"], "操作权限仍必须逐条查（放行的是范围，不是权限）"


@pytest.mark.asyncio
async def test_authz_returns_fetched_rule_when_scope_resource_declared(monkeypatch):
    """声明了 ``scope_resource`` → 返回的必须是**取回来的那条规则**。

    与上一条配对：只钉"未声明 → allow_all"的话，一个**恒** ``allow_all`` 的实现也能通过
    （变异实测 M12：把整段换成 ``return action, FilterRule(operator="allow_all")``，上一条
    照样绿）。两条一起才圈住那个分支。
    """
    marker = FilterRule(operator="in", field="dept_id", value=["D-1"])

    async def _rule(request, resource):  # noqa: ANN001, ARG001
        assert resource == "ontology", "必须按对象类型声明的 resource 去取"
        return marker

    async def _allow(request, user, permission):  # noqa: ANN001, ARG001
        return True

    monkeypatch.setattr(ontology_routers, "authorize", _allow)
    monkeypatch.setattr(ontology_routers, "fetch_scope_rule", _rule)
    monkeypatch.setattr(
        "app.ontology.actions.executor._resolve",
        lambda action_id: (SimpleNamespace(id=action_id, required_permissions=[]), SimpleNamespace(scope_resource="ontology")),
    )

    _action, rule = await ontology_routers._authz_for_action(None, SimpleNamespace(id=uuid.uuid4()), "whatever")
    assert rule is marker


# ── actor_role：写进审计的是**角色 code**，来自 gateway 正典身份 ──────────


@pytest.mark.asyncio
async def test_resolve_actor_role_returns_gateway_role_code(monkeypatch):
    """``resolve_actor_role`` 取 ``identity.role_code``（**code**，不是显示名）。"""
    _install_fake_gateway(monkeypatch, (200, {"is_admin": False, "permissions": [], "identity": {"role_code": "dept_head", "role_name": "部门负责人"}}))
    assert await ontostudio_auth.resolve_actor_role(_FakeRequest(), ontostudio_auth.CurrentUser(id=uuid.uuid4(), username="u", email="u@local")) == "dept_head"


@pytest.mark.asyncio
async def test_resolve_actor_role_is_none_on_failure(monkeypatch):
    """取不到身份 → ``None``（审计列可空），**不**影响动作本身——本函数绝不抛。"""
    _install_fake_gateway(monkeypatch, httpx.ConnectError("boom"))
    assert await ontostudio_auth.resolve_actor_role(_FakeRequest(), ontostudio_auth.CurrentUser(id=uuid.uuid4(), username="u", email="u@local")) is None

    _install_fake_gateway(monkeypatch, (200, {"is_admin": True, "permissions": []}))  # 无 identity 段
    assert await ontostudio_auth.resolve_actor_role(_FakeRequest(), ontostudio_auth.CurrentUser(id=uuid.uuid4(), username="u", email="u@local")) is None

    _install_fake_gateway(monkeypatch, (200, {"identity": {"role_code": ""}}))  # 空串不当 code
    assert await ontostudio_auth.resolve_actor_role(_FakeRequest(), ontostudio_auth.CurrentUser(id=uuid.uuid4(), username="u", email="u@local")) is None


@pytest.mark.asyncio
async def test_invoke_passes_resolved_role_code_to_audit(monkeypatch, make_token):
    """端点传给审计的是 ``resolve_actor_role`` 的结果，**不是** ``user.role_name``。

    判别力（变异实测 2026-09-23）：把端点里那行换回计划原文的 ``actor_role=user.role_name``
    → 本用例红（claim 里那个显示名被写进审计，而不是网关身份给的 code）。

    顺带钉住"claims 里的角色不是授权真源"：本 token 自带 ``role_name="超级管理员"``，
    端点仍取网关身份。
    """
    captured: dict = {}

    async def _fake_core(action_id, params, **kw):  # noqa: ANN001, ANN003, ARG001
        captured.update(kw)
        return {"action_id": action_id}

    async def _allow(request, user, permission):  # noqa: ANN001, ARG001
        return True

    async def _scope(request, resource):  # noqa: ANN001, ARG001
        return FilterRule(operator="allow_all")

    async def _role(request, user):  # noqa: ANN001, ARG001
        return "dept_head"

    monkeypatch.setattr("app.ontology.actions.executor.invoke_action_core", _fake_core)
    monkeypatch.setattr(ontology_routers, "authorize", _allow)
    monkeypatch.setattr(ontology_routers, "fetch_scope_rule", _scope)
    monkeypatch.setattr(ontology_routers, "resolve_actor_role", _role)

    token = make_token(roles=("superadmin",), role_name="超级管理员")
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.post(INVOKE, json=_body())
    assert r.status_code == 200
    assert captured["actor_role"] == "dept_head"
    assert captured["source"] == "api"
    assert captured["target_pk"] == uuid.UUID(_PK)
    assert captured["project"] is ontology_routers._project_incrementally, "project 必须是本模块那个同步函数本身"


# ── project 可调用：必须同步（Task 5 docstring 记的坑）──────────────────


def test_project_refresh_is_synchronous(monkeypatch):
    """``project`` 必须是**同步**可调用，且真的调用 ``get_kernel().refresh()``。

    为什么必须有这条：``invoke_action_core`` 同步调用 ``project(action_id, pk)``——写成
    ``async def`` 时它拿到的是一个**被丢弃的协程对象**，异常不回传、**静默算作
    projected=True**（executor 模块 docstring 明文记了这条）。这条钉住"本侧没写错"的
    那一半；executor 对协程的容忍度是 Task 5 的决策，不在此断言。

    变异检验：把 ``_project_incrementally`` 改成 ``async def`` → 两个断言同时红
    （``iscoroutinefunction`` 为真；调用返回协程而非 None）。
    """
    calls: list[str] = []

    class _Kernel:
        def refresh(self) -> None:
            calls.append("refresh")

    monkeypatch.setattr("app.ontology.kernel.service.get_kernel", lambda: _Kernel())

    assert not inspect.iscoroutinefunction(ontology_routers._project_incrementally)
    result = ontology_routers._project_incrementally("review_entity.confirm", uuid.uuid4())
    assert not inspect.iscoroutine(result)
    assert result is None
    assert calls == ["refresh"]


def test_project_refresh_does_not_swallow_kernel_errors(monkeypatch):
    """``refresh()`` 抛异常必须向外交给 executor 记入 errors——不吞。

    吞掉的后果：``projected`` 恒 True，运维失去"投影失败"的唯一信号。
    """

    class _Kernel:
        def refresh(self) -> None:
            raise RuntimeError("schema 编译失败")

    monkeypatch.setattr("app.ontology.kernel.service.get_kernel", lambda: _Kernel())
    with pytest.raises(RuntimeError):
        ontology_routers._project_incrementally("review_entity.confirm", uuid.uuid4())
