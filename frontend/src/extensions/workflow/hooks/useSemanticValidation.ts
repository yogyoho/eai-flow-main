"use client";

import { useCallback } from "react";

import type { WorkflowGraph, DAGValidationResult } from "../types";

/** Semantic validation for v2 two-layer graphs. */
export function useSemanticValidation() {
  const validateV2 = useCallback((graph: WorkflowGraph): DAGValidationResult => {
    const errors: string[] = [];
    const warnings: string[] = [];

    const phaseNodes = graph.mainGraph?.nodes ?? [];
    const phaseEdges = graph.mainGraph?.edges ?? [];
    const subGraphs = graph.subGraphs ?? {};

    // ── 1. Cycle detection (phase level) ──
    const phaseAdj: Record<string, string[]> = {};
    for (const n of phaseNodes) phaseAdj[n.id] = [];
    for (const e of phaseEdges) {
      if (e.source && e.target) {
        phaseAdj[e.source] ??= [];
        phaseAdj[e.source]!.push(e.target);
      }
    }
    const phaseIdSet = new Set(phaseNodes.map((n) => n.id));
    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color: Record<string, number> = {};
    for (const id of phaseIdSet) color[id] = WHITE;

    const hasPhaseCycle = (function detectCycle(): boolean {
      const visit = (id: string): boolean => {
        color[id] = GRAY;
        for (const next of phaseAdj[id] ?? []) {
          if (!phaseIdSet.has(next)) continue;
          if (color[next] === GRAY) return true;
          if (color[next] === WHITE && visit(next)) return true;
        }
        color[id] = BLACK;
        return false;
      };
      for (const id of phaseIdSet) {
        if (color[id] === WHITE && visit(id)) return true;
      }
      return false;
    })();
    if (hasPhaseCycle) errors.push("阶段图存在循环依赖");

    // ── 2. Subflow with no tasks (v2) ──
    for (const n of phaseNodes) {
      if (n.type !== "subflow") continue;
      const tg = subGraphs[n.id];
      if (!tg?.nodes || tg.nodes.length === 0) {
        warnings.push(`阶段 "${String(n.data?.label ?? n.id)}" 没有任务节点`);
      }
    }

    // ── 3. Disconnected phase nodes ──
    const connectedPhases = new Set<string>();
    for (const e of phaseEdges) {
      if (e.source) connectedPhases.add(e.source);
      if (e.target) connectedPhases.add(e.target);
    }
    for (const n of phaseNodes) {
      if (!connectedPhases.has(n.id) && phaseNodes.length > 1) {
        warnings.push(`阶段 "${String(n.data?.label ?? n.id)}" 未连接任何边`);
      }
    }

    // ── 4. Task-level validation ──
    for (const n of phaseNodes) {
      if (n.type !== "subflow") continue;
      const tg = subGraphs[n.id];
      if (!tg) continue;
      const taskNodes = tg.nodes || [];
      const taskEdges = tg.edges || [];
      const taskIdSet = new Set(taskNodes.map((t) => t.id));

      // 4a. Review nodes missing rejected edge
      for (const t of taskNodes) {
        if (t.type !== "review") continue;
        const hasRejectedEdge = taskEdges.some(
          (e) => e.source === t.id && e.label === "rejected",
        );
        const hasRollbackTarget = !!(t.data as Record<string, unknown>)?.rollbackTarget;
        if (!hasRejectedEdge && !hasRollbackTarget) {
          const reviewLabel = String((t.data as { label?: string })?.label ?? t.id);
          const phaseLabel = String(n.data?.label ?? n.id);
          warnings.push(
            `审核节点 "${reviewLabel}" 在阶段 "${phaseLabel}" 中没有驳回边也未指定回退目标`,
          );
        }
      }

      // 4b. Cycle detection (task level)
      const taskAdj: Record<string, string[]> = {};
      for (const t of taskNodes) taskAdj[t.id] = [];
      for (const e of taskEdges) {
        if (e.source && e.target && taskIdSet.has(e.source) && taskIdSet.has(e.target)) {
          taskAdj[e.source] ??= [];
          taskAdj[e.source]!.push(e.target);
        }
      }
      const tColor: Record<string, number> = {};
      for (const id of taskIdSet) tColor[id] = WHITE;
      const hasTaskCycle = (function detectTaskCycle(): boolean {
        const visit = (id: string): boolean => {
          tColor[id] = GRAY;
          for (const next of taskAdj[id] ?? []) {
            if (!taskIdSet.has(next)) continue;
            if (tColor[next] === GRAY) return true;
            if (tColor[next] === WHITE && visit(next)) return true;
          }
          tColor[id] = BLACK;
          return false;
        };
        for (const id of taskIdSet) {
          if (tColor[id] === WHITE && visit(id)) return true;
        }
        return false;
      })();
      if (hasTaskCycle) {
        errors.push(`阶段 "${n.data?.label || n.id}" 的任务图存在循环依赖`);
      }

      // 4c. Disconnected task nodes
      const connectedTasks = new Set<string>();
      for (const e of taskEdges) {
        if (e.source) connectedTasks.add(e.source);
        if (e.target) connectedTasks.add(e.target);
      }
      for (const t of taskNodes) {
        if (!connectedTasks.has(t.id) && taskNodes.length > 1) {
          const taskLabel = String((t.data as { label?: string })?.label ?? t.id);
          const phaseLabel2 = String(n.data?.label ?? n.id);
          warnings.push(
            `任务节点 "${taskLabel}" 在阶段 "${phaseLabel2}" 中未连接任何边`,
          );
        }
      }
    }

    return { valid: errors.length === 0, errors, warnings };
  }, []);

  return { validateV2 };
}
