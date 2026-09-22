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
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

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
    try:
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
