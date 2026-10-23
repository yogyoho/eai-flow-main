import {
  ArrowRight,
  CalendarClock,
  CircleDollarSign,
  Compass,
  Gauge,
  Layers3,
  ListChecks,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge, severityTone } from '../components/ui'
import { dateTimeText, money, percent, relativeDue, stageLabel, TODO_STATUS_LABELS, TODO_TYPES } from '../lib/format'
import { useSession } from '../App'

export default function Workbench() {
  const { summary } = useSession()
  const navigate = useNavigate()
  const metrics = summary.metrics
  const headline = metrics.blockers
    ? `${metrics.blockers} 项阻断待处置：先关闭风险，再确认预测。`
    : metrics.overdue_opportunities
      ? `${metrics.overdue_opportunities} 个商机阶段超期，今日优先补充推进动作。`
      : '今日商机与待办已同步，按阶段节奏推进即可。'
  const briefText =
    summary.brief.find((item) => item.kind === 'forecast')?.text ||
    summary.brief[0]?.text ||
    '预测随阶段与超期状态实时变化，所有金额来自当前销售快照。'
  const [selectedStage, setSelectedStage] = useState(
    () => summary.funnel.find((item) => item.overdue)?.stage || summary.funnel[0]?.stage || '',
  )
  const selected = summary.funnel.find((item) => item.stage === selectedStage) || summary.funnel[0]
  const selectedPosition = selected
    ? summary.funnel.findIndex((item) => item.stage === selected.stage) + 1
    : 0

  return (
    <div className="stack workbench">
      <section className="metric-grid">
        <MetricCard
          icon={<ListChecks size={18} />}
          label="今日待办"
          value={metrics.today_todos}
          hint={`${metrics.open_todos} 项未结`}
          to="/todos"
        />
        <MetricCard
          icon={<ShieldAlert size={18} />}
          label="待我审批"
          value={metrics.pending_approvals}
          hint={`${metrics.approved_approvals} 单已通过`}
          to="/approvals?mine=1"
          tone={metrics.pending_approvals ? 'amber' : undefined}
        />
        <MetricCard
          icon={<Gauge size={18} />}
          label="阻断项"
          value={metrics.blockers}
          hint="优先于普通待办"
          to="/todos?severity=blocker"
          tone={metrics.blockers ? 'red' : undefined}
        />
        <MetricCard
          icon={<CalendarClock size={18} />}
          label="阶段超期"
          value={metrics.overdue_opportunities}
          hint="需补充动作或发起审批"
          to="/opportunities?overdue=1"
          tone={metrics.overdue_opportunities ? 'amber' : undefined}
        />
        <MetricCard
          icon={<TrendingUp size={18} />}
          label="胜率"
          value={percent(metrics.win_rate)}
          hint="已结束商机口径"
          to="/opportunities"
        />
      </section>

      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">今日作战简报 · 系统摘要</span>
          <h2>{headline}</h2>
          <p>
            当前在管 {metrics.active_opportunities} 个商机，含税金额 {money(metrics.active_amount, true)}，
            加权预测 {money(metrics.weighted_forecast, true)}。加权值使用阶段概率与超期降权，不是承诺值。
          </p>
          <div className="hero-actions">
            <button type="button" className="button primary" onClick={() => navigate('/todos')}>
              处理待办 <ArrowRight size={16} />
            </button>
            <button type="button" className="button ghost" onClick={() => navigate('/opportunities')}>
              查看漏斗
            </button>
          </div>
        </div>
        <div className="hero-rail">
          <div className="hero-stat">
            <span>在管商机</span>
            <strong>{metrics.active_opportunities}</strong>
            <small>个活跃商机</small>
          </div>
          <div className="hero-stat">
            <span>加权预测</span>
            <strong>{money(metrics.weighted_forecast, true)}</strong>
            <small>在管 {money(metrics.active_amount, true)}</small>
          </div>
          <div className="hero-stat">
            <span>有效胜率</span>
            <strong>{percent(metrics.win_rate)}</strong>
            <small>已结束商机口径</small>
          </div>
          <div className="hero-stat">
            <span>今日阻断</span>
            <strong>{metrics.blockers}</strong>
            <small>不可跳过</small>
          </div>
          <div className="hero-signal">
            <Sparkles size={17} />
            <p>{briefText}</p>
          </div>
        </div>
      </section>

      <section className="panel funnel-panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">C1 · 商机漏斗</span>
            <h3>九阶段管道</h3>
          </div>
          <div className="legend">
            <span><i className="legend-dot" />当前阶段</span>
            <span><i className="legend-dot amber" />超期</span>
          </div>
        </header>
        <div className="pipe-wrap">
          <div className="pipe-rail" aria-label="九阶段管道">
            {summary.funnel.map((item) => {
              const detail = `${item.label}：${item.count} 个在管，含税 ${money(item.amount, true)}，加权 ${money(item.weighted_amount, true)}${item.overdue ? `，${item.overdue} 个超期` : ''}`
              return (
                <button
                  type="button"
                  className={`pipe-node ${selected?.stage === item.stage ? 'is-active' : ''} ${item.overdue ? 'has-overdue' : ''}`}
                  key={item.stage}
                  aria-pressed={selected?.stage === item.stage}
                  onClick={() => setSelectedStage(item.stage)}
                  title={detail}
                >
                  <span className="pipe-node-dot">{item.stage}</span>
                  <strong>{item.label}</strong>
                  <em>{item.count} 个</em>
                </button>
              )
            })}
          </div>
          {selected ? (
            <div className="pipe-detail" id="pipe-detail" aria-live="polite">
              <div className="pipe-identity">
                <span className="pipe-detail-kicker">
                  {selected.stage} · 第 {selectedPosition} / {summary.funnel.length} 阶段
                </span>
                <h4>{selected.label}</h4>
                <span className="pipe-context">C1 · 商机漏斗</span>
              </div>
              <div className="pipe-metrics">
                <div><span>在管商机</span><strong>{selected.count} 个</strong></div>
                <div><span>含税金额</span><strong>{money(selected.amount, true)}</strong></div>
                <div><span>加权金额</span><strong>{money(selected.weighted_amount, true)}</strong></div>
                <div><span>超期</span><strong className={selected.overdue ? 'danger-text' : undefined}>{selected.overdue ? `${selected.overdue} 个` : '0 个'}</strong></div>
              </div>
              <div className="pipe-side">
                <span className={`pipe-status ${selected.overdue ? 'is-warn' : 'is-ok'}`}>
                  {selected.overdue ? `${selected.overdue} 个阶段超期` : '阶段状态正常'}
                </span>
                <button
                  type="button"
                  className="pipe-link"
                  onClick={() => navigate(`/opportunities?stage=${selected.stage}`)}
                >
                  查看阶段商机 <ArrowRight size={14} />
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <div className="two-column sync-panels">
        <section className="panel queue-panel">
          <header className="panel-head">
            <div>
              <span className="eyebrow">A02 · 统一待办</span>
              <h3>优先队列</h3>
            </div>
            <Link className="text-link" to="/todos">
              全部待办 <ArrowRight size={14} />
            </Link>
          </header>
          <div className="compact-list">
            {summary.top_todos.map((todo) => (
              <Link className="compact-row" key={todo.id} to={`/todos?focus=${todo.id}`}>
                <Badge tone={severityTone(todo.severity)}>{TODO_TYPES[todo.type] || todo.type}</Badge>
                <div className="compact-main">
                  <strong>{todo.title}</strong>
                  <span>
                    {todo.opportunity_name || todo.todo_no} · {relativeDue(todo.due_at)}
                  </span>
                </div>
                <Badge tone={todo.is_overdue ? 'red' : 'neutral'}>{todo.severity === 'blocker' ? '阻断' : TODO_STATUS_LABELS[todo.status] || todo.status}</Badge>
              </Link>
            ))}
            {!summary.top_todos.length ? <p className="muted pad">当前没有待办。</p> : null}
          </div>
        </section>

        <section className="panel queue-panel">
          <header className="panel-head">
            <div>
              <span className="eyebrow">关注商机</span>
              <h3>下一步动作</h3>
            </div>
            <Link className="text-link" to="/opportunities">
              全部商机 <ArrowRight size={14} />
            </Link>
          </header>
          <div className="compact-list">
            {summary.top_opportunities.map((opp) => (
              <Link className="compact-row" key={opp.id} to={`/opportunities?focus=${opp.id}`}>
                <span className="stage-pill">{opp.stage}</span>
                <div className="compact-main">
                  <strong>{opp.name}</strong>
                  <span>
                    {opp.customer_name || opp.customer_group_name || '未关联客户'} · {opp.product_line}
                  </span>
                </div>
                <div className="compact-number">
                  <strong>{money(opp.amount, true)}</strong>
                  <span className={opp.is_overdue ? 'danger-text' : 'muted'}>{opp.is_overdue ? '阶段超期' : stageLabel(opp.stage)}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <section className="panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">快捷入口</span>
            <h3>常用作业面</h3>
          </div>
          <span className="tag">按角色配置</span>
        </header>
        <div className="quick-grid">
          {summary.quick_entries.map((entry) => (
            <Link className="quick-tile" key={`${entry.kind}-${entry.link}`} to={entry.link}>
              <span className="q-ic">
                <ArrowRight size={14} />
              </span>
              {entry.label}
            </Link>
          ))}
        </div>
      </section>

      <section className="panel insight-panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">今日简报</span>
            <h3>系统给销售的三句话</h3>
          </div>
          <Compass size={20} className="muted" />
        </header>
        <div className="insight-grid">
          {summary.brief.map((item) => (
            <Link className={`insight-card ${item.kind}`} key={item.text} to={item.link}>
              <span>{item.kind === 'todo' ? '行动' : item.kind === 'forecast' ? '预测' : item.kind === 'approval' ? '审批' : '数据'}</span>
              <p>{item.text}</p>
              <ArrowRight size={15} />
            </Link>
          ))}
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">未接入能力</span>
            <h3>明确占位，不造数字</h3>
          </div>
          <Badge tone="neutral">QW2 范围</Badge>
        </header>
        <div className="placeholder-grid">
          {summary.placeholders.map((item) => (
            <div className="placeholder-card" key={item.code}>
              <div className="placeholder-code">{item.code}</div>
              <strong>{item.label}</strong>
              <p>{item.hint}</p>
              <span className="placeholder-status">待接入</span>
            </div>
          ))}
        </div>
      </section>

      <footer className="page-foot">
        <Layers3 size={15} />
        <span>
          数据快照生成于 {dateTimeText(summary.data_as_of)}。商机与待办以本平台为准；客户、矿井、工作面等主数据为本地最小记录，
          请以来源系统复核。
        </span>
      </footer>
    </div>
  )
}

function MetricCard({
  icon,
  label,
  value,
  hint,
  to,
  tone,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  hint: string
  to: string
  tone?: 'amber' | 'red'
}) {
  return (
    <Link className={`metric-card ${tone ? `tone-${tone}` : ''}`} to={to}>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
      <CircleDollarSign className="metric-watermark" size={48} />
    </Link>
  )
}
