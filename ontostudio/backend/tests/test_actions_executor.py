"""执行管线：解析→范围→锁定→前置→UPDATE→审计→重投影。

本文件把「权限判定的结果」与「数据范围规则」作为入参喂给核心函数，
从而与 gateway 解耦（gateway 侧单测在 backend/tests/test_permissions_scope_endpoint.py）。
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

import asyncpg
import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import db
from app.db import ensure_tables
from app.ontology import connectors
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
    return await _seed_entity_in(_ext_url(), status=status)


async def _seed_entity_in(url: str, status: str = "pending_review") -> uuid.UUID:
    engine = create_async_engine(url, poolclass=NullPool)
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
    return await _get_status_in(_ext_url(), pk)


async def _get_status_in(url: str, pk: uuid.UUID) -> str:
    engine = create_async_engine(url, poolclass=NullPool)
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
    return await _audit_rows_in(_ext_url(), pk)


async def _audit_rows_in(url: str, pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT id, action_id, params, before, after, source FROM dg_action_audit WHERE target_pk = :id"),
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
    """`= ANY(:p)` 绑 Python list 的**正向**钉子：列表含目标 pk 时必须放行。

    **判别力边界（审查者 2026-09-23 双向变异实测，别高估本条）**：它只对「放行方向」敏感。
    把 `scope.py` 的 `_LEAF_SQL["in"]` 改成恒不匹配 → **只它红**（故它是该方向的唯一钉子，
    删不得）；改成恒匹配 → **它仍绿**。**首段的旧叙事（"钉住这条通道能跑"）高于事实**，
    已删——空集与语义那一半由 `test_scope_in_empty_list_is_executable_and_denies` 与
    `test_scope_in_list_excludes_non_matching_row` 承担，`not_in` 空集与 `sql_write` 守卫
    由 `tests/test_actions_sql_write.py` 承担。

    只留两件别处没有的事实：
    ① **空 list 由列类型推断成功**（uuid 列 → `uuid[]`、text 列 → `text[]`），与是否为空无关
       ⇒ 计划列的备选修法 `= ANY(CAST(:p AS text[]))` **不必启用**，且它对 uuid 列是错的
       （`uuid = ANY(text[])` 无算子，会引入新错）。
    ② **`overlap`（`col && $1`）是另一条绑定路径，本条证不了它**——它的运维前置条件已迁到
       `scope.py` 的 `_LEAF_SQL["overlap"]` 上方（那里才是它该在的载体，不再吊在测试里）。
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


# ── Task 5 Step 6：写路径韧性——审计表懒建（有界）+ 非「表不存在」不得懒建 ──────────────
# 计划: docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md「Task 5 / ### Step 6」。
#
# 分工：**正面**（真 42P01 → 懒建 → 重试成功）只有真库能造出真形状——asyncpg 的原始异常被
# SQLAlchemy 包两层、且只有内层两层带 sqlstate——故第 1 条在一个**一次性 scratch 库**上跑
# （见 _reset_scratch_db 里「为什么不改真表」）；**反面**（不该触发 / 只触发一次）真库给不出
# 反例（42P01 只有一种），故第 2/3/4 条用注入的失败喂同一条代码路径（_write_with_lazy_audit_table）。

_SCRATCH_DB = "ontostudio_pytest_lazy"


def _scratch_url() -> str:
    """scratch 库 URL（同实例、换库名）——_ext_url 可能带 query，故用 make_url 改 database。"""
    return make_url(_ext_url()).set(database=_SCRATCH_DB).render_as_string(hide_password=False)


