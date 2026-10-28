export const STAGES = [
  { code: 'S1', label: '线索', short: 'S1' },
  { code: 'S2', label: '初步接触', short: 'S2' },
  { code: 'S3', label: '需求确认', short: 'S3' },
  { code: 'S4', label: '技术方案 / 示范', short: 'S4' },
  { code: 'S5', label: '投标立项', short: 'S5' },
  { code: 'S6', label: '报价审批', short: 'S6' },
  { code: 'S7', label: '投标', short: 'S7' },
  { code: 'S8', label: '中标 / 失标', short: 'S8' },
  { code: 'S9', label: '合同生效', short: 'S9' },
]

export const ROLE_LABELS: Record<string, string> = {
  sales_rep: '客户经理',
  regional_manager: '大区经理',
  sales_director: '销售总监',
  compliance_officer: '合规官',
  data_steward: '数据管家',
  sales_admin: '销售管理员',
}

export const TODO_TYPES: Record<string, string> = {
  approval: '审批',
  data_fix: '数据补全',
  arbitration: '撞单仲裁',
  rule_event: '规则事件',
}

export const SEVERITY_LABELS: Record<string, string> = {
  blocker: '阻断',
  high: '高',
  medium: '中',
  low: '低',
}

export const GATE_LABELS: Record<string, string> = {
  R4: 'R4 新客户例外',
  R6: 'R6 关联方审查',
  DUPLICATE: '撞单合并',
  R10: 'R10 撞单仲裁',
}

export const RULE_LABELS: Record<string, string> = {
  STAGE_OVERDUE: '阶段停留超期',
  R2: 'R2 概率规则',
  R4: 'R4 新客户例外',
  R6: 'R6 关联方审查',
  R9: 'R9 阶段字段校验',
  R10: 'R10 撞单仲裁',
  DUPLICATE: '撞单',
  MANUAL: '手工创建',
}

export const TODO_STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  cancelled: '已取消',
}

export const APPROVAL_STATUS_LABELS: Record<string, string> = {
  pending_start: '待启动',
  running: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  returned: '待修改重提',
  cancelled: '已取消',
  expired: '已过期',
  failed: '启动失败',
}

export const STEP_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  active: '进行中',
  approved: '已通过',
  rejected: '已驳回',
  returned: '已退回',
  skipped: '已跳过',
  cancelled: '已取消',
}

export const ACTION_LABELS: Record<string, string> = {
  approve: '同意',
  reject: '驳回',
  return: '退回申请人',
  resubmit: '重新提交',
  delegate: '转办',
  cancel: '取消',
  create: '发起',
}

export const OBJECT_TYPE_LABELS: Record<string, string> = {
  opportunity: '商机',
  customer: '客户',
  approval_request: '审批单',
  todo: '待办',
}

export function nextStage(stage: string): string | null {
  const index = STAGES.findIndex((item) => item.code === stage)
  if (index < 0 || index >= STAGES.length - 1) return null
  return STAGES[index + 1].code
}

export function stageLabel(code: string): string {
  return STAGES.find((item) => item.code === code)?.label || code
}

export function money(value?: number | null, compact = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (compact) {
    if (Math.abs(value) >= 100_000_000) return `¥${(value / 100_000_000).toFixed(2)}\u00a0亿`
    if (Math.abs(value) >= 10_000) return `¥${(value / 10_000).toFixed(0)}\u00a0万`
  }
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 0 }).format(value)
}

export function percent(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value)}%`
}

export function dateText(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function dateTimeText(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function relativeDue(value?: string | null): string {
  if (!value) return '无期限'
  const due = new Date(value).getTime()
  const hours = Math.round((due - Date.now()) / 36e5)
  if (hours < 0) return `已超时 ${Math.abs(hours)}h`
  if (hours < 24) return `${hours}h 后到期`
  return `${Math.round(hours / 24)}d 后到期`
}

export function initials(name?: string | null): string {
  if (!name) return '—'
  const clean = name.trim()
  if (!clean) return '—'
  if (/[\u4e00-\u9fff]/.test(clean)) return clean.slice(-2)
  const parts = clean.split(/\s+/).filter(Boolean)
  if (parts.length > 1) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
  return clean.slice(0, 2).toUpperCase()
}

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}
