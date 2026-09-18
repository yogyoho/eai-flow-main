/* 复制自 frontend/src/extensions/ontology/stats.ts（S2 Task 1）——字节级零改动（import 仅 graphology 系）。 */
/**
 * 语义地图概览统计纯函数 (EAI-CUSTOM, plan semantic-map v2 Task 3 Step 3.1).
 *
 * 输入一律为纯数组（GraphNode/GraphEdge 投影，见 ../graphSnapshot.ts），不接
 * graphStore 实例——store 图是 directed multi，Louvain 需无向单图，投影在本
 * 模块内部构造后即弃。所有函数对空输入返回空结果，绝不抛（Louvain 包 try/catch）。
 */
import Graph from "graphology";
import louvain from "graphology-communities-louvain";

export interface TypeDistEntry {
  name: string;
  count: number;
}

export interface DegreeTopEntry {
  label: string;
  degree: number;
}

export interface CommunitySizeEntry {
  community: number;
  size: number;
  labels: string[];
}

/** 按 type 计数，降序（同数按名称升序保证稳定）。空 type 归入"（未分类）"。 */
export function typeDistribution(nodes: { type: string }[]): TypeDistEntry[] {
  const counts = new Map<string, number>();
  for (const node of nodes) {
    const key = node.type || "（未分类）";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(
      (left, right) =>
        right.count - left.count || left.name.localeCompare(right.name),
    );
}

/**
 * 度数 Top N（默认 10）降序；度 = 无向端点计数（同对多类型边各计一次端点）。
 * 度为 0 的孤点不进榜（Hub 榜单语义）；同度按 label 升序稳定排序。
 */
export function degreeTop(
  nodes: { id: string; label: string }[],
  edges: { source: string; target: string }[],
  n = 10,
): DegreeTopEntry[] {
  const degree = new Map<string, number>();
  for (const node of nodes) {
    degree.set(node.id, 0);
  }
  for (const edge of edges) {
    if (edge.source === edge.target) continue; // store 图本就禁自环，防御性跳过
    if (degree.has(edge.source)) {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    }
    if (degree.has(edge.target)) {
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    }
  }
  const labelById = new Map(
    nodes.map((node) => [node.id, node.label || node.id]),
  );
  return [...degree.entries()]
    .filter(([, value]) => value > 0)
    .map(([id, value]) => ({ label: labelById.get(id) ?? id, degree: value }))
    .sort(
      (left, right) =>
        right.degree - left.degree || left.label.localeCompare(right.label),
    )
    .slice(0, Math.max(0, Math.floor(n)));
}

/**
 * 固定种子 RNG（mulberry32，8 行内联免加依赖）：louvain 默认 randomWalk 走
 * Math.random，同一图两次运行可能得到不同分区与不同社区编号——canvas 图例与
 * 概览图各自独立跑 communityAssignments，图例 "#3 · 120" 与概览 "#3" 会描述
 * 不同节点组。固定种子 → 同图同分区同编号（跨视图/跨开关一致）。
 */
const LOUVAIN_SEED = 0x5eed;

function mulberry32(seed: number): () => number {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Louvain 社区分配：nodeId → community id。空图/异常 → 空 Map，绝不抛。
 * 构造 undirected 单图投影（节点全量先 addNode 保孤点入社；mergeEdge 对同对
 * 多边去重——addEdge 在非 multi 图上遇重复对会抛）；悬空边（端点不在节点集）
 * 跳过。rng 固定种子保证确定性（见 mulberry32 注）。
 */
export function communityAssignments(
  nodes: { id: string }[],
  edges: { source: string; target: string }[],
): Map<string, number> {
  const result = new Map<string, number>();
  if (nodes.length === 0) {
    return result;
  }
  try {
    const projection = new Graph({ type: "undirected", allowSelfLoops: false });
    for (const node of nodes) {
      projection.addNode(node.id);
    }
    for (const edge of edges) {
      if (edge.source === edge.target) continue;
      if (projection.hasNode(edge.source) && projection.hasNode(edge.target)) {
        projection.mergeEdge(edge.source, edge.target);
      }
    }
    const mapping = louvain(projection, { rng: mulberry32(LOUVAIN_SEED) });
    projection.forEachNode((nodeId) => {
      const community = mapping[nodeId];
      if (community !== undefined) {
        result.set(nodeId, Number(community));
      }
    });
  } catch {
    // Louvain 对退化输入可能抛（空边集/单点等），统计场景静默降级为无社区
    return new Map();
  }
  return result;
}

/** Louvain 社区规模分组（规模降序，同规模按社区 id 升序），labels = 社区成员实体名。 */
export function communitySizes(
  nodes: { id: string; label: string }[],
  edges: { source: string; target: string }[],
): CommunitySizeEntry[] {
  const assignments = communityAssignments(nodes, edges);
  if (assignments.size === 0) {
    return [];
  }
  const labelById = new Map(
    nodes.map((node) => [node.id, node.label || node.id]),
  );
  const grouped = new Map<number, { size: number; labels: string[] }>();
  assignments.forEach((community, nodeId) => {
    const entry = grouped.get(community) ?? { size: 0, labels: [] };
    entry.size += 1;
    entry.labels.push(labelById.get(nodeId) ?? nodeId);
    grouped.set(community, entry);
  });
  return [...grouped.entries()]
    .map(([community, entry]) => ({
      community,
      size: entry.size,
      labels: entry.labels,
    }))
    .sort(
      (left, right) =>
        right.size - left.size || left.community - right.community,
    );
}
