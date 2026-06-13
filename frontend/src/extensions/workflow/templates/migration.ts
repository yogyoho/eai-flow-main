/** V1 flat graph → v2 unified graph migration, plus auto-detect.
 *
 * NOTE: This module intentionally handles LEGACY node types (phase, manual_edit,
 * sub_workflow, notify) for migration purposes. These are mapped to the modern
 * 6-type set (subflow, task, review, ai_generate, condition, merge).
 */
import type { WorkflowGraph, DAGNode } from "../types";

/**
 * Convert a legacy v1 flat graph to v2 unified graph.
 * Creates a single default subflow containing all non-phase nodes.
 */
export function migrateLegacyToUnified(legacy: { nodes?: { id: string; type: string; position: { x: number; y: number }; data: Record<string, unknown> }[]; edges?: { id: string; source: string; target: string; label?: string }[] }): WorkflowGraph {
  const nodes = legacy.nodes ?? [];
  const edges = legacy.edges ?? [];
  const phaseIds = new Set(nodes.filter((n) => n.type === "phase").map((n) => n.id));
  const taskNodes = nodes.filter((n) => n.type !== "phase");

  // Map old types → new types
  const typeMap: Record<string, string> = {
    review: "review", condition: "condition",
    ai_generate: "ai_generate", manual_edit: "task",
    merge: "merge", notify: "notify", sub_workflow: "ai_generate",
  };

  // Convert phase nodes to subflow nodes
  const mainNodes: DAGNode[] = [];
  for (const pn of nodes.filter((n) => n.type === "phase")) {
    mainNodes.push({ id: pn.id, type: "subflow", position: pn.position, data: { ...pn.data, label: pn.data?.label as string ?? pn.id } });
  }

  // If no phases, create default subflow
  if (mainNodes.length === 0 && taskNodes.length > 0) {
    mainNodes.push({ id: "subflow-main", type: "subflow", position: { x: 300, y: 200 }, data: { label: "主流程" } });
    phaseIds.add("subflow-main");
  }

  // Assign tasks to subflows
  const taskToSub: Record<string, string> = {};
  for (const tn of taskNodes) {
    let sid = mainNodes[0]?.id ?? "subflow-main";
    for (const e of edges) {
      if (e.target === tn.id && phaseIds.has(e.source)) { sid = e.source; break; }
      if (e.source === tn.id && phaseIds.has(e.target)) { sid = e.target; break; }
    }
    taskToSub[tn.id] = sid;
  }

  // Build sub-graphs
  const subGraphs: Record<string, { nodes: DAGNode[]; edges: WorkflowGraph["mainGraph"]["edges"] }> = {};
  for (const pn of mainNodes) subGraphs[pn.id] = { nodes: [], edges: [] };

  for (const tn of taskNodes) {
    const sid = taskToSub[tn.id] ?? mainNodes[0]!.id;
    const sg = subGraphs[sid]!;
    sg.nodes.push({ id: tn.id, type: typeMap[tn.type] ?? "task", position: tn.position, data: { label: (tn.data?.label as string) ?? tn.type } as DAGNode["data"] });
  }

  // Route edges
  for (const e of edges) {
    const srcSub = phaseIds.has(e.source) ? e.source : taskToSub[e.source];
    const tgtSub = phaseIds.has(e.target) ? e.target : taskToSub[e.target];
    if (!srcSub || !tgtSub) continue;
    if (srcSub === tgtSub) {
      subGraphs[srcSub]!.edges.push({ id: e.id, source: e.source, target: e.target, label: e.label });
    }
  }

  // Count tasks
  for (const mn of mainNodes) mn.data.taskCount = subGraphs[mn.id]?.nodes.length ?? 0;

  return { version: 2, mainGraph: { nodes: mainNodes, edges: [] }, subGraphs };
}

/** Check if a serialized graph is legacy v1 format (has top-level nodes but no mainGraph). */
export function isLegacyGraph(g: Record<string, unknown> | null | undefined): boolean {
  if (!g) return false;
  return Array.isArray(g.nodes) && g.mainGraph === undefined;
}
