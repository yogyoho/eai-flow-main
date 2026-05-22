import { authFetch } from "@/extensions/api/client";

import type { Plugin, PluginInstance, ApiKey, CreateApiKeyRequest } from "./types";

const API_BASE = "/plugins";

export const pluginApi = {
  listPlugins: async (): Promise<Plugin[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/registry`);
    return data.items.map((item) => ({
      id: item.id as string,
      name: item.name as string,
      type: item.type as Plugin["type"],
      version: item.version as string,
      author: item.author as string,
      description: item.description as string,
      configSchema: (item.config_schema as Record<string, unknown>) ?? null,
      icon: (item.icon as string) ?? null,
      permissions: (item.permissions as string[]) ?? [],
      status: item.status as Plugin["status"],
      createdAt: item.created_at as string,
    }));
  },

  listInstances: async (projectId?: string): Promise<PluginInstance[]> => {
    const query = projectId ? `?project_id=${projectId}` : "";
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/instances${query}`);
    return data.items.map((item) => ({
      id: item.id as string,
      pluginId: item.plugin_id as string,
      pluginName: item.plugin_name as string,
      pluginType: item.plugin_type as PluginInstance["pluginType"],
      projectId: (item.project_id as string) ?? null,
      config: (item.config as Record<string, unknown>) ?? {},
      status: item.status as PluginInstance["status"],
      lastSyncAt: (item.last_sync_at as string) ?? null,
      createdAt: item.created_at as string,
    }));
  },

  installPlugin: async (pluginId: string, projectId?: string, config?: Record<string, unknown>): Promise<PluginInstance> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/instances`, {
      method: "POST",
      body: JSON.stringify({ plugin_id: pluginId, project_id: projectId, config }),
    });
    return {
      id: data.id as string,
      pluginId: data.plugin_id as string,
      pluginName: data.plugin_name as string,
      pluginType: data.plugin_type as PluginInstance["pluginType"],
      projectId: (data.project_id as string) ?? null,
      config: (data.config as Record<string, unknown>) ?? {},
      status: data.status as PluginInstance["status"],
      lastSyncAt: (data.last_sync_at as string) ?? null,
      createdAt: data.created_at as string,
    };
  },

  updateInstance: async (instanceId: string, config: Record<string, unknown>): Promise<PluginInstance> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/instances/${instanceId}`, {
      method: "PATCH",
      body: JSON.stringify({ config }),
    });
    return {
      id: data.id as string,
      pluginId: data.plugin_id as string,
      pluginName: data.plugin_name as string,
      pluginType: data.plugin_type as PluginInstance["pluginType"],
      projectId: (data.project_id as string) ?? null,
      config: (data.config as Record<string, unknown>) ?? {},
      status: data.status as PluginInstance["status"],
      lastSyncAt: (data.last_sync_at as string) ?? null,
      createdAt: data.created_at as string,
    };
  },

  toggleInstance: async (instanceId: string, enabled: boolean): Promise<void> => {
    await authFetch(`${API_BASE}/instances/${instanceId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: enabled ? "active" : "disabled" }),
    });
  },

  listApiKeys: async (): Promise<ApiKey[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/api-keys`);
    return data.items.map((item) => ({
      id: item.id as string,
      name: item.name as string,
      keyPrefix: item.key_prefix as string,
      scope: (item.scope as string[]) ?? [],
      projectId: (item.project_id as string) ?? null,
      createdBy: item.created_by as string,
      expiresAt: (item.expires_at as string) ?? null,
      lastUsedAt: (item.last_used_at as string) ?? null,
      createdAt: item.created_at as string,
    }));
  },

  createApiKey: async (req: CreateApiKeyRequest): Promise<{ id: string; key: string }> => {
    return authFetch(`${API_BASE}/api-keys`, {
      method: "POST",
      body: JSON.stringify({
        name: req.name,
        scope: req.scope,
        project_id: req.projectId,
        expires_at: req.expiresAt,
      }),
    });
  },

  revokeApiKey: async (id: string): Promise<void> => {
    await authFetch(`${API_BASE}/api-keys/${id}`, { method: "DELETE" });
  },
};