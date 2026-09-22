"""执行管线：解析→范围→锁定→前置→UPDATE→审计→重投影。

本文件把「权限判定的结果」与「数据范围规则」作为入参喂给核心函数，
从而与 gateway 解耦（gateway 侧单测在 backend/tests/test_permissions_scope_endpoint.py）。
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions import executor as executor_module
from app.ontology.actions.executor import ActionError, ScopeDenied, invoke_action_core
from app.ontology.connectors import _ext_url
from app.ontology.registry import get_registry
from app.ontology.schemas import ActionSpec, Precondition, StateChange
from app.ontology.scope import FilterRule

# Task 5 偏离①：计划给的这行只有 integration。本仓 asyncio_mode 是 strict（其余 async 测试
# 一律显式 @pytest.mark.asyncio，见 tests/test_ontology_engine.py），故缺 asyncio 标记时
# 6 条 async 测试全部以 「async def functions are not natively supported」 报错——不是失败，
# 是根本没跑。计划写的 Expected: PASS 在这个环境里不成立。
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_entity(status: str = "pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status)
                       VALUES ('doc_graph','mine','测试实体', :norm, '{}'::jsonb, 0.9, :status) RETURNING id"""
                ),
                {"norm": f"测试实体-{uuid.uuid4().hex[:8]}", "status": status},
            )
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _get_status(pk: uuid.UUID) -> str:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT status FROM dg_entities WHERE id = :id"), {"id": pk})
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _get_updated_at(pk: uuid.UUID) -> datetime:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT updated_at FROM dg_entities WHERE id = :id"), {"id": pk})
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows(pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT action_id, params, before, after, source FROM dg_action_audit WHERE target_pk = :id"),
                {"id": pk},
            )
            return [dict(r._mapping) for r in rows]
    finally:
        await engine.dispose()


async def test_happy_path_writes_status_and_audit():
    pk = await _seed_entity()
    result = await invoke_action_core(
        "review_entity.confirm",
        {},
        target_pk=pk,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="mcp",
        scope_rule=FilterRule(operator="allow_all"),
        project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}
    assert await _get_status(pk) == "active"
    audit = await _audit_rows(pk)
    assert len(audit) == 1
    assert audit[0]["before"] == {"status": "pending_review"}
    assert audit[0]["source"] == "mcp"


async def test_precondition_violation_returns_409():
    pk = await _seed_entity(status="active")
    with pytest.raises(ActionError) as e:
        await invoke_action_core(
            "review_entity.confirm",
            {},
            target_pk=pk,
            actor_id=uuid.uuid4(),
            actor_role="admin",
            source="api",
            scope_rule=FilterRule(operator="allow_all"),
            project=lambda *a, **k: True,
        )
    assert e.value.status_code == 409
    assert "pending_review" in e.value.detail


async def test_out_of_scope_returns_404():
    pk = await _seed_entity()
    with pytest.raises(ScopeDenied) as e:
        await invoke_action_core(
            "review_entity.confirm",
            {},
            target_pk=pk,
            actor_id=uuid.uuid4(),
            actor_role="user",
            source="api",
            scope_rule=FilterRule(operator="none_allow"),
            project=lambda *a, **k: True,
        )
    assert e.value.status_code == 404


async def test_unknown_action_rejected():
    with pytest.raises(ActionError, match="unknown action"):
        await invoke_action_core(
            "nope.nope",
            {},
            target_pk=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            actor_role="admin",
            source="api",
            scope_rule=FilterRule(operator="allow_all"),
            project=lambda *a, **k: True,
        )


