// ── Enums ──

export type ReportType =
  | "environmental_impact"
  | "geological_survey"
  | "feasibility_study"
  | "safety_assessment"
  | "energy_assessment"
  | "other";

export type ProjectStatus = "setup" | "outline" | "writing" | "editing" | "approval" | "published" | "archived";

export type ChapterStatus = "pending" | "writing" | "draft" | "editing" | "completed" | "rejected" | "approved";

export type MemberRole = "manager" | "editor" | "reviewer" | "approver";

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
  pending: "待处理",
  writing: "AI撰写中",
  draft: "初稿",
  editing: "编辑中",
  completed: "已完成",
  rejected: "退回修改",
  approved: "已通过",
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "项目经理",
  editor: "编辑",
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