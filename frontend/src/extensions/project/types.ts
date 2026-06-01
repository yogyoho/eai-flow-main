// ── Enums ──

export type ReportType =
  | "environmental_impact"
  | "geological_survey"
  | "feasibility_study"
  | "safety_assessment"
  | "energy_assessment"
  | "other";

export type ProjectStatus = "active" | "completed" | "archived";

export type MemberRole = "owner" | "member";

// ── Chapter ──

export interface ProjectChapter {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  level: number;
  sortOrder: number;
  status: string;
  content: string | null;
  assignedTo: string | null;
  assignedName: string | null;
  wordCountTarget: number;
  wordCountCurrent: number;
  purpose: string | null;
  generationHint: string | null;
  children: ProjectChapter[];
  createdAt: string | null;
  updatedAt: string | null;
}

// ── Member ──

export interface ProjectMember {
  id: string;
  projectId: string;
  userId: string;
  username: string;
  role: MemberRole;
  createdAt: string | null;
}

// ── Project ──

export interface ReportProject {
  id: string;
  name: string;
  reportType: ReportType;
  templateId: string | null;
  status: ProjectStatus;
  threadId: string | null;
  createdBy: string | null;
  members: ProjectMember[];
  chapters: ProjectChapter[];
  chapterCount: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  reportType: ReportType;
  status: ProjectStatus;
  templateId: string | null;
  templateName: string | null;
  chapterCount: number;
  memberCount: number;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

// ── API Request Types ──

export interface CreateProjectRequest {
  name: string;
  reportType: ReportType;
  templateId?: string | null;
  members?: { userId: string; role: MemberRole }[];
}

export interface UpdateProjectRequest {
  name?: string;
  status?: ProjectStatus;
}

// ── Labels ──

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  environmental_impact: "环境影响评价",
  geological_survey: "地质勘查",
  feasibility_study: "可行性研究",
  safety_assessment: "安全评价",
  energy_assessment: "节能评价",
  other: "其他",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  active: "进行中",
  completed: "已完成",
  archived: "已归档",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  owner: "负责人",
  member: "成员",
};

// ── Approval config types ──

export interface ApprovalStepConfig {
  stepOrder: number;
  stepName: string;
  reviewerId: string;
}

export interface ApprovalSubmitRequest {
  steps: ApprovalStepConfig[];
}

export interface ApprovalWorkflowWithRecords {
  id: string;
  stepOrder: number;
  stepName: string;
  reviewerId: string | null;
  roleRequired: string;
  status: string;
  records: Array<{
    id: string;
    workflowId: string;
    chapterId: string | null;
    action: string;
    reviewerId: string;
    reviewerName: string;
    comment: string | null;
    createdAt: string | null;
  }>;
}

export interface ApprovalStatusResponse {
  projectId: string;
  currentStep: number | null;
  totalSteps: number;
  steps: ApprovalWorkflowWithRecords[];
  allApproved: boolean;
}

// ── Project Permissions ──

export interface ProjectPermissions {
  role: string | null;
  permissions: string[];
  phaseDuties: Record<string, { duty: string; role?: string }> | null;
  isAdmin: boolean;
}
