# AI智能工程报告写作平台 — 前端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 DeerFlow 前端基础上，实现报告项目管理、协作审批、插件平台、数据集成、报告输出五大功能模块的前端页面和组件。

**Architecture:** 遵循现有 `src/extensions/<module>/` 扩展模式，每个模块包含 types.ts、api.ts、主页面组件和 components/ 子目录。路由页面放在 `src/app/<route>/page.tsx`，通过 ShellLayout 包裹。API 使用 authFetch 模式（cookie 认证 + CSRF），后端通信遵循 snake_case ↔ camelCase 转换规范。

**Tech Stack:** Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, Shadcn UI (src/components/ui/), Framer Motion, Lucide Icons, TanStack Query

**Design Spec:** `docs/superpowers/specs/2026-05-21-report-platform-feature-design.md`

---

## Phase 0: 基础设施（共享类型、API 工具、侧边栏导航）

### Task 1: 创建共享类型定义

**Files:**
- Create: `src/extensions/project/types.ts`
- Create: `src/extensions/approval/types.ts`
- Create: `src/extensions/plugin/types.ts`
- Create: `src/extensions/data-source/types.ts`
- Create: `src/extensions/output/types.ts`

- [ ] **Step 1: 创建项目模块类型定义**

```typescript
// src/extensions/project/types.ts

export type ReportType = "environmental_impact" | "geological_survey" | "feasibility_study" | "safety_assessment" | "energy_assessment" | "other";

export type ProjectStatus = "planning" | "writing" | "review" | "finalizing" | "archived";

export type MemberRole = "manager" | "writer" | "reviewer" | "approver" | "issuer";

export type ChapterStatus = "not_started" | "writing" | "pending_review" | "approved" | "signed";

export type MilestoneStatus = "pending" | "in_progress" | "completed" | "overdue";

export interface ReportProject {
  id: string;
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard: string;
  status: ProjectStatus;
  templateId: string | null;
  complianceRuleSetId: string | null;
  lawIds: string[];
  members: ProjectMember[];
  outline: ReportOutline | null;
  milestones: Milestone[];
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMember {
  userId: string;
  username: string;
  role: MemberRole;
  chapterAssignments: string[];
  avatarUrl?: string;
}

export interface ReportOutline {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  order: number;
  status: ChapterStatus;
  assigneeId: string | null;
  assigneeName: string | null;
  wordCountTarget: number;
  wordCountCurrent: number;
  description: string;
  children: ReportOutline[];
}

export interface Milestone {
  id: string;
  projectId: string;
  name: string;
  dueDate: string;
  completedAt: string | null;
  status: MilestoneStatus;
}

export interface CreateProjectRequest {
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard?: string;
  templateId?: string;
  complianceRuleSetId?: string;
  lawIds?: string[];
  members?: { userId: string; role: MemberRole }[];
}

export interface UpdateProjectRequest {
  name?: string;
  client?: string;
  targetStandard?: string;
  status?: ProjectStatus;
  complianceRuleSetId?: string;
  lawIds?: string[];
}

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  environmental_impact: "环境影响评价",
  geological_survey: "地质勘查",
  feasibility_study: "可行性研究",
  safety_assessment: "安全评价",
  energy_assessment: "节能评价",
  other: "其他",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: "规划中",
  writing: "编写中",
  review: "审核中",
  finalizing: "定稿中",
  archived: "已归档",
};

export const CHAPTER_STATUS_LABELS: Record<ChapterStatus, string> = {
  not_started: "未开始",
  writing: "编写中",
  pending_review: "待审核",
  approved: "已通过",
  signed: "已签发",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "项目经理",
  writer: "编写人",
  reviewer: "审核人",
  approver: "批准人",
  issuer: "签发人",
};
```

- [ ] **Step 2: 创建审批模块类型定义**

```typescript
// src/extensions/approval/types.ts

export type ApprovalAction = "approve" | "reject" | "comment";

export type ApprovalStepType = "review" | "technical_review" | "sign_off";

export interface ApprovalWorkflow {
  id: string;
  name: string;
  reportType: string;
  steps: ApprovalStep[];
  isDefault: boolean;
}

export interface ApprovalStep {
  id: string;
  workflowId: string;
  order: number;
  name: string;
  requiredRole: string;
  canReject: boolean;
  parallel: boolean;
}

export interface ApprovalRecord {
  id: string;
  projectId: string;
  stepId: string;
  chapterId: string | null;
  reviewerId: string;
  reviewerName: string;
  action: ApprovalAction;
  comment: string;
  actedAt: string;
}

export interface SubmitApprovalRequest {
  projectId: string;
  chapterIds?: string[];
}

export interface ApprovalActionRequest {
  projectId: string;
  stepId: string;
  chapterId?: string;
  action: ApprovalAction;
  comment?: string;
}
```

- [ ] **Step 3: 创建插件模块类型定义**

```typescript
// src/extensions/plugin/types.ts

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
```

- [ ] **Step 4: 创建数据源模块类型定义**

