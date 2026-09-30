/* 复制自 frontend/src/extensions/ontology/explorerDataSource.ts（S2 Task 1）——仅 import 路径改本地，内容零改动。 */
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
 *
 * EAI-CUSTOM(2026-09-30 关系折叠边): fetchEdges 改走 mode=flat 折叠投影——关系行由后端
 * 直接折叠为 实体—谓词—实体 带标签连线，画布上关系是连线不是圆点（旧 default 双轨投影
 * 的悬挂边在关系节点不在窗口时全部不可见）。映射沿用同一 ApiEdge 形状：
 * - ApiEdge.type/familyId ← 谓词值（family 计数即"按谓词聚合"，正是关系类型维度语义）；
 *   同一实体对同谓词的平行关系行按确定性 id 合并为一条（Explorer 既有语义）。
 * - ApiEdge.label 显示谓词值（英文，如 bidder_of_project）。注册表端点不吐谓词值级中文
 *   标注（/registry 仅计数指纹、/object-types 仅属性名清单），按任务口径回退英文谓词名，
 *   不硬编码中文对照表。
 * - relation_pk（关系行 id）透传进 properties，供溯源/详情延伸（DetailPanel 对 relation
 *   的懒加载仍走 /objects 通道，不受折叠影响）。
 */
import {
  fetchEdges as fetchEdgesPage,
  fetchNodes as fetchNodesPage,
} from "./api/ontology-graph-api";
import type { GraphEdge, GraphNode } from "./api/ontology-graph-api";
import { fetchRegistryContent } from "./api/registry-api";
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
    properties: {
      label: edge.label,
      // EAI-CUSTOM(2026-09-30 关系折叠边): flat 边携带关系行 id 供溯源；default 边无此字段
      ...(edge.relation_pk != null ? { relation_pk: edge.relation_pk } : {}),
    },
  };
}

function yieldToMain(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// EAI-CUSTOM(2026-09-30 谓词中文标注): eia.yaml 的 "# 谓词中文标注: xxx=中文" 注释块是
// 唯一真源（与后端 llm_extract.load_enums 同源解析），用户规则=本体英文必有对应中文。
// 边标签优先中文，标注缺失/接口不可达时回退英文谓词值；模块级缓存一次。
let predicateLabelCache: Map<string, string> | null = null;
async function getPredicateLabels(): Promise<Map<string, string>> {
  if (predicateLabelCache) {
    return predicateLabelCache;
  }
  const map = new Map<string, string>();
  try {
    const content = await fetchRegistryContent("eia.yaml");
    for (const m of (content.raw ?? "").matchAll(/# 谓词中文标注: (.+)/g)) {
      const line = m[1];
      if (!line) {
        continue;
      }
      for (const pair of line.trim().split(/\s+/)) {
        const eq = pair.indexOf("=");
        if (eq > 0) {
          map.set(pair.slice(0, eq), pair.slice(eq + 1));
        }
      }
    }
  } catch {
    // 标注不可达：保持空表，回退英文谓词值
  }
  predicateLabelCache = map;
  return map;
}

/** EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain 非空 → /graph/* 带 domain= 服务端过滤；
 *  取数器随域重建（调用方 useMemo 依赖域），切域即换一组 fetchers。 */
export function makeExplorerFetchers(domain = ""): {
  fetchNodes: ExplorerFetchNodes;
  fetchEdges: ExplorerFetchEdges;
} {
  const fetchNodes: ExplorerFetchNodes = async (signal, onProgress) => {
    let cursor: string | null = null;
    const collected: ApiNode[] = [];

    while (true) {
      const page = await fetchNodesPage(cursor, { signal, domain: domain || undefined });
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
    const predicateLabels = await getPredicateLabels();

    while (true) {
      // EAI-CUSTOM(2026-09-30 关系折叠边): mode=flat —— 关系折叠为实体间带谓词标签的连线
      const page = await fetchEdgesPage(cursor, { signal, domain: domain || undefined, mode: "flat" });
      if (!page.edges.length) {
        break;
      }
      for (const edge of page.edges) {
        const mapped = toExplorerEdge(edge);
        // EAI-CUSTOM(2026-09-30): 边标签优先谓词中文（标注真源=eia.yaml 注释块），回退英文谓词值
        const zh = predicateLabels.get(edge.type);
        if (zh) {
          mapped.properties.label = zh;
        }
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
