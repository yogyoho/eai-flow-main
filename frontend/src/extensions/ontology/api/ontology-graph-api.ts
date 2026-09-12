/**
 * Ontology 语义地图数据适配层 (EAI-CUSTOM, plan 2026-09-12 Task 2 Step 2.4).
 *
 * 把 Semantica Explorer 的 /api/graph/nodes|edges 数据契约映射到本系统
 * /api/extensions/ontology/graph/* 端点（T1 已交付，见 backend/app/extensions/ontology/graph_views.py）。
 * 游标为后端 base64 串，本层不透明透传。
 *
 * 注意：authFetch 默认 base = "/api/extensions"（见 @/extensions/api/client），
 * 因此这里传扩展内相对路径 "/ontology/..." —— 对齐 bid-quote 等既有扩展 API 的用法，
 * 若写成全路径会产生 /api/extensions/api/extensions/ 双前缀。
 */
import { authFetch } from "@/extensions/api/client";

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
  return cursor ? `${url}&cursor=${encodeURIComponent(cursor)}` : url;
}

/** 分页拉取全部 enabled 对象类型实例的统一节点投影。 */
export async function fetchNodes(cursor?: string | null): Promise<NodesPage> {
  const url = withCursor(`${BASE}/graph/nodes?limit=${NODES_LIMIT}`, cursor);
  const res = await authFetch<Partial<NodesPage>>(url);
  return { nodes: res.nodes ?? [], next_cursor: res.next_cursor ?? null };
}

/** 分页拉取全部 enabled 链接实例的统一边投影（stub 链接不产生边）。 */
export async function fetchEdges(cursor?: string | null): Promise<EdgesPage> {
  const url = withCursor(`${BASE}/graph/edges?limit=${EDGES_LIMIT}`, cursor);
  const res = await authFetch<Partial<EdgesPage>>(url);
  return { edges: res.edges ?? [], next_cursor: res.next_cursor ?? null };
}

/** 注册表元信息（版本指纹 + 类型计数）——页面顶栏 chip 用。 */
export async function fetchRegistryMeta(): Promise<RegistryMeta> {
  return authFetch<RegistryMeta>(`${BASE}/registry`);
}

/** 对象/链接类型清单（含 stub 链接的 enabled:false + note）——Registry 面板用。 */
export async function fetchObjectTypes(): Promise<RegistrySchema> {
  return authFetch<RegistrySchema>(`${BASE}/object-types`);
}
