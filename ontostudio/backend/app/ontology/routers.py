"""Ontology 语义层 REST 路由 — 6 核心端点（pytest HTTP 集成测试载体）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §8
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T6（D16）

EAI-CUSTOM(2026-08-15): 只读语义地图/管理查询，admin-gated(system:access)。
search/traverse/reload 包装随 1b（D16 砍面后的剩余项）。

EAI-CUSTOM(2026-09-22, plan Task 7): 末段追加**动作执行**端点
``POST /actions/invoke``——本模块唯一的写路径暴露面（设计 §2/§3）。
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

# EAI-CUSTOM(2026-09-17 迁出独立): 原 gateway 依赖 app.extensions.auth.middleware /
# app.extensions.schemas → 本地 app.auth（S1 Task 2 已实装 HS256 JWT 验签, v1 superadmin-only）。
# EAI-CUSTOM(2026-09-22 Task 7): authorize / fetch_scope_rule / resolve_actor_role 三个动作层
# 入口**顶层**导入——测试经 ``app.ontology.routers.<name>`` 打桩（见 tests/test_actions_rest.py）。
from app.auth import CurrentUser, authorize, fetch_scope_rule, require_permission, resolve_actor_role
from app.ontology.connectors import OntologyConnectors
from app.ontology.engine import Engine, OntologyError
from app.ontology.graph_views import edges_page, nodes_page
from app.ontology.registry import get_registry, get_registry_store
from app.ontology.scope import FilterRule

router = APIRouter(prefix="/api/extensions/ontology", tags=["ontology"])

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine(get_registry, OntologyConnectors())
    return _engine


def _http_error(e: Exception) -> HTTPException:
    status = 404 if type(e).__name__ in ("UnknownObjectError", "UnknownLinkError") else 400
    return HTTPException(status_code=status, detail=f"{type(e).__name__}: {e}")


@router.get("/registry")
async def get_registry_meta(_: CurrentUser = Depends(require_permission("system:access"))):
    """注册表元信息 + 各 access 可用性（断连显式 available:false）。"""
    store = get_registry_store()
    reg = store.get()
    seen: set[tuple[str, str | None, str | None]] = set()
    accesses = []
    for o in reg.object_types.values():
        key = (o.access.path, o.access.source_id, o.access.table or o.access.table_name)
        if key not in seen:
            seen.add(key)
            accesses.append(o.access)
    con = OntologyConnectors()
    return {
        "registry_version": reg.registry_version,
        "fingerprint": store._agg(reg)[:8],
        "schema_version": reg.manifest.schema_version,
        "object_type_count": len(reg.object_types),
        "link_type_count": len(reg.link_types),
        "availability": await con.availability(accesses),
    }


@router.get("/object-types")
async def list_object_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = get_registry()
    return {
        "object_types": [{"name": o.api_name, "display_name": o.display_name, "description": o.description, "pk": o.pk.api_name, "properties": [p.api_name for p in o.visible_properties()]} for o in reg.object_types.values()],
        "link_types": [{"name": lt.api_name, "source": lt.source, "target": lt.target, "enabled": lt.enabled, **({"note": lt.note} if not lt.enabled and lt.note else {})} for lt in reg.link_types.values()],
    }


@router.get("/objects/{object_type}")
async def list_objects(
    object_type: str,
    filters: str | None = Query(None, description='JSON 数组, 如 [{"column":"unit_price","op":"gte","value":100}]'),
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    order: str | None = None,
    desc: bool = False,
    offset: int = Query(0, ge=0, description="页码分页偏移（与 cursor 互斥）"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    parsed: list[dict[str, Any]] | None = None
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"filters 不是合法 JSON: {e}") from e
    try:
        return await _get_engine().list_objects(object_type, filters=parsed, q=q, limit=limit, cursor=cursor, order=order, desc=desc, offset=offset)
    except OntologyError as e:
        raise _http_error(e) from e


@router.get("/objects/{object_type}/{pk}")
async def get_object(object_type: str, pk: str, _: CurrentUser = Depends(require_permission("system:access"))):
    try:
        obj = await _get_engine().get_object(object_type, pk)
    except OntologyError as e:
        raise _http_error(e) from e
    if obj is None:
        raise HTTPException(status_code=404, detail=f"未找到 {object_type}#{pk}")
    return obj


@router.get("/objects/{object_type}/{pk}/links/{link_type}")
async def get_links(
    object_type: str,
    pk: str,
    link_type: str,
    limit: int = 100,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        return await _get_engine().get_links(object_type, pk, link_type, limit=limit)
    except OntologyError as e:
        raise _http_error(e) from e


@router.post("/aggregate")
async def aggregate(
    body: dict[str, Any],
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        return await _get_engine().aggregate(body["object_type"], body["group_by"], metric=body.get("metric", "count"), metric_column=body.get("metric_column"), filters=body.get("filters"), limit=body.get("limit", 100))
    except OntologyError as e:
        raise _http_error(e) from e
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"缺少必填字段: {e}") from e


# EAI-CUSTOM(2026-09-12, plan Task1): 语义地图图投影端点（Semantica Explorer 方言，投影逻辑在 graph_views.py）


@router.get("/graph/nodes")
async def graph_nodes(
    limit: int = 500,
    cursor: str | None = None,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """语义地图统一节点投影（全部 enabled 对象类型，Explorer 方言）。"""
    try:
        return await nodes_page(get_registry(), _get_engine(), cursor, max(1, min(limit, 2000)))
    except OntologyError as e:
        raise _http_error(e) from e


@router.get("/graph/edges")
async def graph_edges(
    limit: int = 1000,
    cursor: str | None = None,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """语义地图统一边投影（全部 enabled 链接；stub 不产生边）。"""
    try:
        return await edges_page(get_registry(), _get_engine(), cursor, max(1, min(limit, 5000)))
    except OntologyError as e:
        raise _http_error(e) from e


# ── 动作执行（EAI-CUSTOM 2026-09-22, plan Task 7 / 设计 §2 §3）──────────────
# 本模块的**唯一写路径**。鉴权分两层，两层都过才落到 invoke_action_core：
#   ① 操作权限 —— 动作声明里的 required_permissions，逐条问 gateway（authorize）
#   ② 数据范围 —— 目标对象类型的 scope_resource → FilterRule（fetch_scope_rule）
# 另有一道**路由级**门槛（system:access），它只决定"能不能进这个面"，不参与上面两层。


class ActionInvokeRequest(BaseModel):
    """动作调用入参。

    ``extra="forbid"``：调用方多传一个字段（例如以为有 ``force``）时 422 而不是静默忽略。

    ``pk`` 用 ``uuid.UUID`` 而非 ``str``（**偏离计划①**）：计划写 ``pk: str`` + 函数体里
    ``uuid.UUID(body.pk)``，畸形 pk 会以 ``ValueError`` 逃成**丢掉 detail 的裸 500**。
    归因是"送来的东西不可用"，按本仓错误契约（executor 模块 docstring 的表）该是 4xx；
    交给 Pydantic 校验即得 422，且校验点与 action_id 同级、不再散在函数体里。
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    pk: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)