```typescript
// src/extensions/data-source/types.ts

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
```

- [ ] **Step 5: 创建输出模块类型定义**

```typescript
// src/extensions/output/types.ts

export type OutputFormat = "docx" | "pdf" | "preview";
export type WatermarkType = "draft" | "review" | "final";

export interface LayoutTemplate {
  id: string;
  name: string;
  reportType: string;
  pageSettings: PageSettings;
  coverTemplate: CoverTemplate | null;
  tocSettings: TocSettings | null;
  bodyStyles: BodyStyles;
  headingStyles: HeadingStyle[];
  tableStyles: TableStyles | null;
  figureStyles: FigureStyles | null;
  headerFooter: HeaderFooter | null;
  referenceStyle: string;
  appendixRules: AppendixRules | null;
  createdAt: string;
  updatedAt: string;
}

export interface PageSettings {
  paperSize: "A4" | "A3" | "B5" | "letter";
  orientation: "portrait" | "landscape";
  marginTop: number;
  marginBottom: number;
  marginLeft: number;
  marginRight: number;
}

export interface CoverTemplate {
  showLogo: boolean;
  logoPosition: "left" | "center" | "right";
  showTitle: boolean;
  showClient: boolean;
  showDate: boolean;
  showProjectNumber: boolean;
}

export interface TocSettings {
  maxDepth: number;
  showPageNumbers: boolean;
  leaderDots: boolean;
}

export interface BodyStyles {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  paragraphSpacing: number;
  firstLineIndent: number;
}

export interface HeadingStyle {
  level: number;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  numbering: "decimal" | "chinese" | "none";
}

export interface TableStyles {
  headerBg: string;
  headerColor: string;
  borderColor: string;
  stripeRows: boolean;
}

export interface FigureStyles {
  captionPosition: "above" | "below";
  numbering: "chapter" | "continuous";
  showSource: boolean;
}

export interface HeaderFooter {
  headerText: string;
  footerText: string;
  showPageNumber: boolean;
  showLogo: boolean;
}

export interface AppendixRules {
  numbering: "A-B-C" | "I-II-III" | "1-2-3";
  separateToc: boolean;
}

export interface GenerateOutputRequest {
  projectId: string;
  format: OutputFormat;
  layoutTemplateId: string;
  watermark?: WatermarkType;
  chapterIds?: string[];
}

export interface GenerateOutputResult {
  taskId: string;
  status: "queued" | "processing" | "completed" | "failed";
  downloadUrl?: string;
  fileName?: string;
}

export const WATERMARK_LABELS: Record<WatermarkType, string> = {
  draft: "初稿",
  review: "送审稿",
  final: "正式稿",
};
```

- [ ] **Step 6: 提交类型文件**

```bash
git add src/extensions/project/types.ts src/extensions/approval/types.ts src/extensions/plugin/types.ts src/extensions/data-source/types.ts src/extensions/output/types.ts
git commit -m "feat: add type definitions for report platform modules"
```

---

### Task 2: 创建 API 客户端

**Files:**
- Create: `src/extensions/project/api.ts`
- Create: `src/extensions/approval/api.ts`
- Create: `src/extensions/plugin/api.ts`
- Create: `src/extensions/data-source/api.ts`
- Create: `src/extensions/output/api.ts`

- [ ] **Step 1: 创建项目模块 API**

```typescript
// src/extensions/project/api.ts

import { authFetch } from "@/extensions/api";
import type {
  ReportProject,
  ReportOutline,
  CreateProjectRequest,
  UpdateProjectRequest,
  Milestone,
} from "./types";

const API_BASE = "/api/project";

function toCamelCase<T>(data: Record<string, unknown>): T {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data)) {
    const camelKey = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
    if (value && typeof value === "object" && !Array.isArray(value) && !(value instanceof Date)) {
      result[camelKey] = toCamelCase(value as Record<string, unknown>);
    } else if (Array.isArray(value)) {
      result[camelKey] = value.map((item) =>
        item && typeof item === "object" && !Array.isArray(item)
          ? toCamelCase(item as Record<string, unknown>)
          : item
      );
    } else {
      result[camelKey] = value;
    }
  }
  return result as T;
}

function toSnakeCase(data: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data)) {
    const snakeKey = key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
    if (value === undefined) continue;
    result[snakeKey] = value;
  }
  return result;
}

export const projectApi = {
  list: async (params?: { status?: string; reportType?: string; search?: string }): Promise<ReportProject[]> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.reportType) query.set("report_type", params.reportType);
    if (params?.search) query.set("search", params.search);
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/projects?${query}`);
    return data.items.map((item) => toCamelCase<ReportProject>(item));
  },

  get: async (id: string): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}`);
    return toCamelCase<ReportProject>(data);
  },

  create: async (req: CreateProjectRequest): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects`, {
      method: "POST",
      body: JSON.stringify(toSnakeCase(req as Record<string, unknown>)),
    });
    return toCamelCase<ReportProject>(data);
  },

  update: async (id: string, req: UpdateProjectRequest): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(toSnakeCase(req as Record<string, unknown>)),
    });
    return toCamelCase<ReportProject>(data);
  },

  delete: async (id: string): Promise<void> => {
    await authFetch<void>(`${API_BASE}/projects/${id}`, { method: "DELETE" });
  },

  getOutline: async (projectId: string): Promise<ReportOutline[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/projects/${projectId}/outline`);
    return data.items.map((item) => toCamelCase<ReportOutline>(item));
  },

  updateOutline: async (projectId: string, outlineId: string, updates: Partial<ReportOutline>): Promise<ReportOutline> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${projectId}/outline/${outlineId}`, {
      method: "PATCH",
      body: JSON.stringify(toSnakeCase(updates as Record<string, unknown>)),
    });
    return toCamelCase<ReportOutline>(data);
  },

  addMember: async (projectId: string, userId: string, role: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, role }),
    });
  },

  removeMember: async (projectId: string, userId: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members/${userId}`, { method: "DELETE" });
  },

  getMilestones: async (projectId: string): Promise<Milestone[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/projects/${projectId}/milestones`);
    return data.items.map((item) => toCamelCase<Milestone>(item));
  },
};
```

- [ ] **Step 2: 创建审批模块 API**

```typescript
// src/extensions/approval/api.ts

