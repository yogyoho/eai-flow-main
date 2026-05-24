import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CreateProjectRequest,
  ChapterTreeNode,
  ChapterUpdateRequest,
  ProjectListItem,
  ProjectChapter,
  ReportProject,
  StartEditingResponse,
  StartWritingResponse,
  UpdateProjectRequest,
} from "./types";

const API_BASE = "/project";

export const projectApi = {
  // ── Projects ──

  list: async (params?: {
    status?: string;
    reportType?: string;
    search?: string;
    skip?: number;
    limit?: number;
  }): Promise<{ items: ProjectListItem[]; total: number }> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.reportType) query.set("report_type", params.reportType);
    if (params?.search) query.set("search", params.search);
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    const data = await authFetch<{ items: Record<string, unknown>[]; total: number }>(`${API_BASE}/projects?${query}`);
    return {
      items: data.items.map((item) => toCamelCase<ProjectListItem>(item)),
      total: data.total,
    };
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

  // ── Outline ──

  getOutline: async (projectId: string): Promise<ProjectChapter[]> => {
    return await authFetch<ProjectChapter[]>(`${API_BASE}/projects/${projectId}/outline`);
  },

  replaceOutline: async (projectId: string, chapters: ChapterTreeNode[]): Promise<ProjectChapter[]> => {
    return await authFetch<ProjectChapter[]>(`${API_BASE}/projects/${projectId}/outline`, {
      method: "PUT",
      body: JSON.stringify({ chapters }),
    });
  },

  updateChapter: async (projectId: string, chapterId: string, updates: ChapterUpdateRequest): Promise<ProjectChapter> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/chapters/${chapterId}`,
      {
        method: "PATCH",
        body: JSON.stringify(toSnakeCase(updates as Record<string, unknown>)),
      },
    );
    return toCamelCase<ProjectChapter>(data);
  },

  confirmOutline: async (projectId: string): Promise<ReportProject> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/confirm-outline`,
      { method: "POST" },
    );
    return toCamelCase<ReportProject>(data);
  },

  // ── Members ──

  addMember: async (projectId: string, userId: string, role: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, role }),
    });
  },

  removeMember: async (projectId: string, userId: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/members/${userId}`, { method: "DELETE" });
  },

  // ── Writing & Editing ──

  startWriting: async (projectId: string): Promise<StartWritingResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/start-writing`,
      { method: "POST" },
    );
    return toCamelCase<StartWritingResponse>(data);
  },

  startChapterEditing: async (projectId: string, chapterId: string): Promise<StartEditingResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/chapters/${chapterId}/start-editing`,
      { method: "POST" },
    );
    return toCamelCase<StartEditingResponse>(data);
  },

  // ── Legacy aliases ──

  /** @deprecated Use updateChapter instead */
  updateOutline: async (projectId: string, outlineId: string, data: Record<string, unknown>): Promise<ProjectChapter> => {
    return projectApi.updateChapter(projectId, outlineId, data as import("./types").ChapterUpdateRequest);
  },
};