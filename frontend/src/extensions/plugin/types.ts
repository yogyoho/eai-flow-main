export type PluginType = "data_connector" | "tool" | "output" | "custom";
export type PluginStatus = "registered" | "installed" | "enabled" | "disabled";
export type InstanceStatus = "active" | "error" | "disabled";

export interface Plugin {
  id: string;
  name: string;
  type: PluginType;
  version: string;
  author: string;
  description: string;
  configSchema: Record<string, unknown> | null;
  icon: string | null;
  permissions: string[];
  status: PluginStatus;
  createdAt: string;
}

export interface PluginInstance {
  id: string;
  pluginId: string;
  pluginName: string;
  pluginType: PluginType;
  projectId: string | null;
  config: Record<string, unknown>;
  status: InstanceStatus;
  lastSyncAt: string | null;
  createdAt: string;
}

export interface ApiKey {
  id: string;
  name: string;
  keyPrefix: string;
  scope: string[];
  projectId: string | null;
  createdBy: string;
  expiresAt: string | null;
  lastUsedAt: string | null;
  createdAt: string;
}

export interface CreateApiKeyRequest {
  name: string;
  scope: string[];
  projectId?: string;
  expiresAt?: string;
}

export const PLUGIN_TYPE_LABELS: Record<PluginType, string> = {
  data_connector: "数据连接器",
  tool: "工具",
  output: "输出插件",
  custom: "自定义",
};

export const PLUGIN_STATUS_LABELS: Record<PluginStatus, string> = {
  registered: "已注册",
  installed: "已安装",
  enabled: "已启用",
  disabled: "已禁用",
};