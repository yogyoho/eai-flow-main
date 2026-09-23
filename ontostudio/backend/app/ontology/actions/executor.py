"""动作执行管线（设计 §2）。

Postgres dg_* 是唯一真相源；提交后的增量重投影失败**不回滚**业务状态，
只记入 errors 并可重放——与 kernel/infer.py 的失败降级取向一致。

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §2。

**错误契约（本模块只有一种对外异常）**：任何失败都以 ``ActionError``（含 ``ScopeDenied``）
抛出，``status_code`` / ``detail`` 直接被 Task 7 的 REST 与 Task 8 的 MCP 消费。
三个下游编译器的异常都要在这里归一：

| 来源 | 异常 | 归因 | 码 |
|---|---|---|---|
| ``scope.py::rule_to_sql`` | ``ScopeCompileError`` | 入参形状（规则从网关 wire 解出） | 400 |
| ``sql_write.build_precondition_where`` / ``build_update_set`` | ``WriteGuardError`` | registry 声明笔误（调用方无从修正） | 500 |
| ``registry`` 解析 | 本模块自产 | 声明缺失 | 404 / 500 |

400/500 的分界是**归因**而非严重度：400 = 送来的东西不可用，500 = 服务端自己的声明坏了。
不归一的话它们会以 ``ValueError`` 逃出模块，在 REST 层变成丢掉 detail 的裸 500。
**DB 故障**（连接失败、权限不足、审计表缺失）同样归一到 500：坏的是服务端这一侧——
归因与懒建/重试的规则见 ``_write_with_lazy_audit_table``。

**已知天花板（有意，非疏漏）**：数据范围里 ``not_in`` 的空集编译为 ``NOT (col = ANY('{}'))``
≡ ``TRUE`` ≡ **放行全部**（``NOT IN`` 的标准语义，方向与 ``in`` 相反）。今日无暴露路径——
参考实现 ``backend/app/extensions/auth/engine.py`` 不产出 ``ne/not_in/not``——且按设计 §9
它的修复位置在**网关侧解析层**（模板解析为空时 fail-closed 成 ``none_allow``），
**不在 ``scope.py``**（纯编译器不该做语义裁决）。若网关将来开始下发 ``not_in``，
必须先补上那条 fail-closed 再做。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db import ensure_tables
from app.ontology.actions.sql_write import WriteGuardError, build_precondition_where, build_update_set, quote_ident
from app.ontology.connectors import _ext_url
from app.ontology.registry import get_registry
from app.ontology.scope import FilterRule, ScopeCompileError, rule_to_sql


class ActionError(Exception):
    """动作执行失败。status_code/detail 直接映射到 HTTP 与 MCP 错误体。"""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ScopeDenied(ActionError):
    """目标行不在调用者的数据范围内。用 404 而非 403——不泄漏行是否存在。"""

    def __init__(self, detail: str = "目标不存在或不在可见范围内") -> None:
        super().__init__(detail, status_code=404)


def _resolve(action_id: str):
    """解析动作声明与其目标对象类型。未知即拒（fail-closed）。

    Registry 是合并快照（actions / object_types 两张扁平字典），不保存 per-domain
    DomainFile——所以这里按 id 直查，不遍历域。
    """
    registry = get_registry()
    action = registry.get_action(action_id)
    if action is None:
        raise ActionError(f"unknown action: {action_id}", 404)
    obj = registry.object_types.get(action.target)
    if obj is None:  # registry 加载时已校验，此处是纵深防御
        raise ActionError(f"action {action_id} target unresolved: {action.target}", 500)
    return action, obj


def _bind_params(target_pk: uuid.UUID, *fragments: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    """合并各片段产出的命名参数，键重复即拒。

    今日三处来源前缀互斥（``scope_N`` / ``pre_N`` / ``set_N``）且都不产 ``pk``，故正常路径
    永不触发（已逐处核对，并有测试钉住）。但 ``**`` 盲合并下"键撞了"不报错，只会让后写的值
    静默覆盖先写的——写路径上这意味着守卫按另一个量求值、或 UPDATE 打到别的行：
    **错的不是报错，而是没报错**。这里宁可直接失败。
    """
    merged: dict[str, Any] = {"pk": target_pk}
    for fragment_name, fragment_params in fragments:
        dupes = merged.keys() & fragment_params.keys()
        if dupes:
            raise ActionError(f"SQL 参数名冲突: {sorted(dupes)}（来源 {fragment_name}）", 500)
        merged.update(fragment_params)
    return merged


# ── 写路径韧性：审计表懒建 + 有界重试（计划 Task 5 Step 6）────────────────────────
# 背景：dg_action_audit 在活库里可能压根不存在——建表只在 lifespan 跑一次，而 dev compose
# 没有 postgres-ext 的 depends_on（offline 有），DB 后起时本服务早就在跑了（设计 §1.2.1
# 表第三行把这条缺口判给 Task 5）。本表**只有本模块一个写入方**，故「表不存在」的发现点
# 就在这条 INSERT 上；修在这里而不是给 lifespan 加轮询，是因为后者的代价（多一个与写路径
# 竞争的建表者）换不到任何东西。
_lazy_schema_attempted = False

_UNDEFINED_TABLE_SQLSTATE = "42P01"


def _is_missing_table_error(exc: BaseException) -> bool:
    """异常链里是否存在「表不存在」（SQLSTATE ``42P01``）——懒建的**唯一**触发器。

    为什么必须这么窄（``except DBAPIError`` 是错的）：宽 catch 会把连接失败、权限不足、
    死锁一并读成「表还没建」，于是去做一次注定失败的建表、再重试一次注定失败的写，最后
    抛出的错误指向「懒建之后仍失败」——一次普通的基础设施故障被改写成一条误导性路径
    （且真正的错误被后一条错误盖住）。只有 42P01 的含义是确定的：schema 缺失，且**恰好**
    是 create_all 能补上的那一类。

    为什么必须走异常链：asyncpg 的原始异常被 SQLAlchemy 包了两层，而**只有内层两层带
    ``sqlstate``**（顶层为 None——2026-09-23 对真库实测，见 tests/test_actions_executor.py
    的懒建测试）：
    ``sqlalchemy.exc.ProgrammingError`` → ``AsyncAdapt_asyncpg_dbapi.ProgrammingError``(42P01)
    → ``asyncpg.exceptions.UndefinedTableError``。只看最外层就永远不触发。
    只走 ``__cause__`` / ``orig``（SQLAlchemy 用 ``raise ... from ...`` 挂链），**不走
    ``__context__``**——后者是「恰好在外层 except 里又抛」的副产品，会把与本次失败无关的
    嵌套异常拉进来（假阳性）。
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, asyncpg.exceptions.UndefinedTableError):
            return True
        if _UNDEFINED_TABLE_SQLSTATE in (getattr(cur, "sqlstate", None), getattr(cur, "pgcode", None)):
            return True
        nxt: BaseException | None = cur.__cause__ if cur.__cause__ is not None else getattr(cur, "orig", None)
        cur = nxt if isinstance(nxt, BaseException) else None
    return False


