import type {
  DefJson,
  ModelValue,
  NodeJson,
  NodeTypeName,
  SkipJson,
} from "@/lib/types";
import { NODE_TYPE_BY_NAME, NODE_TYPE_META } from "./nodeRegistry";

export interface LFNodeText {
  x?: number;
  y?: number;
  value?: string;
}

export interface LFNodeData {
  id: string;
  type: NodeTypeName;
  x: number;
  y: number;
  text?: LFNodeText;
  properties: Record<string, unknown>;
}

export interface LFEdgeData {
  id: string;
  type: "skip";
  sourceNodeId: string;
  targetNodeId: string;
  text?: LFNodeText;
  pointsList?: { x: number; y: number }[];
  properties: Record<string, unknown>;
}

export interface LFGraphData {
  nodes: LFNodeData[];
  edges: LFEdgeData[];
}

export interface DefinitionMeta {
  id?: number | null;
  flowCode: string;
  flowName: string;
  modelValue: ModelValue;
  category?: string | null;
  version?: string | null;
  isPublish?: number | null;
  formCustom?: string;
  formPath?: string | null;
  listenerType?: string | null;
  listenerPath?: string | null;
  ext?: string | null;
}

const NAME_BY_TYPE: Record<number, NodeTypeName> = {
  0: "start",
  1: "between",
  2: "end",
  3: "serial",
  4: "parallel",
  5: "inclusive",
};

const GATEWAYS: NodeTypeName[] = ["serial", "parallel", "inclusive"];

const NODE_BOX: Record<NodeTypeName, { halfWidth: number; halfHeight: number }> = {
  start: { halfWidth: 28, halfHeight: 28 },
  end: { halfWidth: 28, halfHeight: 28 },
  between: { halfWidth: 88, halfHeight: 26 },
  serial: { halfWidth: 30, halfHeight: 30 },
  parallel: { halfWidth: 30, halfHeight: 30 },
  inclusive: { halfWidth: 30, halfHeight: 30 },
};

function distanceToNode(point: { x: number; y: number }, node: LFNodeData): number {
  const box = NODE_BOX[node.type] || NODE_BOX.between;
  const dx = Math.max(Math.abs(point.x - node.x) - box.halfWidth, 0);
  const dy = Math.max(Math.abs(point.y - node.y) - box.halfHeight, 0);
  return Math.hypot(dx, dy);
}

/**
 * Legacy seeded definitions all shared one hard-coded edge path. If a stored
 * path does not start/end near its nodes, discard it so LogicFlow computes a
 * fresh route from the real node positions instead of drawing an orphan line.
 */
function edgePointsLookValid(
  points: { x: number; y: number }[],
  source: LFNodeData | undefined,
  target: LFNodeData | undefined,
): boolean {
  if (!source || !target || points.length < 2) return false;
  const tolerance = 64;
  return (
    distanceToNode(points[0], source) <= tolerance &&
    distanceToNode(points[points.length - 1], target) <= tolerance
  );
}

export const NODE_LABEL: Record<NodeTypeName, string> = {
  start: "开始",
  between: "审批节点",
  end: "结束",
  serial: "条件网关",
  parallel: "并行网关",
  inclusive: "包容网关",
};

function int(value: string | undefined, fallback = 0): number {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function parseNodeCoordinate(coordinate?: string | null) {
  if (!coordinate) return { x: 0, y: 0, textX: undefined, textY: undefined };
  const [point, text] = coordinate.split("|");
  const [x, y] = point.split(",");
  let textX: number | undefined;
  let textY: number | undefined;
  if (text) {
    const [tx, ty] = text.split(",");
    textX = int(tx, 0);
    textY = int(ty, 0);
  }
  return { x: int(x, 0), y: int(y, 0), textX, textY };
}

export function parseEdgeCoordinate(coordinate?: string | null) {
  if (!coordinate) return { points: [] as { x: number; y: number }[], textX: undefined, textY: undefined };
  const [pointsPart, textPart] = coordinate.split("|");
  const points = pointsPart
    .split(";")
    .map((item) => {
      const [x, y] = item.split(",");
      return { x: int(x, 0), y: int(y, 0) };
    })
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  let textX: number | undefined;
  let textY: number | undefined;
  if (textPart) {
    const [tx, ty] = textPart.split(",");
    textX = int(tx, 0);
    textY = int(ty, 0);
  }
  return { points, textX, textY };
}

function parseExt(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      const result: Record<string, unknown> = {};
      for (const item of parsed) {
        if (item && typeof item === "object" && "code" in item) {
          const entry = item as { code: string; value?: unknown };
          result[entry.code] = entry.value;
        }
      }
      return result;
    }
    if (parsed && typeof parsed === "object") return parsed as Record<string, unknown>;
    return {};
  } catch {
    return {};
  }
}