async def _authz_for_action(request: Request, user: CurrentUser, action_id: str) -> tuple[Any, FilterRule]:
    """解析动作 → 逐条校验 ``required_permissions`` → 取 ``scope_resource`` 的范围规则。

    两层缺一不可：只用权限点会漏掉"这人能审，但不能审**这一行**"；只用数据范围会漏掉
    "这行在他范围内，但他没有审核权"。

    ``scope_resource`` 未声明 → ``allow_all``：**放行的是范围，不是权限**（第 ① 层照查）。
    这条回退今日不生效（所有动作都 targeting ``graph_entity``，而它声明了 ``ontology``），
    是给"对象类型无身份列、无从按行裁剪"的将来形态留的口子——**有意的**，不是漏判。
    """
    from app.ontology.actions.executor import ActionError, _resolve

    action, obj = _resolve(action_id)
    for perm in action.required_permissions:
        if not await authorize(request, user, perm):
            raise ActionError(f"缺少权限：{perm}", status_code=403)

    if not obj.scope_resource:
        return action, FilterRule(operator="allow_all")
    rule = await fetch_scope_rule(request, obj.scope_resource)
    return action, rule


def _project_incrementally(action_id: str, pk: uuid.UUID, row: dict[str, Any] | None) -> None:
    """提交后投影（REST 通道入口，委托 ``actions.projection.project_row``）。

    EAI-CUSTOM(2026-09-26 人审闭环切片 T2)——本函数**此前的 docstring 与实现双双失真**：
    名字承诺"只刷受影响行"，实现却是 ``get_kernel().refresh()``（schema 重编+闭包+全规则，
    store-global），且**从不读 ``dg_*`` 行**——确认后接口回 ``projected:true`` 而断言图没有
    这一行（KNOWN_GAP，原 ``test_03_..._KNOWN_GAP`` 用例钉住，本切片反转并删除该用例）。
    docstring 亦只承认"非增量"、未承认"根本没投影"——一并订正于此。

    现委托双通道共享的 ``project_row``（MCP 同源，T3A）：executor 传入合并行（T1A，
    ``FOR UPDATE`` 锁定行 ∪ ``RETURNING`` after，投影不复读 DB）→ 单行装载（force_status
    强转：确认→active、驳回→rejected）→ ``refresh()`` 重跑闭包与规则。

    代价口径：refresh 是 store-global，单次确认 ≈ 全量 refresh（千级图秒级；实测表与
    "同步占住 ASGI worker"的并发警告见 eng-review OQ1 与设计稿 Open Questions，不再复述）。

    **必须同步**：``invoke_action_core`` 同步调用 ``project(...)``。写成 ``async def`` 会拿到
    被丢弃的协程并**静默算作 projected=True**——最糟的一类失败：看起来成功。
    tests/test_actions_rest.py 有两条用例钉住（同步性 + 异常不吞）。异常**向外抛**，
    由 executor 记入 ``errors``（degraded；重跑 ``POST /formal/load`` 自愈，不回滚业务状态）。
    """
    from app.ontology.actions.projection import project_row

    project_row(action_id, pk, row)


