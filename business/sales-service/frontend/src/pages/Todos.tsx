import {
  Check,
  CheckCheck,
  ChevronRight,
  Clock3,
  Inbox,
  ListChecks,
  Play,
  Search,
  ShieldCheck,
  UserRoundCheck,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useSession } from '../App'
import { api, qs, type Approval, type Paged, type Todo, type TodoStats } from '../api'
import {
  Badge,
  Drawer,
  EmptyState,
  ErrorBanner,
  Field,
  Modal,
  Spinner,
  severityTone,
  statusTone,
  useToast,
} from '../components/ui'
import { APPROVAL_STATUS_LABELS, OBJECT_TYPE_LABELS, ROLE_LABELS, RULE_LABELS, SEVERITY_LABELS, STEP_STATUS_LABELS, TODO_STATUS_LABELS, TODO_TYPES, dateTimeText, errorText, relativeDue } from '../lib/format'

const TYPES = ['approval', 'data_fix', 'arbitration', 'rule_event']
const SEVERITIES = ['blocker', 'high', 'medium', 'low']

export default function Todos() {
  const { identity } = useSession()
  const { push } = useToast()
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => Object.fromEntries(params.entries()), [params])
  const [data, setData] = useState<(Paged<Todo> & { stats: TodoStats }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [focus, setFocus] = useState<string | null>(params.get('focus'))
  const [resolveTarget, setResolveTarget] = useState<Todo | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.get<Paged<Todo> & { stats: TodoStats }>(`/todos${qs({ ...filters, limit: 50 })}`)
      setData(result)
      setSelected((current) => current.filter((id) => result.items.some((item) => item.id === id)))
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

  function openTodo(id: string) {
    setFocus(id)
    const next = new URLSearchParams(params)
    next.set('focus', id)
    setParams(next, { replace: true })
  }

  function closeTodo() {
    setFocus(null)
    const next = new URLSearchParams(params)
    next.delete('focus')
    setParams(next, { replace: true })
  }

  async function quickAction(todo: Todo, action: 'start' | 'resolve' | 'cancel') {
    if (action === 'resolve') {
      setResolveTarget(todo)
      return
    }
    try {
      await api.post(`/todos/${todo.id}/${action}`, action === 'cancel' ? { reason: '在待办列表中取消' } : undefined)
      push(action === 'start' ? '已开始处理' : '已取消', 'success')
      await load()
      if (focus === todo.id) closeTodo()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function batchResolve() {
    if (!selected.length) return
    try {
      const result = await api.post<{ processed: number }>('/todos/batch', {
        todo_ids: selected,
        action: 'resolve',
        resolution: '批量处理完成',
      })
      push(`已处理 ${result.processed} 项待办`, 'success')
      setSelected([])
      await load()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function assignToMe(todo: Todo) {
    try {
      await api.patch(`/todos/${todo.id}`, { assignee_id: identity.user_id })
      push('已分派给我', 'success')
      await load()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  const stats = data?.stats

  return (
    <div className="stack">
      <section className="todo-stat-grid">
        <div className="todo-stat"><span>未结</span><strong>{stats?.open ?? '—'}</strong></div>
        <div className={`todo-stat ${stats?.overdue ? 'warn' : ''}`}><span>已超时</span><strong>{stats?.overdue ?? '—'}</strong></div>
        <div className={`todo-stat ${stats?.blocker ? 'danger' : ''}`}><span>阻断</span><strong>{stats?.blocker ?? '—'}</strong></div>
        <div className="todo-stat"><span>审批</span><strong>{stats?.approval ?? '—'}</strong></div>
        <div className="todo-stat"><span>数据补全</span><strong>{stats?.data_fix ?? '—'}</strong></div>
        <div className="todo-stat"><span>撞单仲裁</span><strong>{stats?.arbitration ?? '—'}</strong></div>
      </section>

      <section className="panel filter-panel">
        <div className="filter-row">
          <label className="search-box">
            <Search size={17} />
            <input value={filters.keyword || ''} onChange={(event) => setFilter('keyword', event.target.value)} placeholder="搜索待办标题、编号" />
          </label>
          <select value={filters.type || ''} onChange={(event) => setFilter('type', event.target.value)}>
            <option value="">全部类型</option>
            {TYPES.map((type) => <option key={type} value={type}>{TODO_TYPES[type]}</option>)}
          </select>
          <select value={filters.status || ''} onChange={(event) => setFilter('status', event.target.value)}>
            <option value="">全部状态</option>
            <option value="open">待处理</option>
            <option value="in_progress">处理中</option>
            <option value="resolved">已解决</option>
            <option value="cancelled">已取消</option>
          </select>
          <select value={filters.severity || ''} onChange={(event) => setFilter('severity', event.target.value)}>
            <option value="">全部优先级</option>
            {SEVERITIES.map((severity) => <option key={severity} value={severity}>{SEVERITY_LABELS[severity]}</option>)}
          </select>
          <button
            type="button"
            className={`toggle-chip ${filters.overdue === 'true' ? 'on' : ''}`}
            onClick={() => setFilter('overdue', filters.overdue === 'true' ? '' : 'true')}
          >
            <Clock3 size={15} /> 仅超时
          </button>
          {selected.length ? (
            <button type="button" className="button primary" onClick={() => void batchResolve()}>
              <CheckCheck size={16} /> 批量解决 {selected.length}
            </button>
          ) : null}
        </div>
        <div className="filter-summary">
          <span><Inbox size={14} /> 共 {data?.total ?? 0} 项</span>
          <span className="muted">审批待办只能到审批中心处理；这里批量操作会自动跳过。</span>
        </div>
      </section>

      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}

      <section className="panel table-panel">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table todo-table">
                <thead>
                  <tr>
                    <th className="check-col">
                      <input
                        type="checkbox"
                        checked={!!data?.items.length && selected.length === data.items.filter((item) => item.type !== 'approval').length}
                        onChange={(event) => setSelected(event.target.checked ? data?.items.filter((item) => item.type !== 'approval').map((item) => item.id) || [] : [])}
                        aria-label="全选"
                      />
                    </th>
                    <th>待办</th>
                    <th>类型 / 优先级</th>
                    <th>对象</th>
                    <th>处理人</th>
                    <th>时限</th>
                    <th>状态</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((todo) => (
                    <tr
                      key={todo.id}
                      className={`${todo.severity === 'blocker' ? 'row-blocker' : ''} ${todo.is_overdue ? 'row-overdue' : ''}`}
                      onClick={() => openTodo(todo.id)}
                    >
                      <td className="check-col" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected.includes(todo.id)}
                          disabled={todo.type === 'approval'}
                          onChange={(event) => {
                            setSelected((current) =>
                              event.target.checked ? [...current, todo.id] : current.filter((id) => id !== todo.id),
                            )
                          }}
                          aria-label="选择待办"
                        />
                      </td>
                      <td>
                        <div className="primary-cell">
                          <strong>{todo.title}</strong>
                          <span>{todo.todo_no} · {todo.description || '无补充说明'}</span>
                        </div>
                      </td>
                      <td>
                        <div className="inline-badges">
                          <Badge tone={todo.type === 'approval' ? 'violet' : 'neutral'}>{TODO_TYPES[todo.type] || todo.type}</Badge>
                          <Badge tone={severityTone(todo.severity)}>{SEVERITY_LABELS[todo.severity] || todo.severity}</Badge>
                        </div>
                      </td>
                      <td>
                        <span>{todo.opportunity_name || OBJECT_TYPE_LABELS[todo.object_type] || todo.object_type}</span>
                        <span className="cell-sub">{todo.source_rule ? RULE_LABELS[todo.source_rule] || todo.source_rule : '手工创建'}</span>
                      </td>
                      <td>
                        <span>{todo.assignee_name || (todo.assignee_role ? ROLE_LABELS[todo.assignee_role] || todo.assignee_role : '角色池')}</span>
                        <span className="cell-sub">{todo.assignee_id || '未指定个人'}</span>
                      </td>
                      <td>
                        <span className={todo.is_overdue ? 'danger-text' : ''}>{relativeDue(todo.due_at)}</span>
                        <span className="cell-sub">{dateTimeText(todo.due_at)}</span>
                      </td>
                      <td><Badge tone={statusTone(todo.status)}>{TODO_STATUS_LABELS[todo.status] || todo.status}</Badge></td>
                      <td onClick={(event) => event.stopPropagation()}>
                        <div className="row-actions">
                          {todo.type === 'approval' ? (
                            <Link className="button ghost tiny" to={`/approvals?focus=${todo.object_id}`}>
                              <ShieldCheck size={14} /> 审批
                            </Link>
                          ) : (
                            <>
                              {todo.status === 'open' ? (
                                <button type="button" className="icon-button" onClick={() => void quickAction(todo, 'start')} title="开始处理">
                                  <Play size={15} />
                                </button>
                              ) : null}
                              <button type="button" className="icon-button" onClick={() => void quickAction(todo, 'resolve')} title="解决">
                                <Check size={15} />
                              </button>
                              {!todo.assignee_id ? (
                                <button type="button" className="icon-button" onClick={() => void assignToMe(todo)} title="分派给我">
                                  <UserRoundCheck size={15} />
                                </button>
                              ) : null}
                              <button type="button" className="icon-button danger" onClick={() => void quickAction(todo, 'cancel')} title="取消">
                                <X size={15} />
                              </button>
                            </>
                          )}
                          <ChevronRight size={15} className="muted" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data?.items.length ? (
              <EmptyState title="当前没有待办" description="规则引擎会在阶段超期、数据缺失、撞单或审批时生成待办。" icon={<ListChecks size={22} />} />
            ) : null}
          </>
        )}
      </section>

      <div className="two-column">
        <section className="panel">
          <header className="panel-head">
            <div>
              <span className="eyebrow">升级与 SLA</span>
              <h3>超时处理路径</h3>
            </div>
            <span className="tag danger">阻断 · 不可跳过</span>
          </header>
          <div className="pad">
            <div className="esc-step done">
              <span className="esc-dot"><Check size={10} /></span>
              <div className="esc-main">
                <b>责任人处置</b>
                <span>SLA 内完成 · 当前 {stats?.open ?? 0} 项在办</span>
              </div>
              <Badge tone="green">正常</Badge>
            </div>
            <div className={`esc-step ${stats?.overdue ? 'on' : ''}`}>
              <span className="esc-dot">2</span>
              <div className="esc-main">
                <b>大区 / 服务区经理</b>
                <span>超时后升级 · 当前 {stats?.overdue ?? 0} 项已超时</span>
              </div>
              <Badge tone={stats?.overdue ? 'amber' : 'neutral'}>{stats?.overdue ? '升级中' : '待触发'}</Badge>
            </div>
            <div className="esc-step">
              <span className="esc-dot">3</span>
              <div className="esc-main">
                <b>销售总监 / 营销中心</b>
                <span>审批 SLA 每步 24 小时 · 4 小时升级窗口</span>
              </div>
              <Badge tone="neutral">按规则触发</Badge>
            </div>
            <div className="esc-step">
              <span className="esc-dot">4</span>
              <div className="esc-main">
                <b>经营例会督办</b>
                <span>整体审批 7 天到期，过期不自动通过</span>
              </div>
              <Badge tone="neutral">兜底</Badge>
            </div>
          </div>
        </section>

        <section className="panel">
          <header className="panel-head">
            <div>
              <span className="eyebrow">当前队列</span>
              <h3>待办结构</h3>
            </div>
            <span className="tag">实时统计</span>
          </header>
          <div className="pad">
            <div className="mini-row"><span>规则事件</span><div /><strong>{stats?.rule_event ?? 0}</strong></div>
            <div className="mini-row"><span>审批待办</span><div /><strong>{stats?.approval ?? 0}</strong></div>
            <div className="mini-row"><span>数据补全</span><div /><strong>{stats?.data_fix ?? 0}</strong></div>
            <div className="mini-row"><span>撞单仲裁</span><div /><strong>{stats?.arbitration ?? 0}</strong></div>
            <div className="note-bar">
              <ListChecks size={13} />
              <span>规则事件与审批进入同一队列，但审批保留原单据审签链；批量操作会自动跳过审批待办。</span>
            </div>
          </div>
        </section>
      </div>

      <div className="note-bar">
        <ShieldCheck size={13} />
        <span>
          <b>处置原则：</b>阻断项必须人工关闭；审批待办只能到审批中心决策；超时只升级提醒，不代替责任人处理。
        </span>
      </div>

      {focus ? (
        <TodoDrawer
          id={focus}
          onClose={closeTodo}
          onChanged={() => void load()}
          onResolve={(todo) => setResolveTarget(todo)}
        />
      ) : null}

      <ResolveTodoModal
        todo={resolveTarget}
        onClose={() => setResolveTarget(null)}
        onDone={async () => {
          setResolveTarget(null)
          push('待办已解决', 'success')
          await load()
          if (focus) closeTodo()
        }}
      />
    </div>
  )
}

function TodoDrawer({
  id,
  onClose,
  onChanged,
  onResolve,
}: {
  id: string
  onClose: () => void
  onChanged: () => void
  onResolve: (todo: Todo) => void
}) {
  const { identity } = useSession()
  const { push } = useToast()
  const [todo, setTodo] = useState<Todo | null>(null)
  const [approval, setApproval] = useState<Approval | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await api.get<Todo>(`/todos/${id}`)
      setTodo(data)
      if (data.approval?.id) {
        const request = await api.get<Approval>(`/approvals/${data.approval.id}`)
        setApproval(request)
      }
    } catch (err) {
      setError(errorText(err))
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  async function start() {
    if (!todo) return
    try {
      await api.post(`/todos/${todo.id}/start`)
      push('已开始处理', 'success')
      await load()
      onChanged()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function assignToMe() {
    if (!todo) return
    try {
      await api.patch(`/todos/${todo.id}`, { assignee_id: identity.user_id })
      push('已分派给我', 'success')
      await load()
      onChanged()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      title={todo?.title || '待办详情'}
      subtitle={todo ? `${todo.todo_no} · ${TODO_TYPES[todo.type] || todo.type}` : null}
      footer={
        todo ? (
          <div className="drawer-actions">
            <span className="muted">{relativeDue(todo.due_at)}</span>
            <div>
              {todo.type === 'approval' && approval ? (
                <Link className="button primary small" to={`/approvals?focus=${approval.id}`}>
                  去审批中心
                </Link>
              ) : (
                <>
                  {todo.status === 'open' ? (
                    <button type="button" className="button ghost small" onClick={() => void start()}>
                      <Play size={15} /> 开始处理
                    </button>
                  ) : null}
                  {!todo.assignee_id ? (
                    <button type="button" className="button ghost small" onClick={() => void assignToMe()}>
                      <UserRoundCheck size={15} /> 分派给我
                    </button>
                  ) : null}
                  <button type="button" className="button primary small" onClick={() => onResolve(todo)}>
                    <Check size={15} /> 解决
                  </button>
                </>
              )}
            </div>
          </div>
        ) : null
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      {!todo ? (
        <Spinner />
      ) : (
        <div className="detail-stack">
          <section className="detail-hero">
            <div>
              <span className="eyebrow">待办说明</span>
              <h3>{todo.description || '无补充说明'}</h3>
              <span className="muted">{todo.opportunity_name || OBJECT_TYPE_LABELS[todo.object_type] || todo.object_type} · 来源 {todo.source_rule ? RULE_LABELS[todo.source_rule] || todo.source_rule : '手工创建'}</span>
            </div>
            <div className="detail-kpis">
              <div><span>优先级</span><strong>{SEVERITY_LABELS[todo.severity] || todo.severity}</strong><small>升级次数 {todo.escalation_level}</small></div>
              <div><span>时限</span><strong className={todo.is_overdue ? 'danger-text' : ''}>{relativeDue(todo.due_at)}</strong><small>{dateTimeText(todo.due_at)}</small></div>
              <div><span>状态</span><strong>{TODO_STATUS_LABELS[todo.status] || todo.status}</strong><small>{todo.assignee_name || todo.assignee_role || '未分派'}</small></div>
            </div>
          </section>

          {approval ? (
            <section className="detail-card">
              <div className="section-head">
                <div>
                  <h3>审批进度</h3>
                  <p className="muted">{approval.request_no} · {approval.gate_code} · {APPROVAL_STATUS_LABELS[approval.status] || approval.status}</p>
                </div>
                <Link className="text-link" to={`/approvals?focus=${approval.id}`}>打开审批中心</Link>
              </div>
              <div className="step-inline">
                {approval.steps.map((step) => (
                  <span key={step.step_no} className={`step-chip ${step.status}`}>
                    {step.step_no}. {ROLE_LABELS[step.approver_role] || step.approver_role} · {STEP_STATUS_LABELS[step.status] || step.status}
                  </span>
                ))}
              </div>
              <div className="fact-list">
                <div><dt>申请原因</dt><dd>{approval.reason}</dd></div>
                <div><dt>申请人</dt><dd>{approval.requested_by === identity.user_id ? '我' : approval.requested_by}</dd></div>
                <div><dt>超时时间</dt><dd>{dateTimeText(approval.expires_at)}</dd></div>
              </div>
            </section>
          ) : null}

          <section className="detail-card">
            <h3>对象</h3>
            <dl className="fact-list">
              <div><dt>对象类型</dt><dd>{OBJECT_TYPE_LABELS[todo.object_type] || todo.object_type}</dd></div>
              <div><dt>对象编号</dt><dd>{todo.object_id}</dd></div>
              <div><dt>创建时间</dt><dd>{dateTimeText(todo.created_at)}</dd></div>
              <div><dt>更新时间</dt><dd>{dateTimeText(todo.updated_at)}</dd></div>
            </dl>
          </section>
        </div>
      )}
    </Drawer>
  )
}

function ResolveTodoModal({
  todo,
  onClose,
  onDone,
}: {
  todo: Todo | null
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const [resolution, setResolution] = useState('已补充所需信息并确认')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (!todo) return
    setError('')
    setSaving(true)
    try {
      await api.post(`/todos/${todo.id}/resolve`, { resolution })
      await onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={!!todo}
      title="解决待办"
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>取消</button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={!resolution.trim() || saving}>
            确认解决
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <p className="muted">{todo?.title}</p>
        <Field label="处理结论" required>
          <textarea rows={4} value={resolution} onChange={(event) => setResolution(event.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}
