import { authFetch } from "@/extensions/api/client";

import { toCamelCase, toSnakeCase } from "./transforms";
import type {
  CreateWorkflowRequest,
  DAGValidationResult,
  PhaseReview,
  ReviewActionRequest,
  ReviewAssignmentItem,
  ReviewStatus,
  TemplateApproval,
  UpdateWorkflowRequest,
  WorkflowDefinition,
  WorkflowDefinitionListResponse,
  WorkflowGraph,
  WorkflowStatusResponse,
} from "./types";

const API_BASE = "/workflow";

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

  listTemplates: async (reportType?: string): Promise<WorkflowDefinitionListResponse> => {
    const query = new URLSearchParams();
    query.set("is_template", "true");
    query.set("template_status", "published");
    if (reportType) query.set("report_type", reportType);
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

  publishTemplate: async (id: string): Promise<WorkflowDefinition> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}/publish-template`, {
      method: "POST",
    });
    return toCamelCase<WorkflowDefinition>(data);
  },

  unpublishTemplate: async (id: string): Promise<WorkflowDefinition> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}`, {
      method: "PUT",
      body: JSON.stringify({ template_status: "draft" }),
    });
    return toCamelCase<WorkflowDefinition>(data);
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

  // ── Phase Reviews ──

  assignReviews: async (
    projectId: string,
    phaseNode: string,
    assignments: ReviewAssignmentItem[],
  ): Promise<PhaseReview[]> => {
    const body = {
      project_id: projectId,
      phase_node: phaseNode,
      assignments: assignments.map((a) => toSnakeCase(a as unknown as Record<string, unknown>)),
    };
    const data = await authFetch<Record<string, unknown>[]>(
      `${API_BASE}/projects/${projectId}/phase-reviews/assign`,
      { method: "POST", body: JSON.stringify(body) },
    );
    return data.map((d) => toCamelCase<PhaseReview>(d));
  },

  submitReviewAction: async (
    projectId: string,
    reviewId: string,
    req: ReviewActionRequest,
  ): Promise<PhaseReview> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phase-reviews/${reviewId}/action`,
      { method: "POST", body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)) },
    );
    return toCamelCase<PhaseReview>(data);
  },

  getReviewStatus: async (projectId: string, phaseNode: string): Promise<ReviewStatus> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phase-reviews?phase_node=${phaseNode}`,
    );
    return toCamelCase<ReviewStatus>(data);
  },

  getMyReviews: async (projectId: string): Promise<PhaseReview[]> => {
    const data = await authFetch<Record<string, unknown>[]>(
      `${API_BASE}/projects/${projectId}/phase-reviews/my`,
    );
    return data.map((d) => toCamelCase<PhaseReview>(d));
  },

  // ── Workflow Monitoring ──

  getWorkflowStatus: async (projectId: string): Promise<WorkflowStatusResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/workflow-status`,
    );
    return toCamelCase<WorkflowStatusResponse>(data);
  },

  startWorkflow: async (projectId: string, workflowId: string): Promise<{ status: string; temporalWorkflowId: string }> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/start-workflow`,
      { method: "POST", body: JSON.stringify({ workflow_id: workflowId }) },
    );
    return toCamelCase<{ status: string; temporalWorkflowId: string }>(data);
  },

  cancelWorkflow: async (projectId: string): Promise<{ status: string }> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/workflow-cancel`,
      { method: "POST" },
    );
    return toCamelCase<{ status: string }>(data);
  },

  // ── Template Approval ──

  submitApproval: async (id: string): Promise<TemplateApproval> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}/submit-approval`, {
      method: "POST",
    });
    return toCamelCase<TemplateApproval>(data);
  },

  reviewApproval: async (id: string, action: "approved" | "rejected", comment?: string): Promise<TemplateApproval> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}/review-approval`, {
      method: "POST",
      body: JSON.stringify({ action, comment }),
    });
    return toCamelCase<TemplateApproval>(data);
  },

  getApprovals: async (id: string): Promise<TemplateApproval[]> => {
    const data = await authFetch<Record<string, unknown>[]>(`${API_BASE}/definitions/${id}/approvals`);
    return data.map((d) => toCamelCase<TemplateApproval>(d));
  },

  withdrawApproval: async (id: string): Promise<{ status: string }> => {
    return authFetch<{ status: string }>(`${API_BASE}/definitions/${id}/withdraw-approval`, {
      method: "POST",
    });
  },
};
