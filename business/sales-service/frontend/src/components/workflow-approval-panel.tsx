import {
  WorkflowApprovalPanel as WorkflowEmbedPanel,
  type WorkflowApprovalPanelProps,
  type WorkflowEmbedClient,
  type WorkflowView,
} from '@eai/workflow-embed'
import '@eai/workflow-embed/styles.css'
import { useMemo } from 'react'

import { api } from '../api'

type Props = Omit<WorkflowApprovalPanelProps, 'client'>

/**
 * Sales adapter for the shared @eai/workflow-embed package.
 *
 * The package owns presentation and interaction; this adapter is the only
 * place that knows the sales BFF routes. Both calls stay same-origin and use
 * the existing sales session (bearer token or EAI cookie).
 */
export function WorkflowApprovalPanel(props: Props) {
  const client = useMemo<WorkflowEmbedClient>(
    () => ({
      getWorkflow: (approvalId) => api.get<WorkflowView>(`/approvals/${approvalId}/workflow`),
      decide: (approvalId, input) => api.post<unknown>(`/approvals/${approvalId}/decision`, input),
    }),
    [],
  )

  return <WorkflowEmbedPanel layout="stacked" {...props} client={client} />
}