async def test_scope_sql_is_executable_with_list_params():
    """M-8（Task 1 审查遗留）：`= ANY(:p)` 传 Python list 给 asyncpg 的类型推断
    从未被任何测试证明过（`col = ANY($1)` 依赖列类型推出 uuid[]）。
    Task 1 的绿只证明 SQL 文本形态正确，不证明这条通道能跑——故在此显式钉住。

    **⚠️ 并需覆盖空 list**（Task 4 审查前向风险）：`in`/`not_in` 编译为 `= ANY(:pre_0)`
    且绑定 Python list，而**空 list 是可达的**——网关 `backend/app/extensions/auth/engine.py:52`
    在模板解析出空 list 时正是产出 `FilterRule(operator="in", value=[])`。
    `ANY(:[])` 传空 Python list 时 asyncpg 能否推断数组元素类型**未经验证**。
    **⚠️⚠️ 本段的初版修法是错的，已在 Task 4 审查中被证伪，勿照抄**：初版写「空集短路
    （`in` 空 → `FALSE`、**`not_in` 空 → `TRUE`**）」——**`not_in` 空 → TRUE 本身就是 fail-open**。
    真库实测：`NOT ('a' = ANY(ARRAY[]::text[]))` = `NOT FALSE` = **TRUE**，
    即**前置条件恒满足、守卫静默失效**；而参数为 `NULL` 时 `NOT(...)` = NULL → 行被过滤 → 拒绝。
    也就是说 `sql_write.py` 里那句 `list(cond.value or [])` **把"漏填 value"从 fail-closed 翻转成了 fail-open**。

    **读路径与写路径的空集语义必须分开裁决**：

    | 路径 | `in` 空 | `not_in` 空 |
    |---|---|---|
    | 读（`scope.py` 数据范围过滤） | `FALSE`（filter 掉，安全） | 需单独裁决 |
    | **写（`sql_write.py` 前置条件守卫）** | `FALSE`（拒绝该动作，安全） | **绝不能是 TRUE**——守卫不该产出恒真式 |

    修法：`sql_write.py` 侧——`in` 空编译为 `FALSE`；**`not_in` 空直接 `raise WriteGuardError`**
    （"不在空集里"字面意义上等于"全部"，对守卫永远不是想要的东西）。类型推断那一半（`ANY(:[])`
    传空 list 时 asyncpg 能否推断元素类型）**仍未验证**，需 Task 5 用真库测试钉住；
    显式转型 `= ANY(CAST(:pre_0 AS text[]))` 是备选。

    **只覆盖 `in`。`overlap`（`col && $1`）是另一条绑定路径，本测试证不了它**——
    `&&` 要求操作数是 array 列，而本体面对的表（cpa_*/csp_*/dg_*）无 array 列，
    构造不出用例。**这不是死代码**：`config/permissions.yaml:99` 有真实模板
    `allowed_depts OVERLAP: $identity.dept_ids` 在用。**触发条件**：一旦某对象类型的
    `scope_bindings` 指向 array 列，必须先补一条 overlap 的集成测试再上线。
    """
    pk = await _seed_entity()
    rule = FilterRule(operator="in", field="id", value=[str(pk)])
    result = await invoke_action_core(
        "review_entity.confirm",
        {},
        target_pk=pk,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="api",
        scope_rule=rule,
        project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}


async def test_projection_failure_does_not_rollback():
    """投影失败不回滚业务状态：审计与 UPDATE 已提交，errors 里留痕。"""
    pk = await _seed_entity()
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("projection boom")

    result = await invoke_action_core(
        "review_entity.confirm",
        {},
        target_pk=pk,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="api",
        scope_rule=FilterRule(operator="allow_all"),
        project=boom,
    )
    assert result["projected"] is False
    assert result["errors"] and "projection boom" in result["errors"][0]
    assert await _get_status(pk) == "active"
    assert len(await _audit_rows(pk)) == 1


# ── 以下为 Task 5 派发时点名的四处问题 + 两条前向风险的钉住测试 ──────────────────


class _StubRegistry:
    """只含一个假动作的 registry 桩（目标对象类型仍取真 registry 的 graph_entity）。

    为什么需要它：`_resolve` 从热加载的 registry 快照取声明，而「声明有笔误」这条路径
    必须能构造出真实 registry 里不存在的畸形声明——否则它永远不可达（Task 9 的 lint 上线前，
    畸形声明确实能进 registry）。
    """

    def __init__(self, action: ActionSpec, obj: object) -> None:
        self.actions = {action.id: action}
        self.object_types = {action.target: obj}

    def get_action(self, action_id: str) -> ActionSpec | None:
        return self.actions.get(action_id)


def _stub_registry(monkeypatch, action: ActionSpec, obj=None) -> None:
    target = obj if obj is not None else get_registry().object_types[action.target]
    monkeypatch.setattr(executor_module, "get_registry", lambda: _StubRegistry(action, target))


def _action(**overrides) -> ActionSpec:
    """真实 review_entity.confirm 的声明形状，可按需替换前置/后置段。"""
    base: dict = {
        "id": "review_entity.confirm",
        "display_name": "确认实体",
        "description": "测试用假动作",
        "domain": "doc_graph",
        "target": "graph_entity",
        "required_permissions": ["ontology:action:review"],
        "preconditions": [Precondition(field="status", op="eq", value="pending_review")],
        "postconditions": [StateChange(field="status", set="active")],
    }
    base.update(overrides)
    return ActionSpec(**base)


