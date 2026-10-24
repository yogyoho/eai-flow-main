import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FileText,
  Filter,
  GitBranch,
  History,
  Link2,
  Paperclip,
  PencilLine,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useSession } from '../App'
import { api, qs, type Gate, type Json, type MasterOptions, type Opportunity, type Paged } from '../api'
import {
  Badge,
  Drawer,
  EmptyState,
  ErrorBanner,
  Field,
  Modal,
  Spinner,
  statusTone,
  useToast,
} from '../components/ui'
import {
  GATE_LABELS,
  ROLE_LABELS,
  STAGES,
  TODO_TYPES,
  dateText,
  dateTimeText,
  errorText,
  money,
  nextStage,
  percent,
  relativeDue,
  stageLabel,
} from '../lib/format'

const REGIONS = [
  { code: 'NORTH', label: '北方大区' },
  { code: 'NORTHWEST', label: '西北大区' },
  { code: 'DEFAULT', label: '未分配区域' },
]

export default function Opportunities() {
  const { identity, summary } = useSession()
  const { push } = useToast()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<Paged<Opportunity> | null>(null)
  const [options, setOptions] = useState<MasterOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<string | null>(params.get('focus'))
  const [createOpen, setCreateOpen] = useState(params.get('new') === '1')
  const filters = useMemo(() => Object.fromEntries(params.entries()), [params])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.get<Paged<Opportunity>>(`/opportunities${qs({ ...filters, limit: 20 })}`)
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
    api.get<MasterOptions>('/master-data/options').then(setOptions).catch(() => undefined)
  }, [])

  useEffect(() => {
    const value = params.get('focus')
    if (value) setFocus(value)
  }, [params])

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('skip')
    setParams(next, { replace: true })
  }

  function openOpportunity(id: string) {
    setFocus(id)
    const next = new URLSearchParams(params)
    next.set('focus', id)
    setParams(next, { replace: true })
  }

  function closeDrawer() {
    setFocus(null)
    const next = new URLSearchParams(params)
    next.delete('focus')
    setParams(next, { replace: true })
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / 20)) : 1
  const page = Math.floor(Number(filters.skip || 0) / 20) + 1

  return (
    <div className="stack">
      <section className="metric-grid">
        <div className="metric-card accent">
          <span>在途商机</span>
          <strong>{summary.metrics.active_opportunities}</strong>
          <small>个活跃商机 · 覆盖当前数据范围</small>
        </div>
        <div className="metric-card">
          <span>加权预测</span>
          <strong>{money(summary.metrics.weighted_forecast, true)}</strong>
          <small>在管 {money(summary.metrics.active_amount, true)}</small>
        </div>
        <div className="metric-card">
          <span>有效胜率</span>
          <strong>{percent(summary.metrics.win_rate)}</strong>
          <small>已结束商机口径</small>
        </div>
        <div className={`metric-card ${summary.metrics.overdue_opportunities ? 'tone-amber' : ''}`}>
          <span>阶段超期</span>
          <strong>{summary.metrics.overdue_opportunities}</strong>
          <small>超阶段上限 · 自动降权</small>
        </div>
        <div className="metric-card">
          <span>当前筛选</span>
          <strong>{data?.total ?? '—'}</strong>
          <small>个商机 · 筛选结果</small>
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">C1 · 九段状态机</span>
            <h3>阶段分布</h3>
          </div>
          <span className="tag">点击阶段筛选</span>
        </header>
        <div className="funnel">
          {summary.funnel.map((item) => (
            <button
              type="button"
              className={`funnel-step ${item.overdue ? 'has-overdue' : ''} ${
                filters.stage === item.stage ? 'is-active' : ''
              }`}
              key={item.stage}
              onClick={() => setFilter('stage', filters.stage === item.stage ? '' : item.stage)}
            >
              <div className="funnel-code">{item.stage}</div>
              <div className="funnel-body">
                <span>{item.label}</span>
                <strong>{item.count}</strong>
                <small>{money(item.amount, true)} · 加权 {money(item.weighted_amount, true)}</small>
                <div className="funnel-bar">
                  <i
                    style={{
                      width: `${Math.max(
                        6,
                        Math.round((item.amount / Math.max(...summary.funnel.map((row) => row.amount), 1)) * 100),
                      )}%`,
                    }}
                  />
                  {item.overdue ? <em>{item.overdue} 超期</em> : null}
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="panel filter-panel">
        <div className="filter-row">
          <label className="search-box">
            <Search size={17} />
            <input
              value={filters.keyword || ''}
              onChange={(event) => setFilter('keyword', event.target.value)}
              placeholder="搜索商机编号、名称、客户"
            />
          </label>
          <select value={filters.stage || ''} onChange={(event) => setFilter('stage', event.target.value)}>
            <option value="">全部阶段</option>
            {STAGES.map((stage) => (
              <option key={stage.code} value={stage.code}>
                {stage.code} · {stage.label}
              </option>
            ))}
          </select>
          <select value={filters.region_code || ''} onChange={(event) => setFilter('region_code', event.target.value)}>
            <option value="">全部区域</option>
            {REGIONS.map((region) => (
              <option key={region.code} value={region.code}>
                {region.label}
              </option>
            ))}
          </select>
          <select value={filters.sort || 'updated_desc'} onChange={(event) => setFilter('sort', event.target.value)}>
            <option value="updated_desc">最近更新</option>
            <option value="amount_desc">金额从高到低</option>
            <option value="close_asc">预计关闭最近</option>
            <option value="stage_asc">阶段从早到晚</option>
          </select>
          <button
            type="button"
            className={`toggle-chip ${filters.overdue === '1' ? 'on' : ''}`}
            onClick={() => setFilter('overdue', filters.overdue === '1' ? '' : '1')}
          >
            <CircleAlert size={15} /> 仅超期
          </button>
          <button
            type="button"
            className={`toggle-chip ${filters.duplicates_only === 'true' ? 'on' : ''}`}
            onClick={() => setFilter('duplicates_only', filters.duplicates_only === 'true' ? '' : 'true')}
          >
            <GitBranch size={15} /> 撞单
          </button>
          <button type="button" className="button primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> 新建商机
          </button>
        </div>
        <div className="filter-summary">
          <span>
            <Filter size={14} /> 共 {data?.total ?? 0} 个商机
          </span>
          <span className="muted">列表金额为含税合同预估额，概率来自规则与人工覆盖。</span>
        </div>
      </section>

      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}

      <section className="panel table-panel">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table opportunity-table">
                <thead>
                  <tr>
                    <th>商机 / 客户</th>
                    <th>阶段</th>
                    <th className="num">金额</th>
                    <th className="num">有效概率</th>
                    <th>负责人 / 区域</th>
                    <th>预计关闭</th>
                    <th>风险</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((opp) => (
                    <tr key={opp.id} className={opp.is_overdue ? 'row-overdue' : ''} onClick={() => openOpportunity(opp.id)}>
                      <td>
                        <div className="primary-cell">
                          <strong>{opp.name}</strong>
                          <span>
                            {opp.opportunity_no} · {opp.customer_name || '未关联客户'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={`stage-pill stage-${opp.stage.toLowerCase()}`}>{opp.stage}</span>
                        <span className="cell-sub">{opp.stage_label}</span>
                      </td>
                      <td className="num">
                        <strong>{money(opp.amount, true)}</strong>
                        <span className="cell-sub">加权 {money(opp.weighted_amount, true)}</span>
                      </td>
                      <td className="num">
                        <strong>{percent(opp.effective_probability)}</strong>
                        <span className="cell-sub">{opp.probability_source === 'manual' ? '人工覆盖' : '规则'}</span>
                      </td>
                      <td>
                        <span>{opp.owner_name || opp.owner_id || '未分配'}</span>
                        <span className="cell-sub">{REGIONS.find((r) => r.code === opp.region_code)?.label || opp.region_code}</span>
                      </td>
                      <td>
                        <span>{dateText(opp.expected_close_date)}</span>
                        <span className={`cell-sub ${opp.is_overdue ? 'danger-text' : ''}`}>
                          {opp.is_overdue ? '阶段停留超期' : relativeDue(opp.stage_due_at)}
                        </span>
                      </td>
                      <td>
                        {opp.is_overdue ? <Badge tone="amber">超期</Badge> : null}
                        {opp.duplicate_of_id ? <Badge tone="red">已合并</Badge> : null}
                        {!opp.is_overdue && !opp.duplicate_of_id ? <span className="muted">—</span> : null}
                      </td>
                      <td>
                        <ChevronRight size={16} className="muted" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data?.items.length ? <EmptyState title="没有匹配的商机" description="调整筛选条件，或从主数据补全客户后新建商机。" /> : null}
            <div className="pager">
              <span>
                第 {page} / {pages} 页
              </span>
              <div>
                <button
                  type="button"
                  className="button ghost small"
                  disabled={page <= 1}
                  onClick={() => setFilter('skip', String(Math.max(0, (page - 2) * 20)))}
                >
                  <ChevronLeft size={15} /> 上一页
                </button>
                <button
                  type="button"
                  className="button ghost small"
                  disabled={page >= pages}
                  onClick={() => setFilter('skip', String(page * 20))}
                >
                  下一页 <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <div className="page-foot">
        <Link2 size={15} />
        <span>商机阶段只能逐级推进；跨阶段推进或回退会被规则拦截，并留下审计记录。</span>
      </div>

      <div className="note-bar">
        <ShieldCheck size={13} />
        <span>
          <b>三道硬闸门：</b>新客户集团投标立项前须有关联示范面（R4）；报价冲突未裁决不得生效（R2）；
          关联方未走专用审批流不得生效（R6）。超期降权只影响预测，不改变阶段事实。
        </span>
      </div>

      {focus ? (
        <OpportunityDrawer
          id={focus}
          onClose={closeDrawer}
          onChanged={() => {
            void load()
            push('商机已更新', 'success')
          }}
        />
      ) : null}

      <CreateOpportunityModal
        open={createOpen}
        options={options}
        identityRegion={identity.region_code}
        ownerId={identity.user_id}
        onClose={() => {
          setCreateOpen(false)
          const next = new URLSearchParams(params)
          next.delete('new')
          setParams(next, { replace: true })
        }}
        onCreated={(created) => {
          setCreateOpen(false)
          push('商机已创建', 'success')
          void load()
          openOpportunity(created.id)
        }}
      />
    </div>
  )
}

function OpportunityDrawer({
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
  const [detail, setDetail] = useState<Opportunity | null>(null)
  const [attachments, setAttachments] = useState<Json[]>([])
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'overview' | 'timeline' | 'approvals' | 'files'>('overview')
  const [modal, setModal] = useState<'' | 'transition' | 'rollback' | 'probability' | 'approval'>('')
  const uploadRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get<Opportunity>(`/opportunities/${id}`)
      setDetail(data)
      const files = await api.get<{ items: Json[] }>(`/attachments${qs({ object_type: 'opportunity', object_id: id })}`)
      setAttachments(files.items)
    } catch (err) {
      setError(errorText(err))
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  async function upload(file: File) {
    const form = new FormData()
    form.set('object_type', 'opportunity')
    form.set('object_id', id)
    form.set('file', file)
    try {
      await api.upload('/attachments', form)
      push('附件已上传到 MinIO', 'success')
      await load()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function removeAttachment(attachmentId: string) {
    if (!window.confirm('删除该附件？对象存储中的文件也会被删除。')) return
    try {
      await api.del(`/attachments/${attachmentId}`)
      push('附件已删除', 'success')
      await load()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  async function resolveDuplicate(caseId: string, resolution: string) {
    try {
      await api.post(`/opportunities/duplicates/${caseId}/resolve`, {
        resolution,
        reason: resolution === 'merge' ? '以当前商机为主记录合并' : '经大区确认处理',
        primary_opportunity_id: resolution === 'merge' ? id : undefined,
      })
      push('撞单已处理', 'success')
      await load()
      onChanged()
    } catch (err) {
      push(errorText(err), 'error')
    }
  }

  return (
    <Drawer
      open
      wide
      onClose={onClose}
      title={detail ? detail.name : '商机详情'}
      subtitle={
        detail ? (
          <span className="drawer-title-meta">
            {detail.opportunity_no} · <span className="stage-pill">{detail.stage}</span> {detail.stage_label}
          </span>
        ) : null
      }
      footer={
        detail ? (
          <div className="drawer-actions">
            <span className="muted">v{detail.version} · 更新于 {dateTimeText(detail.updated_at)}</span>
            <div>
              <button type="button" className="button ghost small" onClick={() => setModal('rollback')}>
                <RotateCcw size={15} /> 回退
              </button>
              <button type="button" className="button ghost small" onClick={() => setModal('probability')}>
                <PencilLine size={15} /> 概率
              </button>
              <button type="button" className="button primary small" onClick={() => setModal('transition')}>
                推进阶段 <ArrowRight size={15} />
              </button>
            </div>
          </div>
        ) : null
      }
    >
      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}
      {!detail ? (
        <Spinner />
      ) : (
        <div className="detail-stack">
          <section className="detail-hero">
            <div>
              <span className="eyebrow">预计金额</span>
              <strong className="detail-amount">{money(detail.amount)}</strong>
              <span className="muted">
                {detail.customer_name || '未关联客户'} · {detail.product_line} · {detail.owner_name || detail.owner_id || '未分配'}
              </span>
            </div>
            <div className="detail-kpis">
              <div>
                <span>有效概率</span>
                <strong>{percent(detail.effective_probability)}</strong>
                <small>{detail.probability_source === 'manual' ? '人工覆盖' : '规则计算'}</small>
              </div>
              <div>
                <span>加权金额</span>
                <strong>{money(detail.weighted_amount, true)}</strong>
                <small>{detail.forecast_excluded ? '不计入预测' : '计入预测'}</small>
              </div>
              <div>
                <span>预计关闭</span>
                <strong>{dateText(detail.expected_close_date)}</strong>
                <small className={detail.is_overdue ? 'danger-text' : ''}>
                  {detail.is_overdue ? '阶段停留超期' : relativeDue(detail.stage_due_at)}
                </small>
              </div>
            </div>
          </section>

          <section className="stage-rail">
            {STAGES.map((stage) => {
              const current = stage.code === detail.stage
              const done = STAGES.findIndex((s) => s.code === stage.code) < STAGES.findIndex((s) => s.code === detail.stage)
              return (
                <div key={stage.code} className={`stage-node ${current ? 'current' : ''} ${done ? 'done' : ''}`}>
                  <span>{stage.code}</span>
                  <small>{stage.label}</small>
                </div>
              )
            })}
          </section>

          <div className="tabs">
            {[
              ['overview', '概览'],
              ['timeline', '时间线'],
              ['approvals', '审批'],
              ['files', '附件'],
            ].map(([key, label]) => (
              <button key={key} type="button" className={tab === key ? 'active' : ''} onClick={() => setTab(key as typeof tab)}>
                {label}
              </button>
            ))}
          </div>

          {tab === 'overview' ? (
            <div className="detail-grid">
              <section className="detail-card">
                <h3>关键字段</h3>
                <dl className="fact-list">
                  <div><dt>客户集团</dt><dd>{detail.customer?.group_name || detail.customer_group_name || '—'}</dd></div>
                  <div><dt>矿井 / 工作面</dt><dd>{detail.mine?.name || '—'} / {detail.workface_name || '—'}</dd></div>
                  <div><dt>区域</dt><dd>{REGIONS.find((r) => r.code === detail.region_code)?.label || detail.region_code}</dd></div>
                  <div><dt>来源</dt><dd>{detail.source === 'seed' ? '演示种子' : detail.source}</dd></div>
                  <div><dt>关联方状态</dt><dd>{detail.customer?.related_party_status || 'unknown'}</dd></div>
                  <div><dt>客户完整度</dt><dd>{detail.customer?.completeness ?? '—'}%</dd></div>
                </dl>
              </section>
              <section className="detail-card">
                <h3>闸门检查</h3>
                <div className="gate-list">
                  {detail.gates?.slice(0, 8).map((gate) => (
                    <div className={`gate-row ${gate.status}`} key={`${gate.gate_code}-${gate.checked_at}`}>
                      <Badge tone={gate.status === 'block' ? 'red' : 'green'}>{gate.status === 'block' ? '阻断' : '通过'}</Badge>
                      <div>
                        <strong>{GATE_LABELS[gate.gate_code] || gate.gate_code}</strong>
                        <span>{gate.message}</span>
                      </div>
                    </div>
                  ))}
                  {!detail.gates?.length ? <p className="muted">暂无闸门检查记录。</p> : null}
                </div>
              </section>
              <section className="detail-card">
                <h3>待办与动作</h3>
                <div className="mini-list">
                  {detail.todos?.map((todo) => (
                    <Link to={`/todos?focus=${todo.id}`} key={todo.id} className="mini-row">
                      <Badge tone={todo.status === 'open' ? 'amber' : 'neutral'}>{TODO_TYPES[todo.type] || todo.type}</Badge>
                      <span>{todo.title}</span>
                      <small>{relativeDue(todo.due_at)}</small>
                    </Link>
                  ))}
                  {!detail.todos?.length ? <p className="muted">当前没有关联待办。</p> : null}
                </div>
              </section>
              <section className="detail-card">
                <h3>撞单与审批</h3>
                {detail.duplicates?.filter((item) => item.status === 'pending').length ? (
                  detail.duplicates
                    .filter((item) => item.status === 'pending')
                    .map((item) => (
                      <div className="duplicate-box" key={item.id}>
                        <div>
                          <strong>疑似撞单</strong>
                          <span>{(item.match_keys || []).join(' / ') || '同客户 / 工作面 / 产品线'}</span>
                        </div>
                        <div className="inline-actions">
                          <button type="button" className="button ghost small" onClick={() => void resolveDuplicate(item.id, 'keep_both')}>
                            保留双方
                          </button>
                          <button type="button" className="button ghost small" onClick={() => void resolveDuplicate(item.id, 'not_duplicate')}>
                            非重复
                          </button>
                          <button type="button" className="button primary small" onClick={() => void resolveDuplicate(item.id, 'merge')}>
                            合并到本商机
                          </button>
                        </div>
                      </div>
                    ))
                ) : (
                  <p className="muted">没有待处理撞单。</p>
                )}
                <div className="approval-strip">
                  <button type="button" className="button ghost small" onClick={() => setModal('approval')}>
                    <ShieldCheck size={15} /> 发起审批
                  </button>
                  {(detail.approvals || []).slice(0, 4).map((item) => (
                    <Link className="approval-chip" key={item.id} to={`/approvals?focus=${item.id}`}>
                      {item.gate_code} · {item.status}
                    </Link>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

          {tab === 'timeline' ? (
            <div className="timeline">
              {(detail.history || []).map((item, index) => (
                <div className="timeline-row" key={`${item.id}-${index}`}>
                  <span className="timeline-dot" />
                  <div>
                    <strong>
                      {item.action === 'advance' ? '推进' : item.action === 'rollback' ? '回退' : item.action}
                      {item.from_stage ? ` ${item.from_stage} → ${item.to_stage}` : ''}
                    </strong>
                    <p>{item.reason || item.impact || '无备注'}</p>
                    <small>{dateTimeText(item.created_at)} · {item.operator_id || 'system'}</small>
                  </div>
                </div>
              ))}
              {(detail.probability_history || []).map((item, index) => (
                <div className="timeline-row" key={`prob-${index}`}>
                  <span className="timeline-dot alt" />
                  <div>
                    <strong>概率 {item.effective_probability}%</strong>
                    <p>{item.manual_reason || '规则重算'}</p>
                    <small>{dateTimeText(item.created_at)}</small>
                  </div>
                </div>
              ))}
              {!detail.history?.length && !detail.probability_history?.length ? <EmptyState title="还没有时间线记录" /> : null}
            </div>
          ) : null}

          {tab === 'approvals' ? (
            <div className="approval-list">
              {(detail.approvals || []).map((item) => (
                <div className="approval-card" key={item.id}>
                  <div>
                    <strong>{GATE_LABELS[item.gate_code] || item.gate_code}</strong>
                    <span>{item.request_no}</span>
                  </div>
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                  <div className="step-inline">
                    {(item.steps || []).map((step: Json) => (
                      <span key={step.step_no} className={`step-chip ${step.status}`}>
                        {step.step_no}. {ROLE_LABELS[step.approver_role] || step.approver_role}
                      </span>
                    ))}
                  </div>
                  <Link className="text-link" to={`/approvals?focus=${item.id}`}>
                    查看审批 <ArrowRight size={14} />
                  </Link>
                </div>
              ))}
              {!detail.approvals?.length ? (
                <EmptyState
                  title="还没有审批单"
                  description="R4 新客户例外、R6 关联方、撞单合并可在此发起。"
                  icon={<ShieldCheck size={22} />}
                />
              ) : null}
            </div>
          ) : null}

          {tab === 'files' ? (
            <section className="detail-card">
              <div className="section-head">
                <div>
                  <h3>附件</h3>
                  <p className="muted">文件存储在 MinIO 的 sales-attachments 桶；服务不可用时上传会明确失败，不落空记录。</p>
                </div>
                <div>
                  <input
                    ref={uploadRef}
                    type="file"
                    hidden
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) void upload(file)
                      event.target.value = ''
                    }}
                  />
                  <button type="button" className="button ghost small" onClick={() => uploadRef.current?.click()}>
                    <Upload size={15} /> 上传附件
                  </button>
                </div>
              </div>
              <div className="file-list">
                {attachments.map((file) => (
                  <div className="file-row" key={file.id}>
                    <FileText size={18} />
                    <div>
                      <strong>{file.file_name}</strong>
                      <span>{Math.ceil((file.size_bytes || 0) / 1024)} KB · {dateTimeText(file.created_at)}</span>
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => void api.download(`/attachments/${file.id}/download`, file.file_name)}
                      aria-label="下载"
                    >
                      <ArrowDownToLine size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button danger"
                      onClick={() => void removeAttachment(file.id)}
                      aria-label="删除"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                {!attachments.length ? <EmptyState title="还没有附件" icon={<Paperclip size={22} />} /> : null}
              </div>
            </section>
          ) : null}
        </div>
      )}

      {detail ? (
        <>
          <TransitionModal
            open={modal === 'transition'}
            opportunity={detail}
            onClose={() => setModal('')}
            onDone={async () => {
              setModal('')
              await load()
              onChanged()
            }}
          />
          <RollbackModal
            open={modal === 'rollback'}
            opportunity={detail}
            onClose={() => setModal('')}
            onDone={async () => {
              setModal('')
              await load()
              onChanged()
            }}
          />
          <ProbabilityModal
            open={modal === 'probability'}
            opportunity={detail}
            onClose={() => setModal('')}
            onDone={async () => {
              setModal('')
              await load()
              onChanged()
            }}
          />
          <ApprovalRequestModal
            open={modal === 'approval'}
            opportunity={detail}
            onClose={() => setModal('')}
            onDone={async () => {
              setModal('')
              await load()
              onChanged()
            }}
          />
        </>
      ) : null}
    </Drawer>
  )
}

function TransitionModal({
  open,
  opportunity,
  onClose,
  onDone,
}: {
  open: boolean
  opportunity: Opportunity
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const { push } = useToast()
  const target = nextStage(opportunity.stage)
  const [reason, setReason] = useState('')
  const [result, setResult] = useState<'won' | 'lost'>('won')
  const [lostReason, setLostReason] = useState('')
  const [lostNote, setLostNote] = useState('')
  const [lostReasons, setLostReasons] = useState<Array<{ code: string; label: string; requires_note: boolean }>>([])
  const [contractNo, setContractNo] = useState('')
  const [contractAmount, setContractAmount] = useState(String(opportunity.contract_amount || opportunity.amount || ''))
  const [contractDate, setContractDate] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open && target === 'S8') {
      api
        .get<{ items: Array<{ code: string; label: string; requires_note: boolean }> }>('/lost-reason-codes')
        .then((data) => setLostReasons(data.items))
        .catch(() => undefined)
    }
  }, [open, target])

  async function submit() {
    setError('')
    setSaving(true)
    try {
      await api.post(`/opportunities/${opportunity.id}/transition`, {
        to_stage: target,
        expected_version: opportunity.version,
        reason: reason || undefined,
        result: target === 'S8' ? result : undefined,
        lost_reason_code: target === 'S8' && result === 'lost' ? lostReason : undefined,
        lost_reason_note: target === 'S8' && result === 'lost' ? lostNote : undefined,
        contract_no: target === 'S9' ? contractNo : undefined,
        contract_amount: target === 'S9' ? Number(contractAmount) : undefined,
        contract_effective_date: target === 'S9' ? contractDate : undefined,
      })
      push('阶段已推进', 'success')
      await onDone()
    } catch (err: unknown) {
      const context = err && typeof err === 'object' && 'context' in err ? (err as { context?: Json }).context : undefined
      const gates = context?.blocked as Gate[] | undefined
      setError(gates?.map((gate) => gate.message).join('；') || errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title={`推进到 ${target ? `${target} ${stageLabel(target)}` : '下一阶段'}`}
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={!target || saving}>
            {saving ? '提交中…' : '确认推进'}
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      {!target ? (
        <p>当前阶段已到合同生效，无法继续推进。</p>
      ) : (
        <div className="form-stack">
          <p className="muted">只允许推进到相邻阶段。系统会重新检查必填字段、示范面、报价冲突与审批闸门。</p>
          {target === 'S8' ? (
            <>
              <Field label="结果" required>
                <select value={result} onChange={(event) => setResult(event.target.value as 'won' | 'lost')}>
                  <option value="won">中标</option>
                  <option value="lost">失标</option>
                </select>
              </Field>
              {result === 'lost' ? (
                <>
                  <Field label="失标原因" required>
                    <select value={lostReason} onChange={(event) => setLostReason(event.target.value)}>
                      <option value="">请选择</option>
                      {lostReasons.map((item) => (
                        <option value={item.code} key={item.code}>
                          {item.code} · {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="失标说明">
                    <textarea rows={3} value={lostNote} onChange={(event) => setLostNote(event.target.value)} />
                  </Field>
                </>
              ) : null}
            </>
          ) : null}
          {target === 'S9' ? (
            <>
              <Field label="合同编号" required>
                <input value={contractNo} onChange={(event) => setContractNo(event.target.value)} />
              </Field>
              <div className="form-grid">
                <Field label="合同金额">
                  <input value={contractAmount} onChange={(event) => setContractAmount(event.target.value)} inputMode="decimal" />
                </Field>
                <Field label="生效日期">
                  <input type="date" value={contractDate} onChange={(event) => setContractDate(event.target.value)} />
                </Field>
              </div>
            </>
          ) : null}
          <Field label="推进说明">
            <textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="记录本次推进的依据" />
          </Field>
          <div className="rule-note">
            <Check size={15} />
            <span>
              当前有效概率 {percent(opportunity.effective_probability)}；推进后按新阶段与超期状态重算，人工覆盖不自动继承。
            </span>
          </div>
        </div>
      )}
    </Modal>
  )
}

function RollbackModal({
  open,
  opportunity,
  onClose,
  onDone,
}: {
  open: boolean
  opportunity: Opportunity
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const { push } = useToast()
  const prior = STAGES.filter((stage) => STAGES.findIndex((s) => s.code === stage.code) < STAGES.findIndex((s) => s.code === opportunity.stage))
  const [target, setTarget] = useState(prior.at(-1)?.code || '')
  const [reason, setReason] = useState('')
  const [impact, setImpact] = useState('')
  const [remedy, setRemedy] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    setError('')
    setSaving(true)
    try {
      await api.post(`/opportunities/${opportunity.id}/rollback`, {
        to_stage: target,
        expected_version: opportunity.version,
        reason,
        impact,
        remedy,
      })
      push('阶段已回退', 'success')
      await onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title="回退阶段"
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={!target || saving}>
            确认回退
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <Field label="回退到" required>
          <select value={target} onChange={(event) => setTarget(event.target.value)}>
            {prior.map((stage) => (
              <option key={stage.code} value={stage.code}>
                {stage.code} · {stage.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="原因" required>
          <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        <Field label="影响" required>
          <textarea rows={2} value={impact} onChange={(event) => setImpact(event.target.value)} placeholder="对预测、合同、待办的影响" />
        </Field>
        <Field label="补救措施" required>
          <textarea rows={2} value={remedy} onChange={(event) => setRemedy(event.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}

function ProbabilityModal({
  open,
  opportunity,
  onClose,
  onDone,
}: {
  open: boolean
  opportunity: Opportunity
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const { push } = useToast()
  const [value, setValue] = useState(String(opportunity.manual_probability ?? opportunity.effective_probability))
  const [reason, setReason] = useState(opportunity.manual_reason || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    setError('')
    setSaving(true)
    try {
      await api.post(`/opportunities/${opportunity.id}/probability`, {
        manual_probability: value === '' ? null : Number(value),
        reason: reason || null,
        expected_version: opportunity.version,
      })
      push('概率已更新', 'success')
      await onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title="覆盖有效概率"
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={saving}>
            保存覆盖
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <div className="rule-note">
          <CircleAlert size={15} />
          <span>规则概率 {percent(opportunity.rule_probability)}。覆盖超过阈值时必须说明原因；清空数值可恢复规则概率。</span>
        </div>
        <Field label="人工概率（0–100）">
          <input type="number" min={0} max={100} value={value} onChange={(event) => setValue(event.target.value)} />
        </Field>
        <Field label="覆盖原因">
          <textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}

function ApprovalRequestModal({
  open,
  opportunity,
  onClose,
  onDone,
}: {
  open: boolean
  opportunity: Opportunity
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const { push } = useToast()
  const duplicates = (opportunity.duplicates || []).filter((item) => item.status === 'pending')
  const approvable = (opportunity.pending_gate_codes || []).filter((code) => ['R4', 'R6', 'DUPLICATE', 'R10'].includes(code))
  const [gate, setGate] = useState(approvable[0] || (duplicates.length ? 'DUPLICATE' : 'R4'))
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const gates = Array.from(new Set([...approvable, ...(duplicates.length ? ['DUPLICATE'] : [])]))

  async function submit() {
    setError('')
    setSaving(true)
    try {
      await api.post(`/opportunities/${opportunity.id}/approvals`, {
        gate_code: gate,
        reason,
        evidence: duplicates.length ? { duplicate_case_id: duplicates[0].id } : {},
      })
      push('审批已发起，审批引擎稍后接管', 'success')
      await onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title="发起审批"
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={!gate || reason.trim().length < 2 || saving}>
            提交审批
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <div className="rule-note">
          <ShieldCheck size={15} />
          <span>
            审批通过只解除闸门，不会自动推进阶段。R4 为 24h + 24h；R6 增加合规 48h；整体 7 天过期，过期不会自动通过。
          </span>
        </div>
        <Field label="审批闸门" required>
          <select value={gate} onChange={(event) => setGate(event.target.value)}>
            {gates.map((code) => (
              <option key={code} value={code}>
                {GATE_LABELS[code] || code}
              </option>
            ))}
            {!gates.length ? <option value="R4">R4 新客户例外</option> : null}
          </select>
        </Field>
        <Field label="申请说明" required>
          <textarea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="说明为什么需要破例、风险与补救措施" />
        </Field>
      </div>
    </Modal>
  )
}

function CreateOpportunityModal({
  open,
  options,
  identityRegion,
  ownerId,
  onClose,
  onCreated,
}: {
  open: boolean
  options: MasterOptions | null
  identityRegion: string
  ownerId: string
  onClose: () => void
  onCreated: (created: Opportunity) => void
}) {
  const [name, setName] = useState('')
  const [customerId, setCustomerId] = useState('')
  const [mineId, setMineId] = useState('')
  const [workfaceId, setWorkfaceId] = useState('')
  const [productLine, setProductLine] = useState('智能综采')
  const [amount, setAmount] = useState('1000000')
  const [closeDate, setCloseDate] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const customer = options?.customers.find((item) => item.id === customerId)
  const mines = options?.mines.filter((item) => item.customer_id === customerId) || []
  const workfaces = options?.workfaces.filter((item) => item.mine_id === mineId) || []
  const products = Array.from(new Set(options?.products.map((item) => item.product_line) || [])).filter(Boolean)

  async function submit() {
    setError('')
    setSaving(true)
    try {
      const created = await api.post<Opportunity>('/opportunities', {
        name,
        customer_id: customerId,
        mine_id: mineId || undefined,
        workface_id: workfaceId || undefined,
        product_line: productLine,
        amount: Number(amount),
        expected_close_date: closeDate || undefined,
        owner_id: ownerId,
        region_code: customer?.region_code || identityRegion,
        source: 'manual',
      })
      onCreated(created)
      setName('')
      setCustomerId('')
      setMineId('')
      setWorkfaceId('')
      setCloseDate('')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title="新建商机"
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="button primary"
            onClick={() => void submit()}
            disabled={!name || !customerId || !productLine || saving}
          >
            创建并打开
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <Field label="商机名称" required>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：塔山煤矿 8206 智能综采新建" />
        </Field>
        <Field label="客户" required>
          <select
            value={customerId}
            onChange={(event) => {
              setCustomerId(event.target.value)
              setMineId('')
              setWorkfaceId('')
            }}
          >
            <option value="">请选择客户</option>
            {options?.customers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.region_code}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="矿井">
            <select value={mineId} onChange={(event) => { setMineId(event.target.value); setWorkfaceId('') }}>
              <option value="">不指定</option>
              {mines.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </Field>
          <Field label="工作面">
            <select value={workfaceId} onChange={(event) => setWorkfaceId(event.target.value)}>
              <option value="">不指定</option>
              {workfaces.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="form-grid">
          <Field label="产品线" required>
            <select value={productLine} onChange={(event) => setProductLine(event.target.value)}>
              {products.length ? products.map((item) => <option key={item}>{item}</option>) : <option>智能综采</option>}
            </select>
          </Field>
          <Field label="预计金额">
            <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" />
          </Field>
        </div>
        <Field label="预计关闭日期" hint="S1→S2 必填，缺失会被阶段字段闸门拦截。">
          <input type="date" value={closeDate} onChange={(event) => setCloseDate(event.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}
