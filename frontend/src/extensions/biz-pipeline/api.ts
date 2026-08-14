/**
 * biz-pipeline API client —— Route B 薄前端直调 data_source REST(零后端增量,复用①端点)。
 * base=/api/extensions(authFetch 默认),data-sources 路由前缀 /data-sources。
 */

import { authFetch } from "@/extensions/api/client";

import type { QueryResult } from "./types";

const API_BASE = "/data-sources";
const SOURCE_NAME = "biz-pipeline";

let sourceIdCache: string | null = null;
const datasetIdCache: Record<string, string> = {};

interface ListItem {
  id: string;
  name?: string;
  label?: string;
}

export async function resolveSourceId(name = SOURCE_NAME): Promise<string> {
  if (sourceIdCache) return sourceIdCache;
  const resp = await authFetch<{ items: ListItem[] }>(API_BASE);
  const hit = resp.items.find((s) => s.name === name);
  if (!hit) throw new Error(`数据源 "${name}" 未找到`);
  sourceIdCache = hit.id;
  return sourceIdCache;
}

export async function resolveDatasetId(sourceId: string, label: string): Promise<string> {
  if (datasetIdCache[label]) return datasetIdCache[label];
  const resp = await authFetch<{ items: ListItem[] }>(`${API_BASE}/${sourceId}/datasets`);
  const hit = resp.items.find((d) => d.label === label);
  if (!hit) throw new Error(`数据集 "${label}" 未找到`);
  datasetIdCache[label] = hit.id;
  return datasetIdCache[label];
}

export async function queryDataset(sourceId: string, datasetId: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/datasets/${datasetId}/query`, { method: "POST" });
}

export async function querySql(sourceId: string, sql: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export function clearBizPipelineCache() {
  sourceIdCache = null;
  for (const k of Object.keys(datasetIdCache)) delete datasetIdCache[k];
}
