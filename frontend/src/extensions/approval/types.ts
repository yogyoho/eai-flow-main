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