import { authFetch } from "@/extensions/api";
import type {
  ApprovalWorkflow,
  ApprovalRecord,
  SubmitApprovalRequest,
  ApprovalActionRequest,
} from "./types";

const API_BASE = "/api/approval";

export const approvalApi = {
  getWorkflow: async (reportType: string): Promise<ApprovalWorkflow | null> => {
    try {
      const data = await authFetch<Record<string, unknown>>(`${API_BASE}/workflows/default?report_type=${reportType}`);
      const result: ApprovalWorkflow = {
        id: data.id as string,
        name: data.name as string,
        reportType: data.report_type as string,
        isDefault: data.is_default as boolean,
        steps: (data.steps as Record<string, unknown>[]).map((s) => ({
          id: s.id as string,
          workflowId: s.workflow_id as string,
          order: s.order as number,
          name: s.name as string,
          requiredRole: s.required_role as string,
          canReject: s.can_reject as boolean,
          parallel: s.parallel as boolean,
        })),
      };
      return result;
    } catch {
      return null;
    }
  },

  submitForApproval: async (req: SubmitApprovalRequest): Promise<void> => {
    await authFetch(`${API_BASE}/submissions`, {
      method: "POST",
      body: JSON.stringify({
        project_id: req.projectId,
        chapter_ids: req.chapterIds,
      }),
    });
  },

  act: async (req: ApprovalActionRequest): Promise<ApprovalRecord> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/actions`, {
      method: "POST",
      body: JSON.stringify({
        project_id: req.projectId,
        step_id: req.stepId,
        chapter_id: req.chapterId,
        action: req.action,
        comment: req.comment,
      }),
    });
    return {
      id: data.id as string,
      projectId: data.project_id as string,
      stepId: data.step_id as string,
      chapterId: (data.chapter_id as string) ?? null,
      reviewerId: data.reviewer_id as string,
      reviewerName: data.reviewer_name as string,
      action: data.action as "approve" | "reject" | "comment",
      comment: (data.comment as string) ?? "",
      actedAt: data.acted_at as string,
    };
  },

  getRecords: async (projectId: string): Promise<ApprovalRecord[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/records?project_id=${projectId}`);
    return data.items.map((item) => ({
      id: item.id as string,
      projectId: item.project_id as string,
      stepId: item.step_id as string,
      chapterId: (item.chapter_id as string) ?? null,
      reviewerId: item.reviewer_id as string,
      reviewerName: item.reviewer_name as string,
      action: item.action as "approve" | "reject" | "comment",
      comment: (item.comment as string) ?? "",
      actedAt: item.acted_at as string,
    }));
  },
};
```

- [ ] **Step 3: 创建插件模块 API**

```typescript
// src/extensions/plugin/api.ts

import { authFetch } from "@/extensions/api";
import type { Plugin, PluginInstance, ApiKey, CreateApiKeyRequest, PLUGIN_TYPE_LABELS } from "./types";

const API_BASE = "/api/plugins";

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
```

- [ ] **Step 4: 创建数据源模块 API**

```typescript
// src/extensions/data-source/api.ts

import { authFetch } from "@/extensions/api";
import type { DataSource, CreateDataSourceRequest, TestConnectionResult } from "./types";

const API_BASE = "/api/data-sources";

