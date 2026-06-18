import { authFetch } from "@/extensions/api/client";

import type {
  CreateDataSourceRequest,
  DataSource,
  DataSourceDataset,
  DatasetCreateRequest,
  TestConnectionResult,
} from "./types";

const API_BASE = "/data-sources";

function transformDataSource(data: Record<string, unknown>): DataSource {
  return {
    id: data.id as string,
    name: data.name as string,
    description: (data.description as string) ?? null,
    type: data.type as DataSource["type"],
    connectionConfig: (data.connection_config as Record<string, unknown>) ?? {},
    authType: data.auth_type as DataSource["authType"],
    syncMode: data.sync_mode as DataSource["syncMode"],
    syncConfig: (data.sync_config as Record<string, unknown>) ?? null,
    status: data.status as DataSource["status"],
    lastSyncAt: (data.last_sync_at as string) ?? null,
    createdBy: data.created_by as string,
    createdAt: data.created_at as string,
    updatedAt: data.updated_at as string,
  };
}

export const dataSourceApi = {
  list: async (): Promise<DataSource[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}`);
    return data.items.map(transformDataSource);
  },

  get: async (id: string): Promise<DataSource> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/${id}`);
    return transformDataSource(data);
  },

  create: async (req: CreateDataSourceRequest): Promise<DataSource> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}`, {
      method: "POST",
      body: JSON.stringify({
        name: req.name,
        description: req.description || undefined,
        type: req.type,
        connection_config: req.connectionConfig,
        auth_type: req.authType,
        sync_mode: req.syncMode,
        sync_config: req.syncConfig,
      }),
    });
    return dataSourceApi.get(data.id as string);
  },

  update: async (id: string, req: Partial<CreateDataSourceRequest>): Promise<DataSource> => {
    await authFetch(`${API_BASE}/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: req.name,
        description: req.description || undefined,
        type: req.type,
        connection_config: req.connectionConfig,
        auth_type: req.authType,
        sync_mode: req.syncMode,
        sync_config: req.syncConfig,
      }),
    });
    return dataSourceApi.get(id);
  },

  delete: async (id: string): Promise<void> => {
    await authFetch(`${API_BASE}/${id}`, { method: "DELETE" });
  },

  testConnection: async (id: string): Promise<TestConnectionResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/${id}/test`, {
      method: "POST",
    });
    return {
      success: data.success as boolean,
      message: data.message as string,
      metadata: (data.metadata as Record<string, unknown>) ?? undefined,
    };
  },

  sync: async (id: string): Promise<void> => {
    await authFetch(`${API_BASE}/${id}/sync`, { method: "POST" });
  },
};

function transformDataset(data: Record<string, unknown>): DataSourceDataset {
  return {
    id: data.id as string,
    sourceId: (data.source_id as string) ?? "",
    tableName: (data.table_name as string) ?? "",
    label: (data.label as string) ?? "",
    description: (data.description as string) ?? null,
    keyColumns: (data.key_columns as string[] | null) ?? null,
    defaultQuery: (data.default_query as string) ?? null,
    createdAt: (data.created_at as string) ?? "",
    updatedAt: (data.updated_at as string) ?? "",
  };
}

export const datasetApi = {
  list: async (sourceId: string): Promise<DataSourceDataset[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/${sourceId}/datasets`);
    return data.items.map(transformDataset);
  },

  create: async (sourceId: string, req: DatasetCreateRequest): Promise<DataSourceDataset> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/${sourceId}/datasets`, {
      method: "POST",
      body: JSON.stringify({
        table_name: req.tableName,
        label: req.label,
        description: req.description,
        key_columns: req.keyColumns,
        default_query: req.defaultQuery,
      }),
    });
    return transformDataset(data);
  },

  update: async (datasetId: string, req: Partial<DatasetCreateRequest>): Promise<DataSourceDataset> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/datasets/${datasetId}`, {
      method: "PATCH",
      body: JSON.stringify({
        table_name: req.tableName,
        label: req.label,
        description: req.description,
        key_columns: req.keyColumns,
        default_query: req.defaultQuery,
      }),
    });
    return transformDataset(data);
  },

  delete: async (datasetId: string): Promise<void> => {
    await authFetch(`${API_BASE}/datasets/${datasetId}`, { method: "DELETE" });
  },
};