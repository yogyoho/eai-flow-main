import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  ReportProject,
  ReportOutline,
  CreateProjectRequest,
  UpdateProjectRequest,
  Milestone,
} from "./types";

const API_BASE = "/api/project";

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
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<ReportProject>(data);
  },

  update: async (id: string, req: UpdateProjectRequest): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
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