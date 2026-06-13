// ── DAG Node Types ──

export type DAGNodeType = "subflow" | "task" | "review" | "ai_generate" | "condition" | "merge";

export interface RoleSlot {
  roleKey: string;
  count: number;
  label: string;
}

/** Notification configuration for any node. */
export interface NotificationConfig {
  trigger: "on_start" | "on_complete" | "on_error" | "on_review_pending" | "on_review_complete";
  targets?: string; // e.g. "role:manager, user:uuid" — empty = all members
  message?: string;
}

export interface DAGNodeData {
  label: string;
  team?: string;
  chapterRange?: number[];
  aiAssist?: boolean;
  inputFrom?: string[];
  mode?: "chapter" | "dimension" | "mixed";
  expression?: string;
  /** Required roles — who needs to be assigned before work can start. */
  requiredRoles?: RoleSlot[];
  /** Notifications to fire at lifecycle events. */
  notifications?: NotificationConfig[];
  [key: string]: unknown;
}

// ── Extended Types ──

/** Reviewer binding for task/review nodes. */
export interface ReviewerBinding {
  type: "role" | "position" | "user";
  value: string;
  label: string;
  required: boolean;
}

/** Review mode for task nodes. */
export type ReviewMode = "all" | "any" | "ratio" | "sequential";

/** Extended node data for task-type nodes. */
export interface TaskNodeData extends DAGNodeData {
  reviewMode?: ReviewMode;
  reviewers?: ReviewerBinding[];
  ratioThreshold?: number;
  rollbackTarget?: string;
  assignment?: {
    roles?: string[];
    positions?: string[];
    users?: string[];
  };
}

/** Extended node data for workflow-type nodes (notify, subflow, etc.). */
export interface WorkflowNodeData extends DAGNodeData {
  taskCount?: number;
}

// ── Core DAG Types ──

export interface DAGNode {
  id: string;
  type: DAGNodeType;
  position: { x: number; y: number };
  data: DAGNodeData;
}

export interface DAGEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

/** A single flat sub-graph (nodes + edges). */
export interface FlatGraph {
  nodes: DAGNode[];
  edges: DAGEdge[];
}

/**
 * Workflow graph — v2 hierarchical structure.
 * mainGraph: top-level subflow nodes and their edges.
 * subGraphs: keyed by subflow node ID, each contains its own nodes/edges.
 */
export interface WorkflowGraph {
  version?: number;
  mainGraph: FlatGraph;
  subGraphs?: Record<string, FlatGraph>;
}

// ── Workflow Definition ──

export interface WorkflowDefinition {
  id: string;
  name: string;
  reportType: string | null;
  graphJson: WorkflowGraph;
  isTemplate: boolean;
  orgBindings: Record<string, { deptCode?: string; departmentCode?: string }> | null;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  description: string | null;
  templateStatus: string | null;
  visibleDeptIds: string[] | null;
  version: number;
}

export interface WorkflowDefinitionListItem {
  id: string;
  name: string;
  reportType: string | null;
  isTemplate: boolean;
  createdAt: string | null;
  templateStatus: string | null;
  description: string | null;
}

export interface WorkflowDefinitionListResponse {
  items: WorkflowDefinitionListItem[];
  total: number;
}

// ── API Request Types ──

export interface CreateWorkflowRequest {
  name: string;
  reportType?: string | null;
  graphJson: WorkflowGraph;
  isTemplate?: boolean;
  orgBindings?: Record<string, { deptCode?: string }> | null;
  description?: string | null;
  visibleDeptIds?: string[] | null;
}

export interface UpdateWorkflowRequest {
  name?: string | null;
  reportType?: string | null;
  graphJson?: WorkflowGraph;
  isTemplate?: boolean;
  orgBindings?: Record<string, { deptCode?: string }> | null;
  description?: string | null;
  templateStatus?: string | null;
  visibleDeptIds?: string[] | null;
}

// ── Validation ──

export interface DAGValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// ── Phase Review ──

export interface PhaseReview {
  id: string;
  projectId: string;
  phaseNode: string;
  chapterId: string | null;
  reviewerId: string;
  reviewType: "chapter" | "dimension";
  dimension: string | null;
  status: "pending" | "approved" | "rejected";
  comment: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ReviewAssignmentItem {
  chapterId?: string | null;
  reviewerId: string;
  reviewType: "chapter" | "dimension";
  dimension?: string | null;
}

export interface ReviewStatus {
  phaseNode: string;
  total: number;
  approved: number;
  rejected: number;
  pending: number;
  allApproved: boolean;
  reviews: PhaseReview[];
}

export interface ReviewActionRequest {
  action: "approved" | "rejected";
  comment?: string | null;
}

// ── Workflow Monitoring ──

export interface WorkflowNodeStatus {
  nodeId: string;
  nodeType: string;
  label: string;
  status: "pending" | "running" | "completed" | "error";
  startedAt: string | null;
  completedAt: string | null;
  chapterTotal?: number | null;
  chapterCompleted?: number | null;
  reviewTotal?: number | null;
  reviewApproved?: number | null;
}

export interface WorkflowStatusResponse {
  projectId: string;
  workflowId: string | null;
  temporalWorkflowId: string | null;
  currentPhaseNode: string | null;
  status: "idle" | "running" | "completed" | "failed";
  nodes: WorkflowNodeStatus[];
  workflowName?: string | null;
  graphJson?: WorkflowGraph | null;
}

// ── Template Approval ──

export interface TemplateApproval {
  id: string;
  templateId: string;
  requesterId: string;
  reviewerId: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  comment: string | null;
  createdAt: string | null;
  reviewedAt: string | null;
}
