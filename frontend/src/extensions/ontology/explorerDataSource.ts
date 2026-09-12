/**
 * Explorer 取数接缝实现 (EAI-CUSTOM, quality-review Fix 1, plan 2026-09-12 ontology-ui).
 *
 * 把本系统 /graph/* 端点（T1 契约 {id,type,label,properties} / {source,target,type,label}）
 * 映射为 Explorer 的 ApiNode/ApiEdge（explorer/types.ts:275-294），并包装成
 * useLoadGraph 的注入式接缝签名（UseLoadGraphOptions.fetchNodes/fetchEdges，
 * explorer/useLoadGraph.ts 的 ExplorerFetchNodes/ExplorerFetchEdges）。
 *
 * 映射决策：
 * - ApiNode.content ← T1 label（Explorer 以 content 做节点标签与实体形状分类）。
 * - ApiEdge.id ← `${source}->${target}#${type}`——确定性 id，跨页 dedup 安全；
 *   同一对节点的不同链接类型经 type 后缀保持相异；同类型同对边按 Explorer 语义视为同边合并。
 * - ApiEdge.familyId ← type（family 计数按链接类型聚合）。
 * - ApiEdge.weight ← 1（T1 无权重；log1p(1) 走 Explorer 默认视觉基线）。
 * - ApiEdge.properties ← { label }（保留 display_name 供详情展示）。
 * - ApiNode.valid_from/valid_until 不设（本系统无时间界 → Explorer 时间徽章恒灭）。
 */
import {
  fetchEdges as fetchEdgesPage,
  fetchNodes as fetchNodesPage,
} from "./api/ontology-graph-api";
import type { GraphEdge, GraphNode } from "./api/ontology-graph-api";
import { createGraphLoadProgress } from "./explorer/graphLoading";
import type { ApiEdge, ApiNode, GraphLoadProgress } from "./explorer/types";
// type-only：接缝类型定义在 vendored useLoadGraph（仅取类型，不拉运行时模块图）
import type {
  ExplorerFetchEdges,
  ExplorerFetchNodes,
} from "./explorer/useLoadGraph";

export function toExplorerNode(node: GraphNode): ApiNode {
  return {
    id: node.id,
    type: node.type,
    content: node.label,
    properties: node.properties,
  };
}

export function toExplorerEdge(edge: GraphEdge): ApiEdge {
  return {
    id: `${edge.source}->${edge.target}#${edge.type}`,
    familyId: edge.type,
    source: edge.source,
    target: edge.target,
    type: edge.type,
    weight: 1,
    properties: { label: edge.label },
  };
}

function yieldToMain(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

export function makeExplorerFetchers(): {
  fetchNodes: ExplorerFetchNodes;
  fetchEdges: ExplorerFetchEdges;
} {
  const fetchNodes: ExplorerFetchNodes = async (signal, onProgress) => {
    let cursor: string | null = null;
    const collected: ApiNode[] = [];

    while (true) {
      const page = await fetchNodesPage(cursor, { signal });
      if (!page.nodes.length) {
        break;
      }
      collected.push(...page.nodes.map(toExplorerNode));
      onProgress?.(progressNodes(collected.length));
      if (!page.next_cursor) {
        break;
      }
      cursor = page.next_cursor;
      await yieldToMain();
    }

    return collected;
  };

  const fetchEdges: ExplorerFetchEdges = async (
    signal,
    nodeIds,
    nodeProgress,
    onProgress,
  ) => {
    let cursor: string | null = null;
    const collected: ApiEdge[] = [];
    const seenEdgeIds = new Set<string>();

    while (true) {
      const page = await fetchEdgesPage(cursor, { signal });
      if (!page.edges.length) {
        break;
      }
      for (const edge of page.edges) {
        const mapped = toExplorerEdge(edge);
        if (!nodeIds.has(mapped.source) || !nodeIds.has(mapped.target)) {
          continue;
        }
        if (seenEdgeIds.has(mapped.id)) {
          continue;
        }
        seenEdgeIds.add(mapped.id);
        collected.push(mapped);
      }
      onProgress?.(progressEdges(seenEdgeIds.size, nodeProgress));
      if (!page.next_cursor) {
        break;
      }
      cursor = page.next_cursor;
      await yieldToMain();
    }

    return collected;
  };

  return { fetchNodes, fetchEdges };
}

function progressNodes(loaded: number): GraphLoadProgress {
  return createGraphLoadProgress({
    phase: "fetching_nodes",
    progressKind: "indeterminate",
    loaded,
    total: null,
    nodesLoaded: loaded,
    nodesTotal: null,
    edgesLoaded: 0,
    edgesTotal: null,
    message: `Loading nodes ${loaded.toLocaleString()}`,
  });
}

function progressEdges(
  loaded: number,
  nodeProgress: { loaded: number; total: number | null },
): GraphLoadProgress {
  return createGraphLoadProgress({
    phase: "fetching_edges",
    progressKind: "indeterminate",
    loaded,
    total: null,
    nodesLoaded: nodeProgress.loaded,
    nodesTotal: nodeProgress.total,
    edgesLoaded: loaded,
    edgesTotal: null,
    message: `Loading edges ${loaded.toLocaleString()}`,
  });
}