export const dataSourceApi = {
  list: async (): Promise<DataSource[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}`);
    return data.items.map((item) => ({
      id: item.id as string,
      name: item.name as string,
      type: item.type as DataSource["type"],
      connectionConfig: (item.connection_config as Record<string, unknown>) ?? {},
      authType: item.auth_type as DataSource["authType"],
      syncMode: item.sync_mode as DataSource["syncMode"],
      syncConfig: (item.sync_config as Record<string, unknown>) ?? null,
      status: item.status as DataSource["status"],
      lastSyncAt: (item.last_sync_at as string) ?? null,
      createdBy: item.created_by as string,
      createdAt: item.created_at as string,
      updatedAt: item.updated_at as string,
    }));
  },

  get: async (id: string): Promise<DataSource> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/${id}`);
    return {
      id: data.id as string,
      name: data.name as string,
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
  },

  create: async (req: CreateDataSourceRequest): Promise<DataSource> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}`, {
      method: "POST",
      body: JSON.stringify({
        name: req.name,
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
```

- [ ] **Step 5: 创建输出模块 API**

```typescript
// src/extensions/output/api.ts

import { authFetch } from "@/extensions/api";
import type { LayoutTemplate, GenerateOutputRequest, GenerateOutputResult } from "./types";

const API_BASE = "/api/output";

export const outputApi = {
  listTemplates: async (): Promise<LayoutTemplate[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/templates`);
    return data.items.map((item) => transformTemplate(item));
  },

  getTemplate: async (id: string): Promise<LayoutTemplate> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}`);
    return transformTemplate(data);
  },

  generate: async (req: GenerateOutputRequest): Promise<GenerateOutputResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/generate`, {
      method: "POST",
      body: JSON.stringify({
        project_id: req.projectId,
        format: req.format,
        layout_template_id: req.layoutTemplateId,
        watermark: req.watermark,
        chapter_ids: req.chapterIds,
      }),
    });
    return {
      taskId: data.task_id as string,
      status: data.status as GenerateOutputResult["status"],
      downloadUrl: (data.download_url as string) ?? undefined,
      fileName: (data.file_name as string) ?? undefined,
    };
  },

  getTaskStatus: async (taskId: string): Promise<GenerateOutputResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/tasks/${taskId}`);
    return {
      taskId: data.task_id as string,
      status: data.status as GenerateOutputResult["status"],
      downloadUrl: (data.download_url as string) ?? undefined,
      fileName: (data.file_name as string) ?? undefined,
    };
  },
};

function transformTemplate(data: Record<string, unknown>): LayoutTemplate {
  return {
    id: data.id as string,
    name: data.name as string,
    reportType: data.report_type as string,
    pageSettings: data.page_settings as LayoutTemplate["pageSettings"],
    coverTemplate: (data.cover_template as LayoutTemplate["coverTemplate"]) ?? null,
    tocSettings: (data.toc_settings as LayoutTemplate["tocSettings"]) ?? null,
    bodyStyles: data.body_styles as LayoutTemplate["bodyStyles"],
    headingStyles: (data.heading_styles as LayoutTemplate["headingStyles"]) ?? [],
    tableStyles: (data.table_styles as LayoutTemplate["tableStyles"]) ?? null,
    figureStyles: (data.figure_styles as LayoutTemplate["figureStyles"]) ?? null,
    headerFooter: (data.header_footer as LayoutTemplate["headerFooter"]) ?? null,
    referenceStyle: (data.reference_style as string) ?? "gb7714",
    appendixRules: (data.appendix_rules as LayoutTemplate["appendixRules"]) ?? null,
    createdAt: data.created_at as string,
    updatedAt: data.updated_at as string,
  };
}
```

- [ ] **Step 6: 提交 API 文件**

```bash
git add src/extensions/project/api.ts src/extensions/approval/api.ts src/extensions/plugin/api.ts src/extensions/data-source/api.ts src/extensions/output/api.ts
git commit -m "feat: add API client modules for report platform"
```

---

### Task 3: 更新侧边栏导航

**Files:**
- Modify: `src/extensions/shell/Sidebar.tsx`

- [ ] **Step 1: 添加新的导航项**

在 `Sidebar.tsx` 的 `navItems` 数组中添加报告项目管理入口，在现有导航项之间插入：

```typescript
// 在 navItems 数组中添加（在 knowledge 和 admin 之间）:
{ href: "/projects", label: "报告项目", icon: ClipboardList },

// 在 bottomNavItems 上方添加一个分隔区域（如果需要）
// 或者直接在 navItems 中添加:
{ href: "/data-sources", label: "数据源", icon: Database },
```

同时更新 import 语句，添加 `ClipboardList` 图标：

```typescript
import {
  Bot,
  Factory,
  BookOpen,
  Settings2,
  Settings,
  LogOut,
  UserCircle,
  FolderCheck,
  ClipboardList,
  Database,
} from "lucide-react";
```

更新 active state 匹配逻辑（因为 `/projects` 路由有子路径 `/projects/[id]`）：

```typescript
// 在 NavIcon 的 isActive 计算中：
const isActive =
  pathname === href ||
  (href !== "/" && pathname.startsWith(href));
```

- [ ] **Step 2: 提交侧边栏更新**

```bash
git add src/extensions/shell/Sidebar.tsx
git commit -m "feat: add project and data-source navigation to sidebar"
```

---

## Phase 1: 报告项目管理（P0）

### Task 4: 项目列表页