function serializeExt(map: Record<string, unknown> | undefined): string | null {
  if (!map) return null;
  const entries = Object.entries(map)
    .filter(([key, value]) => key && value !== undefined && value !== null && value !== "")
    .map(([code, value]) => ({ code, value }));
  return entries.length ? JSON.stringify(entries) : null;
}

export function metaFromDef(def: DefJson): DefinitionMeta {
  return {
    id: def.id ?? null,
    flowCode: def.flowCode,
    flowName: def.flowName,
    modelValue: "CLASSICS",
    category: def.category ?? null,
    version: def.version ?? null,
    isPublish: def.isPublish ?? null,
    formCustom: def.formCustom || "N",
    formPath: def.formPath ?? null,
    listenerType: def.listenerType ?? null,
    listenerPath: def.listenerPath ?? null,
    ext: def.ext ?? null,
  };
}

export function defJsonToGraph(def: DefJson): LFGraphData {
  const nodes: LFNodeData[] = [];
  const edges: LFEdgeData[] = [];
  const nodeTypes = new Map<string, NodeTypeName>();
  const nodeByCode = new Map<string, LFNodeData>();

  for (const node of def.nodeList || []) {
    const type = NAME_BY_TYPE[node.nodeType] || "between";
    nodeTypes.set(node.nodeCode, type);
    const coord = parseNodeCoordinate(node.coordinate);
    const text: LFNodeText = {
      value: node.nodeName || NODE_LABEL[type],
      // Labels always stay inside the node shape. Legacy textX/textY offsets
      // from the removed DingTalk-style layout are ignored.
      x: coord.x,
      y: coord.y,
    };
    const lfNode: LFNodeData = {
      id: node.nodeCode,
      type,
      x: coord.x,
      y: coord.y,
      text,
      properties: {
        nodeType: node.nodeType,
        nodeRatio: node.nodeRatio || "0",
        permissionFlag: node.permissionFlag || "",
        anyNodeSkip: node.anyNodeSkip || "",
        listenerType: node.listenerType || "",
        listenerPath: node.listenerPath || "",
        formCustom: node.formCustom || "N",
        formPath: node.formPath || "",
        status: node.status ?? null,
        extMap: parseExt(node.ext),
        designer: true,
      },
    };
    nodes.push(lfNode);
    nodeByCode.set(node.nodeCode, lfNode);
  }

  let fallbackId = 0;
  for (const node of def.nodeList || []) {
    for (const skip of node.skipList || []) {
      if (!skip.nextNodeCode || !nodeTypes.has(skip.nextNodeCode)) continue;
      const sourceNode = nodeByCode.get(node.nodeCode);
      const targetNode = nodeByCode.get(skip.nextNodeCode);
      const coord = parseEdgeCoordinate(skip.coordinate);
      const pathIsUsable = edgePointsLookValid(coord.points, sourceNode, targetNode);
      const text: LFNodeText = { value: skip.skipName || "通过" };
      if (pathIsUsable && coord.textX !== undefined && coord.textY !== undefined) {
        text.x = coord.textX;
        text.y = coord.textY;
      }
      const edge: LFEdgeData = {
        id: String(skip.id ?? `edge_${node.nodeCode}_${skip.nextNodeCode}_${fallbackId++}`),
        type: "skip",
        sourceNodeId: node.nodeCode,
        targetNodeId: skip.nextNodeCode,
        text,
        properties: {
          skipType: skip.skipType || "PASS",
          skipName: skip.skipName || "通过",
          skipCondition: skip.skipCondition || "",
          expr: skip.expr || skip.skipCondition || "",
          status: skip.status ?? null,
          originalId: skip.id ?? null,
          designer: true,
        },
      };
      if (pathIsUsable) edge.pointsList = coord.points;
      edges.push(edge);
    }
  }

  return { nodes, edges };
}

function textOf(node: { text?: LFNodeText | string }): LFNodeText {
  if (!node.text) return {};
  if (typeof node.text === "string") return { value: node.text };
  return node.text;
}

