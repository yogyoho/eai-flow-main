export type Json = Record<string, any>

export interface Identity {
  user_id: string
  username: string
  display_name: string
  email?: string | null
  role_code: string
  sales_role: string
  sales_role_label: string
  region_code: string
  data_scope: string
  dept_id?: string | null
  dept_ids: string[]
  is_admin: boolean
  permissions: string[]
  auth_source: string
}

export interface Paged<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface WorkbenchSummary {
  identity: Identity
  data_as_of: string
  metrics: {
    today_todos: number
    open_todos: number
    pending_approvals: number
    blockers: number
    overdue_opportunities: number
    active_opportunities: number
    active_amount: number
    weighted_forecast: number
    approved_approvals: number
    win_rate: number
  }
  funnel: Array<{
    stage: string
    label: string
    count: number
    amount: number
    weighted_amount: number
    overdue: number
  }>
  brief: Array<{ kind: string; text: string; link: string }>
  top_todos: Todo[]
  top_opportunities: Opportunity[]
  pending_approval_items: any[]
  placeholders: Array<{ code: string; label: string; status: string; hint: string }>
  quick_entries: Array<{ label: string; link: string; kind: string }>
}

export interface Opportunity {
  id: string
  opportunity_no: string
  name: string
  customer_id: string
  customer_name?: string | null
  customer_group_name?: string | null
  mine_id?: string | null
  workface_id?: string | null
  workface_name?: string | null
  product_line: string
  amount: number
  currency: string
  stage: string
  stage_label: string
  status: string
  result?: string | null
  stage_entered_at?: string | null
  stage_due_at?: string | null
  expected_close_date?: string | null
  owner_id?: string | null
  owner_name?: string | null
  region_code: string
  source: string
  rule_probability: number
  manual_probability?: number | null
  manual_reason?: string | null
  effective_probability: number
  probability_source: string
  forecast_excluded: boolean
  duplicate_of_id?: string | null
  lost_reason_code?: string | null
  lost_reason_note?: string | null
  contract_no?: string | null
  contract_amount?: number | null
  contract_effective_date?: string | null
  version: number
  created_at?: string | null
  updated_at?: string | null
  is_overdue: boolean
  weighted_amount: number
  customer?: Json | null
  gates?: Gate[]
  pending_gate_codes?: string[]
  history?: Json[]
  probability_history?: Json[]
  duplicates?: Json[]
  approvals?: Json[]
  todos?: Json[]
  contacts?: Json[]
  [key: string]: any
}

export interface Gate {
  gate_code: string
  status: string
  message: string
  evidence?: Json
  action?: string | null
  checked_at?: string | null
}

export interface Todo {
  id: string
  todo_no: string
  type: string
  severity: string
  title: string
  description?: string | null
  object_type: string
  object_id: string
  opportunity_name?: string | null
  source_rule?: string | null
  assignee_id?: string | null
  assignee_role?: string | null
  assignee_name?: string | null
  status: string
  due_at?: string | null
  sla_minutes?: number | null
  escalation_level: number
  is_overdue: boolean
  resolution?: string | null
  resolved_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  approval?: Json | null
  [key: string]: any
}

export interface TodoStats {
  open: number
  overdue: number
  blocker: number
  high: number
  approval: number
  data_fix: number
  arbitration: number
  rule_event: number
}

export interface Approval {
  id: string
  request_no: string
  definition_code?: string
  gate_code: string
  status: string
  current_step: number
  reason: string
  requested_by: string
  requested_at?: string | null
  completed_at?: string | null
  expires_at?: string | null
  steps: Array<{
    step_no: number
    approver_role: string
    approver_id?: string | null
    status: string
    decision?: string | null
    comment?: string | null
    sla_due_at?: string | null
    decided_at?: string | null
    escalation_level?: number
    mode?: string
  }>
  opportunity?: Json | null
  actions?: Json[]
  evidence?: Json
  payload?: Json
  [key: string]: any
}

export interface MasterOptions {
  groups: Array<{ id: string; name: string; is_new_customer: boolean; region_code: string }>
  customers: Array<{ id: string; name: string; group_id?: string | null; region_code: string; related_party_status: string }>
  mines: Array<{ id: string; name: string; customer_id: string }>
  workfaces: Array<{ id: string; name: string; mine_id: string }>
  products: Array<{ id: string; name: string; product_line: string; model?: string | null }>
  contacts: Array<{ id: string; name: string; customer_id: string; title?: string | null }>
}

export class ApiError extends Error {
  status: number
  code?: string
  context?: Json

  constructor(message: string, status: number, code?: string, context?: Json) {
    super(message)
    this.status = status
    this.code = code
    this.context = context
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/sales/api'

export function getToken(): string {
  return localStorage.getItem('sales_token') || sessionStorage.getItem('sales_token') || ''
}

export function setToken(token: string): void {
  if (token) localStorage.setItem('sales_token', token)
  else localStorage.removeItem('sales_token')
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 401) {
    throw new ApiError('登录状态已失效，请重新通过 EAI 门户进入。', 401, 'AUTH-401')
  }
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'object' && body ? body.detail || '请求失败' : '请求失败'
    const code = typeof body === 'object' && body ? body.code : undefined
    const context = typeof body === 'object' && body ? body.context : undefined
    throw new ApiError(String(detail), response.status, code, context)
  }
  return body as T
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
  async download(path: string, fallbackName = 'attachment'): Promise<void> {
    const headers = new Headers()
    const token = getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API_BASE}${path}`, { headers, credentials: 'include' })
    if (!response.ok) throw new ApiError('附件下载失败', response.status)
    const blob = await response.blob()
    const disposition = response.headers.get('content-disposition') || ''
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    const name = match ? decodeURIComponent(match[1]) : fallbackName
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(url)
  },
}