async def _build_audit_table_once(original: BaseException) -> None:
    """懒建审计表——每进程**一次**；再失败就如实抛（不是一个重试循环）。

    有界为什么是硬要求：无界重试会把「DB 长期不可用」变成**每条写请求**都附带一次建表尝试
    （每次至少一个 5s 握手超时），而它注定失败——故障从「一条 500」放大成「每个请求多 5 秒
    且仍然失败」。flag 在 await **之前**置位：并发请求里只有第一个能建，其余立刻失败
    （fail-closed——宁可让调用方看到「表不存在」，也不让 N 个请求各建一次表）。

    已知限制（有意，非疏漏）：`create_all` **只建缺失的表，不做 schema 变更**——本机制
    只解决「dg_action_audit 不存在」，解决不了「表在但列不全」（那仍需人工迁移，同
    app/db.py 的声明）。别把懒建读成自动迁移。
    """
    global _lazy_schema_attempted
    if _lazy_schema_attempted:
        raise ActionError(f"审计表 dg_action_audit 不存在，且本进程已尝试过懒建（不再重试）: {original}", 500) from original
    _lazy_schema_attempted = True
    try:
        await ensure_tables()
    except Exception as exc:  # DB 不可达 / 权限不足 / 建表被拒 → 如实抛（服务端问题 = 500）
        raise ActionError(f"审计表 dg_action_audit 不存在，自动建表失败: {exc}", 500) from exc


