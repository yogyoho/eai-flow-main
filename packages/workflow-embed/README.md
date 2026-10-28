# @eai/workflow-embed

Reusable workflow approval panel for EAI business frontends.

It contains the read-only view (frozen form snapshot, flow chart, workflow history) and the
approve / reject / return action surface. Authentication and platform calls stay in the host BFF;
the browser never receives the workflow internal service token.

## Install

Local workspace (this repository):

```json
{
  "dependencies": {
    "@eai/workflow-embed": "file:../../../packages/workflow-embed"
  }
}
```

The path is relative to the consuming frontend package. In a published environment, use the
registry version instead.

## Usage

```tsx
import {
  WorkflowApprovalPanel,
  type WorkflowEmbedClient,
} from '@eai/workflow-embed'
import '@eai/workflow-embed/styles.css'

const client: WorkflowEmbedClient = {
  getWorkflow: (approvalId) =>
    fetch(`/sales/api/v1/approvals/${approvalId}/workflow`, {
      credentials: 'include',
    }).then((response) => {
      if (!response.ok) throw new Error('workflow view failed')
      return response.json()
    }),
  decide: (approvalId, input) =>
    fetch(`/sales/api/v1/approvals/${approvalId}/decision`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }).then((response) => {
      if (!response.ok) throw new Error('decision failed')
      return response.json()
    }),
}

export function ApprovalDetail({ approvalId }: { approvalId: string }) {
  return (
    <WorkflowApprovalPanel
      approvalId={approvalId}
      client={client}
      layout="stacked" // form and chart each get a full row
      onChanged={() => {
        // refresh the host approval detail/list
      }}
    />
  )
}
```

## BFF contract

`client.getWorkflow(approvalId)` must return:

```ts
interface WorkflowView {
  available: boolean
  engine: string
  platform_instance_id: number | null
  workflow_id?: string
  message?: string
  instance?: Record<string, any>
  tasks: Record<string, any>[]
  history: Record<string, any>[]
  chart?: Record<string, any> | null
  form?: {
    formCode?: string
    formName?: string
    formPath?: string
    schema?: { fields?: Array<{ key: string; label: string; required?: boolean }> }
    formContent?: string | null
  } | null
  capabilities: {
    can_decide: boolean
    can_cancel: boolean
    actions: string[]
    active_step?: number | null
  }
}
```

`client.decide(approvalId, input)` receives:

```ts
{
  action: 'approve' | 'reject' | 'return'
  comment?: string
  idempotency_key: string
}
```

The host BFF is responsible for:

- resolving the sales user / tenant / permissions;
- calling the workflow platform with server-side credentials;
- applying the decision to the sales projection;
- returning a safe error message.

## Build

```bash
cd packages/workflow-embed
pnpm install
pnpm build
```

The package emits ESM and declarations to `dist/`. `styles.css` is exported from the package root:

```ts
import '@eai/workflow-embed/styles.css'
```

For an internal registry, publish from this directory:

```bash
pnpm build
pnpm publish
```

`prepublishOnly` rebuilds `dist/` first. Consumers should pin a published version once the
internal registry is available; the `file:` dependency is only for this monorepo and its Docker
build.

## Layout

- `layout="split"` (default): form snapshot and chart are displayed side by side.
- `layout="stacked"`: form snapshot and chart each occupy a full row, which is recommended for
  approval drawers or narrow containers.

## Design notes

- The component is intentionally presentation-only. It does not know the sales API, EAI cookies,
  or workflow internal tokens.
- `@eai/workflow-embed` is a peer-dependency package: `react` and `lucide-react` must be supplied by
  the host application.
- The package uses `wf-` prefixed classes and CSS variables so it can be embedded in different
  business shells without leaking styles.
- `/workflow` remains the standalone designer and administration workbench. This package is for
  business approval pages, not for embedding the full workflow site.