export function graphToDefJson(
  graph: LFGraphData,
  meta: DefinitionMeta,
): DefJson {
  const nodeTypeByCode = new Map<string, number>();
  for (const node of graph.nodes) {
    nodeTypeByCode.set(node.id, NODE_TYPE_BY_NAME[node.type] ?? 1);
  }

  const nodeList: NodeJson[] = graph.nodes.map((node) => {
    const text = textOf(node);
    let coordinate = `${Math.round(node.x)},${Math.round(node.y)}`;
    if (text.x !== undefined && text.y !== undefined) {
      coordinate += `|${Math.round(text.x)},${Math.round(text.y)}`;
    }
    const properties = node.properties || {};
    return {
      nodeType: NODE_TYPE_BY_NAME[node.type] ?? 1,
      nodeCode: node.id,
      nodeName: text.value || NODE_LABEL[node.type],
      nodeRatio: String(properties.nodeRatio ?? "0") || "0",
      permissionFlag: (properties.permissionFlag as string) || null,
      coordinate,
      anyNodeSkip: (properties.anyNodeSkip as string) || null,
      listenerType: (properties.listenerType as string) || null,
      listenerPath: (properties.listenerPath as string) || null,
      formCustom: (properties.formCustom as string) || "N",
      formPath: (properties.formPath as string) || null,
      ext: serializeExt(properties.extMap as Record<string, unknown> | undefined),
      version: meta.version || null,
      skipList: [],
    };
  });

  const byCode = new Map(nodeList.map((node) => [node.nodeCode, node]));

  for (const edge of graph.edges) {
    const source = byCode.get(edge.sourceNodeId);
    if (!source) continue;
    if (!byCode.has(edge.targetNodeId)) continue;
    const text = textOf(edge);
    let coordinate = "";
    if (edge.pointsList?.length) {
      coordinate = edge.pointsList
        .map((point) => `${Math.round(point.x)},${Math.round(point.y)}`)
        .join(";");
      if (text.x !== undefined && text.y !== undefined) {
        coordinate += `|${Math.round(text.x)},${Math.round(text.y)}`;
      }
    }
    const properties = edge.properties || {};
    const skip: SkipJson = {
      skipType: (properties.skipType as string) || "PASS",
      skipCondition: (properties.skipCondition as string) || null,
      skipName: text.value || (properties.skipName as string) || "通过",
      nowNodeCode: edge.sourceNodeId,
      nowNodeType: nodeTypeByCode.get(edge.sourceNodeId),
      nextNodeCode: edge.targetNodeId,
      nextNodeType: nodeTypeByCode.get(edge.targetNodeId),
      coordinate: coordinate || null,
    };
    source.skipList.push(skip);
  }

  return {
    id: meta.id ?? null,
    flowCode: meta.flowCode,
    flowName: meta.flowName,
    modelValue: meta.modelValue,
    category: meta.category ?? null,
    version: meta.version ?? null,
    isPublish: meta.isPublish ?? null,
    formCustom: meta.formCustom || "N",
    formPath: meta.formPath ?? null,
    listenerType: meta.listenerType ?? null,
    listenerPath: meta.listenerPath ?? null,
    ext: meta.ext ?? null,
    chartStatusColor: [],
    nodeList,
  };
}

export function nextNodeCode(type: NodeTypeName, existing: Iterable<string>): string {
  const used = new Set(existing);
  const base =
    type === "start"
      ? "start"
      : type === "end"
        ? "end"
        : type === "between"
          ? "approval"
          : type;
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}_${index}`)) index += 1;
  return `${base}_${index}`;
}

export function makeNode(
  type: NodeTypeName,
  x: number,
  y: number,
  existing: Iterable<string>,
): LFNodeData {
  const id = nextNodeCode(type, existing);
  return {
    id,
    type,
    x,
    y,
    text: { value: NODE_LABEL[type], x, y },
    properties: {
      nodeRatio: "0",
      permissionFlag: "",
      anyNodeSkip: "",
      listenerType: "",
      listenerPath: "",
      formCustom: "N",
      formPath: "",
      extMap: {},
      status: null,
      designer: true,
    },
  };
}

export function seedGraph(): LFGraphData {
  const start = makeNode("start", 420, 120, []);
  start.text = { value: "开始", x: 420, y: 120 };
  const approval = makeNode("between", 420, 250, [start.id]);
  approval.text = { value: "部门审批", x: 420, y: 250 };
  const end = makeNode("end", 420, 390, [start.id, approval.id]);
  end.text = { value: "结束", x: 420, y: 390 };
  return {
    nodes: [start, approval, end],
    edges: [
      {
        id: `edge_${start.id}_${approval.id}`,
        type: "skip",
        sourceNodeId: start.id,
        targetNodeId: approval.id,
        text: { value: "提交", x: 420, y: 207 },
        properties: { skipType: "PASS", skipName: "提交", skipCondition: "", designer: true },
      },
      {
        id: `edge_${approval.id}_${end.id}`,
        type: "skip",
        sourceNodeId: approval.id,
        targetNodeId: end.id,
        text: { value: "通过", x: 420, y: 337 },
        properties: { skipType: "PASS", skipName: "通过", skipCondition: "", designer: true },
      },
    ],
  };
}

export function isGateway(type: NodeTypeName): boolean {
  return GATEWAYS.includes(type);
}

export function nodeTypeLabel(type: NodeTypeName): string {
  return NODE_TYPE_META[type]?.label || type;
}