**Files:**
- Create: `src/extensions/project/ProjectList.tsx`
- Create: `src/extensions/project/components/ProjectCard.tsx`
- Create: `src/extensions/project/components/StatusBadge.tsx`
- Create: `src/app/projects/page.tsx`

- [ ] **Step 1: 创建 StatusBadge 组件**

文件: `src/extensions/project/components/StatusBadge.tsx`

通用状态徽章组件，用于项目状态和章节状态。遵循现有 `getStatusBadge` 模式（参考 `knowledge/page.tsx`），使用 `success/primary/destructive/muted` 语义色。

- [ ] **Step 2: 创建 ProjectCard 组件**

文件: `src/extensions/project/components/ProjectCard.tsx`

项目卡片组件。遵循现有卡片模式（`rounded-xl border border-border bg-background shadow-sm`）。显示：
- 报告类型图标 + 名称 + 状态徽章
- 委托方、报告类型、创建时间
- 底部：成员头像组 + 操作按钮（编辑/删除）
- 点击卡片导航到项目详情页

使用 `motion.div` 包裹实现 AnimatePresence 动画（参照 knowledge page 卡片模式）。

- [ ] **Step 3: 创建 ProjectList 主组件**

文件: `src/extensions/project/ProjectList.tsx`

遵循 `KnowledgeBaseManagement` 页面模式（`src/app/knowledge/page.tsx`）:
- 页面标题 "报告项目" + "新建项目" 按钮
- 搜索栏 + 状态筛选 + 报告类型筛选
- 项目卡片网格 (`grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3`)
- 空状态提示
- 使用 `useState` + `useEffect` 加载数据
- 自定义 Toast 系统（复用现有 useToast 模式）

- [ ] **Step 4: 创建路由页面**

文件: `src/app/projects/page.tsx`

```typescript
"use client";

import { Suspense } from "react";
import { ShellLayout } from "@/extensions/shell";
import { ProjectList } from "@/extensions/project/ProjectList";

export default function ProjectsPage() {
  return (
    <ShellLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div>}>
        <ProjectList />
      </Suspense>
    </ShellLayout>
  );
}
```

- [ ] **Step 5: 提交**

```bash
git add src/extensions/project/ProjectList.tsx src/extensions/project/components/ src/app/projects/page.tsx
git commit -m "feat: add project list page with cards, search, and filters"
```

---

### Task 5: 项目创建向导

**Files:**
- Create: `src/extensions/project/ProjectCreateWizard.tsx`

- [ ] **Step 1: 实现多步创建向导**

遵循现有 modal 模式（`AnimatePresence` + `motion.div` + `bg-black/40 backdrop-blur-sm` 遮罩），但使用步骤指示器（Step 1/2/3/4）。

步骤：
1. **基本信息** — 项目名称、报告类型（下拉选择）、委托方、目标标准
2. **选择模板** — 从知识工厂模板库中选择（调用知识工厂 API 获取模板列表）
3. **报告大纲** — 预览从模板生成的大纲，支持手动调整（增删章节、拖拽排序）
4. **成员分配** — 指定项目经理、编写人、审核人（调用用户列表 API）

每个步骤底部有"上一步/下一步/创建"按钮。创建完成后导航到项目详情页。

- [ ] **Step 2: 提交**

```bash
git add src/extensions/project/ProjectCreateWizard.tsx
git commit -m "feat: add project creation wizard with template and member steps"
```

---

### Task 6: 项目详情页（看板 + 大纲）

**Files:**
- Create: `src/extensions/project/ProjectDetail.tsx`
- Create: `src/extensions/project/components/KanbanBoard.tsx`
- Create: `src/extensions/project/components/OutlineTree.tsx`
- Create: `src/extensions/project/components/MemberList.tsx`
- Create: `src/extensions/project/components/MilestoneTimeline.tsx`
- Create: `src/app/projects/[id]/page.tsx`

- [ ] **Step 1: 创建 KanbanBoard 组件**

看板视图，每列对应一个章节状态（未开始/编写中/待审核/已通过/已签发）。每行显示一个章节卡片（标题、负责人、字数进度）。使用水平滚动布局。

- [ ] **Step 2: 创建 OutlineTree 组件**

大纲树组件，递归渲染 `ReportOutline` 章节树。支持展开/折叠、拖拽排序（后续P1）、点击打开编辑器。

- [ ] **Step 3: 创建 MemberList 组件**

成员管理面板，显示角色分组列表。支持添加/移除成员、修改角色。

- [ ] **Step 4: 创建 MilestoneTimeline 组件**

时间线组件，垂直显示里程碑。每个节点显示名称、日期、状态。

- [ ] **Step 5: 创建 ProjectDetail 主组件**

使用顶部 Tab 导航（参照 knowledge-factory 页面的 tab 模式）:
- **概览** Tab: 项目信息卡 + 进度仪表盘 + 里程碑时间线
- **看板** Tab: KanbanBoard 组件
- **大纲** Tab: OutlineTree 组件
- **成员** Tab: MemberList 组件
- **审批** Tab: 审批流程面板（Phase 2 实现）

