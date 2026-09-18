/**
 * Ontology 语义地图数据适配层 (EAI-CUSTOM, plan 2026-09-12 Task 2 Step 2.4).
 *
 * 把 Semantica Explorer 的 /api/graph/nodes|edges 数据契约映射到本系统
 * /api/extensions/ontology/graph/* 端点（T1 已交付，见 backend/app/extensions/ontology/graph_views.py）。
 * 游标为后端 base64 串，本层不透明透传。
 *
 * 注意：独立前端 authFetch 默认 base = "/api/ontostudio/api/extensions"（见 @/lib/api，
 * dev proxy rewrite → /api/extensions，S1-T3 nginx 同语义），因此这里仍传扩展内相对路径
 * "/ontology/..."；若写成全路径会产生双前缀。复制自
 * frontend/src/extensions/ontology/api/ontology-graph-api.ts（S2 Task 1），仅 import
 * 路径与本段注释改动，fetcher 签名与 T1 契约不变。
 */
import { authFetch } from "@/lib/api";

const BASE = "/ontology";

/** Explorer 方言节点：id = "<api_name>:<pk>"，label = 首个 searchable 属性值。 */
export interface GraphNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
}

/** Explorer 方言边：source/target 均为节点 id。 */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  label: string;
}

export interface NodesPage {
  nodes: GraphNode[];
  next_cursor: string | null;
}

export interface EdgesPage {
  edges: GraphEdge[];
  next_cursor: string | null;
}

export interface RegistryMeta {
  registry_version: number;
  fingerprint: string;
  object_type_count: number;
  link_type_count: number;
}

export interface ObjectTypeSummary {
  name: string;
  display_name: string;
  description: string;
  pk: string;
  properties: string[];
}

export interface LinkTypeSummary {
  name: string;
  source: string;
  target: string;
  enabled: boolean;
  note?: string;
}

export interface RegistrySchema {
  object_types: ObjectTypeSummary[];
  link_types: LinkTypeSummary[];
}

const NODES_LIMIT = 500;
const EDGES_LIMIT = 1000;

