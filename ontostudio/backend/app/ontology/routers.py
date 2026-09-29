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
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


# EAI-CUSTOM(2026-09-29): include=mentions → 投影含 mention 溯源节点/边（默认排除，见
# graph_views._MENTION_TYPES——批量入图后 mention 行数远超实体，会挤占本体浏览 limit 窗口）。
def _include_mentions(include: str | None) -> bool:
    return "mentions" in {s.strip() for s in (include or "").split(",") if s.strip()}


# EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain= 查询参数（doc_graph|eia）——过滤实体类型
# 行域，语义在 graph_views（声明了 filterable domain 属性的类型走引擎行过滤；无域列的
# 关系/证据类型保持脚手架不参与域裁剪）。可用域集合取自 registry 各对象类型的 domain 声明，
# 未知值 422（不是静默空集——拼错域名的请求应该被点名，而不是拿到一张"空图"还以为没数据）。
def _domain_or_422(domain: str | None) -> str | None:
    if domain is None or not domain.strip():
        return None
    d = domain.strip()
    allowed = {ot.domain for ot in get_registry().object_types.values() if ot.domain}
    if d not in allowed:
        raise HTTPException(status_code=422, detail=f"未知域: {d}（可用域: {sorted(allowed)}）")
    return d


@router.get("/graph/nodes")
async def graph_nodes(
    limit: int = 500,
    cursor: str | None = None,
    include: str | None = None,
    domain: str | None = None,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """语义地图统一节点投影（全部 enabled 对象类型，Explorer 方言）。

    EAI-CUSTOM(2026-09-29): 默认排除 mention 溯源节点（label=uuid，不进本体浏览窗口，
    经 DetailPanel 懒加载查看）；`include=mentions` opt-in 恢复全集。
    EAI-CUSTOM(2026-09-29 图谱投影域过滤): `domain=doc_graph|eia` 服务端行过滤（实体类型
    行域）；缺省行为不变。游标只编 type_idx/offset——跨域传同一游标是调用方错误，不设防。
    """
    try:
        return await nodes_page(get_registry(), _get_engine(), cursor, max(1, min(limit, 2000)), _include_mentions(include), domain=_domain_or_422(domain))
    except OntologyError as e:
        raise _http_error(e) from e


@router.get("/graph/edges")
async def graph_edges(
    limit: int = 1000,
    cursor: str | None = None,
    include: str | None = None,
    domain: str | None = None,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """语义地图统一边投影（全部 enabled 链接；stub 不产生边）。

    EAI-CUSTOM(2026-09-29): 默认与节点同规则排除 mention 链接（节点不在场则边成孤端）；
    `include=mentions` opt-in 恢复全集。
    EAI-CUSTOM(2026-09-29 图谱投影域过滤): `domain=` 与节点同参——链接两端声明了域属性的
    一侧加行域守卫（如 relation_subject 的实体端），无域列的一端不裁剪（与节点侧
    脚手架语义一致）。缺省行为不变。
    """
    try:
        return await edges_page(get_registry(), _get_engine(), cursor, max(1, min(limit, 5000)), _include_mentions(include), domain=_domain_or_422(domain))
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


# ── 批量执行（EAI-CUSTOM 2026-09-29 批量确认摊销）────────────────────────────
# 与单条同一套双层鉴权（操作权限 + 数据范围，逐 batch 一次而非逐行），行级执行与
# 全批一次投影在 executor.invoke_action_batch_core。选型（单条路径不动）：单条
# /actions/invoke **保留同步投影**——写/投影本就解耦（行事务提交后投影，投影失败
# degraded 不回滚，重跑全量装载自愈），审计一致性与 fail-closed 均无破坏；改后台
# refresh 会破坏四态 UI 的 projected:true 契约并有进程重启丢 refresh 的风险。
# 批量场景的提效走本端点的 O(1) 摊销（全批一次 refresh）。

_MAX_BATCH_PKS = 200
"""单批 pks 上限 = 前端待审拉取上限（ontology-graph-api PENDING_REVIEW_LIMIT）。
超限 422：批量是摊销手段，不是把无限列表灌进一个请求的通道。"""


class ActionInvokeBatchRequest(BaseModel):
    """批量动作调用入参（契约同 ActionInvokeRequest 的 extra="forbid" / UUID 校验）。

    重复 pk 422：同批重复行第二次必撞前置条件（409），让它进 failed 列表只会制造
    一条看似真实的假失败——入口直接点名更诚实。
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    pks: list[uuid.UUID] = Field(min_length=1, max_length=_MAX_BATCH_PKS)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pks")
    @classmethod
    def _no_duplicate_pks(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len({str(p) for p in value}) != len(value):
            raise ValueError("pks 含重复主键")
        return value


def _project_batch_amortized(action_id: str, rows: dict[uuid.UUID, dict[str, Any]]) -> set[uuid.UUID]:
    """批量提交后投影（REST 通道入口，委托 ``actions.projection.project_rows``）。

    EAI-CUSTOM(2026-09-29 批量确认摊销)：与单条 ``_project_incrementally`` 同源
    （双通道共享 projection 模块），差异只在摊销——N 行一次装载 + 全批一次
    ``refresh()``。**必须同步**：``invoke_action_batch_core`` 同步调用本函数，写成
    ``async def`` 会拿到被丢弃的协程并静默算作 projected=True（与单条同坑，tests
    钉住同步性）。异常**向外抛**，由 executor 全批记 degraded（不回滚业务状态）。
    """
    from app.ontology.actions.projection import project_rows

    return project_rows(action_id, rows)


@router.post("/actions/invoke_batch")
async def invoke_action_batch_endpoint(
    body: ActionInvokeBatchRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("system:access")),
):
    """批量执行同一动作（EAI-CUSTOM 2026-09-29 批量确认摊销）。

    鉴权与单条 ``/actions/invoke`` 完全同层：路由级 ``system:access`` + 动作
    ``required_permissions``（authorize 逐条）+ 数据范围（scope_resource → FilterRule），
    每批解析一次——范围规则是按调用者身份取的，对批内每一行同等生效（行级 404 仍由
    executor 逐行裁决，不因批量放宽）。

    响应体逐行结果（``results``/``succeeded``/``failed``）：失败行带 ``status_code``/
    ``detail``（404 范围外 / 409 前置不满足 / 500 DB 故障），HTTP 状态整体仍 200——
    部分成功是本端点的正常形态，用 207/多状态反而逼客户端解析混合语义。
    只有鉴权/声明级失败才以 4xx/5xx 短路（与单条一致）。
    """
    from app.ontology.actions.executor import ActionError, invoke_action_batch_core

    try:
        _action, scope_rule = await _authz_for_action(request, user, body.action_id)
        actor_role = await resolve_actor_role(request, user)
        return await invoke_action_batch_core(
            body.action_id,
            body.params,
            target_pks=list(body.pks),
            actor_id=user.id,
            actor_role=actor_role,
            source="api",
            scope_rule=scope_rule,
            # 直接传函数本身（同单条的理由）。
            project_batch=_project_batch_amortized,
        )
    except ActionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