页面顶部：返回按钮 + 项目名称 + 状态徽章 + 操作下拉菜单（编辑/删除/归档）

- [ ] **Step 6: 创建路由页面**

文件: `src/app/projects/[id]/page.tsx`

```typescript
"use client";

import { use } from "react";
import { Suspense } from "react";
import { ShellLayout } from "@/extensions/shell";
import { ProjectDetail } from "@/extensions/project/ProjectDetail";

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <ShellLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div>}>
        <ProjectDetail projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
```

- [ ] **Step 7: 提交**

```bash
git add src/extensions/project/ProjectDetail.tsx src/extensions/project/components/ src/app/projects/[id]/page.tsx
git commit -m "feat: add project detail page with kanban, outline, members, and milestones"
```

---

## Phase 2: 协作与审批流（P0）

### Task 7: 审批面板组件

**Files:**
- Create: `src/extensions/approval/ApprovalPanel.tsx`
- Create: `src/extensions/approval/components/ApprovalStepCard.tsx`
- Create: `src/extensions/approval/components/ApprovalTimeline.tsx`
- Create: `src/extensions/approval/components/ApprovalAction.tsx`

- [ ] **Step 1: 创建 ApprovalStepCard 组件**

显示单个审批步骤：步骤名称、审批人、状态（等待中/进行中/已完成/已拒绝）。已完成步骤显示绿色对勾，进行中显示脉冲动画。

- [ ] **Step 2: 创建 ApprovalTimeline 组件**

垂直时间线，按步骤顺序展示审批进度。每个节点包含审批人信息和操作记录。

- [ ] **Step 3: 创建 ApprovalAction 组件**

审批操作面板：通过/退回/评论三个按钮 + 评论输入框。加载状态用 `Loader2`。

- [ ] **Step 4: 创建 ApprovalPanel 主组件**

嵌入到项目详情页的"审批"Tab 中。功能：
- 展示当前项目的审批工作流步骤
- 提交审批按钮（从"编写中"提交到"内审"）
- 审批操作（通过/退回/评论）
- 审批记录时间线

- [ ] **Step 5: 提交**

```bash
git add src/extensions/approval/
git commit -m "feat: add approval panel with timeline and action components"
```

---

### Task 8: 章节协作编辑页

**Files:**
- Create: `src/extensions/project/ChapterEditor.tsx`
- Create: `src/app/projects/[id]/chapter/[chapterId]/page.tsx`

- [ ] **Step 1: 创建 ChapterEditor 组件**

基于现有 Tiptap 编辑器（`src/extensions/docmgr/TiptapEditor.tsx`），增加：
- 顶部工具栏：章节标题 + 编辑者信息 + 锁定状态 + 返回项目按钮
- 左侧：章节大纲侧边栏（快速导航）
- 右侧：AI 写作助手面板（集成 DeerFlow 写作会话）
- 底部：字数统计 / 目标字数进度条

- [ ] **Step 2: 创建路由页面**

```typescript
// src/app/projects/[id]/chapter/[chapterId]/page.tsx
"use client";

import { use } from "react";
import { Suspense } from "react";
import { ShellLayout } from "@/extensions/shell";
import { ChapterEditor } from "@/extensions/project/ChapterEditor";

export default function ChapterEditorPage({
  params,
}: {
  params: Promise<{ id: string; chapterId: string }>;
}) {
  const { id, chapterId } = use(params);
  return (
    <ShellLayout>
      <ChapterEditor projectId={id} chapterId={chapterId} />
    </ShellLayout>
  );
}
```

- [ ] **Step 3: 提交**

```bash
git add src/extensions/project/ChapterEditor.tsx src/app/projects/[id]/chapter/
git commit -m "feat: add chapter collaboration editor with AI assistant panel"
```

---

## Phase 3: 插件平台（P1）

### Task 9: 插件市场与管理页

**Files:**
- Create: `src/extensions/plugin/PluginMarketplace.tsx`
- Create: `src/extensions/plugin/components/PluginCard.tsx`
- Create: `src/extensions/plugin/components/PluginConfigForm.tsx`
- Create: `src/extensions/plugin/components/ApiKeyManager.tsx`
- Create: `src/app/plugins/page.tsx`

- [ ] **Step 1: 创建 PluginCard 组件**

插件卡片，显示图标、名称、类型标签、描述、版本、作者。底部：安装/启用/禁用/配置按钮。

- [ ] **Step 2: 创建 PluginConfigForm 组件**

根据插件的 JSON Schema 动态生成配置表单。支持 string/number/boolean/select 类型字段。使用现有 Shadcn Input/Select/Switch 组件。

- [ ] **Step 3: 创建 ApiKeyManager 组件**

API Key 管理面板。表格展示 Key 列表（名称、前缀、范围、过期时间、最后使用时间）。创建 Key 时显示一次完整 Key（复制提示）。吊销操作有确认对话框。

- [ ] **Step 4: 创建 PluginMarketplace 主组件**

