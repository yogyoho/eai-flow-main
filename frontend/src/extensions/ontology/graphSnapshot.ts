/**
 * graphStore 单例 → 纯数组快照 (EAI-CUSTOM, plan semantic-map v2 Task 3).
 *
 * 概览统计（stats.ts）与社区着色（OntologyGraphCanvas）共用：把 vendored
 * store 图（directed multi，Explorer 方言属性）投影回 T1 契约的
 * GraphNode/GraphEdge 纯数组。只读投影，不改 store。字段回退链与
 * useLoadGraph 建图字段对齐（nodeType ← T1 type；edge properties.label ← T1 label）。
 */
import type {
  GraphEdge,
  GraphNode,
} from "@/extensions/ontology/api/ontology-graph-api";
import {
  graph,
  type EdgeAttributes,
  type NodeAttributes,
} from "@/extensions/ontology/explorer/graphStore";

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function readGraphSnapshot(): GraphSnapshot {
  const nodes: GraphNode[] = [];
  graph.forEachNode((nodeId, attributes) => {
    const attrs = attributes as NodeAttributes;
    nodes.push({
      id: nodeId,
      type: attrs.nodeType ?? "",
      label: attrs.label ?? "",
      properties: attrs.properties ?? {},
    });
    return true;
  });
  const edges: GraphEdge[] = [];
  graph.forEachEdge((_edgeId, attributes, source, target) => {
    const attrs = attributes as EdgeAttributes;
    edges.push({
      source,
      target,
      type: attrs.edgeType ?? "",
      label: String(attrs.properties?.label ?? ""),
    });
    return true;
  });
  return { nodes, edges };
}
