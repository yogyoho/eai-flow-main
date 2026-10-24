import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleAlert,
  ExternalLink,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
  TimerReset,
  UserRoundCheck,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useSession } from '../App'
import { api, qs, type Approval, type Json, type Paged } from '../api'
import {
  Badge,
  Drawer,
  EmptyState,
  ErrorBanner,
  Field,
  Spinner,
  statusTone,
  useToast,
} from '../components/ui'
import { ACTION_LABELS, APPROVAL_STATUS_LABELS, GATE_LABELS, ROLE_LABELS, STEP_STATUS_LABELS, dateTimeText, errorText, money, relativeDue } from '../lib/format'

const STATUSES = ['pending_start', 'running', 'approved', 'rejected', 'returned', 'cancelled', 'expired', 'failed']

export default function Approvals() {
  const { identity } = useSession()
  const { push } = useToast()
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => Object.fromEntries(params.entries()), [params])
  const [data, setData] = useState<(Paged<Approval> & { pending_my_action: number }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<string | null>(params.get('focus'))

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.get<Paged<Approval> & { pending_my_action: number }>(`/approvals${qs({ ...filters, limit: 50 })}`)
      setData(result)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const value = params.get('focus')
    if (value) setFocus(value)
  }, [params])

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function openApproval(id: string) {
    setFocus(id)
    const next = new URLSearchParams(params)
    next.set('focus', id)
    setParams(next, { replace: true })
  }

  function closeApproval() {
    setFocus(null)
    const next = new URLSearchParams(params)
    next.delete('focus')
    setParams(next, { replace: true })
  }

  return (
    <div className="stack">
      <section className="metric-grid">
        <div className="metric-card accent">
          <span>待我处理</span>
          <strong>{data?.pending_my_action ?? '—'}</strong>
          <small>当前账号的活跃审批步骤</small>
        </div>
        <div className="metric-card">
          <span>审批单总量</span>
          <strong>{data?.total ?? '—'}</strong>
          <small>受当前筛选条件约束</small>
        </div>
        <div className="metric-card">
          <span>运行中</span>
          <strong>{data?.items.filter((item) => item.status === 'running').length ?? '—'}</strong>
          <small>由 Temporal 持有流程状态</small>
        </div>
        <div className="metric-card">
          <span>已通过</span>
          <strong>{data?.items.filter((item) => item.status === 'approved').length ?? '—'}</strong>
          <small>通过只解除闸门，不推进阶段</small>
        </div>
        <div className="metric-card">
          <span>执行引擎</span>
          <strong className="metric-word">Temporal</strong>
          <small>
            <a className="text-link" href="/temporal/" target="_blank" rel="noreferrer">
              Temporal UI <ExternalLink size={11} />
            </a>
          </small>
        </div>
      </section>

      <div className="note-bar">
        <ShieldCheck size={13} />
        <span>
          <b>审批决定不直接改商机。</b>决策先进入 Temporal，由幂等 activity 写入审批投影；通过只解除闸门，
          销售仍需回到商机执行下一步。允许自批与转办；转办会重置该步骤 24 小时时钟。
        </span>
      </div>

      <section className="panel filter-panel">
        <div className="filter-row">
          <label className="search-box">
            <Search size={17} />
            <input value={filters.opportunity_id || ''} onChange={(event) => setFilter('opportunity_id', event.target.value)} placeholder="按商机 ID 过滤" />
          </label>
          <select value={filters.status || ''} onChange={(event) => setFilter('status', event.target.value)}>
            <option value="">全部状态</option>
            {STATUSES.map((status) => <option key={status} value={status}>{APPROVAL_STATUS_LABELS[status] || status}</option>)}
          </select>
          <select value={filters.gate_code || ''} onChange={(event) => setFilter('gate_code', event.target.value)}>
            <option value="">全部闸门</option>
            <option value="R4">R4 新客户例外</option>
            <option value="R6">R6 关联方审查</option>
            <option value="DUPLICATE">撞单合并</option>
            <option value="R10">R10 撞单仲裁</option>
          </select>
          <button
            type="button"
            className={`toggle-chip ${filters.mine === '1' ? 'on' : ''}`}
            onClick={() => setFilter('mine', filters.mine === '1' ? '' : '1')}
          >
            <UserRoundCheck size={15} /> 待我审批
          </button>
          <button type="button" className="button ghost" onClick={() => void load()}>
            <RefreshCw size={15} /> 刷新
          </button>
        </div>
        <div className="filter-summary">
          <span><ShieldCheck size={14} /> 共 {data?.total ?? 0} 单</span>
          <span className="muted">审批状态由 Temporal 投影，前端不会本地推断通过或过期。</span>
        </div>
      </section>

      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}

      <section className="panel table-panel">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>审批单 / 商机</th>
                    <th>闸门</th>
                    <th>当前步骤</th>
                    <th>申请人</th>
                    <th>时限</th>
                    <th>状态</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((item) => {
                    const activeStep = item.steps.find((step) => step.status === 'active') || item.steps.find((step) => step.status === 'pending')
                    return (
                      <tr key={item.id} onClick={() => openApproval(item.id)}>
                        <td>
                          <div className="primary-cell">
                            <strong>{item.request_no}</strong>
                            <span>{item.opportunity_name || item.opportunity?.name || item.opportunity_id}</span>
                          </div>
                        </td>
                        <td>
                          <Badge tone="violet">{GATE_LABELS[item.gate_code] || item.gate_code}</Badge>
                          <span className="cell-sub">{item.definition_code || '默认模板'}</span>
                        </td>
                        <td>
                          <span>{item.current_step} / {item.steps.length}</span>
                          <span className="cell-sub">
                            {activeStep ? `${ROLE_LABELS[activeStep.approver_role] || activeStep.approver_role} · ${relativeDue(activeStep.sla_due_at)}` : '已结束'}
                          </span>
                        </td>
                        <td>
                          <span>{item.requested_by === identity.user_id ? '我' : item.requested_by}</span>
                          <span className="cell-sub">{dateTimeText(item.requested_at)}</span>
                        </td>
                        <td>
                          <span className={item.status === 'expired' ? 'danger-text' : ''}>{dateTimeText(item.expires_at)}</span>
                          <span className="cell-sub">整体 7 天</span>
                        </td>
                        <td><Badge tone={statusTone(item.status)}>{APPROVAL_STATUS_LABELS[item.status] || item.status}</Badge></td>
                        <td><ChevronRight size={16} className="muted" /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {!data?.items.length ? (
              <EmptyState title="没有匹配的审批单" description="从商机详情发起 R4、R6 或撞单审批后，会由 Temporal 接管流程。" icon={<ShieldCheck size={22} />} />
            ) : null}
          </>
        )}
      </section>

      <div className="note-bar warn">
        <TimerReset size={13} />
        <span>
          <b>时限规则：</b>每个审批步骤 24 小时，超时 4 小时进入升级提醒，整单 7 天到期。
          过期状态不会自动通过；需由有权限的审批人重新发起或按流程处理。
        </span>
      </div>

      {focus ? (
        <ApprovalDrawer
          id={focus}
          onClose={closeApproval}
          onChanged={() => void load()}
        />
      ) : null}
    </div>
  )
}