async def _invoke(action_id="review_entity.confirm", *, pk, scope_rule, project=None, params=None):
    return await invoke_action_core(
        action_id,
        params if params is not None else {},
        target_pk=pk,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="api",
        scope_rule=scope_rule,
        project=project or (lambda *a, **k: True),
    )


async def test_scope_in_list_excludes_non_matching_row():
    """前向风险 B（Task 1 的 M-8 遗留）——判别力靠「列表里放**别的** pk」。

    计划给的那条（`value=[str(pk)]`）只证明「没抛异常 + 行还在」，**证不了列表值被真的
    绑进去求值**：把 `rule_to_sql` 换成恒 `TRUE` 它照样绿。这条用不匹配的 pk 要求 404，
    才把「值确实进了 SQL 并被求值」钉住——且未越权行必须原封不动。
    """
    pk = await _seed_entity()
    other = await _seed_entity()
    with pytest.raises(ScopeDenied):
        await _invoke(pk=pk, scope_rule=FilterRule(operator="in", field="id", value=[str(other)]))
    assert await _get_status(pk) == "pending_review"  # 未越权行绝不被改


async def test_scope_in_empty_list_is_executable_and_denies():
    """前向风险 A：`= ANY(:p)` 绑**空** Python list 时 asyncpg 的元素类型推断。

    这条**必须真的跑到 SQL**（只断言编译出的字符串是假绿）：空 list 若推断不出类型，
    SQLAlchemy/asyncpg 会抛 `DataError`，本测试会以非 ScopeDenied 的异常炸掉。

    真库实测结论（2026-09-23，本测试首跑）：**推断成功，无需改 `scope.py`**——
    `col = ANY($1)` 由**列类型**推出 `uuid[]` / `text[]`，与环境无关；
    故计划里那条备选修法（`= ANY(CAST(:p AS text[]))`）**不必启用**，且它对 uuid 列是错的
    （`uuid = ANY(text[])` 无算子，会引入新错）。此处不覆盖 `not_in`：见 executor.py 的
    已知天花板注释（空集的 `not_in` 恒真 = fail-open，修复位置在网关解析层）。
    """
    pk = await _seed_entity()
    for field in ("id", "status"):  # uuid 列与 text 列，两条类型推断路径
        with pytest.raises(ScopeDenied):
            await _invoke(pk=pk, scope_rule=FilterRule(operator="in", field=field, value=[]))
    assert await _get_status(pk) == "pending_review"


async def test_declaration_error_in_precondition_is_action_error(monkeypatch):
    """问题①：动作声明有笔误时 `build_precondition_where` 抛 `WriteGuardError`（ValueError），
    不是 `ActionError`。Task 7 的 REST 层只 `except ActionError`，裸异常会变成 500 且**丢掉 detail**。

    状态码取 500 而非 400：调用方没做错任何事——`action_id` 合法、`params` 根本不进 SQL
    （设计 §2 订正：本设计不存在参数化前置条件）。坏的是服务端自己的 registry 声明，
    与 `_resolve` 里既有两处 registry 缺陷（target unresolved / no physical table）同一归因。
    """
    pk = await _seed_entity()
    _stub_registry(monkeypatch, _action(preconditions=[Precondition(field="bad col!", op="eq", value="x")]))
    with pytest.raises(ActionError) as e:
        await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
    assert e.value.status_code == 500
    assert "bad col!" in e.value.detail


async def test_declaration_error_in_postcondition_is_action_error(monkeypatch):
    """问题①的另一半：`build_update_set` 同样会抛 `WriteGuardError`。"""
    pk = await _seed_entity()
    _stub_registry(monkeypatch, _action(postconditions=[StateChange(field="bad col!", set="active")]))
    with pytest.raises(ActionError) as e:
        await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
    assert e.value.status_code == 500
    assert "bad col!" in e.value.detail


async def test_malformed_scope_rule_is_action_error():
    """问题①的第三处同类（计划未列出，但 `scope.py` 的 docstring 明文把它派给了 executor）：
    「本模块自己拥有 wire 解码与标识符校验，故**所有畸形输入都归一到这里**——调用方
    （executor）只需捕获本异常映射 4xx」。缺这一层，网关下发一个编译不了的规则就是裸 500。

    状态码取 400（与上面两条相反）：这条是**入参形状**问题——规则从网关 wire 解出来，
    不合法即请求侧数据不可用，且这正是 `ScopeCompileError` docstring 写明的 4xx 契约。
    """
    pk = await _seed_entity()
    with pytest.raises(ActionError) as e:
        await _invoke(pk=pk, scope_rule=FilterRule(operator="bogus_op", field="id", value=1))
    assert e.value.status_code == 400
    assert "bogus_op" in e.value.detail


