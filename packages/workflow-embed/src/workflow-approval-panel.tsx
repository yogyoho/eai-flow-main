import {
  CheckCircle2,
  CircleAlert,
  FileText,
  History,
  RefreshCw,
  RotateCcw,
  Workflow,
  X,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'

import type {
  Json,
  WorkflowApprovalPanelProps,
  WorkflowFormSnapshot,
  WorkflowView,
} from './types.js'

type DecisionAction = 'approve' | 'reject' | 'return'

interface FormField {
  key: string
  label: string
  type?: string
  required?: boolean
  span?: number
}

interface FormSchemaView {
  columns: number
  fields: FormField[]
}

interface ChartPoint {
  x: number
  y: number
}

interface ChartNode {
  node: Json
  x: number
  y: number
  width: number
  height: number
  type: number
  label: string
}

interface ChartLink {
  key: string
  skip: Json
  source: ChartNode
  target: ChartNode
  points: ChartPoint[]
  labelX: number
  labelY: number
  rejected: boolean
  status: number
}

const STATUS_COLORS: Record<number, string> = {
  0: '#cbd5e1',
  1: '#f59e0b',
  2: '#10b981',
}

const ACTION_LABELS: Record<string, string> = {
  approve: '通过',
  reject: '驳回',
  return: '退回申请人',
}

function isReturnHistory(item: Json): boolean {
  if (String(item.skip_type ?? '').toUpperCase() !== 'REJECT') return false
  const targets = String(item.target_node_code ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  return targets.includes('start') || String(item.target_node_name ?? '').includes('发起')
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function text(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function dateText(value: unknown): string {
  if (!value || typeof value !== 'string') return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN')
}

function coordinate(value: unknown): [number, number] | null {
  if (typeof value !== 'string') return null
  const head = value.split('|')[0]
  const [x, y] = head.split(',')
  const px = Number(x)
  const py = Number(y)
  return Number.isFinite(px) && Number.isFinite(py) ? [px, py] : null
}

function nodeSize(type: number): { width: number; height: number } {
  if (type === 0 || type === 2) return { width: 56, height: 56 }
  if (type >= 3) return { width: 60, height: 60 }
  return { width: 176, height: 52 }
}

function chartNode(node: Json, index: number): ChartNode | null {
  const point = coordinate(node.coordinate)
  if (!point) return null
  const type = Number(node.nodeType ?? 1)
  const size = nodeSize(type)
  return {
    node,
    x: point[0],
    y: point[1],
    width: size.width,
    height: size.height,
    type,
    label: String(node.nodeName || node.nodeCode || `节点 ${index + 1}`),
  }
}

/**
 * Build the read-only edge route from the node boxes, not from stored edge
 * coordinates. This keeps arrows attached even when a definition carries an
 * older or custom path that no longer matches the node positions.
 */
function chartLink(
  skip: Json,
  source: ChartNode,
  target: ChartNode,
  rejectOffset: number,
): ChartLink {
  const rejected = String(skip.skipType ?? '').toUpperCase() === 'REJECT'
  let points: ChartPoint[]
  let labelX: number
  let labelY: number

  if (rejected) {
    const startY = source.y + source.height / 2
    const endY = target.y + target.height / 2
    const routeY = Math.max(startY, endY) + 64 + rejectOffset * 26
    points = [
      { x: source.x, y: startY },
      { x: source.x, y: routeY },
      { x: target.x, y: routeY },
      { x: target.x, y: endY },
    ]
    labelX = (source.x + target.x) / 2
    labelY = routeY + 16
  } else if (Math.abs(source.y - target.y) < 6) {
    const direction = target.x >= source.x ? 1 : -1
    points = [
      { x: source.x + (direction * source.width) / 2, y: source.y },
      { x: target.x - (direction * target.width) / 2, y: target.y },
    ]
    labelX = (source.x + target.x) / 2
    labelY = source.y - 16
  } else {
    const startY = source.y + (target.y >= source.y ? source.height / 2 : -source.height / 2)
    const endY = target.y + (target.y >= source.y ? -target.height / 2 : target.height / 2)
    const midY = (startY + endY) / 2
    points = [
      { x: source.x, y: startY },
      { x: source.x, y: midY },
      { x: target.x, y: midY },
      { x: target.x, y: endY },
    ]
    labelX = (source.x + target.x) / 2
    labelY = midY - 10
  }

  return {
    key: `${skip.nowNodeCode ?? source.node.nodeCode}-${skip.nextNodeCode ?? target.node.nodeCode}-${rejectOffset}`,
    skip,
    source,
    target,
    points,
    labelX,
    labelY,
    rejected,
    status: Number(skip.status ?? 0),
  }
}

function formSchema(form?: WorkflowFormSnapshot | null): FormSchemaView {
  const direct = form?.schema
  if (Array.isArray(direct?.fields) && direct.fields.length) {
    return {
      columns: direct.layout?.columns === 1 ? 1 : 2,
      fields: direct.fields,
    }
  }
  if (typeof form?.formContent === 'string') {
    try {
      const parsed = JSON.parse(form.formContent) as {
        layout?: { columns?: number }
        fields?: FormField[]
      }
      if (Array.isArray(parsed.fields)) {
        return {
          columns: parsed.layout?.columns === 1 ? 1 : 2,
          fields: parsed.fields,
        }
      }
    } catch {
      // The form content is not required for the read-only panel.
    }
  }
  return { columns: 2, fields: [] }
}

function fieldSpan(field: FormField): 1 | 2 {
  if (field.span === 1) return 1
  if (field.span === 2) return 2
  return field.type === 'textarea' ? 2 : 1
}

function formVariables(view: WorkflowView): Json {
  const raw = view.instance?.variable ?? view.instance?.variables
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as Json
    } catch {
      return {}
    }
  }
  return raw && typeof raw === 'object' ? (raw as Json) : {}
}

function WorkflowMiniChart({ chart }: { chart?: Json | null }) {
  const markerBase = `wf-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, '') || 'chart'}`
  const markerColors = {
    done: '#10b981',
    todo: '#f59e0b',
    idle: '#cbd5e1',
    reject: '#e11d48',
  }

  const layout = useMemo(() => {
    const sourceNodes: Json[] = Array.isArray(chart?.nodeList) ? chart.nodeList : []
    const nodes = sourceNodes
      .map((node, index) => chartNode(node, index))
      .filter((node): node is ChartNode => node !== null)
    const byCode = new Map(nodes.map((node) => [String(node.node.nodeCode ?? ''), node]))
    const links: ChartLink[] = []
    let rejectOffset = 0
    for (const source of nodes) {
      const skips: Json[] = Array.isArray(source.node.skipList) ? source.node.skipList : []
      for (const skip of skips) {
        const target = byCode.get(String(skip.nextNodeCode ?? ''))
        if (!target) continue
        const rejected = String(skip.skipType ?? '').toUpperCase() === 'REJECT'
        const offset = rejected ? rejectOffset++ : 0
        links.push(chartLink(skip, source, target, offset))
      }
    }

    // Overlapping edges share path segments; paint unvisited (grey) ones
    // first so traversed and pending paths stay visible on top. The sort is
    // stable, so edges of the same status keep their natural order.
    links.sort((a, b) => a.status - b.status)

    const xs = [
      ...nodes.flatMap((node) => [node.x - node.width / 2, node.x + node.width / 2]),
      ...links.flatMap((link) => link.points.map((point) => point.x)),
      ...links.map((link) => link.labelX),
    ]
    const ys = [
      ...nodes.flatMap((node) => [node.y - node.height / 2, node.y + node.height / 2]),
      ...links.flatMap((link) => link.points.map((point) => point.y)),
      ...links.map((link) => link.labelY),
    ]
    if (!xs.length || !ys.length) {
      return { nodes, links, viewBox: null }
    }
    const minX = Math.min(...xs) - 70
    const maxX = Math.max(...xs) + 70
    const minY = Math.min(...ys) - 50
    const maxY = Math.max(...ys) + 50
    return {
      nodes,
      links,
      viewBox: `${minX} ${minY} ${Math.max(520, maxX - minX)} ${Math.max(240, maxY - minY)}`,
    }
  }, [chart])

  if (!layout.nodes.length) {
    const sourceNodes: Json[] = Array.isArray(chart?.nodeList) ? chart.nodeList : []
    if (!sourceNodes.length) return <p className="wf-empty">暂无流程图数据</p>
    return (
      <div className="wf-node-list">
        {sourceNodes.map((node, index) => (
          <span className="wf-node-chip" key={`${node.nodeCode ?? 'node'}-${index}`}>
            <i className={`wf-dot wf-dot-${Number(node.status ?? 0)}`} />
            {node.nodeName || node.nodeCode || `节点 ${index + 1}`}
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="wf-chart">
      <svg viewBox={layout.viewBox ?? undefined} role="img" aria-label="审批流程图">
        <defs>
          {Object.entries(markerColors).map(([tone, color]) => (
            <marker
              key={tone}
              id={`${markerBase}-${tone}`}
              viewBox="0 0 10 10"
              markerWidth="7"
              markerHeight="7"
              refX="9"
              refY="5"
              orient="auto"
            >
              <path
                d="M 1 1 L 9 5 L 1 9"
                fill="none"
                stroke={color}
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </marker>
          ))}
        </defs>

        {layout.links.map((link) => {
          const traversedReject = link.rejected && link.status === 2
          const tone = traversedReject
            ? 'reject'
            : link.status === 2
              ? 'done'
              : link.status === 1
                ? 'todo'
                : 'idle'
          const color = markerColors[tone]
          return (
            <g key={link.key}>
              <polyline
                points={link.points.map((point) => `${point.x},${point.y}`).join(' ')}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeDasharray={traversedReject ? '6 4' : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
                markerEnd={`url(#${markerBase}-${tone})`}
              />
              {link.skip.skipName ? (
                <text
                  x={link.labelX}
                  y={link.labelY}
                  textAnchor="middle"
                  fontSize={10.5}
                  fill={traversedReject ? markerColors.reject : link.status === 1 ? '#b45309' : '#64748b'}
                  stroke="#ffffff"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {link.skip.skipName}
                </text>
              ) : null}
            </g>
          )
        })}

        {layout.nodes.map((item, index) => {
          const color = STATUS_COLORS[Number(item.node.status ?? 0)] || '#cbd5e1'
          const fill = color === '#cbd5e1' ? '#f8fafc' : `${color}18`
          return (
            <g key={`${item.node.nodeCode ?? 'node'}-${index}`}>
              <title>{item.label}</title>
              {item.type === 0 || item.type === 2 ? (
                <circle cx={item.x} cy={item.y} r={28} fill={fill} stroke={color} strokeWidth={2} />
              ) : item.type >= 3 ? (
                <polygon
                  points={`${item.x},${item.y - 30} ${item.x + 30},${item.y} ${item.x},${item.y + 30} ${item.x - 30},${item.y}`}
                  fill={fill}
                  stroke={color}
                  strokeWidth={2}
                />
              ) : (
                <rect
                  x={item.x - item.width / 2}
                  y={item.y - item.height / 2}
                  width={item.width}
                  height={item.height}
                  rx={10}
                  fill={fill}
                  stroke={color}
                  strokeWidth={2}
                />
              )}
              <text x={item.x} y={item.y + 4} textAnchor="middle" fontSize={11} fill="#334155">
                {item.label}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="wf-legend">
        <span><i className="wf-dot wf-dot-0" />未开始</span>
        <span><i className="wf-dot wf-dot-1" />待处理</span>
        <span><i className="wf-dot wf-dot-2" />已完成</span>
        {layout.links.some((link) => link.rejected) ? (
          <span><i className="wf-dot" style={{ background: markerColors.reject }} />退回 / 驳回</span>
        ) : null}
      </div>
    </div>
  )
}

function FormSnapshot({ view }: { view: WorkflowView }) {
  const { columns, fields } = formSchema(view.form)
  const variables = formVariables(view)
  if (!fields.length) return <p className="wf-empty">该流程没有绑定表单字段</p>
  return (
    <div className={`wf-form-grid${columns === 1 ? ' wf-form-grid-single' : ''}`}>
      {fields.map((field, index) => (
        <div
          className={`wf-form-field${columns === 2 && fieldSpan(field) === 2 ? ' wf-form-field-wide' : ''}`}
          key={`${field.key}-${index}`}
        >
          <span>{field.label}{field.required ? ' *' : ''}</span>
          <strong>{text(variables[field.key])}</strong>
        </div>
      ))}
    </div>
  )
}

export function WorkflowApprovalPanel({
  approvalId,
  client,
  refreshToken = 0,
  onChanged,
  onError,
  className = '',
  layout = 'split',
}: WorkflowApprovalPanelProps) {
  const panelClassName = `wf-panel ${layout === 'stacked' ? 'wf-layout-stacked' : ''} ${className}`
    .replace(/\s+/g, ' ')
    .trim();
  const clientRef = useRef(client)
  const onErrorRef = useRef(onError)
  const requestRef = useRef(0)
  clientRef.current = client
  onErrorRef.current = onError

  const [view, setView] = useState<WorkflowView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [decision, setDecision] = useState<DecisionAction | null>(null)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const commentId = useId()

  const load = useCallback(async () => {
    const ticket = ++requestRef.current
    setLoading(true)
    try {
      const data = await clientRef.current.getWorkflow(approvalId)
      if (ticket !== requestRef.current) return
      setView(data)
      setError('')
    } catch (err) {
      if (ticket !== requestRef.current) return
      const message = errorText(err, 'workflow 审批视图加载失败')
      setError(message)
      onErrorRef.current?.(message)
    } finally {
      if (ticket === requestRef.current) setLoading(false)
    }
  }, [approvalId])

  useEffect(() => {
    void load()
  }, [load, refreshToken])

  useEffect(() => {
    if (!decision) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDecision(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [decision])

  async function submit() {
    if (!decision) return
    if ((decision === 'reject' || decision === 'return') && !comment.trim()) return
    setSaving(true)
    setError('')
    try {
      await clientRef.current.decide(approvalId, {
        action: decision,
        comment: comment.trim() || undefined,
        idempotency_key: `${decision}-${approvalId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      })
      setDecision(null)
      setComment('')
      await load()
      onChanged?.()
    } catch (err) {
      const message = errorText(err, '审批提交失败')
      setError(message)
      onErrorRef.current?.(message)
    } finally {
      setSaving(false)
    }
  }

  if (loading && !view) {
    return (
      <section className={panelClassName}>
        <div className="wf-loading">
          <i className="wf-spinner" />
          加载 workflow 审批视图…
        </div>
      </section>
    )
  }

  if (!view) {
    return (
      <section className={panelClassName}>
        <div className="wf-alert wf-alert-error">
          <CircleAlert size={15} />
          <span>{error || 'workflow 审批视图加载失败'}</span>
        </div>
      </section>
    )
  }

  if (!view.available && view.engine !== 'workflow_platform') return null

  const actions = view.capabilities?.actions ?? []
  const canDecide = Boolean(view.capabilities?.can_decide)
  const history = Array.isArray(view.history) ? view.history : []

  return (
    <section className={panelClassName} data-workflow-embed="true">
      <header className="wf-header">
        <div>
          <h3 className="wf-title"><Workflow size={18} /> Workflow 审批</h3>
          <p className="wf-subtitle">
            {view.available
              ? `${view.form?.formName || view.form?.formCode || '审批表单'} · 实例 ${view.platform_instance_id ?? '-'}`
              : view.message || 'workflow 平台暂不可用'}
          </p>
        </div>
        <button
          type="button"
          className="wf-btn wf-btn-ghost wf-btn-sm"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? 'wf-spin' : undefined} /> 刷新
        </button>
      </header>

      {error ? (
        <div className="wf-alert wf-alert-error">
          <CircleAlert size={15} />
          <span>{error}</span>
          <button type="button" className="wf-alert-close" onClick={() => setError('')} aria-label="关闭">
            <X size={14} />
          </button>
        </div>
      ) : null}

      {view.available ? (
        <>
          <div className="wf-grid">
            <div className="wf-card">
              <h4 className="wf-card-title"><FileText size={14} /> 表单快照</h4>
              <FormSnapshot view={view} />
            </div>
            <div className="wf-card">
              <h4 className="wf-card-title"><Workflow size={14} /> 流程图</h4>
              <WorkflowMiniChart chart={view.chart} />
            </div>
          </div>

          <div className="wf-card wf-history">
            <h4 className="wf-card-title"><History size={14} /> workflow 审批历史</h4>
            {history.length ? (
              <div className="wf-history-list">
                {history.map((item, index) => {
                  const rejected = String(item.skip_type ?? '').toUpperCase() === 'REJECT'
                  const passed = String(item.skip_type ?? '').toUpperCase() === 'PASS'
                  const returned = isReturnHistory(item)
                  return (
                    <div className="wf-history-row" key={`${item.id ?? index}`}>
                      {returned ? (
                        <RotateCcw size={15} className="wf-danger" />
                      ) : rejected ? (
                        <XCircle size={15} className="wf-danger" />
                      ) : (
                        <CheckCircle2 size={15} className="wf-success" />
                      )}
                      <div className="wf-history-main">
                        <strong>{item.node_name || item.node_code || '审批节点'}</strong>
                        <span>
                          {item.approver || '-'} · {returned ? '退回申请人' : rejected ? '驳回' : passed ? '通过' : '处理'}
                        </span>
                        {item.message ? <p>{item.message}</p> : null}
                      </div>
                      <small>{dateText(item.update_time || item.create_time)}</small>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="wf-empty">暂无 workflow 审批历史</p>
            )}
          </div>

          {canDecide ? (
            <div className="wf-actions">
              <span className="wf-hint">当前由你处理第 {view.capabilities?.active_step ?? '-'} 步</span>
              {actions.includes('return') ? (
                <button type="button" className="wf-btn wf-btn-ghost wf-btn-sm" onClick={() => { setComment(''); setDecision('return') }}>
                  <RotateCcw size={15} /> 退回申请人
                </button>
              ) : null}
              {actions.includes('reject') ? (
                <button type="button" className="wf-btn wf-btn-ghost wf-btn-sm" onClick={() => { setComment(''); setDecision('reject') }}>
                  <XCircle size={15} /> 驳回
                </button>
              ) : null}
              {actions.includes('approve') ? (
                <button type="button" className="wf-btn wf-btn-primary wf-btn-sm" onClick={() => { setComment(''); setDecision('approve') }}>
                  <CheckCircle2 size={15} /> 通过
                </button>
              ) : null}
            </div>
          ) : view.capabilities?.can_resubmit ? (
            <div className="wf-actions">
              <span className="wf-hint">审批已退回申请人，等待修改并重新提交</span>
            </div>
          ) : view.capabilities?.can_cancel ? (
            <div className="wf-actions">
              <span className="wf-hint">审批进行中，当前步骤由其他审批人处理</span>
            </div>
          ) : null}
        </>
      ) : (
        <div className="wf-unavailable">
          <CircleAlert size={16} />
          <span>{view.message || 'workflow 平台暂不可用，审批页面仍使用业务侧投影数据。'}</span>
        </div>
      )}

      {decision ? (
        <div
          className="wf-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setDecision(null)
          }}
        >
          <div className="wf-modal" role="dialog" aria-modal="true" aria-label={`${ACTION_LABELS[decision]}审批`}>
            <header className="wf-modal-head">
              <h2>{ACTION_LABELS[decision]}审批</h2>
              <button type="button" className="wf-icon-btn" onClick={() => setDecision(null)} aria-label="关闭">
                <X size={18} />
              </button>
            </header>
            <div className="wf-modal-body">
              {error ? (
                <div className="wf-alert wf-alert-error">
                  <CircleAlert size={15} />
                  <span>{error}</span>
                </div>
              ) : null}
              <div className={`wf-chip ${decision === 'approve' ? 'wf-chip-success' : 'wf-chip-danger'}`}>
                {ACTION_LABELS[decision]}
              </div>
              <p className="wf-modal-text">
                {decision === 'approve'
                  ? '确认通过该 workflow 审批任务？'
                  : decision === 'return'
                    ? '退回申请人修改：原审批单号和 workflow 实例保留，申请人重新提交后从第一步重新审批。'
                    : '驳回为终态，必须填写审批意见。'}
              </p>
              <label className="wf-label" htmlFor={commentId}>
                审批意见{decision === 'approve' ? '' : ' *'}
              </label>
              <textarea
                id={commentId}
                className="wf-textarea"
                rows={4}
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                autoFocus
              />
            </div>
            <footer className="wf-modal-foot">
              <button type="button" className="wf-btn wf-btn-ghost" onClick={() => setDecision(null)}>取消</button>
              <button
                type="button"
                className={`wf-btn ${decision === 'approve' ? 'wf-btn-primary' : 'wf-btn-danger'}`}
                onClick={() => void submit()}
                disabled={saving || ((decision === 'reject' || decision === 'return') && !comment.trim())}
              >
                {saving ? '提交中…' : `确认${ACTION_LABELS[decision]}`}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </section>
  )
}