使用 Tab 导航（参照 knowledge-factory 模式）:
- **市场** Tab: 可安装的插件网格
- **已安装** Tab: 已安装的插件实例列表 + 配置入口
- **API Key** Tab: ApiKeyManager 组件

- [ ] **Step 5: 创建路由页面**

```typescript
// src/app/plugins/page.tsx
"use client";

import { ShellLayout } from "@/extensions/shell";
import { PluginMarketplace } from "@/extensions/plugin/PluginMarketplace";

export default function PluginsPage() {
  return (
    <ShellLayout>
      <PluginMarketplace />
    </ShellLayout>
  );
}
```

- [ ] **Step 6: 提交**

```bash
git add src/extensions/plugin/ src/app/plugins/page.tsx
git commit -m "feat: add plugin marketplace with config form and API key manager"
```

---

## Phase 4: 数据源管理（P1）

### Task 10: 数据源管理页

**Files:**
- Create: `src/extensions/data-source/DataSourceManager.tsx`
- Create: `src/extensions/data-source/components/DataSourceCard.tsx`
- Create: `src/extensions/data-source/components/ConnectionStatusBadge.tsx`
- Create: `src/extensions/data-source/components/DataSourceForm.tsx`
- Create: `src/app/data-sources/page.tsx`

- [ ] **Step 1: 创建 ConnectionStatusBadge 组件**

连接状态徽章：已连接（绿）、连接错误（红）、未连接（灰）、测试中（蓝+旋转图标）。

- [ ] **Step 2: 创建 DataSourceCard 组件**

数据源卡片：名称、类型图标、连接状态徽章、最后同步时间、操作按钮（测试连接/同步/编辑/删除）。

- [ ] **Step 3: 创建 DataSourceForm 组件**

数据源创建/编辑表单（Modal 内使用）：
- 名称、类型选择
- 连接配置（根据类型动态展示不同字段）
  - database: 主机、端口、数据库名、用户名、密码
  - api: URL、认证方式
  - file: 文件路径/上传
  - gis: 文件上传（Shapefile 等）
- 同步模式选择
- 测试连接按钮

- [ ] **Step 4: 创建 DataSourceManager 主组件**

页面布局（参照知识库管理页）：
- 标题 "数据源管理" + "添加数据源" 按钮
- 数据源卡片网格
- 创建/编辑 Modal

- [ ] **Step 5: 创建路由页面**

```typescript
// src/app/data-sources/page.tsx
"use client";

import { ShellLayout } from "@/extensions/shell";
import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";

export default function DataSourcesPage() {
  return (
    <ShellLayout>
      <DataSourceManager />
    </ShellLayout>
  );
}
```

- [ ] **Step 6: 提交**

```bash
git add src/extensions/data-source/ src/app/data-sources/page.tsx
git commit -m "feat: add data source management with connection testing and CRUD"
```

---

## Phase 5: 报告输出引擎（P1）

### Task 11: 输出模板与生成页

**Files:**
- Create: `src/extensions/output/OutputManager.tsx`
- Create: `src/extensions/output/components/LayoutTemplateCard.tsx`
- Create: `src/extensions/output/components/OutputConfigPanel.tsx`
- Create: `src/extensions/output/components/OutputProgress.tsx`
- Create: `src/app/output/page.tsx`

- [ ] **Step 1: 创建 LayoutTemplateCard 组件**

排版模板卡片：名称、报告类型标签、预览缩略图（可选）、使用次数。

- [ ] **Step 2: 创建 OutputConfigPanel 组件**

输出配置面板：
- 项目选择下拉
- 输出格式选择（Word/PDF）
- 排版模板选择
- 水印选择（初稿/送审稿/正式稿）
- 章节选择（可选：全部或指定章节）
- 生成按钮

- [ ] **Step 3: 创建 OutputProgress 组件**

输出生成进度组件：轮询任务状态，显示进度条 + 状态文字。完成后显示下载按钮。

- [ ] **Step 4: 创建 OutputManager 主组件**

使用 Tab 导航：
- **排版模板** Tab: LayoutTemplateCard 网格
- **生成输出** Tab: OutputConfigPanel + OutputProgress
- **历史记录** Tab: 已生成的输出列表（下载链接 + 时间 + 格式）

- [ ] **Step 5: 创建路由页面**

```typescript
// src/app/output/page.tsx
"use client";

import { ShellLayout } from "@/extensions/shell";
import { OutputManager } from "@/extensions/output/OutputManager";

export default function OutputPage() {
  return (
    <ShellLayout>
      <OutputManager />
    </ShellLayout>
  );
}
```

- [ ] **Step 6: 提交**

```bash
git add src/extensions/output/ src/app/output/page.tsx
git commit -m "feat: add report output engine with layout templates and generation"
```

---

## Phase 6: 集成与收尾（P0 收尾）

### Task 12: 集成项目详情与审批

**Files:**
- Modify: `src/extensions/project/ProjectDetail.tsx` — 嵌入 ApprovalPanel