async def test_audit_after_records_real_db_value_for_now_column(monkeypatch):
    """问题②：`now=True` 的列被记成 `None` 不是「由 DB 决定」，是**审计行与实际不符**。

    审计是这条链路存在的唯一追溯凭据（设计 §1.2），一行写着 `after: {"updated_at": null}`
    而库里是 `NOW()` 就是伪造记录。这里要求 after 里是**事务内 RETURNING 取回的真值**，
    并与库中落地值逐位相等。用 `updated_at` 是因为它只能由这条 UPDATE 改变
    （`onupdate=func.now()` 只在 ORM 层生效，本走的是裸 SQL）。
    """
    pk = await _seed_entity()
    _stub_registry(
        monkeypatch,
        _action(postconditions=[StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)]),
    )
    result = await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))

    live = await _get_updated_at(pk)
    assert live is not None
    assert isinstance(result["after"]["updated_at"], datetime)
    assert result["after"]["updated_at"] == live

    recorded = (await _audit_rows(pk))[0]["after"]["updated_at"]
    assert recorded is not None
    assert datetime.fromisoformat(recorded) == live


async def test_param_name_collision_is_rejected(monkeypatch):
    """问题④：`{"pk": ...} **scope_params, **pre_params, **set_params` 的键碰撞。

    今日四个来源的前缀互斥（`pk` 字面量 / `scope_N` / `pre_N` / `set_N`），已逐处核对；
    但这条并集是**值的唯一落点**，一旦将来某处换了前缀或新产 `pk`，`**` 会静默让后者
    覆盖前者——绑错的值不会报错，只会让守卫按错误的量判。故用一条桩规则直接注入碰撞键，
    钉住「宁可直接失败也不静默覆盖」。

    判别力：计划版的 `**` 合并会让 scope 的 `pk` 覆盖真正的目标主键，
    于是查询以一个非 uuid 字符串去匹配 uuid 列 → DataError（不是 ActionError）→ 本测试红。
    """
    pk = await _seed_entity()
    monkeypatch.setattr(executor_module, "rule_to_sql", lambda rule, bindings=None: ("TRUE", {"pk": "hijacked"}))
    with pytest.raises(ActionError) as e:
        await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
    assert e.value.status_code == 500
    assert "pk" in e.value.detail
    assert await _get_status(pk) == "pending_review"


async def test_illegal_identifier_in_registry_is_action_error(monkeypatch):
    """问题①的最后一处同类（自审补）：`quote_ident(obj.access.table)` 与
    `quote_ident(obj.pk.column)` 引的是 registry 里的标识符，同样只过 `sql_write` 的白名单——
    表名/主键列名的笔误（`dg-entities`）会抛 `WriteGuardError`，而它同样不能是裸异常。
    计划给的代码只包了前置条件与 SET 两处，这两处漏在外。
    """
    pk = await _seed_entity()
    real = get_registry().object_types["graph_entity"]
    bad_changes = [
        ({"access": real.access.model_copy(update={"table": "bad table"})}, "bad table"),
        ({"pk": real.pk.model_copy(update={"column": "bad col!"})}, "bad col!"),
    ]
    for changes, rejected in bad_changes:
        _stub_registry(monkeypatch, _action(), real.model_copy(update=changes))
        with pytest.raises(ActionError) as e:
            await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
        assert e.value.status_code == 500
        assert rejected in e.value.detail  # detail 里带的是被拒的标识符本身


async def test_caller_params_are_recorded_but_never_reach_sql():
    """设计 §9 的头号风险是「写路径是新的攻击面」，而 `params` 是调用方**唯一**能控制的东西。

    设计 §2 的订正写明：本设计不存在"参数化前置条件"，`params` 只进审计行
    （`CAST(:params AS jsonb)`），从不进 SQL 值位置。故这里喂一组敌意参数，断言两件事：
    原样记进审计（它是追溯凭据），且业务结果完全由声明决定——`params` 想改的那列没被改。
    """
    pk = await _seed_entity()
    hostile = {"status": "rejected", "note": "x'); DROP TABLE dg_entities; --"}
    result = await _invoke(pk=pk, params=hostile, scope_rule=FilterRule(operator="allow_all"))

    assert (await _audit_rows(pk))[0]["params"] == hostile
    assert result["after"] == {"status": "active"}  # 声明说了算
    assert await _get_status(pk) == "active"
