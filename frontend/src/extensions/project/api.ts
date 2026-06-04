import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  ApprovalStepConfig,
  ApprovalStatusResponse,
  BatchAssignRequest,
  CreateProjectRequest,
  PhaseBoardResponse,
  PhaseReadinessResponse,
  ProjectListItem,
  ProjectPermissions,
  ReportProject,
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

  enter: async (id: string): Promise<{ threadId: string; projectId: string }> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${id}/enter`, { method: "POST" });
    return toCamelCase<{ threadId: string; projectId: string }>(data);
  },

  getFiles: async (id: string): Promise<Record<string, unknown>[]> => {
    const data = await authFetch<Record<string, unknown>[]>(`${API_BASE}/projects/${id}/files`);
    return data;
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

  updateMember: async (
    projectId: string,
    userId: string,
    data: { role?: string; phase_duties?: Record<string, unknown> },
  ): Promise<{ success: boolean }> => {
    return authFetch(`${API_BASE}/projects/${projectId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  // ── Approval workflow ──

  submitApproval: async (
    projectId: string,
    steps: ApprovalStepConfig[],
  ): Promise<{ projectId: string; status: string; stepCount: number }> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/submit-approval`,
      {
        method: "POST",
        body: JSON.stringify(toSnakeCase({ steps })),
      },
    );
    return toCamelCase(data);
  },

  doApprovalAction: async (
    projectId: string,
    workflowId: string,
    action: "approve" | "reject",
    comment?: string,
  ): Promise<Record<string, unknown>> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/approval-action`,
      {
        method: "POST",
        body: JSON.stringify(toSnakeCase({ workflowId, action, comment })),
      },
    );
    return data;
  },

  getApprovalStatus: async (projectId: string): Promise<ApprovalStatusResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/approval-status`,
    );
    return toCamelCase<ApprovalStatusResponse>(data);
  },

  // ── Permissions ──

  getMyPermissions: async (projectId: string): Promise<ProjectPermissions> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/my-permissions`,
    );
    return toCamelCase<ProjectPermissions>(data);
  },

  // ── Chapters ──

  updateChapterStatus: async (projectId: string, chapterId: string, status: string): Promise<void> => {
    await authFetch(`${API_BASE}/projects/${projectId}/chapters/${chapterId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  // ── Phase Board ──

  getPhaseBoard: async (projectId: string, phaseNode: string): Promise<PhaseBoardResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phases/${phaseNode}/board`,
    );
    return toCamelCase<PhaseBoardResponse>(data);
  },

  batchAssign: async (
    projectId: string,
    phaseNode: string,
    assignments: BatchAssignRequest["assignments"],
  ): Promise<{ updated: number; total: number }> => {
    return authFetch(`${API_BASE}/projects/${projectId}/phases/${phaseNode}/batch-assign`, {
      method: "POST",
      body: JSON.stringify({ assignments }),
    });
  },

  // ── Phase Readiness ──

  getPhaseReadiness: async (projectId: string, phaseNode: string): Promise<PhaseReadinessResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phases/${phaseNode}/readiness`,
    );
    return toCamelCase<PhaseReadinessResponse>(data);
  },
};