- [ ] **Step 1: 在 ProjectDetail 的审批 Tab 中嵌入 ApprovalPanel**

将 `ApprovalPanel` 组件集成到项目详情页的"审批"Tab 中。传入 `projectId` 和当前用户角色信息。

- [ ] **Step 2: 在 KanbanBoard 章节卡片中添加审批状态指示**

如果章节处于"待审核"状态，显示小黄色徽章。点击可快速打开审批面板。

- [ ] **Step 3: 提交**

```bash
git add src/extensions/project/ProjectDetail.tsx
git commit -m "feat: integrate approval panel into project detail page"
```

---

### Task 13: 最终验证与导航完善

**Files:**
- Modify: `src/extensions/shell/Sidebar.tsx` — 确认所有新路由高亮正确

- [ ] **Step 1: 验证侧边栏导航高亮**

确保以下路径的侧边栏高亮逻辑正确：
- `/projects` 和 `/projects/[id]` 和 `/projects/[id]/chapter/[chapterId]` → 高亮"报告项目"
- `/plugins` → 高亮"插件"（如果有）
- `/data-sources` → 高亮"数据源"
- `/output` → 高亮"输出"（如果有）

- [ ] **Step 2: 运行类型检查**

```bash
cd frontend && pnpm typecheck
```

Expected: 无新增类型错误

- [ ] **Step 3: 运行 lint**

```bash
cd frontend && pnpm lint
```

Expected: 无新增 lint 错误

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "feat: finalize navigation and verify all report platform pages"
```

---

## P2 功能（后续迭代，仅列出任务清单）

### P2 Tasks (outline only)

- [ ] Task 14: 并行审批流程支持 — 修改 ApprovalPanel 支持并行审批节点显示
- [ ] Task 15: 电子签章集成 — 创建 ESignComponent 对接第三方签章 API
- [ ] Task 16: CAD 文件预览 — 创建 CadPreview 组件（DWG/DXF 渲染）
- [ ] Task 17: GIS 数据可视化 — 创建 GisViewer 组件（地图 + 空间数据叠加）
- [ ] Task 18: Webhook 管理 — 创建 WebhookManager 组件（事件订阅 + 回调配置）
- [ ] Task 19: 项目模板库 — 创建 ProjectTemplateGallery 组件（保存/复用项目配置）
- [ ] Task 20: 高级排版编辑器 — 创建 LayoutTemplateEditor 可视化编辑排版规则

---

## File Structure Summary

```
src/
├── app/
│   ├── projects/
│   │   ├── page.tsx                          # 项目列表路由
│   │   └── [id]/
│   │       ├── page.tsx                      # 项目详情路由
│   │       └── chapter/
│   │           └── [chapterId]/
│   │               └── page.tsx              # 章节编辑路由
│   ├── plugins/
│   │   └── page.tsx                          # 插件市场路由
│   ├── data-sources/
│   │   └── page.tsx                          # 数据源管理路由
│   └── output/
│       └── page.tsx                          # 输出引擎路由
├── extensions/
│   ├── project/
│   │   ├── types.ts                          # 类型定义
│   │   ├── api.ts                            # API 客户端
│   │   ├── ProjectList.tsx                   # 项目列表页
│   │   ├── ProjectDetail.tsx                 # 项目详情页
│   │   ├── ProjectCreateWizard.tsx           # 创建向导
│   │   ├── ChapterEditor.tsx                 # 章节编辑器
│   │   └── components/
│   │       ├── ProjectCard.tsx
│   │       ├── StatusBadge.tsx
│   │       ├── KanbanBoard.tsx
│   │       ├── OutlineTree.tsx
│   │       ├── MemberList.tsx
│   │       └── MilestoneTimeline.tsx
│   ├── approval/
│   │   ├── types.ts
│   │   ├── api.ts
│   │   ├── ApprovalPanel.tsx
│   │   └── components/
│   │       ├── ApprovalStepCard.tsx
│   │       ├── ApprovalTimeline.tsx
│   │       └── ApprovalAction.tsx
│   ├── plugin/
│   │   ├── types.ts
│   │   ├── api.ts
│   │   ├── PluginMarketplace.tsx
│   │   └── components/
│   │       ├── PluginCard.tsx
│   │       ├── PluginConfigForm.tsx
│   │       └── ApiKeyManager.tsx
│   ├── data-source/
│   │   ├── types.ts
│   │   ├── api.ts
│   │   ├── DataSourceManager.tsx
│   │   └── components/
│   │       ├── DataSourceCard.tsx
│   │       ├── ConnectionStatusBadge.tsx
│   │       └── DataSourceForm.tsx
│   ├── output/
│   │   ├── types.ts
│   │   ├── api.ts
│   │   ├── OutputManager.tsx
│   │   └── components/
│   │       ├── LayoutTemplateCard.tsx
│   │       ├── OutputConfigPanel.tsx
│   │       └── OutputProgress.tsx
│   └── shell/
│       └── Sidebar.tsx                        # 修改：添加新导航项
```