function ApprovalDrawer({
  id,
  onClose,
  onChanged,
}: {
  id: string
  onClose: () => void
  onChanged: () => void
}) {
  const { identity } = useSession()
  const { push } = useToast()
  const [approval, setApproval] = useState<Approval | null>(null)
  const [attachments, setAttachments] = useState<Json[]>([])
  const [error, setError] = useState('')
  const [decision, setDecision] = useState<'approve' | 'reject' | 'return' | 'delegate' | null>(null)
  const [assignmentKey, setAssignmentKey] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get<Approval>(`/approvals/${id}`)
      setApproval(data)
      const files = await api.get<{ items: Json[] }>(`/attachments${qs({ object_type: 'approval_request', object_id: id })}`)
      setAttachments(files.items)
    } catch (err) {
      setError(errorText(err))
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  const activeStep = approval?.steps.find((step) => step.status === 'active')
  const isParallelStep = activeStep?.mode === 'parallel_all' || activeStep?.mode === 'parallel_any'
  const myAssignments = useMemo(() => {
    if (!activeStep || !isParallelStep || approval?.status !== 'running') return []
    return (activeStep.assignments || []).filter(
      (assignment) =>
        assignment.status === 'active' &&
        (identity.is_admin ||
          (assignment.approver_id
            ? assignment.approver_id === identity.user_id
            : identity.sales_role === assignment.approver_role || identity.role_code === assignment.approver_role)),
    )
  }, [activeStep, approval?.status, identity.is_admin, identity.role_code, identity.sales_role, isParallelStep])

  useEffect(() => {
    if (!myAssignments.length) {
      setAssignmentKey(null)
      return
    }
    if (!assignmentKey || !myAssignments.some((assignment) => assignment.assignment_key === assignmentKey)) {
      setAssignmentKey(myAssignments[0].assignment_key)
    }
  }, [assignmentKey, myAssignments])

  const canDecide =
    approval?.status === 'running' &&
    activeStep &&
    (isParallelStep
      ? myAssignments.length > 0
      : identity.is_admin ||
        (activeStep.approver_id
          ? activeStep.approver_id === identity.user_id
          : identity.sales_role === activeStep.approver_role || identity.role_code === activeStep.approver_role))
  const canCancel = approval && ['pending_start', 'running'].includes(approval.status) && (identity.is_admin || approval.requested_by === identity.user_id)

  async function cancel() {
    if (!approval) return
    try {
      await api.post(`/approvals/${approval.id}/cancel`, { reason: '发起人在审批中心取消' })
      push('取消信号已提交', 'success')
      await load()
      onChanged()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function retry() {
    if (!approval) return
    try {
      await api.post(`/approvals/${approval.id}/retry`)
      push('已触发重试', 'success')
      await load()
      onChanged()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function upload(file: File) {
    if (!approval) return
    const form = new FormData()
    form.set('object_type', 'approval_request')
    form.set('object_id', approval.id)
    form.set('file', file)
    try {
      await api.upload('/attachments', form)
      push('审批附件已上传', 'success')
      await load()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  return (
    <Drawer
      open
      wide
      onClose={onClose}
      title={approval ? approval.request_no : '审批详情'}
      subtitle={approval ? `${GATE_LABELS[approval.gate_code] || approval.gate_code} · ${APPROVAL_STATUS_LABELS[approval.status] || approval.status}` : null}
      footer={
        approval ? (
          <div className="drawer-actions">
            <span className="muted">整体过期 {dateTimeText(approval.expires_at)}</span>
            <div>
              {canCancel ? (
                <button type="button" className="button ghost small" onClick={() => void cancel()}>
                  <X size={15} /> 取消审批
                </button>
              ) : null}
              {['pending_start', 'failed'].includes(approval.status) ? (
                <button type="button" className="button ghost small" onClick={() => void retry()}>
                  <RefreshCw size={15} /> 重试启动
                </button>
              ) : null}
              {isParallelStep && myAssignments.length > 1 ? (
                <select
                  className="assignment-select"
                  value={assignmentKey || ''}
                  onChange={(event) => setAssignmentKey(event.target.value)}
                  aria-label="选择审批席位"
                >
                  {myAssignments.map((assignment) => (
                    <option key={assignment.assignment_key} value={assignment.assignment_key}>
                      {ROLE_LABELS[assignment.approver_role || ''] || assignment.approver_role || assignment.assignment_key}
                    </option>
                  ))}
                </select>
              ) : null}
              {canDecide ? (
                <>
                  <button type="button" className="button ghost small" onClick={() => setDecision('return')}>退回</button>
                  <button type="button" className="button ghost small" onClick={() => setDecision('reject')}>驳回</button>
                  <button type="button" className="button ghost small" onClick={() => setDecision('delegate')}>
                    <UserRoundCheck size={15} /> 转办
                  </button>
                  <button type="button" className="button primary small" onClick={() => setDecision('approve')}>
                    <Check size={15} /> 通过
                  </button>
                </>
              ) : null}
            </div>
          </div>
        ) : null
      }
    >
      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}
      {!approval ? (
        <Spinner />
      ) : (
        <div className="detail-stack">
          <section className="detail-hero">
            <div>
              <span className="eyebrow">申请原因</span>
              <h3>{approval.reason}</h3>
              <span className="muted">
                {approval.opportunity_name || approval.opportunity?.name || approval.opportunity_id} · 申请人 {approval.requested_by === identity.user_id ? '我' : approval.requested_by}
              </span>
            </div>
            <div className="detail-kpis">
              <div><span>状态</span><strong>{APPROVAL_STATUS_LABELS[approval.status] || approval.status}</strong><small>{approval.completed_at ? '流程已完成' : `当前第 ${approval.current_step} 步`}</small></div>
              <div><span>金额</span><strong>{money(approval.payload?.amount, true)}</strong><small>阶段 {approval.payload?.stage}</small></div>
              <div><span>整体时限</span><strong>{approval.completed_at ? '已结束' : relativeDue(approval.expires_at)}</strong><small>{approval.completed_at ? dateTimeText(approval.completed_at) : '过期不自动通过'}</small></div>
            </div>
          </section>

          <section className="detail-card">
            <div className="section-head">
              <div>
                <h3>审批步骤</h3>
                <p className="muted">步骤按顺序激活；会签需全部通过，或签任一通过；SLA 超时升级 4 小时，仍未处理则过期。</p>
              </div>
            </div>
            <div className="approval-steps">
              {approval.steps.map((step) => (
                <div className={`approval-step ${step.status}`} key={step.step_no}>
                  <div className="step-number">{step.step_no}</div>
                  <div className="step-main">
                    <strong>
                      {ROLE_LABELS[step.approver_role] || step.approver_role}
                      {step.mode === 'parallel_all' ? ' · 会签' : step.mode === 'parallel_any' ? ' · 或签' : ''}
                    </strong>
                    {step.mode === 'parallel_all' || step.mode === 'parallel_any' ? (
                      <div className="approval-assignments">
                        {(step.assignments || []).map((assignment) => (
                          <span className={`assignment-chip ${assignment.status}`} key={assignment.assignment_key}>
                            {assignment.approver_id || ROLE_LABELS[assignment.approver_role || ''] || assignment.approver_role || assignment.assignment_key}
                            {' · '}
                            {STEP_STATUS_LABELS[assignment.status] || assignment.status}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span>
                        {step.approver_id ? `指定：${step.approver_id}` : '角色池'} · {STEP_STATUS_LABELS[step.status] || step.status}
                      </span>
                    )}
                    {step.comment ? <p>{step.comment}</p> : null}
                  </div>
                  <div className="step-time">
                    {step.status === 'active' || step.status === 'pending' ? (
                      <>
                        <span className={step.status === 'active' ? 'amber-text' : ''}>{relativeDue(step.sla_due_at)}</span>
                        <small>{dateTimeText(step.sla_due_at)}</small>
                      </>
                    ) : (
                      <>
                        <span>{STEP_STATUS_LABELS[step.status] || step.status}</span>
                        <small>{dateTimeText(step.decided_at)}</small>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="two-column">
            <section className="detail-card">
              <h3>证据</h3>
              <pre className="code-block">{JSON.stringify(approval.evidence || {}, null, 2)}</pre>
            </section>
            <section className="detail-card">
              <h3>操作记录</h3>
              <div className="mini-list">
                {(approval.actions || []).map((action, index) => (
                  <div className="mini-row" key={`${action.created_at}-${index}`}>
                    <Badge tone={action.action === 'reject' ? 'red' : action.action === 'delegate' ? 'amber' : 'green'}>
                      {ACTION_LABELS[action.action] || action.action}
                    </Badge>
                    <span>{action.actor_id === identity.user_id ? '我' : action.actor_id}</span>
                    <small>{dateTimeText(action.created_at)}</small>
                  </div>
                ))}
                {!approval.actions?.length ? <p className="muted">暂无操作记录。</p> : null}
              </div>
            </section>
          </div>

          <section className="detail-card">
            <div className="section-head">
              <div>
                <h3>附件</h3>
                <p className="muted">审批证据附件保存在 MinIO，下载仍走销售服务鉴权。</p>
              </div>
              <label className="button ghost small">
                <FileText size={15} /> 上传
                <input
                  type="file"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void upload(file)
                    event.target.value = ''
                  }}
                />
              </label>
            </div>
            <div className="file-list">
              {attachments.map((file) => (
                <div className="file-row" key={file.id}>
                  <FileText size={18} />
                  <div>
                    <strong>{file.file_name}</strong>
                    <span>{Math.ceil((file.size_bytes || 0) / 1024)} KB · {dateTimeText(file.created_at)}</span>
                  </div>
                  <button type="button" className="button ghost tiny" onClick={() => void api.download(`/attachments/${file.id}/download`, file.file_name)}>
                    下载
                  </button>
                </div>
              ))}
              {!attachments.length ? <p className="muted">没有附件。</p> : null}
            </div>
          </section>

          {approval.opportunity ? (
            <Link className="text-link" to={`/opportunities?focus=${approval.opportunity.id}`}>
              打开关联商机 <ArrowRight size={14} />
            </Link>
          ) : null}
        </div>
      )}
      {approval && decision ? (
        <DecisionModal
          approval={approval}
          action={decision}
          assignmentKey={assignmentKey}
          onClose={() => setDecision(null)}
          onDone={async () => {
            setDecision(null)
            await load()
            onChanged()
          }}
        />
      ) : null}
    </Drawer>
  )
}

function DecisionModal({
  approval,
  action,
  assignmentKey,
  onClose,
  onDone,
}: {
  approval: Approval
  action: 'approve' | 'reject' | 'return' | 'delegate'
  assignmentKey: string | null
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const { push } = useToast()
  const [comment, setComment] = useState('')
  const [delegateTo, setDelegateTo] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const activeStep = approval.steps.find((step) => step.status === 'active')

  async function submit() {
    setError('')
    setSaving(true)
    try {
      const idempotencyKey = `${action}-${approval.id}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      await api.post(`/approvals/${approval.id}/decision`, {
        action,
        comment: comment || undefined,
        delegate_to: action === 'delegate' ? delegateTo : undefined,
        assignment_key: assignmentKey || undefined,
        idempotency_key: idempotencyKey,
      })
      push('决策已提交 Temporal', 'success')
      await onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  const title = action === 'approve' ? '通过审批' : action === 'reject' ? '驳回审批' : action === 'return' ? '退回审批' : '转办审批'
  const valid = action === 'approve' || (action === 'delegate' ? delegateTo.trim().length > 0 : comment.trim().length > 0)

  return (
    <div className="nested-modal">
      <div className="modal nested" role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭"><X size={18} /></button>
        </header>
        <div className="modal-body">
          {error ? <ErrorBanner message={error} /> : null}
          <div className="form-stack">
            <div className="rule-note">
              <CircleAlert size={15} />
              {action === 'delegate' ? (
                <span>转办后第 {activeStep?.step_no} 步会重新激活，时钟重置为 24 小时。</span>
              ) : action === 'approve' ? (
                <span>通过只解除闸门；不会自动推进商机阶段。</span>
              ) : (
                <span>{action === 'reject' ? '驳回为终态，需要填写意见。' : '退回为终态，需要填写意见。'}</span>
              )}
            </div>
            {action === 'delegate' ? (
              <Field label="接收人用户 ID" required hint="接收人必须能从 EAI 身份中解析；当前版本不做本地账号选择。">
                <input value={delegateTo} onChange={(event) => setDelegateTo(event.target.value)} placeholder="例如：demo-manager" />
              </Field>
            ) : null}
            <Field label={action === 'approve' ? '审批意见' : '意见'} required={action !== 'approve'}>
              <textarea rows={4} value={comment} onChange={(event) => setComment(event.target.value)} />
            </Field>
          </div>
        </div>
        <footer className="modal-foot">
          <div className="modal-actions">
            <button type="button" className="button ghost" onClick={onClose}>取消</button>
            <button type="button" className={`button ${action === 'reject' ? 'danger' : 'primary'}`} onClick={() => void submit()} disabled={!valid || saving}>
              {saving ? '提交中…' : `确认${title.replace('审批', '')}`}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
