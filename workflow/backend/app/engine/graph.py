"""In-memory flow graph and traversal semantics (NodeServiceImpl port)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FlowDefinition, FlowNode, FlowSkip
from ..utils import to_json
from .enums import NodeType, SkipType, is_gateway, is_start
from .expression import evaluate_condition


class FlowGraphError(ValueError):
    pass


@dataclass(slots=True)
class FlowGraph:
    definition: FlowDefinition
    nodes: dict[str, FlowNode]
    skips: list[FlowSkip]
    outgoing: dict[str, list[FlowSkip]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.outgoing:
            grouped: dict[str, list[FlowSkip]] = defaultdict(list)
            for skip in self.skips:
                grouped[skip.now_node_code].append(skip)
            self.outgoing = dict(grouped)

    def node(self, code: str) -> FlowNode:
        node = self.nodes.get(code)
        if node is None:
            raise FlowGraphError(f"节点不存在: {code}")
        return node

    @property
    def start_node(self) -> FlowNode:
        for node in self.nodes.values():
            if is_start(node.node_type):
                return node
        raise FlowGraphError("流程缺少开始节点")

    @property
    def end_node(self) -> FlowNode:
        for node in self.nodes.values():
            if node.node_type == NodeType.END:
                return node
        raise FlowGraphError("流程缺少结束节点")

    def next_node(
        self,
        now_node: FlowNode | str,
        any_node_code: str | None = None,
        skip_type: str = SkipType.PASS,
    ) -> FlowNode:
        node = self.node(now_node) if isinstance(now_node, str) else now_node
        if any_node_code:
            # Explicit targets are used by ``rejectAtWill`` / ``rejectLast``.  A
            # regular node is allowed here; the caller already resolved it from
            # history.  Gateways are expanded by ``next_nodes``.
            return self.node(any_node_code)
        if node.any_node_skip and skip_type == SkipType.REJECT:
            return self.node(node.any_node_skip)

        candidates = self.outgoing.get(node.node_code, [])
        if not candidates:
            raise FlowGraphError(f"节点 {node.node_code} 没有配置跳转")
        selected = next(
            (skip for skip in candidates if not skip.skip_type or skip.skip_type == skip_type),
            None,
        )
        if selected is None:
            raise FlowGraphError(f"节点 {node.node_code} 缺少 {skip_type} 类型的跳转")
        target = self.node(selected.next_node_code)
        if is_start(target.node_type):
            raise FlowGraphError("不允许跳转到开始节点")
        return target

    def expand_gateway(
        self,
        node: FlowNode,
        variables: dict | None = None,
        _visited: set[str] | None = None,
    ) -> list[FlowNode]:
        """Recursively resolve gateways into concrete target nodes."""

        variables = variables or {}
        if not is_gateway(node.node_type):
            if is_start(node.node_type):
                raise FlowGraphError("不允许跳转到开始节点")
            return [node]

        visited = _visited or set()
        if node.node_code in visited:
            return []
        visited.add(node.node_code)

        candidates = list(self.outgoing.get(node.node_code, []))
        if not candidates:
            raise FlowGraphError(f"网关 {node.node_code} 没有出口")

        if node.node_type == NodeType.SERIAL:
            chosen = None
            default = None
            for skip in candidates:
                if skip.skip_condition:
                    if evaluate_condition(skip.skip_condition, variables):
                        chosen = skip
                        break
                else:
                    default = default or skip
            chosen = chosen or default
            candidates = [chosen] if chosen else []
        elif node.node_type == NodeType.INCLUSIVE:
            candidates = [
                skip
                for skip in candidates
                if not skip.skip_condition or evaluate_condition(skip.skip_condition, variables)
            ]

        if not candidates:
            raise FlowGraphError(f"网关 {node.node_code} 没有满足条件的分支")

        result: list[FlowNode] = []
        seen: set[str] = set()
        for skip in candidates:
            target = self.node(skip.next_node_code)
            for resolved in self.expand_gateway(target, variables, visited):
                if resolved.node_code not in seen:
                    seen.add(resolved.node_code)
                    result.append(resolved)
        return result

    def next_nodes(
        self,
        now_node: FlowNode | str,
        any_node_code: str | None = None,
        skip_type: str = SkipType.PASS,
        variables: dict | None = None,
    ) -> list[FlowNode]:
        node = self.node(now_node) if isinstance(now_node, str) else now_node
        target = self.next_node(node, any_node_code, skip_type)
        return self.expand_gateway(target, variables or {})

    def _walk_codes(self, code: str, *, backwards: bool) -> list[str]:
        """Depth-first predecessor/successor codes, gateways skipped later."""

        grouped: dict[str, list[FlowSkip]] = defaultdict(list)
        for skip in self.skips:
            if skip.skip_type and skip.skip_type != SkipType.PASS:
                continue
            key = skip.next_node_code if backwards else skip.now_node_code
            grouped[key].append(skip)

        visited: set[str] = set()
        order: list[str] = []

        def walk(current: str) -> None:
            if current in visited:
                return
            visited.add(current)
            for skip in grouped.get(current, []):
                neighbour = skip.now_node_code if backwards else skip.next_node_code
                if neighbour not in order:
                    order.append(neighbour)
                walk(neighbour)

        walk(code)
        return order

    def previous_nodes(self, code: str) -> list[FlowNode]:
        result = []
        for item in self._walk_codes(code, backwards=True):
            node = self.nodes.get(item)
            if node is not None and not is_gateway(node.node_type):
                result.append(node)
        # Source reverses then de-duplicates then reverses again.
        result.reverse()
        deduped: list[FlowNode] = []
        seen: set[str] = set()
        for node in result:
            if node.node_code not in seen:
                seen.add(node.node_code)
                deduped.append(node)
        deduped.reverse()
        return deduped

    def suffix_nodes(self, code: str) -> list[FlowNode]:
        return [
            node
            for item in self._walk_codes(code, backwards=False)
            if (node := self.nodes.get(item)) is not None and not is_gateway(node.node_type)
        ]


def graph_from_snapshot(snapshot: dict, definition: FlowDefinition) -> FlowGraph:
    """Build a runtime graph from the frozen instance snapshot.

    The snapshot's node/skip ids are preserved because chart edge status is
    keyed by ``skip.id``. Objects are transient (never added to the session);
    they only carry the fields the traversal engine reads.
    """

    nodes: dict[str, FlowNode] = {}
    skips: list[FlowSkip] = []
    for raw in snapshot.get("nodeList") or []:
        code = str(raw.get("nodeCode") or "")
        if not code:
            continue
        ext = raw.get("ext")
        node_type_value = raw.get("nodeType")
        node_type = int(node_type_value) if node_type_value is not None else NodeType.BETWEEN
        nodes[code] = FlowNode(
            id=int(raw.get("id") or 0),
            node_type=node_type,
            definition_id=definition.id,
            node_code=code,
            node_name=raw.get("nodeName"),
            permission_flag=raw.get("permissionFlag"),
            node_ratio=str(raw.get("nodeRatio") or "0"),
            coordinate=raw.get("coordinate"),
            any_node_skip=raw.get("anyNodeSkip"),
            listener_type=raw.get("listenerType"),
            listener_path=raw.get("listenerPath"),
            form_custom=str(raw.get("formCustom") or "N"),
            form_path=raw.get("formPath"),
            version=str(raw.get("version") or definition.version),
            ext=ext if isinstance(ext, str) or ext is None else to_json(ext),
            tenant_id=definition.tenant_id,
        )
        for edge in raw.get("skipList") or []:
            skips.append(
                FlowSkip(
                    id=int(edge.get("id") or 0),
                    definition_id=definition.id,
                    now_node_code=str(edge.get("nowNodeCode") or code),
                    now_node_type=edge.get("nowNodeType"),
                    next_node_code=str(edge.get("nextNodeCode") or ""),
                    next_node_type=edge.get("nextNodeType"),
                    skip_name=edge.get("skipName"),
                    skip_type=str(edge.get("skipType") or SkipType.PASS),
                    skip_condition=edge.get("skipCondition"),
                    coordinate=edge.get("coordinate"),
                    tenant_id=definition.tenant_id,
                )
            )
    return FlowGraph(definition=definition, nodes=nodes, skips=skips)


async def load_graph(session: AsyncSession, definition_id: int) -> FlowGraph:
    definition = await session.get(FlowDefinition, definition_id)
    if definition is None or definition.del_flag != "0":
        raise FlowGraphError("流程定义不存在")
    nodes = (await session.execute(select(FlowNode).where(FlowNode.definition_id == definition_id))).scalars().all()
    skips = (await session.execute(select(FlowSkip).where(FlowSkip.definition_id == definition_id))).scalars().all()
    return FlowGraph(
        definition=definition,
        nodes={node.node_code: node for node in nodes},
        skips=list(skips),
    )


def graph_from_payload(payload: dict) -> tuple[dict[str, dict], list[dict]]:
    """Build lightweight maps from a DefJson payload (save-time validation)."""

    nodes: dict[str, dict] = {}
    skips: list[dict] = []
    for node in payload.get("nodeList") or []:
        code = node.get("nodeCode")
        if not code:
            continue
        nodes[code] = node
        for skip in node.get("skipList") or []:
            skips.append({**skip, "nowNodeCode": skip.get("nowNodeCode") or code})
    return nodes, skips


def iter_targets(skips: Iterable[dict]) -> set[str]:
    return {skip.get("nextNodeCode") for skip in skips if skip.get("nextNodeCode")}
