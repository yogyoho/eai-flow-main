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
    _: CurrentUser = Depends(require_permission("system:access")),
):
    parsed: list[dict[str, Any]] | None = None
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"filters 不是合法 JSON: {e}") from e
    try:
        return await _get_engine().list_objects(object_type, filters=parsed, q=q, limit=limit, cursor=cursor, order=order, desc=desc)
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


def _project_incrementally(action_id: str, pk: uuid.UUID) -> None:
    """增量重投影：只刷新受影响行对应的三元组（设计 §2 步骤 5）。

    **当前实现是全量重算**——``get_kernel().refresh()`` 做 schema 重编 + 闭包 + 全部规则
    重跑（``app/ontology/kernel/service.py:31``），与"只刷这一行"无关。名字描述的是**契约**
    （调用方只关心"这次提交后图被更新了"），不是当前代价；真正的增量收敛是 P1-7 的独立任务，
    **此处如实标注，不假装已经增量**。

    代价（**实测**，2026-09-23，内存 kernel + ``load_ontology`` 装载后计时 ``refresh()``）：
    每次动作一次全量重算，随图规模近似线性——**约 0.8 ms / 三元组**：

    | 实体数 | 断言三元组 | refresh |
    |---|---|---|
    | 100 | 163 | 246 ms |
    | 500 | 563 | 534 ms |
    | 1000 | 1063 | 1056 ms |
    | 2000 | 2063 | 1692 ms |

    （含约 0.2 s 与规模无关的固定开销：schema 重编 + owlrl 初始化。按 0.8 ms/三元组外推：
    **1 万级 ≈ 8 s、5 万级 ≈ 40 s+**——那已是用户可感知的写延迟。）

    更要紧的不是这几百毫秒，而是**它在本函数里是同步的**：这段计算直接占住一个 ASGI 事件
    循环任务，期间该 worker 上其它请求全部排队（不是"慢一点"，是"并发被掐住"）。所以判据是
    **并发量 × 规模**：单实例 dev / 小图（今日形态）可接受；一旦本体图进入**万级三元组或
    出现并发动作**，就必须收敛成真增量（P1-7），不能继续按"反正很快"处理。

    **必须同步**：``invoke_action_core`` 同步调用 ``project(action_id, pk)``（executor 模块
    docstring 明文记了这条）。写成 ``async def`` 时它会拿到一个**被丢弃的协程对象**，异常不回传、
    **静默算作 projected=True**——最糟的一类失败：看起来成功。tests/test_actions_rest.py 有
    两条用例钉住（同步性 + 异常不吞）。

    异常**向外抛**，由 executor 记入 ``errors``（投影失败不回滚业务状态，设计 §2 步骤 5）；
    这里绝不吞——吞掉等于让 ``projected`` 恒 True，运维失去唯一的失败信号。
    """
    from app.ontology.kernel.service import get_kernel

    get_kernel().refresh()


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