async def _admin_exec(sql: str) -> None:
    """在真库上跑一条管理语句。

    CREATE/DROP DATABASE **不能在事务块里**执行，故这里用 asyncpg 直连（它默认自动提交），
    而不是 SQLAlchemy 引擎。``WITH (FORCE)``（PG ≥ 13，本机 16.14）顺带掐掉残留连接——
    否则上一轮异常的残留连接会让下一轮 DROP 失败。
    """
    dsn = make_url(_ext_url()).set(drivername="postgresql").render_as_string(hide_password=False)
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _exec_in(url: str, sql: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


async def _reset_scratch_db(scratch: str) -> None:
    """重建一次性 scratch 库：**全部 dg_* 就位，唯独 dg_action_audit 不存在**。

    为什么另起一个库，而不是把真表改名藏起来（**初版就是这么写的，已被实测证伪**）：
    PostgreSQL 的 ``ALTER TABLE ... RENAME`` **不会**跟着改索引名（``dg_action_audit_pkey``、
    ``ix_dg_action_audit_*`` 都留在原表上），于是懒建的 create_all 建表时撞名失败
    （DuplicateTableError：relation "ix_dg_action_audit_actor_created" already exists）——
    不但测不出懒建，还把一个改名后的活库留在原地污染后续用例（2026-09-23 实测）。
    DROP 真表也一样：中途崩掉就是一个坏掉的活库。独立库最坏只脏自己。
    """
    await _admin_exec(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}" WITH (FORCE)')
    await _admin_exec(f'CREATE DATABASE "{_SCRATCH_DB}"')
    await ensure_tables()  # 生产建表路径（调用方已把 _ext_url 指向 scratch）
    await _exec_in(scratch, "DROP TABLE dg_action_audit")  # 制造「表缺失」——本测试的起点


@pytest.fixture()
def lazy_flag_reset(monkeypatch):
    """懒建 flag 是模块级「每进程一次」——用例之间必须复位，否则先跑的那条把额度用光。

    用 monkeypatch 而非直接赋值：用例结束自动还原（不在活树里留状态）。
    """
    monkeypatch.setattr(executor_module, "_lazy_schema_attempted", False)


async def test_missing_audit_table_is_lazily_created_and_write_succeeds(monkeypatch, lazy_flag_reset):
    """表**真的不存在**时：懒建一次 → 重试成功；断言**可观测效果**（状态改了 + 审计行在）。

    为什么不注入自造异常（也不用改名/删真表）：本条的判别力正在两处**真实形状**——
    ① 生产的异常链（asyncpg 原始异常被 SQLAlchemy 包两层，只有内层两层带 sqlstate，
    顶层为 None，见 executor 的 ``_is_missing_table_error``）；
    ② ``ensure_tables`` **真的**把缺的表建出来（这里是 scratch 库里真的没有那张表）。
    自造异常验不到①，改名/删真表则有污染活库的实测事故。故：整条链路（Postgres 的 42P01
    → 识别器 → 懒建 → 新事务重试 → 审计行落地）都跑真的，只是库是一次性的。
    顺带钉住「重试在原事务之外」：实测同一事务里失败后再发语句只回 25P02
    （``InFailedSQLTransaction``）——重试若复用那个已回滚的事务，本条必然红。
    """
    scratch = _scratch_url()
    monkeypatch.setattr(connectors, "_ext_url", lambda: scratch)  # app.db.ensure_tables → scratch
    monkeypatch.setattr(executor_module, "_ext_url", lambda: scratch)  # 写路径引擎 → scratch
    await _reset_scratch_db(scratch)
    try:
        pk = await _seed_entity_in(scratch)
        result = await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
        status = await _get_status_in(scratch, pk)
        audit = await _audit_rows_in(scratch, pk)  # 真库读：懒建出来的表里必须有这一行
    finally:
        await _admin_exec(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}" WITH (FORCE)')

    assert result["after"] == {"status": "active"}
    assert status == "active"  # 业务写真的落地了
    assert len(audit) == 1 and audit[0]["source"] == "api"  # 审计行真的在（且只有一条：失败那次已回滚）
    assert executor_module._lazy_schema_attempted is True  # 次级钉住：走的确实是懒建那条路


class _FailingBegin:
    """``engine.begin()`` 的替身：进入即抛（模拟连接阶段失败），退出照常。"""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc_info) -> bool:
        return False


class _FailingEngine:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def begin(self) -> _FailingBegin:
        return _FailingBegin(self._exc)

    async def dispose(self) -> None:
        pass


