// Collab Workspace — API 客户端
// EAI-CUSTOM: 全新模块。authFetch base = /api/extensions，故前缀 /workspace
// 统一处理 snake_case↔camelCase 转换（后端 Pydantic 用 snake_case，前端类型用 camelCase）

import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CollabActivity,
  CollabAgentRun,
  CollabGate,
  CollabMember,
  CollabProject,
  CollabSection,
  CollabTask,
} from "./types";

const API_BASE = "/workspace";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const hasBody = method !== "GET" && method !== "HEAD";
  // 请求体转 snake_case
  const body = hasBody && options.body
    ? JSON.stringify(toSnakeCase(JSON.parse(options.body as string)))
    : options.body;
  const data = await authFetch<unknown>(path, { ...options, body });
  // 响应转 camelCase（对象/数组）
  if (data === null || data === undefined) return data as T;
  if (Array.isArray(data)) {
    return data.map((item) => (item && typeof item === "object" ? toCamelCase(item as Record<string, unknown>) : item)) as T;
  }
  if (typeof data === "object") {
    return toCamelCase(data as Record<string, unknown>) as T;
  }
  return data as T;
}

export const workspaceApi = {
  // ── Projects ──

  listProjects: async (): Promise<CollabProject[]> => {
    const data = await request<CollabProject[]>(`${API_BASE}/projects`);
    return data ?? [];
  },

  createProject: async (name: string, kind: "quickdoc" | "report"): Promise<CollabProject> => {
    return request<CollabProject>(`${API_BASE}/projects`, {
      method: "POST",
      body: JSON.stringify({ name, kind }),
    });
  },

  getProject: async (id: string): Promise<CollabProject> => {
    return request<CollabProject>(`${API_BASE}/projects/${id}`);
  },

  updateProject: async (id: string, patch: Record<string, unknown>): Promise<CollabProject> => {
    return request<CollabProject>(`${API_BASE}/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  deleteProject: async (id: string): Promise<void> => {
    await request<void>(`${API_BASE}/projects/${id}`, { method: "DELETE" });
  },

  getTier: async (id: string): Promise<{ tierState: string; signals: CollabProject["tierSignals"] }> => {
    return request(`${API_BASE}/projects/${id}/tier`);
  },

  release: async (id: string): Promise<CollabProject> => {
    return request<CollabProject>(`${API_BASE}/projects/${id}/release`, { method: "POST" });
  },

  promoteToReport: async (id: string): Promise<CollabSection[]> => {
    return request<CollabSection[]>(`${API_BASE}/projects/${id}/promote-to-report`, { method: "POST" });
  },

  // ── Sections ──

  listSections: async (id: string): Promise<CollabSection[]> => {
    return request<CollabSection[]>(`${API_BASE}/projects/${id}/sections`);
  },

  createSection: async (id: string, title: string): Promise<CollabSection> => {
    return request<CollabSection>(`${API_BASE}/projects/${id}/sections`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  // ── Members ──

  listMembers: async (id: string): Promise<CollabMember[]> => {
    return request<CollabMember[]>(`${API_BASE}/projects/${id}/members`);
  },

  addMember: async (id: string, member: { memberType: "human" | "agent"; userId?: string; agentName?: string; role?: string }): Promise<CollabMember> => {
    return request<CollabMember>(`${API_BASE}/projects/${id}/members`, {
      method: "POST",
      body: JSON.stringify(member),
    });
  },

  removeMember: async (id: string, memberId: string): Promise<void> => {
    await request<void>(`${API_BASE}/projects/${id}/members/${memberId}`, { method: "DELETE" });
  },

  // ── Tasks ──

  listTasks: async (id: string): Promise<CollabTask[]> => {
    return request<CollabTask[]>(`${API_BASE}/projects/${id}/tasks`);
  },

  createTask: async (id: string, task: { title: string; kind: string }): Promise<CollabTask> => {
    return request<CollabTask>(`${API_BASE}/projects/${id}/tasks`, {
      method: "POST",
      body: JSON.stringify(task),
    });
  },

  assignTask: async (id: string, taskId: string, assign: { assigneeType: "human" | "agent"; userId?: string; agentName?: string }): Promise<CollabTask> => {
    return request<CollabTask>(`${API_BASE}/projects/${id}/tasks/${taskId}/assign`, {
      method: "POST",
      body: JSON.stringify(assign),
    });
  },

  spawnRun: async (id: string, taskId: string, body: { agentName?: string } = {}): Promise<{ runId: string; status: string }> => {
    return request(`${API_BASE}/projects/${id}/tasks/${taskId}/runs`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  listRuns: async (id: string, taskId: string): Promise<CollabAgentRun[]> => {
    return request<CollabAgentRun[]>(`${API_BASE}/projects/${id}/tasks/${taskId}/runs`);
  },

  // ── Gates ──

  listGates: async (id: string): Promise<CollabGate[]> => {
    return request<CollabGate[]>(`${API_BASE}/projects/${id}/gates`);
  },

  judgeGate: async (id: string, gateId: string, action: "approve" | "reject" | "comment", comment?: string): Promise<{ id: string; state: string }> => {
    return request(`${API_BASE}/projects/${id}/gates/${gateId}/judge`, {
      method: "POST",
      body: JSON.stringify({ action, comment }),
    });
  },

  reopenGate: async (id: string, gateId: string): Promise<{ id: string; state: string }> => {
    return request(`${API_BASE}/projects/${id}/gates/${gateId}/reopen`, { method: "POST" });
  },

  // ── Publish / Activity ──

  publishDoc: async (id: string): Promise<{ synced: string[]; skipped: string[] }> => {
    return request(`${API_BASE}/projects/${id}/publish-doc`, { method: "POST" });
  },

  listActivities: async (id: string): Promise<CollabActivity[]> => {
    return request<CollabActivity[]>(`${API_BASE}/projects/${id}/activities`);
  },
};
