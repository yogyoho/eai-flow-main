import { authFetch } from "@/extensions/api/client";

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
      return {
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