function withCursor(url: string, cursor?: string | null): string {
  if (!cursor) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}cursor=${encodeURIComponent(cursor)}`;
}

/** 分页拉取全部 enabled 对象类型实例的统一节点投影。 */
export async function fetchNodes(
  cursor?: string | null,
  options?: { signal?: AbortSignal },
): Promise<NodesPage> {
  const url = withCursor(`${BASE}/graph/nodes?limit=${NODES_LIMIT}`, cursor);
  const res = await authFetch<Partial<NodesPage>>(url, {
    signal: options?.signal,
  });
  return { nodes: res.nodes ?? [], next_cursor: res.next_cursor ?? null };
}

/** 分页拉取全部 enabled 链接实例的统一边投影（stub 链接不产生边）。 */
export async function fetchEdges(
  cursor?: string | null,
  options?: { signal?: AbortSignal },
): Promise<EdgesPage> {
  const url = withCursor(`${BASE}/graph/edges?limit=${EDGES_LIMIT}`, cursor);
  const res = await authFetch<Partial<EdgesPage>>(url, {
    signal: options?.signal,
  });
  return { edges: res.edges ?? [], next_cursor: res.next_cursor ?? null };
}

/** 注册表元信息（版本指纹 + 类型计数）——页面顶栏 chip 用。 */
export async function fetchRegistryMeta(): Promise<RegistryMeta> {
  return authFetch<RegistryMeta>(`${BASE}/registry`);
}

/** 待复核实体计数拉取上限——后端 service.list_pending_review 的 limit 钳制值（doc_graph/service.py）。 */
export const PENDING_REVIEW_LIMIT = 200;

/**
 * 待复核实体计数（doc-graph 实体消解 REST，GET /api/extensions/doc-graph/resolution/pending）。
 * count 为钳制后行数：达到 PENDING_REVIEW_LIMIT 只说明"≥200"。失败（含无 system:access 403）
 * 由调用方按 query error 处理。
 */
export async function fetchPendingReviewCount(): Promise<number> {
  return (await fetchPending()).count;
}

/** 对象/链接类型清单（含 stub 链接的 enabled:false + note）——Registry 面板用。 */
export async function fetchObjectTypes(): Promise<RegistrySchema> {
  return authFetch<RegistrySchema>(`${BASE}/object-types`);
}

/** get_links 响应：data = 对侧行的 visible 属性投影（含 pk 字段）。 */
export interface ObjectLinksPage {
  data: Record<string, unknown>[];
  link_type: string;
  from: { object_type: string; pk: unknown };
}

/** 单对象沿一个链接类型取对侧行（DetailPanel 关联链接区按需拉取）。 */
export async function fetchObjectLinks(
  apiName: string,
  pk: string,
  linkType: string,
  options?: { signal?: AbortSignal },
): Promise<ObjectLinksPage> {
  return authFetch<ObjectLinksPage>(
    `${BASE}/objects/${encodeURIComponent(apiName)}/${encodeURIComponent(pk)}/links/${encodeURIComponent(linkType)}`,
    { signal: options?.signal },
  );
}

// ── doc-graph 实体消解 REST（EAI-CUSTOM, semantic-map v2 Task 4）──────────
// 后端契约: backend/app/extensions/ontology/doc_graph/routers.py。
// 错误语义（UI 接住，前端不重复校验）: ResourceNotFound→404；重复合并/自合并→409；
// 请求体越界→422。authFetch 抛出的 Error 带 status 字段、message = detail 文案。

/** status=pending_review 实体行（置信度升序，后端排好）。 */
export interface ResolutionEntity {
  id: string;
  domain: string;
  etype: string;
  canonical_name: string;
  confidence: number;
}

/** 同 etype 相近实体建议行（similarity ≥ 阈值，降序 Top-N）。 */
export interface ResolutionSuggestion {
  id: string;
  canonical_name: string;
  etype: string;
  /** 0~1 相似度（后端 round 4 位）。 */
  similarity: number;
  /** auto_merge = 精确同名可直并；review = 需人工判断。 */
  action: "auto_merge" | "review";
}

export interface MergeResult {
  merge_id: string;
  candidate_id: string;
  canonical_id: string;
}

export interface UnmergeResult {
  restored_candidate_id: string;
}

export interface PendingPage {
  entities: ResolutionEntity[];
  count: number;
}

export interface SuggestionsResult {
  entity: { id: string; canonical_name: string; etype: string };
  suggestions: ResolutionSuggestion[];
}

const RESOLUTION_BASE = "/doc-graph/resolution";

/** 待复核实体列表（置信度升序；count = 钳制后行数，达 PENDING_REVIEW_LIMIT 只说明"≥200"）。 */
export async function fetchPending(
  etype?: string | null,
): Promise<PendingPage> {
  const url = etype
    ? `${RESOLUTION_BASE}/pending?limit=${PENDING_REVIEW_LIMIT}&etype=${encodeURIComponent(etype)}`
    : `${RESOLUTION_BASE}/pending?limit=${PENDING_REVIEW_LIMIT}`;
  const res = await authFetch<Partial<PendingPage>>(url);
  return {
    entities: res.entities ?? [],
    count:
      typeof res.count === "number"
        ? res.count
        : Array.isArray(res.entities)
          ? res.entities.length
          : 0,
  };
}

/** 目标实体 + 同 etype 相近实体合并建议（Top-N，默认 5；目标不存在→404）。 */
export async function fetchSuggestions(
  entityId: string,
  top = 5,
): Promise<SuggestionsResult> {
  return authFetch<SuggestionsResult>(
    `${RESOLUTION_BASE}/suggestions?entity_id=${encodeURIComponent(entityId)}&top=${top}`,
  );
}

/** candidate 并入 canonical（manual 合并 + 留痕，可 unmerge 撤销；重复合并/自合并→409）。 */
export async function mergeEntities(
  candidateId: string,
  canonicalId: string,
  confidence?: number,
): Promise<MergeResult> {
  return authFetch<MergeResult>(`${RESOLUTION_BASE}/merge`, {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      canonical_id: canonicalId,
      method: "manual",
      confidence: confidence ?? 1.0,
    }),
  });
}

/** 撤销一次合并（删留痕行，candidate 还原 active；merge 不存在→404）。 */
export async function unmergeEntities(mergeId: string): Promise<UnmergeResult> {
  return authFetch<UnmergeResult>(`${RESOLUTION_BASE}/unmerge`, {
    method: "POST",
    body: JSON.stringify({ merge_id: mergeId }),
  });
}
