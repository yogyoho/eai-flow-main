export type Json = Record<string, any>

export interface WorkflowFormField {
  key: string
  label: string
  type?: string
  required?: boolean
  options?: string[]
  placeholder?: string
  span?: number
}

export interface WorkflowFormSnapshot {
  formCode?: string
  formName?: string
  formPath?: string
  schema?: {
    layout?: { columns?: number }
    fields?: WorkflowFormField[]
  }
  formContent?: string | null
}

export interface WorkflowView {
  available: boolean
  engine: string
  platform_instance_id: number | null
  workflow_id?: string
  message?: string
  instance?: Json
  tasks: Json[]
  history: Json[]
  chart?: Json | null
  form?: WorkflowFormSnapshot | null
  capabilities: {
    can_decide: boolean
    can_cancel: boolean
    can_resubmit?: boolean
    actions: string[]
    active_step?: number | null
  }
}

export type WorkflowDecisionAction = 'approve' | 'reject' | 'return' | string

export interface WorkflowDecisionInput {
  action: WorkflowDecisionAction
  comment?: string
  idempotency_key?: string
}

/**
 * The host application owns authentication and the BFF endpoint.
 * Implementations must call the host BFF, never the workflow platform
 * directly, so internal service tokens stay on the server.
 */
export interface WorkflowEmbedClient {
  getWorkflow(approvalId: string): Promise<WorkflowView>
  decide(approvalId: string, input: WorkflowDecisionInput): Promise<unknown>
}

export interface WorkflowApprovalPanelProps {
  approvalId: string
  client: WorkflowEmbedClient
  refreshToken?: number
  onChanged?: () => void
  onError?: (message: string) => void
  className?: string
  /** "split" keeps form and chart side by side; "stacked" gives each a full row. */
  layout?: 'split' | 'stacked'
}