def _dbapi_error(orig: BaseException) -> sqlalchemy.exc.DBAPIError:
    """按 SQLAlchemy 生产形状裹一层 DBAPIError（``orig`` 为原始驱动异常）。

    用 ``DBAPIError.instance``（SQLAlchemy 自己的构造器）而不是手搓：形状（顶层是那个宽基类
    ``DBAPIError``、``orig`` 挂原始异常）正是「宽 catch 会误吞」要验的东西。
    """
    return sqlalchemy.exc.DBAPIError.instance("INSERT INTO dg_action_audit (...) VALUES (...)", {}, orig, Exception)


def _counting_ensure_tables(calls: dict) -> Callable[[], Awaitable[None]]:
    async def _inner() -> None:
        calls["n"] += 1

    return _inner


async def test_connection_failure_does_not_trigger_lazy_build(monkeypatch, lazy_flag_reset):
    """**连接失败不是「表不存在」**：不得懒建，且必须如实转 ActionError 500。

    为什么这条必须有：宽 catch（``except DBAPIError``）会把一次基础设施故障改写成
    「懒建之后仍失败」——去做一次注定失败的建表、再重试一次注定失败的写，最后抛出的错误
    盖住真正的原因。判别力（变异实测见报告）：把 ``_is_missing_table_error`` 换成
    ``except DBAPIError`` → 本条红（calls 变 1）。
    """
    calls = {"n": 0}
    monkeypatch.setattr(executor_module, "ensure_tables", _counting_ensure_tables(calls))
    monkeypatch.setattr(
        executor_module,
        "create_async_engine",
        lambda *a, **k: _FailingEngine(_dbapi_error(ConnectionRefusedError("connection refused"))),
    )
    pk = await _seed_entity()
    with pytest.raises(ActionError) as e:
        await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))
    assert e.value.status_code == 500  # DB 不可达是服务端问题
    assert "写事务失败" in e.value.detail
    assert calls["n"] == 0, "连接失败被当成了表缺失 → 懒建被触发（吞错）"
    assert await _get_status(pk) == "pending_review"


_NON_MISSING_DB_ERRORS = {
    "privilege_42501": lambda: _dbapi_error(asyncpg.exceptions.InsufficientPrivilegeError("permission denied for table dg_action_audit")),
    "conn_refused_no_sqlstate": lambda: _dbapi_error(ConnectionRefusedError("connection refused")),
    "undefined_column_42703": lambda: _dbapi_error(asyncpg.exceptions.UndefinedColumnError('column "x" does not exist')),
    "query_canceled_57014": lambda: _dbapi_error(asyncpg.exceptions.QueryCanceledError("canceling statement due to statement timeout")),
    # asyncpg 的 command_timeout 触发时抛的是 **asyncio TimeoutError**，不是 57014（2026-09-23 实测：
    # 引擎带 command_timeout=1 跑 pg_sleep(5) → 链上只有 TimeoutError，没有 sqlstate）。这条把
    # Task 5 Step 6 (b) 那个超时的**真实形状**也钉在「不触发懒建」这一侧。
    "command_timeout_TimeoutError": lambda: TimeoutError(),
}


@pytest.mark.parametrize("case", list(_NON_MISSING_DB_ERRORS))
async def test_only_missing_table_triggers_lazy_build(monkeypatch, lazy_flag_reset, case):
    """**只有 42P01** 触发懒建；其余 DB 失败一律如实 500。

    几个近亲都要挡住：42501（权限——建表同样建不了，重试只会再失败一次）、42703（同属
    Undefined* 家族，但不是「表缺失」）、57014（服务端取消：`statement_timeout` /
    `pg_cancel_backend` 给的就是它）、`TimeoutError`（**asyncpg 的 command_timeout 抛的那个**——
    链路刚被掐断时去建表是南辕北辙，只会再撞一次同样的超时）。
    前三条都带 sqlstate，故本条同时钉住「判的是 sqlstate 的**值**，不是『有没有 sqlstate』」。
    """
    calls = {"n": 0}
    write_calls = {"n": 0}
    monkeypatch.setattr(executor_module, "ensure_tables", _counting_ensure_tables(calls))

    async def _boom() -> tuple[dict, dict]:
        write_calls["n"] += 1
        raise _NON_MISSING_DB_ERRORS[case]()

    with pytest.raises(ActionError) as e:
        await executor_module._write_with_lazy_audit_table(_boom)
    assert e.value.status_code == 500
    assert "写事务失败" in e.value.detail
    assert calls["n"] == 0, f"{case} 触发了懒建——识别器太宽"
    assert write_calls["n"] == 1, "失败被重试了——除 42P01 外都不该重试"


