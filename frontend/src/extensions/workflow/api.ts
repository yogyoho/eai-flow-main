import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CreateWorkflowRequest,
  DAGValidationResult,
  UpdateWorkflowRequest,
  WorkflowDefinition,
  WorkflowDefinitionListResponse,
  WorkflowGraph,
} from "./types";

const API_BASE = "/api/extensions/workflow";

export const workflowApi = {
  // ── Definitions ──

  list: async (params?: {
    isTemplate?: boolean;
    reportType?: string;
  }): Promise<WorkflowDefinitionListResponse> => {
    const query = new URLSearchParams();
    if (params?.isTemplate !== undefined) query.set("is_template", String(params.isTemplate));
    if (params?.reportType) query.set("report_type", params.reportType);
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions?${query}`);
    return toCamelCase<WorkflowDefinitionListResponse>(data);
  },

  get: async (id: string): Promise<WorkflowDefinition> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}`);
    return toCamelCase<WorkflowDefinition>(data);
  },

  create: async (req: CreateWorkflowRequest): Promise<WorkflowDefinition> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions`, {
      method: "POST",
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<WorkflowDefinition>(data);
  },

  update: async (id: string, req: UpdateWorkflowRequest): Promise<WorkflowDefinition> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}`, {
      method: "PUT",
      body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)),
    });
    return toCamelCase<WorkflowDefinition>(data);
  },

  delete: async (id: string): Promise<void> => {
    await authFetch<void>(`${API_BASE}/definitions/${id}`, { method: "DELETE" });
  },

  validate: async (graph: WorkflowGraph): Promise<DAGValidationResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/validate`, {
      method: "POST",
      body: JSON.stringify(graph),
    });
    return toCamelCase<DAGValidationResult>(data);
  },

  // ── Traceability / Sources ──

  getSources: async (projectId: string, chapterId: string): Promise<{ sources: any[]; stats: Record<string, number> }> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${projectId}/chapters/${chapterId}/sources`);
    return toCamelCase<{ sources: any[]; stats: Record<string, number> }>(data);
  },

  getMissingSources: async (projectId: string, chapterId: string): Promise<{ missing: Array<{ blockIndex: number; preview: string }> }> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/projects/${projectId}/chapters/${chapterId}/sources/missing`);
    return toCamelCase<{ missing: Array<{ blockIndex: number; preview: string }> }>(data);
  },
};
