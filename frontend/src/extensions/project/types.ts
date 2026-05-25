// ── Enums ──

export type ReportType =
  | "environmental_impact"
  | "geological_survey"
  | "feasibility_study"
  | "safety_assessment"
  | "energy_assessment"
  | "other";

export type ProjectStatus = "setup" | "outline" | "writing" | "editing" | "approval" | "published" | "archived";

export type ChapterStatus =
  | "not_started"
  | "pending"
  | "writing"
  | "draft"
  | "editing"
  | "pending_review"
  | "completed"
  | "rejected"
  | "approved"
  | "signed";

export type MemberRole = "manager" | "editor" | "writer" | "reviewer" | "approver";

// ── Chapter ──

export interface ProjectChapter {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  level: number;
  sortOrder: number;
  status: ChapterStatus;
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

/** For outline batch updates — id is null for new nodes */
export interface ChapterTreeNode {
  id?: string;
  title: string;
  level: number;
  sortOrder: number;
  purpose?: string | null;
  generationHint?: string | null;
  wordCountTarget?: number;
  children: ChapterTreeNode[];
}

// ── Member ──

export interface ProjectMember {
  id: string;
  projectId: string;
  userId: string;
  username: string;
  role: MemberRole;
  chapterAssignments?: string[];
  createdAt: string | null;
}

// ── Project ──

export interface ReportProject {
  id: string;
  name: string;
  reportType: ReportType;
  templateId: string | null;
  status: ProjectStatus;
  currentStage: number;
  threadId: string | null;
  createdBy: string | null;
  members: ProjectMember[];
  chapters: ProjectChapter[];
  chapterCount: number;
  client?: string;
  targetStandard?: string;
  outline?: string;
  milestones?: Milestone[];
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  reportType: ReportType;
  status: ProjectStatus;
  currentStage: number;
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
  client?: string;
  targetStandard?: string;
  members?: { userId: string; role: MemberRole }[];
}

export interface UpdateProjectRequest {
  name?: string;
  status?: ProjectStatus;
  currentStage?: number;
}

export interface OutlineBatchUpdateRequest {
  chapters: ChapterTreeNode[];
}

export interface ChapterUpdateRequest {
  title?: string;
  content?: string | null;
  status?: ChapterStatus;
  assignedTo?: string | null;
  wordCountTarget?: number;
}

// ── AI Action ──

export type AiActionType = "polish" | "expand" | "condense" | "format_check" | "compliance_check" | "terminology_check";

export interface AiActionRequest {
  chapterIds: string[];
  action: AiActionType;
  params?: {
    targetWordCount?: number;
    standard?: string;
  };
}

export interface AiActionResponse {
  threadId: string;
  taskCount: number;
}

// ── Writing / Editing thread responses ──

export interface StartWritingResponse {
  threadId: string;
  projectId: string;
}

export interface StartEditingResponse {
  threadId: string;
  projectId: string;
  chapterId: string;
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
  setup: "项目设定",
  outline: "大纲确认",
  writing: "AI撰写",
  editing: "协作编辑",
  approval: "审批",
  published: "已发布",
  archived: "已归档",
};

export const CHAPTER_STATUS_LABELS: Record<ChapterStatus, string> = {
  not_started: "未开始",
  pending: "待处理",
  writing: "AI撰写中",
  draft: "初稿",
  editing: "编辑中",
  pending_review: "待审核",
  completed: "已完成",
  rejected: "退回修改",
  approved: "已通过",
  signed: "已签发",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "经理",
  editor: "编辑",
  writer: "撰写人",
  reviewer: "审核人",
  approver: "批准人",
};

export const STAGE_LABELS = [
  "项目设定",
  "大纲确认",
  "AI撰写",
  "协作编辑",
  "审批",
  "定稿输出",
] as const;

// ── Permission types ──

export interface ProjectMembership {
  role: MemberRole | null;
  permissions: string[];
  defaultTab: string;
}

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

// ── Legacy aliases (used by old components pending Phase 2+ rewrite) ──

/** @deprecated Use ProjectChapter instead */
export type ReportOutline = ProjectChapter;

/** @deprecated Milestones removed in workflow redesign */
export type MilestoneStatus = "pending" | "in_progress" | "completed" | "overdue";

/** @deprecated Milestones removed in workflow redesign */
export interface Milestone {
  id: string;
  name: string;
  dueDate: string;
  status: MilestoneStatus;
  completedAt?: string | null;
  config?: { color: string };
}

export const MILESTONE_STATUS_LABELS: Record<MilestoneStatus, string> = {
  pending: "待开始",
  in_progress: "进行中",
  completed: "已完成",
  overdue: "已逾期",
};