async def test_command_timeout_failure_detail_is_not_empty(monkeypatch, lazy_flag_reset):
    """命令阶段超时转出的 detail **不得为空**（Task 7 收口该超时时补的钉子）。

    为什么需要单列一条：``str(TimeoutError())`` 是空串，而 Task 7 之后这条路径是**设计上可达**
    且用户会看到的（写路径引擎现在带 `command_timeout`）。回到 `f"{prefix}: {exc}"` 的写法时
    detail 变成 ``"写事务失败: "``——**唯一线索被留空**，而上面那条参数化用例断的是
    ``"写事务失败" in detail``，它照样绿（变异实测：把 `_write_failure_detail` 短路成
    `f"{prefix}: {exc}"` → 只有本条红）。
    """

    async def _timeout() -> tuple[dict, dict]:
        raise TimeoutError()

    with pytest.raises(ActionError) as e:
        await executor_module._write_with_lazy_audit_table(_timeout)
    assert e.value.status_code == 500
    assert e.value.detail.strip() != "写事务失败:", f"超时 detail 丢光了线索: {e.value.detail!r}"
    assert f"{executor_module._WRITE_COMMAND_TIMEOUT_S}s" in e.value.detail, "detail 未写明是哪个超时、值是多少"


async def test_lazy_build_is_attempted_once_per_process(monkeypatch, lazy_flag_reset):
    """有界：懒建后仍失败 → 抛出且**不再重试**（每进程一次，不是重试循环）。

    判别力（变异实测见报告）：删掉 ``_build_audit_table_once`` 的 flag 分支 → 第二个请求
    的计数变 2 → 本条红。
    """
    calls = {"n": 0}
    write_calls = {"n": 0}
    monkeypatch.setattr(executor_module, "ensure_tables", _counting_ensure_tables(calls))

    async def _still_missing() -> tuple[dict, dict]:
        write_calls["n"] += 1
        raise asyncpg.exceptions.UndefinedTableError('relation "dg_action_audit" does not exist')

    with pytest.raises(ActionError) as first:
        await executor_module._write_with_lazy_audit_table(_still_missing)
    assert first.value.status_code == 500
    assert "懒建审计表后写入仍失败" in first.value.detail  # 懒建过、重试过，仍失败才抛
    assert calls["n"] == 1 and write_calls["n"] == 2, (calls, write_calls)  # 重试**恰好**一次

    with pytest.raises(ActionError) as second:
        await executor_module._write_with_lazy_audit_table(_still_missing)
    assert calls["n"] == 1, "懒建被第二次尝试了——有界 flag 失效"
    assert write_calls["n"] == 3, "第二个请求不该重试（连表都还没建出来）"
    assert "已尝试过懒建" in second.value.detail


