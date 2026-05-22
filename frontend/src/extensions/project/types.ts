export type ReportType = "environmental_impact" | "geological_survey" | "feasibility_study" | "safety_assessment" | "energy_assessment" | "other";

export type ProjectStatus = "planning" | "writing" | "review" | "finalizing" | "archived";

export type MemberRole = "manager" | "writer" | "reviewer" | "approver" | "issuer";

export type ChapterStatus = "not_started" | "writing" | "pending_review" | "approved" | "signed";

export type MilestoneStatus = "pending" | "in_progress" | "completed" | "overdue";

export interface ReportProject {
  id: string;
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard: string;
  status: ProjectStatus;
  templateId: string | null;
  complianceRuleSetId: string | null;
  lawIds: string[];
  members: ProjectMember[];
  outline: ReportOutline | null;
  milestones: Milestone[];
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMember {
  userId: string;
  username: string;
  role: MemberRole;
  chapterAssignments: string[];
  avatarUrl?: string;
}

export interface ReportOutline {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  order: number;
  status: ChapterStatus;
  assigneeId: string | null;
  assigneeName: string | null;
  wordCountTarget: number;
  wordCountCurrent: number;
  description: string;
  children: ReportOutline[];
}

export interface Milestone {
  id: string;
  projectId: string;
  name: string;
  dueDate: string;
  completedAt: string | null;
  status: MilestoneStatus;
}

export interface CreateProjectRequest {
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard?: string;
  templateId?: string;
  complianceRuleSetId?: string;
  lawIds?: string[];
  members?: { userId: string; role: MemberRole }[];
}

export interface UpdateProjectRequest {
  name?: string;
  client?: string;
  targetStandard?: string;
  status?: ProjectStatus;
  complianceRuleSetId?: string;
  lawIds?: string[];
}

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  environmental_impact: "环境影响评价",
  geological_survey: "地质勘查",
  feasibility_study: "可行性研究",
  safety_assessment: "安全评价",
  energy_assessment: "节能评价",
  other: "其他",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: "规划中",
  writing: "编写中",
  review: "审核中",
  finalizing: "定稿中",
  archived: "已归档",
};

export const CHAPTER_STATUS_LABELS: Record<ChapterStatus, string> = {
  not_started: "未开始",
  writing: "编写中",
  pending_review: "待审核",
  approved: "已通过",
  signed: "已签发",
};

export const MILESTONE_STATUS_LABELS: Record<MilestoneStatus, string> = {
  pending: "待开始",
  in_progress: "进行中",
  completed: "已完成",
  overdue: "已逾期",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "项目经理",
  writer: "编写人",
  reviewer: "审核人",
  approver: "批准人",
  issuer: "签发人",
};