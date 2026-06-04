// ── DAG Node Types ──

export type DAGNodeType = "phase" | "review" | "condition" | "ai_generate" | "merge" | "sub_workflow";

export interface RoleSlot {
  roleKey: string;
  count: number;
  label: string;
}

export interface DAGNodeData {
  label: string;
  team?: string;
  chapterRange?: number[];
  aiAssist?: boolean;
  inputFrom?: string[];
  mode?: "chapter" | "dimension" | "mixed";
  expression?: string;
  /** Required roles for this phase — who needs to be assigned before work can start. */
  requiredRoles?: RoleSlot[];
  /** Embedded sub-workflow graph definition (for sub_workflow nodes). */
  graphJson?: WorkflowGraph;
  [key: string]: unknown;
}

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

export interface WorkflowGraph {
  nodes: DAGNode[];
  edges: DAGEdge[];
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
  // Phase enrichment
  chapterTotal?: number | null;
  chapterCompleted?: number | null;
  // Review/Approval enrichment
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