async def test_lazy_build_failure_is_action_error_and_not_retried(monkeypatch, lazy_flag_reset):
    """懒建本身失败（DB 不可达/权限不足）→ 如实 ActionError 500，写不重试、建表不再试。

    有界的代价写在这里也算账：DB 恢复后本进程不会再自动补建（flag 已置位），需重启或人工
    建表——**这是有意的**，被无界重试换来的「每个请求多一次建表尝试」不值得。
    """
    calls = {"n": 0}
    write_calls = {"n": 0}

    async def _failing_ensure_tables() -> None:
        calls["n"] += 1
        raise _dbapi_error(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr(executor_module, "ensure_tables", _failing_ensure_tables)

    async def _still_missing() -> tuple[dict, dict]:
        write_calls["n"] += 1
        raise asyncpg.exceptions.UndefinedTableError('relation "dg_action_audit" does not exist')

    with pytest.raises(ActionError) as e:
        await executor_module._write_with_lazy_audit_table(_still_missing)
    assert e.value.status_code == 500
    assert "自动建表失败" in e.value.detail
    assert calls["n"] == 1 and write_calls["n"] == 1, (calls, write_calls)  # 建表失败即抛，不再重试写


async def test_returns_audit_id_of_the_audit_row():
    """spec §2 的返回契约含 ``audit_id``：审计表（设计 §1.2）存在的意义就是追溯，调用方
    拿不到审计 id 就断了追溯钩子——Task 7/8 上线后再补要动契约。

    断言**等于审计行的 id**（单点查库比对），而不是"字段存在"：后者对写死一个常量、
    或对错拿上一行的 id 都没有判别力。
    """
    pk = await _seed_entity()
    result = await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))

    audit = await _audit_rows(pk)
    assert len(audit) == 1
    assert result["audit_id"] == str(audit[0]["id"])
    assert isinstance(result["audit_id"], str)  # 与 "pk" 同形：Task 8 原样 json.dumps


async def test_write_path_engine_bounds_both_phases(monkeypatch):
    """确定性钉住写路径引擎的**两个阶段**超时——照 Task 3 的「捕获引擎实参」手法，不用计时
    上界（上界抓不到值漂移，那条已被变异证伪）。

    握手与命令两个阶段**分开裁决**（见 app/db.py 末尾的表）：握手无「合法的长等待」，
    无超时即请求永久挂起并占住 ASGI 任务，误杀面为零；命令阶段有合法的长等待
    （`SELECT ... FOR UPDATE` 撞并发长事务），超时值必须**明显高于**它——但 Phase 无界
    同样是"占住 ASGI 任务"，只是位置更靠后（链路被静默掐断时只能等 TCP keepalive）。

    **本用例在 Task 7 被翻转过一次，别按旧文读**：此前断言 `command_timeout` **缺席**，
    理由是"让将来加它必须是一次有意识的决定"。Task 7 做了那次决定（计划 line 131
    「留给 Task 7 的暴露面裁决」）→ 现在正向断言其**存在且等于写路径自己的 60s**，
    并额外断言它**故意不等于** `db._COMMAND_TIMEOUT_S`（两条路径的误杀面不同，见
    executor 顶部常量注释；用 `!=` 挡住"顺手统一成同源"）。
    """
    pk = await _seed_entity()
    captured: dict = {}
    real = create_async_engine
    monkeypatch.setattr(
        executor_module,
        "create_async_engine",
        lambda url, **kw: (captured.update(kw), real(url, **kw))[1],
    )

    await _invoke(pk=pk, scope_rule=FilterRule(operator="allow_all"))

    # `==` 而非 `<=`（M-3）：本测试声明「与 app/db.py 同值**同源**」，而 `<= 5` 抓不到
    # 「db._CONNECT_TIMEOUT_S 改成 3、这里留 5」的漂移——那正是"同源"被破坏的形态。
    assert "connect_args" in captured, "写路径引擎丢了握手超时——黑洞地址上请求会永久挂起"
    assert captured["connect_args"].get("timeout") == db._CONNECT_TIMEOUT_S, captured["connect_args"]
    # Task 7 裁定（计划 line 131「留给 Task 7 的暴露面裁决」）：命令阶段**已收口**。
    # 本断言此前是 `not in`（有意留空，且写明"将来加它必须是一次有意识的决定"）——Task 7 做了
    # 那次决定，故此处翻转为**正向**断言，值的漂移由 `==` 钉住（照同一条 `==` 而非 `<=` 的道理）。
    # **故意不等于 db._COMMAND_TIMEOUT_S**：两条路径的误杀面不同（那边 ≈ 一条 WARNING，这边是
    # 用户可见的 500），取 60 而非 30 的理由见 executor 顶部常量注释。故意用 `!=` 反向断言，
    # 免得后人"顺手统一成同源"把这条取舍抹平。
    assert captured["connect_args"].get("command_timeout") == executor_module._WRITE_COMMAND_TIMEOUT_S, captured["connect_args"]
    assert executor_module._WRITE_COMMAND_TIMEOUT_S != db._COMMAND_TIMEOUT_S, "写路径与建表路径的命令超时不是同一条取舍，别统一成同源"


