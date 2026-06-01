// ── DAG Node Types ──

export type DAGNodeType = "phase" | "review" | "condition" | "ai_generate" | "merge" | "sub_workflow";

export interface DAGNodeData {
  label: string;
  team?: string;
  chapterRange?: number[];
  aiAssist?: boolean;
  inputFrom?: string[];
  mode?: "chapter" | "dimension" | "mixed";
  expression?: string;
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
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface WorkflowDefinitionListItem {
  id: string;
  name: string;
  reportType: string | null;
  isTemplate: boolean;
  createdAt: string | null;
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
}

export interface UpdateWorkflowRequest {
  name?: string | null;
  reportType?: string | null;
  graphJson?: WorkflowGraph;
  isTemplate?: boolean;
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
}

export interface WorkflowStatusResponse {
  projectId: string;
  workflowId: string | null;
  temporalWorkflowId: string | null;
  currentPhaseNode: string | null;
  status: "idle" | "running" | "completed" | "failed";
  nodes: WorkflowNodeStatus[];
}
