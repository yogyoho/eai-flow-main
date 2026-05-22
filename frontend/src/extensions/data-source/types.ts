export type DataSourceType = "database" | "api" | "file" | "gis";
export type AuthType = "none" | "basic" | "oauth" | "api_key" | "certificate";
export type SyncMode = "manual" | "scheduled" | "event";
export type ConnectionStatus = "connected" | "error" | "disconnected" | "testing";

export interface DataSource {
  id: string;
  name: string;
  type: DataSourceType;
  connectionConfig: Record<string, unknown>;
  authType: AuthType;
  syncMode: SyncMode;
  syncConfig: Record<string, unknown> | null;
  status: ConnectionStatus;
  lastSyncAt: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateDataSourceRequest {
  name: string;
  type: DataSourceType;
  connectionConfig: Record<string, unknown>;
  authType: AuthType;
  syncMode: SyncMode;
  syncConfig?: Record<string, unknown>;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  metadata?: Record<string, unknown>;
}

export const DATA_SOURCE_TYPE_LABELS: Record<DataSourceType, string> = {
  database: "数据库",
  api: "API接口",
  file: "文件",
  gis: "GIS数据",
};

export const CONNECTION_STATUS_LABELS: Record<ConnectionStatus, string> = {
  connected: "已连接",
  error: "连接错误",
  disconnected: "未连接",
  testing: "测试中",
};

export const AUTH_TYPE_LABELS: Record<AuthType, string> = {
  none: "无认证",
  basic: "基本认证",
  oauth: "OAuth",
  api_key: "API密钥",
  certificate: "证书",
};

export const SYNC_MODE_LABELS: Record<SyncMode, string> = {
  manual: "手动",
  scheduled: "定时",
  event: "事件驱动",
};