async def test_missing_target_table_does_not_trigger_lazy_build(monkeypatch, lazy_flag_reset):
    """I-1 反例：**目标表**缺失而审计表好好的 → 不得懒建、不得烧 flag、且 500 而非 404。

    为什么必须单列一条（今日该维度零覆盖，`_NON_MISSING_DB_ERRORS` 那几条都验不到"语句维度"）：
    识别器只看「异常链里有没有 42P01」、**不看是哪条语句报的**，而同一事务里有三条语句打在
    目标表上。放它过去有三个各自独立成立的后果——
    ① 一次目标表 DDL 事故被报成 404「目标不存在或不在可见范围内」（把基础设施故障改写成
       误导性路径，正是识别器注释里自称要避免的）；
    ② 本进程一次性的懒建额度被烧掉，之后**真的**审计表缺失时归因错；
    ③ `create_all` 建**所有**缺失的 dg_* 表 → 目标表被静默重建为**空表**，下次请求拿到一个
       看起来合理的 404，而真正的 DDL 事故不可见。

    可达性：registry 热加载且 `access.table` 不与库比对（新域声明先于 DDL 落地即触发）；
    离线部署的部分恢复更是同时缺多张表。
    """
    scratch = _scratch_url()
    monkeypatch.setattr(connectors, "_ext_url", lambda: scratch)
    monkeypatch.setattr(executor_module, "_ext_url", lambda: scratch)
    await _admin_exec(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}" WITH (FORCE)')
    await _admin_exec(f'CREATE DATABASE "{_SCRATCH_DB}"')
    await ensure_tables()  # scratch 里 dg_* 全就位（含审计表）
    await _exec_in(scratch, "DROP TABLE dg_entities CASCADE")  # 只拿掉**目标表**

    calls = {"n": 0}
    real_ensure_tables = executor_module.ensure_tables

    async def _counting_ensure_tables() -> None:
        calls["n"] += 1
        await real_ensure_tables()

    monkeypatch.setattr(executor_module, "ensure_tables", _counting_ensure_tables)

    with pytest.raises(ActionError) as e:
        await _invoke(pk=uuid.uuid4(), scope_rule=FilterRule(operator="allow_all"))

    assert e.value.status_code == 500, "目标表缺失被误报成 404（会读成'行不存在或不在可见范围'）"
    assert "目标表不存在" in e.value.detail
    assert calls["n"] == 0, "目标表缺失不该触发懒建（建表只该由审计表的 42P01 触发）"
    assert executor_module._lazy_schema_attempted is False, "一次性懒建额度被目标表的 42P01 烧掉了"


async def test_malformed_db_url_is_action_error(monkeypatch):
    """M-1：引擎构造也在错误归一之内。

    不包的话 URL 畸形（配置写坏）抛的是 `ArgumentError`（SQLAlchemyError 子类）——与本模块
    「只有一种对外异常」及「DB 不可达 → 500」都不对称：连不上归一到 500，URL 坏了却裸抛，
    Task 7 的 `except ActionError` 接不住。
    """
    monkeypatch.setattr(executor_module, "_ext_url", lambda: "这不是一个-URL")
    with pytest.raises(ActionError) as e:
        await _invoke(pk=uuid.uuid4(), scope_rule=FilterRule(operator="allow_all"))
    assert e.value.status_code == 500
    assert "引擎构造失败" in e.value.detail