@router.post("/actions/invoke")
async def invoke_action_endpoint(
    body: ActionInvokeRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("system:access")),
):
    """执行一个已声明的动作（设计 §2）。

    权限分两层：操作权限（``required_permissions``，经 ``authorize``）与数据范围
    （``scope_resource`` → ``FilterRule``）。两者任一不过即拒。

    ``actor_role`` 取角色 **code**（非显示名）且来自 gateway 正典身份——理由见
    ``app.auth.resolve_actor_role`` 的 docstring（简短版：显示名会随改名改历史审计行，
    而本服务的 ``role_name`` 只可能来自 claims，gateway Cookie 不带角色 claim ⇒ 恒 NULL）。
    它**失败不拒动作**：审计标注缺失不该拦下一次合法审核。

    返回体中的 ``before``/``after``/``projected``/``errors`` 由 ``invoke_action_core`` 决定
    （见其 docstring）；本层只做错误映射——``ActionError`` 自带 ``status_code``/``detail``。
    """
    from app.ontology.actions.executor import ActionError, invoke_action_core

    try:
        _action, scope_rule = await _authz_for_action(request, user, body.action_id)
        actor_role = await resolve_actor_role(request, user)
        return await invoke_action_core(
            body.action_id,
            body.params,
            target_pk=body.pk,
            actor_id=user.id,
            actor_role=actor_role,
            source="api",
            scope_rule=scope_rule,
            # 直接传函数本身，不套 lambda：套一层反而多一个能把"同步/异步"写错的位置。
            project=_project_incrementally,
        )
    except ActionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
