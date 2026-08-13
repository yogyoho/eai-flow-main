/**
 * bid-quote API client —— Route B 薄前端直调 data_source REST。
 * base=/api/extensions(authFetch 默认),data-sources 路由前缀 /data-sources。
 */

import { authFetch } from "@/extensions/api/client";

import type { QueryResult } from "./types";

const API_BASE = "/data-sources";
const SOURCE_NAME = "bid-quote";

// ponytail: 模块级缓存 source/dataset id(resolve 一次后复用),刷新时 clearBidQuoteCache 清掉
let sourceIdCache: string | null = null;
const datasetIdCache: Record<string, string> = {};

interface ListItem {
  id: string;
  name?: string;
  label?: string;
}

/** 列出数据源,按 name 匹配拿 id(模块固定 'bid-quote'),结果缓存。 */
export async function resolveSourceId(name = SOURCE_NAME): Promise<string> {
  if (sourceIdCache) return sourceIdCache;
  const resp = await authFetch<{ items: ListItem[] }>(API_BASE);
  const hit = resp.items.find((s) => s.name === name);
  if (!hit) throw new Error(`数据源 "${name}" 未找到`);
  sourceIdCache = hit.id;
  return sourceIdCache;
}

/** 按 label 匹配拿 dataset id(罐装视图),结果缓存。 */
export async function resolveDatasetId(sourceId: string, label: string): Promise<string> {
  if (datasetIdCache[label]) return datasetIdCache[label];
  const resp = await authFetch<{ items: ListItem[] }>(`${API_BASE}/${sourceId}/datasets`);
  const hit = resp.items.find((d) => d.label === label);
  if (!hit) throw new Error(`数据集 "${label}" 未找到`);
  datasetIdCache[label] = hit.id;
  return datasetIdCache[label];
}

/** 跑罐装 dataset 的 default_query(POST,无 body)。 */
export async function queryDataset(sourceId: string, datasetId: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/datasets/${datasetId}/query`, {
    method: "POST",
  });
}

/** 跑下钻参数化只读 SQL(POST body {sql})。 */
export async function querySql(sourceId: string, sql: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

/** 清缓存(刷新按钮用)。 */
export function clearBidQuoteCache() {
  sourceIdCache = null;
  for (const k of Object.keys(datasetIdCache)) delete datasetIdCache[k];
}
