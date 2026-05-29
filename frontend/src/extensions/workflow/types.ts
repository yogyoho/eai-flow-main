// ── DAG Node Types ──

export type DAGNodeType = "phase" | "review" | "condition" | "ai_generate" | "merge";

export interface DAGNodeData {
  label: string;
  team?: string;
  chapterRange?: number[];
  aiAssist?: boolean;
  inputFrom?: string[];
  mode?: "chapter" | "dimension" | "mixed";
  expression?: string;
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
