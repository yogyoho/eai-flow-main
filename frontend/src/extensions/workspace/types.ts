// Collab Workspace — 类型定义
// EAI-CUSTOM: 全新模块，AgentSpace 式人+agent 协作 workspace

export type ProjectKind = "quickdoc" | "report";
export type TierState = "tier1" | "tier2" | "tier3";
export type ProjectStatus = "active" | "submitted_for_release" | "released" | "archived";

export interface CollabProject {
  id: string;
  name: string;
  kind: ProjectKind;
  docId: string | null;
  ownerId: string | null;
  tierState: TierState;
  tierSignals: Array<{ signal: string; at: string; to: string }> | null;
  escalatedAt: string | null;
  status: ProjectStatus;
  compliancePin: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  sectionCount: number;
  memberCount: number;
  taskCount: number;
}

export interface CollabProjectTier {
  projectId: string;
  tierState: TierState;
  escalatedAt: string | null;
  signals: Array<{ signal: string; at: string; to: string }> | null;
}

export interface CollabSection {
  id: string;
  projectId: string;
  parentId: string | null;
  title: string;
  level: number;
  sortOrder: number;
  status: string;
  docId: string | null;
  content: string | null;
  revision: number;
  wordCountTarget: number;
  wordCountCurrent: number;
  children?: CollabSection[];
}

export type MemberType = "human" | "agent";

export interface CollabMember {
  id: string;
  projectId: string;
  memberType: MemberType;
  userId: string | null;
  agentName: string | null;
  role: "owner" | "editor" | "reviewer" | "coordinator";
  joinedAt: string | null;
}

export type TaskStatus = "pending" | "in_progress" | "done" | "blocked";
export type TaskKind = "section_write" | "doc_review" | "research";

export interface CollabTask {
  id: string;
  projectId: string;
  title: string;
  kind: TaskKind;
  assigneeType: MemberType;
  assigneeUserId: string | null;
  assigneeAgentName: string | null;
  status: TaskStatus;
  sectionRef: string | null;
  docId: string | null;
  context: Record<string, unknown> | null;
  handoffState: string | null;
  handoffPayload: Record<string, unknown> | null;
  threadId: string | null;
  runId: string | null;
  attemptCount: number;
  lastError: string | null;
  revision: number;
  dueAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface CollabGate {
  id: string;
  taskId: string | null;
  scope: "task" | "project_release";
  state: "pending" | "approved" | "rejected";
  mode: string;
  participants: Array<{ type: MemberType; user_id?: string; userId?: string; agent_name?: string; agentName?: string; weight: number }>;
  deadlineAt: string | null;
  resolvedAt: string | null;
  revision: number;
}

export interface CollabActivity {
  id: string;
  actorType: MemberType;
  actorId: string | null;
  action: string;
  target: string | null;
  detail: Record<string, unknown> | null;
  createdAt: string | null;
}

export interface CollabAgentRun {
  id: string;
  threadId: string | null;
  runId: string | null;
  agentName: string;
  status: string;
  startedAt: string | null;
  finishedAt: string | null;
}