async def _write_with_lazy_audit_table(
    write_txn: Callable[[], Awaitable[tuple[dict[str, Any], dict[str, Any]]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """写事务 + 「审计表不存在」时的**一次**懒建重试；其余 DB 失败如实转 ``ActionError``。

    归因（模块 docstring 的错误契约表同一套）：DB 失败一律 500——调用方没做错任何事
    （入参从不进 SQL 值位置），坏的是服务端这一侧。业务判定（``ScopeDenied`` 404 /
    前置条件 409）不是 DB 故障，原样上抛。

    重试必须在**新事务**里：``engine.begin()`` 的上下文已随异常回滚，复用它只会拿到一个
    失效事务——对同一事务再发任何语句只回 25P02（``InFailedSQLTransaction``，2026-09-23
    探针实测；同一 engine 上开新事务则正常）。那会把真正的错误盖成一个假错误。

    可测试性：写成「接受一个写事务可调用」而非内联，是为了让「只对 42P01 触发」「只重试
    一次」能用注入的失败确定性地钉住（真库只能给出 42P01 这一种反例）。
    """
    try:
        return await write_txn()
    except ActionError:
        raise
    except Exception as exc:
        if not _is_missing_table_error(exc):
            raise ActionError(f"写事务失败: {exc}", 500) from exc
        await _build_audit_table_once(exc)  # 失败即抛 ActionError（每进程一次，不再重试）
    try:  # 原事务已回滚 → 这一次是新事务
        return await write_txn()
    except ActionError:
        raise
    except Exception as exc:
        raise ActionError(f"懒建审计表后写入仍失败: {exc}", 500) from exc


async def invoke_action_core(
    action_id: str,
    params: dict[str, Any],
    *,
    target_pk: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str | None,
    source: str,
    scope_rule: FilterRule,
    project: Callable[[str, uuid.UUID], None],
) -> dict[str, Any]:
    """管线主体。鉴权与取范围规则由调用方（REST/MCP）完成后传入。

    project(action_id, pk) 在**提交后**调用，用于增量重投影；抛异常不回滚。
    它是**同步**可调用（Task 7 传的是 ``lambda: get_kernel().refresh()``）：传 async 函数
    只会拿到一个被丢弃的协程对象，并静默算作投影成功。
    """
    action, obj = _resolve(action_id)
    table = obj.access.table
    if not table:
        raise ActionError(f"action {action_id} target has no physical table", 500)

    # 声明编译分两处 try（数据范围规则 / 动作声明），异常一律归一为 ActionError——
    # 错误契约见模块 docstring 的表。
    try:
        scope_sql, scope_params = rule_to_sql(scope_rule, obj.scope_bindings or None)
    except ScopeCompileError as e:
        # 4xx：规则由网关注入，编译不了即入参侧数据不可用。这条映射是 scope.py 的 docstring
        # 明文派给 executor 的（"调用方只需捕获本异常映射 4xx"），计划给的代码漏了它。
        raise ActionError(f"数据范围规则无法编译: {e}", 400) from e

    # 表名 / 主键列 / 前置条件 / SET 的**标识符**也都只来自 registry 声明，同样过 sql_write
    # 的白名单——四处必须一起包：只包后两处的话，`table: dg-entities` 这类笔误会以裸
    # WriteGuardError 逃出去（自审实测确认）。
    try:
        pre_sql, pre_params = build_precondition_where(action.preconditions)
        set_sql, set_params = build_update_set(action.postconditions)
        pk_col = quote_ident(obj.pk.column)
        table_q = quote_ident(table)
        returning = ", ".join(quote_ident(c.field) for c in action.postconditions)
    except WriteGuardError as e:
        # 5xx：坏的是 registry 里的动作声明（热加载 YAML），与调用方及其 params 无关——
        # 设计 §2 订正写明本设计不存在"参数化前置条件"，params 从不进 SQL 值位置。
        # 归因与 _resolve 既有的两处 registry 缺陷（target unresolved / no physical table）一致。
        raise ActionError(f"动作声明不合法: {action.id}: {e}", 500) from e

    where = f"{pk_col} = :pk AND ({scope_sql})"
    params_all = _bind_params(target_pk, ("scope", scope_params), ("precondition", pre_params), ("set", set_params))

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    errors: list[str] = []

    async def _write_txn() -> tuple[dict[str, Any], dict[str, Any]]:
        """一次写事务：锁定行 → 前置条件 → UPDATE(RETURNING) → 审计。"""
        async with engine.begin() as conn:
            locked = await conn.execute(text(f"SELECT * FROM {table_q} WHERE {where} FOR UPDATE"), params_all)
            row = locked.mappings().first()
            if row is None:
                raise ScopeDenied()

            ok = await conn.execute(text(f"SELECT ({pre_sql}) AS ok FROM {table_q} WHERE {pk_col} = :pk"), params_all)
            if not ok.scalar_one():
                expected = ", ".join(f"{c.field} {c.op} {c.value!r}" for c in action.preconditions)
                raise ActionError(f"前置条件不满足：需要 {expected}", status_code=409)

            before = {c.field: row.get(c.field) for c in action.postconditions}

            # RETURNING 而非把 after 算成 "None = 由 DB 决定"：审计行（设计 §1.2）是这条写路径
            # 唯一的追溯凭据，一行写着 after.updated_at = null 而库里是 NOW() 就不是"由 DB 决定"，
            # 是**审计记录与实际不符**。RETURNING 搭在同一条 UPDATE 上，不额外多一次往返。
            updated = await conn.execute(text(f"UPDATE {table_q} SET {set_sql} WHERE {pk_col} = :pk RETURNING {returning}"), params_all)
            updated_row = updated.mappings().first()
            if updated_row is None:
                # 该行在上面已被 FOR UPDATE 锁定，同事务内不可能消失；到这里说明代码错了，
                # 不能继续写一条没有对应变更的审计行。
                raise ActionError(f"锁定行在 UPDATE 时消失: {target_pk}", 500)
            after = {c.field: updated_row[c.field] for c in action.postconditions}

            await conn.execute(
                text(
                    """INSERT INTO dg_action_audit
                       (action_id, domain, target_table, target_pk, actor_id, actor_role, params, before, after, source)
                       VALUES (:action_id, :domain, :tbl, :pk, :actor, :role,
                               CAST(:params AS jsonb), CAST(:before AS jsonb), CAST(:after AS jsonb), :source)"""
                ),
                {
                    "action_id": action.id,
                    "domain": action.domain,
                    "tbl": table,
                    "pk": target_pk,
                    "actor": actor_id,
                    "role": actor_role,
                    "params": _json(params),
                    "before": _json(before),
                    "after": _json(after),
                    "source": source,
                },
            )
            return before, after

    try:
        # 懒建审计表 / 有界重试 / DB 失败归因全在这层（见 _write_with_lazy_audit_table）
        before, after = await _write_with_lazy_audit_table(_write_txn)
    finally:
        await engine.dispose()

    try:
        project(action.id, target_pk)
        projected = True
    except Exception as e:  # 投影失败不回滚业务状态（设计 §2 步骤 5）
        projected = False
        errors.append(f"{type(e).__name__}: {e}")

    return {
        "action_id": action.id,
        "target": obj.api_name,
        "pk": str(target_pk),
        "before": before,
        "after": after,
        "source": source,
        "projected": projected,
        "errors": errors,
    }


def _json(value: Any) -> str:
    # default=str 兜住 datetime/Decimal 等非 JSON 类型（审计列是 jsonb，不容许序列化失败）。
    return json.dumps(value, ensure_ascii=False, default=str)
